"""Наклейка на корпус: два QR на этикетку Niimbot 50×30 мм (203 dpi → 400×240 px).

    uv run --with "qrcode[pil]" python tools/make-sticker.py

1 · Wi-Fi — телефон подключается к точке доступа подставки «Figurki Setup».
2 · Настройка — страница с шагами: docs/s/index.html на GitHub Pages.
"""
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

WIFI = "WIFI:T:nopass;S:Figurki Setup;;"
SETUP = "https://rudnik275.github.io/nfc-figurines/s/"
W, H = 400, 240  # 50×30 мм при 203 dpi
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
OUT = Path(__file__).resolve().parent.parent / "docs" / "stickers"


def qr(data: str, size: int) -> Image.Image:
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
    code.add_data(data)
    code.make(fit=True)
    modules = code.modules_count
    box = size // modules  # целое число точек на модуль — края QR не размываются
    code.box_size = box
    return code.make_image(fill_color="black", back_color="white").get_image().convert("1"), modules, box


def main() -> None:
    sticker = Image.new("1", (W, H), 1)
    draw = ImageDraw.Draw(sticker)
    font = ImageFont.truetype(FONT, 22)
    for i, (data, label) in enumerate([(WIFI, "1 · Wi-Fi"), (SETUP, "2 · Настройка")]):
        img, modules, box = qr(data, 168)
        x = 16 + i * 200 + (168 - img.width) // 2
        y = 16 + (168 - img.height) // 2
        sticker.paste(img, (x, y))
        tw = draw.textlength(label, font=font)
        draw.text((16 + i * 200 + (168 - tw) / 2, 196), label, font=font, fill=0)
        print(f"{label}: {modules}×{modules} модулей, {box} точек на модуль ({box / 8:.2f} мм)")
    OUT.mkdir(parents=True, exist_ok=True)
    sticker.save(OUT / "sticker-50x30.png", dpi=(203, 203))
    sticker.resize((W * 3, H * 3), Image.NEAREST).save(OUT / "sticker-50x30-preview.png")
    print(f"готово: {OUT / 'sticker-50x30.png'}")


if __name__ == "__main__":
    main()
