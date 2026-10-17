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
from .log import Timeline, get as logger, notify

MAC = sys.platform == "darwin"
WIN = sys.platform.startswith("win")
WAYLAND = (not MAC and not WIN) and os.environ.get("XDG_SESSION_TYPE") == "wayland"

SELECT_FIRST = "Select (highlight) some text first, then press the hotkey."
HOTKEY_GRACE = 0.25      # seconds after the hotkey press (= process start) before we inject a key
PASTE_WAIT = 0.6         # longest wait for the app to read our text before the clipboard is put back
PASTE_RETRIES = 2        # paste keys sent again when nobody read our text (never once the paste landed)
RETRY_GRACE = 0.4        # seconds between offering the selection again and the retried paste key


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


def _press_paste_key():
    """Shift+Insert, with the modifier keys released first. Returns (sent ok?, timing note)."""
    if WAYLAND:
        t0 = time.monotonic()
        _ydotool_release_modifiers()
        t1 = time.monotonic()
        pasted = _ydotool(_LINUX_KEYCODES["shift"], _LINUX_KEYCODES["insert"])
        return pasted, "ydotool %dms + %dms" % ((t1 - t0) * 1000, (time.monotonic() - t1) * 1000)
    kb = _keyboard()
    _release_modifiers(kb)
    from pynput.keyboard import Key
    _chord(kb, Key.shift, Key.insert)
    return True, "pynput"


# ---------------------------------------------------------------------- Linux
def _is_fix_process(args):
    """Does this /proc cmdline (list of bytes) belong to a `--once` run of this app (a fix, or the
    background holder it forked)?"""
    return b"--once" in args and any(b"layoutfix" in a.lower() for a in args)


def _other_fix_processes():
    """How many other `--once` processes of ours are alive: holders from earlier fixes keep serving the
    restored clipboard, and one could be a fix that is still running. -1 when /proc is unreadable."""
    me, uid = os.getpid(), os.getuid()
    count = 0
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit() and int(p) != me]
    except OSError:
        return -1
    for pid in pids:
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid:
                continue
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                args = f.read().split(b"\0")
        except OSError:
            continue
        if _is_fix_process(args):
            count += 1
    return count


def _previous_fix_age():
    """Seconds since the last fix finished (the fix lock file is touched at the end of each fix), or None."""
    try:
        return time.time() - os.stat(instance.lock_path("fix")).st_mtime
    except OSError:
        return None


def _mark_fix_finished():
    try:
        os.utime(instance.lock_path("fix"))
    except OSError:
        pass


def _fix_linux(convert, timeline=None):
    """Convert the highlighted text (primary selection) and paste with Shift+Insert.

    The clipboard backend is normally the windowless X11 client (through XWayland on Wayland); the
    fallbacks (wl-clipboard / xclip) open a window per call on GNOME, which made the dock flicker.
    """
    timeline = timeline or Timeline()
    clip = clipboard.linux_backend(WAYLAND)
    if clip is None:
        notify("Install wl-clipboard (Wayland) or xclip (X11) to use this app on Linux.")
        return
    if WAYLAND and not _ydotool_ready():
        notify("Wayland needs ydotool with its ydotoold service running (see the README).")
        return

    timeline.header("fix started (%s session, %s backend)" % ("wayland" if WAYLAND else "x11", clip.name))
    age = _previous_fix_age()
    timeline.mark("previous fix finished %s ago, other --once processes alive: %d",
                  "%.1fs" % age if age is not None else "?", _other_fix_processes())
    text = clip.text("primary")
    timeline.mark("selection read: %d chars", len(text))
    if not text.strip():
        logger().info("result: NOTHING SELECTED, nothing changed")
        notify(SELECT_FIRST)
        return
    if len(text) > safety.MAX_CHARS:
        notify("The selection is too long to convert safely.")
        return
    out = convert(text)
    timeline.mark("converted: %d -> %d chars (%s)", len(text), len(out), "changed" if out != text else "UNCHANGED")
    if out == text:
        logger().info("result: nothing to convert")
        return

    saved = clip.snapshot("clipboard")
    timeline.mark("clipboard saved: %s", ", ".join(sorted(saved)) if saved else "empty")
    try:
        clip.write_text("clipboard", out)
        clip.write_text("primary", out)                   # terminals paste the primary selection
        timeline.mark("clipboard + primary set")
        # The user is still letting go of the hotkey: wait (serving requests), counted from the key press.
        clip.idle(max(0.0, HOTKEY_GRACE - (time.time() - timeline.started)))
        clip.mark_key_sent()
        pasted, note = _press_paste_key()
        timeline.mark("paste key (Shift+Insert) sent: %s (%s)", "ok" if pasted else "FAILED", note)
        if not pasted:
            notify("Could not send the paste key. Is the ydotoold service running?")
        waited, seen = clip.wait_for_paste(PASTE_WAIT)    # until the app has read our text (or PASTE_WAIT)
        timeline.mark("app read our text: %s (waited %dms)", seen or "NOT SEEN", waited * 1000)
        for attempt in range(1, PASTE_RETRIES + 1):
            if seen or not pasted:
                break
            # Nobody asked for our text, so the key did not paste: an app can only paste what it reads
            # from the selection owner, and that is us. Offer the selection again from a fresh owner
            # window (the compositor re-reads TARGETS and hands the focused app a new offer), give a
            # hotkey modifier that is still held time to go up, and press the paste key once more.
            clip.write_text("clipboard", out)
            clip.write_text("primary", out)
            clip.idle(RETRY_GRACE)
            late = clip.read_since_key()
            if late:                                      # the first paste landed after all: never twice
                timeline.mark("retry %d cancelled: our text was read late (%s)", attempt, late)
                break
            clip.mark_key_sent()
            pasted, note = _press_paste_key()
            timeline.mark("retry %d: selection set again, paste key sent: %s (%s)", attempt,
                          "ok" if pasted else "FAILED", note)
            waited, seen = clip.wait_for_paste(PASTE_WAIT)
            timeline.mark("app read our text: %s (waited %dms)", seen or "NOT SEEN", waited * 1000)
        report = clip.report()                            # who asked for our selections, and when
        if report:
            timeline.mark("%s", report)
    finally:
        clip.restore("clipboard", saved)
        holder = clip.detach()
        timeline.mark("clipboard restored%s", " (kept by background pid %d)" % holder if holder else "")


