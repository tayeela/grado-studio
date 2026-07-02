import json
import unittest
import urllib.parse

import _paths  # noqa: F401
from grado_connectors import ConnectorError, FgistpConnector, NspdCapture

# Захват как его шлёт браузерное расширение: GeoJSON EPSG:3857,
# вложенный options (иногда строкой), дубликаты геометрии
MERC_RING = [[4187345.5, 7509247.8], [4187445.5, 7509247.8],
             [4187445.5, 7509347.8], [4187345.5, 7509247.8]]
NSPD_PAYLOAD = {
    "type": "FeatureCollection",
    "grado_source": "nspd",
    "features": [
        {"type": "Feature",
         "geometry": {"type": "Polygon", "coordinates": [MERC_RING]},
         "properties": {"options": {"cad_num": "77:09:0004021:181",
                                    "land_record_type": "Земельный участок"}}},
        {"type": "Feature",  # дубликат по геометрии
         "geometry": {"type": "Polygon", "coordinates": [MERC_RING]},
         "properties": {"options": '{"cad_num": "77:09:0004021:181"}'}},
    ],
}


class TestNspd(unittest.TestCase):
    def test_capture_normalized(self):
        result = NspdCapture().fetch(payload=NSPD_PAYLOAD)
        self.assertEqual(len(result["features"]), 1, "дубликат геометрии отброшен")
        f = result["features"][0]
        self.assertEqual(f["grado_key"], "77:09:0004021:181")
        self.assertEqual(f["properties"]["opt_cad_num"], "77:09:0004021:181")
        self.assertEqual(f["properties"]["opt_land_record_type"], "Земельный участок")
        lon, lat = f["geometry"]["coordinates"][0][0]
        self.assertAlmostEqual(lon, 37.6155646, places=5)
        self.assertAlmostEqual(lat, 55.7522242, places=5)
        self.assertIn("дубликатов по геометрии отброшено: 1", result["notes"][0])

    def test_rejects_foreign_payload(self):
        with self.assertRaises(ConnectorError):
            NspdCapture().fetch(payload={"grado_source": "fgis_tp", "features": []})


UIN = "1" * 25
LAYERS = {"layer_stp_list": [
    {"classid": "60107", "class_name": "Функциональные зоны",
     "class_title": "Карта функциональных зон", "geom_type": "100",
     "stp_name": "Генеральный план г. Пущино"},
    {"classid": "60108", "class_name": "Дороги", "class_title": "Транспорт",
     "geom_type": "010", "stp_name": "Генеральный план г. Пущино"},
    {"classid": "60109", "class_name": "Пустой слой",
     "class_title": "Карта функциональных зон", "geom_type": "100",
     "stp_name": "Генеральный план г. Пущино"},
]}
WFS_60107 = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "id": "geo_db_data_fgistp_pol.101",
     "geometry": {"type": "Polygon",
                  "coordinates": [[[37.6, 54.8], [37.7, 54.8], [37.7, 54.9], [37.6, 54.8]]]},
     "properties": {"mt_status": 1, "mt_classid": "60107"}},
]}


def fake_transport(url):
    if "json_layers_stp_list.jsp" in url:
        assert f"uin={UIN}" in url
        return json.dumps(LAYERS).encode()
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    cql = q["CQL_FILTER"][0]
    assert f"uin='{UIN}'" in cql
    assert "((kit is null) OR (kit='irrelevant'))" in cql
    if "mt_classid='60107'" in cql:
        return json.dumps(WFS_60107).encode()
    return json.dumps({"type": "FeatureCollection", "features": []}).encode()


class TestFgistp(unittest.TestCase):
    def setUp(self):
        self.conn = FgistpConnector(transport=fake_transport)

    def test_discover(self):
        layers = self.conn.discover(UIN)
        self.assertEqual(len(layers), 3)
        self.assertEqual(layers[0]["classid"], "60107")

    def test_fetch_polygons(self):
        result = self.conn.fetch(UIN)
        self.assertEqual(len(result["features"]), 1)
        f = result["features"][0]
        self.assertEqual(f["grado_key"], "geo_db_data_fgistp_pol.101")
        self.assertEqual(f["properties"]["class_name"], "Функциональные зоны")
        self.assertEqual(f["properties"]["status_name"], "существующая")
        self.assertEqual(f["properties"]["uin"], UIN)
        self.assertIn("УИН " + UIN, result["source_doc"])
        self.assertIn("Пущино", result["source_doc"])
        self.assertTrue(any("60109" in n for n in result["notes"]),
                        "пустой слой отмечен в примечаниях")

    def test_wfs_url_format(self):
        url = self.conn.wfs_url(UIN, "60107", status="2")
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(q["typeName"][0], "min_eco_test:geo_db_data_fgistp_pol")
        self.assertEqual(q["version"][0], "2.0.0")
        self.assertEqual(q["srsName"][0], "EPSG:4326")
        self.assertIn("mt_status='2'", q["CQL_FILTER"][0])

    def test_unknown_geom_type(self):
        with self.assertRaises(ConnectorError):
            self.conn.wfs_url(UIN, "60107", geom_type="999")

    def test_no_layers_of_type_noted(self):
        result = self.conn.fetch(UIN, geom_type="001")
        self.assertEqual(result["features"], [])
        self.assertTrue(any("нет слоёв" in n for n in result["notes"]))


if __name__ == "__main__":
    unittest.main()
