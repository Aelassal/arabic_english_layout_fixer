import unittest

from layoutfix.core import arabic_to_english, english_to_arabic, fix


class CoreTests(unittest.TestCase):
    def test_arabic_to_english(self):
        self.assertEqual(arabic_to_english("اثممخ"), "hello")
        self.assertEqual(arabic_to_english("ثممخ ءخقمي"), "ello xorld")

    def test_english_to_arabic(self):
        self.assertEqual(english_to_arabic("hello"), "اثممخ")

    def test_roundtrip(self):
        for word in ["hello", "python", "test, me.", "a;b'c", "UIO", "Dad Fox Lot", "Hello World"]:
            self.assertEqual(arabic_to_english(english_to_arabic(word)), word, word)

    def test_auto_direction(self):
        self.assertEqual(fix("اثممخ"), "hello")
        self.assertEqual(fix("hello"), "اثممخ")

    def test_spaces_digits_newlines_untouched(self):
        self.assertEqual(arabic_to_english("اثممخ ١٢٣\nاثممخ"), "hello 123\nhello")

    def test_shifted_keys(self):
        self.assertEqual(english_to_arabic("U"), "‘")
        self.assertEqual(arabic_to_english("‘÷×"), "UIO")

    def test_ascii_shift_symbols_only_inside_arabic_words(self):
        self.assertEqual(arabic_to_english("ش]"), "aD")           # Arabic word: ] came from Shift+D
        self.assertEqual(arabic_to_english("a[1]"), "a[1]")       # plain English token is left alone

    def test_presentation_forms(self):
        self.assertEqual(arabic_to_english("ﺍﺛﻤﻤﺦ"), "hello")

    def test_mixed_text_leaves_arabic_words_alone_when_converting_to_arabic(self):
        out = fix("Meeting مع أحمد")
        self.assertTrue(out.endswith("مع أحمد"))

    def test_emoji_and_symbols_survive(self):
        self.assertEqual(fix("hello 😀"), "اثممخ 😀")


if __name__ == "__main__":
    unittest.main()
