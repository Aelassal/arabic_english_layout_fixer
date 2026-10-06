import os
import plistlib
import tempfile
import unittest

from layoutfix import autostart, config, history, instance, safety


class SafetyTests(unittest.TestCase):
    def test_line_copy_detection(self):
        self.assertTrue(safety.looks_like_line_copy("some line\n"))
        self.assertTrue(safety.looks_like_line_copy("some line\r\n"))
        self.assertFalse(safety.looks_like_line_copy("selected words"))
        self.assertFalse(safety.looks_like_line_copy("two\nlines\n"))

    def test_non_text_types(self):
        types = ["text/plain", "UTF8_STRING", "image/png", "application/x-thing"]
        self.assertEqual(safety.non_text_types(types), ["image/png", "application/x-thing"])
        self.assertEqual(safety.non_text_types(["text/plain", "text/html", "STRING"]), [])

    def test_mac_clipboard_info(self):
        self.assertTrue(safety.mac_clipboard_has_non_text("«class PNGf», 5231, «class utf8», 4"))
        self.assertFalse(safety.mac_clipboard_has_non_text("«class utf8», 12, «class RTF », 300"))


class AutostartTests(unittest.TestCase):
    def test_desktop_entry_quotes_special_characters(self):
        entry = autostart.desktop_entry(["/opt/My App/run $x.sh", "-m", "50%"])
        self.assertIn('Exec="/opt/My App/run \\$x.sh" "-m" "50%%"', entry)

    def test_launch_agent_is_valid_plist_even_with_xml_characters(self):
        argv = ["/Applications/R&D <tool>/app", "--flag"]
        data = plistlib.loads(autostart.launch_agent(argv))
        self.assertEqual(data["ProgramArguments"], argv)
        self.assertTrue(data["RunAtLoad"])


class InstanceAndHistoryTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.environ["LAYOUTFIX_CONFIG_DIR"] = self.dir.name

    def tearDown(self):
        os.environ.pop("LAYOUTFIX_CONFIG_DIR")
        self.dir.cleanup()

    def test_second_lock_is_refused_until_released(self):
        first = instance.try_lock("app")
        self.assertIsNotNone(first)
        self.assertIsNone(instance.try_lock("app"))
        other = instance.try_lock("other")
        self.assertIsNotNone(other)
        other.release()
        first.release()
        again = instance.try_lock("app")
        self.assertIsNotNone(again)
        again.release()

    def test_undo_restores_original_text(self):
        mixed = "Meeting at 5pm مع أحمد"
        converted = history.convert(mixed)
        self.assertNotEqual(converted, mixed)
        self.assertEqual(history.convert(converted), mixed)        # second press undoes it
        self.assertNotEqual(history.convert(mixed), mixed)         # and the undo entry is consumed

    def test_history_file_is_private_and_corruption_is_ignored(self):
        history.convert("hello")
        path = history._path()
        if os.name == "posix":
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")
        path.write_text("{broken")
        self.assertEqual(history.convert("hello"), "اثممخ")


if __name__ == "__main__":
    unittest.main()
