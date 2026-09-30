"""Sheets of ГРАДО 2: a sheet from styled objects renders to PDF and SVG through the core renderer."""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402
import print_io  # noqa: E402


def sheet(**kw):
    lon, lat = 37.525, 55.7925
    sq = lambda d, e: {"type": "Polygon", "coordinates": [[[lon - d, lat - e], [lon + d, lat - e], [lon + d, lat + e], [lon - d, lat + e], [lon - d, lat - e]]]}
    base = {"title": "Существующее положение", "size": "A3", "scale": 2000, "center": [lon, lat],
            "layers": [{"title": "Здания", "features": [{"g": sq(.0005, .0003), "fill": "#cbc6be", "stroke": "#4d4d4d", "w": 1, "a": 1, "label": "12"}]},
                       {"title": "ЗОУИТ", "features": [{"g": sq(.001, .0006), "fill": "#7a4ab0", "stroke": "#7a4ab0", "w": 1, "hatch": True}]},
                       {"title": "Красные линии", "features": [{"g": {"type": "LineString", "coordinates": [[lon - .002, lat], [lon + .002, lat + .0004]]},
                                                                "lt": [next(iter(S.REDLN["linetypes"]))], "lc": "#d7191c", "w": 1.3}]}],
            "legend": [{"title": "Здания", "kind": "poly", "items": [{"label": "здания", "fill": "#cbc6be", "stroke": "#4d4d4d"}]}],
            "tep": [["Территория", "45,9 га"], ["Плотность", "25,0 тыс. м²/га"]],
            "territory": sq(.002, .0012)}
    base.update(kw)
    return base


class Print(unittest.TestCase):
    def test_plain_paper_sheet_fills_the_page_in_both_orientations(self):
        for orient, size in (("L", (420, 297)), ("P", (297, 420))):
            doc = print_io.build_document({"sheets": [sheet(size="BA3", orient=orient, title="Лист 1")]}, S.REDLN, S.LGR_DASH)
            page = doc.pages[0]
            self.assertEqual(tuple(page.size), size)
            x, y, w, h = page.frames[0].rect                     # карта: поля по 2 %, пропорции бумаги
            self.assertAlmostEqual(w / h, size[0] / size[1], places=6)
        self.assertTrue(print_io.render_pdf({"sheets": [sheet(size="BA3", orient="P")]}, S.REDLN, S.LGR_DASH).startswith(b"%PDF"))

    def test_pdf_album_of_two_sheets(self):
        pdf = print_io.render_pdf({"meta": {"object": "Хорошёво"}, "sheets": [sheet(), sheet(size="A1", title="Эскиз")]}, S.REDLN, S.LGR_DASH)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page "), 2)

    def test_svg_preview_has_frame_and_title(self):
        svg = print_io.render_preview_svg({"meta": {"object": "Хорошёво", "stage": "Предпроект"}, "sheets": [sheet()]}, S.REDLN, S.LGR_DASH)
        self.assertIn("<svg", svg)
        self.assertIn("Существующее положение", svg)
        self.assertIn("Условные обозначения", svg)

    def test_tep_sheet_lists_all_rows_in_columns(self):
        rows = [[f"Показатель {i}", f"{i},0"] for i in range(60)]
        svg = print_io.render_preview_svg({"meta": {}, "sheets": [{"title": "ТЭП", "size": "A3", "kind": "tep", "tep": rows}]}, S.REDLN, S.LGR_DASH)
        self.assertIn("Показатель 0", svg)
        self.assertIn("Показатель 59", svg)                 # 60 строк на А3 — во второй колонке, ничего не потеряно
        self.assertNotIn("не поместилось", svg)

    def test_map_scale_puts_100m_at_50mm_on_1_2000(self):
        tr = print_io.MapTransform((0, 0, 200, 200), [37.525, 55.7925], 2000)
        x0, _ = tr.mm(37.525, 55.7925)
        lon1 = S.crs.msk_to_wgs84(*[a + b for a, b in zip(S.crs.wgs84_to_msk(37.525, 55.7925), (100, 0))])[0]
        x1, _ = tr.mm(lon1, 55.7925)
        self.assertAlmostEqual(x1 - x0, 50, places=1)

    def test_linetype_draws_shapes_and_dashes(self):
        name = next(n for n, lt in S.REDLN["linetypes"].items() if any("shape" in e for e in lt["pattern"]))
        ops = print_io.linetype_ops([(0, 0), (200, 0)], name, 0.5, (1, 0, 0), .3, S.REDLN)
        self.assertGreater(len(ops[0]["rings"]), 10)


