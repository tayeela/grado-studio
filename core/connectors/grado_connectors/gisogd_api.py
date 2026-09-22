"""Коннектор ГИС ОГД Москвы — прямая выгрузка слоёв по открытому REST API.

Портал gisogd.mos.ru («Карта градостроительства», Москомархитектура) — фронтенд
поверх открытого REST API без авторизации (≈660 слоёв):

    BASE = https://gisogd.mos.ru/gis/api/2.8/gisogd/isogd
    GET /layers/                                → каталог (id, code, name, parent_id, type)
    GET /layers/{code}/export/?format=geojson   → весь слой, WGS84 (CRS84)

⚠ Параметр `bbox` этот API ИГНОРИРУЕТ. Проверено 2026-07-15 на `virtual1742`:
`/objects/` без bbox и с bbox ~150 м отдают одинаковые 3285 объектов, export
с bbox — те же 3285. Слой всегда приходит ЦЕЛИКОМ (функц. зоны Генплана:
14 МБ gzip → 44 МБ JSON, ~8 с). Поэтому здесь: слой скачивается один раз,
кладётся в дисковый кэш, а по видимой области режем САМИ (bbox-пересечение,
чистый Python — geopandas не нужен). Выгрузка следующей площадки берёт слой из
кэша и отвечает мгновенно.

Вежливость: данные официальные и открытые (ИСОГД публичен), но портал не
«долбим» — кэш на диске с TTL и пауза между сетевыми запросами.
"""

import gzip
import json
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

from .contract import Connector, ConnectorError, make_result

BASE = "https://gisogd.mos.ru/gis/api/2.8/gisogd/isogd"
_UA = "grado-studio/0.1 (+urban planning; ISOGD open data)"
_TTL_SEC = 7 * 24 * 3600      # Генплан/ПЗЗ меняются редко — недели хватает
_PAUSE = 0.5                  # пауза между сетевыми запросами, с

# Кураторский набор слоёв ОГД (коды сверены с живым каталогом 2026-07-15;
# `virtualNNN` со временем меняются — проверять через catalog()).
#
# ВАЖНО про функц. зоны: старая Москва и присоединённые территории лежат в
# РАЗНЫХ ветках и устроены по-разному.
#   • Старая Москва — ОДИН слой virtual1742 (3285 об., 14 МБ gzip). Несёт
#     naimfunkzony + summfondpersp (суммарный фонд, тыс. м² — прямой вход ТЭП).
#     ТиНАО он НЕ покрывает (проверено на Былово: 0 объектов).
#   • ТиНАО — 15 отдельных слоёв, по одному на тип зоны (тип = имя слоя).
#     Слои лёгкие (десятки–сотни объектов). summfondpersp тут НЕТ, есть
#     name/fz_type/name_rajon.
_TINAO_FUNC_ZONES = {
    "virtual1982": "Жилая зона",
    "virtual1981": "Зона объектов внешнего транспорта",
    "virtual1980": "Общественная зона",
    "virtual1979": "Общественно-жилая зона",
    "virtual1978": "Общественно-производственная зона",
    "virtual1977": "Общественно-производственно-жилая зона",
    "virtual1976": "Природная зона",
    "virtual1975": "Природно-жилая зона",
    "virtual1971": "Природно-общественная зона",
    "virtual1970": "Природно-общественно-жилая зона",
    "virtual1969": "Природно-общественно-производственная зона",
    "virtual1968": "Природно-производственная зона",
    "virtual1967": "Производственная зона",
    "virtual1966": "Производственно-жилая зона",
    "virtual1965": "Сельскохозяйственная зона",
}

GISOGD_API_LAYERS = {
    "gisogd.func_zones": {
        "codes": {"virtual1742": None},
        "title": "Функц. зоны Генплана (Москва)",
        "kind": "zone",
        "layer_id": "source.gisogd.func_zones",
    },
    "gisogd.func_zones_tinao": {
        "codes": _TINAO_FUNC_ZONES,     # тип зоны = имя слоя (в атрибут zone_title)
        "title": "Функц. зоны (Новая Москва, ТиНАО)",
        "kind": "zone",
        "layer_id": "source.gisogd.func_zones",
    },
    "gisogd.szz": {
        "codes": {"virtual1743": "СЗЗ установленная",
                  "virtual1746": "СЗЗ ориентировочная",
                  "virtual1745": "СЗЗ расчётная"},
        "title": "Санитарно-защитные зоны (ОГД)",
        "kind": "restrict",
        "layer_id": "source.gisogd.restrict",
        "style_id": "lgr.szz.set",
    },
    "gisogd.vodookhr": {
        "codes": {"virtual1747": "Водоохранная зона"},
        "title": "Водоохранные зоны (ОГД)",
        "kind": "restrict",
        "layer_id": "source.gisogd.restrict",
        "style_id": "lgr.vodookhr",
    },
}


def _ssl_context():
    # Сборки Python.org на macOS не видят системные CA (правило 6 CLAUDE.md).
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _http_get(url, timeout=300):
    """GET → распакованные байты. gzip обязателен: слой 44 МБ ужимается до 14."""
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA, "Accept-Encoding": "gzip"})
    ctx = _ssl_context()
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except urllib.error.HTTPError as e:
            raise ConnectorError(f"ГИС ОГД ответил HTTP {e.code}") from None
        except Exception as e:                       # сеть/таймаут — пробуем ещё
            last = e
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
                continue
    raise ConnectorError(f"ГИС ОГД недоступен: {last}")


