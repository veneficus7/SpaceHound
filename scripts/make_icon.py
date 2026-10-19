"""Render the SpaceHound logo (by Veneficus): a sand-coloured hound sniffing out amber
"sonar" waves on an espresso tile lit like a desert lamp.

Writes assets/icon.ico, assets/icon.png, assets/logo.svg, ui/favicon.png and
ui/logo-mark.svg (the mark alone, for the dark badges in the app). Needs Pillow.
The same path data drives the PNG rendering and the SVG files.
"""

import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 1024          # design units
SS = 2            # supersampling factor for smooth edges

# ----------------------------------------------------------------------------- shapes (1024 units)
DX = -70  # shift the whole mark left to leave room for the waves

HEAD = [
    ("M", 300, 880),
    ("C", 236, 720, 238, 520, 322, 420),
    ("C", 380, 350, 470, 318, 560, 334),
    ("C", 640, 348, 704, 396, 770, 448),
    ("C", 802, 472, 824, 494, 822, 524),
    ("C", 819, 554, 792, 566, 760, 566),
    ("C", 712, 568, 664, 572, 630, 596),
    ("C", 604, 616, 594, 648, 604, 690),
    ("C", 614, 740, 642, 800, 652, 880),
    ("Z",),
]
EAR = [
    ("M", 404, 382),
    ("C", 464, 366, 514, 412, 510, 480),
    ("C", 508, 584, 488, 690, 436, 750),
    ("C", 404, 788, 346, 772, 344, 714),
    ("C", 342, 622, 350, 470, 404, 382),
    ("Z",),
]
# collar band across the neck (clipped to the head shape) and a hanging tag
COLLAR = [("M", 200, 768), ("L", 700, 742), ("L", 700, 808), ("L", 200, 834), ("Z",)]
COLLAR_COLOR = (170, 238, 250)   # spice blue
TAG = (470, 846, 30)
TAG_COLOR = (240, 169, 60)
EYE = (606, 446, 25)        # cx, cy, r
NOSE = (806, 518, 32)
WAVE_C = (848, 520)
WAVES = [(78, 30, 0.95), (138, 30, 0.7), (198, 30, 0.42)]   # radius, width, opacity
WAVE_SPAN = 52              # degrees either side of horizontal

C_A, C_B, C_C = (58, 44, 32), (32, 25, 19), (18, 14, 11)   # tile gradient: lamp-lit espresso
EAR_COLOR = (240, 169, 60)
DARK = (23, 18, 15)
SAND = (239, 227, 204)
AMBER = (240, 169, 60)


def shift(path):
    out = []
    for cmd in path:
        if cmd[0] == "Z":
            out.append(cmd)
        else:
            vals = list(cmd[1:])
            for i in range(0, len(vals), 2):
                vals[i] += DX
            out.append((cmd[0], *vals))
    return out


def bezier_points(path, steps=40):
    pts = []
    cur = None
    for cmd in path:
        if cmd[0] == "M":
            cur = (cmd[1], cmd[2])
            pts.append(cur)
        elif cmd[0] == "L":
            cur = (cmd[1], cmd[2])
            pts.append(cur)
        elif cmd[0] == "C":
            x0, y0 = cur
            x1, y1, x2, y2, x3, y3 = cmd[1:]
            for i in range(1, steps + 1):
                t = i / steps
                mt = 1 - t
                x = mt ** 3 * x0 + 3 * mt * mt * t * x1 + 3 * mt * t * t * x2 + t ** 3 * x3
                y = mt ** 3 * y0 + 3 * mt * mt * t * y1 + 3 * mt * t * t * y2 + t ** 3 * y3
                pts.append((x, y))
            cur = (x3, y3)
    return pts


def svg_path(path):
    parts = []
    for cmd in path:
        if cmd[0] == "Z":
            parts.append("Z")
        else:
            parts.append(cmd[0] + " " + " ".join(f"{v:g}" for v in cmd[1:]))
    return " ".join(parts)


def squircle_mask(size, margin, n=5.0):
    """Superellipse (iOS / Windows 11 style) mask."""
    mask = Image.new("L", (size, size), 0)
    px = mask.load()
    c = size / 2
    r = size / 2 - margin
    for y in range(size):
        dy = abs((y + 0.5 - c) / r)
        if dy >= 1:
            continue
        span = r * (1 - dy ** n) ** (1 / n)
        x0, x1 = int(c - span), int(c + span)
        for x in range(max(0, x0), min(size, x1 + 1)):
            px[x, y] = 255
    return mask


