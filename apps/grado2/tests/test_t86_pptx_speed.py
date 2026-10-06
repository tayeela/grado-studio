"""T86: выгрузка PPTX быстро — кэш основы ЕГКО между PDF и PPTX, заливка контуров в растре по охвату, шрифты в файле."""
import io
import struct
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import print_io  # noqa: E402
from grado_render.backend_pptx import PptxBackend  # noqa: E402

LON, LAT = 37.525, 55.7925
MASK = {"type": "Polygon", "coordinates": [[[LON - .02, LAT - .01], [LON + .02, LAT - .01], [LON + .02, LAT + .01], [LON - .02, LAT + .01], [LON - .02, LAT - .01]]]}


def ring(lon, lat, d):
    return [[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]


class FakeEgko:
    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    def __call__(self, bbox, code):
        self.calls += 1
        if self.fail:
            raise OSError("no portal")
        return [{"geometry": {"type": "Polygon", "coordinates": [ring(LON, LAT, .004)]}},
                {"geometry": {"type": "Polygon", "coordinates": [ring(LON + .01, LAT, 1e-7)]}}]      # крошка: на листе не видна


class EgkoCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(print_io, "PRINT_OPS_CACHE", Path(self.tmp.name))
        self.p.start()
        self.rect = (10, 10, 400, 280)
        self.tr = print_io.MapTransform(self.rect, (LON, LAT), 25000)

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_second_call_uses_cache(self):
        e = FakeEgko()
        a = print_io.egko_ops(self.tr, self.rect, MASK, e)
        n = e.calls
        self.assertEqual(n, len(print_io.EGKO_BASE))
        b = print_io.egko_ops(self.tr, self.rect, MASK, e)
        self.assertEqual(e.calls, n, "ЕГКО второй раз не запрашивается")
        self.assertEqual(a, b)
        self.assertGreater(len(a), 2)

    def test_other_scale_is_other_key(self):
        e = FakeEgko()
        print_io.egko_ops(self.tr, self.rect, MASK, e)
        n = e.calls
        print_io.egko_ops(print_io.MapTransform(self.rect, (LON, LAT), 50000), self.rect, MASK, e)
        self.assertGreater(e.calls, n)

    def test_failed_layer_not_cached(self):
        e = FakeEgko(fail=True)
        print_io.egko_ops(self.tr, self.rect, MASK, e)
        self.assertEqual(list(Path(self.tmp.name).glob("*.pkl")), [])

    def test_tiny_polygons_skipped(self):
        e = FakeEgko()
        out = print_io.egko_ops(self.tr, self.rect, MASK, e)
        paths = [o for o in out if o["op"] == "path" and o.get("fill") != print_io.hex_to_rgb("#f3f3f1")]
        self.assertEqual(len(paths), len(print_io.EGKO_BASE), "по одному видимому контуру на слой, крошки нет")


class RasterFill(unittest.TestCase):
    def test_hole_and_speed(self):
        from PIL import Image
        outer = [(0, 0), (200, 0), (200, 100), (0, 100)]
        hole = [(80, 30), (120, 30), (120, 70), (80, 70)]
        ops = [{"op": "clip", "rect": (0, 0, 200, 100)}]
        ops += [{"op": "path", "rings": [outer, hole], "closed": True, "fill": (1, 0, 0), "stroke": None, "width": 0, "dash": None} for _ in range(300)]
        ops.append({"op": "unclip"})
        t = time.time()
        res = print_io.pptx_rasterize(ops, dpi=100)
        self.assertLess(time.time() - t, 20, "контуры с дырами не должны красить весь холст каждый")
        png = [o for o in res if o["op"] == "image"][0]["data"]
        im = Image.open(io.BytesIO(png)).convert("RGBA")
        k = im.width / 200
        self.assertEqual(im.getpixel((int(20 * k), int(50 * k)))[:3], (255, 0, 0))     # заливка
        self.assertEqual(im.getpixel((int(100 * k), int(50 * k)))[3], 0)               # дыра прозрачна


class FontsEmbedded(unittest.TestCase):
    def test_fonts_in_pptx(self):
        ops = [{"op": "text", "x": 10, "y": 10, "text": "Тест", "size": 3, "font_family": "sans", "color": (0, 0, 0)},
               {"op": "text", "x": 10, "y": 20, "text": "Жирный", "size": 3, "font_family": "sans-bold", "color": (0, 0, 0)},
               {"op": "text", "x": 10, "y": 30, "text": "Схема", "size": 3, "font_family": "ui", "color": (0, 0, 0)}]
        data = PptxBackend("t").render([(100, 100, [("Тексты", ops)])])
        z = zipfile.ZipFile(io.BytesIO(data))
        names = z.namelist()
        self.assertEqual(sorted(n for n in names if n.startswith("ppt/fonts/")), ["ppt/fonts/font1.fntdata", "ppt/fonts/font2.fntdata", "ppt/fonts/font3.fntdata"])
        pres = z.read("ppt/presentation.xml").decode("utf-8")
        self.assertIn("<p:embeddedFontLst>", pres)
        for face in ("Montserrat", "PT Sans"):
            self.assertIn(f'<p:font typeface="{face}"/>', pres)
        self.assertIn("fntdata", z.read("[Content_Types].xml").decode("utf-8"))
        rels = z.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
        self.assertEqual(rels.count("relationships/font"), 3)
        eot = z.read("ppt/fonts/font1.fntdata")
        size, fsize, ver = struct.unpack("<III", eot[:12])
        self.assertEqual((size, ver, struct.unpack("<H", eot[34:36])[0]), (len(eot), 0x00020001, 0x504C))
        self.assertEqual(eot[size - fsize:size - fsize + 4], b"\x00\x01\x00\x00")       # TrueType внутри


class Progress(unittest.TestCase):
    def test_sheet_progress_pdf_and_pptx(self):
        import server as S
        sh = {"title": "Лист", "size": "A3", "scale": 2000, "center": [LON, LAT], "legend": [], "tep": [], "layers": []}
        spec = {"sheets": [sh, sh]}
        for fn in (print_io.render_pdf, print_io.render_pptx):
            seen = []
            fn(spec, S.REDLN, S.LGR_DASH, None, lambda got, total: seen.append((got, total)))
            self.assertEqual(seen, [(0, 2), (1, 2), (2, 2)], fn.__name__)


if __name__ == "__main__":
    unittest.main()
