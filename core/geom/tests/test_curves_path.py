"""Проверяет дуги и пути grado_geom: пикетаж, сопряжения, офсеты, аффинные преобразования.

Запуск: python -m unittest discover -s core/geom/tests (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import math
import unittest

from grado_geom import Arc, CurveError, Path, PathError, curve_spec, tessellate_curve, rotate, scale, mirror


class TestArc(unittest.TestCase):
    def test_from_3pts_semicircle(self):
        arc = Arc.from_3pts((0, 0), (1, 1), (2, 0))
        self.assertAlmostEqual(arc.cx, 1.0)
        self.assertAlmostEqual(arc.cy, 0.0)
        self.assertAlmostEqual(arc.r, 1.0)
        self.assertAlmostEqual(arc.length(), math.pi)
        x, y = arc.point_at(0.5)
        self.assertAlmostEqual(x, 1.0)
        self.assertAlmostEqual(y, 1.0)
        self.assertAlmostEqual(math.dist(arc.start, (0, 0)), 0)
        self.assertAlmostEqual(math.dist(arc.end, (2, 0)), 0)

    def test_collinear_rejected(self):
        with self.assertRaises(CurveError):
            Arc.from_3pts((0, 0), (1, 0), (2, 0))

    def test_linearize_sagitta(self):
        arc = Arc(0, 0, 100, 0, math.pi / 2)
        tol = 0.01
        pts = arc.linearize(tol)
        for a, b in zip(pts, pts[1:]):
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            sagitta = 100 - math.hypot(mx, my)
            self.assertLessEqual(sagitta, tol * 1.001)

    def test_offset_left(self):
        ccw = Arc(0, 0, 10, 0, math.pi / 2)
        self.assertAlmostEqual(ccw.offset(2).r, 8.0, msg="центр слева — радиус меньше")
        cw = Arc(0, 0, 10, math.pi / 2, -math.pi / 2)
        self.assertAlmostEqual(cw.offset(2).r, 12.0, msg="центр справа — радиус больше")
        with self.assertRaises(CurveError):
            ccw.offset(10.5)

    def test_tangent(self):
        arc = Arc(0, 0, 5, 0, math.pi / 2)
        self.assertAlmostEqual(arc.tangent_at(0.0), math.pi / 2)


class TestPath(unittest.TestCase):
    def test_station_on_polyline(self):
        p = Path.polyline([(0, 0), (10, 0), (10, 10)])
        self.assertAlmostEqual(p.length(), 20.0)
        (x, y), tangent = p.point_at_station(15)
        self.assertAlmostEqual((x, y), (10, 5))
        self.assertAlmostEqual(tangent, math.pi / 2)

    def test_fillet_length(self):
        p = Path.fillet_polyline([(0, 0), (10, 0), (10, 10)], radius=2)
        self.assertAlmostEqual(p.length(), 16 + math.pi, places=9)
        self.assertTrue(p.is_g1(), "сопряжение тангенциально")

    def test_fillet_radius_too_big(self):
        with self.assertRaises(PathError):
            Path.fillet_polyline([(0, 0), (3, 0), (3, 3)], radius=5)

    def test_stations(self):
        p = Path.fillet_polyline([(0, 0), (10, 0), (10, 10)], radius=2)
        sts = p.stations(5)
        self.assertEqual(len(sts), 5)
        self.assertAlmostEqual(sts[-1][0], 16 + math.pi, places=9)
        self.assertAlmostEqual(math.dist(sts[-1][1], (10, 10)), 0, places=9)

    def test_offset_g1_chain(self):
        p = Path.fillet_polyline([(0, 0), (10, 0), (10, 10)], radius=2)
        off = p.offset(1)  # левый офсет; поворот налево — офсет внутри
        self.assertAlmostEqual(off.length(), 16 + math.pi / 2, places=9)
        self.assertTrue(off.is_g1(), "офсет G1-цепи остаётся G1")

    def test_offset_miter_rectangle(self):
        rect = Path.polyline([(0, 0), (10, 0), (10, 6), (0, 6)], closed=True)
        inner = rect.offset(1)   # ccw-обход: слева — внутренность
        self.assertAlmostEqual(inner.area(), 8 * 4, places=6)
        outer = rect.offset(-1)
        self.assertAlmostEqual(outer.area(), 12 * 8, places=6)

    def test_curve_spec_round_and_tessellation(self):
        arc = curve_spec({"type": "arc", "cx": 0, "cy": 0, "r": 10,
                          "a0": 0, "sweep": math.pi / 2})
        pts = tessellate_curve(arc, 0.05)
        self.assertGreater(len(pts), 2)
        self.assertAlmostEqual(pts[0][0], 10)
        circle = tessellate_curve({"type": "circle", "cx": 0, "cy": 0, "r": 5}, 0.05)
        self.assertEqual(circle[0], circle[-1])

    def test_affine_rotate_scale_mirror(self):
        turned = rotate([(1, 0)], (0, 0), 90)
        self.assertAlmostEqual(turned[0][0], 0, places=6)
        self.assertAlmostEqual(turned[0][1], 1, places=6)
        self.assertEqual(scale([(2, 0)], (0, 0), 3), [(6, 0)])
        self.assertEqual(mirror([(1, 2)], (0, 0), (1, 0)), [(1, -2)])

    def test_offset_mixed_non_g1_rejected(self):
        arc = Arc(0, 0, 5, 0, math.pi / 2)
        p = Path([("seg", (0, 0), (5, 0)), ("arc", arc)])
        self.assertFalse(p.is_g1())
        with self.assertRaises(PathError):
            p.offset(1)


if __name__ == "__main__":
    unittest.main()
