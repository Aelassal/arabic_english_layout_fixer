"""Remember the last conversion for 10 minutes so pressing the hotkey on the result undoes it.

Stored in the config folder (one entry, replaced each time, owner-only permissions).
"""
import json
import os
import time

from . import config, core

TTL_SECONDS = 600
MAX_CHARS = 10_000


def _path():
    return config.config_path().parent / "last.json"


def _write(data: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def convert(text: str) -> str:
    """core.fix with undo: converting the previous result gives back the original text."""
    try:
        entry = json.loads(_path().read_text(encoding="utf-8"))
        if entry["out"] == text and time.time() - entry["t"] < TTL_SECONDS:
            _path().unlink(missing_ok=True)
            return entry["src"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    out = core.fix(text)
    if len(text) <= MAX_CHARS and out != text:
        try:
            _write({"src": text, "out": out, "t": time.time()})
        except OSError:
            pass
    return out
