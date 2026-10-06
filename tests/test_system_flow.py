"""Exercise the Linux fix flow with a fake clipboard and fake key presses."""
import os
import tempfile
import unittest
from unittest import mock

from layoutfix import system


class FakeClip:
    def __init__(self, clipboard, primary):
        self.sel = {"clipboard": clipboard, "primary": primary}   # (mime, data) pairs

    def text(self, sel):
        mime, data = self.sel[sel]
        return data if mime == "text" else ""

    def snapshot(self, sel):
        return self.sel[sel]

    def restore(self, sel, snap):
        self.sel[sel] = snap

    def write_text(self, sel, text):
        self.sel[sel] = ("text", text)


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

    def run_flow(self, clip, convert=lambda t: t[::-1]):
        with mock.patch.object(system.clipboard, "linux_backend", lambda wayland: clip):
            system._fix_linux(convert)

    def test_pastes_converted_text_and_restores_an_image_on_the_clipboard(self):
        image = ("image/png", b"\x89PNG...")
        clip = FakeClip(clipboard=image, primary=("text", "abc"))
        pasted = []
        self.on_press = lambda: pasted.append(clip.text("clipboard"))
        self.run_flow(clip)
        self.assertEqual(pasted, ["cba"])                         # converted text was on the clipboard at paste time
        self.assertEqual(clip.sel["clipboard"], image)            # the image is back
        self.assertEqual(self.presses, [(42, 110)])               # Shift+Insert only, never Ctrl+C

    def test_never_releases_super(self):
        self.assertNotIn(125, system._ALL_MODIFIER_CODES)
        self.assertNotIn(126, system._ALL_MODIFIER_CODES)

    def test_nothing_selected_changes_nothing(self):
        clip = FakeClip(clipboard=("text", "keep me"), primary=("empty", b""))
        self.run_flow(clip)
        self.assertEqual(self.presses, [])
        self.assertEqual(clip.sel["clipboard"], ("text", "keep me"))
        self.assertTrue(self.notices)

    def test_clipboard_restored_even_if_convert_fails(self):
        clip = FakeClip(clipboard=("text", "old"), primary=("text", "abc"))

        def boom(text):
            raise RuntimeError("bug")
        with self.assertRaises(RuntimeError):
            self.run_flow(clip, convert=boom)
        self.assertEqual(clip.sel["clipboard"], ("text", "old"))

    def test_too_long_selection_is_refused(self):
        clip = FakeClip(clipboard=("text", "old"), primary=("text", "x" * 200_000))
        self.run_flow(clip)
        self.assertEqual(self.presses, [])
        self.assertTrue(self.notices)


if __name__ == "__main__":
    unittest.main()
