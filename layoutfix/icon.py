"""The app icon, drawn with shapes (no fonts, so it renders the same everywhere)."""
from PIL import Image, ImageDraw


def make_icon(size: int = 64):
    s = size / 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2 * s, 2 * s, 62 * s, 62 * s), 14 * s, fill=(30, 120, 90))
    white = (255, 255, 255)
    # right-pointing arrow (top) and left-pointing arrow (bottom): a "swap" symbol
    d.rectangle((12 * s, 21 * s, 38 * s, 27 * s), fill=white)
    d.polygon([(36 * s, 12 * s), (52 * s, 24 * s), (36 * s, 36 * s)], fill=white)
    d.rectangle((26 * s, 37 * s, 52 * s, 43 * s), fill=white)
    d.polygon([(28 * s, 28 * s), (12 * s, 40 * s), (28 * s, 52 * s)], fill=white)
    return img
