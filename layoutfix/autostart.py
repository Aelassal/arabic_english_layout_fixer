"""Start-with-login, per OS."""
import plistlib
import subprocess
import sys
from pathlib import Path

NAME = "ArabicLayoutFixer"
WIN = sys.platform.startswith("win")
MAC = sys.platform == "darwin"


def command_argv() -> list:
    if getattr(sys, "frozen", False):                   # PyInstaller build
        return [sys.executable]
    exe = sys.executable
    if WIN and exe.lower().endswith("python.exe"):      # pythonw: no console window
        exe = exe[:-len("python.exe")] + "pythonw.exe"
    return [exe, "-m", "layoutfix"]


def _desktop_quote(arg: str) -> str:
    """Quote one argument for the Exec= line of a .desktop file (freedesktop spec)."""
    arg = arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
    return f'"{arg}"'


def desktop_entry(argv: list) -> str:
    exec_line = " ".join(_desktop_quote(a) for a in argv)
    return f"[Desktop Entry]\nType=Application\nName=Arabic Layout Fixer\nExec={exec_line}\nX-GNOME-Autostart-enabled=true\n"


def launch_agent(argv: list) -> bytes:
    return plistlib.dumps({"Label": "com.aelassal.arabiclayoutfixer", "ProgramArguments": argv, "RunAtLoad": True})


def _file_path() -> Path:
    home = Path.home()
    if MAC:
        return home / "Library/LaunchAgents/com.aelassal.arabiclayoutfixer.plist"
    return home / ".config/autostart/arabic-layout-fixer.desktop"


def _run_key():
    import winreg
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                          0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)


def is_enabled() -> bool:
    if WIN:
        import winreg
        try:
            with _run_key() as key:
                winreg.QueryValueEx(key, NAME)
            return True
        except OSError:
            return False
    return _file_path().exists()


def set_enabled(on: bool) -> None:
    """Raises ValueError with a user-readable message when it cannot be enabled."""
    argv = command_argv()
    if WIN:
        import winreg
        with _run_key() as key:
            if on:
                winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(argv))
            else:
                try:
                    winreg.DeleteValue(key, NAME)
                except OSError:
                    pass
        return
    path = _file_path()
    if not on:
        path.unlink(missing_ok=True)
        return
    if MAC and ("/Volumes/" in argv[0] or "AppTranslocation" in argv[0]):
        raise ValueError("Move Arabic Layout Fixer to the Applications folder first, then turn this on.")
    path.parent.mkdir(parents=True, exist_ok=True)
    if MAC:
        path.write_bytes(launch_agent(argv))
    else:
        path.write_text(desktop_entry(argv), encoding="utf-8")
