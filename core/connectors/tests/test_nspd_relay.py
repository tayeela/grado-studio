"""Проверяет переключение НСПД на релей (GRADO_NSPD_BASE, токен) и загрузку файлов сертификатов.

Без сети: запросы подменены; токен и сертификат в тесте — тестовые заглушки.
Запуск: python -m unittest discover -s core/connectors/tests (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import json
import os
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _paths  # noqa: F401
from grado_connectors import ConnectorError, netutil
from grado_connectors import nspd

TOKEN = "t0ken-for-tests-0123456789abcdef"
RELAY = "https://relay.example.test"


class _Resp:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self, n=-1):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _env(**kw):
    base = {k: v for k, v in os.environ.items()
            if k not in ("GRADO_NSPD_BASE", "GRADO_NSPD_RELAY_TOKEN")}
    base.update(kw)
    return mock.patch.dict(os.environ, base, clear=True)


class Relay(unittest.TestCase):
    def test_default_is_nspd(self):
        with _env():
            self.assertEqual(nspd._base_url(), "https://nspd.gov.ru")
            self.assertEqual(nspd._intersects_url(), nspd.INTERSECTS_URL)
            self.assertEqual(nspd._relay_headers(nspd._base_url()), {})

    def test_base_replaces_host(self):
        with _env(GRADO_NSPD_BASE=RELAY + "/"):
            self.assertEqual(nspd._base_url(), RELAY)
            self.assertEqual(nspd._intersects_url(),
                             RELAY + "/api/geoportal/v1/intersects?typeIntersect=fullObject")

    def test_bad_base_rejected(self):
        for bad in ("http://relay.example.test", "relay.example.test",
                    RELAY + "/api", RELAY + "?x=1"):
            with _env(GRADO_NSPD_BASE=bad):
                with self.assertRaises(ConnectorError) as cm:
                    nspd._base_url()
                cm.exception.args[0].encode("ascii")      # правило 4: только ASCII

    def test_token_goes_only_to_relay(self):
        with _env(GRADO_NSPD_RELAY_TOKEN=TOKEN):          # без релея токен не уходит на nspd.gov.ru
            self.assertEqual(nspd._relay_headers(nspd._base_url()), {})
        with _env(GRADO_NSPD_BASE=RELAY, GRADO_NSPD_RELAY_TOKEN=TOKEN):
            self.assertEqual(nspd._relay_headers(nspd._base_url()),
                             {"X-Grado-Relay-Token": TOKEN})

    def _capture(self, call):
        seen = []

        def fake_open(req, timeout, ctx=None):
            seen.append(req)
            return _Resp({"features": []})
        with mock.patch.object(netutil, "open_url", fake_open):
            call()
        return seen[0]

    def test_post_and_get_carry_token_and_keep_portal_headers(self):
        with _env(GRADO_NSPD_BASE=RELAY, GRADO_NSPD_RELAY_TOKEN=TOKEN):
            req = self._capture(lambda: nspd.NspdDirect()._http_post(
                nspd._intersects_url(), {"geom": {}}))
            self.assertTrue(req.full_url.startswith(RELAY + "/api/geoportal/"))
            self.assertEqual(req.get_header("X-grado-relay-token"), TOKEN)
            self.assertEqual(req.get_header("Referer"), "https://nspd.gov.ru/map")
            req = self._capture(lambda: nspd._http_get(RELAY + nspd.SEARCH_PATH + "?query=1"))
            self.assertEqual(req.get_header("X-grado-relay-token"), TOKEN)
            self.assertEqual(req.get_header("Origin"), "https://nspd.gov.ru")

    def test_without_variables_nothing_changes(self):
        with _env(GRADO_NSPD_RELAY_TOKEN=TOKEN):
            req = self._capture(lambda: nspd._http_get(nspd.SEARCH_URL + "?query=1"))
            self.assertTrue(req.full_url.startswith("https://nspd.gov.ru/"))
            self.assertFalse(req.has_header("X-grado-relay-token"))

    def test_search_uses_base(self):
        urls = []

        def get(url):
            urls.append(url)
            return {"data": {"type": "FeatureCollection", "features": []}}
        with _env(GRADO_NSPD_BASE=RELAY):
            nspd.search_cadastral(["77:01:0001001:1"], transport=get)
        self.assertTrue(urls[0].startswith(RELAY + "/api/geoportal/v2/search/geoportal?"))

    def test_token_not_in_error_message(self):
        import urllib.error
        with _env(GRADO_NSPD_BASE=RELAY, GRADO_NSPD_RELAY_TOKEN=TOKEN):
            with mock.patch.object(netutil, "open_url",
                                   side_effect=urllib.error.URLError("boom")):
                with self.assertRaises(Exception) as cm:
                    nspd._http_get(RELAY + nspd.SEARCH_PATH + "?query=1")
        self.assertNotIn(TOKEN, str(cm.exception))


class CertFiles(unittest.TestCase):
    def test_cer_extension_accepted_and_help_names_current(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            ca = home / ".grado2" / "ca"
            ca.mkdir(parents=True)
            for n in ("a.cer", "b.crt", "c.pem", "d.txt"):
                (ca / n).write_bytes(b"x")
            with mock.patch.object(Path, "home", return_value=home), _env():
                names = {p.name for p in nspd._extra_ca_files()}
        self.assertTrue({"a.cer", "b.crt", "c.pem"} <= names)
        self.assertNotIn("d.txt", names)
        self.assertIn("russian_trusted_root_ca.cer", nspd._CERT_HELP)
        self.assertNotIn("_pem.crt", nspd._CERT_HELP)

    def test_der_and_pem_both_load(self):
        # самоподписанный тестовый корень: DER-файл и тот же в PEM должны грузиться в контекст
        pem = _TEST_PEM
        der = ssl.PEM_cert_to_DER_cert(pem)
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            ca = home / ".grado2" / "ca"
            ca.mkdir(parents=True)
            (ca / "root.cer").write_bytes(der)
            with mock.patch.object(Path, "home", return_value=home), _env(GRADO_NSPD_CA=""):
                ctx_der = nspd._ssl_context()
            (ca / "root.cer").write_text(pem)
            with mock.patch.object(Path, "home", return_value=home), _env(GRADO_NSPD_CA=""):
                ctx_pem = nspd._ssl_context()
        for ctx in (ctx_der, ctx_pem):
            subjects = [dict(x[0] for x in c["subject"]).get("commonName")
                        for c in ctx.get_ca_certs()]
            self.assertIn("grado-test-root", subjects)


# Тестовый самоподписанный сертификат CN=grado-test-root (ни к чему не привязан, ключ не сохранён).
_TEST_PEM = """-----BEGIN CERTIFICATE-----
MIIDJzCCAg+gAwIBAgIUBCgU1pycUbmLasZbOQTbTZ7hg3gwDQYJKoZIhvcNAQEL
BQAwGjEYMBYGA1UEAwwPZ3JhZG8tdGVzdC1yb290MCAXDTI2MTAwNzEwMzQxNloY
DzIxMjYwOTEzMTAzNDE2WjAaMRgwFgYDVQQDDA9ncmFkby10ZXN0LXJvb3QwggEi
MA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQCnjCIyYhUm6VC4si3/sE2cTfZg
bmT1JStqq5FLz9JldibaPNxZ4BcnWSWMLQyXJr3XiC41/YT2065E3Ieulh5RK0Gs
dPwK6FxF49bMKnEH97rnUJVu1GsjjX0sV2FzXuv8JP+2Z45z8JvDkrkmgLDSJOJN
k4KWxDzFMxDg6q5aIXx5DU2lfzp8fuy2Ywy73H4eDOWwUwocmp2GXyK2HX08Vuml
Ujg4v+TgRH9sfeJjtQFmkcmkMIzRmYGw7jBYxcZPaOSRVHf25JDCi0wPvuxtXziv
o1rdOtQdu6hN9HKchcnX0/xf3fbaxmbN+In7YUnvvgMT0krKByRAbzFsVtQZAgMB
AAGjYzBhMB0GA1UdDgQWBBQft1rm1KzoFNO1Q8Dw3IYNTmAIBDAfBgNVHSMEGDAW
gBQft1rm1KzoFNO1Q8Dw3IYNTmAIBDAPBgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB
/wQEAwIBBjANBgkqhkiG9w0BAQsFAAOCAQEAEwRugqyv+Pjdg7Pk7wr1FyWWZqZb
QMaMJnnm94+KCR0oqy7T0/vm/g27mr5NCoMaF5OSVv5+5vP/cDgXVcFsP59PDyml
kdRkQ4hBAd0niqoy58GaHT4eJH84+u9EJMIJX+t7a5YZr53XuvxgkX6RcQ+dw3t0
l0Xdn7Mjv7mHCOqYrSM/5s8SRRX0EZXoIH9jmcPqQNB11Ecy4PdjFgIzfzKEw0sx
KHJQzb8VfHzyPT1+ILGAlUuDNdIRhrF9J9b2U+SAxJe97/680uZrajB1YA9rw1Yf
BhY2kX0yK+bHDpMRZ9xJ0tNzGO/MhUJPzvffkj4qmGCGUJbYwZJz9XPraw==
-----END CERTIFICATE-----
"""


if __name__ == "__main__":
    unittest.main()
