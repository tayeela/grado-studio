import sqlite3
import tempfile
import unittest
from pathlib import Path

from grado_model import Project, ProjectError, ClassifierError

BOUNDARY = {"type": "Polygon", "coordinates": [[
    [413000, 6178000], [413500, 6178000], [413500, 6178300], [413000, 6178300],
    [413000, 6178000]]]}


class TestProject(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.grado"
        self.p = Project.create(self.path, "Тест")

    def tearDown(self):
        self.p.close()
        self.tmp.cleanup()

    def test_create_refuses_overwrite(self):
        with self.assertRaises(ProjectError):
            Project.create(self.path, "Второй")

    def test_gpkg_pragmas(self):
        (app_id,) = self.p.conn.execute("PRAGMA application_id").fetchone()
        self.assertEqual(app_id, 0x47504B47, "application_id должен быть 'GPKG'")
        for table in ("gpkg_spatial_ref_sys", "gpkg_contents", "gpkg_geometry_columns"):
            self.assertTrue(self.p.conn.execute(
                f"SELECT 1 FROM sqlite_master WHERE name='{table}'").fetchone(), table)

    def test_layer_and_feature_roundtrip(self):
        layer = self.p.add_layer("terr.boundary")
        fid = layer.add_feature(BOUNDARY, attrs={"name": "Граница"})
        self.assertEqual(fid, 1)
        feats = list(layer.features())
        self.assertEqual(len(feats), 1)
        self.assertEqual(feats[0]["geom"], BOUNDARY)
        self.assertEqual(feats[0]["attrs"]["name"], "Граница")
        self.assertEqual(feats[0]["source"], "manual")
        self.assertTrue(feats[0]["source_date"])
        self.assertAlmostEqual(layer.area_ha(), 15.0)

    def test_provenance_recorded(self):
        layer = self.p.add_layer("cad.zouit")
        layer.add_feature(
            {"type": "Polygon", "coordinates": BOUNDARY["coordinates"]},
            attrs={"kind": "СЗЗ"}, source="nspd",
            source_date="2026-07-01", source_doc="77:00-6.123")
        f = next(layer.features())
        self.assertEqual((f["source"], f["source_date"], f["source_doc"]),
                         ("nspd", "2026-07-01", "77:00-6.123"))
        # Polygon автоматически обёрнут в MultiPolygon по классификатору
        self.assertEqual(f["geom"]["type"], "MultiPolygon")

    def test_unknown_source_rejected(self):
        layer = self.p.add_layer("terr.boundary")
        with self.assertRaises(ProjectError):
            layer.add_feature(BOUNDARY, source="откуда-то")

    def test_geom_type_mismatch(self):
        layer = self.p.add_layer("pp.red_line")
        with self.assertRaises(ProjectError):
            layer.add_feature(BOUNDARY)

    def test_attrs_validated(self):
        layer = self.p.add_layer("oks.building")
        with self.assertRaises(ClassifierError):
            layer.add_feature(BOUNDARY, attrs={"floors": "двенадцать"})
        with self.assertRaises(ClassifierError):
            layer.add_feature(BOUNDARY, attrs={"nope": 1})

    def test_duplicate_layer(self):
        self.p.add_layer("terr.boundary")
        with self.assertRaises(ProjectError):
            self.p.add_layer("terr.boundary")

    def test_reopen(self):
        layer = self.p.add_layer("terr.boundary")
        layer.add_feature(BOUNDARY, attrs={"name": "Граница"})
        self.p.close()
        p2 = Project.open(self.path)
        self.assertEqual(p2.meta("name"), "Тест")
        self.assertEqual([l["code"] for l in p2.layers()], ["terr.boundary"])
        self.assertAlmostEqual(p2.layer("terr.boundary").area_ha(), 15.0)
        p2.close()
        self.p = Project.open(self.path)

    def test_open_non_project(self):
        other = Path(self.tmp.name) / "other.sqlite"
        sqlite3.connect(other).execute("CREATE TABLE t (x)")
        with self.assertRaises(ProjectError):
            Project.open(other)

    def test_contents_registered(self):
        self.p.add_layer("terr.boundary")
        row = self.p.conn.execute(
            "SELECT data_type, srs_id FROM gpkg_contents WHERE table_name='l_terr_boundary'"
        ).fetchone()
        self.assertEqual(row, ("features", 32637))
        row = self.p.conn.execute(
            "SELECT geometry_type_name FROM gpkg_geometry_columns "
            "WHERE table_name='l_terr_boundary'").fetchone()
        self.assertEqual(row[0], "POLYGON")


if __name__ == "__main__":
    unittest.main()
