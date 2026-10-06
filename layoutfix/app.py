"""Tray icon + global hotkey."""
import subprocess
import sys
import threading
import time

from . import autostart, config, core, system
from .icon import make_icon

_busy = threading.Lock()


def run_fix():
    if _busy.acquire(blocking=False):
        try:
            system.fix_selection(core.fix)
        finally:
            _busy.release()


def _in_thread(fn):
    return lambda *a: threading.Thread(target=fn, daemon=True).start()


class Hotkey:
    """Owns the global-hotkey listener and swaps it when the setting changes."""

    def __init__(self):
        self.listener = None
        self.current = None

    def apply(self, hotkey):
        from pynput import keyboard
        if self.listener:
            self.listener.stop()
            self.listener = None
        if system.WAYLAND:
            return
        try:
            self.listener = keyboard.GlobalHotKeys({hotkey: _in_thread(run_fix)})
            self.listener.daemon = True
            self.listener.start()
            self.current = hotkey
        except Exception as exc:                 # unusable hotkey: fall back to the default
            print(f"Could not register {hotkey!r}: {exc}", file=sys.stderr)
            if hotkey != config.default_hotkey():
                self.apply(config.default_hotkey())


def open_settings():
    cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "layoutfix"]
    subprocess.Popen(cmd + ["--settings"])


def main():
    if "--once" in sys.argv:                    # for Wayland / custom shortcuts
        run_fix()
        return
    if "--settings" in sys.argv:
        from . import settings
        settings.main()
        return

    import pystray

    if system.WAYLAND:
        print("Wayland: global hotkeys are blocked. Bind your own system shortcut to:\n"
              "  ArabicLayoutFixer --once   (or: python -m layoutfix --once)", file=sys.stderr)

    hotkey = Hotkey()
    hotkey.apply(config.load_hotkey())

    menu = pystray.Menu(
        pystray.MenuItem(lambda item: f"Select text, then press {config.pretty(config.load_hotkey())}",
                         None, enabled=False),
        pystray.MenuItem("Fix selected text now", _in_thread(run_fix)),
        pystray.MenuItem("Settings...", lambda icon, item: open_settings()),
        pystray.MenuItem("Start with computer", lambda icon, item: autostart.set_enabled(not autostart.is_enabled()),
                         checked=lambda item: autostart.is_enabled()),
        pystray.MenuItem("Quit", lambda icon, item: icon.stop()),
    )
    icon = pystray.Icon("layoutfix", make_icon(64), "Arabic Layout Fixer", menu)

    def watch_config():                         # pick up changes made in the settings window
        seen = config.last_changed()
        while True:
            time.sleep(1)
            now = config.last_changed()
            if now != seen:
                seen = now
                hotkey.apply(config.load_hotkey())
                icon.update_menu()

    threading.Thread(target=watch_config, daemon=True).start()
    icon.run()
