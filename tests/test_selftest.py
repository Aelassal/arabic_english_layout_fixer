import os
import tempfile
import importlib.util
import unittest

from layoutfix import app


@unittest.skipUnless(importlib.util.find_spec("pyperclip"), "app dependencies are not installed")
class SelftestTests(unittest.TestCase):
    def test_selftest_passes_in_a_normal_install(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            os.environ["LAYOUTFIX_CONFIG_DIR"] = d
            try:
                self.assertEqual(app._selftest(), 0)
            finally:
                os.environ.pop("LAYOUTFIX_CONFIG_DIR")


if __name__ == "__main__":
    unittest.main()
