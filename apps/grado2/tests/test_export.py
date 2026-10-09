"""Exports of ГРАДО 2: GeoJSON in МСК for QGIS (/api/export/geojson) and the ТЭП + sheet list workbook (/api/export/xlsx)."""
import io
import json
import re
import sys
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402
import export_io  # noqa: E402

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
LON, LAT = 37.6, 55.75
SQ = [[LON, LAT], [LON + .001, LAT], [LON + .001, LAT + .0007], [LON, LAT + .0007], [LON, LAT]]


def area(ring):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))) / 2


class Http(unittest.TestCase):
    def setUp(self):
        self.srv = S.Server(("127.0.0.1", 0))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def post(self, path, obj):
        data = obj if isinstance(obj, bytes) else json.dumps(obj).encode("utf-8")
        try:
            r = urllib.request.urlopen(urllib.request.Request(self.base + path, data=data, method="POST"), timeout=10)
        except urllib.error.HTTPError as e:
            r = e
        return r.status, r.headers, r.read()


class GeoJsonExport(Http):
    LAYERS = [{"name": "Эскиз: здания", "features": [
        {"type": "Feature", "properties": {"Этажность": 9, "Назначение": "жилое"}, "geometry": {"type": "Polygon", "coordinates": [SQ]}},
        {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [LON, LAT]}}]},
        {"name": "Эскиз: здания", "features": []}]

    def test_zip_has_one_utf8_file_per_layer_in_msk(self):
        st, h, body = self.post("/api/export/geojson", {"layers": self.LAYERS})
        self.assertEqual((st, h["Content-Type"]), (200, "application/zip"))
        z = zipfile.ZipFile(io.BytesIO(body))
        self.assertEqual(sorted(z.namelist()), ["README.txt", "Эскиз_ здания.geojson", "Эскиз_ здания_2.geojson"])
        fc = json.loads(z.read("Эскиз_ здания.geojson").decode("utf-8"))
        self.assertIn("+proj=tmerc", fc["crs"]["properties"]["name"])
        self.assertEqual(fc["features"][0]["properties"], {"Этажность": 9, "Назначение": "жилое"})
        x, y = S.crs.wgs84_to_msk(LON, LAT)                                   # то же значение, что пишет экспорт DXF
        px, py = fc["features"][1]["geometry"]["coordinates"]
        self.assertAlmostEqual(px, x, places=6)
        self.assertAlmostEqual(py, y, places=6)
        self.assertIn("МСК", z.read("README.txt").decode("utf-8"))

    def test_point_equals_dxf_export(self):
        try:
            import ezdxf
            import dxf_io
        except ImportError:
            self.skipTest("ezdxf not installed")
        fc = {"type": "FeatureCollection", "features": [self.LAYERS[0]["features"][1]]}
        z = zipfile.ZipFile(io.BytesIO(dxf_io.export_dxf([{"name": "P", "features": fc}], S.REDLN, S.LGR_COLORS)))
        pt = next(e for e in ezdxf.read(io.StringIO(z.read("grado2.dxf").decode())).modelspace() if e.dxftype() == "POINT")
        g = zipfile.ZipFile(io.BytesIO(export_io.export_geojson([{"name": "P", "features": fc}])))
        gx, gy = json.loads(g.read("P.geojson"))["features"][0]["geometry"]["coordinates"]
        self.assertAlmostEqual(gx, pt.dxf.location.x, places=6)
        self.assertAlmostEqual(gy, pt.dxf.location.y, places=6)

    def test_area_is_preserved(self):
        fc = json.loads(zipfile.ZipFile(io.BytesIO(export_io.export_geojson(self.LAYERS[:1]))).read("Эскиз_ здания.geojson"))
        ring = fc["features"][0]["geometry"]["coordinates"][0]
        want = area([list(S.crs.wgs84_to_msk(x, y)) for x, y in SQ])
        self.assertAlmostEqual(area(ring), want, places=4)
        self.assertTrue(70 < area(ring) / 1 < 90000)                           # ~64 x 78 m, метры, а не градусы

    def test_malformed_is_400_not_500(self):
        bad = [{}, {"layers": []}, {"layers": "x"}, {"layers": [1]}, {"layers": [{"name": "", "features": []}]},
               {"layers": [{"name": "a", "features": "x"}]}, {"layers": [{"name": "a", "features": [1]}]},
               {"layers": [{"name": "a", "features": [{"geometry": {"type": "Point", "coordinates": [True, 55]}}]}]},
               {"layers": [{"name": "a", "features": [{"geometry": {"type": "Point", "coordinates": [1e400, 55]}}]}]},
               {"layers": [{"name": "a", "features": [{"geometry": {"type": "Point", "coordinates": [10 ** 30, 55]}}]}]},
               {"layers": [{"name": "a", "features": [{"geometry": {"type": "Point", "coordinates": [37]}}]}]},
               {"layers": [{"name": "a", "features": [{"geometry": {"type": "Polygon", "coordinates": [37]}}]}]},
               {"layers": [{"name": "a", "features": [{"geometry": {"type": "GeometryCollection"}}]}]},
               {"layers": [{"name": "a", "features": [{"geometry": {"type": "GeometryCollection", "geometries": [{"type": "Circle"}]}}]}]},
               {"layers": [{"name": "a", "features": [{"geometry": None, "properties": 5}]}]},
               {"layers": [{"name": 5, "features": []}]}]
        for b in bad:
            raw = json.dumps(b).replace("1e+400", "1e400").encode()
            self.assertEqual(self.post("/api/export/geojson", raw)[0], 400, b)
        self.assertEqual(self.post("/api/export/geojson", b"[]")[0], 400)
        self.assertEqual(self.post("/api/export/geojson", b'{"layers":[{"name":"a","features":[{"properties":{"x":NaN},"geometry":{"type":"Point","coordinates":[37,55]}}]}]}')[0], 400)


