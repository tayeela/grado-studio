"""Коннектор OSM (Overpass API) — прямая выгрузка векторов по экстенту.

Открытые данные, авторизация не нужна. Запрос собирается только из
выбранных наборов (дороги/здания/землепользование/вода) одним обращением
к Overpass; ответ `out geom` несёт координаты прямо в way — без второй
фазы резолва узлов. Локальный однопользовательский инструмент = «лёгкое
использование» по политике Overpass; лимит площади держит фронт+сервер.
"""

import json
import threading
import time
import ssl
import urllib.error
import urllib.parse
import urllib.request

from . import netutil
from .contract import Connector, ConnectorError, make_result

# Основной инстанс + публичные зеркала: при 429/504 (перегрузка) пробуем
# следующее — прозрачно для пользователя.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
_UA = "grado-studio/0.1 (local single-user desktop tool for urban planning)"

# Наборы данных: ключ → перечень way-селекторов Overpass. Ключи повторяют
# EXTENT_SOURCES студии (osm.<ключ>). Selector'ы без bbox — он подставляется
# при сборке запроса.
OSM_SETS = {
    "roads": ['way["highway"]'],
    # здания с внутренним двором в OSM — мультиполигон-relation, у его контуров тега building нет
    "buildings": ['way["building"]', 'relation["building"]["type"="multipolygon"]'],
    "landuse": ['way["landuse"]',
                'way["leisure"~"^(park|garden|pitch|playground)$"]',
                'way["natural"~"^(wood|scrub|grassland|heath)$"]',
                # крупные парки/леса/промзоны в OSM — мультиполигон-relation
                # (часто с вырезами-островами), а не way; без этих строк они
                # терялись (та же причина, что у воды выше)
                'relation["landuse"]',
                'relation["leisure"~"^(park|garden|pitch|playground)$"]',
                'relation["natural"~"^(wood|scrub|grassland|heath)$"]'],
    "water": ['way["natural"="water"]',
              'way["water"]',
              'way["waterway"~"^(riverbank|dock|canal)$"]',
              # крупная вода (реки/пруды с островами) в OSM — мультиполигон-
              # relation, а не way; без этих строк Москва-река и т.п. терялись
              'relation["natural"="water"]',
              'relation["water"]',
              'relation["waterway"="riverbank"]'],
    # админ-границы — только relation (границы в OSM = отношения из ways-
    # сегментов). Уровни 6 (районы области / городские округа) и 8 (районы
    # Москвы / поселения / города) — рабочий масштаб градпроектирования;
    # уровень 4 (весь субъект) намеренно исключён — гигантская геометрия,
    # вешает Overpass.
    "boundaries": ['relation["boundary"="administrative"]'
                   '["admin_level"~"^(6|8)$"]'],
    # социальные объекты для радиусов обслуживания: точки (узел или центр контура)
    "social": ['nwr["amenity"~"^(school|kindergarten|clinic|hospital|doctors|pharmacy)$"]'],
}
_SOCIAL = {"school", "kindergarten", "clinic", "hospital", "doctors", "pharmacy"}

# Замкнутые наборы становятся полигонами; дороги остаются линиями. Границы —
# кольца (контур адм. единицы), но на холсте рисуются без заливки.
_RING_SETS = {"buildings", "landuse", "water", "boundaries"}


def _in_ring(pt, ring):
    x, y, inside = pt[0], pt[1], False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _assemble_rings(segments):
    """Сшить member-way мультиполигона в замкнутые кольца по совпадающим
    концам (общие узлы OSM в ответе имеют идентичные координаты). Внешняя
    граница мультиполигона часто разбита на десятки way — их надо соединить
    в замкнутые контуры, иначе каждый кусок стал бы мусорным полигоном."""
    segs = [list(s) for s in segments if s and len(s) >= 2]
    rings = []
    while segs:
        ring = segs.pop(0)
        changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for i, s in enumerate(segs):
                if s[0] == ring[-1]:
                    ring += s[1:]; segs.pop(i); changed = True; break
                if s[-1] == ring[-1]:
                    ring += s[-2::-1]; segs.pop(i); changed = True; break
                if s[-1] == ring[0]:
                    ring = s[:-1] + ring; segs.pop(i); changed = True; break
                if s[0] == ring[0]:
                    ring = s[::-1][:-1] + ring; segs.pop(i); changed = True; break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
    return rings

