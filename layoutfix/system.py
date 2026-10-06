"""Read the selection, convert it, paste it back, and give the user their clipboard back.

Safety rules:
- Only one fix runs at a time, across processes (file lock).
- The clipboard is restored in a `finally`, and only if it still holds our own text.
- Images / files on the clipboard are never overwritten (Linux restores them, Windows/macOS refuse).
- Nothing is pasted unless something was really selected.
- No Ctrl+C is ever sent on Linux (it would interrupt a program running in a terminal).
"""
import os
import shutil
import subprocess
import sys
import time
import uuid

from . import clipboard, instance, safety
from .log import get as logger, notify

MAC = sys.platform == "darwin"
WIN = sys.platform.startswith("win")
WAYLAND = (not MAC and not WIN) and os.environ.get("XDG_SESSION_TYPE") == "wayland"

SELECT_FIRST = "Select (highlight) some text first, then press the hotkey."


# ---------------------------------------------------------------- key presses
def _keyboard():
    from pynput.keyboard import Controller
    return Controller()


def _release_modifiers(kb):
    from pynput.keyboard import Key
    for k in (Key.ctrl, Key.alt, Key.shift, Key.cmd):
        try:
            kb.release(k)
        except Exception:
            pass


def _chord(kb, *keys):
    for k in keys:
        kb.press(k)
    for k in reversed(keys):
        kb.release(k)


def _ydotool_socket():
    return os.environ.get("YDOTOOL_SOCKET") or f"/run/user/{os.getuid()}/.ydotool_socket"


def _ydotool_ready():
    return bool(shutil.which("ydotool")) and os.path.exists(_ydotool_socket())


def _ydotool(*codes):
    """Press and release a chord via ydotool (Wayland). Returns True when it succeeded."""
    env = {**os.environ, "YDOTOOL_SOCKET": _ydotool_socket()}
    seq = [f"{c}:1" for c in codes] + [f"{c}:0" for c in reversed(codes)]
    try:
        return subprocess.run(["ydotool", "key", *seq], env=env, timeout=5,
                              capture_output=True).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


_LINUX_KEYCODES = dict(ctrl=29, shift=42, alt=56, insert=110)
_ALL_MODIFIER_CODES = (29, 97, 42, 54, 56, 100)    # left/right ctrl, shift, alt. Never Super: a lone Super
                                                       # release opens the GNOME Activities overview.


def _ydotool_release_modifiers():
    env = {**os.environ, "YDOTOOL_SOCKET": _ydotool_socket()}
    try:
        subprocess.run(["ydotool", "key", *[f"{c}:0" for c in _ALL_MODIFIER_CODES]], env=env,
                       timeout=5, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        pass


# ---------------------------------------------------------------------- Linux
def _fix_linux(convert):
    """Convert the highlighted text (primary selection) and paste with Shift+Insert."""
    clip = clipboard.linux_backend(WAYLAND)
    if clip is None:
        notify("Install wl-clipboard (Wayland) or xclip (X11) to use this app on Linux.")
        return
    if WAYLAND and not _ydotool_ready():
        notify("Wayland needs ydotool with its ydotoold service running (see the README).")
        return

    text = clip.text("primary")
    if not text.strip():
        notify(SELECT_FIRST)
        return
    if len(text) > safety.MAX_CHARS:
        notify("The selection is too long to convert safely.")
        return
    out = convert(text)
    if out == text:
        return

    # Every wl-clipboard call briefly opens a window on GNOME (the dock flickers): keep the calls few.
    # Total per fix: read selection, read clipboard, write clipboard, write primary, restore clipboard.
    saved = clip.snapshot("clipboard")
    try:
        clip.write_text("clipboard", out)
        clip.write_text("primary", out)                   # terminals paste the primary selection
        time.sleep(0.25)                                  # let the user let go of the hotkey
        if WAYLAND:
            _ydotool_release_modifiers()
            if not _ydotool(_LINUX_KEYCODES["shift"], _LINUX_KEYCODES["insert"]):
                notify("Could not send the paste key. Is the ydotoold service running?")
        else:
            kb = _keyboard()
            _release_modifiers(kb)
            from pynput.keyboard import Key
            _chord(kb, Key.shift, Key.insert)
        time.sleep(0.35)                                  # let the app read the clipboard
    finally:
        clip.restore("clipboard", saved)


# ------------------------------------------------------------ Windows / macOS
def _fix_desktop(convert):
    import pyperclip
    from pynput.keyboard import Key

    if clipboard.has_non_text():
        notify("Your clipboard holds an image or files. Paste or clear it first so it is not lost.")
        return

    kb = _keyboard()
    # Ctrl+Insert / Shift+Insert also work in terminals, where Ctrl+C would interrupt the running program.
    copy_keys, paste_keys = ((Key.cmd, "c"), (Key.cmd, "v")) if MAC else ((Key.ctrl, Key.insert), (Key.shift, Key.insert))

    previous = pyperclip.paste()
    marker = f"layoutfix-{uuid.uuid4().hex}"
    ours = {marker}
    try:
        pyperclip.copy(marker)                            # tells us whether the copy really copied something
        time.sleep(0.3)                                   # let the user let go of the hotkey
        _release_modifiers(kb)
        _chord(kb, *copy_keys)
        text = marker
        for _ in range(12):                               # wait up to ~0.6 s for the copy to land
            time.sleep(0.05)
            text = pyperclip.paste()
            if text != marker:
                break
        if text == marker or not text.strip():
            notify(SELECT_FIRST)
            return
        if safety.looks_like_line_copy(text):
            notify(SELECT_FIRST)                          # the editor copied a whole line instead
            return
        if len(text) > safety.MAX_CHARS:
            notify("The selection is too long to convert safely.")
            return
        out = convert(text)
        if out == text:
            return
        ours.add(out)
        pyperclip.copy(out)
        time.sleep(0.05)
        _chord(kb, *paste_keys)
        time.sleep(0.6)                                   # some apps read the clipboard late
    finally:
        try:
            if pyperclip.paste() in ours:                 # don't clobber anything the user copied since
                pyperclip.copy(previous)
        except Exception:
            logger().exception("could not restore the clipboard")


def fix_selection(convert):
    lock = instance.try_lock("fix")
    if lock is None:                                      # another fix is already running
        logger().info("skipped: another fix is still running")
        return
    started = time.time()
    with lock:
        if MAC or WIN:
            _fix_desktop(convert)
        else:
            _fix_linux(convert)
    logger().info("fix finished in %.2fs", time.time() - started)
