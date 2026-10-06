import unittest
from layoutfix.core import arabic_to_english, english_to_arabic, fix


class CoreTests(unittest.TestCase):
    def test_arabic_to_english(self):
        self.assertEqual(arabic_to_english("اثممخ"), "hello")
        self.assertEqual(arabic_to_english("ثممخ ءخقمي"), "ello xorld")

    def test_english_to_arabic(self):
        self.assertEqual(english_to_arabic("hello"), "اثممخ")

    def test_roundtrip(self):
        for word in ["hello", "python", "test, me.", "a;b'c"]:
            self.assertEqual(arabic_to_english(english_to_arabic(word)), word)

    def test_auto_direction(self):
        self.assertEqual(fix("اثممخ"), "hello")
        self.assertEqual(fix("hello"), "اثممخ")

    def test_spaces_digits_untouched(self):
        self.assertEqual(arabic_to_english("اثممخ ١٢٣"), "hello 123")


if __name__ == "__main__":
    unittest.main()