class Clip(unittest.TestCase):
    def test_ring_is_clipped_to_the_frame(self):
        ring = [(-100, -100), (300, -100), (300, 300), (-100, 300)]
        c = print_io.clip_ring(ring, (0, 0, 100, 50), pad=0)
        xs, ys = zip(*c)
        self.assertEqual((min(xs), max(xs), min(ys), max(ys)), (0, 100, 0, 50))

    def test_ring_outside_disappears(self):
        self.assertEqual(print_io.clip_ring([(500, 500), (600, 500), (600, 600)], (0, 0, 100, 100)), [])


class PresentationSlides(unittest.TestCase):
    def test_title_and_map_slide_with_table_and_satellite(self):
        import base64
        jpeg = base64.b64decode(SlidePanelsAndPhotos.JPEG)
        seen = []
        tiles = lambda z, x, y: (seen.append((z, x, y)), jpeg)[1]
        spec = {"meta": {"object": "Проект планировки квартала", "short": "ППТ Квартал", "place": "СВАО, район Алексеевский", "date": "Сентябрь 2026"},
                "sheets": [{"kind": "title", "size": "P", "title": "Титул"},
                           {"size": "P", "title": "Ортофотоплан", "scale": 2000, "center": [37.65, 55.80], "basemap": "sat", "layers": [], "legend": [], "tep": [],
                            "territory": None, "table": {"title": "Участки", "cols": [["№", .1, "left"], ["Номер", .9, "left"]], "rows": [["1", "77:02:0023014:42"]]}}]}
        doc = print_io.build_document(spec, {}, {}, tiles)
        self.assertEqual([p.size for p in doc.pages], [(338.67, 190.5)] * 2)
        pages = print_io.document_pages_ops(doc, None)
        self.assertTrue(seen and all(z >= 15 for z, _, _ in seen))                   # 1:2000 — крупные тайлы
        self.assertTrue(any(o["op"] == "image" and "quad" in o for o in pages[1][2]))
        texts = [o.get("text") for o in pages[1][2] if o["op"] == "text"]
        self.assertIn("Ортофотоплан", texts)
        self.assertIn("(СВАО, район Алексеевский)", texts)
        self.assertIn("2", texts)                                                       # номер слайда
        self.assertIn("77:02:0023014:42", texts)
        self.assertTrue(print_io.render_pdf(spec, {}, {}, tiles).startswith(b"%PDF"))



