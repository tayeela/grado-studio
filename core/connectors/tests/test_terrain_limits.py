import io
import unittest

import _paths  # noqa: F401
from grado_connectors import ConnectorError, TerrainContours

try:
    from PIL import Image
except ImportError:
    Image = None


def _tile(z, x, y):
    """Terrarium-тайл с уклоном 0…255 м по строкам."""
    im = Image.new("RGB", (256, 256))
    for j in range(256):
        h = 32768 + j
        for i in range(256):
            im.putpixel((i, j), (h // 256, h % 256, 0))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


@unittest.skipUnless(Image, "нужен Pillow")
class TestIntervalLimits(unittest.TestCase):
    BBOX = (37.60, 55.75, 37.601, 55.751)

    def _fetch(self, interval):
        return TerrainContours(transport=_tile).fetch(self.BBOX, interval=interval)

    def test_bad_interval_rejected(self):
        for bad in (0, -5, float("nan"), float("inf"), "abc"):
            with self.assertRaises(ConnectorError, msg=str(bad)):
                self._fetch(bad)

    def test_too_many_levels_rejected(self):
        with self.assertRaises(ConnectorError):
            self._fetch(0.0001)

    def test_normal_interval_works(self):
        self.assertTrue(self._fetch(10)["features"])


if __name__ == "__main__":
    unittest.main()
