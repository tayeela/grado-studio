"""Поиск адреса через OpenStreetMap Nominatim (решение владельца 01.10.2026).

Правила политики Nominatim: не чаще 1 запроса в секунду на весь сервер (общий замок + метка времени), узнаваемый
User-Agent, поиск только по явному запросу (без автодополнения), ответы кэшируются. Только Москва и область.
"""
import json
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request

from .contract import ConnectorError
from .netutil import open_url, read_capped

URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "GRADO2/0.88 (urban planning workspace; contact: owner)"
MIN_INTERVAL = 1.1            # с между запросами к Nominatim (политика: не чаще 1 в секунду; запас на дрожание)
CACHE_SEC = 24 * 3600
CACHE_MAX = 500
FAIL_SEC = 45                 # сбой портала помним столько секунд: повторный поиск отвечает сразу
LOCK_TIMEOUT = 20             # сколько ждать очереди к Nominatim, потом Busy
QUERY_MAX = 200
LIMIT = 8
RETRIES = 3                   # повторов после первой попытки при 429/5xx
VIEWBOX_MSK = "36.8,56.1,38.0,55.1"   # сначала Москва в границах с ТиНАО: left,top,right,bottom
VIEWBOX = "35.1,57.0,40.3,54.2"       # ничего в Москве — Московская область (рамка с запасом)
_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f]+")


class Busy(Exception):
    """Очередь к сервису занята дольше LOCK_TIMEOUT: ответ сервера 503, а не бесконечное ожидание."""


def clean_query(q):
    """Управляющие символы -> пробел, пробелы схлопнуты. Пустая строка и длиннее QUERY_MAX -> ValueError (ASCII)."""
    q = " ".join(_CTRL.sub(" ", str(q or "")).split())
    if not q:
        raise ValueError("empty query")
    if len(q) > QUERY_MAX:
        raise ValueError(f"query longer than {QUERY_MAX} characters")
    return q


def _default_transport(url, headers, timeout=20):
    """(url, headers) -> (код, тело). Сетевой сбой -> ConnectorError."""
    import certifi
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(cafile=certifi.where())
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    req = urllib.request.Request(url, headers=headers)
    try:
        with open_url(req, timeout, ctx) as r:
            return r.status, read_capped(r, 4 * 2**20)
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (OSError, ConnectorError) as e:
        raise ConnectorError(f"Nominatim: сбой сети ({e})") from e


class Geocoder:
    def __init__(self, transport=None, clock=time.monotonic, sleep=time.sleep, wall=time.time):
        self.transport = transport or _default_transport
        self.clock, self.sleep, self.wall = clock, sleep, wall
        self.lock = threading.Lock()          # один запрос к Nominatim за раз, и пауза между ними — под этим же замком
        self.last = None                      # момент последнего запроса (по clock)
        self.cache = {}                       # ключ -> (время wall, результаты)
        self.fails = {}                       # ключ -> (время wall, текст сбоя): мёртвый сервис не долбим повторами

    def _wait(self, extra=0.0):
        """Под замком: выдержать MIN_INTERVAL (и extra) с момента прошлого запроса."""
        if self.last is not None:
            need = max(MIN_INTERVAL, extra) - (self.clock() - self.last)
            if need > 0:
                self.sleep(need)
        self.last = self.clock()

    def _hit(self, key):
        """Кэш без замка: готовый ответ или повтор недавнего сбоя (ConnectorError) — к сети не идём."""
        now = self.wall()
        hit = self.cache.get(key)
        if hit and now - hit[0] <= CACHE_SEC:
            return [dict(r) for r in hit[1]]
        bad = self.fails.get(key)
        if bad and now - bad[0] <= FAIL_SEC:
            raise ConnectorError(bad[1])
        return None

    def geocode(self, query, lock_timeout=LOCK_TIMEOUT):
        q = clean_query(query)
        key = q.casefold()
        got = self._hit(key)                  # кэш и недавний сбой — до замка: занятый замок их не задерживает
        if got is not None:
            return got
        if not self.lock.acquire(timeout=lock_timeout):
            raise Busy("geocoder busy")
        try:
            got = self._hit(key)              # пока ждали замок, тот же запрос мог уже отработать
            if got is not None:
                return got
            now = self.wall()
            for k in [k for k, v in self.cache.items() if now - v[0] > CACHE_SEC]:
                del self.cache[k]
            for k in [k for k, v in self.fails.items() if now - v[0] > FAIL_SEC]:
                del self.fails[k]
            try:
                # «Вороново» есть и во Владимирской области: сначала ищем в Москве, и только если там пусто — по области
                res = self._fetch(q, VIEWBOX_MSK) or self._fetch(q, VIEWBOX)
            except ConnectorError as e:
                if len(self.fails) >= CACHE_MAX:
                    self.fails.pop(min(self.fails, key=lambda k: self.fails[k][0]))
                self.fails[key] = (self.wall(), str(e))
                raise
            if len(self.cache) >= CACHE_MAX:
                self.cache.pop(min(self.cache, key=lambda k: self.cache[k][0]))
            self.cache[key] = (self.wall(), res)
            return [dict(r) for r in res]
        finally:
            self.lock.release()

    def _fetch(self, q, viewbox):
        """Один поиск в рамке (под self.lock): повторы при 429/5xx, общий лимит 1 запрос в секунду."""
        params = {"format": "jsonv2", "q": q, "accept-language": "ru", "countrycodes": "ru", "viewbox": viewbox,
                  "bounded": "1", "limit": str(LIMIT), "addressdetails": "0"}
        url = URL + "?" + urllib.parse.urlencode(params)
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Language": "ru"}
        code, body = None, b""
        for attempt in range(RETRIES + 1):
            self._wait(2.0 * attempt)
            code, body = self.transport(url, headers)
            if code == 200:
                break
            if code != 429 and not 500 <= code < 600:
                raise ConnectorError(f"Nominatim: ответ {code}")
        else:
            raise ConnectorError(f"Nominatim: ответ {code} после {RETRIES + 1} попыток")
        return parse(body)


def parse(body):
    try:
        data = json.loads(body)
    except ValueError as e:
        raise ConnectorError("Nominatim: ответ не JSON") from e
    if not isinstance(data, list):
        raise ConnectorError("Nominatim: неожиданный ответ")
    out = []
    for it in data:
        try:
            lon, lat = float(it["lon"]), float(it["lat"])
            bb = it.get("boundingbox")
            if bb:
                s, n, w, e = (float(v) for v in bb)           # Nominatim: [south, north, west, east]
                bbox = [w, s, e, n]
            else:
                bbox = [lon, lat, lon, lat]
        except (KeyError, TypeError, ValueError):
            continue
        display = str(it.get("display_name") or "")
        name = str(it.get("name") or "") or display.split(",")[0].strip()
        kind = str(it.get("addresstype") or it.get("type") or it.get("category") or "")
        out.append({"name": name, "display": display, "lon": lon, "lat": lat, "bbox": bbox, "kind": kind})
    return out


_DEFAULT = Geocoder()


def geocode(query):
    """Адрес/место -> [{name, display, lon, lat, bbox:[w,s,e,n], kind}] (до 8). ValueError — плохой запрос,
    ConnectorError — Nominatim не ответил."""
    return _DEFAULT.geocode(query)