class SlidePanelsAndPhotos(unittest.TestCase):
    JPEG = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABALDA4MChAODQ4SERATGCgaGBYWGDEjJR0oOjM9PDkzODdASFxOQERXRTc4UG1RV19iZ2hnPk1xeXBkeFxlZ2P/2wBDARESEhgVGC8aGi9jQjhCY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2P/wAARCAAGAAgDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAH/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAwX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCAARn/2Q=="      # JPEG 8 × 6 из canvas браузера (профиль ICC вырезан)

    def test_two_maps_on_one_slide_with_captions(self):
        panel = lambda cap: {"scale": 5000, "center": [37.65, 55.80], "layers": [{"title": "Зоны", "features": [
            {"g": {"type": "Polygon", "coordinates": [[[37.649, 55.799], [37.651, 55.799], [37.651, 55.801], [37.649, 55.799]]]},
             "fill": "#ffffff", "stroke": "#333333", "w": 1, "a": 0, "label": "3.5.1, 4.4\n12.0.2"}]}], "territory": None, "caption": cap}
        spec = {"meta": {}, "sheets": [{"size": "P", "title": "ПЗЗ", "panels": [panel("Зоны и ВРИ"), panel("Подзоны")], "legend": [], "note": ""}]}
        ops = print_io.document_pages_ops(print_io.build_document(spec, {}, {}), None)[0][2]
        texts = [o.get("text") for o in ops if o["op"] == "text"]
        self.assertIn("Зоны и ВРИ", texts)
        self.assertIn("Подзоны", texts)
        self.assertEqual(texts.count("12.0.2"), 2)                              # подпись в две строки — в каждой карте
        clips = [o["rect"] for o in ops if o["op"] == "clip"]
        self.assertEqual(len(clips), 2)
        self.assertLess(clips[0][0] + clips[0][2], clips[1][0])                  # карты рядом, не наезжают

    def test_photo_slide_places_pictures_and_numbers(self):
        ph = {"data": self.JPEG, "w": 8, "h": 6}
        spec = {"meta": {}, "sheets": [{"size": "P", "kind": "photos", "title": "Материалы фотофиксации", "scale": 2000, "center": [37.65, 55.80],
                                         "layers": [], "legend": [], "territory": None, "photos": [ph, ph, ph]}]}
        ops = print_io.document_pages_ops(print_io.build_document(spec, {}, {}), None)[0][2]
        imgs = [o for o in ops if o["op"] == "image" and o.get("w", 0) < 200]          # без картинки шапки
        self.assertEqual(len(imgs), 3)
        self.assertTrue(all(abs(o["w"] / o["h"] - 8 / 6) < 1e-6 and o["x"] > 130 for o in imgs))   # пропорции снимка, справа от карты
        self.assertTrue({"1", "2", "3"} <= {o.get("text") for o in ops if o["op"] == "text"})
        self.assertTrue(print_io.render_pdf(spec, {}, {}).startswith(b"%PDF"))


class SlideLabels(unittest.TestCase):
    def _ops(self, **kw):
        sh = {"size": "P", "title": "Т", "scale": 5000, "center": [37.65, 55.80], "legend": [], "territory": None, **kw}
        return print_io.document_pages_ops(print_io.build_document({"meta": {}, "sheets": [sh]}, {}, {}), None)[0][2]

    def test_street_label_runs_along_the_line_once(self):
        road = lambda y: {"g": {"type": "LineString", "coordinates": [[37.640, y], [37.660, y + .004]]}, "stroke": "#f5d58a", "w": 1, "label": "Кулаков переулок"}
        ops = self._ops(layers=[{"title": "Улицы", "features": [road(55.799), road(55.797)]}])
        lab = [o for o in ops if o["op"] == "text" and o.get("text") == "Кулаков переулок"]
        self.assertEqual(len(lab), 1)                                   # одно название — одна подпись
        self.assertLess(abs(lab[0]["angle"]), math.pi / 2)              # не вверх ногами
        self.assertNotAlmostEqual(lab[0]["angle"], 0, places=2)         # повёрнута по линии

    def test_callout_box_and_leader(self):
        terr = {"type": "Polygon", "coordinates": [[[37.649, 55.799], [37.651, 55.799], [37.651, 55.801], [37.649, 55.799]]]}
        ops = self._ops(layers=[], territory=terr, callout=["проектируемая территория", "район Алексеевский"])
        texts = [o.get("text") for o in ops if o["op"] == "text"]
        self.assertIn("проектируемая территория", texts)
        self.assertIn("район Алексеевский", texts)

    def test_long_legend_line_wraps(self):
        long = "Граница зоны регулирования застройки и хозяйственной деятельности объекта культурного наследия"
        ops = self._ops(layers=[], legend=[{"title": "ОКН", "kind": "poly", "items": [{"label": long, "fill": "#cc0000"}, {"label": "б", "fill": "#00cc00"}]}])
        texts = [o.get("text") for o in ops if o["op"] == "text"]
        self.assertTrue(any(t and t.endswith("наследия") for t in texts))   # конец строки не потерян


    def test_slide_has_no_north_arrow_or_scale_bar(self):
        texts = [o.get("text") for o in self._ops(layers=[]) if o["op"] == "text"]
        self.assertNotIn("С", texts)
        self.assertFalse(any(t and "М 1:" in t for t in texts))
        a3 = print_io.document_pages_ops(print_io.build_document({"meta": {}, "sheets": [sheet()]}, S.REDLN, S.LGR_DASH), None)[0][2]
        self.assertIn("С", [o.get("text") for o in a3 if o["op"] == "text"])     # на листе А3 по ГОСТ — остаются


    def test_a_format_slides_keep_the_slide_design(self):
        for size, wh in (("PA4", (297, 210)), ("PA3", (420, 297)), ("PA2", (594, 420))):
            sh = {"size": size, "title": "Ортофотоплан", "scale": 2000, "center": [37.65, 55.80], "layers": [], "legend": [], "territory": None}
            doc = print_io.build_document({"meta": {"place": "СВАО"}, "sheets": [sh]}, {}, {})
            self.assertEqual(doc.pages[0].size, wh)
            ops = print_io.document_pages_ops(doc, None)[0][2]
            title = next(o for o in ops if o.get("text") == "Ортофотоплан")
            self.assertAlmostEqual(title["size"], 3.8 * wh[0] / 338.67, places=3)   # оформление растёт с листом
            m, c = print_io.layout(size)
            self.assertLess(m[0] + m[2], c[0])                                      # карта не заходит под легенду
            self.assertLessEqual(c[0] + c[2], wh[0])


