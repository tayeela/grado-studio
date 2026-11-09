"""Слои знака в печати (symparts.py): полоса внутрь — внутри контура и нужной ширины, значки вдоль линии — с шагом и
на нужной стороне (внутрь полигона при side > 0, наружу при side < 0, справа по ходу у линии), штриховка и линия по контуру;
print_io рисует части поверх объекта карты листа."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402,F401  пути к core (grado_render)
import symparts  # noqa: E402

SQ = [[(0, 0), (40, 0), (40, 40), (0, 40)]]        # квадрат 40 мм, ось y вниз


def inside(x, y):
    return 0 < x < 40 and 0 < y < 40


class SymParts(unittest.TestCase):
    def test_band_is_inside_and_as_wide_as_asked(self):
        from shapely.geometry import Polygon
        ops = symparts.parts_ops("poly", [SQ], [{"k": "band", "c": "#ff0000", "a": .5, "b": 10}])
        self.assertEqual(len(ops), 1)
        band = Polygon(ops[0]["rings"][0], ops[0]["rings"][1:])
        b = 10 * symparts.PX_MM
        self.assertAlmostEqual(band.area, 40 * 40 - (40 - 2 * b) ** 2, delta=0.5)
        self.assertTrue(Polygon(SQ[0]).buffer(1e-6).contains(band))
        self.assertGreater(min(ops[0]["fill"]), 0.4)                 # 50 % красного поверх белого — светлее чистого

    def test_marks_face_inside_or_outside_whatever_the_ring_direction(self):
        for ring in (SQ[0], list(reversed(SQ[0]))):
            for side, want in ((1, True), (-1, False)):
                ops = symparts.parts_ops("poly", [[ring]], [{"k": "marks", "shape": "tick", "step": 40, "size": 10, "side": side}])
                self.assertGreater(len(ops), 4)
                for o in ops:
                    (x0, y0), (x1, y1) = o["rings"][0]
                    self.assertEqual(inside(x1, y1), want, (ring[:2], side, o["rings"][0]))

    def test_marks_step_along_a_line_and_right_side(self):
        step = 20 * symparts.PX_MM
        ops = symparts.parts_ops("line", [[(0, 0), (100, 0)]], [{"k": "marks", "shape": "tick", "step": 20, "size": 5, "side": 1}])
        xs = [o["rings"][0][0][0] for o in ops]
        self.assertAlmostEqual(xs[0], step / 2, places=6)
        self.assertAlmostEqual(xs[1] - xs[0], step, places=6)
        self.assertTrue(all(o["rings"][0][1][1] > 0 for o in ops))   # y вниз: справа по ходу на восток — ниже линии

    def test_hatch_and_outline(self):
        ops = symparts.parts_ops("poly", [SQ], [{"k": "hatch", "c": "#000000", "hp": "x0", "hs": 8, "w": 1}, {"k": "line", "c": "#0000ff", "w": 2, "dash": [6, 4]}])
        self.assertGreaterEqual(len(ops), 3)                         # штриховка сеткой (2 направления) + линия
        last = ops[-1]
        self.assertEqual(last["stroke"], (0.0, 0.0, 1.0))
        self.assertEqual(last["dash"], [6 * symparts.PX_MM, 4 * symparts.PX_MM])

    def test_polygon_parts_skip_lines(self):
        self.assertEqual(symparts.parts_ops("line", [[(0, 0), (10, 0)]], [{"k": "band", "b": 5}, {"k": "hatch"}]), [])

    def test_print_map_draws_parts_on_top(self):
        import print_io
        import server as S
        lon, lat, d = 37.803, 55.827, .0005
        sq = {"type": "Polygon", "coordinates": [[[lon - d, lat - d / 2], [lon + d, lat - d / 2], [lon + d, lat + d / 2], [lon - d, lat + d / 2], [lon - d, lat - d / 2]]]}
        feat = {"g": sq, "fill": "#cccccc", "stroke": "#000000", "w": 1, "a": 1,
                "parts": [{"k": "marks", "c": "#e34948", "shape": "tri", "step": 16, "size": 5, "side": 1}]}
        spec = {"block": {"w": 100, "h": 80, "scale": 2000, "center": [lon, lat]}, "layers": [{"title": "Зона", "features": [feat]}]}
        import layout_io
        _, ops = layout_io._map_ops(spec, S.REDLN, S.LGR_DASH, None)
        red = [o for o in ops if o.get("op") == "path" and o.get("fill") == print_io.hex_to_rgb("#e34948")]
        self.assertGreater(len(red), 4)


if __name__ == "__main__":
    unittest.main()
