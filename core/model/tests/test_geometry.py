"""Геометрия проекта (grado_model.geometry): площадь и длина, дыры, WKB и GPKG-blob, проверка типа.

Запуск: python -m unittest discover -s core/model/tests (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import unittest

from grado_model import geometry


SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]]}


class TestGeometry(unittest.TestCase):
    def test_area_square(self):
        self.assertAlmostEqual(geometry.area(SQUARE), 10000.0)

    def test_area_with_hole(self):
        geom = {"type": "Polygon", "coordinates": [
            SQUARE["coordinates"][0],
            [[10, 10], [20, 10], [20, 20], [10, 20], [10, 10]],
        ]}
        self.assertAlmostEqual(geometry.area(geom), 10000.0 - 100.0)

    def test_area_multipolygon(self):
        geom = {"type": "MultiPolygon", "coordinates": [
            SQUARE["coordinates"],
            [[[200, 0], [250, 0], [250, 50], [200, 50], [200, 0]]],
        ]}
        self.assertAlmostEqual(geometry.area(geom), 10000.0 + 2500.0)

    def test_length(self):
        geom = {"type": "LineString", "coordinates": [[0, 0], [3, 4], [3, 14]]}
        self.assertAlmostEqual(geometry.length(geom), 15.0)

    def test_wkb_roundtrip(self):
        for geom in [
            {"type": "Point", "coordinates": [413000.5, 6178000.25]},
            {"type": "LineString", "coordinates": [[0, 0], [1, 2], [3, 4]]},
            SQUARE,
            {"type": "MultiPolygon", "coordinates": [SQUARE["coordinates"]]},
            {"type": "MultiLineString", "coordinates": [[[0, 0], [1, 1]], [[2, 2], [3, 3]]]},
        ]:
            with self.subTest(geom["type"]):
                self.assertEqual(geometry.wkb_decode(geometry.wkb_encode(geom)), geom)

    def test_gpkg_blob_roundtrip(self):
        blob = geometry.gpkg_blob(SQUARE, 32637)
        geom, srs = geometry.gpkg_parse(blob)
        self.assertEqual(geom, SQUARE)
        self.assertEqual(srs, 32637)
        self.assertEqual(blob[:2], b"GP")

    def test_invalid(self):
        with self.assertRaises(geometry.GeometryError):
            geometry.validate({"type": "Circle", "coordinates": []})


if __name__ == "__main__":
    unittest.main()
