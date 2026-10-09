"""Проверяет площадь полигонов внутри других (grado_geom.overlay): дубли, дыры, общие границы.

Запуск: python -m unittest discover -s core/geom/tests (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import unittest

from grado_geom.overlay import union_intersection_area


def square(x, y, s):
    return [[(x, y), (x + s, y), (x + s, y + s), (x, y + s)]]


class UnionIntersectionAreaTests(unittest.TestCase):
    def test_partial_overlap_with_clip(self):
        area = union_intersection_area([square(50, 50, 100)], [square(0, 0, 100)])
        self.assertAlmostEqual(2500, area, delta=0.5)

    def test_duplicates_and_nested_are_not_double_counted(self):
        regions = [square(0, 0, 100), square(0, 0, 100), square(20, 20, 30)]
        self.assertAlmostEqual(10000, union_intersection_area(regions, [square(0, 0, 100)]), delta=0.5)

    def test_adjacent_regions_share_edge(self):
        regions = [square(0, 0, 50), [[(50, 0), (100, 0), (100, 50), (50, 50)]]]
        self.assertAlmostEqual(5000, union_intersection_area(regions, [square(0, 0, 100)]), delta=0.5)

    def test_hole_and_orientation(self):
        ring = [(0, 0), (0, 100), (100, 100), (100, 0)]          # по часовой
        hole = [(40, 40), (60, 40), (60, 60), (40, 60)]
        area = union_intersection_area([[ring, hole]], [square(-10, -10, 200)])
        self.assertAlmostEqual(9600, area, delta=0.5)

    def test_triangle_exact_and_disjoint(self):
        tri = [[(0, 0), (100, 0), (0, 100)]]
        self.assertAlmostEqual(5000, union_intersection_area([tri], [square(0, 0, 100)]), delta=0.5)
        self.assertEqual(0.0, union_intersection_area([square(500, 500, 10)], [square(0, 0, 100)]))

    def test_small_coordinates_are_exact(self):
        # граница в градусах (как у district_shares), треугольник 0,01° на стыке двух районов: точно 3/4 на западе;
        # прежний шаг 0,05 давал одну строку сканирования и 100 % западу
        terr = [[(37.70, 55.80), (37.71, 55.80), (37.70, 55.81)]]
        west = [[(37.60, 55.70), (37.705, 55.70), (37.705, 55.90), (37.60, 55.90)]]
        east = [[(37.705, 55.70), (37.80, 55.70), (37.80, 55.90), (37.705, 55.90)]]
        a, b = union_intersection_area([terr], [west]), union_intersection_area([terr], [east])
        self.assertAlmostEqual(0.75, a / (a + b), places=9)

    def test_degenerate_rings_give_zero(self):
        for ring in ([(1, 1), (1, 1), (1, 1)], [(0, 0), (1, 1), (2, 2)], [(0, 0), (float("nan"), 1), (2, 2)]):
            self.assertEqual(0.0, union_intersection_area([[ring]], [square(0, 0, 10)]))

    def test_self_intersecting_ring_is_repaired(self):
        bow = [[(0, 0), (100, 100), (100, 0), (0, 100)]]          # «бабочка»: два треугольника по 2500
        self.assertAlmostEqual(5000, union_intersection_area([bow], [square(0, 0, 100)]), delta=0.5)


if __name__ == "__main__":
    unittest.main()
