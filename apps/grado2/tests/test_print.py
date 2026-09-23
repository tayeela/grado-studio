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

    def test_map_scale_puts_100m_at_50mm_on_1_2000(self):
        tr = print_io.MapTransform((0, 0, 200, 200), [37.525, 55.7925], 2000)
        x0, _ = tr.mm(37.525, 55.7925)
        lon1 = S.crs.msk50_to_wgs84(*[a + b for a, b in zip(S.crs.wgs84_to_msk50(37.525, 55.7925), (100, 0))])[0]
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
