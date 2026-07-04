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


class TestSchemaV2(unittest.TestCase):
    """MODEL-01: layer_id != semantic_class, метаданные слоя, style_id."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "v2.grado"
        self.p = Project.create(self.path, "V2")

    def tearDown(self):
        self.p.close()
        self.tmp.cleanup()

    def test_layer_metadata_from_classifier(self):
        L = self.p.add_layer("oks.building")
        self.assertEqual(L.layer_id, "oks.building")   # legacy 1:1
        self.assertEqual(L.semantic_class, "oks.building")
        self.assertEqual(L.stage, "project")
        self.assertEqual(L.style_id, "building.fill")

    def test_two_layers_share_semantic_class(self):
        # ключевая возможность MODEL-01: source-слой и проектный слой одного
        # класса живут раздельно (разные таблицы), под своими layer_id
        proj = self.p.add_layer("tp.func_zone", layer_id="project.tp.func_zone")
        src = self.p.add_layer("tp.func_zone", layer_id="source.fgistp.func_zones",
                               stage="existing", source_kind="fgistp",
                               title="ФГИС ТП: зоны")
        self.assertNotEqual(proj.table, src.table)
        zone = {"type": "Polygon", "coordinates": BOUNDARY["coordinates"]}
        proj.add_feature(zone, attrs={"zone_title": "Ж-1"})
        src.add_feature(zone, attrs={"zone_title": "Ж-исх"})
        # разрешаются по layer_id независимо
        self.assertEqual(self.p.layer_by_id("source.fgistp.func_zones").source_kind, "fgistp")
        self.assertEqual(next(self.p.layer_by_id("project.tp.func_zone").features())
                         ["attrs"]["zone_title"], "Ж-1")
        codes = [l["code"] for l in self.p.layers()]
        self.assertEqual(codes.count("tp.func_zone"), 2, "два слоя одного класса")

    def test_per_object_style_id(self):
        L = self.p.add_layer("oks.building")
        L.add_feature(BOUNDARY, attrs={"floors": 9}, style_id="building.accent")
        f = next(L.features())
        self.assertEqual(f["style_id"], "building.accent")

    def test_style_id_defaults_none(self):
        L = self.p.add_layer("terr.boundary")
        L.add_feature(BOUNDARY)
        self.assertIsNone(next(L.features())["style_id"])

    def test_migration_from_v1_schema(self):
        # старый .grado (grado_layers без layer_id, feature без style_id)
        self.p.close()
        path = Path(self.tmp.name) / "old.grado"
        conn = sqlite3.connect(str(path))
        # минимальный проект как до MODEL-01
        conn.executescript("""
            CREATE TABLE grado_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE gpkg_contents (table_name TEXT PRIMARY KEY, data_type TEXT,
                identifier TEXT, description TEXT, last_change TEXT, srs_id INTEGER,
                min_x REAL, min_y REAL, max_x REAL, max_y REAL);
            CREATE TABLE grado_layers (table_name TEXT PRIMARY KEY,
                classifier_code TEXT NOT NULL, title TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE "l_terr_boundary" (id INTEGER PRIMARY KEY AUTOINCREMENT,
                geom BLOB, source TEXT NOT NULL DEFAULT 'manual',
                source_date TEXT NOT NULL, source_doc TEXT, "name" TEXT);
        """)
        conn.executemany("INSERT INTO grado_meta VALUES (?,?)",
                         [("name", "Старый"), ("srs_id", "32637")])
        conn.execute("INSERT INTO grado_layers VALUES "
                     "('l_terr_boundary','terr.boundary','Граница','2026-01-01')")
        conn.execute("INSERT INTO gpkg_contents (table_name, data_type, srs_id) "
                     "VALUES ('l_terr_boundary','features',32637)")
        conn.commit()
        conn.close()
        p = Project.open(path)   # должен мигрировать без ошибок
        try:
            layers = p.layers()
            self.assertEqual(layers[0]["layer_id"], "terr.boundary")
            self.assertEqual(layers[0]["stage"], "base", "стадия восстановлена")
            self.assertEqual(layers[0]["style_id"], "boundary.line")
            # колонка style_id добавлена в feature-таблицу
            fcols = [r[1] for r in p.conn.execute(
                'PRAGMA table_info("l_terr_boundary")')]
            self.assertIn("style_id", fcols)
            p.layer("terr.boundary").add_feature(BOUNDARY, style_id="x")
            self.assertEqual(next(p.layer("terr.boundary").features())["style_id"], "x")
        finally:
            p.close()


if __name__ == "__main__":
    unittest.main()
