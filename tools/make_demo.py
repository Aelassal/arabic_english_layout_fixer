"""Builds assets/demo.gif: type in Arabic by mistake -> select -> hotkey -> fixed."""
from PIL import Image, ImageDraw, ImageFont

W, H = 640, 260
AR = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf", 44)
EN = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
UI = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
BG, BOX, FG, GREEN, SEL = (245, 247, 246), (255, 255, 255), (27, 36, 32), (30, 120, 90), (176, 214, 255)


def frame(text, font, caption, selected=False, key=False):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 60, W - 40, 150), 10, fill=BOX, outline=(200, 208, 204), width=2)
    box = d.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    x, y = 70, 105 - th // 2 - box[1]
    if selected:
        d.rectangle((x - 4, 72, x + tw + 4, 138), fill=SEL)
    d.text((x, y), text, font=font, fill=FG)
    d.text((40, 24), caption, font=UI, fill=(93, 106, 99))
    if key:
        d.rounded_rectangle((200, 180, W - 200, 226), 10, fill=GREEN)
        d.text((W // 2, 203), "Ctrl + Alt + A", font=UI, fill="white", anchor="mm")
    return img


frames = [
    (frame("اثممخ", AR, "1. You typed with the Arabic layout by mistake"), 1400),
    (frame("اثممخ", AR, "2. Select it", selected=True), 1000),
    (frame("اثممخ", AR, "3. Press the hotkey", selected=True, key=True), 900),
    (frame("hello", EN, "4. Fixed. No retyping."), 2200),
]
frames[0][0].save("assets/demo.gif", save_all=True, append_images=[f for f, _ in frames[1:]],
                  duration=[d for _, d in frames], loop=0)
