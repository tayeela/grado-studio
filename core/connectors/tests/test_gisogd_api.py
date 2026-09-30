"""Коннектор ГИС ОГД по открытому REST API портала.

Ключевая особенность, ради которой существует кэш: портал ИГНОРИРУЕТ bbox и
всегда отдаёт слой целиком (проверено на virtual1742: 3285 объектов и без
bbox, и с bbox 150 м). Поэтому режем по области сами, а слой держим в кэше.
Слой приходит zip-архивом SHP в родных координатах ГИС ОГД (тестовый портал — _shpfix).
"""

import gzip
import io
import json
import struct
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

import _paths  # noqa: F401
from _shpfix import shp_zip
from grado_connectors import ConnectorError, GisogdApi
from grado_connectors import gisogd_api
from grado_connectors.gisogd_api import GISOGD_API_LAYERS, catalog, norm_id


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
        return self.payload if isinstance(self.payload, bytes) else shp_zip(self.payload)


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
            self.assertTrue((Path(td) / "virtual1742.shp.gz").is_file())
            self.assertFalse((Path(td) / "virtual1742.geojson.gz").exists(), "прежний GeoJSON-кэш не пишется")

    def test_line_cache_gives_same_answer(self):
        # второй запрос идёт по построчному кэшу: те же объекты, те же ключи, без сети
        t = FakeTransport()
        with tempfile.TemporaryDirectory() as td:
            conn = GisogdApi(transport=t, cache_dir=td)
            first = conn.fetch(BBOX, "virtual1742")
            self.assertTrue((Path(td) / "virtual1742.shp.lines.gz").is_file())
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

    def test_export_url_asks_shp(self):
        t = FakeTransport()
        GisogdApi(transport=t).fetch(BBOX, "virtual1742")
        self.assertIn("/layers/virtual1742/export/", t.calls[0])
        self.assertIn("format=shp", t.calls[0], "родные координаты ОГД — только в SHP; GeoJSON портала сдвинут на ~7,7 м")

    def test_old_geojson_cache_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            import gzip
            (Path(td) / "virtual1742.geojson.gz").write_bytes(gzip.compress(json.dumps(LAYER).encode()))
            t = FakeTransport()
            GisogdApi(transport=t, cache_dir=td).fetch(BBOX, "virtual1742")
            self.assertEqual(len(t.calls), 1, "слой перекачивается в SHP, старый GeoJSON не берётся")

    def test_dbf_names_back_to_full(self):
        # .dbf режет имена до 10 знаков: naimfunkzo, summfondpe — коннектор возвращает прежние полные имена
        r = GisogdApi(transport=FakeTransport()).fetch(BBOX, "virtual1742")
        p = r["features"][0]["properties"]
        self.assertEqual(p["naimfunkzony"], "жилая зона")
        self.assertEqual(p["summfondpersp"], "440.1")
        self.assertNotIn("naimfunkzo", p)

    def test_coordinates_back_to_wgs84(self):
        r = GisogdApi(transport=FakeTransport()).fetch(BBOX, "virtual1742")
        ring = r["features"][0]["geometry"]["coordinates"][0]
        want = LAYER["features"][0]["geometry"]["coordinates"][0]
        got = {(round(x, 9), round(y, 9)) for x, y in ring}
        self.assertEqual(got, {(round(x, 9), round(y, 9)) for x, y in want})

    def test_broken_payload_raises(self):
        conn = GisogdApi(transport=FakeTransport(payload=b"<html>not a zip</html>"))
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
        from _shpfix import shp_zip
        seen = []
        body = shp_zip({"type": "FeatureCollection", "features": []})
        with tempfile.TemporaryDirectory() as d:
            GisogdApi(transport=lambda url: body, cache_dir=d, progress=lambda *a: seen.append(a)).fetch((0, 0, 1, 1), "x1")
        self.assertEqual(seen, [("x1", len(body), len(body), "parse")])

