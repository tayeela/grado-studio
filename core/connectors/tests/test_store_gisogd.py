import io
import json
import stat
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import _paths  # noqa: F401
from grado_connectors import GisogdZip, NspdCapture, SnapshotStore, StoreError, diff
from grado_connectors.contract import ConnectorError
from grado_connectors import gisogd
from grado_connectors.gisogd import clean_msg, find_ogr2ogr
from grado_connectors.crs import OGD_PROJ4

GJ = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "id": 1,
     "geometry": {"type": "Polygon",
                  "coordinates": [[[37.5, 55.7], [37.51, 55.7], [37.51, 55.71], [37.5, 55.7]]]},
     "properties": {"NAME": "Зона 1"}},
    {"type": "Feature", "id": 2,
     "geometry": {"type": "Point", "coordinates": [37.505, 55.705]},
     "properties": {"NAME": "Точка"}},
]}


def nspd_result():
    return NspdCapture().fetch(payload={
        "type": "FeatureCollection", "grado_source": "nspd",
        "features": [{"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [4187345.5, 7509247.8]},
                      "properties": {"options": {"cad_num": "77:09:1"}}}]})


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SnapshotStore(Path(self.tmp.name) / "snaps")
        self.conn = NspdCapture()

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_load_verify(self):
        sid = self.store.save(self.conn, nspd_result())
        manifest, features = self.store.load(sid)
        self.assertEqual(manifest["source"], "nspd")
        self.assertEqual(manifest["count"], 1)
        self.assertEqual(len(features), 1)
        self.assertTrue(self.store.verify(sid))

    def test_idempotent_same_content(self):
        sid1 = self.store.save(self.conn, nspd_result())
        sid2 = self.store.save(self.conn, nspd_result())
        self.assertEqual(sid1, sid2)
        self.assertEqual(len(self.store.list()), 1)

    def test_tamper_detected(self):
        sid = self.store.save(self.conn, nspd_result())
        path = self.store.root / sid / "data.geojson"
        path.write_text(
            path.read_text(encoding="utf-8").replace("77:09:1", "77:09:2"),
            encoding="utf-8")
        with self.assertRaises(StoreError):
            self.store.verify(sid)

    def test_latest_by_params(self):
        self.store.save(self.conn, nspd_result())
        m = self.store.latest("nspd")
        self.assertIsNotNone(m)
        self.assertIsNone(self.store.latest("fgistp"))

    def test_concurrent_identical_save_is_idempotent(self):
        # ThreadingHTTPServer: два одинаковых импорта параллельно не должны
        # ронять FileExistsError — контракт save() идемпотентен
        import threading
        errors, sids = [], []
        barrier = threading.Barrier(8)

        def worker():
            try:
                barrier.wait()
                sids.append(self.store.save(self.conn, nspd_result()))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [], "гонка save() уронила импорт")
        self.assertEqual(len(set(sids)), 1, "тот же контент — один снимок")
        self.assertEqual(len(self.store.list()), 1)


class TestDiff(unittest.TestCase):
    def test_added_removed_changed(self):
        a = [{"grado_key": "1", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}},
             {"grado_key": "2", "geometry": {"type": "Point", "coordinates": [1, 1]}, "properties": {}}]
        b = [{"grado_key": "2", "geometry": {"type": "Point", "coordinates": [1, 2]}, "properties": {}},
             {"grado_key": "3", "geometry": {"type": "Point", "coordinates": [3, 3]}, "properties": {}}]
        d = diff(a, b)
        self.assertEqual(d, {"added": ["3"], "removed": ["1"], "changed": ["2"]})


def make_ogd_zip(path, inner_files):
    """Внешний ZIP с вложенным ZIP (как отдаёт портал ОГД)."""
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        for name, data in inner_files.items():
            zf.writestr(name, data)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("выгрузка/данные.zip", inner.getvalue())


class TestGisogd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_nested_zip_geojson(self):
        zpath = Path(self.tmp.name) / "ogd.zip"
        make_ogd_zip(zpath, {"functional_zones.geojson": json.dumps(GJ, ensure_ascii=False)})
        result = GisogdZip().fetch(zpath)
        self.assertEqual(len(result["features"]), 2)
        f = result["features"][0]
        self.assertEqual(f["grado_key"], "functional_zones:1")
        self.assertEqual(f["properties"]["grado_member"], "functional_zones")
        self.assertEqual(f["properties"]["NAME"], "Зона 1")
        self.assertIn("ogd.zip", result["source_doc"])

    def test_empty_archive_noted(self):
        zpath = Path(self.tmp.name) / "empty.zip"
        make_ogd_zip(zpath, {"readme.txt": "пусто"})
        result = GisogdZip().fetch(zpath)
        self.assertEqual(result["features"], [])
        self.assertTrue(any("ни shp" in n for n in result["notes"]))

    def test_zip_cannot_write_outside_import_directory(self):
        zpath = Path(self.tmp.name) / "unsafe.zip"
        escaped = Path(self.tmp.name).parent / "grado-escaped.geojson"
        escaped.unlink(missing_ok=True)
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("../grado-escaped.geojson", json.dumps(GJ))
        with self.assertRaises(ConnectorError):
            GisogdZip().fetch(zpath)
        self.assertFalse(escaped.exists())

    def test_zip_symlink_is_rejected(self):
        zpath = Path(self.tmp.name) / "symlink.zip"
        link = zipfile.ZipInfo("link.geojson")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr(link, "../../outside")
        with self.assertRaises(ConnectorError):
            GisogdZip().fetch(zpath)

    @unittest.skipUnless(find_ogr2ogr(), "нет ogr2ogr (GDAL/QGIS)")
    def test_shp_msk50_roundtrip(self):
        """SHP в МСК-50 → WGS84 через ogr2ogr: путь реальных выгрузок ОГД."""
        work = Path(self.tmp.name)
        src = work / "src.geojson"
        src.write_text(json.dumps({
            "type": "FeatureCollection",
            "features": [GJ["features"][0]],
        }, ensure_ascii=False), encoding="utf-8")
        shp = work / "zones.shp"
        subprocess.run(
            [find_ogr2ogr(), "-f", "ESRI Shapefile", str(shp), str(src),
             "-s_srs", "EPSG:4326", "-t_srs", OGD_PROJ4],
            check=True, capture_output=True, timeout=300)
        zpath = work / "ogd_shp.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            for part in work.glob("zones.*"):
                zf.write(part, part.name)
        result = GisogdZip().fetch(zpath)
        self.assertEqual(len(result["features"]), 1)
        lon, lat = result["features"][0]["geometry"]["coordinates"][0][0]
        self.assertAlmostEqual(lon, 37.5, delta=1e-6)
        self.assertAlmostEqual(lat, 55.7, delta=1e-6)


