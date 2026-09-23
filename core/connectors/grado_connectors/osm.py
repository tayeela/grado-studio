"""Коннектор OSM (Overpass API) — прямая выгрузка векторов по экстенту.

Открытые данные, авторизация не нужна. Запрос собирается только из
выбранных наборов (дороги/здания/землепользование/вода) одним обращением
к Overpass; ответ `out geom` несёт координаты прямо в way — без второй
фазы резолва узлов. Локальный однопользовательский инструмент = «лёгкое
использование» по политике Overpass; лимит площади держит фронт+сервер.
"""

import json
import time
import ssl
import urllib.parse
import urllib.request

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
    "buildings": ['way["building"]'],
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
              "boundary", "admin_level", "amenity")


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


class OsmOverpass(Connector):
    name = "osm"
    source = "osm"

    def __init__(self, transport=None):
        self.transport = transport or self._http_post

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
            # 429/504 зеркало отдаёт за доли секунды — повтор дешёвый
            for attempt in range(3):
                req = urllib.request.Request(url, data=data, headers={"User-Agent": _UA})
                try:
                    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                        return json.loads(r.read().decode("utf-8"))
                except urllib.error.HTTPError as e:
                    if e.code not in (429, 504) or attempt == 2:
                        raise
                    time.sleep(2 * (attempt + 1))

        errors = []
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
        data = self.transport(query)

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
        notes = []
        if skipped:
            notes.append(f"пропущено вырожденных геометрий: {skipped}")
        return make_result(
            features,
            params={"bbox": ",".join(f"{float(v):.5f}" for v in bbox),
                    "sets": sorted(sets)},
            source_doc="OpenStreetMap (Overpass API)",
            notes=notes)
