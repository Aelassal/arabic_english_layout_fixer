"""Tray icon + global hotkey."""
import sys
import threading

from . import autostart, core, system

DEFAULT_HOTKEY = "<ctrl>+<alt>+a"
_busy = threading.Lock()


def run_fix():
    if _busy.acquire(blocking=False):
        try:
            system.fix_selection(core.fix)
        finally:
            _busy.release()


def _icon_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), 14, fill=(30, 120, 90))
    d.text((18, 18), "ع/A", fill="white")
    return img


def main():
    if "--once" in sys.argv:                    # for Wayland / custom shortcuts
        run_fix()
        return

    import pystray
    from pynput import keyboard

    hotkey = DEFAULT_HOTKEY
    if system.WAYLAND:
        print("Wayland: global hotkeys are blocked. Bind your own system shortcut to:\n"
              "  python -m layoutfix --once", file=sys.stderr)
    else:
        listener = keyboard.GlobalHotKeys({hotkey: lambda: threading.Thread(target=run_fix).start()})
        listener.daemon = True
        listener.start()

    def toggle_autostart(icon, item):
        autostart.set_enabled(not autostart.is_enabled())

    shown = hotkey.replace("<", "").replace(">", "").replace("+", " + ").title()
    menu = pystray.Menu(
        pystray.MenuItem(f"Select text, then press {shown}", None, enabled=False),
        pystray.MenuItem("Fix selected text now", lambda i, it: threading.Thread(target=run_fix).start()),
        pystray.MenuItem("Start with computer", toggle_autostart, checked=lambda it: autostart.is_enabled()),
        pystray.MenuItem("Quit", lambda icon, it: icon.stop()),
    )
    pystray.Icon("layoutfix", _icon_image(), "Arabic Layout Fixer", menu).run()