if __name__ == "__main__":
    unittest.main()


class Pptx(unittest.TestCase):
    """Альбом в редактируемый PPTX: те же листы, рамки листа — группами, подписи — текстом."""

    def test_album_to_pptx(self):
        import io
        import zipfile
        spec = {"meta": {"object": "Проект планировки квартала", "short": "ППТ Квартал", "place": "СВАО, район Алексеевский"},
                "sheets": [{"kind": "title", "size": "PA3", "style": "pptkrt", "title": "Титул"},
                           {"size": "PA3", "style": "pptkrt", "title": "Месторасположение", "legend": [], "rect": [24, 44, 263, 233],
                            "scale": 2000, "center": [37.65, 55.80], "layers": [
                                {"title": "Участки", "features": [{"g": {"type": "Polygon", "coordinates": [[[37.649, 55.799], [37.651, 55.799], [37.651, 55.801], [37.649, 55.799]]]},
                                                                   "fill": None, "stroke": "#0000ff", "w": 1, "a": 0}]}]}]}
        data = print_io.render_pptx(spec, {}, {})
        z = zipfile.ZipFile(io.BytesIO(data))
        s2 = z.read("ppt/slides/slide2.xml").decode("utf-8")
        self.assertIn("Месторасположение", s2)
        self.assertIn('name="Карта"', s2)
        self.assertIn('name="Участки"', s2)
        self.assertIn('<a:round/>', s2)                                  # изломы контуров карты скруглены


