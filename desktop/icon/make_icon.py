"""Draws the Matutino icon from plain shapes (no fonts): a masthead M, a full
stop in the paper's accent red, and the masthead's double rule.

    python desktop/icon/make_icon.py

Writes the web and tray icons into matutino/static/ and the app icons into
desktop/icon/ (Matutino.icns needs macOS's iconutil; the rest only Pillow).
"""
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
STATIC = os.path.join(ROOT, "matutino", "static")
PAPER, INK, ACCENT = "#f5f1e8", "#141311", "#8e1f14"

# A Roman capital M in a 512 box: thin left stem, thick first diagonal, thin
# second diagonal, thick right stem, plain serifs.
M = [
    [(106, 136), (120, 136), (120, 376), (106, 376)],      # left stem (thin)
    [(104, 136), (156, 136), (244, 384), (230, 384)],      # first diagonal (thick)
    [(230, 384), (244, 384), (346, 136), (332, 136)],      # second diagonal (thin)
    [(332, 136), (380, 136), (380, 376), (332, 376)],      # right stem (thick)
    [(78, 128), (156, 128), (156, 138), (78, 138)],        # serifs
    [(318, 128), (404, 128), (404, 138), (318, 138)],
    [(82, 372), (144, 372), (144, 382), (82, 382)],
    [(308, 372), (404, 372), (404, 382), (308, 382)],
]
STOP = (418, 352, 448, 382)                                 # the full stop
RULES = [(86, 410, 426, 419), (86, 426, 426, 429)]          # the double rule


def shapes(ink=INK, accent=ACCENT, rule=True):
    """[(kind, coords, colour)] in the 512 box."""
    out = [("poly", p, ink) for p in M] + [("rect", STOP, accent)]
    if rule:
        out += [("rect", r, ink) for r in RULES]
    return out


# variant -> (background, scale, centre y of the glyph, glyph options)
VARIANTS = {
    "icon": ("square", 1.0, 232, {}),                  # full bleed: iOS and browsers round it themselves
    "maskable": ("square", .72, 232, {}),              # Android may crop to a circle: keep to the middle 80%
    "mac": ("mac", .74, 244, {}),                      # macOS tile with a shadow
    "tile": ("tile", .9, 248, {"rule": False}),        # Windows icon and tray: no rule, it blurs when small
    "template": (None, 1.18, 262, {"ink": "#000", "accent": "#000", "rule": False}),  # macOS menu bar
}


def _xf(scale, cy):
    return lambda x, y: (256 + (x - 256) * scale, cy + (y - 256) * scale)


def svg(variant):
    bg, scale, cy, opts = VARIANTS[variant]
    f = _xf(scale, cy)
    body = []
    if bg == "square":
        body.append('<rect width="512" height="512" fill="%s"/>' % PAPER)
    elif bg == "mac":
        body.append('<defs><filter id="s" x="-20%%" y="-20%%" width="140%%" height="140%%">'
                    '<feDropShadow dx="0" dy="6" stdDeviation="7" flood-opacity=".28"/></filter></defs>'
                    '<rect x="50" y="50" width="412" height="412" rx="92" fill="%s" filter="url(#s)"/>' % PAPER)
    elif bg == "tile":
        body.append('<rect x="16" y="16" width="480" height="480" rx="72" fill="%s"/>' % PAPER)
    for kind, c, colour in shapes(**opts):
        pts = c if kind == "poly" else [(c[0], c[1]), (c[2], c[1]), (c[2], c[3]), (c[0], c[3])]
        # One path per shape: overlapping strokes in one path could cancel out.
        body.append('<path fill="%s" d="M%s Z"/>' % (colour, " L".join("%g %g" % f(x, y) for x, y in pts)))
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">%s</svg>\n' % "".join(body)


def png(variant, size):
    bg, scale, cy, opts = VARIANTS[variant]
    k = 4 * size / 512.0                                    # draw 4x, then shrink: smooth edges
    big = int(size * 4)
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if bg == "square":
        d.rectangle((0, 0, big, big), fill=PAPER)
    elif bg == "mac":
        shadow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((50 * k, 56 * k, 462 * k, 468 * k), 92 * k, fill=(0, 0, 0, 72))
        im = Image.alpha_composite(im, shadow.filter(ImageFilter.GaussianBlur(7 * k)))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((50 * k, 50 * k, 462 * k, 462 * k), 92 * k, fill=PAPER)
    elif bg == "tile":
        d.rounded_rectangle((16 * k, 16 * k, 496 * k, 496 * k), 72 * k, fill=PAPER)
    f = _xf(scale, cy)
    for kind, c, colour in shapes(**opts):
        pts = c if kind == "poly" else [(c[0], c[1]), (c[2], c[1]), (c[2], c[3]), (c[0], c[3])]
        d.polygon([(x * k, y * k) for x, y in (f(*p) for p in pts)], fill=colour)
    return im.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(STATIC, exist_ok=True)
    with open(os.path.join(STATIC, "favicon.svg"), "w") as fh:
        fh.write(svg("icon"))
    for name, variant, size in [("favicon-32.png", "icon", 32), ("apple-touch-icon.png", "icon", 180),
                                ("icon-192.png", "icon", 192), ("icon-512.png", "icon", 512),
                                ("icon-maskable-512.png", "maskable", 512)]:
        png(variant, size).save(os.path.join(STATIC, name), optimize=True)
    for variant in ("icon", "mac", "tile", "template"):
        with open(os.path.join(HERE, "%s.svg" % variant), "w") as fh:
            fh.write(svg(variant))
    png("tile", 64).save(os.path.join(STATIC, "tray.png"))                  # Windows notification area
    png("template", 44).save(os.path.join(STATIC, "tray-template.png"))     # macOS menu bar, 22 pt @2x
    tile = png("tile", 256)
    tile.save(os.path.join(HERE, "Matutino.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                                         (128, 128), (256, 256)])
    if shutil.which("iconutil"):
        with tempfile.TemporaryDirectory() as tmp:
            iconset = os.path.join(tmp, "Matutino.iconset")
            os.makedirs(iconset)
            for pt in (16, 32, 128, 256, 512):
                png("mac", pt).save(os.path.join(iconset, "icon_%dx%d.png" % (pt, pt)))
                png("mac", pt * 2).save(os.path.join(iconset, "icon_%dx%d@2x.png" % (pt, pt)))
            subprocess.check_call(["iconutil", "-c", "icns", iconset, "-o", os.path.join(HERE, "Matutino.icns")])
    else:
        print("iconutil not found (macOS only): Matutino.icns left as it is", file=sys.stderr)
    print("icons written to %s and %s" % (STATIC, HERE))


if __name__ == "__main__":
    main()