class _FakeResp:
    """Ответ портала: отдаёт байты кусками; headers как у http.client."""

    def __init__(self, body, gz=False):
        self.body, self.pos = body, 0
        self.headers = {"Content-Encoding": "gzip"} if gz else {}

    def read(self, n=-1):
        n = len(self.body) - self.pos if n is None or n < 0 else n
        chunk = self.body[self.pos:self.pos + n]
        self.pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestLayerCode(unittest.TestCase):
    """Код слоя идёт в URL и имена файлов кэша — проверяется в самом коннекторе."""

    BAD = ["../x", "..", "a/b", "a\\b", ".hidden", "a..b", "", "virtual1742\n", "/etc/passwd", "a b", "c:x", "x\x00y"]

    def test_bad_codes_rejected_before_network_and_disk(self):
        for map_name in ("isogd", "base2"):
            for bad in self.BAD:
                with tempfile.TemporaryDirectory() as td:
                    conn = GisogdApi(transport=lambda *a, **k: self.fail("сеть не должна вызываться"),
                                     cache_dir=td, map_name=map_name)
                    with self.assertRaises(ConnectorError, msg=repr(bad)):
                        conn.fetch(BBOX, bad)
                    self.assertEqual(list(Path(td).iterdir()), [], "ничего не создано в кэше")

    def test_real_layer_codes_match(self):
        codes = [c for spec in GISOGD_API_LAYERS.values() for c in spec["codes"]]
        self.assertTrue(codes)
        for c in codes + ["virtual6", "virtual1742", "layer_12.v2-x"]:
            self.assertEqual(gisogd_api._check_code(c), c)

    def test_cache_child_stays_under_root(self):
        with tempfile.TemporaryDirectory() as td:
            conn = GisogdApi(transport=FakeTransport(), cache_dir=Path(td) / "cache")
            with self.assertRaises(ConnectorError):
                conn._cache_child("virtual1", "../escape.gz")
            self.assertEqual(conn._cache_path("virtual1").parent, Path(td) / "cache")


class TestSizeCaps(unittest.TestCase):
    def test_inflate_respects_room(self):
        bomb = gzip.compress(b"\0" * 5_000_000)
        with self.assertRaises(ConnectorError):
            gisogd_api._inflate(zlib.decompressobj(wbits=31), bomb, 1000)
        ok = gisogd_api._inflate(zlib.decompressobj(wbits=31), bomb, 5_000_000)
        self.assertEqual(len(ok), 5_000_000)

    def test_http_get_gzip_bomb_rejected_without_retries(self):
        resp = _FakeResp(gzip.compress(b"\0" * 5_000_000), gz=True)
        with mock.patch.object(gisogd_api, "open_url", return_value=resp) as m, \
                mock.patch.object(gisogd_api, "_MAX_LAYER", 100_000):
            with self.assertRaises(ConnectorError):
                gisogd_api._http_get("https://gisogd.mos.ru/x")
        self.assertEqual(m.call_count, 1, "превышение потолка не повторяется")

    def test_http_get_plain_over_cap_rejected(self):
        with mock.patch.object(gisogd_api, "open_url", return_value=_FakeResp(b"x" * 500_000)), \
                mock.patch.object(gisogd_api, "_MAX_LAYER", 100_000):
            with self.assertRaises(ConnectorError):
                gisogd_api._http_get("https://gisogd.mos.ru/x")

    def test_http_get_gzip_roundtrip(self):
        payload = b"hello " * 50_000
        with mock.patch.object(gisogd_api, "open_url", return_value=_FakeResp(gzip.compress(payload), gz=True)):
            self.assertEqual(gisogd_api._http_get("https://gisogd.mos.ru/x"), payload)

    def test_http_stream_gzip_bomb_rejected(self):
        resp = _FakeResp(gzip.compress(b"\0" * 5_000_000), gz=True)
        with mock.patch.object(gisogd_api, "open_url", return_value=resp), \
                mock.patch.object(gisogd_api, "_MAX_STREAM", 100_000):
            _total, it = gisogd_api._http_stream("https://gisogd.mos.ru/x")
            with self.assertRaises(ConnectorError):
                list(it)

    def test_stream_build_over_cap_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as td:
            conn = GisogdApi(transport=lambda url, timeout=None: b"\0" * 300_000, cache_dir=td, map_name="base2")
            with mock.patch.object(gisogd_api, "_MAX_STREAM", 100_000):
                with self.assertRaises(ConnectorError):
                    conn.fetch(BBOX, "virtual6")
            self.assertEqual(list(Path(td).iterdir()), [], "ни .zip.part, ни недостроенной сетки")


