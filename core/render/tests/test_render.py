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

    def test_three_ui_families_have_cyrillic(self):
        for family in ("ui", "serif", "mono"):
            font = Font(find_font(family))
            self.assertGreater(font.gid_for("Я"), 0, family)


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

    def test_inline_style_passes_label_font_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Project.create(Path(tmp) / "font.grado", "Шрифт")
            layer = p.add_layer("tp.func_zone")
            layer.add_feature(
                {"type": "Polygon", "coordinates": [[
                    [413000, 6178000], [413100, 6178000], [413100, 6178100],
                    [413000, 6178100], [413000, 6178000]]]},
                attrs={"zone_title": "Ж-1"}, style_id="canvas.font")
            styles = StyleSet(id_styles={"canvas.font": {
                "fill": "#eeeeee", "stroke": "#333333",
                "label_field": "zone_title", "label_font_family": "serif"}})
            ops = build_ops(p, (10, 10, 200, 160), scale=1000, styles=styles)
            p.close()
        label = next(o for o in ops if o["op"] == "text")
        self.assertEqual(label["font_family"], "serif")


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

    def test_embeds_and_selects_three_font_families(self):
        ops = [
            {"op": "text", "x": 20, "y": 30, "size": 5,
             "text": "Системный", "font_family": "ui"},
            {"op": "text", "x": 20, "y": 50, "size": 5,
             "text": "С засечками", "font_family": "serif"},
            {"op": "text", "x": 20, "y": 70, "size": 5,
             "text": "Моноширинный", "font_family": "mono"},
        ]
        pdf = PdfBackend().render([(160, 100, ops)])
        self.assertEqual(pdf.count(b"/FontFile2"), 3)
        streams = re.findall(rb"stream\n(.*?)\nendstream", pdf, re.S)
        page = b""
        for stream in streams:
            try:
                data = zlib.decompress(stream)
            except zlib.error:
                continue
            if b" Tj" in data:
                page = data
        self.assertIn(b"/F1 ", page)
        self.assertIn(b"/F2 ", page)
        self.assertIn(b"/F3 ", page)


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


class TestMoscowGenplanLibrary(unittest.TestCase):
    """Функциональные зоны Генплана (moscow_genplan.json), источник — QML Москвы."""

    def setUp(self):
        from grado_render import load_library, merged_library
        self.lib = load_library("moscow_genplan")
        self.merged = merged_library()["styles"]
        self.by_zone = {s["gp_zone"]: s for s in self.lib["styles"].values()
                        if s.get("gp_zone")}

    def test_base_palette_is_saturated(self):
        # выбор юзера: насыщенная палитра (Некрасовка = Щербинка), не пастель
        # Новой Москвы (#fcc2c2/#faedbb) и не оттенки Троицка (#f76767/#f3d357)
        self.assertEqual(self.by_zone["общественная зона"]["fill"], "#ff6666")
        self.assertEqual(self.by_zone["жилая зона"]["fill"], "#ffdd55")
        self.assertEqual(self.by_zone["природная зона"]["fill"], "#77cc99")
        self.assertEqual(self.by_zone["производственная зона"]["fill"], "#bbbbee")

    def test_fill_is_solid_opaque(self):
        # решение юзера: заливка сплошная и непрозрачная, как в QML
        for sid, s in self.lib["styles"].items():
            self.assertIsNone(s.get("fill_opacity"), f"{sid} — заливка без прозрачности")
            self.assertFalse(s["hatch"], f"{sid} — зона заливается, а не штрихуется")

    def test_moscow_keys_are_data_values_not_labels(self):
        # У «ФЗ ГП Москва» value (в данных) и label (подпись) РАСХОДЯТСЯ во всех
        # категориях. Ключ обязан быть по value, иначе знак не найдётся никогда.
        s = self.merged["gp.msk.administrativno_delovye"]
        self.assertEqual(s["gp_zone"],
                         "специализированные административно-деловые общественные зоны")
        self.assertEqual(s["title"], "Административно-деловые")

    def test_zone_codes_from_troitsk(self):
        # ФЗ ГП Троицк задаёт категории числовым кодом fztype, имя — в подписи
        self.assertEqual(self.lib["fz_code"]["100"], "общественная зона")
        self.assertEqual(self.lib["fz_code"]["400"], "природная зона")
        for zone in self.lib["fz_code"].values():
            self.assertIn(zone, self.by_zone, f"код указывает на зону без знака: {zone}")

    def test_merged_into_library_without_collision(self):
        # два классификатора (базовый и московский) живут в одной библиотеке
        self.assertIn("gp.zhilaya_zona", self.merged)
        self.assertIn("gp.msk.promyshlennye_zony", self.merged)
        self.assertIn("lgr.vodookhr", self.merged, "знаки ЛГР на месте")
        zones = [s["gp_zone"] for s in self.lib["styles"].values() if s.get("gp_zone")]
        self.assertEqual(len(zones), len(set(zones)), "имя зоны не должно дублироваться")


