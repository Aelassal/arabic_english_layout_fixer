"""Exercise the Linux fix flow with a fake clipboard and fake key presses."""
import os
import tempfile
import time
import unittest
from unittest import mock

from layoutfix import system
from layoutfix.log import Timeline


class FakeClip:
    name = "fake"

    def __init__(self, clipboard, primary):
        self.sel = {"clipboard": clipboard, "primary": primary}   # snapshots: {mime: bytes}
        self.idled = []
        self.key_marked = False
        self.paste_seen = "CLIPBOARD as UTF8_STRING"
        self.detached = 0

    def text(self, sel):
        return self.sel[sel].get("text/plain", b"").decode()

    def snapshot(self, sel):
        return dict(self.sel[sel])

    def restore(self, sel, snap):
        self.sel[sel] = dict(snap)

    def write_text(self, sel, text):
        self.sel[sel] = {"text/plain": text.encode()}

    def idle(self, seconds):
        self.idled.append(seconds)

    def mark_key_sent(self):
        self.key_marked = True

    def wait_for_paste(self, max_wait, grace=0.1):
        return 0.01, self.paste_seen

    def detach(self):
        self.detached += 1
        return None


class LinuxFlowTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.environ["LAYOUTFIX_CONFIG_DIR"] = self.dir.name
        self.notices = []
        patches = [
            mock.patch.object(system, "notify", self.notices.append),
            mock.patch.object(system, "WAYLAND", True),
            mock.patch.object(system, "_ydotool_ready", lambda: True),
            mock.patch.object(system, "_ydotool_release_modifiers", lambda: None),
            mock.patch.object(system.time, "sleep", lambda s: None),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.presses = []
        self.on_press = lambda: None

        def fake_ydotool(*codes):
            self.on_press()
            self.presses.append(codes)
            return True
        p = mock.patch.object(system, "_ydotool", fake_ydotool)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        os.environ.pop("LAYOUTFIX_CONFIG_DIR")
        self.dir.cleanup()

    def run_flow(self, clip, convert=lambda t: t[::-1], timeline=None):
        with mock.patch.object(system.clipboard, "linux_backend", lambda wayland: clip):
            system._fix_linux(convert, timeline)

    def test_pastes_converted_text_and_restores_an_image_on_the_clipboard(self):
        image = {"image/png": b"\x89PNG..."}
        clip = FakeClip(clipboard=image, primary={"text/plain": b"abc"})
        pasted = []
        self.on_press = lambda: pasted.append(clip.text("clipboard"))
        self.run_flow(clip)
        self.assertEqual(pasted, ["cba"])                         # converted text was on the clipboard at paste time
        self.assertEqual(clip.sel["clipboard"], image)            # the image is back
        self.assertEqual(clip.sel["primary"], {"text/plain": b"cba"})   # terminals paste PRIMARY
        self.assertEqual(self.presses, [(42, 110)])               # Shift+Insert only, never Ctrl+C
        self.assertTrue(clip.key_marked)
        self.assertEqual(clip.detached, 1)                        # restored data is kept served

    def test_never_releases_super(self):
        self.assertNotIn(125, system._ALL_MODIFIER_CODES)
        self.assertNotIn(126, system._ALL_MODIFIER_CODES)

    def test_hotkey_grace_is_counted_from_the_key_press(self):
        clip = FakeClip(clipboard={}, primary={"text/plain": b"abc"})
        self.run_flow(clip, timeline=Timeline(started=time.time() - 0.1))   # process started 100 ms ago
        self.assertEqual(len(clip.idled), 1)
        self.assertAlmostEqual(clip.idled[0], 0.15, delta=0.05)
        clip = FakeClip(clipboard={}, primary={"text/plain": b"abc"})
        self.run_flow(clip, timeline=Timeline(started=time.time() - 5))     # long ago: no wait at all
        self.assertEqual(clip.idled, [0.0])

    def test_nothing_selected_changes_nothing(self):
        clip = FakeClip(clipboard={"text/plain": b"keep me"}, primary={})
        self.run_flow(clip)
        self.assertEqual(self.presses, [])
        self.assertEqual(clip.sel["clipboard"], {"text/plain": b"keep me"})
        self.assertEqual(clip.detached, 0)
        self.assertTrue(self.notices)

    def test_clipboard_restored_even_if_convert_fails(self):
        clip = FakeClip(clipboard={"text/plain": b"old"}, primary={"text/plain": b"abc"})

        def boom(text):
            raise RuntimeError("bug")
        with self.assertRaises(RuntimeError):
            self.run_flow(clip, convert=boom)
        self.assertEqual(clip.sel["clipboard"], {"text/plain": b"old"})

    def test_clipboard_restored_even_if_the_key_press_fails(self):
        clip = FakeClip(clipboard={"text/plain": b"old"}, primary={"text/plain": b"abc"})
        with mock.patch.object(system, "_ydotool", side_effect=OSError("no ydotool")):
            with self.assertRaises(OSError):
                self.run_flow(clip)
        self.assertEqual(clip.sel["clipboard"], {"text/plain": b"old"})
        self.assertEqual(clip.detached, 1)

    def test_too_long_selection_is_refused(self):
        clip = FakeClip(clipboard={"text/plain": b"old"}, primary={"text/plain": b"x" * 200_000})
        self.run_flow(clip)
        self.assertEqual(self.presses, [])
        self.assertTrue(self.notices)

    def test_second_fix_is_skipped_while_one_runs(self):
        clip = FakeClip(clipboard={}, primary={"text/plain": b"abc"})
        inner = []
        with mock.patch.object(system.clipboard, "linux_backend", lambda wayland: clip):
            def convert(text):
                lock = system.instance.try_lock("fix")
                inner.append(lock)
                return text[::-1]
            system.fix_selection(convert)
        self.assertEqual(inner, [None])                           # the lock was held during the fix
        again = system.instance.try_lock("fix")
        self.assertIsNotNone(again)                               # and released afterwards
        again.release()


if __name__ == "__main__":
    unittest.main()