class TestCorruptArchive(unittest.TestCase):
    """Обрезанная запись в SHP: struct.error/IndexError не выходят наружу сырым текстом."""

    @staticmethod
    def _bad_zip():
        shp = bytearray(100)
        struct.pack_into(">i", shp, 0, 9994)
        struct.pack_into("<i", shp, 32, 1)
        shp += struct.pack(">ii", 1, 2) + struct.pack("<i", 1) + b"\0" * 0   # Point с телом в 4 байта: X,Y нет
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("a.shp", bytes(shp))
        return buf.getvalue()

    def test_isogd_wraps_into_connector_error(self):
        conn = GisogdApi(transport=FakeTransport(self._bad_zip()))
        with self.assertRaises(ConnectorError) as cm:
            conn.fetch(BBOX, "virtual1742")
        self.assertNotIn("unpack", str(cm.exception))
        self.assertIn("повреждён", str(cm.exception))

    def test_base2_stream_wraps_into_connector_error(self):
        with tempfile.TemporaryDirectory() as td:
            conn = GisogdApi(transport=FakeTransport(self._bad_zip()), cache_dir=td, map_name="base2")
            with self.assertRaises(ConnectorError) as cm:
                conn.fetch(BBOX, "virtual6")
            self.assertNotIn("unpack", str(cm.exception))
            self.assertEqual(list(Path(td).iterdir()), [], "недостроенный кэш убран")

    def test_shp_features_indexerror_wrapped(self):
        with mock.patch.object(gisogd_api, "iter_zip", side_effect=IndexError("list index out of range")):
            with self.assertRaises(ConnectorError) as cm:
                list(gisogd_api._shp_features(None, "v1"))
        self.assertNotIn("list index", str(cm.exception))


class TestNetworkErrorText(unittest.TestCase):
    def test_paths_and_newlines_stripped(self):
        err = OSError("fail\n/Users/tayeela/secret/dir/file.tmp\nsecond")
        with mock.patch.object(gisogd_api, "open_url", side_effect=err), mock.patch.object(gisogd_api.time, "sleep"):
            with self.assertRaises(ConnectorError) as cm:
                gisogd_api._http_get("https://gisogd.mos.ru/x")
        msg = str(cm.exception)
        self.assertNotIn("/Users", msg)
        self.assertNotIn("\n", msg)


if __name__ == "__main__":
    unittest.main()


class LongTexts(unittest.TestCase):
    """dBASE режет строки на 254 байтах; полный текст берётся из GeoJSON слоя потоком (OOM сервера 25.09.2026)."""

    VRI = "Размещение жилых домов, " * 40              # ~ 1 000 знаков, в .dbf обрезается

    def layer(self):
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": _poly(37.60, 55.75, 37.61, 55.76), "properties": {"orbis_id": 7, "vri": self.VRI}},
            {"type": "Feature", "geometry": _poly(37.605, 55.752, 37.606, 55.753), "properties": {"orbis_id": 8, "vri": "коротко"}}]}

    def test_full_text_restored_from_geojson_stream_in_small_pieces(self):
        layer = self.layer()
        gj = json.dumps(layer, ensure_ascii=False).encode("utf-8")

        def transport(url, timeout=None):
            return gj if "format=geojson" in url else shp_zip(layer)
        with tempfile.TemporaryDirectory() as td:
            conn = GisogdApi(transport=transport, cache_dir=td)
            # GeoJSON кусками по 7 байт: объекты и русские буквы рвутся посередине
            conn._chunks = lambda url, code: (gj[i:i + 7] for i in range(0, len(gj), 7))
            r = conn.fetch(BBOX, "virtual130")
            by = {f["properties"]["orbis_id"]: f["properties"]["vri"] for f in r["features"]}
            self.assertEqual(by[7], self.VRI)
            self.assertEqual(by[8], "коротко")
            again = GisogdApi(transport=lambda *a, **k: self.fail("второй раз — из кэша"), cache_dir=td).fetch(BBOX, "virtual130")
            self.assertEqual({f["properties"]["orbis_id"]: f["properties"]["vri"] for f in again["features"]}[7], self.VRI)