class GeoJsonExportHardening(Http):
    PT = {"type": "Point", "coordinates": [LON, LAT]}
    POLY = {"type": "Polygon", "coordinates": [SQ]}

    def zip(self, layers):
        st, h, body = self.post("/api/export/geojson", {"layers": layers})
        self.assertEqual(st, 200, body)
        return zipfile.ZipFile(io.BytesIO(body))

    def test_geometry_collection_is_flattened_with_same_properties(self):
        gc = {"type": "GeometryCollection", "geometries": [self.PT, {"type": "GeometryCollection", "geometries": [self.POLY]}]}
        z = self.zip([{"name": "L", "features": [{"type": "Feature", "properties": {"a": 1}, "geometry": gc}]}])
        fs = json.loads(z.read("L.geojson"))["features"]
        self.assertEqual([f["geometry"]["type"] for f in fs], ["Point", "Polygon"])
        self.assertEqual([f["properties"] for f in fs], [{"a": 1}, {"a": 1}])
        self.assertIn("разложено на части: 1", z.read("README.txt").decode("utf-8"))

    def test_null_and_empty_geometry_skipped_and_counted(self):
        empty = {"type": "GeometryCollection", "geometries": []}
        z = self.zip([{"name": "L", "features": [{"geometry": None}, {"properties": {}}, {"geometry": empty}, {"geometry": self.PT}]}])
        self.assertEqual(len(json.loads(z.read("L.geojson"))["features"]), 1)
        self.assertIn("без геометрии: 3", z.read("README.txt").decode("utf-8"))

    def test_clean_export_readme_has_no_counts(self):
        z = self.zip([{"name": "L", "features": [{"geometry": self.PT}]}])
        self.assertNotIn("Пропущено", z.read("README.txt").decode("utf-8"))

    def test_windows_reserved_names_get_suffix(self):
        names = ["CON", "nul", "Com1", "LPT9", "aux.txt", "COM0", "CONSOLE"]
        z = self.zip([{"name": n, "features": []} for n in names])
        self.assertEqual(sorted(z.namelist()), sorted(["CON_.geojson", "nul_.geojson", "Com1_.geojson", "LPT9_.geojson",
                                                       "aux.txt_.geojson", "COM0.geojson", "CONSOLE.geojson", "README.txt"]))

    def test_feature_cap_is_400(self):
        old = export_io.MAX_FEATURES
        export_io.MAX_FEATURES = 3
        try:
            f = {"geometry": self.PT}
            self.assertEqual(self.post("/api/export/geojson", {"layers": [{"name": "a", "features": [f] * 3}]})[0], 200)
            st, _, body = self.post("/api/export/geojson", {"layers": [{"name": "a", "features": [f] * 2}, {"name": "b", "features": [f] * 2}]})
            self.assertEqual(st, 400)
            self.assertIn(b"too many features", body)
            gc = {"geometry": {"type": "GeometryCollection", "geometries": [self.PT] * 4}}      # разбор не обходит предел
            self.assertEqual(self.post("/api/export/geojson", {"layers": [{"name": "a", "features": [gc]}]})[0], 400)
        finally:
            export_io.MAX_FEATURES = old

    def test_gc_nesting_is_limited(self):
        g = self.PT
        for _ in range(10):
            g = {"type": "GeometryCollection", "geometries": [g]}
        self.assertEqual(self.post("/api/export/geojson", {"layers": [{"name": "a", "features": [{"geometry": g}]}]})[0], 400)


