"""Draws the app icon (a calendar page with an eighth note, in the app's blue) and writes it in every format it's
needed in, into app/assets/:

    icon.png    1024 px: the window's own icon (title bar, taskbar; scheduler_app.py) and the source of the others
    icon.ico    Windows (the .exe; dev/build_exe.py), 16 to 256 px
    icon.icns   Mac (the .app, the Dock; dev/build_exe.py), 16 to 1024 px

    python dev/make_icon.py

Drawn on a 512-unit grid, 8 times larger than needed and scaled down, so the edges are smooth. Needs Pillow (comes
with reportlab).
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "assets"
SS = 8                                              # drawn at 512 * SS px, then scaled down
TOP, BOTTOM = (0x1A, 0x7B, 0xD6), (0x00, 0x4F, 0x9E)   # the tile's gradient (around the app's #005FB8)
BLUE, DARK, BAND, WHITE = (0x00, 0x5F, 0xB8), (0x00, 0x4F, 0x9E), (0xCF, 0xE4, 0xFA), (0xFF, 0xFF, 0xFF)


def s(*v):
    """Grid units -> pixels of the big drawing."""
    return [round(x * SS) for x in v]


def bezier(p0, p1, p2, p3, n=48):
    return [tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t ** 2 * c + t ** 3 * d
                  for a, b, c, d in zip(p0, p1, p2, p3)) for t in (i / n for i in range(n + 1))]


def draw():
    size = 512 * SS
    # the tile: a rounded square with a top-to-bottom gradient
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        grad.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)))
    grad = grad.resize((size, size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(s(16, 16, 496, 496), radius=108 * SS, fill=255)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # the calendar page, its header band and the two binder rings
    d.rounded_rectangle(s(96, 118, 416, 418), radius=40 * SS, fill=WHITE)
    d.rounded_rectangle(s(96, 118, 416, 192), radius=40 * SS, fill=BAND, corners=(True, True, False, False))
    for x in (170, 316):
        d.rounded_rectangle(s(x, 88, x + 26, 160), radius=13 * SS, fill=WHITE, outline=DARK, width=8 * SS)

    # the eighth note: a tilted head, a stem flush with its right edge (no overhang), a smooth flag
    head = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cx, cy, rx, ry = 226, 352, 46, 36
    ImageDraw.Draw(head).ellipse(s(cx - rx, cy - ry, cx + rx, cy + ry), fill=BLUE)
    img.alpha_composite(head.rotate(22, resample=Image.BICUBIC, center=(cx * SS, cy * SS)))
    right = cx + (rx ** 2 * 0.9272 ** 2 + ry ** 2 * 0.3746 ** 2) ** 0.5   # the tilted head's rightmost x
    touch = cy - (rx ** 2 - ry ** 2) * 0.9272 * 0.3746 / (right - cx)    # ...where that point is: the stem ends there
    stem_l, stem_r, top = right - 21, right, 208
    d.rectangle(s(stem_l, top, stem_r, touch), fill=BLUE)
    outer = bezier((stem_r, top), (stem_r + 2, top + 40), (stem_r + 62, top + 52), (stem_r + 60, top + 104))
    tip = bezier((stem_r + 60, top + 104), (stem_r + 59, top + 118), (stem_r + 55, top + 128),
                 (stem_r + 48, top + 136))
    inner = bezier((stem_r + 48, top + 136), (stem_r + 52, top + 98), (stem_r + 26, top + 80), (stem_r, top + 72))
    d.polygon([(x * SS, y * SS) for x, y in outer + tip + inner], fill=BLUE)
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    big = draw().resize((1024, 1024), Image.LANCZOS)
    big.save(OUT / "icon.png")
    big.save(OUT / "icon.ico", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
    big.save(OUT / "icon.icns")
    print(f"Wrote {', '.join(p.name for p in sorted(OUT.glob('icon.*')))} in {OUT}")


if __name__ == "__main__":
    main()