def gradient(size):
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x * 0.55 + y * 0.45) / size
            if t < 0.5:
                k = t / 0.5
                c = tuple(int(C_A[i] + (C_B[i] - C_A[i]) * k) for i in range(3))
            else:
                k = (t - 0.5) / 0.5
                c = tuple(int(C_B[i] + (C_C[i] - C_B[i]) * k) for i in range(3))
            px[x, y] = c
    return img


def scale_pts(pts, k):
    return [(x * k, y * k) for x, y in pts]


def render(size_units=S):
    W = size_units * SS
    k = W / S
    base = gradient(W).convert("RGBA")
    mask = squircle_mask(W, int(36 * k))
    # soft light from the top-left
    glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    gx, gy = (WAVE_C[0] + DX) * k, WAVE_C[1] * k
    ImageDraw.Draw(glow).ellipse((gx - 0.42 * W, gy - 0.42 * W, gx + 0.42 * W, gy + 0.42 * W), fill=AMBER + (70,))
    glow = glow.filter(ImageFilter.GaussianBlur(120 * k))
    base = Image.alpha_composite(base, glow)

    # drop shadow of the mark
    shadow = Image.new("L", (W, W), 0)
    sd = ImageDraw.Draw(shadow)
    sd.polygon(scale_pts(bezier_points(shift(HEAD)), k), fill=150)
    shadow = shadow.filter(ImageFilter.GaussianBlur(26 * k))
    shadow = ImageChops.offset(shadow, int(0 * k), int(18 * k))
    dark = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    dark.putalpha(shadow)
    base = Image.alpha_composite(base, dark)

    d = ImageDraw.Draw(base)
    white = (255, 255, 255, 255)
    sand = SAND + (255,)
    # sonar waves
    cx, cy = (WAVE_C[0] + DX) * k, WAVE_C[1] * k
    for r, w, a in WAVES:
        layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        rr, ww = r * k, w * k
        ld.arc((cx - rr, cy - rr, cx + rr, cy + rr), start=-WAVE_SPAN, end=WAVE_SPAN, fill=AMBER + (int(255 * a),), width=int(ww))
        for ang in (-WAVE_SPAN, WAVE_SPAN):  # round caps
            t = math.radians(ang)
            ex, ey = cx + (rr - ww / 2) * math.cos(t), cy + (rr - ww / 2) * math.sin(t)
            ld.ellipse((ex - ww / 2, ey - ww / 2, ex + ww / 2, ey + ww / 2), fill=AMBER + (int(255 * a),))
        base = Image.alpha_composite(base, layer)
    d = ImageDraw.Draw(base)
    # head, ear, eye, nose
    head_pts = scale_pts(bezier_points(shift(HEAD)), k)
    d.polygon(head_pts, fill=sand)
    # collar: band clipped to the head silhouette
    head_mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(head_mask).polygon(head_pts, fill=255)
    band = Image.new("L", (W, W), 0)
    ImageDraw.Draw(band).polygon(scale_pts(bezier_points(shift(COLLAR)), k), fill=255)
    collar = Image.new("RGBA", (W, W), COLLAR_COLOR + (255,))
    collar.putalpha(ImageChops.multiply(head_mask, band))
    base = Image.alpha_composite(base, collar)
    d = ImageDraw.Draw(base)
    tx, ty, tr = (TAG[0] + DX) * k, TAG[1] * k, TAG[2] * k
    d.ellipse((tx - tr, ty - tr, tx + tr, ty + tr), fill=TAG_COLOR + (255,))
    d.polygon(scale_pts(bezier_points(shift(EAR)), k), fill=EAR_COLOR + (255,))
    for (x, y, r) in (EYE, NOSE):
        x, y, r = (x + DX) * k, y * k, r * k
        d.ellipse((x - r, y - r, x + r, y + r), fill=DARK + (255,))
    # eye sparkle
    ex, ey, er = (EYE[0] + DX) * k, EYE[1] * k, EYE[2] * k
    d.ellipse((ex + er * 0.15, ey - er * 0.55, ex + er * 0.55, ey - er * 0.15), fill=white)

    # thin amber rim so the dark tile still reads on a dark taskbar
    rim = ImageChops.subtract(mask, squircle_mask(W, int(36 * k) + int(7 * k)))
    rim_layer = Image.new("RGBA", (W, W), AMBER + (0,))
    rim_layer.putalpha(rim.point(lambda v: int(v * 0.4)))
    base = Image.alpha_composite(base, rim_layer)

    out = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    return out.resize((size_units, size_units), Image.LANCZOS)


