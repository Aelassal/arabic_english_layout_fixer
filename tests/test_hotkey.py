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


class FireOnRelease(unittest.TestCase):
    def matcher(self, hotkey="<ctrl>+<alt>+a"):
        return Matcher(hotkey, fire_on_release=True)

    def test_does_not_fire_on_press_but_when_every_key_is_up(self):
        m = self.matcher()
        m.press(mod("ctrl_l")); m.press(mod("alt_l"))
        self.assertFalse(m.press(ch("a")))               # armed, not fired
        self.assertFalse(m.release(ch("a")))             # modifiers still held
        self.assertFalse(m.release(mod("alt_l")))
        self.assertTrue(m.release(mod("ctrl_l")))        # the last key went up

    def test_main_key_released_last(self):
        m = self.matcher()
        m.press(mod("ctrl")); m.press(mod("alt")); m.press(ch("a"))
        self.assertFalse(m.release(mod("ctrl")))
        self.assertFalse(m.release(mod("alt")))
        self.assertTrue(m.release(ch("a")))

    def test_fires_once_per_use(self):
        m = self.matcher()
        m.press(mod("ctrl")); m.press(mod("alt")); m.press(ch("a"))
        m.release(ch("a")); m.release(mod("alt"))
        self.assertTrue(m.release(mod("ctrl")))
        self.assertFalse(m.release(mod("ctrl")))
        m.press(mod("ctrl")); m.press(mod("alt")); m.press(ch("a"))
        m.release(ch("a")); m.release(mod("alt"))
        self.assertTrue(m.release(mod("ctrl")))

    def test_auto_repeat_does_not_arm_twice(self):
        m = self.matcher()
        m.press(mod("ctrl")); m.press(mod("alt"))
        for _ in range(5):
            m.press(ch("a"))
        m.release(ch("a")); m.release(mod("alt"))
        self.assertTrue(m.release(mod("ctrl")))

    def test_another_key_cancels(self):
        m = self.matcher()
        m.press(mod("ctrl")); m.press(mod("alt")); m.press(ch("a"))
        m.press(ch("b"))                                  # the user went on typing
        m.release(ch("a")); m.release(mod("alt"))
        self.assertFalse(m.release(mod("ctrl")))

    def test_incomplete_chord_never_fires(self):
        m = self.matcher()
        m.press(mod("ctrl")); m.press(ch("a"))            # alt missing
        m.release(ch("a"))
        self.assertFalse(m.release(mod("ctrl")))

    def test_injected_events_are_ignored(self):
        m = self.matcher()
        m.press(mod("ctrl")); m.press(mod("alt")); m.press(ch("a"))
        m.release(ch("a")); m.release(mod("alt"))
        self.assertFalse(m.press(mod("shift"), injected=True))      # the tool's own keys
        self.assertFalse(m.release(mod("shift"), injected=True))
        self.assertEqual(m.held, {"ctrl"})
        self.assertTrue(m.release(mod("ctrl")))

    def test_lone_function_key(self):
        m = self.matcher("<f9>")
        m.press(K(name="f9"))
        self.assertTrue(m.release(K(name="f9")))
        m.press(mod("ctrl")); m.press(K(name="f9"))                 # F9 with Ctrl is a different shortcut
        m.release(K(name="f9"))
        self.assertFalse(m.release(mod("ctrl")))

    def test_resync_drops_stale_modifiers_the_os_says_are_up(self):
        m = self.matcher()
        m.held = {"ctrl", "alt", "shift"}                  # a shift release was lost
        m.resync(["ctrl", "alt"])
        self.assertEqual(m.held, {"ctrl", "alt"})
        m.resync(None)                                     # unknown: keep what we have
        self.assertEqual(m.held, {"ctrl", "alt"})
        m = Matcher("<cmd>+a", fire_on_release=True)
        m.held = {"cmd", "shift"}
        m.resync(["win"])                                  # Windows names the key "win"
        self.assertEqual(m.held, {"cmd"})

    def test_resync_never_trusts_a_reading_without_the_hotkeys_own_modifiers(self):
        m = self.matcher()
        m.held = {"ctrl", "alt"}
        m.resync([])                                       # a wrong reading must not break the hotkey
        self.assertEqual(m.held, {"ctrl", "alt"})
        m.resync(["ctrl"])
        self.assertEqual(m.held, {"ctrl", "alt"})

    def test_listener_fires_the_callback_on_release(self):
        calls = []
        listener = hotkey.HotkeyListener("<ctrl>+<alt>+a", lambda: calls.append(1), lambda: ["ctrl", "alt"])
        # drive the same handlers pynput would call, through a stub Listener
        import sys, types
        handlers = {}

        class StubListener:
            def __init__(self, on_press, on_release):
                handlers["press"], handlers["release"] = on_press, on_release
            daemon = True
            def start(self): pass
            def stop(self): pass
        fake = types.ModuleType("pynput.keyboard")
        fake.Listener = StubListener
        pkg = types.ModuleType("pynput"); pkg.keyboard = fake
        saved = {k: sys.modules.get(k) for k in ("pynput", "pynput.keyboard")}
        sys.modules.update({"pynput": pkg, "pynput.keyboard": fake})
        try:
            listener.start()
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        handlers["press"](mod("ctrl"), False); handlers["press"](mod("alt"), False); handlers["press"](ch("a"), False)
        self.assertEqual(calls, [])
        handlers["release"](ch("a"), False); handlers["release"](mod("alt"), False)
        self.assertEqual(calls, [])
        handlers["release"](mod("ctrl"), False)
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
