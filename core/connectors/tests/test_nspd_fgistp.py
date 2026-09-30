import json
import os
import ssl
import unittest
import urllib.error
import urllib.parse
from unittest import mock

import _paths  # noqa: F401
from grado_connectors import ConnectorError, FgistpConnector, NspdCapture, nspd
from grado_connectors.nspd import NspdDirect

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


# Протокол v2 (JSP): фикстуры имитируют РЕАЛЬНЫЕ ответы вьюера geomnpn —
# атрибуты лежат в КОРНЕ feature (properties нет), координаты EPSG:3857.
UIN = "4678300002010307202209291"
LAYERS = {"layer_stp_list": [
    {"classid": "603010502", "class_name": "Охранная зона газопроводов",
     "class_title": "ЗОУИТ", "geom_type": "100",
     "stp_name": "Генплан г.о. Химки"},
    {"classid": "601010302", "class_name": "Граница городского округа",
     "class_title": "Границы", "geom_type": "010",
     "stp_name": "Генплан г.о. Химки"},
    {"classid": "603019999", "class_name": "Пустой слой",
     "class_title": "ЗОУИТ", "geom_type": "100",
     "stp_name": "Генплан г.о. Химки"},
]}
# Москва, EPSG:3857 (как отдаёт json_stp_layer_obj_list.jsp)
MERC_TRI = [[4187345.5, 7509247.8], [4187445.5, 7509247.8],
            [4187445.5, 7509347.8], [4187345.5, 7509247.8]]
OBJS_GAS = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "id": "x.1", "naim": "Охранная зона ГРС",
     "globalid": "GUID-1", "tp_stat": 1, "number": "7",
     "geometry": {"type": "Polygon", "coordinates": [MERC_TRI]}},
]}
CATALOG = {"stp_list": [
    {"uin": UIN, "stp_name": "Генплан г.о. Химки", "stp_extent": "x"},
    {"uin": "2" * 25, "stp_name": "Генплан г. Пущино", "stp_extent": "y"},
]}


def fake_transport(url):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if "json_stp_list.jsp" in url:
        return json.dumps(CATALOG).encode()
    if "json_layers_stp_list.jsp" in url:
        assert q["uin"][0] == UIN
        return json.dumps(LAYERS).encode()
    assert "json_stp_layer_obj_list.jsp" in url
    assert q["uin"][0] == UIN and q["reg_code"][0] == "0"
    assert q["st_code"][0] in ("1", "2")
    if q["obj_code"][0] == "603010502" and q["st_code"][0] == "1":
        return json.dumps(OBJS_GAS).encode()
    return json.dumps({"type": "FeatureCollection", "features": []}).encode()


class TestFgistp(unittest.TestCase):
    def setUp(self):
        self.conn = FgistpConnector(transport=fake_transport)

    def test_catalog(self):
        rows = self.conn.catalog()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["uin"], UIN)

    def test_discover(self):
        layers = self.conn.discover(UIN)
        self.assertEqual(len(layers), 3)
        self.assertEqual(layers[0]["classid"], "603010502")

    def test_fetch_converts_and_annotates(self):
        result = self.conn.fetch(UIN)
        self.assertEqual(len(result["features"]), 1)
        f = result["features"][0]
        # ключ — стабильный globalid, а не порядковый номер
        self.assertEqual(f["grado_key"], "GUID-1")
        p = f["properties"]
        self.assertEqual(p["class_name"], "Охранная зона газопроводов")
        self.assertEqual(p["status_name"], "существующий")
        self.assertEqual(p["naim"], "Охранная зона ГРС")
        self.assertEqual(p["uin"], UIN)
        # геометрия сконвертирована 3857 → WGS84 ещё в коннекторе
        lon, lat = f["geometry"]["coordinates"][0][0]
        self.assertAlmostEqual(lon, 37.6155646, places=5)
        self.assertAlmostEqual(lat, 55.7522242, places=5)
        self.assertIn("УИН " + UIN, result["source_doc"])
        self.assertIn("Химки", result["source_doc"])
        self.assertTrue(any("603019999" in n for n in result["notes"]),
                        "пустой слой отмечен в примечаниях")

    def test_fetch_filters_by_classid(self):
        result = self.conn.fetch(UIN, classids={"601010302"})
        self.assertEqual(len(result["features"]), 0)
        self.assertEqual(result["params"]["classids"], ["601010302"])

    def test_objects_url_format(self):
        url = self.conn.objects_url(UIN, "603010502", "100", "2")
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(q["obj_code"][0], "603010502")
        self.assertEqual(q["st_code"][0], "2")
        self.assertEqual(q["geom_type"][0], "100")
        self.assertIn("json_stp_layer_obj_list.jsp", url)

    def test_unknown_geom_type(self):
        with self.assertRaises(ConnectorError):
            self.conn.objects_url(UIN, "60107", geom_type="999")

    def test_no_layers_of_type_noted(self):
        result = self.conn.fetch(UIN, geom_type="001")
        self.assertEqual(result["features"], [])
        self.assertTrue(any("слоёв в документе нет" in n for n in result["notes"]))