class TestMoscowLgrLibrary(unittest.TestCase):
    """Системная библиотека Эталона ЛГР (приказ ММА от 10.03.2025 № 65).

    Соответствие проверяется на ЧИСТОЙ библиотеке: если какой-то тест в этом
    же процессе импортировал studio_core, тот применяет личные правки знаков
    пользователя (style_overrides.json) глобально — и тесты эталона начинали
    зависеть от пользовательских данных на машине."""

    def setUp(self):
        from grado_render import style
        self._saved_overrides = style.style_overrides()
        style.set_style_overrides({})

    def tearDown(self):
        from grado_render import style
        style.set_style_overrides(self._saved_overrides)

    def test_merged_library_valid(self):
        from grado_render import merged_library
        lib = merged_library()
        lgr = {sid: s for sid, s in lib["styles"].items()
               if sid.startswith("lgr.")}
        self.assertEqual(len(lgr), 55, "55 знаков (54 Эталона + код 33 из "
                                       "рабочих QML Москвы: 5 КЛ + 28 ЗОУИТ + "
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

    def test_line_label_repeats_upright(self):
        # подпись линии/контура повторяется вдоль дуги, по касательной, не
        # вверх ногами (иначе на длинном ЗОУИТ/красной линии знак не читался)
        from grado_render.scene import line_label_ops
        import math
        ops = line_label_ops([[0, 0], [200, 0]], "прибрежная",
                             (0.8, 0.1, 0.1), 2.2, closed=False)
        self.assertGreaterEqual(len(ops), 2, "повторяется, не одна подпись")
        for o in ops:
            self.assertEqual(o["op"], "text")
            self.assertEqual(o["text"], "прибрежная")
            self.assertLessEqual(abs(o["angle"]), math.pi / 2 + 1e-6)
        # мелкий знак — подпись пропускается (не влезет)
        self.assertEqual(line_label_ops([[0, 0], [3, 0]], "x", (0, 0, 0),
                                        2.2, closed=False), [])

    def test_build_ops_emits_line_label(self):
        # знак ЛГР с line_label в проекте → повёрнутые text-опы в сцене (PDF/SVG)
        with tempfile.TemporaryDirectory() as tmp:
            p = Project.create(Path(tmp) / "t.grado", "ЛГР")
            layer = p.add_layer("cad.zouit")
            layer.add_feature(
                {"type": "MultiPolygon", "coordinates": [[[
                    [413000, 6178000], [413400, 6178000], [413400, 6178300],
                    [413000, 6178300], [413000, 6178000]]]]},
                attrs={"kind": "прибрежная"}, style_id="lgr.pribrezh")
            ops = build_ops(p, (10, 10, 280, 200), scale=1000)
            p.close()
        labels = [o for o in ops if o["op"] == "text" and o.get("angle")]
        self.assertTrue(labels, "line_label знака ЛГР даёт повёрнутые подписи")
        self.assertTrue(all(o["text"] == "прибрежная" for o in labels))

    def test_line_markers_in_library(self):
        from grado_render import merged_library
        lib = merged_library()["styles"]
        by_code = {s["lgr_code"]: s for sid, s in lib.items()
                   if sid.startswith("lgr.")}
        self.assertEqual(len([s for s in by_code.values()
                              if s.get("line_marker")]), 30,
                         "30 знаков несут маркеры (по QML; 49 ЛЗП без маркера)")
        # Величины — в мм ЛИСТА, пересчёт из QML MapUnit (метры местности) на
        # опорный масштаб Эталона М 1:2000: мм = метры / 2.
        # Водоохранная: QML arrowhead interval 20 м / size 3.5 м → ∨1.75/10 мм.
        # px = мм × 96/25.4 (единый множитель, см. MM_PX в генераторе).
        # dir=out: в QML у 16 и 17 один и тот же arrowhead@270 — знаки-близнецы
        # смотрят в одну сторону (прежде 16 стоял «внутрь» и расходился с 17).
        # ow — толщина штриха галки (QML outline_width 1.25 м → 0.62 мм)
        self.assertEqual(by_code[16]["line_marker"],
                         {"shape": "chevron", "period_mm": 10.0, "size_mm": 1.75,
                          "period_px": 37.8, "size_px": 6.61, "dir": "in",
                          "ow_mm": 0.62, "ow_px": 2.34})
        # контурные треугольники (в QML fill alpha=0) — 11/18/50 helper filled=False
        self.assertEqual(by_code[18]["line_marker"].get("filled"), False, "ПК — контурный")
        self.assertEqual(by_code[50]["line_marker"].get("filled"), False, "приаэродром. — контурный")
        self.assertNotIn("filled", by_code[8]["line_marker"], "ООПТ — залитый (не помечен)")
        # 8 ООПТ / 18 ПК / 55 памятник природы — в QML ДВА под-маркера (углы 0 и
        # 180), т.е. глифы по обе стороны линии
        for c in (8, 18, 55):
            self.assertEqual(by_code[c]["line_marker"]["dir"], "both",
                             f"код {c} — засечки по обе стороны (QML: два под-маркера)")
        self.assertEqual(by_code[13]["line_marker"]["shape"], "tee")
        self.assertEqual(by_code[13]["line_marker"]["period_mm"], 4.0,
                         "пояс санохраны: QML interval 8 м → 4 мм на 1:2000")
        self.assertEqual(by_code[55]["line_marker"]["shape"], "dot")
        self.assertEqual(by_code[9]["line_marker"]["shape"], "tick", "QML line=tick, не square")
        self.assertEqual(by_code[20]["line_marker"]["shape"], "tick",
                         "защитная зона ОКН — штрих по QML (одиночная линия, не двойная)")
        self.assertIsNone(by_code[20].get("double_mm"), "в QML код 20 не двойной")
        self.assertEqual(by_code[18]["dash_mm"], None, "граница ПК — сплошная")
        # сверка с эталоном (приказ ММА №65, стр. 9-10, 13 + приложение 2):
        self.assertIsNone(by_code[41].get("line_marker"),
                          "береговая полоса — без маркеров (приложение 2)")
        self.assertEqual(by_code[47]["line_marker"]["shape"], "triangle2",
                         "ООЗТ — два треугольника, наложенных со сдвигом вверх (как ООПТ)")
        self.assertEqual(by_code[47]["line_marker"]["size_mm"], 1.0,
                         "ООЗТ — размер маркера как у ООПТ")
        self.assertEqual(by_code[47]["line_marker"]["dir"], "in")
        # глиф: второй треугольник сдвинут по нормали, не вдоль линии
        from grado_render.scene import marker_ops as _mops
        _ops = _mops([[0, 0], [40, 0]],
                     {"shape": "triangle2", "period_mm": 40, "size_mm": 4, "dir": "in"},
                     stroke="#f00", width=0.3, closed=False, inward=1.0)
        _tris = [o for o in _ops if o.get("op") == "path"]
        self.assertGreaterEqual(len(_tris), 2, "triangle2 даёт ≥2 треугольника")
        _y0 = sum(y for _, y in _tris[0]["rings"][0]) / 3
        _y1 = sum(y for _, y in _tris[1]["rings"][0]) / 3
        self.assertGreater(_y1, _y0 + 0.5, "второй треугольник сдвинут вверх (по нормали)")
        _x0 = sum(x for x, _ in _tris[0]["rings"][0]) / 3
        _x1 = sum(x for x, _ in _tris[1]["rings"][0]) / 3
        self.assertAlmostEqual(_x0, _x1, delta=0.3, msg="сдвиг не вдоль линии")
        self.assertEqual(by_code[46]["line_marker"]["shape"], "triangle",
                         "Резерв ООПТ — треугольники (семейство ООПТ)")
        self.assertEqual(by_code[10]["line_marker"]["shape"], "tick",
                         "охранная зона ОКН — штрих (QML line, не tee)")
        # стиль линии по выноскам размеров осн. таблицы (нет выноски штриха
        # «6.0» → линия сплошная; знаки-зоны с маркерами рисуются по сплошной)
        for c in (8, 9, 10, 37, 38, 47, 50, 55):
            self.assertIsNone(by_code[c]["dash_mm"],
                              f"код {c} — сплошная линия (эталон, осн. таблица)")
        self.assertEqual(by_code[17]["line_marker"]["shape"], "chevron",
                         "прибрежная — шеврон; точки суть штрих-пунктир линии")
        self.assertEqual(by_code[41]["dash_mm"], [3.0, 1.0],
                         "береговая — простой штрих QML 6;2 МЕТРА → 3.0/1.0 мм "
                         "на 1:2000 (не штрих-пунктир)")
        self.assertEqual(len(by_code[61]["dash_mm"]), 6,
                         "зона 3 пояса — штрих-пунктир с двумя точками")
        for c in (22, 64, 65, 66):
            self.assertEqual(by_code[c]["line_marker"]["shape"], "tick",
                             f"код {c} затоп/подтоп — перпенд. штрих (QML line)")
        # направление засечки per-sign — сверено с углом под-маркера в QML.
        # остриём НАРУЖУ — ландшафт ОКН
        for c in (11,):
            self.assertEqual(by_code[c]["line_marker"]["dir"], "out",
                             f"код {c} — засечка остриём наружу зоны (QML)")
        # остриём ВНУТРЬ зоны — апекс на границе, ничего снаружи полигона:
        # ООЗТ/геодез/резерв ООПТ/приаэродром./возд.подходы, а также
        # водоохранная(16)/прибрежная(17) — иначе на нижнем ребре плечи галки
        # свисали ПОД линию (жалоба юзера «нижняя точка ниже пунктира»).
        for c in (47, 38, 46, 50, 51, 16, 17):
            self.assertEqual(by_code[c]["line_marker"]["dir"], "in",
                             f"код {c} — засечка остриём внутрь зоны (эталон)")

    def test_line_styles_match_moscow_qml(self):
        # линии ЛГР приведены к рабочим QML Москвы (spritlines): цвет, ширина
        # 1.0 мм у всех, точные штрихи; перекрывает значения по скану приказа №65
        from grado_render import merged_library
        by_code = {s["lgr_code"]: s for sid, s in
                   merged_library()["styles"].items() if sid.startswith("lgr.")}
        # ГЕЙТ: в QML у ВСЕХ 50 знаков ЛГР line_width=1 при line_width_unit=Pixel
        # (единица УСТРОЙСТВА — не мм и не метры). Прежняя заметка «1.0 мм у всех,
        # unit=MM» была неверна, и линии выходили втрое толще эталона. Сверяем в
        # px: в мм это 0.2646 через ту же связку 96 dpi, что и MM_PX.
        for c, st in by_code.items():
            self.assertEqual(st["width_px"], 1.0,
                             f"код {c} — линия 1 px (QML line_width=1 Pixel)")
        # цвет по семейству QML
        self.assertEqual(by_code[1]["stroke"], "#ff0000", "красные линии — чистый красный")
        self.assertEqual(by_code[2]["stroke"], "#fe0004", "ТОП — «точечный» красный")
        self.assertEqual(by_code[47]["stroke"], "#ff0000", "ООЗТ — красный по эталону (правка юзера)")
        self.assertEqual(by_code[41]["stroke"], "#0018b8", "береговая — синий")
        # штрих точно по QML
        self.assertIsNone(by_code[19]["dash_mm"], "охр. зона ООПТ — сплошная (QML)")
        # ГЕЙТ КЛАССА ОШИБОК: в QML customdash_unit=MapUnit у 49 из 53 знаков —
        # это МЕТРЫ НА МЕСТНОСТИ. Прежде числа QML переносились как мм листа,
        # отчего все штрихи выходили вдвое грубее эталона, а галка садилась на
        # каждый штрих вместо каждого второго. Держим мм = метры_QML / 2
        # (опорный 1:2000). Проверяем обратным пересчётом в метры — так тест
        # прямо сверяется с QML, а не с нашим промежуточным числом.
        def qml_m(code):
            return [round(x * 2, 3) for x in by_code[code]["dash_mm"]]
        self.assertEqual(qml_m(16), [6.0, 4.0], "водоохранная — QML 6;4 МЕТРА")
        self.assertEqual(qml_m(20), [8.0, 2.0], "защитная ОКН — QML 8;2 МЕТРА")
        self.assertEqual(qml_m(49), [0.75, 2.0], "лесопарк — QML 0.75;2 МЕТРА")
        self.assertEqual(by_code[16]["dash_mm"], [3.0, 2.0], "16 — мм на 1:2000")
        # шаг галки 20 м при цикле штриха 10 м ⇒ засечка через штрих (k=2)
        cycle_mm = sum(by_code[16]["dash_mm"])
        self.assertEqual(cycle_mm, 5.0, "цикл штриха 16 = 5 мм = 10 м (QML)")
        self.assertEqual(by_code[16]["line_marker"]["period_mm"], 10.0,
                         "шаг галки 16 = 10 мм = 20 м (QML interval=20 MapUnit)")
        self.assertEqual(round(by_code[16]["line_marker"]["period_mm"] / cycle_mm), 2,
                         "галка через штрих: 20 м / 10 м = 2 (QML)")
        self.assertIn(33, by_code, "код 33 (охранные зоны инфраструктуры) добавлен")
        # штриховка зон по рабочим QML (spritzones): цвет/угол/шаг, код 21 — заливка.
        # Цвет — из ВЛОЖЕННОГО SimpleLine (им QGIS рисует штрихи), а не из
        # легаси-атрибута `color` самого LinePatternFill: у кодов 6 и 19 они
        # различаются, и раньше здесь были закреплены нерисуемые внешние цвета
        # (#27b702 / #e24b29). Проверенные значения совпадают с приказом №65.
        self.assertEqual(by_code[6]["hatch"]["color"], "#eb880e", "ж/д — оранжевая (QML: подсимвол)")
        self.assertEqual(by_code[19]["hatch"]["color"], "#f8f400", "охр. ООПТ — жёлтая (QML: подсимвол)")
        self.assertEqual(by_code[16]["hatch"]["spacing_mm"], 2, "шаг штриховки по QML")
        self.assertEqual(by_code[57]["hatch"]["angle"], 135, "ОКС на ООПТ — угол 135 (QML)")
        self.assertEqual(by_code[21]["fill"], "#18f61f", "режимы ПК — сплошная заливка (QML)")
        self.assertFalse(by_code[21]["hatch"], "режимы ПК — без штриховки")

    def test_dimension_line_is_red(self):
        # выноски/размеры по рабочим QML Москвы (textlines) — красные
        from grado_render import merged_library
        dim = merged_library()["styles"]["dimension.line"]
        self.assertEqual(dim["stroke"], "#ff0000", "размер/выноска — красная (QML)")

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
        # среди ops есть path-и без dash (маркеры-засечки) помимо контура; штрих
        # засечки ЧУТЬ ТОНЬШЕ линии (MARKER_WIDTH_RATIO=0.65 от 1.0 мм = 0.65),
        # правка юзера «галки должны быть чуть тоньше»
        marker_paths = [o for o in ops if o["op"] == "path"
                        and o.get("dash") is None and not o.get("closed")
                        and 0 < o.get("width", 0) < 1.0]
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
        # px холста = мм листа × 96/25.4 (мм пересчитаны из QML MapUnit на 1:2000)
        self.assertEqual(vod["line_marker"],
                         {"shape": "chevron", "period": 37.8, "size": 6.61,
                          "dir": "in", "ow": 2.34})
        # код 20 (защитная ОКН) — по QML одиночная линия со штрихами (не двойная)
        self.assertEqual(fs["lgr.okn.zashchit"]["line_marker"]["shape"], "tick")
        self.assertNotIn("double", fs["lgr.okn.zashchit"])
        # легаси-стили не сломаны: hatch остаётся true
        self.assertIs(fs["restrict.hatch"]["hatch"], True)


if __name__ == "__main__":
    unittest.main()


class TestPrintHolesAndGroundUnits(unittest.TestCase):
    """Печать: дыры полигонов и привязка знаков ЛГР к местности.

    До правки: (1) выколотый полигон печатался сплошным — бэкенды заливали по
    nonzero, а намотка колец в данных портала не гарантирована; (2) штрих и шаг
    засечек брались как мм листа, т.е. рисунок был эталонным только при 1:2000.
    """

    def test_holes_reach_ops_and_print_evenodd(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Project.create(Path(tmp) / "h.grado", "Дыра")
            layer = p.add_layer("tp.func_zone")
            layer.add_feature({"type": "Polygon", "coordinates": [
                [[413000, 6178000], [413400, 6178000], [413400, 6178300],
                 [413000, 6178300], [413000, 6178000]],
                [[413100, 6178100], [413300, 6178100], [413300, 6178200],
                 [413100, 6178200], [413100, 6178100]],
            ]}, attrs={"zone_title": "с дырой"})
            ops = build_ops(p, (10, 10, 257, 180), scale=2000)
            p.close()
        paths = [o for o in ops if o["op"] == "path" and len(o["rings"]) > 1]
        self.assertTrue(paths, "внутреннее кольцо обязано дойти до печати")
        pdf = PdfBackend()
        body = pdf._path_ops(paths[0], 200)
        self.assertIn("B*", body.split(),
                      "путь с дырой закрашивается по even-odd (иначе дыра "
                      "исчезнет при 'неправильной' намотке кольца)")

    def test_plain_polygon_still_nonzero(self):
        op = {"op": "path", "rings": [[(0, 0), (10, 0), (10, 10), (0, 10)]],
              "closed": True, "fill": (0.2, 0.4, 0.8), "stroke": (0, 0, 0),
              "width": 0.5, "dash": None}
        body = PdfBackend()._path_ops(op, 100)
        self.assertIn("B", body.split())
        self.assertNotIn("B*", body.split(), "без дыр — прежнее поведение")

    def test_lgr_dash_and_marker_follow_print_scale(self):
        # штрих 6;4 м и шаг галки 20 м (QML MapUnit) обязаны держаться на ЛЮБОМ
        # масштабе листа, а не только на опорном 1:2000
        st = StyleSet().resolve_id("lgr.vodookhr")
        self.assertTrue(st.ground_units)
        for scale in (2000, 4000, 500):
            s2 = st.for_scale(scale)
            cycle_m = sum(s2.dash) * scale / 1000.0
            period_m = s2.line_marker["period_mm"] * scale / 1000.0
            self.assertAlmostEqual(cycle_m, 10.0, places=2,
                                   msg=f"цикл штриха 10 м на 1:{scale} (QML 6;4)")
            self.assertAlmostEqual(period_m, 20.0, places=2,
                                   msg=f"шаг галки 20 м на 1:{scale} (QML interval)")
            self.assertEqual(round(period_m / cycle_m), 2, "галка через штрих")

    def test_non_lgr_style_untouched_by_scale(self):
        st = StyleSet().resolve_id("red.line.projected")
        if st is not None:
            self.assertIs(st.for_scale(4000), st, "не-ЛГР стиль не пересчитывается")

    def test_marker_outline_width_follows_scale(self):
        # outline_width_unit=MapUnit у 15 знаков — толщина штриха засечки тоже в
        # МЕТРАХ. Не масштабировалась: глиф ужимался, штрих оставался прежним, и
        # на 1:4451 засечка (3 px) со штрихом 2.34 px вырождалась в кляксу.
        st = StyleSet().resolve_id("lgr.vodookhr")
        base = st.line_marker
        ratio = base["ow_mm"] / base["size_mm"]
        for scale in (500, 2000, 4451, 10000):
            lm = st.for_scale(scale).line_marker
            self.assertAlmostEqual(lm["ow_mm"] / lm["size_mm"], ratio, places=9,
                                   msg=f"ow/size постоянно на 1:{scale}")
            # QML: size 3.5 м, ow 1.25 м (1.24 — округление MARKER_OW 0.625→0.62)
            self.assertAlmostEqual(lm["size_mm"] * scale / 1000, 3.5, delta=0.02)
            self.assertAlmostEqual(lm["ow_mm"] * scale / 1000, 1.25, delta=0.02)
