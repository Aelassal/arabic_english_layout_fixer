"""OS-specific bits: read the selection, paste text back, release held modifiers."""
import os
import shutil
import subprocess
import sys
import time

MAC = sys.platform == "darwin"
WIN = sys.platform.startswith("win")
WAYLAND = (not MAC and not WIN) and os.environ.get("XDG_SESSION_TYPE") == "wayland"


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


# ---------------------------------------------------------------- Wayland (Linux)
def _ydotool(*codes):
    os.environ.setdefault("YDOTOOL_SOCKET", f"/run/user/{os.getuid()}/.ydotool_socket")
    seq = [f"{c}:1" for c in codes] + [f"{c}:0" for c in reversed(codes)]
    subprocess.run(["ydotool", "key", *seq], check=False)


def _wl(*cmd, text=None):
    if cmd[0] == "wl-copy":   # it forks into the background; don't wait on its pipes
        subprocess.run(cmd, input=text, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return ""
    return subprocess.run(cmd, input=text, capture_output=True, text=True).stdout


def _fix_wayland(convert):
    if not (shutil.which("wl-paste") and shutil.which("ydotool")):
        print("Wayland needs wl-clipboard and ydotool installed (see README).", file=sys.stderr)
        return
    time.sleep(0.4)
    text = _wl("wl-paste", "-p", "-n")          # current selection
    if not text.strip():
        _ydotool(29, 46)                        # Ctrl+C fallback
        time.sleep(0.15)
        text = _wl("wl-paste", "-n")
    if not text.strip():
        return
    out = convert(text)
    _wl("wl-copy", text=out)
    _wl("wl-copy", "-p", text=out)
    time.sleep(0.1)
    _ydotool(42, 110)                           # Shift+Insert pastes everywhere


# ---------------------------------------------------------- Windows / macOS / X11
def _fix_pynput(convert):
    import pyperclip
    from pynput.keyboard import Key
    kb = _keyboard()
    mod = Key.cmd if MAC else Key.ctrl

    previous = pyperclip.paste()
    marker = f"\0layoutfix-{time.time()}"
    pyperclip.copy(marker)                      # so we can tell if Ctrl+C copied anything
    time.sleep(0.05)
    time.sleep(0.25)                            # let the user release the hotkey
    _release_modifiers(kb)
    _chord(kb, mod, "c")
    time.sleep(0.2)
    text = pyperclip.paste()
    if text == marker or not text.strip():      # nothing was selected
        pyperclip.copy(previous)
        return
    pyperclip.copy(convert(text))
    time.sleep(0.05)
    _chord(kb, mod, "v")
    time.sleep(0.3)
    pyperclip.copy(previous)                    # give the user their clipboard back


def fix_selection(convert):
    (_fix_wayland if WAYLAND else _fix_pynput)(convert)