# Теги, уходящие в атрибуты холста (шум вроде source=* отбрасывается).
_KEEP_TAGS = ("highway", "name", "building", "building:levels", "landuse",
              "leisure", "natural", "water", "waterway", "surface", "lanes",
              "boundary", "admin_level", "amenity", "railway")


def _which_set(tags):
    if tags.get("boundary") == "administrative" and "admin_level" in tags:
        return "boundaries"
    if "building" in tags:
        return "buildings"
    if "highway" in tags:
        return "roads"
    if ("natural" in tags and tags["natural"] == "water") \
            or "water" in tags or "waterway" in tags:
        return "water"
    if "landuse" in tags or "leisure" in tags or "natural" in tags:
        return "landuse"
    return None


def _point_of(el):
    """Точка объекта: узел — сам, контур — среднее его вершин, отношение — среднее вершин членов."""
    if el.get("type") == "node" and "lon" in el:
        return [el["lon"], el["lat"]]
    pts = [[g["lon"], g["lat"]] for g in el.get("geometry") or []] or \
        [[g["lon"], g["lat"]] for m in el.get("members") or [] for g in m.get("geometry") or []]
    if not pts:
        return None
    return [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]


def _bbox_hits(geom, bb):
    """Пересекает ли габарит геометрии прямоугольник (запад, юг, восток, север)."""
    xs, ys = [], []

    def walk(c):
        if c and isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for x in c:
                walk(x)
    walk(geom.get("coordinates") or [])
    return bool(xs) and min(xs) <= bb[2] and max(xs) >= bb[0] and min(ys) <= bb[3] and max(ys) >= bb[1]


class _OverpassCache:
    """Ответы Overpass на диске: <папка>/index.json + <имя>.json.gz. Замок общий на папку (сервер создаёт
    коннектор на каждый запрос), файлы пишутся через свой временный файл — две вкладки не портят кэш."""

    KEEP = 40                         # не больше стольких ответов, старые вытесняются
    _LOCKS = {}

    def __init__(self, folder):
        import threading
        from pathlib import Path
        self.dir = Path(folder)
        self.lock = self._LOCKS.setdefault(str(self.dir.resolve()), threading.Lock())

    def _index(self):
        try:
            return json.loads((self.dir / "index.json").read_text("utf-8"))
        except (OSError, ValueError):
            return []

    def _write(self, name, data):
        import os
        import tempfile
        fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".part")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, self.dir / name)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def find(self, bbox, sets, max_age):
        import gzip
        import os
        import zlib
        now, eps = time.time(), 1e-7
        with self.lock:
            for e in sorted(self._index(), key=lambda e: -e["t"]):
                b = e["bbox"]
                if now - e["t"] > max_age or not set(sets) <= set(e["sets"]):
                    continue
                if b[0] - eps <= bbox[0] and b[1] - eps <= bbox[1] and b[2] + eps >= bbox[2] and b[3] + eps >= bbox[3]:
                    try:
                        name = os.path.basename(str(e["file"]))   # имя из index.json — только файл в папке кэша
                        if name != e["file"] or not name.endswith(".json.gz"):
                            continue
                        with gzip.open(self.dir / name, "rt", encoding="utf-8") as f:
                            return json.load(f), e["t"]
                    except (OSError, ValueError, EOFError, zlib.error):
                        continue
        return None

    def put(self, bbox, sets, data):
        """Сбой кэша не должен ронять выгрузку: ответ Overpass уже есть, он просто не запомнится."""
        import gzip
        import uuid
        try:
            with self.lock:
                self.dir.mkdir(parents=True, exist_ok=True)
                idx = self._index()
                name = f"{uuid.uuid4().hex}.json.gz"
                self._write(name, gzip.compress(json.dumps(data).encode("utf-8")))
                idx.append({"bbox": list(bbox), "sets": sorted(sets), "t": time.time(), "file": name})
                idx.sort(key=lambda e: -e["t"])
                keep = idx[:self.KEEP]
                self._write("index.json", json.dumps(keep).encode("utf-8"))
                live = {e["file"] for e in keep}
                for f in self.dir.glob("*.json.gz"):     # вытесненные и осиротевшие ответы
                    if f.name not in live:
                        f.unlink(missing_ok=True)
        except OSError:
            pass


