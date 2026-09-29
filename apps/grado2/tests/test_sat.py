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

    def test_archive(self):
        """Лист 1400 × 700 м при 0,3 м/пикс — 4667 × 2333 px: два куска; в DXF — растры с полным путём и рамка."""
        base = "/Users/someone/Downloads/sputnik_3_20260930-120000"
        with tempfile.TemporaryDirectory() as d:
            frame = sat_io.frame_msk((37.162, 55.341), [0, 0, 140, 70], 10000)
            data = sat_io.export_sat(frame, d, base, tiles=FakeTiles(d), z=15)
        z = zipfile.ZipFile(io.BytesIO(data))
        names = set(z.namelist())
        self.assertTrue({f"sputnik_3_20260930-120000/{n}" for n in ("sputnik_yandex_01.jpg", "sputnik_yandex_02.jpg", "sputnik_yandex_01.jgw",
                         "sputnik_yandex.dxf", "sputnik_yandex.scr", "README.txt")} <= names)
        from PIL import Image
        f = "sputnik_3_20260930-120000/"
        self.assertEqual(Image.open(io.BytesIO(z.read(f + "sputnik_yandex_01.jpg"))).size, (4096, 2333))
        self.assertEqual(Image.open(io.BytesIO(z.read(f + "sputnik_yandex_02.jpg"))).size, (571, 2333))
        jgw = z.read(f + "sputnik_yandex_02.jgw").decode().split()
        self.assertAlmostEqual(float(jgw[4]), frame[0] + 4096 * .3 + .15, places=3)
        self.assertAlmostEqual(float(jgw[5]), frame[3] - .15, places=3)
        import ezdxf
        doc = ezdxf.read(io.StringIO(z.read(f + "sputnik_yandex.dxf").decode("utf-8")))
        imgs = [e for e in doc.modelspace() if e.dxftype() == "IMAGE"]
        self.assertEqual(len(imgs), 2)
        self.assertEqual(imgs[0].image_def.dxf.filename, base + "/sputnik_yandex_01.jpg")
        self.assertAlmostEqual(imgs[1].dxf.insert[0], frame[0] + 4096 * .3, places=3)
        self.assertAlmostEqual(imgs[1].dxf.insert[1], frame[3] - 2333 * .3, places=3)   # снимок привязан к верхнему краю рамки
        scr = z.read(f + "sputnik_yandex.scr").decode().split("\n")
        self.assertEqual(scr[:3], ["-IMAGE", "A", "sputnik_yandex_01.jpg"])

    def test_too_large(self):
        with self.assertRaises(sat_io.SatError):
            sat_io.export_sat((0, 0, 20000, 20000), "/nonexistent", tiles=FakeTiles("/nonexistent"))


if __name__ == "__main__":
    unittest.main()
