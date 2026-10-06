"""Pure conversion logic: text typed on the wrong keyboard layout -> intended text.

Maps the standard Arabic (101) layout to/from the US QWERTY layout, key for key.
"""

# Arabic char -> the US key that produces it (unshifted)
_AR_TO_EN = dict(zip(
    "ضصثقفغعهخحجد" "شسيبلاتنمكط" "ئءؤرىةوزظ" "ذ",
    "qwertyuiop[]" "asdfghjkl;'" "zxcvnm,./" "`",
))
# Arabic char -> the US key that produces it (with Shift)
_AR_TO_EN_SHIFT = {
    "َ": "Q", "ً": "W", "ُ": "E", "ٌ": "R", "ِ": "A", "ٍ": "S", "ْ": "X", "ّ": "~",
    "إ": "Y", "أ": "H", "ـ": "J", "،": "K", "؛": "P", "؟": "?", "آ": "N", "’": "M",
}
_AR_DIGITS = dict(zip("٠١٢٣٤٥٦٧٨٩", "0123456789"))
# One Arabic key press that yields two characters
_LIGATURES = {"لا": "b", "لإ": "T", "لأ": "G", "لآ": "B"}

_A2E = {**_AR_TO_EN, **_AR_TO_EN_SHIFT, **_AR_DIGITS}
_E2A = {v: k for k, v in _A2E.items() if k not in _AR_DIGITS}
_E2A.update({v: k for k, v in _LIGATURES.items()})


def is_arabic(ch: str) -> bool:
    return "؀" <= ch <= "ۿ"


def arabic_to_english(text: str) -> str:
    for lig, key in _LIGATURES.items():
        text = text.replace(lig, key)
    return "".join(_A2E.get(c, c) for c in text)


def english_to_arabic(text: str) -> str:
    return "".join(_E2A.get(c, c) for c in text)


def fix(text: str) -> str:
    """Convert in whichever direction makes sense for this text."""
    arabic = sum(is_arabic(c) for c in text)
    latin = sum(c.isascii() and c.isalpha() for c in text)
    return arabic_to_english(text) if arabic >= latin else english_to_arabic(text)
