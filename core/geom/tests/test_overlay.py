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


if __name__ == "__main__":
    unittest.main()
