"""Pure conversion logic: text typed on the wrong keyboard layout -> intended text.

Maps the standard Arabic (101) layout to/from the US QWERTY layout, key for key.
"""
import re
import unicodedata

# Arabic char -> the US key that produces it (unshifted)
_AR_TO_EN = dict(zip(
    "ضصثقفغعهخحجد" "شسيبلاتنمكط" "ئءؤرىةوزظ" "ذ",
    "qwertyuiop[]" "asdfghjkl;'" "zxcvnm,./" "`",
))
# Arabic char -> the US key that produces it (with Shift)
_AR_TO_EN_SHIFT = {
    "َ": "Q", "ً": "W", "ُ": "E", "ٌ": "R", "ِ": "A", "ٍ": "S", "ْ": "X", "ّ": "~",
    "إ": "Y", "أ": "H", "ـ": "J", "،": "K", "؛": "P", "؟": "?", "آ": "N", "’": "M",
    "‘": "U", "÷": "I", "×": "O",
}
# Shifted keys that type plain ASCII on the Arabic layout (only read as such inside Arabic words)
_ASCII_SHIFT = {"]": "D", "[": "F", "/": "L", "{": "C", "}": "V", "~": "Z"}
_AR_DIGITS = dict(zip("٠١٢٣٤٥٦٧٨٩", "0123456789"))
# One Arabic key press that yields two characters
_LIGATURES = {"لا": "b", "لإ": "T", "لأ": "G", "لآ": "B"}

_A2E = {**_AR_TO_EN, **_AR_TO_EN_SHIFT, **_AR_DIGITS}
_E2A = {v: k for k, v in _A2E.items() if k not in _AR_DIGITS}
_E2A.update({v: k for k, v in _LIGATURES.items()})
_E2A.update({v: k for k, v in _ASCII_SHIFT.items()})

_PRESENTATION = re.compile("[ﭐ-﷿ﹰ-﻿]")   # Arabic presentation forms (ﻣﺮﺣﺒﺎ)
_TOKENS = re.compile(r"(\s+)")


def is_arabic(ch: str) -> bool:
    return "؀" <= ch <= "ۿ"


def _normalize(text: str) -> str:
    return _PRESENTATION.sub(lambda m: unicodedata.normalize("NFKC", m.group()), text)


def arabic_to_english(text: str) -> str:
    out = []
    for token in _TOKENS.split(_normalize(text)):
        has_arabic = any(is_arabic(c) for c in token)
        for lig, key in _LIGATURES.items():
            token = token.replace(lig, key)
        out.append("".join(
            _A2E.get(c) or (_ASCII_SHIFT.get(c) if has_arabic else None) or c for c in token))
    return "".join(out)


def english_to_arabic(text: str) -> str:
    return "".join(_E2A.get(c, c) for c in text)


def fix(text: str) -> str:
    """Convert in whichever direction makes sense for this text."""
    arabic = sum(is_arabic(c) for c in text)
    latin = sum(c.isascii() and c.isalpha() for c in text)
    return arabic_to_english(text) if arabic >= latin else english_to_arabic(text)
