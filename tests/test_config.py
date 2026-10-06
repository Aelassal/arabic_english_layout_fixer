import os
import tempfile
import unittest

from layoutfix import config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.environ["LAYOUTFIX_CONFIG_DIR"] = self.dir.name

    def tearDown(self):
        os.environ.pop("LAYOUTFIX_CONFIG_DIR")
        self.dir.cleanup()

    def test_parse_and_build_roundtrip(self):
        for hk in ["<ctrl>+<alt>+a", "<ctrl>+<shift>+<f5>", "<cmd>+<space>", "<alt>+7"]:
            mods, key = config.parse(hk)
            self.assertEqual(config.build(mods, key), hk)

    def test_build_orders_modifiers(self):
        self.assertEqual(config.build(["shift", "ctrl"], "k"), "<ctrl>+<shift>+k")

    def test_rejects_invalid(self):
        for bad in ["a", "<ctrl>", "<ctrl>+<alt>", "<ctrl>+ab", ""]:
            with self.assertRaises(ValueError):
                config.parse(bad)
        with self.assertRaises(ValueError):
            config.build([], "a")

    def test_default_when_missing_or_corrupt(self):
        self.assertEqual(config.load_hotkey(), config.default_hotkey())
        config.config_path().parent.mkdir(parents=True, exist_ok=True)
        config.config_path().write_text("{not json")
        self.assertEqual(config.load_hotkey(), config.default_hotkey())

    def test_save_and_load(self):
        config.save_hotkey("<ctrl>+<shift>+f9")
        self.assertEqual(config.load_hotkey(), "<ctrl>+<shift>+f9")
        self.assertGreater(config.last_changed(), 0)

    def test_pretty(self):
        self.assertIn("Ctrl", config.pretty("<ctrl>+<shift>+f9"))
        self.assertTrue(config.pretty("<ctrl>+<alt>+a").endswith("A"))


if __name__ == "__main__":
    unittest.main()
