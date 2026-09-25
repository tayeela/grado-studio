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
        imgs = [o for o in ops if o["op"] == "image"]
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


if __name__ == "__main__":
    unittest.main()
