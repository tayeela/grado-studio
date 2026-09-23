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

import codecs
import gzip
import json
import math
import os
import re
import shutil
import ssl
import threading
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

from .clip import clip_geometry
from .contract import Connector, ConnectorError, make_result

BASE = "https://gisogd.mos.ru/gis/api/2.8/gisogd/isogd"
# Карты портала: isogd — слои ИСОГД (Генплан, ПЗЗ, ЗОУИТ…), base2 — ЕГКО, «Картоснова (дополненная)»: здания, газоны,
# дороги, адреса. Каталог base2 отдаётся только с type=full (без него — пустой массив; проверено 23.09.2026).
MAPS = {
    "isogd": {"base": BASE, "catalog": "/layers/"},
    "base2": {"base": "https://gisogd.mos.ru/gis/api/2.8/gisogd/base2", "catalog": "/layers/?type=full&returnCss=0"},
}
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


class _tmp_beside:
    """Временный файл с уникальным именем рядом с целевым; при выходе без ошибки — атомарная подмена."""

    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        import tempfile
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name + ".", suffix=".part")
        import os
        os.close(fd)
        self.tmp = Path(name)
        return self.tmp

    def __exit__(self, kind, *_):
        if kind is None:
            self.tmp.replace(self.path)
        else:
            self.tmp.unlink(missing_ok=True)
        return False


def _expected_size(headers):
    """Размер слоя без сжатия, если портал его сообщает: Content-Length без gzip или число в ETag «мтайм-размер-inode»."""
    if headers.get("Content-Encoding") != "gzip" and headers.get("Content-Length", "").isdigit():
        return int(headers["Content-Length"])
    m = re.search(r'-(\d+)-', headers.get("ETag") or "")
    return int(m.group(1)) if m else None


def _http_get(url, timeout=300, progress=None):
    """GET → распакованные байты. gzip обязателен: слой 44 МБ ужимается до 14.

    progress(получено, всего или None) — по распакованным байтам, раз в ~0,5 МБ: слой ПЗЗ весит 221 МБ,
    и без процента первая выгрузка выглядит зависанием.
    """
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA, "Accept-Encoding": "gzip"})
    ctx = _ssl_context()
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                gz = r.headers.get("Content-Encoding") == "gzip"
                total, parts, got, told = _expected_size(r.headers), [], 0, 0
                dec = zlib.decompressobj(16 + zlib.MAX_WBITS) if gz else None
                while True:
                    chunk = r.read(1 << 18)
                    if not chunk:
                        break
                    chunk = dec.decompress(chunk) if dec else chunk
                    parts.append(chunk)
                    got += len(chunk)
                    if progress and got - told >= 1 << 19:
                        progress(got, total)
                        told = got
                if dec:
                    parts.append(dec.flush())
                raw = b"".join(parts)
                if progress:
                    progress(len(raw), total)
                return raw
        except urllib.error.HTTPError as e:
            raise ConnectorError(f"ГИС ОГД ответил HTTP {e.code}") from None
        except Exception as e:                       # сеть/таймаут — пробуем ещё
            last = e
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
                continue
    raise ConnectorError(f"ГИС ОГД недоступен: {last}")


