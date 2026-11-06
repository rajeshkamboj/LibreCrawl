"""Render the LibreCrawl app icons (Windows .ico + PNG) with Pillow.

Kept in the repo so the icon can be regenerated without a design tool:

    python packaging/make_icon.py

The mark is a stylised spider web: concentric octagons with radial strands on
a dark slate rounded square, in LibreCrawl's teal accent.
"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SIZE = 1024
BG = (17, 24, 39)          # slate-900
ACCENT = (45, 212, 191)    # teal-400
ACCENT_DIM = (13, 148, 136)  # teal-600


def rounded_square(size, radius, color):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=color)
    return img


def web_layer(size):
    """Concentric octagons + radial spokes, drawn on a transparent canvas."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = size / 2
    max_r = size * 0.345
    stroke = max(2, int(size * 0.019))

    # 8 spokes, stopping at the outer ring
    import math
    spokes = 8
    for i in range(spokes):
        a = math.radians(90 + i * (360 / spokes))
        x = cx + math.cos(a) * max_r * math.cos(math.radians(22.5))
        y = cy - math.sin(a) * max_r * math.cos(math.radians(22.5))
        draw.line([(cx, cy), (x, y)], fill=ACCENT_DIM, width=stroke)

    # 3 concentric octagons
    for frac in (0.42, 0.71, 1.0):
        r = max_r * frac
        pts = []
        for i in range(spokes):
            a = math.radians(90 + 22.5 + i * (360 / spokes))
            pts.append((cx + math.cos(a) * r, cy - math.sin(a) * r))
        draw.polygon(pts, outline=ACCENT, width=stroke)

    # Centre dot
    r = size * 0.055
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)
    return img


def build():
    base = rounded_square(SIZE, int(SIZE * 0.22), BG)
    base.alpha_composite(web_layer(SIZE))

    png_path = HERE / 'librecrawl.png'
    base.resize((512, 512), Image.LANCZOS).save(png_path)

    ico_path = HERE / 'librecrawl.ico'
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    base.save(ico_path, format='ICO', sizes=sizes)
    print(f'wrote {png_path.name} and {ico_path.name}')


if __name__ == '__main__':
    build()
