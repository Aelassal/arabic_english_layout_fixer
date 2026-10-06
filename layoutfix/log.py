"""Log file in the config folder, plus a hook for desktop notifications.

Selected text is never logged, only lengths, timings and error details.
"""
import logging
import logging.handlers
import os
import sys
import time

from . import config

_log = logging.getLogger("layoutfix")
_notifier = None
_import_time = time.time()


def process_start_time() -> float:
    """Epoch seconds when this process was started (before the interpreter loaded), Linux /proc or import time."""
    try:
        with open("/proc/self/stat") as f:
            stat = f.read()
        start_ticks = int(stat.rsplit(")", 1)[1].split()[19])    # field 22: starttime, in clock ticks since boot
        with open("/proc/uptime") as f:
            uptime = float(f.read().split()[0])
        return time.time() - (uptime - start_ticks / os.sysconf("SC_CLK_TCK"))
    except (OSError, ValueError, IndexError, AttributeError):
        return _import_time


class Timeline:
    """Log every step as an offset from process start, so one report shows the whole latency."""

    def __init__(self, started=None):
        self.started = process_start_time() if started is None else started
        self.events = []

    def ms(self) -> int:
        return int((time.time() - self.started) * 1000)

    def mark(self, step: str, *args) -> None:
        self.events.append((self.ms(), step % args if args else step))
        _log.info("  +%5dms %s", self.events[-1][0], self.events[-1][1])

    def header(self, what: str) -> None:
        _log.info("%s pid=%d process started %s, python ready after %dms", what, os.getpid(),
                  time.strftime("%H:%M:%S", time.localtime(self.started))
                  + ".%03d" % int((self.started % 1) * 1000), int((_import_time - self.started) * 1000))


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
