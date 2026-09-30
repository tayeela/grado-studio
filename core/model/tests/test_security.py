"""Защита от враждебных входов: SQL-идентификаторы, геометрия, файл проекта."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from grado_model import Project, ProjectError, geometry, gpkg


class TestIdentifiers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Project.create(Path(self.tmp.name) / "s.grado", "Тест")

    def tearDown(self):
        self.p.close()
        self.tmp.cleanup()

    def test_quote_ident_doubles_quotes(self):
        self.assertEqual(gpkg.quote_ident('a"b'), '"a""b"')
        for bad in ("", "a\x00b", None, 5, "x" * 300):
            with self.assertRaises(gpkg.GpkgError):
                gpkg.quote_ident(bad)

    def test_bad_layer_id_rejected(self):
        with self.assertRaises(ProjectError):
            self.p.add_layer("terr.boundary", layer_id="a\x00b")
        with self.assertRaises(ProjectError):
            self.p.add_layer("terr.boundary", layer_id=["x"])

    def test_bad_field_id_rejected(self):
        with self.assertRaises(ProjectError):
            self.p.add_layer("terr.boundary", fields=[{"id": "a\x00", "type": "string"}])

    def test_injection_in_field_id_is_inert(self):
        evil = 'x" TEXT); DROP TABLE grado_meta; --'
        layer = self.p.add_layer("terr.boundary", fields=[{"id": evil, "type": "string"}])
        layer.add_feature(
            {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            attrs={evil: "v"})
        self.assertEqual(next(layer.features())["attrs"][evil], "v")
        self.assertEqual(self.p.meta("srs_id"), str(self.p.srs_id))  # grado_meta цела

    def test_cyrillic_field_ok(self):
        layer = self.p.add_layer("terr.boundary", fields=[{"id": "Этаж, шт", "type": "integer"}])
        self.assertIn("Этаж, шт", [f["id"] for f in layer.user_fields])

    def test_non_scalar_attr_rejected(self):
        layer = self.p.add_layer("terr.boundary", fields=[{"id": "f", "type": "string"}])
        geom = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        for bad in ({"a": 1}, [1]):
            with self.assertRaises(ProjectError):
                layer.add_feature(geom, attrs={"f": bad})


class TestOpen(unittest.TestCase):
    def test_garbage_file_is_project_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "junk.grado"
            path.write_bytes(b"not a database" * 100)
            with self.assertRaises(ProjectError):
                Project.open(path)

    def test_size_limit(self):
        import grado_model.project as pr
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "p.grado"
            Project.create(path, "T").close()
            old, pr._MAX_PROJECT_BYTES = pr._MAX_PROJECT_BYTES, 10
            try:
                with self.assertRaises(ProjectError):
                    Project.open(path)
            finally:
                pr._MAX_PROJECT_BYTES = old
            Project.open(path).close()

    def test_trusted_schema_off(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "p.grado"
            Project.create(path, "T").close()
            p = Project.open(path)
            try:
                self.assertEqual(p.conn.execute("PRAGMA trusted_schema").fetchone()[0], 0)
            finally:
                p.close()


class TestGeometryValidation(unittest.TestCase):
    def test_non_finite_rejected(self):
        for v in (float("nan"), float("inf"), -float("inf")):
            with self.assertRaises(geometry.GeometryError):
                geometry.validate({"type": "Point", "coordinates": [v, 0]})

    def test_non_numbers_and_shapes_rejected(self):
        for geom in ({"type": "Point", "coordinates": ["1", 0]},
                     {"type": "Point", "coordinates": [1]},
                     {"type": "Point", "coordinates": True},
                     {"type": "LineString", "coordinates": [0, 1]},
                     {"type": ["Point"], "coordinates": [0, 0]}):
            with self.assertRaises(geometry.GeometryError, msg=geom):
                geometry.validate(geom)

    def test_deep_nesting_rejected(self):
        c = [0, 0]
        for _ in range(10000):
            c = [c]
        with self.assertRaises(geometry.GeometryError):
            geometry.validate({"type": "Polygon", "coordinates": c})

    def test_valid_passes(self):
        geometry.validate({"type": "MultiPolygon", "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]]})
        geometry.validate({"type": "LineString", "coordinates": []})


if __name__ == "__main__":
    unittest.main()
