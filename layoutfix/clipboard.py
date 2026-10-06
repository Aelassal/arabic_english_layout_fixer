"""Clipboard access that never loses what the user had copied.

Linux (Wayland via wl-clipboard, X11 via xclip): read and restore the clipboard and the primary
selection, including images and other non-text formats (one format: the most useful one).
Windows / macOS: text only through pyperclip; the app refuses to run when the clipboard holds
an image or files, because those cannot be restored safely.
"""
import os
import shutil
import subprocess
import sys
import time

from . import log, safety


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
    """Shared logic; subclasses supply the five tool commands."""

    def text(self, sel):
        return self.read(sel, None).decode("utf-8", "replace")

    def fast_text(self, sel):
        """Read plain text in a single helper call, or None when the backend cannot."""
        return None

    def snapshot(self, sel):
        quick = self.fast_text(sel)                       # one call in the common (text) case
        if quick:
            return ("text/plain", quick)
        types = self.types(sel)
        non_text = safety.non_text_types(types)
        if non_text:
            data = self.read(sel, non_text[0])
            return (non_text[0], data) if data else ("empty", b"")
        data = self.read(sel, None)
        return ("text/plain", data) if data else ("empty", b"")

    def restore(self, sel, snap):
        mime, data = snap
        if mime == "empty":
            self.clear(sel)
        else:
            self.write(sel, data, mime)

    def write_text(self, sel, text):
        return self.write(sel, text.encode("utf-8"), "text/plain")


class Wayland(_Linux):
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
    _SEL = {"clipboard": "clipboard", "primary": "primary"}

    def types(self, sel):
        return _run(["xclip", "-selection", self._SEL[sel], "-o", "-t", "TARGETS"]).decode().split()

    def read(self, sel, mime):
        return _run(["xclip", "-selection", self._SEL[sel], "-o"] + (["-t", mime] if mime else []))

    def write(self, sel, data, mime):
        return _spawn(["xclip", "-selection", self._SEL[sel], "-t", mime, "-i"], data)

    def clear(self, sel):
        _spawn(["xclip", "-selection", self._SEL[sel], "-i"], b"")


def linux_backend(wayland: bool):
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
