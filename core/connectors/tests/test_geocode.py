"""Проверяет модуль geocode: поиск адреса через Nominatim (паузы, кэш, повторы, ошибки).

Без сети: транспорт и часы подменены (класс Fake).
Запуск: python -m unittest discover -s core/connectors/tests (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import json
import unittest
import urllib.parse

import _paths  # noqa: F401
from grado_connectors import ConnectorError
from grado_connectors import geocode as G

ITEM = {"name": "Вороново", "display_name": "Вороново, Москва, Россия", "lon": "37.1", "lat": "55.3",
        "boundingbox": ["55.2", "55.4", "37.0", "37.2"], "addresstype": "village"}


class Fake:
    """Часы и сон под контролем теста; sleep двигает часы."""
    def __init__(self, answers):
        self.t, self.answers, self.calls, self.sleeps = 100.0, list(answers), [], []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s

    def transport(self, url, headers):
        self.calls.append((self.t, url, headers))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    def geocoder(self):
        return G.Geocoder(self.transport, self.clock, self.sleep, wall=self.clock)


def ok(*items):
    return 200, json.dumps(list(items)).encode()


class Geocode(unittest.TestCase):
    def test_parse_bbox_and_params(self):
        f = Fake([ok(ITEM)])
        r = f.geocoder().geocode("Вороново")
        self.assertEqual(r, [{"name": "Вороново", "display": "Вороново, Москва, Россия", "lon": 37.1, "lat": 55.3,
                              "bbox": [37.0, 55.2, 37.2, 55.4], "kind": "village"}])
        _, url, h = f.calls[0]
        for part in ("format=jsonv2", "bounded=1", "countrycodes=ru", "limit=8", "accept-language=ru"):
            self.assertIn(part, url)
        self.assertTrue(h["User-Agent"].startswith("GRADO2/"))

    def test_rate_limit_waits(self):
        f = Fake([ok(ITEM), ok(ITEM)])
        g = f.geocoder()
        g.geocode("a")
        f.t += 0.3
        g.geocode("b")
        self.assertEqual(len(f.sleeps), 1)
        self.assertGreaterEqual(f.calls[1][0] - f.calls[0][0], 1.0)

    def test_cache(self):
        f = Fake([ok(ITEM)])
        g = f.geocoder()
        g.geocode("Вороново")
        g.geocode("  вороново ")
        self.assertEqual(len(f.calls), 1)
        f.t += G.CACHE_SEC + 1
        f.answers += [ok(), ok()]                       # пусто в Москве — второй запрос по области, тоже пусто
        self.assertEqual(g.geocode("Вороново"), [])
        self.assertEqual(len(f.calls), 3)

    def test_moscow_first_then_region(self):
        f = Fake([ok(ITEM)])
        g = f.geocoder()
        g.geocode("Вороново")
        self.assertEqual(len(f.calls), 1)                   # нашлось в Москве — область не спрашиваем
        self.assertIn("viewbox=" + urllib.parse.quote(G.VIEWBOX_MSK), f.calls[0][1])
        f2 = Fake([ok(), ok(ITEM)])
        self.assertEqual(len(f2.geocoder().geocode("Покров")), 1)
        self.assertEqual(len(f2.calls), 2)
        self.assertIn("viewbox=" + urllib.parse.quote(G.VIEWBOX), f2.calls[1][1])

    def test_retry_then_ok_respects_interval(self):
        f = Fake([(429, b""), (503, b""), ok(ITEM)])
        self.assertEqual(len(f.geocoder().geocode("x")), 1)
        ts = [c[0] for c in f.calls]
        self.assertTrue(all(b - a >= 1.0 for a, b in zip(ts, ts[1:])))

    def test_errors(self):
        f = Fake([(429, b"")] * 4)
        with self.assertRaises(ConnectorError):
            f.geocoder().geocode("x")
        self.assertEqual(len(f.calls), 4)
        for ans in ((403, b""), (200, b"<html>"), (200, b"{}")):
            with self.assertRaises(ConnectorError):
                Fake([ans]).geocoder().geocode("x")
        g = Fake([ConnectorError("net")]).geocoder()
        with self.assertRaises(ConnectorError):
            g.geocode("x")
        self.assertEqual(g.cache, {})                       # сбой не кэшируется

    def test_query_clean(self):
        self.assertEqual(G.clean_query("a\x00b\n\tc"), "a b c")
        for bad in ("", " \x01 ", "я" * 201):
            with self.assertRaises(ValueError):
                G.clean_query(bad)
        G.clean_query("я" * 200)


if __name__ == "__main__":
    unittest.main()


class Limits(unittest.TestCase):
    def test_cache_and_failure_cache_do_not_need_the_lock(self):
        f = Fake([ok(ITEM)] + [(503, b"")] * 8)
        g = f.geocoder()
        self.assertTrue(g.geocode("Вороново"))
        with self.assertRaises(ConnectorError):
            g.geocode("Тестовая")
        n = len(f.calls)
        g.lock.acquire()
        try:
            self.assertTrue(g.geocode("вороново"))                # кэш при занятом замке
            with self.assertRaises(ConnectorError):
                g.geocode("тестовая")                             # недавний сбой — сразу, сеть не трогаем
        finally:
            g.lock.release()
        self.assertEqual(len(f.calls), n)
        f.t += G.FAIL_SEC + 1                                     # срок сбоя вышел: снова идём в сеть
        with self.assertRaises(ConnectorError):
            g.geocode("Тестовая")
        self.assertGreater(len(f.calls), n)

    def test_lock_timeout_raises_busy(self):
        g = Fake([]).geocoder()
        g.lock.acquire()
        try:
            with self.assertRaises(G.Busy):
                g.geocode("Новый запрос", lock_timeout=0.1)
        finally:
            g.lock.release()