def catalog(transport=None):
    """Каталог слоёв портала с путём в дереве (для поиска/проверки кодов)."""
    get = transport or _http_get
    try:
        arr = json.loads(get(f"{BASE}/layers/", timeout=60))
    except ConnectorError:
        raise
    except Exception as e:
        raise ConnectorError(f"ГИС ОГД: каталог не разобран: {e}") from None
    by_id = {x.get("id"): x for x in arr}

    def path(x):
        parts, cur, guard = [], x, 0
        while cur and guard < 8:
            parts.insert(0, cur.get("name") or "")
            cur = by_id.get(cur.get("parent_id"))
            guard += 1
        return " / ".join(p for p in parts if p)

    return [{"code": x.get("code"), "name": x.get("name"),
             "type": x.get("type"), "path": path(x)} for x in arr]


def _geom_bbox(geom):
    """Габариты геометрии GeoJSON (любой вложенности) → (w, s, e, n) | None."""
    xs, ys = [], []

    def walk(c):
        if not isinstance(c, list) or not c:
            return
        if isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
            return
        for item in c:
            walk(item)

    walk((geom or {}).get("coordinates"))
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _overlaps(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def norm_id(v):
    """id портала приходит float'ом (149.0) — ключ дедупа должен быть «149»."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


class GisogdApi(Connector):
    """Слой ОГД по видимой области: кэш слоя целиком + локальный bbox-фильтр."""
    name = "gisogd"
    source = "gisogd"

    def __init__(self, transport=None, cache_dir=None, ttl=_TTL_SEC):
        self.transport = transport or _http_get
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.ttl = ttl

    def _cache_path(self, code):
        if not self.cache_dir:
            return None
        return self.cache_dir / f"{code}.geojson.gz"

    def _layer_bytes(self, code):
        """Слой целиком: из кэша, иначе скачать и закэшировать (gzip на диске)."""
        path = self._cache_path(code)
        if path and path.exists() and (time.time() - path.stat().st_mtime) < self.ttl:
            return gzip.decompress(path.read_bytes()), True
        raw = self.transport(f"{BASE}/layers/{code}/export/?format=geojson")
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(gzip.compress(raw, 6))
            tmp.replace(path)          # атомарно: не оставить битый кэш
        time.sleep(_PAUSE)
        return raw, False

    def _lines_path(self, code):
        return self.cache_dir / f"{code}.lines.gz" if self.cache_dir else None

    def _from_lines(self, code, query):
        """Быстрый путь по кэшу: строка на объект «w,s,e,n<TAB>ключ<TAB>json».
        Разбирается только то, что попало в область: слой ПЗЗ старой Москвы — 221 МБ JSON,
        целиком json.loads — ~5 с и 1,5 ГБ памяти, построчно — около секунды."""
        lp, gz = self._lines_path(code), self._cache_path(code)
        if not (lp and lp.exists() and gz and gz.exists()) or lp.stat().st_mtime < gz.stat().st_mtime \
                or (time.time() - gz.stat().st_mtime) >= self.ttl:
            return None
        out = []
        with gzip.open(lp, "rt", encoding="utf-8") as fh:
            for line in fh:
                bb, key, js = line.rstrip("\n").split("\t", 2)
                fb = tuple(float(v) for v in bb.split(","))
                if _overlaps(fb, query):
                    f = json.loads(js)
                    out.append({"type": "Feature", "geometry": f["geometry"],
                                "properties": f["properties"], "grado_key": key})
        return out

    def _write_lines(self, code, rows):
        lp = self._lines_path(code)
        if not lp:
            return
        tmp = lp.with_suffix(lp.suffix + ".part")
        with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=5) as fh:
            for fb, key, f in rows:
                fh.write(",".join(repr(v) for v in fb) + "\t" + key + "\t"
                         + json.dumps({"geometry": f.get("geometry"), "properties": f.get("properties") or {}},
                                      ensure_ascii=False, separators=(",", ":")) + "\n")
        tmp.replace(lp)

    def fetch(self, bbox, code):
        """bbox = (west, south, east, north) WGS84; code — код слоя портала."""
        west, south, east, north = map(float, bbox)
        query = (west, south, east, north)
        fast = self._from_lines(code, query)
        if fast is not None:
            return make_result(fast, {"code": code, "bbox": ",".join(f"{v:.5f}" for v in query)},
                               source_doc="ГИС ОГД Москвы (gisogd.mos.ru), выгрузка по экстенту", notes=[])
        raw, cached = self._layer_bytes(code)
        try:
            data = json.loads(raw)
        except Exception as e:
            raise ConnectorError(f"ГИС ОГД: слой {code} не разобран: {e}") from None
        if not isinstance(data, dict) or not isinstance(data.get("features"), list):
            raise ConnectorError(f"ГИС ОГД: слой {code} — не FeatureCollection")

        out, notes, rows = [], [], []
        for i, f in enumerate(data["features"]):
            geom = f.get("geometry")
            fb = _geom_bbox(geom)
            if not fb:
                continue
            props = f.get("properties") or {}
            key = f"{code}:{norm_id(props.get('orbis_id') or props.get('id') or f.get('id') or i)}"
            rows.append((fb, key, f))
            if not _overlaps(fb, query):
                continue
            out.append({"type": "Feature", "geometry": geom,
                        "properties": dict(props),
                        "grado_key": key})
        self._write_lines(code, rows)
        if not cached:
            notes.append(f"слой {code} загружен целиком ({len(data['features'])} об., "
                         f"{len(raw)/1e6:.0f} МБ) — портал не фильтрует по области; "
                         f"дальше берётся из кэша")
        return make_result(
            out,
            {"code": code, "bbox": ",".join(f"{v:.5f}" for v in query)},
            source_doc="ГИС ОГД Москвы (gisogd.mos.ru), выгрузка по экстенту",
            notes=notes)
