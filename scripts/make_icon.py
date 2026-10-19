"""Render the SpaceHound app icon (assets/icon.ico + assets/icon.png). Needs Pillow."""

import math
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")
S = 1024  # draw big, scale down for crisp edges


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def render():
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # diagonal violet -> cyan gradient
    grad = Image.new("RGBA", (S, S))
    px = grad.load()
    c0, c1 = (139, 92, 246), (34, 211, 238)
    for y in range(S):
        for x in range(S):
            t = (x + y) / (2 * S)
            r, g, b = lerp(c0, c1, t)
            px[x, y] = (r, g, b, 255)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((40, 40, S - 40, S - 40), radius=230, fill=255)
    base.paste(grad, (0, 0), mask)

    # soft highlight
    hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse((-200, -420, S + 200, 470), fill=(255, 255, 255, 38))
    hl.putalpha(Image.composite(hl.getchannel("A"), Image.new("L", (S, S), 0), mask))
    base = Image.alpha_composite(base, hl)

    d = ImageDraw.Draw(base)
    white = (255, 255, 255, 255)
    cx, cy, r = S // 2, 600, 300
    w = 64
    # gauge arc (from 200deg to 340deg)
    d.arc((cx - r, cy - r, cx + r, cy + r), start=196, end=344, fill=white, width=w)
    for ang in (196, 344):  # round caps
        a = math.radians(ang)
        x, y = cx + (r - w / 2) * math.cos(a), cy + (r - w / 2) * math.sin(a)
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=white)
    # needle pointing up-right
    a = math.radians(-48)
    nx, ny = cx + 205 * math.cos(a), cy + 205 * math.sin(a)
    d.line((cx, cy, nx, ny), fill=white, width=58)
    d.ellipse((nx - 29, ny - 29, nx + 29, ny + 29), fill=white)
    d.ellipse((cx - 62, cy - 62, cx + 62, cy + 62), fill=white)
    # base line
    d.rounded_rectangle((cx - 250, 800, cx + 250, 856), radius=28, fill=white)
    return base


def main():
    os.makedirs(OUT, exist_ok=True)
    img = render()
    img.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT, "icon.png"))
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, "icon.ico"), sizes=sizes)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
