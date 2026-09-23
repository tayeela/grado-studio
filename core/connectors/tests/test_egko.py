"""ЕГКО Москвы — карта base2 портала ГИС ОГД: потоковая выгрузка, сетка на диске, обрезка по рамке.

Слои base2 огромны (газоны — 308 МБ в SHP), поэтому коннектор не держит слой в памяти: архив SHP (родные координаты
ГИС ОГД) ложится на диск, записи читаются по одной, объекты раскладываются по клеткам сетки на диске, выдача режется
по рамке области.
"""

import json
import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401
from grado_connectors import ConnectorError, GisogdApi
from grado_connectors.clip import clip_geometry
from _shpfix import shp_zip
from grado_connectors.gisogd_api import MAPS, catalog

BOX = (37.600, 55.760, 37.612, 55.766)


def _poly(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


# «как портал»: crs перед features, пустые строки — пробелом, id — float, дороги — один полигон на полгорода
LAYER = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
         "features": [
             {"type": "Feature", "id": 1, "properties": {"orbis_id": 1.0, "type_zd": "Жилое", "house": "5", "estate": " ", "h": 14.6},
              "geometry": _poly(37.605, 55.762, 37.606, 55.763)},                       # целиком в области
             {"type": "Feature", "id": 2, "properties": {"orbis_id": 2.0, "type_zd": "Нежилое"},
              "geometry": _poly(37.611, 55.765, 37.613, 55.767)},                       # на краю — режется
             {"type": "Feature", "id": 3, "properties": {"orbis_id": 3.0}, "geometry": _poly(37.3, 55.5, 37.9, 55.9)},   # крупный
             {"type": "Feature", "id": 4, "properties": {"orbis_id": 4.0}, "geometry": _poly(37.70, 55.80, 37.701, 55.801)},   # далеко
             {"type": "Feature", "id": 5, "properties": {"orbis_id": 5.0, "vid_road": "тротуар"},
              "geometry": {"type": "LineString", "coordinates": [[37.59, 55.763], [37.62, 55.763]]}},
             {"type": "Feature", "id": 6, "properties": {"orbis_id": 6.0, "full_addr": "улица Тверская, дом 18"},
              "geometry": {"type": "Point", "coordinates": [37.605, 55.764]}},
             {"type": "Feature", "id": 7, "properties": {"orbis_id": 7.0}, "geometry": {"type": "Point", "coordinates": [37.65, 55.764]}},
         ]}


def pts(g):
    """Вершины геометрии округлённо (1e-9° ≈ 0,1 мм), без порядка обхода: SHP пишет внешнее кольцо по часовой."""
    out, c = set(), g["coordinates"]

    def walk(c):
        if isinstance(c[0], (int, float)):
            out.add((round(c[0], 9), round(c[1], 9)))
        else:
            for x in c:
                walk(x)
    walk(c)
    return out


class FakeTransport:
    def __init__(self, payload=LAYER):
        self.calls, self.payload = [], payload

    def __call__(self, url, timeout=None):
        self.calls.append(url)
        return shp_zip(self.payload)


