"""Яндекс Карты (тайлы vmap3): разбор тайла, сетка EPSG:3395, склейка кусков по id — без сети.

Фикстура — три соседних тайла z18 района Владыкино (углом: здания идут через оба стыка). Эталон yaexport_ref.json
посчитан кодом ~/yandex-hdroads/yaexport.py (to_geom + merge, shapely) и pyproj EPSG:3395 → EPSG:4326.
"""

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _paths  # noqa: F401
from grado_connectors import ConnectorError
from grado_connectors import yandex_vmap as yv

FIX = Path(__file__).parent / "fixtures" / "yandex"
REF = json.loads((FIX / "yaexport_ref.json").read_text("utf-8"))
TILES = [tuple(t) for t in REF["tiles"]]


def blob(x, y):
    return (FIX / f"18_{x}_{y}.pbf").read_bytes()


def metres(lon1, lat1, lon2, lat2):
    return math.hypot((lon2 - lon1) * 111320 * math.cos(math.radians(lat1)), (lat2 - lat1) * 110574)


def tile_bbox(x, y, inset=0.2):
    """Рамка WGS84 внутри тайла (inset — доля от края)."""
    to = yv.tile_to_3395(18, x, y)
    a, b = to(-4096 * (1 - inset), 4096 * (1 - inset)), to(4096 * (1 - inset), -4096 * (1 - inset))
    (w, s), (e, n) = yv.to_lonlat(*a), yv.to_lonlat(*b)
    return (w, s, e, n)


class TestDecode(unittest.TestCase):
    def test_fixture_tiles_parse_and_every_part_is_used(self):
        layers = set()
        for x, y in TILES:
            feats = yv.decode(blob(x, y))          # при расхождении числа частей decode падает
            self.assertTrue(feats)
            layers |= {f["layer"] for f in feats}
        self.assertLessEqual({"building", "road", "hd_road_surface"}, layers)

    def test_truncated_tile_is_an_error(self):
        with self.assertRaises((ValueError, IndexError, ConnectorError)):
            yv.decode(blob(*TILES[0])[:-7])

    def test_empty_tile(self):
        self.assertEqual(yv.decode(b""), [])

    def test_signed_integers_are_zigzag(self):
        # значение атрибута: поле 2, varint 12 → 6; 1 → −1 (z_level подземного уровня)
        self.assertEqual(yv._value(bytes([0x10, 12])), 6)
        self.assertEqual(yv._value(bytes([0x10, 1])), -1)
        # подтверждение на данных: feature_id здания совпадает с id объекта только после раскодирования
        same = [f for x, y in TILES for f in yv.decode(blob(x, y)) if f["layer"] == "building" and f["props"].get("feature_id") == f.get("id")]
        self.assertTrue(same)
        heights = {f["props"]["height"] for x, y in TILES for f in yv.decode(blob(x, y)) if f["layer"] == "building" and "height" in f["props"]}
        self.assertTrue(heights and all(isinstance(h, int) and 0 < h < 150 for h in heights))


class TestGrid(unittest.TestCase):
    def test_edge_4095_is_the_tile_border(self):
        x, y = TILES[0]
        right = yv.tile_to_3395(18, x, y)(4095, 0)
        left_of_next = yv.tile_to_3395(18, x + 1, y)(-4096, 0)
        self.assertAlmostEqual(right[0], left_of_next[0], delta=1e-6)
        bottom = yv.tile_to_3395(18, x, y)(0, 4095)
        top_of_next = yv.tile_to_3395(18, x, y + 1)(0, -4096)
        self.assertAlmostEqual(bottom[1], top_of_next[1], delta=1e-6)
        # без поправки 4095 была бы щель в одну клетку сетки (~1 см)
        self.assertGreater(abs(yv.tile_to_3395(18, x, y)(4094, 0)[0] - left_of_next[0]), 0.01)

    def test_wgs84_against_yaexport_pyproj_to_1cm(self):
        worst = 0.0
        for p in REF["points"]:
            lon, lat = yv.to_lonlat(*yv.tile_to_3395(18, *p["tile"])(p["px"], p["py"]))
            worst = max(worst, metres(lon, lat, p["lon"], p["lat"]))
        self.assertLess(worst, 0.01, f"расхождение с PROJ {worst * 1000:.2f} мм")

    def test_forward_and_back(self):
        for lon, lat in ((37.585, 55.847), (37.3, 55.5), (30.3, 59.9)):
            back = yv.to_lonlat(*yv.lonlat_to_3395(lon, lat))
            self.assertLess(metres(lon, lat, *back), 1e-4)

    def test_tile_range_matches_the_area(self):
        self.assertEqual(len(yv.tile_range((37.576, 55.843, 37.594, 55.852))), 182)
        self.assertEqual(yv.tile_range(tile_bbox(*TILES[0])), [TILES[0]])