# ------------------------------------------------------------ Windows / macOS
COPY_WAIT = 0.6          # longest wait for a copy to land in the clipboard
COPY_RETRIES = 1         # copy keys sent again when nothing was copied (copying twice is harmless)
RELEASE_WAIT = 1.5       # longest wait for the user to let go of the hotkey (Windows/macOS)


def _held_modifiers():
    """Names of the modifier keys that are physically down right now (Windows/macOS), or None when the
    state cannot be read."""
    try:
        if WIN:
            import ctypes
            user32 = ctypes.windll.user32
            keys = (("shift", 0x10), ("ctrl", 0x11), ("alt", 0x12), ("win", 0x5B), ("win", 0x5C))
            return sorted({name for name, vk in keys if user32.GetAsyncKeyState(vk) & 0x8000})
        if MAC:
            import Quartz
            flags = Quartz.CGEventSourceFlagsState(1)            # 1 = the hardware (HID) state
            masks = (("shift", 0x20000), ("ctrl", 0x40000), ("alt", 0x80000), ("cmd", 0x100000))
            return [name for name, mask in masks if flags & mask]
    except Exception:
        logger().exception("could not read the modifier key state")
        return None
    return None                                           # not supported on this platform


def _wait_for_hotkey_release(timeline):
    """Our Ctrl+C / Ctrl+V must not go out while the user still holds the hotkey's keys (the app would see
    Ctrl+Alt+C and ignore it). Wait until they are really up, instead of a blind sleep."""
    held = _held_modifiers()
    if held is None:
        time.sleep(0.3)
        timeline.mark("modifier state unknown, waited 300ms")
        return
    start = timeline.ms()
    for _ in range(int(RELEASE_WAIT / 0.02)):
        if not held:
            break
        time.sleep(0.02)
        held = _held_modifiers() or []
    if held:
        timeline.mark("still holding %s after %dms, sending anyway", "+".join(held), timeline.ms() - start)
    else:
        timeline.mark("hotkey keys were up after %dms", timeline.ms() - start)
    time.sleep(0.05)


def _fix_desktop(convert, timeline=None):
    import pyperclip
    from pynput.keyboard import Key

    timeline = timeline or Timeline(started=time.time())
    timeline.header("fix started (%s)" % ("macOS" if MAC else "Windows"))
    if clipboard.has_non_text():
        timeline.mark("refused: the clipboard holds an image or files")
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
        timeline.mark("clipboard saved (%d chars), marker set", len(previous))
        _wait_for_hotkey_release(timeline)                # let the user let go of the hotkey
        text = marker
        for attempt in range(COPY_RETRIES + 1):
            _release_modifiers(kb)
            _chord(kb, *copy_keys)
            sent = timeline.ms()
            timeline.mark("copy key sent%s", " (retry %d)" % attempt if attempt else "")
            for _ in range(int(COPY_WAIT / 0.05)):        # wait for the copy to land
                time.sleep(0.05)
                text = pyperclip.paste()
                if text != marker:
                    break
            if text != marker:
                timeline.mark("copy landed after %dms: %d chars", timeline.ms() - sent, len(text))
                break
            timeline.mark("copy did NOT land (waited %dms)", timeline.ms() - sent)
        if text == marker or not text.strip():
            notify(SELECT_FIRST)
            return
        if safety.looks_like_line_copy(text):
            timeline.mark("skipped: the editor copied a whole line")
            notify(SELECT_FIRST)                          # the editor copied a whole line instead
            return
        if len(text) > safety.MAX_CHARS:
            timeline.mark("skipped: selection too long (%d chars)", len(text))
            notify("The selection is too long to convert safely.")
            return
        out = convert(text)
        timeline.mark("converted: %d -> %d chars (%s)", len(text), len(out), "changed" if out != text else "unchanged")
        if out == text:
            return
        ours.add(out)
        pyperclip.copy(out)
        time.sleep(0.05)
        _chord(kb, *paste_keys)
        timeline.mark("paste key sent")                   # an app gives no sign that it pasted, so no retry
        time.sleep(0.6)                                   # some apps read the clipboard late
    finally:
        try:
            if pyperclip.paste() in ours:                 # don't clobber anything the user copied since
                pyperclip.copy(previous)
                timeline.mark("clipboard restored")
            else:
                timeline.mark("clipboard left alone (changed since)")
        except Exception:
            logger().exception("could not restore the clipboard")


def fix_selection(convert):
    # the tray app is already running when the hotkey is pressed; only a `--once` process starts with the press
    timeline = Timeline(started=time.time() if MAC or WIN else None)
    lock = instance.try_lock("fix")
    if lock is None:                                      # another fix is already running
        logger().info("skipped: another fix is still running (hotkey pressed %dms ago)", timeline.ms())
        return
    started = time.time()
    with lock:
        if MAC or WIN:
            _fix_desktop(convert, timeline)
        else:
            try:
                _fix_linux(convert, timeline)
            finally:
                _mark_fix_finished()
    logger().info("fix finished in %.2fs (%.2fs since the hotkey press started this process)",
                  time.time() - started, time.time() - timeline.started)
    logger().info("-" * 40)
