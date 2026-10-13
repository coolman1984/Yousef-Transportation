"""Build triporders.ico (16–256 px) from tools/triporders-icon.svg using Pillow.

    python tools/make_icon.py <output.ico>

Pure-Python rasterisation (no Cairo/Inkscape) so CI and the Windows build stay simple.
"""
import math
import os
import struct
import sys
import zlib

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit('Pillow is required: pip install pillow')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG_PATH = os.path.join(ROOT, 'tools', 'triporders-icon.svg')
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

TEAL = (13, 148, 136)
BLUE = (30, 111, 235)
NAVY = (20, 36, 92)
WHITE = (255, 255, 255)


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _bg_color(x, y, n):
    t = (x / n + y / n) / 2
    if t < 0.55:
        return _lerp(TEAL, BLUE, t / 0.55)
    return _lerp(BLUE, NAVY, (t - 0.55) / 0.45)


def _inside_rounded(x, y, n, r):
    cx = min(max(x, r), n - 1 - r)
    cy = min(max(y, r), n - 1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def render(size):
    n = size
    img = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    px = img.load()
    radius = n * 0.22
    for y in range(n):
        for x in range(n):
            if _inside_rounded(x, y, n, radius):
                px[x, y] = _bg_color(x, y, n) + (255,)
    draw = ImageDraw.Draw(img)
    road_w = max(2, int(n * 0.085))
    pts = []
    for i in range(33):
        t = i / 32
        x = int((0.19 + 0.62 * t) * n)
        y = int((0.66 - 0.22 * math.sin(t * math.pi)) * n)
        pts.append((x, y))
    draw.line(pts, fill=WHITE + (240,), width=road_w, joint='curve')
    dot = max(2, n // 18)
    for cx in (int(0.28 * n), int(0.72 * n)):
        cy = int(0.61 * n)
        draw.ellipse((cx - dot, cy - dot, cx + dot, cy + dot), fill=WHITE)
    pin_top = int(0.36 * n)
    pin_w = int(0.18 * n)
    pin_h = int(0.22 * n)
    cx = n // 2
    draw.polygon(
        [(cx, pin_top), (cx + pin_w // 2, pin_top + pin_h // 2), (cx, pin_top + pin_h), (cx - pin_w // 2, pin_top + pin_h // 2)],
        fill=WHITE + (235,),
    )
    stem = max(2, n // 26)
    draw.line((cx, pin_top + pin_h, cx, int(0.58 * n)), fill=WHITE, width=stem)
    return img


def png_bytes(img):
    import io
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def write_ico(path, sizes=ICO_SIZES):
    if not os.path.isfile(SVG_PATH):
        raise FileNotFoundError(SVG_PATH)
    imgs = [png_bytes(render(s)) for s in sizes]
    out = struct.pack('<HHH', 0, 1, len(imgs))
    off = 6 + 16 * len(imgs)
    for s, d in zip(sizes, imgs):
        out += struct.pack('<BBBBHHII', s % 256, s % 256, 0, 0, 1, 32, len(d), off)
        off += len(d)
    out += b''.join(imgs)
    with open(path, 'wb') as f:
        f.write(out)


if __name__ == '__main__':
    dest = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build', 'triporders.ico')
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    write_ico(dest)
    print('icon written to', dest, '(sizes %s)' % ', '.join(map(str, ICO_SIZES)))
