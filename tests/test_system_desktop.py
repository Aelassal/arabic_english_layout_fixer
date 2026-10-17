"""The Windows/macOS fix flow, with a fake clipboard and fake keys (runs on any OS)."""
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

from layoutfix import system


class FakeKey:
    cmd, ctrl, alt, shift, insert = "cmd", "ctrl", "alt", "shift", "insert"


class Desktop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        env = mock.patch.dict(os.environ, {"LAYOUTFIX_CONFIG_DIR": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.tmp.cleanup)
        self.clip = "old"
        self.selection = "اثممخ"
        self.copies_that_land = 1          # which copy attempt (1-based) puts the selection on the clipboard
        self.copy_presses = 0
        self.pastes = []
        self.notices = []

        outer = self
        fake_pyperclip = types.SimpleNamespace(
            paste=lambda: outer.clip, copy=lambda text: setattr(outer, "clip", text))
        fake_keyboard = types.ModuleType("pynput.keyboard")
        fake_keyboard.Key = FakeKey
        fake_pynput = types.ModuleType("pynput")
        fake_pynput.keyboard = fake_keyboard
        for patcher in (
            mock.patch.dict(sys.modules, {"pyperclip": fake_pyperclip, "pynput": fake_pynput,
                                          "pynput.keyboard": fake_keyboard}),
            mock.patch.object(system, "MAC", True), mock.patch.object(system, "WIN", False),
            mock.patch.object(system.time, "sleep", lambda s: None),
            mock.patch.object(system, "_keyboard", lambda: object()),
            mock.patch.object(system, "_release_modifiers", lambda kb: None),
            mock.patch.object(system, "_held_modifiers", lambda: []),
            mock.patch.object(system, "_chord", self.chord),
            mock.patch.object(system.clipboard, "has_non_text", lambda: False),
            mock.patch.object(system, "notify", self.notices.append),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def chord(self, kb, *keys):
        if keys == (FakeKey.cmd, "c"):
            self.copy_presses += 1
            if self.copy_presses == self.copies_that_land:
                self.clip = self.selection
        elif keys == (FakeKey.cmd, "v"):
            self.pastes.append(self.clip)

    def test_normal_fix_pastes_and_restores_the_clipboard(self):
        system.fix_selection(lambda t: "hello")
        self.assertEqual(self.pastes, ["hello"])
        self.assertEqual(self.clip, "old")
        self.assertEqual(self.copy_presses, 1)

    def test_copy_that_does_not_land_is_sent_once_more(self):
        self.copies_that_land = 2
        system.fix_selection(lambda t: "hello")
        self.assertEqual(self.copy_presses, 2)
        self.assertEqual(self.pastes, ["hello"])

    def test_copy_retry_is_bounded_and_nothing_is_pasted_without_a_selection(self):
        self.copies_that_land = 99
        system.fix_selection(lambda t: "hello")
        self.assertEqual(self.copy_presses, system.COPY_RETRIES + 1)
        self.assertEqual(self.pastes, [])
        self.assertEqual(self.notices, [system.SELECT_FIRST])
        self.assertEqual(self.clip, "old")

    def test_waits_until_the_hotkey_keys_are_up(self):
        states = iter([["alt", "ctrl"], ["alt", "ctrl"], ["ctrl"], []])
        seen = []
        with mock.patch.object(system, "_held_modifiers", lambda: seen.append(1) or next(states, [])):
            with self.assertLogs("layoutfix", "INFO") as logs:
                system.fix_selection(lambda t: "hello")
        self.assertEqual(self.copy_presses, 1)
        self.assertGreaterEqual(len(seen), 4)                     # polled until nothing was held
        self.assertIn("hotkey keys were up", "\n".join(logs.output))

    def test_gives_up_waiting_and_still_works_when_a_key_stays_down(self):
        with mock.patch.object(system, "_held_modifiers", lambda: ["alt"]):
            with self.assertLogs("layoutfix", "INFO") as logs:
                system.fix_selection(lambda t: "hello")
        self.assertIn("still holding alt", "\n".join(logs.output))
        self.assertEqual(self.pastes, ["hello"])

    def test_unknown_key_state_falls_back_to_a_short_wait(self):
        with mock.patch.object(system, "_held_modifiers", lambda: None):
            with self.assertLogs("layoutfix", "INFO") as logs:
                system.fix_selection(lambda t: "hello")
        self.assertIn("modifier state unknown", "\n".join(logs.output))
        self.assertEqual(self.pastes, ["hello"])

    def test_old_clipboard_is_put_back_on_every_skip_path(self):
        """The copied selection is ours too: skipping must never leave it in place of the user's clipboard."""
        for label, selection, convert in (
            ("already correct", "hello", None),                       # converts to itself: nothing to paste
            ("whole line copied", "line of code\n", lambda t: "x"),
            ("too long", "x" * (system.safety.MAX_CHARS + 1), lambda t: "x"),
        ):
            with self.subTest(label):
                self.clip, self.selection, self.copy_presses, self.pastes = "old", selection, 0, []
                system.fix_selection(convert or (lambda t: t))
                self.assertEqual(self.pastes, [])
                self.assertEqual(self.clip, "old")

    def test_paste_is_never_repeated(self):
        system.fix_selection(lambda t: "hello")
        self.assertEqual(len(self.pastes), 1)

    def test_clipboard_changed_by_the_user_is_left_alone(self):
        def convert(text):
            return "hello"
        original_chord = self.chord

        def chord_then_user_copies(kb, *keys):
            original_chord(kb, *keys)
            if keys == (FakeKey.cmd, "v"):
                self.clip = "something the user copied"
        with mock.patch.object(system, "_chord", chord_then_user_copies):
            system.fix_selection(convert)
        self.assertEqual(self.clip, "something the user copied")

    def test_log_has_a_timeline_without_the_text(self):
        with self.assertLogs("layoutfix", "INFO") as logs:
            system.fix_selection(lambda t: "hello")
        text = "\n".join(logs.output)
        for step in ("fix started (macOS)", "copy key sent", "copy landed", "converted: 5 -> 5", "paste key sent",
                     "clipboard restored"):
            self.assertIn(step, text)
        self.assertNotIn("hello", text)
        self.assertNotIn(self.selection, text)


if __name__ == "__main__":
    unittest.main()
