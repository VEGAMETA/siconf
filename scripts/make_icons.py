"""Иконки для ярлыков в D:/shortcuts: скруглённый квадрат с градиентом и белым знаком."""
import math
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFilter

OUT = pathlib.Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
S = 1024  # рисуем крупно, потом уменьшаем — сглаживание бесплатно


def base(c1, c2):
    grad = Image.new("RGBA", (S, S))
    px = grad.load()
    for y in range(S):
        for x in range(S):
            t = (x + y) / (2 * S - 2)
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(c1, c2)) + (255,)
    # мягкий блик сверху
    glow = Image.new("L", (S, S), 0)
    ImageDraw.Draw(glow).ellipse((-S * 0.1, -S * 0.8, S * 1.1, S * 0.35), fill=38)
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.06))
    grad = Image.composite(Image.new("RGBA", (S, S), (255, 255, 255, 255)), grad, glow)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((40, 40, S - 40, S - 40), radius=230, fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    return out


def sparkle(draw, cx, cy, r, w):
    """Четырёхлучевая звезда: острые лучи, вогнутые стороны (квадратичные кривые через точку у центра)."""
    tips = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    pts = []
    for i in range(4):
        (x0, y0), (x1, y1) = tips[i], tips[(i + 1) % 4]
        # контрольная точка на диагонали, близко к центру: чем меньше w, тем тоньше лучи
        mx, my = (x0 + x1) / 2 - cx, (y0 + y1) / 2 - cy
        n = math.hypot(mx, my)
        qx, qy = cx + mx / n * w, cy + my / n * w
        for k in range(24):
            s = k / 24
            pts.append(((1 - s) ** 2 * x0 + 2 * (1 - s) * s * qx + s * s * x1,
                        (1 - s) ** 2 * y0 + 2 * (1 - s) * s * qy + s * s * y1))
    draw.polygon(pts, fill=(255, 255, 255, 255))


def shadowed(img, painter):
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    painter(ImageDraw.Draw(layer))
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow.putalpha(layer.getchannel("A").point(lambda v: v * 0.35).filter(ImageFilter.GaussianBlur(18)))
    img.alpha_composite(shadow, (0, 14))
    img.alpha_composite(layer)
    return img


def save(img, name):
    sizes = [(n, n) for n in (16, 24, 32, 48, 64, 128, 256)]
    img.resize((256, 256), Image.LANCZOS).save(OUT / f"{name}.ico", sizes=sizes)
    img.resize((256, 256), Image.LANCZOS).save(OUT / f"{name}.png")


start = shadowed(base((91, 61, 245), (24, 200, 232)), lambda d: (
    sparkle(d, S * 0.45, S * 0.55, S * 0.31, S * 0.07),
    sparkle(d, S * 0.73, S * 0.27, S * 0.13, S * 0.03)))
save(start, "local_ai")

stop = shadowed(base((246, 104, 96), (176, 34, 72)), lambda d: d.rounded_rectangle(
    (S * 0.32, S * 0.32, S * 0.68, S * 0.68), radius=S * 0.07, fill=(255, 255, 255, 255)))
save(stop, "local_ai_stop")
print("ok", sorted(p.name for p in OUT.iterdir()))
