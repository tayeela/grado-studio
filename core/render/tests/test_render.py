import re
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "model"))

from grado_render import (Font, MapTransform, PdfBackend, StyleSet,  # noqa: E402
                          build_ops, find_font, render_svg)
from grado_model import Project  # noqa: E402

OPS = [
    {"op": "clip", "rect": (10, 10, 100, 100)},
    {"op": "path", "rings": [[(20, 20), (80, 20), (80, 80), (20, 80)]],
     "closed": True, "fill": (0.9, 0.9, 0.6), "stroke": (0.3, 0.3, 0.2),
     "width": 0.4, "dash": [2, 1]},
    {"op": "circle", "x": 50, "y": 50, "r": 2, "fill": (0.2, 0.4, 0.7),
     "stroke": None, "width": 0.2},
    {"op": "text", "x": 50, "y": 45, "size": 4, "text": "Москва",
     "color": (0, 0, 0), "anchor": "middle"},
    {"op": "unclip"},
]


class TestFont(unittest.TestCase):
    def setUp(self):
        self.font = Font(find_font())

    def test_cyrillic_glyphs(self):
        gid_lat = self.font.gid_for("A")
        gid_cyr = self.font.gid_for("А")  # U+0410
        self.assertGreater(gid_lat, 0)
        self.assertGreater(gid_cyr, 0)
        self.assertNotEqual(gid_lat, gid_cyr)

    def test_widths(self):
        self.assertGreater(self.font.width_1000("Ш"), 300)
        w = self.font.text_width("Москва", 12)
        self.assertGreater(w, 25)
        self.assertLess(w, 70)


class TestMapTransform(unittest.TestCase):
    def test_scale_and_flip(self):
        tr = MapTransform((10, 10, 100, 100), (500, 500), scale=1000)
        self.assertEqual(tr.to_mm(500, 500), (60.0, 60.0))
        x, y = tr.to_mm(510, 520)
        self.assertAlmostEqual(x, 70.0, msg="1 м = 1 мм при М 1:1000")
        self.assertAlmostEqual(y, 40.0, msg="ось Y листа направлена вниз")


