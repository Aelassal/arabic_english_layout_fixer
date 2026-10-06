"""Start-with-login, per OS. Each function is best-effort."""
import os
import sys
from pathlib import Path

NAME = "ArabicLayoutFixer"


def _command() -> str:
    if getattr(sys, "frozen", False):           # PyInstaller build
        return f'"{sys.executable}"'
    return f'"{sys.executable}" -m layoutfix'


def _paths():
    home = Path.home()
    return (
        home / ".config/autostart/arabic-layout-fixer.desktop",
        home / "Library/LaunchAgents/com.arabiclayoutfixer.plist",
    )


def is_enabled() -> bool:
    if sys.platform.startswith("win"):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, NAME)
            return True
        except OSError:
            return False
    linux, mac = _paths()
    return (mac if sys.platform == "darwin" else linux).exists()


def set_enabled(on: bool) -> None:
    cmd = _command()
    if sys.platform.startswith("win"):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(k, NAME)
                except OSError:
                    pass
        return
    linux, mac = _paths()
    path = mac if sys.platform == "darwin" else linux
    if not on:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        args = "".join(f"<string>{a}</string>" for a in cmd.replace('"', "").split(" -m ")[0:1])
        path.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
<key>Label</key><string>com.arabiclayoutfixer</string>
<key>ProgramArguments</key><array>{args}</array>
<key>RunAtLoad</key><true/>
</dict></plist>''')
    else:
        path.write_text(f"[Desktop Entry]\nType=Application\nName=Arabic Layout Fixer\nExec={cmd}\n")