class TestMerge(unittest.TestCase):
    def setUp(self):
        self.feats = yv.features_from_tiles([(t, blob(*t)) for t in TILES], ["building", "hd_road_surface", "road"])

    def test_same_objects_and_measures_as_yaexport(self):
        for layer, ref in REF["layers"].items():
            mine = [f for f in self.feats if f["properties"]["grado_layer"] == layer]
            self.assertEqual(len(mine), len(ref), f"{layer}: число объектов")
            field = "Длина, м" if layer == "road" else "Площадь, м²"
            # пары по id и величине: у частей комплекса один id
            a = sorted(((int(f["grado_key"].split(":")[2]), f["properties"][field]), i) for i, f in enumerate(mine))
            b = sorted(((r["id"], r["measure"]), i) for i, r in enumerate(ref))
            total_m, total_r = sum(k[1] for k, _ in a), sum(k[1] for k, _ in b)
            self.assertLess(abs(total_m - total_r) / total_r, 0.005, f"{layer}: сумма {total_m} против {total_r}")
            for (ka, ia), (kb, ib) in zip(a, b):
                self.assertEqual(ka[0], kb[0])
                self.assertAlmostEqual(ka[1], kb[1], delta=max(0.2, kb[1] * 0.002))
                g, rb = mine[ia]["geometry"], ref[ib]["bounds"]
                flat = [p for part in g["coordinates"] for ring in (part if g["type"] == "MultiPolygon" else [part]) for p in ring]
                lo = (min(p[0] for p in flat), min(p[1] for p in flat))
                hi = (max(p[0] for p in flat), max(p[1] for p in flat))
                self.assertLess(metres(*lo, rb[0], rb[1]), 0.01)
                self.assertLess(metres(*hi, rb[2], rb[3]), 0.01)

    def test_pieces_become_one_multipolygon(self):
        by_id = {}
        for f in self.feats:
            if f["properties"]["grado_layer"] == "building":
                by_id.setdefault(f["grado_key"], f)
        spread = [f for f in by_id.values() if len(f["geometry"]["coordinates"]) > 1]
        self.assertTrue(spread, "в фикстуре есть здания через стык тайлов")
        for f in spread:
            self.assertEqual(f["geometry"]["type"], "MultiPolygon")
            for part in f["geometry"]["coordinates"]:
                self.assertEqual(part[0][0], part[0][-1], "кольцо замкнуто")

    def test_keys_and_attributes(self):
        keys = [f["grado_key"] for f in self.feats]
        self.assertEqual(len(keys), len(set(keys)), "ключи уникальны")
        b = next(f for f in self.feats if f["properties"]["grado_layer"] == "building")
        self.assertTrue(b["grado_key"].startswith("yandex:building:"))
        self.assertIn("height", b["properties"])
        self.assertIn("ft_type_name", b["properties"])
        self.assertGreater(b["properties"]["Площадь, м²"], 0)

    def test_service_layers_never_exported(self):
        f = yv.features_from_tiles([(t, blob(*t)) for t in TILES], ["land", "hd_road_interchange", "building"])
        self.assertEqual({x["properties"]["grado_layer"] for x in f}, {"building"})

    def test_bbox_keeps_objects_that_touch_it(self):
        box = tile_bbox(*TILES[0], inset=0.45)
        f = yv.features_from_tiles([(t, blob(*t)) for t in TILES], ["building", "road"], bbox=box)
        self.assertTrue(0 < len(f) < len(self.feats))


class FakeTransport:
    def __init__(self, fail=0):
        self.calls, self.fail = [], fail

    def __call__(self, url, timeout=None):
        self.calls.append(url)
        if self.fail:
            self.fail -= 1
            raise OSError("сеть")
        q = dict(p.split("=") for p in url.split("?")[1].split("&"))
        path = FIX / f"{q['z']}_{q['x']}_{q['y']}.pbf"
        return path.read_bytes() if path.exists() else b""


class TestFetch(unittest.TestCase):
    def setUp(self):
        self.sleep = mock.patch.object(yv.time, "sleep", lambda s: None)
        self.sleep.start()

    def tearDown(self):
        self.sleep.stop()

    def test_cache_on_disk_second_time_without_network(self):
        box = tile_bbox(*TILES[0])
        with tempfile.TemporaryDirectory() as d:
            t = FakeTransport()
            first = yv.YandexVmap(transport=t, cache_dir=d, pause=0).fetch(box, ["building"])
            self.assertEqual(len(t.calls), 1)
            self.assertIn("Referer", str(yv.HEADERS))
            self.assertTrue((Path(d) / f"18_{TILES[0][0]}_{TILES[0][1]}.pbf").exists())
            t2 = FakeTransport()
            second = yv.YandexVmap(transport=t2, cache_dir=d, pause=0).fetch(box, ["building"])
            self.assertEqual(t2.calls, [])
            self.assertEqual([f["grado_key"] for f in first["features"]], [f["grado_key"] for f in second["features"]])
            self.assertIn("с диска", second["notes"][0])
            self.assertEqual(second["crs"], "EPSG:4326")
            # устаревший тайл качается заново
            t3 = FakeTransport()
            yv.YandexVmap(transport=t3, cache_dir=d, pause=0, ttl=-1).fetch(box, ["building"])
            self.assertEqual(len(t3.calls), 1)

    def test_retries_then_error(self):
        box = tile_bbox(*TILES[0])
        ok = yv.YandexVmap(transport=FakeTransport(fail=2), pause=0).fetch(box, ["building"])
        self.assertTrue(ok["features"])
        with self.assertRaises(ConnectorError):
            yv.YandexVmap(transport=FakeTransport(fail=9), pause=0).fetch(box, ["building"])

    def test_progress_counts_tiles(self):
        seen = []
        yv.YandexVmap(transport=FakeTransport(), pause=0, progress=lambda got, total: seen.append((got, total))).fetch(tile_bbox(*TILES[0]), ["road"])
        self.assertEqual(seen[-1], (1, 1))


if __name__ == "__main__":
    unittest.main()
