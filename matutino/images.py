"""Shrink downloaded pictures before they are stored.

News sites serve photos at 2000-3000 px and comics at 2800 px; stored as
is, one issue took 135 MB on a 13 GB root disk. Pictures are scaled to at
most MAX_WIDTH and re-encoded: photos as JPEG, line art and anything with
transparency as PNG. Without Pillow the originals are kept.
"""

import io

try:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = 60000000  # beyond this, refuse rather than decode
except ImportError:  # stdlib-only install
    Image = None

AVAILABLE = Image is not None
MAX_WIDTH = 1400
JPEG_QUALITY = 80


class Rejected(Exception):
    """The bytes claim to be an image but are hostile or broken."""


def shrink(data, ext):
    """Return (bytes, ext) ready to store; raise Rejected for a pixel bomb."""
    if Image is None:
        return data, ext
    try:
        im = Image.open(io.BytesIO(data))
        if getattr(im, "is_animated", False):
            return data, ext  # an animated GIF loses its point as a still
        im.load()
    except Image.DecompressionBombError:
        raise Rejected("image too large to decode")
    except Exception:
        return data, ext
    w, h = im.size
    if w > MAX_WIDTH:
        im = im.resize((MAX_WIDTH, max(1, round(h * MAX_WIDTH / float(w)))), Image.LANCZOS)
    alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    out = io.BytesIO()
    if ext in ("png", "gif") or alpha:
        if im.mode not in ("RGB", "RGBA", "L", "LA", "P"):
            im = im.convert("RGBA" if alpha else "RGB")
        im.save(out, "PNG", optimize=True)
        new_ext = "png"
    else:
        if im.mode != "RGB":
            im = im.convert("RGB")
        im.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        new_ext = "jpg"
    new = out.getvalue()
    if w <= MAX_WIDTH and len(new) >= len(data) and new_ext == ext:
        return data, ext  # already small; re-encoding only cost quality
    return new, new_ext
