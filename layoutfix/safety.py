"""Pure checks that decide whether it is safe to touch the clipboard and paste."""

MAX_CHARS = 100_000
_TEXT_MIMES = {"UTF8_STRING", "STRING", "TEXT", "COMPOUND_TEXT"}
# X11 bookkeeping targets that are not data (seen through XWayland / xclip)
_META_TARGETS = {"TARGETS", "TIMESTAMP", "MULTIPLE", "SAVE_TARGETS", "DELETE", "INCR"}
_MAC_NON_TEXT = ("PNGf", "TIFF", "JPEG", "GIFf", "furl", "public.png", "public.tiff", "public.jpeg",
                 "public.file-url")


def looks_like_line_copy(text: str) -> bool:
    """Editors such as VS Code copy the whole current line (plus a newline) when nothing is selected."""
    return text.endswith(("\n", "\r")) and "\n" not in text.rstrip("\r\n")


def non_text_types(mime_types) -> list:
    """The clipboard formats from `mime_types` that are not plain text, images first."""
    other = [t for t in mime_types
             if not t.startswith("text/") and t not in _TEXT_MIMES and t not in _META_TARGETS]
    return sorted(other, key=lambda t: not t.startswith("image/"))


def mac_clipboard_has_non_text(clipboard_info: str) -> bool:
    return any(token in clipboard_info for token in _MAC_NON_TEXT)
