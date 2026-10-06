"""The native (X11) clipboard backend with a fake selection object, plus the fork-safe lock helper."""
import os
import tempfile
import time
import unittest

from layoutfix import clipboard, instance, safety
from layoutfix.x11sel import TEXT_TARGETS


class FakeSelections:
    def __init__(self, targets=(), data=None):
        self._targets = list(targets)
        self._data = data or {}
        self.owned = {}
        self.cleared = []
        self.served = []
        self.serve_calls = []

    def targets(self, sel):
        return self._targets

    def read(self, sel, target, timeout=2.0):
        if target in self._data:
            return (1, 8, self._data[target])
        return None

    def read_text(self, sel, timeout=2.0):
        return self._data.get("UTF8_STRING", b"").decode()

    def own(self, sel, offers):
        self.owned[sel] = offers
        return True

    def own_text(self, sel, text):
        return self.own(sel, {t: text.encode() for t in TEXT_TARGETS})

    def clear(self, sel):
        self.cleared.append(sel)
        self.owned.pop(sel, None)

    def serve(self, seconds, until=None):
        self.serve_calls.append(seconds)
        if until and until():
            return
        time.sleep(min(seconds, 0.01))

    def data_requests_since(self, t):
        return [s for s in self.served if s[0] >= t]


class NativeBackendTests(unittest.TestCase):
    def test_snapshot_keeps_image_and_text_but_ignores_meta_targets(self):
        x = FakeSelections(["TARGETS", "TIMESTAMP", "text/html", "image/png", "UTF8_STRING"],
                           {"image/png": b"PNG", "UTF8_STRING": b"hello"})
        snap = clipboard.Native(x).snapshot("clipboard")
        self.assertEqual(snap, {"image/png": b"PNG", "text/plain": b"hello"})

    def test_snapshot_of_text_only_and_of_empty(self):
        x = FakeSelections(["UTF8_STRING", "STRING"], {"UTF8_STRING": b"t"})
        self.assertEqual(clipboard.Native(x).snapshot("clipboard"), {"text/plain": b"t"})
        self.assertEqual(clipboard.Native(FakeSelections()).snapshot("clipboard"), {})

    def test_restore_offers_all_text_targets_and_images_or_clears(self):
        x = FakeSelections()
        clip = clipboard.Native(x)
        clip.restore("clipboard", {"image/png": b"PNG", "text/plain": b"hi"})
        offers = x.owned["CLIPBOARD"]
        self.assertEqual(offers["image/png"], b"PNG")
        for t in TEXT_TARGETS:
            self.assertEqual(offers[t], b"hi")
        clip.restore("clipboard", {})
        self.assertEqual(x.cleared, ["CLIPBOARD"])
        self.assertNotIn("CLIPBOARD", x.owned)

    def test_write_text_owns_primary_and_clipboard_separately(self):
        x = FakeSelections()
        clip = clipboard.Native(x)
        clip.write_text("primary", "p")
        clip.write_text("clipboard", "c")
        self.assertEqual(x.owned["PRIMARY"]["UTF8_STRING"], b"p")
        self.assertEqual(x.owned["CLIPBOARD"]["UTF8_STRING"], b"c")

    def test_wait_for_paste_returns_as_soon_as_the_app_read_our_text(self):
        x = FakeSelections()
        clip = clipboard.Native(x)
        clip.mark_key_sent()
        x.served.append((time.monotonic(), "CLIPBOARD", "text/plain;charset=utf-8"))
        waited, seen = clip.wait_for_paste(5.0, grace=0.0, min_wait=0.0)
        self.assertEqual(seen, "CLIPBOARD as text/plain;charset=utf-8")
        self.assertLess(waited, 1.0)
        self.assertEqual(x.serve_calls, [0.0, 5.0, 0.0])

    def test_wait_for_paste_always_serves_the_minimum_first(self):
        x = FakeSelections()
        clip = clipboard.Native(x)
        clip.mark_key_sent()
        x.served.append((time.monotonic(), "PRIMARY", "UTF8_STRING"))    # an eager read, not the paste
        clip.wait_for_paste(0.6, grace=0.1, min_wait=0.15)
        self.assertEqual(x.serve_calls[0], 0.15)                          # served unconditionally first
        self.assertAlmostEqual(x.serve_calls[1], 0.45)

    def test_wait_for_paste_ignores_reads_from_before_the_key(self):
        x = FakeSelections()
        clip = clipboard.Native(x)
        x.served.append((time.monotonic() - 1, "CLIPBOARD", "UTF8_STRING"))
        clip.mark_key_sent()
        _waited, seen = clip.wait_for_paste(0.02)
        self.assertIsNone(seen)

    def test_detach_without_ownership_does_nothing(self):
        self.assertIsNone(clipboard.Native(FakeSelections()).detach())

    def test_non_text_types_skips_x11_bookkeeping_targets(self):
        self.assertEqual(safety.non_text_types(["TARGETS", "TIMESTAMP", "MULTIPLE", "UTF8_STRING", "text/html"]), [])
        self.assertEqual(safety.non_text_types(["TARGETS", "application/x-foo", "image/png"]),
                         ["image/png", "application/x-foo"])


class ForkSafeLockTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(os, "fork"), "needs os.fork (not available on Windows)")
    def test_child_can_drop_the_lock_handle_without_unlocking_it(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            os.environ["LAYOUTFIX_CONFIG_DIR"] = d
            try:
                lock = instance.try_lock("fix")
                self.assertIsNotNone(lock)
                pid = os.fork()
                if pid == 0:                                  # child: behave like the background holder
                    instance.forget_locks_in_child()
                    os._exit(0 if instance.try_lock("fix") is None else 1)
                _, status = os.waitpid(pid, 0)
                self.assertEqual(os.waitstatus_to_exitcode(status), 0)   # parent still held it
                self.assertIsNone(instance.try_lock("fix"))             # child's exit did not unlock
                lock.release()
                again = instance.try_lock("fix")
                self.assertIsNotNone(again)
                again.release()
            finally:
                os.environ.pop("LAYOUTFIX_CONFIG_DIR")


if __name__ == "__main__":
    unittest.main()
