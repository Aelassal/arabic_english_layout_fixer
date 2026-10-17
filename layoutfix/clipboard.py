"""Clipboard access that never loses what the user had copied.

Linux: preferably a direct X11 selection client (plain X11, or XWayland on Wayland, where mutter bridges
both selections) that never opens a window; wl-clipboard / xclip are fallbacks when X11 is unavailable.
Read and restore the clipboard and the primary selection, including images and other non-text formats.
Windows / macOS: text only through pyperclip; the app refuses to run when the clipboard holds an image
or files, because those cannot be restored safely.

A snapshot is a dict {mime/target: bytes}; an empty dict means "the clipboard was empty".
"""
import os
import shutil
import subprocess
import sys
import time

from . import instance, log, safety
from .x11sel import TEXT_TARGETS


def _run(cmd, data=None):
    """Run a clipboard helper and return its stdout bytes ('' on failure)."""
    started = time.time()
    try:
        proc = subprocess.run(cmd, input=data, capture_output=True, timeout=5)
        out = proc.stdout if proc.returncode == 0 else b""
        log.get().info("  %-9s %-14s rc=%s bytes=%d %.0fms", cmd[0], " ".join(cmd[1:3]), proc.returncode,
                       len(out), (time.time() - started) * 1000)
        return out
    except (OSError, subprocess.SubprocessError) as exc:
        log.get().warning("  %s failed: %s", cmd[0], exc)
        return b""


def _spawn(cmd, data):
    """wl-copy and xclip stay alive in the background to serve the data: don't wait on their pipes."""
    started = time.time()
    try:
        proc = subprocess.run(cmd, input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        log.get().info("  %-9s %-14s rc=%s bytes=%d %.0fms", cmd[0], " ".join(cmd[1:3]), proc.returncode,
                       len(data or b""), (time.time() - started) * 1000)
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError) as exc:
        log.get().warning("  %s failed: %s", cmd[0], exc)
        return False


class _Linux:
    """Shared logic; subclasses supply the tool commands."""
    name = "helper"

    def text(self, sel):
        return self.read(sel, None).decode("utf-8", "replace")

    def fast_text(self, sel):
        """Read plain text in a single helper call, or None when the backend cannot."""
        return None

    def snapshot(self, sel):
        quick = self.fast_text(sel)                       # one call in the common (text) case
        if quick:
            return {"text/plain": quick}
        types = self.types(sel)
        non_text = safety.non_text_types(types)
        if non_text:
            data = self.read(sel, non_text[0])
            return {non_text[0]: data} if data else {}
        data = self.read(sel, None)
        return {"text/plain": data} if data else {}

    def restore(self, sel, snap):
        if not snap:
            self.clear(sel)
        else:
            mime, data = next(iter(snap.items()))
            self.write(sel, data, mime)

    def write_text(self, sel, text):
        return self.write(sel, text.encode("utf-8"), "text/plain")

    def idle(self, seconds):
        """Wait while keeping any selection we own served."""
        time.sleep(seconds)

    def mark_key_sent(self):
        """Called just before the paste key goes out: reads after this point count as the paste."""

    def wait_for_paste(self, max_wait, grace=0.1):
        """Wait until the focused app has read our text (or `max_wait`). Returns seconds waited, seen?"""
        time.sleep(max_wait)
        return max_wait, None

    def read_since_key(self):
        """'SELECTION as TARGET' if anything read our text since the first paste key, else None."""
        return None

    def report(self):
        """One line about who asked for our selections and when (for the log), '' when unknown."""
        return ""

    def detach(self):
        """Keep serving what we own after this process exits (helpers already do)."""
        return None


class Wayland(_Linux):
    name = "wl-clipboard"
    _SEL = {"clipboard": [], "primary": ["-p"]}

    def types(self, sel):
        return _run(["wl-paste", "-l", *self._SEL[sel]]).decode().split()

    def fast_text(self, sel):
        return _run(["wl-paste", "-n", "-t", "text", *self._SEL[sel]]) or None

    def read(self, sel, mime):
        cmd = ["wl-paste", "-n", *self._SEL[sel]]
        return _run(cmd + (["-t", mime] if mime else []))

    def write(self, sel, data, mime):
        return _spawn(["wl-copy", *self._SEL[sel], "-t", mime], data)

    def clear(self, sel):
        _spawn(["wl-copy", *self._SEL[sel], "--clear"], None)


class X11(_Linux):
    name = "xclip"
    _SEL = {"clipboard": "clipboard", "primary": "primary"}

    def types(self, sel):
        return _run(["xclip", "-selection", self._SEL[sel], "-o", "-t", "TARGETS"]).decode().split()

    def read(self, sel, mime):
        return _run(["xclip", "-selection", self._SEL[sel], "-o"] + (["-t", mime] if mime else []))

    def write(self, sel, data, mime):
        return _spawn(["xclip", "-selection", self._SEL[sel], "-t", mime, "-i"], data)

    def clear(self, sel):
        _spawn(["xclip", "-selection", self._SEL[sel], "-i"], b"")