class TestSnapshotIdValidation(unittest.TestCase):
    def test_bad_sid_rejected_everywhere(self):
        with tempfile.TemporaryDirectory() as td:
            store = SnapshotStore(Path(td) / "store")
            outside = Path(td) / "outside"
            outside.mkdir()
            (outside / "manifest.json").write_text('{"sha256": "x"}', encoding="utf-8")
            for bad in ("../outside", "..", ".hidden", "a/b", "", "a\nb", "/etc"):
                for call in (store.manifest, store.features, store.load, store.verify):
                    with self.assertRaises(StoreError, msg=f"{call.__name__}({bad!r})"):
                        call(bad)

    def test_save_with_bad_connector_name_rejected(self):
        class Evil:
            name, source = "../../evil", "x"
        with tempfile.TemporaryDirectory() as td:
            store = SnapshotStore(Path(td) / "store")
            with self.assertRaises(StoreError):
                store.save(Evil(), {"features": [], "params": {}})
            self.assertFalse((Path(td) / "evil").exists())

    def test_normal_roundtrip_still_works(self):
        with tempfile.TemporaryDirectory() as td:
            store = SnapshotStore(td)
            sid = store.save(NspdCapture(), nspd_result())
            self.assertRegex(sid, r"^[A-Za-z0-9_.-]+$")
            self.assertTrue(store.verify(sid))
            self.assertEqual(store.manifest(sid)["id"], sid)


class TestFindOgr2ogr(unittest.TestCase):
    def _exe(self, d, name="ogr2ogr"):
        p = Path(d) / name
        p.write_text("#!/bin/sh\n", encoding="utf-8")
        p.chmod(0o755)
        return str(p)

    def test_known_path_wins_over_path_lookup(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            known, onpath = self._exe(a), self._exe(b)
            with mock.patch.object(gisogd, "_OGR2OGR_FALLBACKS", [known]), \
                    mock.patch.object(gisogd, "_windows_ogr2ogr_candidates", return_value=[]), \
                    mock.patch.object(gisogd.shutil, "which", return_value=onpath):
                self.assertEqual(find_ogr2ogr(), known)

    def test_path_is_last_resort_and_must_be_absolute_executable(self):
        with tempfile.TemporaryDirectory() as d:
            onpath = self._exe(d)
            with mock.patch.object(gisogd, "_OGR2OGR_FALLBACKS", []), \
                    mock.patch.object(gisogd, "_windows_ogr2ogr_candidates", return_value=[]):
                with mock.patch.object(gisogd.shutil, "which", return_value=onpath):
                    self.assertEqual(find_ogr2ogr(), onpath)
                with mock.patch.object(gisogd.shutil, "which", return_value="ogr2ogr"):
                    self.assertIsNone(find_ogr2ogr(), "относительный путь отвергается")
                (Path(onpath)).chmod(0o644)
                with mock.patch.object(gisogd.shutil, "which", return_value=onpath):
                    self.assertIsNone(find_ogr2ogr(), "неисполняемый файл отвергается")


class TestCleanMsg(unittest.TestCase):
    def test_tmp_paths_newlines_and_length(self):
        tmp = "/var/folders/ab/cd/T/grado_ogd_xyz"
        msg = clean_msg(f"ERROR 1: Unable to open {tmp}/a/b.shp\nnext /Users/me/dir/f.dbf line\n" + "z" * 500, tmp=tmp)
        self.assertNotIn("/var/folders", msg)
        self.assertNotIn("/Users", msg)
        self.assertNotIn("\n", msg)
        self.assertIn("<tmp>", msg)
        self.assertLessEqual(len(msg), 200)

    def test_urls_survive(self):
        self.assertIn("https://gisogd.mos.ru/gis/api", clean_msg("HTTP error https://gisogd.mos.ru/gis/api/x"))


if __name__ == "__main__":
    unittest.main()