class _Resp:
    def __init__(self, body):
        self._b = body

    def read(self, n=-1):
        return self._b if n < 0 else self._b[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _cert_error():
    return urllib.error.URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED"))


class TestNspdCert(unittest.TestCase):
    def setUp(self):
        nspd._insecure_warned = False
        env = {k: v for k, v in os.environ.items() if k != "GRADO_NSPD_INSECURE"}
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)

    def test_cert_failure_raises_without_fallback(self):
        with mock.patch.object(nspd.netutil, "open_url", side_effect=_cert_error()) as m:
            with self.assertRaises(ConnectorError) as cm:
                NspdDirect()._http_post("https://nspd.gov.ru/x", {})
        self.assertEqual(m.call_count, 1, "повтора без проверки быть не должно")
        self.assertIn(".grado2/ca", str(cm.exception))

    def test_insecure_env_uses_unverified_fallback(self):
        ctxs = []

        def fake(req, timeout, ctx):
            ctxs.append(ctx)
            if len(ctxs) == 1:
                raise _cert_error()
            return _Resp(b'{"features": []}')
        with mock.patch.dict(os.environ, {"GRADO_NSPD_INSECURE": "1"}), \
                mock.patch.object(nspd.netutil, "open_url", side_effect=fake), \
                mock.patch("sys.stderr") as err:
            data = NspdDirect()._http_post("https://nspd.gov.ru/x", {})
        self.assertEqual(data, {"features": []})
        self.assertNotEqual(ctxs[0].verify_mode, ssl.CERT_NONE)
        self.assertEqual(ctxs[1].verify_mode, ssl.CERT_NONE)
        self.assertTrue(err.write.called, "предупреждение в stderr")

    def test_extra_ca_skips_bad_files(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".pem") as f:
            f.write("не сертификат")
            f.flush()
            with mock.patch.dict(os.environ, {"GRADO_NSPD_CA": f.name}):
                ctx = nspd._ssl_context()
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_error_text_truncated(self):
        err = urllib.error.URLError("a\nb" + "x" * 500)
        with mock.patch.object(nspd.netutil, "open_url", side_effect=err):
            with self.assertRaises(ConnectorError) as cm:
                NspdDirect()._http_post("https://nspd.gov.ru/x", {})
        self.assertNotIn("\n", str(cm.exception))
        self.assertLess(len(str(cm.exception)), 260)


class TestFgistpBaseUrl(unittest.TestCase):
    def test_https_and_local_http_ok(self):
        FgistpConnector(base_url="https://example.org")
        FgistpConnector(base_url="http://127.0.0.1:8000")
        FgistpConnector(base_url="http://localhost:8000")

    def test_remote_http_and_other_schemes_rejected(self):
        for bad in ("http://example.org", "ftp://example.org", "file:///etc/passwd", "example.org"):
            with self.assertRaises(ConnectorError, msg=bad):
                FgistpConnector(base_url=bad)


if __name__ == "__main__":
    unittest.main()
