"""Выгрузка SHP в раскладке ГИС ОГД (/api/export/shp): набор файлов на слой, поля латиницей до 10 знаков, UTF-8, МСК.
Архив читается обратно своим читателем ГИС ОГД (grado_connectors.shp_reader) — тем же, что разбирает выгрузки портала."""
import io
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402
import export_io  # noqa: E402
from grado_connectors import shp_reader  # noqa: E402

LON, LAT = 37.6, 55.75
SQ = [[LON, LAT], [LON, LAT + .0007], [LON + .001, LAT + .0007], [LON + .001, LAT], [LON, LAT]]   # по часовой в lon/lat
LAYERS = [
    {"name": "Эскиз: секции", "features": [
        {"type": "Feature", "properties": {"№": 1, "Корпус": "секция", "Этажность": 9, "СПП, м²": 4321.5, "Ряд": 2},
         "geometry": {"type": "Polygon", "coordinates": [SQ]}}]},
    {"name": "Эскиз: улицы и стоянки", "features": [
        {"type": "Feature", "properties": {"Вид": "стоянка", "Мест": 40, "Норма": "945-ПП прил. 5"}, "geometry": {"type": "Polygon", "coordinates": [SQ]}},
        {"type": "Feature", "properties": {"Вид": "ось"}, "geometry": {"type": "LineString", "coordinates": [[LON, LAT], [LON + .001, LAT]]}},
        {"type": "Feature", "properties": {}, "geometry": None}]},
]


def records(z, base):
    with z.open(base + ".shp") as shp, z.open(base + ".dbf") as dbf:
        return list(shp_reader.iter_records(io.BytesIO(shp.read()), io.BytesIO(dbf.read()), "utf-8"))


class ShpExport(unittest.TestCase):
    def setUp(self):
        self.srv = S.Server(("127.0.0.1", 0))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def post(self, obj):
        try:
            r = urllib.request.urlopen(urllib.request.Request(self.base + "/api/export/shp", data=json.dumps(obj).encode(), method="POST"), timeout=10)
        except urllib.error.HTTPError as e:
            r = e
        return r.status, r.headers, r.read()

    def test_ogd_layout_round_trip(self):
        st, h, body = self.post({"layers": LAYERS})
        self.assertEqual((st, h["Content-Type"]), (200, "application/zip"))
        z = zipfile.ZipFile(io.BytesIO(body))
        names = set(z.namelist())
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            self.assertIn("Эскиз_ секции" + ext, names)
        self.assertIn("Эскиз_ улицы и стоянки — площади.shp", names)       # точки, линии и площади одного слоя — разные наборы
        self.assertIn("Эскиз_ улицы и стоянки — линии.shp", names)
        self.assertEqual(z.read("Эскиз_ секции.cpg"), b"UTF-8")
        self.assertIn('PROJCS["Moscow_bessel"', z.read("Эскиз_ секции.prj").decode())
        rec = records(z, "Эскиз_ секции")
        self.assertEqual(len(rec), 1)
        p = rec[0]["properties"]
        self.assertEqual((p["num"], p["korpus"], p["etazh"], p["ryad"]), (1, "секция", 9, 2))
        self.assertAlmostEqual(p["spp_m2"], 4321.5)
        self.assertTrue(all(len(k) <= 10 and k.isascii() for k in p))
        x, y = S.crs.wgs84_to_msk(LON, LAT)                                   # координаты — МСК
        ring = rec[0]["geometry"]["coordinates"][0]
        self.assertTrue(any(abs(q[0] - x) < .01 and abs(q[1] - y) < .01 for q in ring))
        park = records(z, "Эскиз_ улицы и стоянки — площади")[0]["properties"]
        self.assertEqual((park["vid"], park["mest"]), ("стоянка", 40))
        csv = z.read("fields.csv").decode("utf-8-sig")
        self.assertIn('"spp_m2";"СПП, м²"', csv)
        self.assertIn("Пропущено объектов без геометрии: 1", z.read("README.txt").decode())

    def test_bad_input_is_400(self):
        st, _, body = self.post({"layers": []})
        self.assertEqual(st, 400)
        self.assertTrue(json.loads(body)["error"])


class FieldNames(unittest.TestCase):
    def test_transliterated_unique_ten_chars(self):
        used = set()
        a = export_io._field_name("Площадь участка по документу", used)
        b = export_io._field_name("Площадь участка по документу, га", used)
        self.assertEqual(a, "ploschad_u")
        self.assertNotEqual(a, b)
        self.assertLessEqual(len(b), 10)
        self.assertEqual(export_io._field_name("2 очередь", used), "f2_ochered")

    def test_outer_ring_clockwise(self):
        ccw = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
        r = export_io._shp_rings({"type": "Polygon", "coordinates": [ccw, ccw]})
        self.assertLess(export_io._ring_area(r[0]), 0)                       # внешнее — по часовой
        self.assertGreater(export_io._ring_area(r[1]), 0)                    # дыра — против


if __name__ == "__main__":
    unittest.main()