class PptKrtSheets(unittest.TestCase):
    """Листы альбома ППТ КРТ по составу «ГК Царицыно»: карта слева (рамка шаблона), справа легенда и списки документов,
    в углу карты — округ и район; длинный заголовок — 18 пт в две строки, а не мельче (владелец 01.10.2026)."""

    def test_map_sheet_with_legend_lists_and_note(self):
        title = "Схема существующего использования территорий с границами зон с особыми условиями использования территорий"
        spec = {"meta": {"short": "№ 3141", "place": "ТАО, район Вороново"},
                "sheets": [{"size": "PA3", "style": "pptkrt", "title": title, "rect": [24, 44, 263, 233], "scale": 10000, "center": [37.2, 55.4],
                            "layers": [], "legend": [{"title": "Границы", "kind": "line", "items": [{"label": "Граница территории рассмотрения", "fill": "#e0158c"}]}],
                            "lists": [{"title": "Проекты планировки территории", "items": ["1. Об утверждении проекта планировки №1218-ПП от 03.08.2021 г."]}],
                            "mapNote": ["Троицкий административный округ", "район Вороново"]}]}
        doc = print_io.build_document(spec, {}, {})
        ops = print_io.document_pages_ops(doc, None)[0][2]
        texts = [o["text"] for o in ops if o["op"] == "text"]
        for t in ("Условные обозначения", "Проекты планировки территории", "Троицкий административный", "район Вороново"):
            self.assertIn(t, texts)
        self.assertTrue(any(t.startswith("1. Об утверждении") for t in texts))
        red = [o for o in ops if o["op"] == "text" and o["x"] == 51]   # название листа: x = 51 мм
        self.assertEqual(len(red), 2)                                  # 100 знаков на 18 пт — две строки
        self.assertEqual(" ".join(o["text"] for o in red), title)
        self.assertTrue(all(abs(o["size"] - 18 * 0.3528) < 1e-9 for o in red))   # кегль не уменьшается
        self.assertLess(red[1]["y"] + 1.6, 44)                         # вторая строка кончается выше карты
        self.assertGreater(red[0]["y"] - 18 * 0.3528 * .7, 27.9)       # первая — ниже шапки
        self.assertFalse(print_io.not_ready(spec))

    def test_photo_sheet_has_map_and_photo_grid(self):
        spec = {"sheets": [{"size": "PA3", "style": "pptkrt", "kind": "photos", "title": "Материалы фотофиксации", "rect": [24, 44, 170, 233],
                            "scale": 2000, "center": [37.2, 55.4], "layers": [], "legend": [], "photos": []}]}
        doc = print_io.build_document(spec, {}, {})
        names = [type(f).__name__ for f in doc.pages[0].frames]
        self.assertIn("SketchMapFrame", names)
        self.assertIn("PhotoGridFrame", names)