class TestSceneFromProject(unittest.TestCase):
    def test_build_ops(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Project.create(Path(tmp) / "t.grado", "Сцена")
            layer = p.add_layer("tp.func_zone")
            layer.add_feature(
                {"type": "Polygon", "coordinates": [[
                    [413000, 6178000], [413200, 6178000], [413200, 6178150],
                    [413000, 6178150], [413000, 6178000]]]},
                attrs={"zone_title": "Ж-1"})
            ops = build_ops(p, (10, 10, 257, 180), scale=2000)
            p.close()
        kinds = [o["op"] for o in ops]
        self.assertEqual(kinds[0], "clip")
        self.assertEqual(kinds[-1], "unclip")
        self.assertIn("path", kinds)
        texts = [o for o in ops if o["op"] == "text"]
        self.assertEqual(texts[0]["text"], "Ж-1", "подпись из атрибута стиля")
        path = next(o for o in ops if o["op"] == "path")
        xs = [x for x, _ in path["rings"][0]]
        self.assertTrue(all(10 <= x <= 267 for x in xs), "геометрия в рамке")
        # 200 м при М 1:2000 = 100 мм
        self.assertAlmostEqual(max(xs) - min(xs), 100.0, places=6)


class TestPdfBackend(unittest.TestCase):
    def setUp(self):
        self.backend = PdfBackend()
        self.pdf = self.backend.render([(297, 210, OPS)])

    def test_structure(self):
        self.assertTrue(self.pdf.startswith(b"%PDF-1.6"))
        self.assertTrue(self.pdf.rstrip().endswith(b"%%EOF"))
        self.assertIn(b"/Identity-H", self.pdf)
        self.assertIn(b"/FontFile2", self.pdf)

    def test_xref_offsets_valid(self):
        m = re.search(rb"xref\n0 (\d+)\n", self.pdf)
        n = int(m.group(1))
        table_at = m.end()
        for num in range(1, n):
            entry = self.pdf[table_at + 20 * num: table_at + 20 * num + 20]
            offset = int(entry[:10])
            self.assertTrue(
                self.pdf[offset:].startswith(f"{num} 0 obj".encode()),
                f"смещение объекта {num} в xref неверно")

    def test_content_stream_draws(self):
        streams = re.findall(rb"stream\n(.*?)\nendstream", self.pdf, re.S)
        page = None
        for s in streams:
            try:
                data = zlib.decompress(s)
            except zlib.error:
                continue
            if b"Tj" in data:
                page = data
        self.assertIsNotNone(page)
        self.assertIn(b" W n", page, "клип рамки карты")
        self.assertIn(b"\nB\n", page, "заливка с обводкой")
        gid = self.backend.font.gid_for("М")
        self.assertIn(f"{gid:04X}".encode(), page, "глиф «М» в тексте")

    def test_multipage(self):
        pdf = PdfBackend().render([(297, 210, OPS), (210, 297, OPS)])
        self.assertEqual(pdf.count(b"/Type /Page "), 2)
        self.assertIn(b"/Count 2", pdf)


class TestWysiwyg(unittest.TestCase):
    def test_both_backends_consume_same_ops(self):
        import copy
        ops = copy.deepcopy(OPS)
        svg = render_svg(297, 210, ops)
        pdf = PdfBackend().render([(297, 210, ops)])
        self.assertEqual(ops, OPS, "бэкенды не мутируют операции")
        self.assertIn("Москва", svg)
        self.assertIn('stroke-dasharray="2,1"', svg)
        self.assertIn("clip-path", svg)
        self.assertGreater(len(pdf), 1000)


class TestHatch(unittest.TestCase):
    def test_restrict_gets_hatch_ops(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Project.create(Path(tmp) / "t.grado", "Штриховка")
            p.add_layer("terr.restrict").add_feature(
                {"type": "Polygon", "coordinates": [[
                    [413000, 6178000], [413100, 6178000], [413100, 6178080],
                    [413000, 6178080], [413000, 6178000]]]},
                attrs={"kind": "СЗЗ"})
            ops = build_ops(p, (10, 10, 200, 160), scale=1000)
            p.close()
        hatches = [o for o in ops if o["op"] == "path" and o.get("width") == 0.16]
        self.assertEqual(len(hatches), 1, "один op штриховки на полигон")
        segs = hatches[0]["rings"]
        self.assertGreater(len(segs), 10, "полигон 100×80 мм — десятки линий")
        for seg in segs:
            self.assertEqual(len(seg), 2, "штриховка — отрезки")

    def test_hatch_segments_inside_frame(self):
        from grado_render.scene import hatch_ops
        square = [[(0, 0), (10, 0), (10, 10), (0, 10)]]
        ops = hatch_ops(square, spacing=2, stroke=(0, 0, 0))
        for seg in ops[0]["rings"]:
            for x, y in seg:
                self.assertTrue(-1e-6 <= x <= 10 + 1e-6)
                self.assertTrue(-1e-6 <= y <= 10 + 1e-6)


# минимальный «JPEG»: SOI + SOF0 (длина 11, точность 8, 1×2, 3 компоненты)
FAKE_JPEG = bytes([0xFF, 0xD8, 0xFF, 0xC0, 0x00, 0x0B, 0x08,
                   0x00, 0x01, 0x00, 0x02, 0x03])


class TestImages(unittest.TestCase):
    def test_jpeg_info(self):
        from grado_render import jpeg_info
        self.assertEqual(jpeg_info(FAKE_JPEG), (2, 1, 3))
        with self.assertRaises(ValueError):
            jpeg_info(b"\x89PNG\r\n")

    def _ops(self):
        return [
            {"op": "image", "data": FAKE_JPEG, "x": 10, "y": 10,
             "w": 100, "h": 50},
            {"op": "image", "data": FAKE_JPEG,
             "quad": ((120, 10), (170, 12), (118, 60))},
        ] + list(OPS)

    def test_pdf_xobject(self):
        pdf = PdfBackend().render([(297, 210, self._ops())])
        self.assertIn(b"/Subtype /Image", pdf)
        self.assertIn(b"/Filter /DCTDecode", pdf)
        self.assertIn(b"/Width 2 /Height 1", pdf)
        self.assertIn(b"/XObject << /Im1", pdf)
        # два op с одинаковыми данными → один встроенный XObject
        self.assertEqual(pdf.count(b"/Subtype /Image"), 1)
        # сам JPEG лежит в потоке без перекодирования
        self.assertIn(FAKE_JPEG, pdf)

    def test_pdf_xref_still_valid_with_images(self):
        pdf = PdfBackend().render([(297, 210, self._ops())])
        m = re.search(rb"xref\n0 (\d+)\n", pdf)
        n = int(m.group(1))
        table_at = m.end()
        for num in range(1, n):
            entry = pdf[table_at + 20 * num: table_at + 20 * num + 20]
            self.assertTrue(
                pdf[int(entry[:10]):].startswith(f"{num} 0 obj".encode()),
                f"смещение объекта {num} в xref неверно")

    def test_pdf_stream_has_do(self):
        backend = PdfBackend()
        pdf = backend.render([(297, 210, self._ops())])
        streams = re.findall(rb"stream\n(.*?)\nendstream", pdf, re.S)
        page = None
        for s in streams:
            try:
                data = zlib.decompress(s)
            except zlib.error:
                continue
            if b"Do" in data:
                page = data
        self.assertIsNotNone(page)
        self.assertEqual(page.count(b"/Im1 Do"), 2)
        # осевой случай: матрица [w 0 0 h x y]
        self.assertIn(b"283.465 0 0 141.732", page)

    def test_svg_image_data_uri(self):
        svg = render_svg(297, 210, self._ops())
        self.assertIn("data:image/jpeg;base64,", svg)
        self.assertIn("matrix(", svg, "quad → аффинное размещение")
        self.assertIn('preserveAspectRatio="none"', svg)


class TestStyleLibrary(unittest.TestCase):
    def test_styles_come_from_json(self):
        from grado_render import hex_to_rgb, load_library
        lib = load_library()
        for sid in ("boundary.line", "func_zone.fill", "restrict.hatch",
                    "red.line.projected", "social.point"):
            self.assertIn(sid, lib["styles"])
        st = StyleSet().resolve("tp.func_zone")
        self.assertEqual(st.fill, hex_to_rgb("#faf0bf"))
        self.assertEqual(st.stroke, hex_to_rgb("#b89e59"))
        self.assertEqual(st.label, "zone_title")
        self.assertAlmostEqual(st.width, 0.25)

    def test_hex_to_rgb(self):
        from grado_render import hex_to_rgb
        self.assertEqual(hex_to_rgb("#ffffff"), (1.0, 1.0, 1.0))
        self.assertEqual(hex_to_rgb("#000000"), (0.0, 0.0, 0.0))
        self.assertIsNone(hex_to_rgb(None))

    def test_codes_index(self):
        # разные коды классификатора разрешаются в свои стили
        s = StyleSet()
        self.assertTrue(s.resolve("terr.restrict").hatch)
        self.assertTrue(s.resolve("cad.zouit").hatch)
        self.assertFalse(s.resolve("oks.building").hatch)
        self.assertEqual(s.resolve("social.object").marker, 1.5)


class TestStyleSet(unittest.TestCase):
    def test_fallback(self):
        st = StyleSet().resolve("нет.такого")
        self.assertIsNotNone(st.stroke)

    def test_zoning_below_redlines(self):
        s = StyleSet()
        self.assertLess(s.resolve("tp.func_zone").z, s.resolve("pp.red_line").z)


if __name__ == "__main__":
    unittest.main()
