import io
import struct
import unittest
import zlib

from matutino import images

from fixtures import png


def pil_jpeg(w, h):
    from PIL import Image
    im = Image.new("RGB", (w, h))
    px = im.load()
    for x in range(0, w, 7):
        for y in range(0, h, 7):
            px[x, y] = ((x * 7) % 255, (y * 3) % 255, (x * y) % 255)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=95)
    return out.getvalue()


def size_of(data):
    from PIL import Image
    return Image.open(io.BytesIO(data)).size


@unittest.skipUnless(images.AVAILABLE, "Pillow not installed")
class Shrink(unittest.TestCase):
    def test_wide_photo_is_scaled_and_lighter(self):
        big = pil_jpeg(3000, 2000)
        data, ext = images.shrink(big, "jpg")
        self.assertEqual(ext, "jpg")
        self.assertEqual(size_of(data), (1400, 933))
        self.assertLess(len(data), len(big))

    def test_line_art_stays_png(self):
        data, ext = images.shrink(png(2800, 60, seed=4), "png")
        self.assertEqual((ext, size_of(data)), ("png", (1400, 30)))

    def test_webp_photo_becomes_jpeg(self):
        from PIL import Image
        out = io.BytesIO()
        Image.new("RGB", (1600, 900), (40, 90, 140)).save(out, "WEBP")
        data, ext = images.shrink(out.getvalue(), "webp")
        self.assertEqual((ext, size_of(data)), ("jpg", (1400, 788)))

    def test_small_image_is_left_alone(self):
        small = png(300, 200, seed=5)
        self.assertEqual(images.shrink(small, "png"), (small, "png"))

    def test_pixel_bomb_is_rejected(self):
        def chunk(t, d):
            return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
        bomb = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 30000, 30000, 8, 2, 0, 0, 0))
                + chunk(b"IEND", b""))
        with self.assertRaises(images.Rejected):
            images.shrink(bomb, "png")

    def test_garbage_passes_through(self):
        self.assertEqual(images.shrink(b"\x89PNG not really", "png"), (b"\x89PNG not really", "png"))


if __name__ == "__main__":
    unittest.main()