class ConceptSheets(unittest.TestCase):
    """Листы 3–9 альбома ППТ КРТ — шапка шаблона, остальное как в «ГК Царицыно»: колонка легенды с подчёркнутыми
    группами, списки документов в рамках цвета документа, карточки участков, таблица зон, сетка снимков 2 + 2 + 4."""

    def _ops(self, sheet):
        base = {"size": "PA3", "style": "pptkrt", "look": "concept", "scale": 7500, "center": [37.2, 55.4], "layers": [], "legend": []}
        doc = print_io.build_document({"meta": {"short": "№ 3141"}, "sheets": [{**base, **sheet}]}, {}, {})
        return doc, print_io.document_pages_ops(doc, None)[0][2]

    def test_column_legend_lists_cards_and_table(self):
        doc, ops = self._ops({"title": "Схема", "mapNote": ["Троицкий административный округ", "район Вороново"],
                              "cLegend": [{"title": "Границы", "items": [{"kind": "line", "stroke": "#ff00ff", "width": 1.1, "dash": [1.1, 1.1], "label": "территории рассмотрения (54,61 га)"}]}],
                              "cLists": [{"title": "Проекты планировки территории", "items": [{"text": "1. Об утверждении №1218-ПП от 03.08.2021 г.", "color": "#f5a623"}]}],
                              "gpTable": {"title": "Функциональные зоны и их параметры", "cols": ["Номер", "Индекс", "Тип", "Фонд"], "rows": [["28", "240", "природно-жилая зона", "118–160"]]},
                              "cCards": {"title": "Сведения о земельных участках", "items": [[["Кадастровый номер", "50:27:0000000:126"], ["Площадь (га)", "47,2008"]]]}})
        texts = [o["text"] for o in ops if o["op"] == "text"]
        for t in ("Условные обозначения", "Границы", "Проекты планировки территории", "Функциональные зоны и их параметры", "50:27:0000000:126", "район Вороново"):
            self.assertIn(t, texts)
        boxes = [o for o in ops if o["op"] == "path" and o.get("stroke") and abs(o["stroke"][0] - 0xF5 / 255) < .01 and o.get("closed")]
        self.assertTrue(boxes)                                            # рамка пункта списка — цветом документа
        self.assertTrue(all(o.get("font_family", "") == "sans-bold" for o in ops if o["op"] == "text" and o["text"] == "Условные обозначения"))
        self.assertIn("ConceptColumnFrame", [type(f).__name__ for f in doc.pages[0].frames])

    def test_overflow_marks_sheet_not_ready_instead_of_silent_cut(self):
        items = [{"kind": "fill", "fill": "#cccccc", "label": f"пункт легенды {i}"} for i in range(60)]
        spec = {"sheets": [{"size": "PA3", "style": "pptkrt", "look": "concept", "scale": 7500, "center": [37.2, 55.4], "layers": [], "legend": [],
                            "title": "Схема", "cLegend": [{"title": "Много пунктов", "items": items}],
                            "cLists": [{"title": "ГПЗУ", "items": [{"text": "1. ГПЗУ № RU77230000-039043 от 24.07.2018 г.", "color": "#231f20"}]}]}]}
        ops = print_io.document_pages_ops(print_io.build_document(spec, {}, {}), None)[0][2]
        texts = [o["text"] for o in ops if o["op"] == "text"]
        self.assertEqual(print_io.not_ready(spec), [1])
        note = [t for t in texts if t.startswith("Лист не готов")]
        self.assertEqual(len(note), 1)
        self.assertIn("пункты легенды", note[0])
        self.assertTrue(all(o["size"] == 10 * 0.3528 for o in ops if o["op"] == "text" and o["text"].startswith("пункт легенды")))   # не мельче

    def test_last_line_not_a_lonely_short_word_and_table_hyphen_break(self):
        import album_io as A
        lines = A._wrap_mm("земельных участков, поставленных на кадастровый учёт", "sans", 10 * A.PT, 120 - 15.5)
        self.assertGreaterEqual(len(lines[-1].split()), 2)             # не «учёт» одно на строке
        self.assertEqual(A._wrap_mm("природно-жилая зона", "sans", 10 * A.PT, 25, orphan=False, hyph=True), ["природно-", "жилая зона"])
        self.assertEqual(A._hyph_parts("1218-ПП"), ["1218-ПП"])        # коды с цифрами не делятся
        cols = ["Номер функц.\xa0зоны", "Индекс функц.\xa0зоны", "Тип функц.\xa0зоны", "Прогнозируемый фонд застройки функц.\xa0зоны, тыс.\xa0кв.\xa0м"]
        w = A._col_widths([120 * c for c in (.17, .17, .3, .36)], cols, [["28", "240", "природно-жилая зона", "118–160"]], 10 * A.PT)
        self.assertAlmostEqual(sum(w), 120, places=6)
        self.assertGreaterEqual(w[0], A._tw("функц. зоны", "sans-bold", 10 * A.PT) + 2 - 1e-6)   # «функц. зоны» не разрывается

    def test_title_longer_than_two_lines_is_not_shrunk_but_marked(self):
        import album_io as A
        lines, fits = A._title_lines("Очень длинное название листа " * 12)
        self.assertFalse(fits)
        self.assertEqual(len(lines), 2)
        self.assertIsNone(A._col_widths([10, 10], ["Прогнозируемый", "Прогнозируемый"], [], 10 * A.PT))   # слово шире таблицы

    def test_photo_grid_like_the_sample(self):
        import base64
        jpeg = base64.b64decode(SlidePanelsAndPhotos.JPEG)
        photos = [{"data": base64.b64encode(jpeg).decode(), "w": 8, "h": 6} for _ in range(8)]
        _, ops = self._ops({"kind": "photos", "title": "Материалы фотофиксации", "rect": [7, 44, 198, 152], "photos": photos})
        imgs = [o for o in ops if o["op"] == "image" and o.get("w", 0) < 200]          # без картинки шапки
        self.assertEqual(len(imgs), 8)
        clips = [o["rect"] for o in ops if o["op"] == "clip" and o.get("rect") and o["rect"][2] == 94]
        self.assertEqual([c[:2] for c in clips], [(215, 44), (319, 44), (215, 125), (319, 125), (7, 206), (111, 206), (215, 206), (319, 206)])

    def test_ortho_bleeds_with_legend_box(self):
        doc, ops = self._ops({"title": "Ортофотоплан", "bleed": True, "rect": [0, 44, 420, 253],
                              "cLegend": [{"items": [{"kind": "line", "stroke": "#e30613", "label": "района"}]}]})
        self.assertIn("OrthoLegendFrame", [type(f).__name__ for f in doc.pages[0].frames])
        self.assertIn("Границы:", [o["text"] for o in ops if o["op"] == "text"])

    def test_view_mark_and_label_plate(self):
        _, ops = self._ops({"title": "Карта", "layers": [{"title": "Точки", "features": [
            {"g": {"type": "Point", "coordinates": [37.2, 55.4]}, "mk": "view", "dir": 90, "fill": "#1f3fbf", "label": "1"},
            {"g": {"type": "Point", "coordinates": [37.205, 55.401]}, "nodot": True, "label": "Кадастровый номер\n77:22:1", "lbox": True, "ls": 3.2}]}]})
        arrows = [o for o in ops if o["op"] == "path" and o.get("fill") and abs(o["fill"][2] - 0xBF / 255) < .01]
        self.assertEqual(len(arrows), 1)
        self.assertFalse(any(o["op"] == "circle" for o in ops))           # плашка без точки-значка
        self.assertIn("77:22:1", [o["text"] for o in ops if o["op"] == "text"])

    def test_corner_note_dark_red_on_separate_lines(self):
        _, ops = self._ops({"title": "Карта", "mapNote": [["Троицкий", "административный округ"], ["район Вороново"]]})
        note = [o for o in ops if o["op"] == "text" and o["text"] in ("Троицкий", "административный округ", "район Вороново")]
        self.assertEqual([o["text"] for o in note], ["Троицкий", "административный округ", "район Вороново"])
        self.assertTrue(all(o["color"][0] > .5 and o["color"][1] < .2 and o.get("font_family") == "sans-bold" for o in note))