# Правила порталов (CLAUDE.md): пауза, не больше 3 попыток, ожидание растёт вдвое (2 с, 4 с). Повторяются перегрузка зеркала
# (429/502/503/504) и обрыв по времени/сети; прочие коды и «runtime error» (нехватка памяти — область слишком большая) — сразу отказ.
RETRY_CODES = (429, 502, 503, 504)
ATTEMPTS = 3


def retry_wait(attempt):
    """Пауза после неудачной попытки с номером attempt (с нуля): 2 с, 4 с, 8 с…"""
    return 2 * 2 ** attempt


def _is_timeout(e):
    return isinstance(e, TimeoutError) or (isinstance(e, urllib.error.URLError) and isinstance(e.reason, TimeoutError))


def post_with_retry(url, data, ctx, sleep=time.sleep, cancel=None):
    """cancel — threading.Event: зеркало, проигравшее гонку, больше не повторяет запросы."""
    for attempt in range(ATTEMPTS):
        if cancel is not None and cancel.is_set():
            raise ConnectorError("Overpass: запрос отменён")
        req = urllib.request.Request(url, data=data, headers={"User-Agent": _UA})
        try:
            with netutil.open_url(req, 60, ctx) as r:
                d = json.loads(netutil.read_capped(r).decode("utf-8"))
            # таймаут или нехватка памяти Overpass приходят как 200 с неполным ответом — это отказ, не данные
            if "runtime error" in (d.get("remark") or ""):
                raise ConnectorError("Overpass: " + d["remark"][:200])
            return d
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_CODES:
                raise
            failure = e
        except (urllib.error.URLError, TimeoutError) as e:
            if not _is_timeout(e):             # SSL, сертификат, отказ соединения — повтор не поможет
                raise
            failure = e
        if attempt < ATTEMPTS - 1:
            if cancel is not None:
                cancel.wait(retry_wait(attempt))
            else:
                sleep(retry_wait(attempt))
    raise failure


