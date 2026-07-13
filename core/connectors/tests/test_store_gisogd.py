import io
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

import _paths  # noqa: F401
from grado_connectors import GisogdZip, NspdCapture, SnapshotStore, StoreError, diff
from grado_connectors.gisogd import find_ogr2ogr
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
        path.write_text(path.read_text().replace("77:09:1", "77:09:2"))
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


if __name__ == "__main__":
    unittest.main()
