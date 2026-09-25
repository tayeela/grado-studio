"""Sheets of ГРАДО 2: a sheet from styled objects renders to PDF and SVG through the core renderer."""

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


if __name__ == "__main__":
    unittest.main()


class PresentationSlides(unittest.TestCase):
    def test_title_and_map_slide_with_table_and_satellite(self):
        try:
            import io
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow нужен, чтобы сделать тестовый тайл JPEG")
        buf = io.BytesIO(); Image.new("RGB", (8, 8), (40, 90, 40)).save(buf, "JPEG"); jpeg = buf.getvalue()
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

