"""Коннектор OSM (Overpass API) — прямая выгрузка векторов по экстенту.

Открытые данные, авторизация не нужна. Запрос собирается только из
выбранных наборов (дороги/здания/землепользование/вода) одним обращением
к Overpass; ответ `out geom` несёт координаты прямо в way — без второй
фазы резолва узлов. Локальный однопользовательский инструмент = «лёгкое
использование» по политике Overpass; лимит площади держит фронт+сервер.
"""

import json
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
                'way["natural"~"^(wood|scrub|grassland|heath)$"]'],
    "water": ['way["natural"="water"]',
              'way["water"]',
              'way["waterway"~"^(riverbank|dock|canal)$"]'],
}

# Замкнутые наборы становятся полигонами; дороги остаются линиями.
_RING_SETS = {"buildings", "landuse", "water"}

# Теги, уходящие в атрибуты холста (шум вроде source=* отбрасывается).
_KEEP_TAGS = ("highway", "name", "building", "building:levels", "landuse",
              "leisure", "natural", "water", "waterway", "surface", "lanes")


def _which_set(tags):
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


class OsmOverpass(Connector):
    name = "osm"
    source = "osm"

    def __init__(self, transport=None):
        self.transport = transport or self._http_post

    def _http_post(self, query):
        data = urllib.parse.urlencode({"data": query}).encode("utf-8")
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ctx = ssl.create_default_context()
        last = None
        for url in OVERPASS_URLS:
            req = urllib.request.Request(url, data=data,
                                         headers={"User-Agent": _UA})
            try:
                with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (429, 504):   # перегрузка — пробуем зеркало
                    last = f"HTTP {e.code}"
                    continue
                raise ConnectorError(f"Overpass ответил HTTP {e.code}") from None
            except Exception as e:
                last = str(e)
                continue
        raise ConnectorError(
            f"Overpass перегружен ({last}) — попробуйте позже "
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
            if el.get("type") != "way" or not el.get("geometry"):
                continue
            pts = [[g["lon"], g["lat"]] for g in el["geometry"]]
            if len(pts) < 2:
                skipped += 1
                continue
            tags = el.get("tags") or {}
            set_key = _which_set(tags)
            if set_key is None or set_key not in sets:
                continue
            props = {k: tags[k] for k in _KEEP_TAGS if k in tags}
            props["grado_set"] = set_key
            if set_key in _RING_SETS:
                if pts[0] != pts[-1]:
                    pts = pts + [pts[0]]
                if len(pts) < 4:      # вырожденное «кольцо» из двух точек
                    skipped += 1
                    continue
                geometry = {"type": "Polygon", "coordinates": [pts]}
            else:
                geometry = {"type": "LineString", "coordinates": pts}
            features.append({"type": "Feature",
                             "grado_key": f"way/{el.get('id')}",
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
