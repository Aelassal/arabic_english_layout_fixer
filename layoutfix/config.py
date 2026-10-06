"""User settings (just the hotkey for now), stored as JSON in the OS config folder."""
import json
import os
import sys
from pathlib import Path

MODIFIERS = ["ctrl", "alt", "shift", "cmd"]
KEYS = ([chr(c) for c in range(ord("a"), ord("z") + 1)] + [str(d) for d in range(10)]
        + [f"f{n}" for n in range(1, 13)] + ["space"])


def default_hotkey() -> str:
    # Option+letter types special characters on macOS, which breaks global hotkeys.
    return "<ctrl>+<shift>+a" if sys.platform == "darwin" else "<ctrl>+<alt>+a"


def config_path() -> Path:
    override = os.environ.get("LAYOUTFIX_CONFIG_DIR")
    if override:
        base = Path(override)
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home())) / "ArabicLayoutFixer"
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support/ArabicLayoutFixer"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "arabic-layout-fixer"
    return base / "config.json"


def parse(hotkey: str):
    """'<ctrl>+<alt>+a' -> (['ctrl', 'alt'], 'a'). Raises ValueError if invalid."""
    mods, key = [], None
    for part in hotkey.split("+"):
        name = part.strip("<>").lower()
        if part.startswith("<") and name in MODIFIERS:
            mods.append(name)
        elif name in KEYS and key is None:
            key = name
        else:
            raise ValueError(f"bad hotkey part: {part!r}")
    if key is None or not set(mods) & {"ctrl", "alt", "cmd"}:
        # Shift alone would trigger on every capital letter the user types.
        raise ValueError("a hotkey needs Ctrl, Alt or Win/Cmd plus a key")
    return mods, key


def build(mods, key: str) -> str:
    ordered = [m for m in MODIFIERS if m in mods]
    keypart = f"<{key}>" if len(key) > 1 else key       # <f5>, <space>, but plain 'a'
    hotkey = "+".join([f"<{m}>" for m in ordered] + [keypart])
    parse(hotkey)                                       # validate
    return hotkey


def pretty(hotkey: str) -> str:
    mods, key = parse(hotkey)
    cmd = "Cmd" if sys.platform == "darwin" else "Win"
    names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "cmd": cmd}
    return " + ".join([names[m] for m in mods] + [key.upper() if len(key) == 1 else key.capitalize()])


def load_hotkey() -> str:
    try:
        hotkey = json.loads(config_path().read_text(encoding="utf-8"))["hotkey"]
        parse(hotkey)
        return hotkey
    except Exception:
        return default_hotkey()


def save_hotkey(hotkey: str) -> None:
    parse(hotkey)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")                      # write-then-rename so readers never see half a file
    tmp.write_text(json.dumps({"hotkey": hotkey}), encoding="utf-8")
    os.replace(tmp, path)


def last_changed() -> float:
    try:
        return config_path().stat().st_mtime
    except OSError:
        return 0.0
