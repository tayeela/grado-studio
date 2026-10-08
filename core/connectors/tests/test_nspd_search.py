"""Проверяет поиск НСПД по кадастровым номерам (search_cadastral): разбор, повторы, лимит 20.

Без сети: транспорт подменён функцией, паузы отключены.
Запуск: python -m unittest discover -s core/connectors/tests (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import unittest
import urllib.parse

import _paths  # noqa: F401
from grado_connectors import ConnectorError, crs
from grado_connectors import nspd
from grado_connectors.nspd import _Retryable, normalize_cadastral, search_cadastral

LON, LAT = 37.6, 55.7


def _ring():
    pts = [(LON, LAT), (LON + .001, LAT), (LON + .001, LAT + .001), (LON, LAT)]
    return [list(crs.wgs84_to_merc(x, y)) for x, y in pts]


def _answer(num):
    return {"data": {"type": "FeatureCollection", "features": [{
        "type": "Feature", "id": 1,
        "geometry": {"type": "Polygon", "coordinates": [_ring()]},
        "properties": {"category": 36368, "options": {
            "cad_num": num, "specified_area": 1234.5,
            "permitted_use_established_by_document": "под жилую застройку"}}}]}}


class Search(unittest.TestCase):
    def test_validation(self):
        good, bad = normalize_cadastral("50:27:0000000:126, 77:22:0030223:315\n50:27:0000000:126 abc 1:2:3")
        self.assertEqual(good, ["50:27:0000000:126", "77:22:0030223:315"])
        self.assertEqual(bad, ["abc", "1:2:3"])
        with self.assertRaises(ConnectorError):
            search_cadastral(["garbage"], transport=lambda u: {})

    def test_found_transform_and_props(self):
        urls = []

        def tr(url):
            urls.append(url)
            return _answer("50:27:0000000:126")
        r = search_cadastral(["50:27:0000000:126", "50:27:0000000:126"], transport=tr, sleep=lambda s: None)
        self.assertEqual(len(urls), 1)                                   # дубль не запрашивается
        q = urllib.parse.parse_qs(urllib.parse.urlparse(urls[0]).query)
        self.assertEqual(q, {"query": ["50:27:0000000:126"], "thematicSearchId": ["1"]})
        self.assertEqual(len(r), 1)
        x, y = r[0]["geometry"]["coordinates"][0][0]
        self.assertAlmostEqual(x, LON, 5)
        self.assertAlmostEqual(y, LAT, 5)
        self.assertEqual(r[0]["properties"]["opt_cad_num"], "50:27:0000000:126")
        self.assertEqual(r[0]["properties"]["opt_specified_area"], 1234.5)
        self.assertEqual(r[0]["grado_key"], "50:27:0000000:126")

    def test_missing_and_other_number_ignored(self):
        def tr(url):
            n = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["query"][0]
            return {"data": {"features": []}} if n.endswith(":1") else _answer("77:22:0030223:999")
        r = search_cadastral(["50:27:0000000:1", "77:22:0030223:315"], transport=tr, sleep=lambda s: None)
        self.assertEqual(r, [])                                          # чужой номер в ответе не принимается

    def test_retry_once_then_ok(self):
        calls = []

        def tr(url):
            calls.append(1)
            if len(calls) == 1:
                raise _Retryable("HTTP 502")
            return _answer("50:27:0000000:126")
        r = search_cadastral(["50:27:0000000:126"], transport=tr, sleep=lambda s: None)
        self.assertEqual((len(calls), len(r)), (2, 1))

    def test_three_attempts_then_error_recorded(self):
        calls, errs = [], []

        def tr(url):
            calls.append(1)
            raise _Retryable("HTTP 597")
        r = search_cadastral(["50:27:0000000:126"], transport=tr, sleep=lambda s: None, errors=errs)
        self.assertEqual((r, len(calls), len(errs)), ([], 3, 1))

    def test_cap_20(self):
        calls = []
        nums = [f"50:27:0000000:{i}" for i in range(1, 31)]
        search_cadastral(nums, transport=lambda u: calls.append(u) or {"features": []}, sleep=lambda s: None)
        self.assertEqual(len(calls), nspd.SEARCH_MAX)


if __name__ == "__main__":
    unittest.main()


class Details(unittest.TestCase):
    def test_ascii_digits_only(self):
        good, bad = normalize_cadastral("٥٠:٢٧:٠٠٠٠٠٠٠:١٢٦ 50:27:0000000:126")
        self.assertEqual(good, ["50:27:0000000:126"])
        self.assertEqual(len(bad), 1)

    def test_no_contour_goes_to_nogeom(self):
        def tr(url):
            d = _answer("50:27:0000000:126")
            for f in d["data"]["features"] if "data" in d else d["features"]:
                f["geometry"] = None
            return d
        ng, errs = [], []
        r = search_cadastral(["50:27:0000000:126"], transport=tr, sleep=lambda s: None, errors=errs, nogeom=ng)
        self.assertEqual((r, ng, errs), ([], ["50:27:0000000:126"], []))
