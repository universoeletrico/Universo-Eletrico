"""Testes offline: envio de artes nao acessa GitHub nem Instagram."""
import io
import unittest

from PIL import Image
from painel.image_management import normalize_post_image


def example(fmt="PNG", size=(1080, 1350)):
    image = Image.new("RGB", size, (16, 70, 115))
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


class TestImageManagement(unittest.TestCase):
    def test_valid_png_to_jpeg_feed(self):
        output = normalize_post_image(example())
        with Image.open(io.BytesIO(output)) as img:
            self.assertEqual(img.format, "JPEG")
            self.assertEqual(img.size, (1080, 1350))

    def test_preserves_full_image_with_padding(self):
        output = normalize_post_image(example(size=(1200, 1200)))
        with Image.open(io.BytesIO(output)) as img:
            self.assertEqual(img.size, (1080, 1350))

    def test_rejects_invalid(self):
        with self.assertRaises(ValueError):
            normalize_post_image(b"not-an-image")

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            normalize_post_image(b"")

    def test_rejects_tiny(self):
        with self.assertRaises(ValueError):
            normalize_post_image(example(size=(250, 250)))


if __name__ == "__main__":
    unittest.main()
