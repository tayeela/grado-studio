"""Коннектор ГИС ОГД по открытому REST API портала.

Ключевая особенность, ради которой существует кэш: портал ИГНОРИРУЕТ bbox и
всегда отдаёт слой целиком (проверено на virtual1742: 3285 объектов и без
bbox, и с bbox 150 м). Поэтому режем по области сами, а слой держим в кэше.
"""

import json
import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401
from grado_connectors import ConnectorError, GisogdApi
from grado_connectors.gisogd_api import catalog, norm_id


def _poly(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[
        [x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


# Слой «как портал»: объект в зоне запроса, объект далеко, объект без геометрии
LAYER = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "geometry": _poly(37.60, 55.75, 37.61, 55.76),
     "properties": {"id": 149.0, "naimfunkzony": "жилая зона",
                    "summfondpersp": "440.1", "fztip": "120"}},
    {"type": "Feature", "geometry": _poly(30.0, 50.0, 30.1, 50.1),
     "properties": {"id": 2.0, "naimfunkzony": "далёкая зона"}},
    {"type": "Feature", "geometry": None, "properties": {"id": 3.0}},
]}

BBOX = (37.60, 55.75, 37.62, 55.76)


class FakeTransport:
    def __init__(self, payload=LAYER):
        self.calls = []
        self.payload = payload

    def __call__(self, url, timeout=None):
        self.calls.append(url)
        return json.dumps(self.payload).encode("utf-8")


class TestGisogdApi(unittest.TestCase):
    def test_filters_by_bbox_locally(self):
        conn = GisogdApi(transport=FakeTransport())
        r = conn.fetch(BBOX, "virtual1742")
        self.assertEqual(len(r["features"]), 1, "остаётся только объект в области")
        self.assertEqual(r["features"][0]["properties"]["naimfunkzony"], "жилая зона")
        self.assertEqual(r["crs"], "EPSG:4326")

    def test_key_has_code_prefix_and_int_id(self):
        # ТиНАО сливает 15 слоёв, id в них свои — без префикса кода ключи
        # столкнулись бы и дедупликация губила бы объекты
        conn = GisogdApi(transport=FakeTransport())
        r = conn.fetch(BBOX, "virtual1982")
        self.assertEqual(r["features"][0]["grado_key"], "virtual1982:149")

    def test_norm_id_strips_float_tail(self):
        self.assertEqual(norm_id(149.0), "149")
        self.assertEqual(norm_id(1.5), "1.5")
        self.assertEqual(norm_id("abc"), "abc")

    def test_cache_avoids_second_download(self):
        t = FakeTransport()
        with tempfile.TemporaryDirectory() as td:
            conn = GisogdApi(transport=t, cache_dir=td)
            first = conn.fetch(BBOX, "virtual1742")
            second = conn.fetch(BBOX, "virtual1742")
            self.assertEqual(len(t.calls), 1, "второй раз слой берётся из кэша")
            self.assertEqual(len(second["features"]), len(first["features"]))
            self.assertTrue(first["notes"], "первая загрузка честно предупреждает")
            self.assertFalse(second["notes"], "из кэша предупреждать не о чем")
            self.assertTrue((Path(td) / "virtual1742.geojson.gz").is_file())

    def test_line_cache_gives_same_answer(self):
        # второй запрос идёт по построчному кэшу: те же объекты, те же ключи, без сети
        t = FakeTransport()
        with tempfile.TemporaryDirectory() as td:
            conn = GisogdApi(transport=t, cache_dir=td)
            first = conn.fetch(BBOX, "virtual1742")
            self.assertTrue((Path(td) / "virtual1742.lines.gz").is_file())
            second = conn.fetch(BBOX, "virtual1742")
            far = conn.fetch((29.9, 49.9, 30.2, 50.2), "virtual1742")
            self.assertEqual(len(t.calls), 1)
            self.assertEqual([f["grado_key"] for f in second["features"]], [f["grado_key"] for f in first["features"]])
            self.assertEqual(second["features"][0]["properties"], first["features"][0]["properties"])
            self.assertEqual([f["properties"]["naimfunkzony"] for f in far["features"]], ["далёкая зона"])

    def test_expired_cache_refetches(self):
        t = FakeTransport()
        with tempfile.TemporaryDirectory() as td:
            conn = GisogdApi(transport=t, cache_dir=td, ttl=0)
            conn.fetch(BBOX, "virtual1742")
            conn.fetch(BBOX, "virtual1742")
            self.assertEqual(len(t.calls), 2, "протухший кэш перекачивается")

    def test_export_url_asks_geojson(self):
        t = FakeTransport()
        GisogdApi(transport=t).fetch(BBOX, "virtual1742")
        self.assertIn("/layers/virtual1742/export/", t.calls[0])
        self.assertIn("format=geojson", t.calls[0])

    def test_broken_payload_raises(self):
        conn = GisogdApi(transport=FakeTransport(payload={"type": "Nonsense"}))
        with self.assertRaises(ConnectorError):
            conn.fetch(BBOX, "virtual1742")

    def test_catalog_builds_tree_path(self):
        tree = [
            {"id": 1, "parent_id": None, "code": "f1", "name": "Слои", "type": "folder"},
            {"id": 2, "parent_id": 1, "code": "f2", "name": "Генплан", "type": "folder"},
            {"id": 3, "parent_id": 2, "code": "virtual1742",
             "name": "Функциональные зоны", "type": "layer"},
        ]

        def transport(url, timeout=None):
            return json.dumps(tree).encode("utf-8")

        cat = catalog(transport=transport)
        row = next(c for c in cat if c["code"] == "virtual1742")
        self.assertEqual(row["path"], "Слои / Генплан / Функциональные зоны")
        self.assertEqual(row["type"], "layer")



class GisogdProgress(unittest.TestCase):
    """Первая выгрузка слоя целиком сообщает ход: размер берётся из Content-Length или ETag портала."""

    def test_expected_size_from_headers(self):
        from grado_connectors.gisogd_api import _expected_size
        self.assertEqual(_expected_size({"Content-Length": "22099748"}), 22099748)
        self.assertEqual(_expected_size({"Content-Encoding": "gzip", "Content-Length": "6000000",
                                         "ETag": 'W/"1790146102.3793728-22099748-2461611553"'}), 22099748)
        self.assertIsNone(_expected_size({"Content-Encoding": "gzip"}))

    def test_parse_stage_reported_with_custom_transport(self):
        import json
        import tempfile
        from grado_connectors.gisogd_api import GisogdApi
        seen = []
        body = json.dumps({"type": "FeatureCollection", "features": []}).encode()
        with tempfile.TemporaryDirectory() as d:
            GisogdApi(transport=lambda url: body, cache_dir=d, progress=lambda *a: seen.append(a)).fetch((0, 0, 1, 1), "x1")
        self.assertEqual(seen, [("x1", len(body), len(body), "parse")])

if __name__ == "__main__":
    unittest.main()
