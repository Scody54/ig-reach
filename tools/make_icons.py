"""Generates the IG Reach icon for web + Android. Run: python tools/make_icons.py"""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
C1, C2 = (225, 48, 108), (247, 119, 55)


def icon(size, maskable=False, round_corners=True):
    s = size * 4  # draw large, then downscale for smooth edges
    grad = Image.new("RGB", (s, s))
    px = grad.load()
    for y in range(s):
        for x in range(s):
            t = (x + y) / (2 * s)
            px[x, y] = tuple(int(C1[i] + (C2[i] - C1[i]) * t) for i in range(3))
    mask = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(mask)
    if maskable or not round_corners:
        d.rectangle([0, 0, s, s], fill=255)
    else:
        d.rounded_rectangle([0, 0, s, s], radius=int(s * 0.22), fill=255)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    # glyph: three rising bars + arrow (= growing reach)
    g = ImageDraw.Draw(img)
    pad = 0.30 if maskable else 0.22
    x0, x1, y1 = s * pad, s * (1 - pad), s * (1 - pad)
    w = (x1 - x0) / 5
    for i, h in enumerate([0.30, 0.50, 0.72]):
        bx = x0 + i * 2 * w
        g.rounded_rectangle([bx, y1 - (y1 - s * pad) * h, bx + w * 1.2, y1], radius=int(w * 0.3), fill="white")
    ax, ay = x1, s * pad
    g.polygon([(ax, ay), (ax - w * 1.6, ay + w * 0.2), (ax - w * 0.2, ay + w * 1.6)], fill="white")
    g.line([(x0 + w * 0.6, y1 - (y1 - s * pad) * 0.55), (ax - w * 0.6, ay + w * 0.6)], fill="white", width=int(w * 0.35))
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    st = ROOT / "static"
    icon(192).save(st / "icon-192.png")
    icon(512).save(st / "icon-512.png")
    icon(512, maskable=True).save(st / "icon-512-maskable.png")
    icon(180, round_corners=False).save(st / "apple-touch-icon.png")
    res = ROOT / "android" / "app" / "src" / "main" / "res"
    for name, px in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
        d = res / f"mipmap-{name}"
        d.mkdir(parents=True, exist_ok=True)
        icon(px).save(d / "ic_launcher.png")
    print("icons written")