class LabelsInFrame(unittest.TestCase):
    """Подпись территории — целиком в рамке; занятое место ищется внутри своего контура; подложка легенды снимка —
    полупрозрачная (ExtGState в PDF)."""

    def test_area_label_is_pulled_inside_the_frame(self):
        sq = lambda x0, y0, d: {"type": "Polygon", "coordinates": [[[x0, y0], [x0 + d, y0], [x0 + d, y0 + d], [x0, y0 + d], [x0, y0]]]}
        sheet = {"size": "PA3", "style": "pptkrt", "look": "concept", "title": "Карта", "scale": 10000, "center": [37.2, 55.4], "rect": [0, 44, 420, 253],
                 "noFrame": True, "legend": [], "layers": [{"title": "СНТ", "features": [
                     {"g": sq(37.1650, 55.398, .004), "fill": None, "stroke": "#ffffff", "w": 0, "a": 0, "label": "СНТ «Очень длинное название»", "ls": 4.3, "lf": "sans-bold"}]}]}
        ops = print_io.document_pages_ops(print_io.build_document({"sheets": [sheet]}, {}, {}), None)[0][2]
        t = next(o for o in ops if o["op"] == "text" and o["text"].startswith("СНТ"))
        self.assertGreaterEqual(t["x"] - print_io._text_w(t["text"], "sans-bold", 4.3) / 2, 0)

    def test_translucent_legend_plate(self):
        from grado_render import PdfBackend
        pdf = PdfBackend().render([(100, 60, [{"op": "path", "rings": [[(0, 0), (50, 0), (50, 20), (0, 20)]], "closed": True,
                                                "fill": (1, 1, 1), "alpha": .72, "stroke": None, "width": 0, "dash": None}])])
        self.assertIn(b"/ExtGState << /GA1 << /ca 0.72 >>", pdf)

    def test_street_label_runs_stop_at_junctions_and_bends(self):
        pts = [(0, 0), (10, 0), (20, 0.2), (30, 0), (30, 20)]           # прямо 30 мм, затем поворот
        runs = print_io._straight_runs(pts, [False] * 5)
        self.assertAlmostEqual(max(r[0] for r in runs), 30, places=1)
        runs = print_io._straight_runs(pts, [False, False, True, False, False])   # перекрёсток на 20 мм
        self.assertAlmostEqual(max(r[0] for r in runs), 20, delta=.1)
