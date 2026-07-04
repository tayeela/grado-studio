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


class TestMoscowLgrLibrary(unittest.TestCase):
    """Системная библиотека Эталона ЛГР (приказ ММА от 10.03.2025 № 65)."""

    def test_merged_library_valid(self):
        from grado_render import merged_library
        lib = merged_library()
        lgr = {sid: s for sid, s in lib["styles"].items()
               if sid.startswith("lgr.")}
        self.assertEqual(len(lgr), 54, "54 знака Эталона (5 КЛ + 27 ЗОУИТ + "
                                       "17 иных + 5 прил. 1)")
        codes = [s["lgr_code"] for s in lgr.values()]
        self.assertEqual(len(codes), len(set(codes)), "коды ЛГР уникальны")
        # базовые стили default.json не потеряны при мерже
        self.assertIn("func_zone.fill", lib["styles"])
        self.assertIn("fallback", lib)

    def test_priorities_of_annex2(self):
        from grado_render import merged_library
        by_code = {s["lgr_code"]: s for sid, s in
                   merged_library()["styles"].items() if sid.startswith("lgr.")}
        # выборка из приложения 2: 13 — высший (1), 45 — низший (27)
        self.assertEqual(by_code[13]["lgr_priority"], 1)
        self.assertEqual(by_code[45]["lgr_priority"], 27)
        self.assertEqual(by_code[16]["lgr_priority"], 12)
        # высший приоритет → рисуется поверх (больший z)
        self.assertGreater(by_code[13]["z"], by_code[45]["z"])

    def test_hatch_shape_and_colors(self):
        from grado_render import merged_library
        lib = merged_library()["styles"]
        vod = lib["lgr.vodookhr"]           # водоохранная: синяя 45° плотная
        self.assertEqual(vod["hatch"]["angle"], 45)
        self.assertEqual(vod["hatch"]["color"], "#0669b2")
        les = lib["lgr.lesopark"]           # лесопарковый пояс: сетка
        self.assertTrue(les["hatch"]["cross"])
        self.assertFalse(lib["lgr.zastroyka"]["hatch"],
                         "линия застройки — ЛГР без зоны")

    def test_hatch_ops_angles(self):
        from grado_render.scene import hatch_ops
        square = [[(0, 0), (10, 0), (10, 10), (0, 10)]]
        for angle in (0, 45, 90, 135):
            ops = hatch_ops(square, spacing=2, stroke=(0, 0, 0), angle=angle)
            self.assertTrue(ops, f"угол {angle}: есть штрихи")
            for seg in ops[0]["rings"]:
                for x, y in seg:
                    self.assertTrue(-1e-6 <= x <= 10 + 1e-6)
                    self.assertTrue(-1e-6 <= y <= 10 + 1e-6)
        h = hatch_ops(square, spacing=2, stroke=(0, 0, 0), angle=0)[0]["rings"]
        self.assertTrue(all(abs(a[1] - b[1]) < 1e-9 for a, b in h),
                        "угол 0 — горизонтальные отрезки")
        cross = hatch_ops(square, spacing=2, stroke=(0, 0, 0), cross=True)
        single = hatch_ops(square, spacing=2, stroke=(0, 0, 0), angle=45)
        self.assertGreater(len(cross[0]["rings"]), len(single[0]["rings"]),
                           "сетка гуще одиночной диагонали")

    def test_per_object_style_id_in_ops(self):
        # объект со style_id Эталона рендерится знаком ЛГР, а не стилем слоя
        with tempfile.TemporaryDirectory() as tmp:
            p = Project.create(Path(tmp) / "t.grado", "ЛГР")
            layer = p.add_layer("cad.zouit")
            layer.add_feature(
                {"type": "MultiPolygon", "coordinates": [[[
                    [413000, 6178000], [413100, 6178000], [413100, 6178080],
                    [413000, 6178080], [413000, 6178000]]]]},
                attrs={"kind": "водоохранная"}, style_id="lgr.vodookhr")
            ops = build_ops(p, (10, 10, 200, 160), scale=1000)
            p.close()
        hatches = [o for o in ops if o["op"] == "path" and o.get("width") == 0.16]
        self.assertEqual(len(hatches), 1)
        # цвет штриховки — синий #0669b2 из Эталона, не цвет слоя ЗОУИТ
        r, g, b = hatches[0]["stroke"]
        self.assertAlmostEqual(r, 0x06 / 255, places=3)
        self.assertAlmostEqual(b, 0xb2 / 255, places=3)

    def test_line_markers_in_library(self):
        from grado_render import merged_library
        lib = merged_library()["styles"]
        by_code = {s["lgr_code"]: s for sid, s in lib.items()
                   if sid.startswith("lgr.")}
        self.assertEqual(len([s for s in by_code.values()
                              if s.get("line_marker")]), 30,
                         "30 знаков Эталона несут маркеры-засечки")
        # выборка по образцам: водоохранная ∨3.5/20, пояс санохраны ⊥2/8,
        # памятник природы ●3/20, территории ОКН ■1.5/20
        self.assertEqual(by_code[16]["line_marker"],
                         {"shape": "chevron", "period_mm": 20.0, "size_mm": 3.5,
                          "period_px": 40.0, "size_px": 7.0})
        self.assertEqual(by_code[13]["line_marker"]["shape"], "tee")
        self.assertEqual(by_code[13]["line_marker"]["period_mm"], 8.0)
        self.assertEqual(by_code[55]["line_marker"]["shape"], "dot")
        self.assertEqual(by_code[9]["line_marker"]["shape"], "square")
        self.assertEqual(by_code[20]["double_mm"], 2.0, "защитная зона ОКН — двойная")
        self.assertEqual(by_code[18]["dash_mm"], None, "граница ПК — сплошная")
        # сверка с эталоном (приказ ММА №65, стр. 9-10, 13 + приложение 2):
        self.assertIsNone(by_code[41].get("line_marker"),
                          "береговая полоса — без маркеров (приложение 2)")
        self.assertEqual(by_code[47]["line_marker"]["shape"], "triangle",
                         "ООЗТ — залитые треугольники ▼")
        self.assertEqual(by_code[46]["line_marker"]["shape"], "triangle",
                         "Резерв ООПТ — треугольники (семейство ООПТ)")
        self.assertEqual(by_code[10]["line_marker"]["shape"], "tee",
                         "охранная зона ОКН — Т-засечки")

    def test_marker_ops_along_ring(self):
        from grado_render.scene import marker_ops, _inward_sign
        ring = [(0, 0), (100, 0), (100, 60), (0, 60)]
        spec = {"shape": "chevron", "period_mm": 20.0, "size_mm": 3.5}
        ops = marker_ops(ring, spec, (1, 0, 0), closed=True,
                         inward=_inward_sign(ring))
        self.assertTrue(ops, "по периметру 320 мм — маркеры есть")
        segs = [seg for o in ops if o["op"] == "path" for seg in o["rings"]]
        self.assertGreaterEqual(len(segs), 2 * 10, "~16 галочек по 2 отрезка")
        # засечки не выходят из кольца дальше size: все точки внутри bbox+eps
        for seg in segs:
            for x, y in seg:
                self.assertTrue(-4 <= x <= 104 and -4 <= y <= 64)
        # заливные формы: треугольники по периметру
        tri = marker_ops(ring, {"shape": "triangle", "period_mm": 20,
                                "size_mm": 2}, (1, 0, 0), closed=True,
                         inward=_inward_sign(ring))
        fills = [o for o in tri if o["op"] == "path" and o["fill"]]
        self.assertGreater(len(fills), 10)

    def test_marker_ops_inward(self):
        # нормаль засечек направлена внутрь кольца (как в Эталоне)
        from grado_render.scene import marker_ops, _inward_sign
        for ring in ([(0, 0), (100, 0), (100, 60), (0, 60)],   # CCW
                     [(0, 0), (0, 60), (100, 60), (100, 0)]):  # CW
            ops = marker_ops(ring, {"shape": "tick", "period_mm": 20,
                                    "size_mm": 3}, (0, 0, 0), closed=True,
                             inward=_inward_sign(ring))
            for o in ops:
                for (x1, y1), (x2, y2) in o["rings"]:
                    # конец засечки строго внутри прямоугольника
                    self.assertTrue(0 - 1e-6 <= x2 <= 100 + 1e-6)
                    self.assertTrue(0 - 1e-6 <= y2 <= 60 + 1e-6)

    def test_per_object_marker_ops_from_style_id(self):
        # объект со знаком Эталона получает засечки в PDF-сцене
        with tempfile.TemporaryDirectory() as tmp:
            p = Project.create(Path(tmp) / "t.grado", "ЛГР-маркеры")
            layer = p.add_layer("cad.zouit")
            layer.add_feature(
                {"type": "MultiPolygon", "coordinates": [[[
                    [413000, 6178000], [413200, 6178000], [413200, 6178150],
                    [413000, 6178150], [413000, 6178000]]]]},
                attrs={"kind": "водоохранная"}, style_id="lgr.vodookhr")
            ops = build_ops(p, (10, 10, 200, 160), scale=1000)
            p.close()
        # среди ops есть path-и с width 0.5 без dash (маркеры) помимо контура
        marker_paths = [o for o in ops if o["op"] == "path"
                        and o.get("dash") is None and o.get("width") == 0.5
                        and not o.get("closed")]
        self.assertTrue(marker_paths, "засечки chevron в сцене")

    def test_frontend_styles_passthrough(self):
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parents[3] / "apps" / "studio"))
        import studio_core
        fs = studio_core.frontend_styles()
        vod = fs["lgr.vodookhr"]
        self.assertEqual(vod["hatch"]["angle"], 45)
        self.assertEqual(vod["hatch"]["color"], "#0669b2")
        self.assertEqual(vod["line_label"], "водоохранная")
        self.assertEqual(vod["group"], "ЗОУИТ")
        self.assertEqual(vod["lgr_code"], 16)
        self.assertEqual(vod["line_marker"],
                         {"shape": "chevron", "period": 40.0, "size": 7.0})
        self.assertEqual(fs["lgr.okn.zashchit"]["double"], 4.0)
        # легаси-стили не сломаны: hatch остаётся true
        self.assertIs(fs["restrict.hatch"]["hatch"], True)


if __name__ == "__main__":
    unittest.main()