class OsmOverpass(Connector):
    name = "osm"
    source = "osm"

    def __init__(self, transport=None, cache_dir=None, fresh_s=24 * 3600, stale_s=90 * 24 * 3600):
        """cache_dir — папка дискового кэша ответов Overpass (None — без кэша).

        Ответ моложе fresh_s отдаётся с диска без запроса; если зеркала не
        ответили, берётся и более старый, но не старше stale_s — с пометкой.
        Кэш с бо́льшей областью и не меньшим составом наборов покрывает запрос.
        """
        self.transport = transport or self._http_post
        self.cache = _OverpassCache(cache_dir) if cache_dir else None
        self.fresh_s, self.stale_s = fresh_s, stale_s

    def _http_post(self, query):
        """Запрос сразу ко всем зеркалам, берём первый годный ответ.

        Зеркала Overpass отвечают через раз: одно висит минуту, другое отдаёт
        504, третье — за 5 секунд. По очереди это давало до трёх минут
        ожидания и пустой результат; гонка ограничивает ожидание самым быстрым
        живым зеркалом.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        data = urllib.parse.urlencode({"data": query}).encode("utf-8")
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ctx = ssl.create_default_context()

        def one(url):
            return post_with_retry(url, data, ctx, cancel=stop)

        errors = []
        stop = threading.Event()
        pool = ThreadPoolExecutor(max_workers=len(OVERPASS_URLS))
        try:
            futures = {pool.submit(one, url): url for url in OVERPASS_URLS}
            for future in as_completed(futures):
                try:
                    return future.result()
                except urllib.error.HTTPError as e:
                    errors.append(f"HTTP {e.code}")
                except Exception as e:
                    errors.append(str(e))
        finally:
            # опоздавшие зеркала доработают в фоне, ответ уже не ждём
            stop.set()                         # проигравшие зеркала не повторяют запросы поверх следующего
            pool.shutdown(wait=False)
        raise ConnectorError(
            f"Overpass не ответил ({'; '.join(errors)}) — попробуйте позже "
            "или уменьшите область")

    def fetch(self, bbox, sets):
        """bbox = (west, south, east, north) WGS84; sets ⊆ OSM_SETS."""
        west, south, east, north = map(float, bbox)
        bb = f"({south},{west},{north},{east})"
        clauses = []
        for key in sets:
            if key not in OSM_SETS:
                raise ConnectorError(f"неизвестный набор OSM: {key!r}")
            clauses += [sel + bb for sel in OSM_SETS[key]]
        query = f"[out:json][timeout:25];({';'.join(clauses)};);out geom;"
        data, cached_at, cache_note = self._answer(query, (west, south, east, north), sets)

        features, skipped = [], 0
        for el in data.get("elements") or []:
            etype = el.get("type")
            tags = el.get("tags") or {}
            # школа или поликлиника — ещё и точка набора social (контур здания при этом остаётся в buildings)
            if "social" in sets and tags.get("amenity") in _SOCIAL:
                pt = _point_of(el)
                if pt:
                    props = {k: tags[k] for k in _KEEP_TAGS if k in tags}
                    props["grado_set"] = "social"
                    features.append({"type": "Feature", "grado_key": f"{etype}/{el.get('id')}/social",
                                     "geometry": {"type": "Point", "coordinates": pt}, "properties": props})
            if etype not in ("way", "relation"):
                continue
            set_key = _which_set(tags)
            if set_key is None or set_key not in sets:
                continue
            props = {k: tags[k] for k in _KEEP_TAGS if k in tags}
            props["grado_set"] = set_key

            if etype == "way":
                if not el.get("geometry"):
                    continue
                pts = [[g["lon"], g["lat"]] for g in el["geometry"]]
                if len(pts) < 2:
                    skipped += 1
                    continue
                if set_key in _RING_SETS:
                    # площадной набор: полигон ТОЛЬКО из замкнутого way.
                    # открытый линейный way (канал/река-центр) в площадном
                    # слое не нужен — раньше он силой замыкался в мусорный
                    # полигон «туда-обратно»; его площадь придёт из relation
                    if pts[0] != pts[-1] or len(pts) < 4:
                        skipped += 1
                        continue
                    geometry = {"type": "Polygon", "coordinates": [pts]}
                else:
                    geometry = {"type": "LineString", "coordinates": pts}
                features.append({"type": "Feature",
                                 "grado_key": f"way/{el.get('id')}",
                                 "geometry": geometry, "properties": props})

            elif set_key in _RING_SETS:      # relation — мультиполигон
                outers, inners = [], []
                for m in el.get("members") or []:
                    if m.get("type") != "way" or not m.get("geometry"):
                        continue
                    seg = [[p["lon"], p["lat"]] for p in m["geometry"]]
                    (inners if m.get("role") == "inner" else outers).append(seg)
                rings = _assemble_rings(outers)
                if not rings:
                    skipped += 1
                    continue
                polys = [[r] for r in rings]
                for hole in _assemble_rings(inners):
                    for poly in polys:        # дыра — в тот внешний контур, что её содержит
                        if _in_ring(hole[0], poly[0]):
                            poly.append(hole)
                            break
                geometry = {"type": "MultiPolygon", "coordinates": polys}
                features.append({"type": "Feature",
                                 "grado_key": f"rel/{el.get('id')}",
                                 "geometry": geometry, "properties": props})
        notes = [cache_note] if cache_note else []
        if cached_at:
            # кэш мог быть снят с области шире запроса — лишнее отсекается по габаритам
            features = [f for f in features if _bbox_hits(f["geometry"], (west, south, east, north))]
        if skipped:
            notes.append(f"пропущено вырожденных геометрий: {skipped}")
        res = make_result(
            features,
            params={"bbox": ",".join(f"{float(v):.5f}" for v in bbox),
                    "sets": sorted(sets)},
            source_doc="OpenStreetMap (Overpass API)",
            notes=notes)
        if cached_at:
            res["fetched_at"] = time.strftime("%Y-%m-%d", time.localtime(cached_at))
        return res

    def _answer(self, query, bbox, sets):
        """(ответ Overpass, время снятия из кэша или None, пометка для пользователя)."""
        if not self.cache:
            return self.transport(query), None, None
        hit = self.cache.find(bbox, sets, self.fresh_s)
        if hit:
            return hit[0], hit[1], f"с диска, ответ в {time.strftime('%H:%M', time.localtime(hit[1]))} (повторно Overpass не запрашивался)"
        try:
            data = self.transport(query)
        except ConnectorError:
            old = self.cache.find(bbox, sets, self.stale_s)
            if not old:
                raise
            day = time.strftime("%d.%m.%Y", time.localtime(old[1]))
            return old[0], old[1], f"Overpass не ответил — взят прошлый ответ от {day}"
        self.cache.put(bbox, sets, data)
        return data, None, None