def _http_stream(url, timeout=900):
    """Открыть выгрузку и отдавать её распакованными кусками, не собирая целиком: газоны ЕГКО — 1,3 ГБ.
    Ожидание 15 минут: крупный слой портал сначала собирает у себя — газоны начали отдаваться через ~4 минуты (23.09.2026).
    Повтор (до трёх попыток) — только на открытии соединения; обрыв посреди слоя — ошибка, без молчаливой докачки."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept-Encoding": "gzip"})
    ctx, last = _ssl_context(), None
    for attempt in range(3):
        try:
            r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
            break
        except urllib.error.HTTPError as e:
            raise ConnectorError(f"ГИС ОГД ответил HTTP {e.code}") from None
        except Exception as e:
            last = e
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
    else:
        raise ConnectorError(f"ГИС ОГД недоступен: {last}")

    def chunks():
        with r:
            dec = zlib.decompressobj(16 + zlib.MAX_WBITS) if r.headers.get("Content-Encoding") == "gzip" else None
            try:
                while True:
                    c = r.read(1 << 20)
                    if not c:
                        break
                    c = dec.decompress(c) if dec else c
                    if c:
                        yield c
                if dec:
                    tail = dec.flush()
                    if tail:
                        yield tail
            except (OSError, zlib.error) as e:
                raise ConnectorError(f"ГИС ОГД: выгрузка прервалась: {e}") from None
    return _expected_size(r.headers), chunks()


class _FeatureStream:
    """Потоковый разбор FeatureCollection: объекты массива features по одному, без json.loads всего файла.
    Каждый объект разбирается C-разбором json (raw_decode); незаконченный на стыке кусков ждёт следующий кусок."""

    def __init__(self):
        self.buf, self.pos, self.state = "", 0, "head"
        self.dec = json.JSONDecoder()

    def feed(self, text):
        self.buf = self.buf[self.pos:] + text
        self.pos = 0
        return self._drain()

    def _drain(self):
        buf = self.buf
        if self.state == "head":
            i = buf.find('"features"')
            j = buf.find("[", i) if i >= 0 else -1
            if j < 0:
                self.pos = max(0, len(buf) - 32)
                return
            self.pos, self.state = j + 1, "items"
        while self.state == "items":
            p, n = self.pos, len(buf)
            while p < n and buf[p] in " \t\r\n,":
                p += 1
            self.pos = p
            if p >= n:
                return
            if buf[p] == "]":
                self.state = "done"
                return
            try:
                obj, end = self.dec.raw_decode(buf, p)
            except ValueError:
                return                             # объект не закончился — ждём следующий кусок
            yield obj, buf[p:end]
            self.pos = end

    def finish(self):
        if self.state != "done":
            raise ConnectorError("ГИС ОГД: выгрузка оборвана или не FeatureCollection")


# сетка индекса слоя ЕГКО: объект не шире клетки лежит в клетке своего юго-западного угла, крупные — в общем файле
_CELL = 0.01                    # ° ≈ 0,63 × 1,1 км в Москве: здание или газон почти всегда меньше
_LOCKS, _LOCKS_GUARD = {}, threading.Lock()


def _layer_lock(key):
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


def catalog(transport=None, map_name="isogd"):
    """Каталог слоёв портала с путём в дереве (для поиска/проверки кодов)."""
    get = transport or _http_get
    m = MAPS[map_name]
    try:
        arr = json.loads(get(m["base"] + m["catalog"], timeout=60))
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

    def __init__(self, transport=None, cache_dir=None, ttl=_TTL_SEC, progress=None, map_name="isogd", clip=False):
        """progress(code, получено, всего или None, этап) — ход первой выгрузки слоя целиком.

        map_name="base2" (ЕГКО): слой идёт потоком и раскладывается по клеткам сетки на диске — в памяти его нет
        ни при выгрузке, ни при выборке; ключ объекта несёт карту («base2:код:id»), потому что коды base2 пишутся
        так же, как коды isogd (virtual6…). clip=True — объекты режутся по рамке области, а не отбираются целиком.
        Карта isogd работает как раньше (слой целиком в памяти, ключ «код:id»)."""
        self.transport = transport or _http_get
        self.progress = progress
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.ttl = ttl
        self.map_name = map_name
        self.base = MAPS[map_name]["base"]
        self.clip = clip
        if map_name != "isogd":
            self.source_doc = "ЕГКО Москвы (картооснова ГИС ОГД, gisogd.mos.ru), выгрузка по экстенту"

    # ---------- ЕГКО: потоковая выгрузка и сетка на диске ----------
    def _grid_dir(self, code):
        return self.cache_dir / f"{self.map_name}.{code}.grid" if self.cache_dir else None

    def _grid_fresh(self, code):
        g = self._grid_dir(code)
        meta = g / "_meta.json" if g else None
        return bool(meta and meta.exists() and (time.time() - meta.stat().st_mtime) < self.ttl)

    def _chunks(self, url, code):
        """Распакованные куски выгрузки; ход — в progress по полученным байтам."""
        if self.transport is _http_get:
            total, it = _http_stream(url)
        else:                                       # тестовый транспорт отдаёт байты целиком
            raw = self.transport(url)
            total, it = len(raw), (raw[i:i + 65536] for i in range(0, len(raw), 65536))
        got, told = 0, 0
        for c in it:
            got += len(c)
            if self.progress and got - told >= 1 << 20:
                self.progress(code, got, total, "download")
                told = got
            yield c
        if self.progress:
            self.progress(code, got, total, "index")

    def _stream_build(self, code, query):
        """Выгрузить слой потоком: объекты в области — сразу в ответ, все — в клетки сетки (если есть кэш)."""
        url = f"{self.base}/layers/{code}/export/?format=geojson"
        grid = self._grid_dir(code)
        tmp = None
        if grid:
            grid.parent.mkdir(parents=True, exist_ok=True)
            tmp = Path(str(grid) + f".{os.getpid()}.{threading.get_ident()}.part")
            shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir()
        buf, size, count, out = {}, 0, 0, []

        def flush():
            nonlocal size
            for cell, lines in buf.items():
                with open(tmp / f"{cell}.lines.gz", "ab") as fh:        # gzip допускает склейку членов
                    fh.write(gzip.compress("".join(lines).encode("utf-8"), 1))
            buf.clear()
            size = 0

        parser, utf8 = _FeatureStream(), codecs.getincrementaldecoder("utf-8")()
        try:
            for chunk in self._chunks(url, code):
                for f, rawtext in parser.feed(utf8.decode(chunk)):
                    count += 1
                    geom = f.get("geometry")
                    fb = _geom_bbox(geom)
                    if not fb:
                        continue
                    props = f.get("properties") or {}
                    key = f"{self.map_name}:{code}:{norm_id(props.get('orbis_id') or props.get('id') or f.get('id') or count)}"
                    if _overlaps(fb, query):
                        out.append({"type": "Feature", "geometry": geom, "properties": dict(props), "grado_key": key})
                    if tmp is None:
                        continue
                    small = fb[2] - fb[0] <= _CELL and fb[3] - fb[1] <= _CELL
                    cell = f"{math.floor(fb[0] / _CELL)}_{math.floor(fb[1] / _CELL)}" if small else "big"
                    line = ",".join(repr(v) for v in fb) + "\t" + key + "\t" + rawtext.replace("\n", " ") + "\n"
                    buf.setdefault(cell, []).append(line)
                    size += len(line)
                    if size > 48_000_000:           # ~50–100 МБ строк в памяти, дальше — на диск
                        flush()
            for _ in parser.feed(utf8.decode(b"", final=True)):
                pass
            parser.finish()
            if tmp is not None:
                flush()
                (tmp / "_meta.json").write_text(json.dumps({"code": code, "map": self.map_name, "count": count, "cell": _CELL}), "utf-8")
                shutil.rmtree(grid, ignore_errors=True)
                tmp.replace(grid)
                tmp = None
        finally:
            if tmp is not None:
                shutil.rmtree(tmp, ignore_errors=True)
        time.sleep(_PAUSE)
        return out, count

    def _grid_read(self, code, query):
        """Выборка из сетки: клетки области и соседние слева/снизу (объект лежит в клетке своего угла) + крупные."""
        g = self._grid_dir(code)
        w, s, e, n = query
        names = [f"{ix}_{iy}" for ix in range(math.floor((w - _CELL) / _CELL), math.floor(e / _CELL) + 1)
                 for iy in range(math.floor((s - _CELL) / _CELL), math.floor(n / _CELL) + 1)] + ["big"]
        out = []
        for name in names:
            p = g / f"{name}.lines.gz"
            if not p.exists():
                continue
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                for line in fh:
                    bb, key, js = line.rstrip("\n").split("\t", 2)
                    if _overlaps(tuple(float(v) for v in bb.split(",")), query):
                        f = json.loads(js)
                        out.append({"type": "Feature", "geometry": f.get("geometry"),
                                    "properties": f.get("properties") or {}, "grado_key": key})
        return out

    def _fetch_stream(self, code, query):
        notes = []
        lock = _layer_lock(str(self._grid_dir(code) or code))
        with lock:                                  # одну и ту же выгрузку не качают две вкладки сразу
            if self.cache_dir and self._grid_fresh(code):
                try:
                    feats = self._grid_read(code, query)
                except (OSError, EOFError, zlib.error, ValueError):
                    shutil.rmtree(self._grid_dir(code), ignore_errors=True)    # битая сетка — собрать заново
                    feats, count = self._stream_build(code, query)
                    notes.append(f"слой {code} ЕГКО загружен заново целиком ({count} об.)")
            else:
                feats, count = self._stream_build(code, query)
                notes.append(f"слой {code} ЕГКО загружен целиком ({count} об.) — портал не фильтрует по области; "
                             f"дальше берётся из кэша")
        if self.clip:
            cut = []
            for f in feats:
                g = clip_geometry(f["geometry"], query)
                if g:
                    cut.append({**f, "geometry": g})
            feats = cut
        return make_result(feats, {"code": code, "map": self.map_name, "bbox": ",".join(f"{v:.5f}" for v in query)},
                           source_doc=self.source_doc, notes=notes)

    def _cache_path(self, code):
        if not self.cache_dir:
            return None
        return self.cache_dir / f"{code}.geojson.gz"

    def _layer_bytes(self, code):
        """Слой целиком: из кэша, иначе скачать и закэшировать (gzip на диске)."""
        path = self._cache_path(code)
        if path and path.exists() and (time.time() - path.stat().st_mtime) < self.ttl:
            try:
                return gzip.decompress(path.read_bytes()), True
            except (OSError, EOFError, zlib.error):
                path.unlink(missing_ok=True)       # недописанный кэш — скачать заново, а не падать до конца срока
        url = f"{self.base}/layers/{code}/export/?format=geojson"
        if self.progress and self.transport is _http_get:
            raw = _http_get(url, progress=lambda got, total: self.progress(code, got, total, "download"))
        else:
            raw = self.transport(url)
        if self.progress:
            self.progress(code, len(raw), len(raw), "parse")
        if path:
            with _tmp_beside(path) as tmp:         # свой временный файл: две вкладки не склеят чужие хвосты
                tmp.write_bytes(gzip.compress(raw, 6))
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
        try:
            with gzip.open(lp, "rt", encoding="utf-8") as fh:
                for line in fh:
                    bb, key, js = line.rstrip("\n").split("\t", 2)
                    fb = tuple(float(v) for v in bb.split(","))
                    if _overlaps(fb, query):
                        f = json.loads(js)
                        out.append({"type": "Feature", "geometry": f["geometry"],
                                    "properties": f["properties"], "grado_key": key})
        except (OSError, EOFError, zlib.error, ValueError):
            lp.unlink(missing_ok=True)             # битый построчный кэш — пересобрать из слоя целиком
            return None
        return out

    def _write_lines(self, code, rows):
        lp = self._lines_path(code)
        if not lp:
            return
        with _tmp_beside(lp) as tmp, gzip.open(tmp, "wt", encoding="utf-8", compresslevel=5) as fh:
            for fb, key, f in rows:
                fh.write(",".join(repr(v) for v in fb) + "\t" + key + "\t"
                         + json.dumps({"geometry": f.get("geometry"), "properties": f.get("properties") or {}},
                                      ensure_ascii=False, separators=(",", ":")) + "\n")

    def fetch(self, bbox, code):
        """bbox = (west, south, east, north) WGS84; code — код слоя портала."""
        west, south, east, north = map(float, bbox)
        query = (west, south, east, north)
        if self.map_name != "isogd":
            return self._fetch_stream(code, query)
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
