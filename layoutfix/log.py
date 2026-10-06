"""Log file in the config folder, plus a hook for desktop notifications.

Selected text is never logged, only lengths and error details.
"""
import logging
import logging.handlers
import sys

from . import config

_log = logging.getLogger("layoutfix")
_notifier = None


def setup() -> None:
    if _log.handlers:
        return
    _log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    try:
        path = config.config_path().parent / "layoutfix.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=200_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(fmt)
        _log.addHandler(handler)
    except OSError:
        pass
    if sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(fmt)
        _log.addHandler(console)


def get():
    return _log


def set_notifier(fn) -> None:
    global _notifier
    _notifier = fn


def notify(message: str) -> None:
    """Tell the user something (tray balloon when available) and log it."""
    _log.info("notice: %s", message)
    if _notifier:
        try:
            _notifier(message)
        except Exception:
            _log.exception("notification failed")
