"""Cross-process locks, so two copies of the app never touch the clipboard at once."""
import sys

from . import config


class Lock:
    def __init__(self, handle):
        self._handle = handle

    def release(self):
        if self._handle is None:
            return
        try:
            if sys.platform.startswith("win"):
                import msvcrt
                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._handle, fcntl.LOCK_UN)
        except OSError:
            pass
        self._handle.close()
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


def try_lock(name: str):
    """Return a Lock if nobody else holds `name`, otherwise None. Never blocks."""
    path = config.config_path().parent / f"{name}.lock"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path, "a+")
    except OSError:
        return Lock(None)            # can't create a lock file: don't block the user
    try:
        if sys.platform.startswith("win"):
            import msvcrt
            handle.seek(0)
            if not handle.read(1):
                handle.write("0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return Lock(handle)
