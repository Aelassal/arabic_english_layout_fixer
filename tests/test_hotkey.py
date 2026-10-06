import unittest
from types import SimpleNamespace as K

from layoutfix import hotkey
from layoutfix.hotkey import Matcher


def mod(name):
    return K(name=name)


def ch(char, vk=None):
    return K(char=char, vk=vk)


class HotkeyTests(unittest.TestCase):
    def test_fires_on_exact_combo(self):
        m = Matcher("<ctrl>+<alt>+a")
        m.press(mod("ctrl_l")); m.press(mod("alt_l"))
        self.assertTrue(m.press(ch("a")))

    def test_fires_with_arabic_layout_active(self):
        m = Matcher("<ctrl>+<alt>+a")
        m.press(mod("ctrl_l")); m.press(mod("alt_l"))
        self.assertTrue(m.press(ch("ش")))             # the A key types ش on the Arabic layout

    def test_ctrl_letter_control_character(self):
        m = Matcher("<ctrl>+<alt>+a")
        m.press(mod("ctrl")); m.press(mod("alt"))
        self.assertTrue(m.press(ch("\x01")))

    def test_ignores_other_combos(self):
        m = Matcher("<ctrl>+<alt>+a")
        m.press(mod("ctrl"))
        self.assertFalse(m.press(ch("a")))             # alt missing
        m.press(mod("alt")); m.press(mod("shift"))
        self.assertFalse(m.press(ch("a")))             # extra shift
        self.assertFalse(Matcher("<ctrl>+<alt>+a").press(ch("a")))

    def test_no_auto_repeat_and_refire_after_release(self):
        m = Matcher("<ctrl>+<alt>+a")
        m.press(mod("ctrl")); m.press(mod("alt"))
        self.assertTrue(m.press(ch("a")))
        self.assertFalse(m.press(ch("a")))
        m.release(ch("a"))
        self.assertTrue(m.press(ch("a")))

    def test_modifier_release(self):
        m = Matcher("<ctrl>+a")
        m.press(mod("ctrl_r")); m.release(mod("ctrl_r"))
        self.assertFalse(m.press(ch("a")))

    def test_function_and_space_keys(self):
        m = Matcher("<ctrl>+<f5>")
        m.press(mod("ctrl"))
        self.assertTrue(m.press(K(name="f5")))
        m = Matcher("<alt>+<space>")
        m.press(mod("alt"))
        self.assertTrue(m.press(K(name="space")))

    def test_unknown_keys_do_not_crash(self):
        self.assertIsNone(hotkey.base_key(K(name="enter")))
        self.assertIsNone(hotkey.base_key(K(char=None, vk=None)))


if __name__ == "__main__":
    unittest.main()