class XlsxExport(Http):
    TEP = [{"group": "Общие", "title": "Территория", "value": 45.9, "unit": "га"},
           {"group": "Общие", "title": "Плотность", "value": 25, "unit": "тыс. м²/га"},
           {"group": "Население", "title": "=CMD()", "value": "+1+1", "unit": "-x"},
           {"group": "Население", "title": "@SUM(A1)", "value": None, "unit": ""}]
    SHEETS = [{"n": 1, "title": "Титул", "format": "А3", "scale": None}, {"n": 2, "title": "План", "format": "А1", "scale": 2000}]

    def book(self, **kw):
        st, h, body = self.post("/api/export/xlsx", {"tep": self.TEP, "sheets": self.SHEETS, **kw})
        self.assertEqual(st, 200)
        self.assertIn("spreadsheetml.sheet", h["Content-Type"])
        return zipfile.ZipFile(io.BytesIO(body))

    @staticmethod
    def cells(z, name):
        root = ET.fromstring(z.read(name))
        return {c.get("r"): c for c in root.iter("{%s}c" % NS["m"])}

    @staticmethod
    def text(c):
        return "".join(t.text or "" for t in c.iter("{%s}t" % NS["m"]))

    def test_opens_and_every_part_is_well_formed(self):
        z = self.book(note="Нормативы изменены вручную: 3", project="Квартал")
        for n in z.namelist():
            ET.fromstring(z.read(n))
        wb = z.read("xl/workbook.xml").decode("utf-8")
        self.assertIn('name="ТЭП"', wb)
        self.assertIn('name="Листы"', wb)

    def test_numbers_are_numeric_cells_and_cyrillic_survives(self):
        z = self.book(note="Нормативы изменены вручную: 3")
        c = self.cells(z, "xl/worksheets/sheet1.xml")
        self.assertEqual(self.text(c["A1"]), "Нормативы изменены вручную: 3")           # примечание — первой строкой
        self.assertEqual(c["A1"].get("s"), "1")                                          # жирным
        row = next(r for r in c if c[r].get("t") == "inlineStr" and self.text(c[r]) == "Территория")
        v = c["B" + row[1:]]
        self.assertEqual(v.get("t"), "n")
        self.assertEqual(float(v.find("m:v", NS).text), 45.9)
        self.assertEqual(self.text(c["C" + row[1:]]), "га")
        self.assertEqual(self.cells(z, "xl/worksheets/sheet2.xml")["D3"].find("m:v", NS).text, "2000")
        self.assertEqual(self.cells(z, "xl/worksheets/sheet2.xml")["D3"].get("t"), "n")
        self.assertIn("customWidth", z.read("xl/worksheets/sheet1.xml").decode("utf-8"))
        self.assertTrue(any(self.text(x) == "Население" and x.get("s") == "1" for x in c.values()))   # заголовок группы жирным

    def test_formula_like_strings_stay_text(self):
        z = self.book()
        for part in ("xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml"):
            self.assertNotIn("<f>", z.read(part).decode("utf-8"))
        c = self.cells(z, "xl/worksheets/sheet1.xml")
        texts = {self.text(x): x.get("t") for x in c.values()}
        for s in ("=CMD()", "+1+1", "-x", "@SUM(A1)"):
            self.assertEqual(texts[s], "inlineStr", s)

    def test_malformed_is_400_not_500(self):
        bad = [{"tep": "x"}, {"tep": [1]}, {"tep": [{"title": ""}]}, {"tep": [{"title": 5}]}, {"tep": [{"title": "a", "value": True}]},
               {"tep": [{"title": "a", "value": [1]}]}, {"tep": [{"title": "a", "value": 10 ** 40}]}, {"tep": [{"title": "a", "value": 1e400}]},
               {"tep": [{"title": "a", "group": 3}]}, {"sheets": [3]}, {"sheets": [{"scale": False}]}, {"sheets": {"a": 1}},
               {"note": 5}, {"project": ["a"]}, {"tep": [{"title": "x" * 40000}]}]
        for b in bad:
            self.assertEqual(self.post("/api/export/xlsx", json.dumps(b).replace("1e+400", "1e400").encode())[0], 400, b)
        self.assertEqual(self.post("/api/export/xlsx", b'{"tep":[{"title":"a","value":NaN}]}')[0], 400)
        self.assertEqual(self.post("/api/export/xlsx", b"[]")[0], 400)

    def test_empty_request_gives_empty_workbook(self):
        st, _, body = self.post("/api/export/xlsx", {})
        self.assertEqual(st, 200)
        ET.fromstring(zipfile.ZipFile(io.BytesIO(body)).read("xl/worksheets/sheet1.xml"))