def write_svgs():
    head, ear = svg_path(shift(HEAD)), svg_path(shift(EAR))
    (ex, ey, er), (nx, ny, nr) = EYE, NOSE
    cx, cy = WAVE_C[0] + DX, WAVE_C[1]
    arcs = []
    for r, w, a in WAVES:
        t = math.radians(WAVE_SPAN)
        x0, y0 = cx + r * math.cos(-t), cy + r * math.sin(-t)
        x1, y1 = cx + r * math.cos(t), cy + r * math.sin(t)
        arcs.append((f"M {x0:.1f} {y0:.1f} A {r} {r} 0 0 1 {x1:.1f} {y1:.1f}", w, a))
    wave_svg = "".join(f'<path d="{p}" fill="none" stroke="#f0a93c" stroke-opacity="{a}" stroke-width="{w}" stroke-linecap="round"/>' for p, w, a in arcs)
    collar = svg_path(shift(COLLAR))
    tx, ty, tr = TAG
    body = f"""{wave_svg}
<path d="{head}" fill="#efe3cc"/>
<path d="{collar}" fill="#aaeefa" clip-path="url(#head)"/><circle cx="{tx + DX}" cy="{ty}" r="{tr}" fill="#f0a93c"/>
<path d="{ear}" fill="#f0a93c"/>
<circle cx="{ex + DX}" cy="{ey}" r="{er}" fill="#17120f"/><circle cx="{nx + DX}" cy="{ny}" r="{nr}" fill="#17120f"/>"""
    clip = f'<clipPath id="head"><path d="{head}"/></clipPath>'
    logo = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3a2c20"/><stop offset=".5" stop-color="#201913"/><stop offset="1" stop-color="#120e0b"/></linearGradient><radialGradient id="lamp" cx="{cx}" cy="{cy}" r="430" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#f0a93c" stop-opacity=".28"/><stop offset="1" stop-color="#f0a93c" stop-opacity="0"/></radialGradient>{clip}</defs>
<rect x="36" y="36" width="952" height="952" rx="230" fill="url(#g)"/><rect x="36" y="36" width="952" height="952" rx="230" fill="url(#lamp)"/><rect x="39.5" y="39.5" width="945" height="945" rx="227" fill="none" stroke="#f0a93c" stroke-opacity=".4" stroke-width="7"/>
{body}
</svg>
"""
    # the mark alone (no tile), for the sidebar's gradient badge
    mark = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="150 290 820 620"><defs>{clip}</defs>
{body}
</svg>
"""
    with open(os.path.join(ROOT, "assets", "logo.svg"), "w", encoding="utf-8") as fh:
        fh.write(logo)
    with open(os.path.join(ROOT, "ui", "logo-mark.svg"), "w", encoding="utf-8") as fh:
        fh.write(mark)


def main():
    os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True)
    img = render()
    img.resize((512, 512), Image.LANCZOS).save(os.path.join(ROOT, "assets", "icon.png"))
    img.resize((256, 256), Image.LANCZOS).save(os.path.join(ROOT, "ui", "favicon.png"))
    sizes = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.resize((256, 256), Image.LANCZOS).save(os.path.join(ROOT, "assets", "icon.ico"), sizes=sizes)
    write_svgs()
    # preview sheet: big + small sizes on dark and light backgrounds
    sheet = Image.new("RGBA", (980, 560), (18, 14, 11, 255))
    sheet.paste(img.resize((420, 420), Image.LANCZOS), (30, 70), img.resize((420, 420), Image.LANCZOS))
    x = 500
    for sz in (128, 64, 48, 32, 24, 16):
        small = img.resize((sz, sz), Image.LANCZOS)
        sheet.paste(small, (x, 120), small)
        x += sz + 22
    light = Image.new("RGBA", (460, 200), (241, 231, 214, 255))
    lx = 20
    for sz in (128, 48, 32, 16):
        small = img.resize((sz, sz), Image.LANCZOS)
        light.paste(small, (lx, 36), small)
        lx += sz + 26
    sheet.paste(light, (500, 320))
    sheet.save(os.path.join(ROOT, "assets", "logo-preview.png"))
    print("icon written")


if __name__ == "__main__":
    main()