class Native(_Linux):
    """Direct X11 selection client (layoutfix.x11sel): no helper processes, no windows."""
    name = "x11"
    _SEL = {"clipboard": "CLIPBOARD", "primary": "PRIMARY"}

    def __init__(self, selections):
        self.x = selections
        self._key_sent_at = None                          # the latest paste key
        self._first_key_at = None                         # the first one: reads after it mean the paste landed
        self._owned_at = None                             # when we last took the selections over

    def text(self, sel):
        return self.x.read_text(self._SEL[sel])

    def types(self, sel):
        return self.x.targets(self._SEL[sel])

    def snapshot(self, sel):
        """Image (if any) plus text: both are offered again on restore."""
        targets = self.types(sel)
        snap = {}
        non_text = safety.non_text_types(targets)
        if non_text:
            res = self.x.read(self._SEL[sel], non_text[0])
            if res and res[2]:
                snap[non_text[0]] = res[2]
        if any(t in targets for t in ("UTF8_STRING", "text/plain;charset=utf-8", "text/plain", "STRING")):
            res = self.x.read(self._SEL[sel], "UTF8_STRING")
            if res and res[2]:
                snap["text/plain"] = res[2]
        log.get().info("  %s targets: %d, kept %s", sel, len(targets), sorted(snap) or "nothing")
        return snap

    def restore(self, sel, snap):
        if not snap:
            self.x.clear(self._SEL[sel])
            return True
        offers = {}
        for mime, data in snap.items():
            if mime == "text/plain":
                offers.update({t: data for t in TEXT_TARGETS})
            else:
                offers[mime] = data
        return self.x.own(self._SEL[sel], offers)

    def write_text(self, sel, text):
        self._owned_at = time.monotonic()
        return self.x.own_text(self._SEL[sel], text)

    def idle(self, seconds):
        self.x.serve(seconds)

    def mark_key_sent(self):
        self._key_sent_at = time.monotonic()
        if self._first_key_at is None:
            self._first_key_at = self._key_sent_at

    def wait_for_paste(self, max_wait, grace=0.1, min_wait=0.15):
        """Serve at least `min_wait` (the focused app also reads the clipboard eagerly when its owner
        changes, and that read must not be mistaken for the paste), then until a read arrives after
        the key was sent, then `grace` more so the app finishes reading."""
        since = self._key_sent_at or time.monotonic()
        started = time.monotonic()
        self.x.serve(min_wait)
        self.x.serve(max(0.0, max_wait - min_wait), until=lambda: bool(self.x.data_requests_since(since)))
        seen = self.x.data_requests_since(since)
        if seen:
            self.x.serve(grace)                           # let the app finish reading
        return time.monotonic() - started, (f"{seen[0][1]} as {seen[0][2]}" if seen else None)

    EAGER_WINDOW = 0.2                                    # reads this soon after we take over are not a paste

    def read_since_key(self):
        """A read of our text since the first paste key. Right after we (re)take the selections the
        compositor's clipboard bridge reads them at once, and that read is not the app pasting."""
        if self._first_key_at is None:
            return None
        seen = [r for r in self.x.data_requests_since(self._first_key_at)
                if self._owned_at is None or not self._owned_at <= r[0] < self._owned_at + self.EAGER_WINDOW]
        return f"{seen[0][1]} as {seen[0][2]}" if seen else None

    def report(self):
        """Every selection request (selection, target, requestor window id) and every takeover seen by
        this process, timed relative to the first paste key (negative = before it). Never any data."""
        origin = self._first_key_at or time.monotonic()
        rel = lambda t: "%+dms" % round((t - origin) * 1000)
        asked = ["%s %s by 0x%x at %s%s" % (sel, tgt, req, rel(t), "" if ok else " (refused)")
                 for t, sel, tgt, req, ok in self.x.requests]
        lost = ["%s at %s" % (sel, rel(t)) for t, sel in self.x.cleared]
        return "selection requests: %s; taken over: %s" % (", ".join(asked) or "none", ", ".join(lost) or "none")

    def detach(self):
        """Fork: the child keeps serving our selections until another app takes them over."""
        if not self.x.owned:
            return None
        pid = os.fork()
        if pid:
            self.x.conn.sock = None                       # the child owns the connection from now on
            return pid
        try:
            instance.forget_locks_in_child()
            devnull = os.open(os.devnull, os.O_RDWR)
            for fd in (0, 1, 2):
                os.dup2(devnull, fd)
            os.setsid()
            started = time.monotonic()
            deadline = started + 24 * 3600
            while self.x.owned and time.monotonic() < deadline:
                before = set(self.x.owned)
                self.x.serve(60, until=lambda: set(self.x.owned) != before)
                for sel in before - set(self.x.owned):    # one line per selection another app took over
                    log.get().info("holder pid=%d: %s taken over by another app after %.1fs",
                                   os.getpid(), self.x.conn.atom_name(sel), time.monotonic() - started)
        except BaseException:
            pass
        os._exit(0)


def native_backend():
    """Native X11 backend, or None (and a log line) when there is no X server to talk to."""
    if not os.environ.get("DISPLAY"):
        log.get().info("no DISPLAY: X11 selection client unavailable")
        return None
    try:
        from . import x11sel
        return Native(x11sel.connect())
    except Exception as exc:
        log.get().warning("X11 selection client unavailable (%s), using helper programs", exc)
        return None


def linux_backend(wayland: bool):
    native = native_backend()
    if native is not None:
        return native
    if wayland and shutil.which("wl-paste") and shutil.which("wl-copy"):
        return Wayland()
    if not wayland and shutil.which("xclip"):
        return X11()
    return None


def has_non_text() -> bool:
    """Windows/macOS: does the clipboard hold an image or files we could not put back?"""
    try:
        if sys.platform.startswith("win"):
            import ctypes
            user32 = ctypes.windll.user32
            png = user32.RegisterClipboardFormatW("PNG")
            # BITMAP, DIB, TIFF, HDROP (files), DIBV5, PNG
            return any(user32.IsClipboardFormatAvailable(f) for f in (2, 8, 6, 15, 17, png))
        if sys.platform == "darwin":
            info = subprocess.run(["osascript", "-e", "clipboard info"], capture_output=True,
                                  text=True, timeout=5).stdout
            return safety.mac_clipboard_has_non_text(info)
    except Exception:
        log.get().exception("could not inspect the clipboard")
    return False
