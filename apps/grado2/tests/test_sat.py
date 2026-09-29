"""Спутник Яндекса для AutoCAD (sat_io): рамка листа в МСК, подробность снимка, архив с DXF, JPG и JGW."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import sat_io
from grado_connectors import crs


class FakeTiles:
    """Тайлы без сети: однотонные JPEG на диске; считает скачивания."""

    def __init__(self, folder):
        self.folder, self.got = Path(folder), 0

    def path(self, z, x, y):
        return self.folder / f"{z}_{x}_{y}.jpg"

    def ensure(self, z, x, y):
        from PIL import Image
        p = self.path(z, x, y)
        if not p.exists():
            Image.new("RGB", (256, 256), ((x * 37) % 255, (y * 53) % 255, 90)).save(p, "JPEG")
            self.got += 1
        return True


class SatExport(unittest.TestCase):
    def test_frame_is_sheet_rect_in_msk(self):
        c = (37.162, 55.341)
        x0, y0, x1, y1 = sat_io.frame_msk(c, [0, 44, 420, 253], 10000)
        self.assertAlmostEqual(x1 - x0, 4200, places=6)
        self.assertAlmostEqual(y1 - y0, 2530, places=6)
        cx, cy = crs.wgs84_to_msk(*c)
        self.assertAlmostEqual((x0 + x1) / 2, cx, places=6)

    def test_auto_resolution(self):
        self.assertEqual(sat_io.auto_mpp((0, 0, 1000, 800)), 0.5)
        self.assertEqual(sat_io.auto_mpp((0, 0, 4200, 2530)), 1.0)

    def test_archive(self):
        with tempfile.TemporaryDirectory() as d:
            frame = sat_io.frame_msk((37.162, 55.341), [0, 0, 60, 40], 10000)   # 600 × 400 м
            data = sat_io.export_sat(frame, 2.0, d, tiles=FakeTiles(d))
        z = zipfile.ZipFile(io.BytesIO(data))
        self.assertTrue({"sputnik_yandex.jpg", "sputnik_yandex.jgw", "sputnik_yandex.dxf", "README.txt"} <= set(z.namelist()))
        from PIL import Image
        self.assertEqual(Image.open(io.BytesIO(z.read("sputnik_yandex.jpg"))).size, (300, 200))
        jgw = z.read("sputnik_yandex.jgw").decode().split()
        self.assertAlmostEqual(float(jgw[4]), frame[0] + 1.0, places=3)
        self.assertAlmostEqual(float(jgw[5]), frame[3] - 1.0, places=3)
        import ezdxf
        doc = ezdxf.read(io.StringIO(z.read("sputnik_yandex.dxf").decode("utf-8")))
        img = next(e for e in doc.modelspace() if e.dxftype() == "IMAGE")
        self.assertAlmostEqual(img.dxf.insert[0], frame[0], places=3)
        self.assertAlmostEqual(img.dxf.insert[1], frame[1], places=3)

    def test_too_large(self):
        with self.assertRaises(sat_io.SatError):
            sat_io.export_sat((0, 0, 20000, 20000), 0.5, "/nonexistent", tiles=FakeTiles("/nonexistent"))


if __name__ == "__main__":
    unittest.main()