class TestEgko(unittest.TestCase):
    def test_base2_url_and_key_carry_the_map(self):
        t = FakeTransport()
        r = GisogdApi(transport=t, map_name="base2").fetch(BOX, "virtual6")
        self.assertTrue(t.calls[0].startswith(MAPS["base2"]["base"] + "/layers/virtual6/export/"))
        keys = {f["grado_key"] for f in r["features"]}
        self.assertIn("base2:virtual6:1", keys, "код base2 пишется как код isogd — ключ несёт карту")
        self.assertIn("ЕГКО", r["source_doc"])

    def test_isogd_default_unchanged(self):
        t = FakeTransport()
        r = GisogdApi(transport=t).fetch(BOX, "virtual6")
        self.assertTrue(t.calls[0].startswith(MAPS["isogd"]["base"] + "/layers/virtual6/export/"))
        self.assertIn("virtual6:1", {f["grado_key"] for f in r["features"]})
        # без обрезки: объект на краю приходит целиком
        edge = next(f for f in r["features"] if f["grado_key"] == "virtual6:2")
        self.assertEqual(pts(edge["geometry"]), pts(LAYER["features"][1]["geometry"]))

    def test_catalog_base2_asks_full(self):
        seen = []
        catalog(lambda url, timeout=None: seen.append(url) or b"[]", map_name="base2")
        self.assertTrue(seen[0].endswith("/base2/layers/?type=full&returnCss=0"))

    def test_export_is_shp_and_bad_zip_is_an_error(self):
        t = FakeTransport()
        GisogdApi(transport=t, map_name="base2").fetch(BOX, "fence2k")
        self.assertIn("format=shp", t.calls[0])
        with self.assertRaises(ConnectorError):
            GisogdApi(transport=lambda url, timeout=None: b"<html>busy</html>", map_name="base2").fetch(BOX, "fence2k")

    def test_grid_cache_second_query_without_network_same_answer(self):
        with tempfile.TemporaryDirectory() as d:
            t = FakeTransport()
            first = GisogdApi(transport=t, cache_dir=d, map_name="base2", clip=True).fetch(BOX, "virtual6")
            t2 = FakeTransport()
            second = GisogdApi(transport=t2, cache_dir=d, map_name="base2", clip=True).fetch(BOX, "virtual6")
            self.assertEqual(t2.calls, [], "второй раз — из сетки на диске")
            key = lambda r: sorted((f["grado_key"], json.dumps(f["geometry"], sort_keys=True)) for f in r["features"])
            self.assertEqual(key(first), key(second))
            grid = Path(d) / "base2.virtual6.shp.grid"
            self.assertTrue((grid / "_meta.json").exists() and (grid / "big.lines.gz").exists())
            # другая область — тоже из сетки, и объекта оттуда нет в первой
            far = GisogdApi(transport=t2, cache_dir=d, map_name="base2").fetch((37.69, 55.79, 37.71, 55.81), "virtual6")
            self.assertIn("base2:virtual6:4", {f["grado_key"] for f in far["features"]})
            self.assertEqual(t2.calls, [])

    def test_isogd_and_base2_caches_do_not_mix(self):
        with tempfile.TemporaryDirectory() as d:
            other = dict(LAYER, features=[dict(LAYER["features"][0], properties={"orbis_id": 1.0, "name": "isogd"})])
            GisogdApi(transport=FakeTransport(other), cache_dir=d).fetch(BOX, "virtual6")
            b = GisogdApi(transport=FakeTransport(), cache_dir=d, map_name="base2").fetch(BOX, "virtual6")
            i = GisogdApi(transport=FakeTransport(), cache_dir=d).fetch(BOX, "virtual6")
            self.assertEqual(len(b["features"]), 5)
            self.assertEqual([f["properties"].get("name") for f in i["features"]], ["isogd"], "isogd берёт свой кэш")

    def test_clip_applies_to_egko(self):
        r = GisogdApi(transport=FakeTransport(), map_name="base2", clip=True).fetch(BOX, "virtual6")
        by = {f["grado_key"]: f["geometry"] for f in r["features"]}
        self.assertEqual(pts(by["base2:virtual6:1"]), pts(LAYER["features"][0]["geometry"]), "целиком внутри — как есть")
        xs = [p[0] for p in by["base2:virtual6:2"]["coordinates"][0]]
        self.assertLessEqual(max(xs), BOX[2] + 1e-12, "край обрезан по рамке")
        big = by["base2:virtual6:3"]["coordinates"][0]
        self.assertEqual(sorted({(round(x, 6), round(y, 6)) for x, y in big}), sorted({(37.6, 55.76), (37.612, 55.76), (37.612, 55.766), (37.6, 55.766)}))
        self.assertNotIn("base2:virtual6:7", by, "точка вне рамки отброшена")
        line = by["base2:virtual6:5"]["coordinates"]
        self.assertEqual([round(line[0][0], 6), round(line[-1][0], 6)], [37.6, 37.612])


class TestClip(unittest.TestCase):
    B = (0, 0, 10, 10)

    def test_polygon_rings_and_holes(self):
        g = clip_geometry({"type": "Polygon", "coordinates": [[[-5, -5], [15, -5], [15, 15], [-5, 15], [-5, -5]],
                                                               [[2, 2], [4, 2], [4, 4], [2, 4], [2, 2]],
                                                               [[20, 20], [21, 20], [21, 21], [20, 20]]]}, self.B)
        self.assertEqual(len(g["coordinates"]), 2, "дыра внутри осталась, дыра снаружи отброшена")
        self.assertEqual({(x, y) for x, y in g["coordinates"][0]}, {(0, 0), (10, 0), (10, 10), (0, 10)})

    def test_polygon_outside_is_none(self):
        self.assertIsNone(clip_geometry({"type": "Polygon", "coordinates": [[[20, 20], [30, 20], [30, 30], [20, 20]]]}, self.B))

    def test_multipolygon_keeps_parts_inside(self):
        g = clip_geometry({"type": "MultiPolygon", "coordinates": [[[[1, 1], [2, 1], [2, 2], [1, 1]]], [[[20, 20], [21, 20], [21, 21], [20, 20]]],
                                                                  [[[8, 8], [12, 8], [12, 9], [8, 8]]]]}, self.B)
        self.assertEqual(g["type"], "MultiPolygon")
        self.assertEqual(len(g["coordinates"]), 2)

    def test_line_splits_into_parts(self):
        g = clip_geometry({"type": "LineString", "coordinates": [[-5, 5], [5, 5], [5, 15], [8, 15], [8, 5], [15, 5]]}, self.B)
        self.assertEqual(g, {"type": "MultiLineString", "coordinates": [[[0, 5], [5, 5], [5, 10]], [[8, 10], [8, 5], [10, 5]]]})

    def test_line_crossing_corner_to_corner(self):
        g = clip_geometry({"type": "LineString", "coordinates": [[-10, -10], [20, 20]]}, self.B)
        self.assertEqual(g["coordinates"], [[0, 0], [10, 10]])

    def test_points_filtered(self):
        self.assertEqual(clip_geometry({"type": "MultiPoint", "coordinates": [[1, 1], [11, 1]]}, self.B)["coordinates"], [[1, 1]])
        self.assertIsNone(clip_geometry({"type": "Point", "coordinates": [11, 1]}, self.B))


if __name__ == "__main__":
    unittest.main()