if __name__ == "__main__":
    unittest.main()


class PlaceByArea(Http):
    """T8: район, зона и K2 территории — по району с наибольшей долей площади; данные только локальные (кэш и эталон)."""
    X0, Y0, W, H = 37.0, 55.0, 0.02, 0.01                     # синтетика: западные 40% — «Арбат» (зона 1), восточные 60% — «Бекасово» (зона 2)

    def rect(self, x0, x1, y0=None, y1=None):
        y0, y1 = (self.Y0, self.Y0 + self.H) if y0 is None else (y0, y1)
        return [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]

    def setUp(self):
        super().setUp()
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.old = (S.CACHE, S._admin_districts, S.OsmOverpass._http_post)
        S.CACHE = Path(self.tmp.name)
        (S.CACHE / "place").mkdir()
        cut = self.X0 + self.W * 0.4
        wide = (self.X0 - 1, self.Y0 - 1, self.X0 + 1, self.Y0 + 1)
        S._admin_districts = lambda: [("Арбат", "ЦАО", [self.rect(self.X0 - .5, cut, self.Y0 - .5, self.Y0 + .5)], wide),
                                      ("Бекасово", "НАО", [self.rect(cut, self.X0 + .5, self.Y0 - .5, self.Y0 + .5)], wide)]
        S.OsmOverpass._http_post = lambda *a, **k: self.fail("no portal traffic expected")
        S._PLACE_MEMO.clear()
        self.cx, self.cy = self.X0 + self.W * 0.2, self.Y0 + self.H / 2           # центр — в Арбате (в 40%)
        key = (round(self.cx, 3), round(self.cy, 3))
        (S.CACHE / "place" / f"{key[0]}_{key[1]}.json").write_text(json.dumps({"elements": [
            {"type": "area", "tags": {"admin_level": "8", "name": "район Арбат"}},
            {"type": "area", "tags": {"admin_level": "5", "name": "Центральный административный округ"}}]}), "utf-8")

    def tearDown(self):
        S.CACHE, S._admin_districts, S.OsmOverpass._http_post = self.old
        S._PLACE_MEMO.clear()
        self.tmp.cleanup()
        super().tearDown()

    def place(self, **kw):
        st, _, body = self.post("/api/place", {"lon": self.cx, "lat": self.cy, **kw})
        return st, json.loads(body)

    def test_larger_share_wins_over_centre(self):
        st, r = self.place(polygon={"type": "Polygon", "coordinates": self.rect(self.X0, self.X0 + self.W)})
        self.assertEqual(st, 200)
        self.assertEqual(r["chosen_by"], "area")
        self.assertEqual(r["district"], "Бекасово")
        self.assertEqual([d["name"] for d in r["districts"]], ["Бекасово", "Арбат"])
        self.assertAlmostEqual(r["districts"][0]["share"], 0.6, places=2)
        self.assertAlmostEqual(r["districts"][1]["share"], 0.4, places=2)
        self.assertEqual((r["zone"], r["tinao"]), (2, 1))
        self.assertEqual(r["k2"], S.DISTRICTS["k2"]["Бекасово"]["value"])
        self.assertEqual(r["okrug"], "Новомосковский административный округ")

    def test_without_polygon_centre_is_used(self):
        st, r = self.place()
        self.assertEqual((st, r["chosen_by"], r["district"], r["zone"], r["districts"]), (200, "centre", "Арбат", 1, []))

    def test_polygon_outside_reference_falls_back_to_centre(self):
        far = [[[40, 50], [40.1, 50], [40.1, 50.1], [40, 50.1], [40, 50]]]
        st, r = self.place(polygon={"type": "Polygon", "coordinates": far})
        self.assertEqual((st, r["chosen_by"], r["district"]), (200, "centre", "Арбат"))

    def test_memo_is_bounded_and_keys_are_small(self):
        old = S.MAX_PLACE_MEMO
        S.MAX_PLACE_MEMO = 2
        try:
            for dx in (0.0, 0.01, 0.02):                          # три разных контура, предел 2
                poly = {"type": "Polygon", "coordinates": self.rect(self.X0 + dx, self.X0 + self.W)}
                self.assertEqual(self.place(polygon=poly)[0], 200)
            self.assertEqual(len(S._PLACE_MEMO), 2)
            self.assertTrue(all(isinstance(k[2], str) and len(k[2]) == 40 for k in S._PLACE_MEMO))
        finally:
            S.MAX_PLACE_MEMO = old

    def test_malformed_polygon_is_400(self):
        for poly in ("x", [], {"type": "Point", "coordinates": [1, 2]}, {"type": "Polygon", "coordinates": "x"}, {"type": "Polygon", "coordinates": []},
                     {"type": "Polygon", "coordinates": [[[1, 2], [3, 4]]]}, {"type": "Polygon", "coordinates": [[[True, 2], [3, 4], [5, 6], [True, 2]]]},
                     {"type": "Polygon", "coordinates": [[[10 ** 30, 2], [3, 4], [5, 6], [10 ** 30, 2]]]},
                     {"type": "Polygon", "coordinates": [[[1, 2], [3, 4], [5, "a"], [1, 2]]]}):
            self.assertEqual(self.place(polygon=poly)[0], 400, poly)
        for body in (b'{"lon":NaN,"lat":55}', b'{"lon":true,"lat":55}', b'{"lon":1e400,"lat":55}', b'{"lon":"x","lat":55}', b'{"lat":55}'):
            self.assertEqual(self.post("/api/place", body)[0], 400, body)
