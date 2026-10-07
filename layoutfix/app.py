"""Tray icon + global hotkey."""
import os
import shutil
import subprocess
import sys
import threading
import time

from . import autostart, config, history, instance, log, system
from .hotkey import HotkeyListener


def run_fix():
    try:
        system.fix_selection(history.convert)
    except Exception:
        log.get().exception("fix failed")
        log.notify("Something went wrong. Nothing was changed. Details are in the log file.")


def _in_thread(fn):
    return lambda *a: threading.Thread(target=fn, daemon=True).start()


class Hotkey:
    """Owns the hotkey listener and swaps it when the setting changes."""

    def __init__(self):
        self.listener = None

    def apply(self, hotkey):
        if self.listener:
            self.listener.stop()
            self.listener = None
        if system.WAYLAND:
            return
        try:
            self.listener = HotkeyListener(hotkey, _in_thread(run_fix))
            self.listener.start()
        except Exception:
            log.get().exception("could not register %r", hotkey)
            if hotkey != config.default_hotkey():
                self.apply(config.default_hotkey())


def open_settings():
    cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "layoutfix"]
    subprocess.Popen(cmd + ["--settings"])


def _import_pystray():
    """pystray picks a Linux backend at import time and can crash when the tray library is missing."""
    try:
        import pystray
        return pystray
    except Exception:
        if sys.platform.startswith("linux"):
            os.environ["PYSTRAY_BACKEND"] = "xorg"
            try:
                import pystray
                return pystray
            except Exception:
                pass
    log.get().exception("no tray icon available")
    return None


def _selftest() -> int:
    """Import everything the app needs and run a tiny conversion. Used by CI on the *built* app,
    because a packaged app can crash at start-up on a missing module even when the tests pass."""
    import importlib
    from . import core
    modules = ["layoutfix.autostart", "layoutfix.clipboard", "layoutfix.hotkey", "layoutfix.icon",
               "layoutfix.settings", "layoutfix.system", "layoutfix.x11sel", "PIL.Image", "pyperclip"]
    if not sys.platform.startswith("linux") or os.environ.get("DISPLAY"):
        modules += ["pynput.keyboard", "pystray"]        # these need a display on Linux
    failed = []
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as exc:
            failed.append(f"{name}: {exc!r}")
    if core.fix("اثممخ") != "hello":
        failed.append("core.fix gave a wrong result")
    from .icon import make_icon
    if make_icon(64).size != (64, 64):
        failed.append("icon has the wrong size")
    for line in failed:
        log.get().error("selftest FAILED %s", line)
    log.get().info("selftest %s (%d modules checked)", "FAILED" if failed else "ok", len(modules))
    return 1 if failed else 0


def main():
    log.setup()
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if "--once" in sys.argv:                    # for Wayland / custom shortcuts
        if shutil.which("notify-send"):
            log.set_notifier(lambda m: subprocess.run(["notify-send", "Arabic Layout Fixer", m], timeout=5))
        run_fix()
        return
    if "--settings" in sys.argv:
        from . import settings
        settings.main()
        return

    app_lock = instance.try_lock("app")
    if app_lock is None:
        log.get().info("Arabic Layout Fixer is already running.")
        return

    hotkey = Hotkey()
    hotkey.apply(config.load_hotkey())
    if system.WAYLAND:
        log.get().warning("Wayland blocks global hotkeys: bind a system shortcut to `ArabicLayoutFixer --once`.")

    pystray = _import_pystray()
    if pystray is None:                         # no tray: keep the hotkey working in the background
        threading.Event().wait()
        return

    def toggle_autostart(icon, item):
        try:
            autostart.set_enabled(not autostart.is_enabled())
        except (ValueError, OSError) as exc:
            log.notify(str(exc))

    menu = pystray.Menu(
        pystray.MenuItem(lambda item: f"Select text, then press {config.pretty(config.load_hotkey())}",
                         None, enabled=False),
        pystray.MenuItem("Settings...", lambda icon, item: open_settings()),
        pystray.MenuItem("Start with computer", toggle_autostart, checked=lambda item: autostart.is_enabled()),
        pystray.MenuItem("Quit", lambda icon, item: icon.stop()),
    )
    from .icon import make_icon                 # imports Pillow: only the tray needs it
    icon = pystray.Icon("layoutfix", make_icon(64), "Arabic Layout Fixer", menu)
    log.set_notifier(lambda message: icon.notify(message, "Arabic Layout Fixer"))

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
