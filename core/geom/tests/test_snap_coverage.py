import unittest

from grado_geom import Coverage, CoverageError, Snapper


class TestSnapper(unittest.TestCase):
    def setUp(self):
        self.s = Snapper(tolerance=0.5)
        self.s.add_segment((0, 0), (10, 10))
        self.s.add_segment((0, 10), (10, 0))

    def test_endpoint_beats_nearest(self):
        r = self.s.snap(0.1, 0.05)
        self.assertEqual(r.kind, "endpoint")
        self.assertEqual(r.point, (0, 0))

    def test_intersection(self):
        r = self.s.snap(5.2, 5.1)
        self.assertEqual(r.kind, "intersection")
        self.assertAlmostEqual(r.point[0], 5.0)
        self.assertAlmostEqual(r.point[1], 5.0)

    def test_priority_over_distance(self):
        # ближайшая точка на отрезке в нуле от курсора, но пересечение в допуске
        r = self.s.snap(5.3, 5.3)
        self.assertEqual(r.kind, "intersection",
                         "характеристическая точка бьёт «ближайшую»")

    def test_nothing_beyond_tolerance(self):
        self.assertIsNone(self.s.snap(50, 50))

    def test_midpoint(self):
        s = Snapper(tolerance=0.5)
        s.add_segment((0, 0), (10, 0))
        r = s.snap(5.1, 0.2)
        self.assertEqual(r.kind, "midpoint")
        self.assertEqual(r.point, (5.0, 0.0))


def sq(x0, y0, w, h):
    return [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]


class TestCoverage(unittest.TestCase):
    def test_shared_edge_detected(self):
        cov = Coverage.from_polygons({"A": sq(0, 0, 10, 10), "B": sq(10, 0, 10, 10)})
        self.assertEqual(len(cov.shared_edges()), 1)
        self.assertAlmostEqual(cov.area("A"), 100)
        self.assertAlmostEqual(cov.area("B"), 100)
        cov.validate()

    def test_edit_shared_edge_moves_both(self):
        cov = Coverage.from_polygons({"A": sq(0, 0, 10, 10), "B": sq(10, 0, 10, 10)})
        (eid,) = cov.shared_edges()
        e = cov.edges[eid]
        p0, p1 = e["pts"][0], e["pts"][-1]
        my = (p0[1] + p1[1]) / 2
        cov.edit_edge(eid, [p0, (13, my), p1])  # выгиб в сторону B

        areas = cov.areas()
        self.assertAlmostEqual(areas["A"] + areas["B"], 200,
                               msg="баланс территории сохраняется")
        self.assertAlmostEqual(max(areas.values()), 115)
        self.assertAlmostEqual(min(areas.values()), 85)
        cov.validate()

    def test_edit_edge_nodes_fixed(self):
        cov = Coverage.from_polygons({"A": sq(0, 0, 10, 10), "B": sq(10, 0, 10, 10)})
        (eid,) = cov.shared_edges()
        with self.assertRaises(CoverageError):
            cov.edit_edge(eid, [(10, 1), (10, 9)])

    def test_three_faces(self):
        # у C промежуточная вершина (10,10): общие границы совпадают повершинно
        cov = Coverage.from_polygons({
            "A": sq(0, 0, 10, 10), "B": sq(10, 0, 10, 10),
            "C": [(0, 10), (10, 10), (20, 10), (20, 16), (0, 16)]})
        self.assertEqual(len(cov.shared_edges()), 3)
        self.assertAlmostEqual(sum(cov.areas().values()), 320)
        cov.validate()

    def test_overlap_rejected(self):
        with self.assertRaises(CoverageError):
            Coverage.from_polygons({"A": sq(0, 0, 10, 10), "B": sq(0, 0, 10, 10)})

    def test_triple_use_rejected(self):
        with self.assertRaises(CoverageError):
            Coverage.from_polygons({
                "A": sq(0, 0, 10, 10), "B": sq(10, 0, 10, 10),
                "C": sq(0, 0, 10, 10)})

    def test_disconnected_fails_validation(self):
        cov = Coverage.from_polygons({"A": sq(0, 0, 10, 10), "B": sq(30, 0, 10, 10)})
        with self.assertRaises(CoverageError):
            cov.validate()


if __name__ == "__main__":
    unittest.main()
