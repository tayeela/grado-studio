"""Коннектор ГИС ОГД Москвы — прямая выгрузка слоёв по открытому REST API.

Портал gisogd.mos.ru («Карта градостроительства», Москомархитектура) — фронтенд
поверх открытого REST API без авторизации (≈660 слоёв):

    BASE = https://gisogd.mos.ru/gis/api/2.8/gisogd/isogd
    GET /layers/                                → каталог (id, code, name, parent_id, type)
    GET /layers/{code}/export/?format=shp       → весь слой, zip SHP в родных координатах ОГД
    (format=geojson — тот же слой в WGS84, но пересчитан порталом со сдвигом ~7,7 м; не используется)

⚠ Параметр `bbox` этот API ИГНОРИРУЕТ. Проверено 2026-07-15 на `virtual1742`:
`/objects/` без bbox и с bbox ~150 м отдают одинаковые 3285 объектов, export
с bbox — те же 3285. Слой всегда приходит ЦЕЛИКОМ (функц. зоны Генплана:
14 МБ gzip → 44 МБ JSON, ~8 с). Поэтому здесь: слой скачивается один раз,
кладётся в дисковый кэш, а по видимой области режем САМИ (bbox-пересечение,
чистый Python — geopandas не нужен). Выгрузка следующей площадки берёт слой из
кэша и отвечает мгновенно.

Вежливость: данные официальные и открытые (ИСОГД публичен), но портал не
«долбим» — кэш на диске с TTL и пауза между сетевыми запросами.

Координаты (с 23.09.2026): слой берётся в SHP (`format=shp`, zip: .shp/.dbf/.cpg, .prj «Moscow_bessel») — это родные
координаты ГИС ОГД — и переводится в WGS84 через OGD_PROJ4 (crs.msk50_to_wgs84), как в QGIS-плагине владельца.
GeoJSON, пересчитанный сервером портала, стоит на ~7,7 м иначе (virtual1681: 13 215 объектов, p95 7,8 м; у ЕГКО так же).
Имена полей в .dbf обрезаны до 10 знаков (podzone_num → podzone_nu); кэш прежнего GeoJSON не используется (имена файлов
кэша с «shp»).
"""

import gzip
import io
import json
import math
import os
import re
import shutil
import ssl
import struct
import threading
import time
import urllib.error
import zipfile
import urllib.request
import zlib
from pathlib import Path

from .clip import clip_geometry
from .contract import Connector, ConnectorError, make_result
from .crs import msk50_to_wgs84, transform_geom
from .gisogd import clean_msg
from .netutil import open_url
from .shp_reader import iter_zip

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

_MAX_LAYER = 512 * 2**20      # потолок слоя, собираемого в памяти (_http_get), — и сжатого, и распакованного
_MAX_STREAM = 2 * 2**30       # потолок потоковой выгрузки на диск (ЕГКО: газоны — 1,3 ГБ)
_CODE_RE = re.compile(r"[A-Za-z0-9_.-]+")


def _check_code(code):
    """Код слоя идёт в URL и имена файлов кэша: только буквы, цифры, «_.-», без «..» и ведущей точки."""
    if (not isinstance(code, str) or not _CODE_RE.fullmatch(code)
            or ".." in code or code.startswith(".")):
        raise ConnectorError("ГИС ОГД: недопустимый код слоя")
    return code


def _inflate(dec, chunk, room):
    """Распаковать кусок gzip, но не больше room байт (защита от gzip-бомбы) → байты."""
    out = []
    while True:
        data = dec.decompress(chunk, room + 1)      # +1: превышение видно по длине, а не по тому, что выход встал ровно
        room -= len(data)
        if room < 0:
            raise ConnectorError("ГИС ОГД: распакованный ответ больше допустимого")
        if data:
            out.append(data)
        chunk = dec.unconsumed_tail
        if not chunk:
            return b"".join(out)


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


class _nowhere:
    """Пустой контекст вместо файла, когда кэша на диске нет."""

    def __enter__(self):
        return None

    def __exit__(self, *_):
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
            with open_url(req, timeout=timeout, context=ctx) as r:
                gz = r.headers.get("Content-Encoding") == "gzip"
                total, parts, got, told, wire = _expected_size(r.headers), [], 0, 0, 0
                dec = zlib.decompressobj(wbits=31) if gz else None
                while True:
                    chunk = r.read(1 << 18)
                    if not chunk:
                        break
                    wire += len(chunk)
                    if wire > _MAX_LAYER:
                        raise ConnectorError(f"ГИС ОГД: ответ больше {_MAX_LAYER // 2**20} МБ")
                    chunk = _inflate(dec, chunk, _MAX_LAYER - got) if dec else chunk
                    parts.append(chunk)
                    got += len(chunk)
                    if got > _MAX_LAYER:
                        raise ConnectorError(f"ГИС ОГД: ответ больше {_MAX_LAYER // 2**20} МБ")
                    if progress and got - told >= 1 << 19:
                        progress(got, total)
                        told = got
                if dec:
                    parts.append(_inflate(dec, b"", _MAX_LAYER - got))
                raw = b"".join(parts)
                if progress:
                    progress(len(raw), total)
                return raw
        except urllib.error.HTTPError as e:
            raise ConnectorError(f"ГИС ОГД ответил HTTP {e.code}") from None
        except ConnectorError:                       # потолок размера, редирект не на https — повтор не поможет
            raise
        except Exception as e:                       # сеть/таймаут — пробуем ещё
            last = e
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
                continue
    raise ConnectorError(f"ГИС ОГД недоступен: {clean_msg(last)}")


def _http_stream(url, timeout=900):
    """Открыть выгрузку и отдавать её распакованными кусками, не собирая целиком: газоны ЕГКО — 1,3 ГБ.
    Ожидание 15 минут: крупный слой портал сначала собирает у себя — газоны начали отдаваться через ~4 минуты (23.09.2026).
    Повтор (до трёх попыток) — только на открытии соединения; обрыв посреди слоя — ошибка, без молчаливой докачки."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept-Encoding": "gzip"})
    ctx, last = _ssl_context(), None
    for attempt in range(3):
        try:
            r = open_url(req, timeout=timeout, context=ctx)
            break
        except urllib.error.HTTPError as e:
            raise ConnectorError(f"ГИС ОГД ответил HTTP {e.code}") from None
        except ConnectorError:                       # редирект не на https — повтор не поможет
            raise
        except Exception as e:
            last = e
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
    else:
        raise ConnectorError(f"ГИС ОГД недоступен: {clean_msg(last)}")

    def chunks():
        with r:
            dec = zlib.decompressobj(wbits=31) if r.headers.get("Content-Encoding") == "gzip" else None
            got = 0
            try:
                while True:
                    c = r.read(1 << 20)
                    if not c:
                        break
                    c = _inflate(dec, c, _MAX_STREAM - got) if dec else c
                    got += len(c)
                    if got > _MAX_STREAM:
                        raise ConnectorError(f"ГИС ОГД: выгрузка больше {_MAX_STREAM // 2**30} ГБ")
                    if c:
                        yield c
                if dec:
                    tail = _inflate(dec, b"", _MAX_STREAM - got)
                    if tail:
                        yield tail
            except (OSError, zlib.error) as e:
                raise ConnectorError(f"ГИС ОГД: выгрузка прервалась: {clean_msg(e)}") from None
    return _expected_size(r.headers), chunks()


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
        raise ConnectorError(f"ГИС ОГД: каталог не разобран: {clean_msg(e)}") from None
    by_id = {x.get("id"): x for x in arr}

    def path(x):
        parts, cur, guard = [], x, 0
        while cur and guard < 8:
            parts.insert(0, cur.get("name") or "")
            cur = by_id.get(cur.get("parent_id"))
            guard += 1
        return " / ".join(p for p in parts if p)

    # id и parent_id — для дерева папок в порядке портала (массив портал отдаёт уже в своём порядке)
    return [{"code": x.get("code"), "name": x.get("name"), "type": x.get("type"), "path": path(x),
             "id": x.get("id"), "parent_id": x.get("parent_id")} for x in arr]


# Имена полей .dbf обрезаны до 10 знаков. Для слоёв ИСОГД из SOURCES возвращаются прежние полные имена, как в GeoJSON
# портала: на них завязаны стиль и запрет «природные зоны» функциональных зон (naimfunkzony), разбор ПЗЗ в server.py
# и поля уже сохранённых проектов. Соответствие сверено 23.09.2026 по всем 30 слоям (старый кэш GeoJSON ↔ .dbf).
DBF_FULL_NAMES = {
    "naimfunkzo": "naimfunkzony", "summfondpe": "summfondpersp", "podzone_nu": "podzone_num", "old_zone_n": "old_zone_num",
    "zone_index": "zone_index_literal_n", "zone_ind_1": "zone_index_literal_f", "restrictio": "restrictions2",
    "num_adm_ok": "num_adm_okr", "name_adm_o": "name_adm_okr", "interval_f": "interval_fo",
    "db2gse_st_": "db2gse_st_area_shape_", "db2gse_sde": "db2gse_sdelength_shape_",
}


def _full_names(props):
    out = {DBF_FULL_NAMES.get(k, k): v for k, v in props.items()}
    # shape_length: обычно усечён в shape_leng; если в слое были оба (уведомления о сносе), второй — shape_le_1
    if "shape_le_1" in out:
        out["shape_length"] = out.pop("shape_le_1")
    elif "shape_leng" in out and "shape_length" not in out:
        out["shape_length"] = out.pop("shape_leng")
    return out


def _shp_features(zf, code, full_names=False):
    """zip-выгрузка слоя в SHP → объекты GeoJSON в WGS84 (родные координаты ОГД → OGD_PROJ4 → WGS84), по одному."""
    # испорченный архив (struct.error/IndexError на обрезанной записи, ValueError ридера) — ошибка коннектора без сырого
    # текста исключения; разбор записей идёт лениво, поэтому try охватывает и сам обход
    bad = (ValueError, KeyError, IndexError, struct.error, EOFError, zlib.error, zipfile.BadZipFile)
    try:
        _prj, records = iter_zip(zf)
        for r in records:
            g = r["geometry"]
            if g and g.get("type") == "MultiPoint" and not g["coordinates"]:
                g = None
            props = _full_names(r["properties"]) if full_names else r["properties"]
            yield {"type": "Feature", "geometry": transform_geom(g, msk50_to_wgs84) if g else None, "properties": props}
    except bad:
        raise ConnectorError(f"ГИС ОГД: слой {code} — архив SHP повреждён или не разобран") from None


def _zip_of(raw, code):
    import io
    import zipfile
    try:
        return zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise ConnectorError(f"ГИС ОГД: слой {code} — ответ не архив SHP") from None


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
    def _cache_child(self, code, name):
        """Путь внутри кэша для слоя code: код проверен, результат не выходит из каталога кэша."""
        _check_code(code)
        if not self.cache_dir:
            return None
        p = self.cache_dir / name
        if not p.resolve().is_relative_to(self.cache_dir.resolve()):
            raise ConnectorError("ГИС ОГД: путь кэша вне каталога кэша")
        return p

    def _grid_dir(self, code):
        return self._cache_child(code, f"{self.map_name}.{code}.shp.grid")

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
        """Выгрузить слой (zip SHP) потоком на диск, затем разобрать по записи: объекты в области — сразу в ответ,
        все — в клетки сетки (если есть кэш). В памяти нет ни архива, ни слоя."""
        import tempfile
        import zipfile
        _check_code(code)
        url = f"{self.base}/layers/{code}/export/?format=shp"
        grid = self._grid_dir(code)
        tmp = None
        base = grid.parent if grid else Path(tempfile.gettempdir())
        base.mkdir(parents=True, exist_ok=True)
        if grid:
            tmp = Path(str(grid) + f".{os.getpid()}.{threading.get_ident()}.part")
            shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir()
        fd, zpath = tempfile.mkstemp(dir=base, prefix=f"{code}.", suffix=".zip.part")
        buf, size, count, out = {}, 0, 0, []

        def flush():
            nonlocal size
            for cell, lines in buf.items():
                with open(tmp / f"{cell}.lines.gz", "ab") as fh:        # gzip допускает склейку членов
                    fh.write(gzip.compress("".join(lines).encode("utf-8"), 1))
            buf.clear()
            size = 0

        try:
            with os.fdopen(fd, "wb") as fh:
                written = 0
                for chunk in self._chunks(url, code):
                    written += len(chunk)
                    if written > _MAX_STREAM:               # частичный файл удалит finally
                        raise ConnectorError(f"ГИС ОГД: слой {code} больше {_MAX_STREAM // 2**30} ГБ")
                    fh.write(chunk)
            try:
                zf = zipfile.ZipFile(zpath)
            except zipfile.BadZipFile:
                raise ConnectorError(f"ГИС ОГД: слой {code} — ответ не архив SHP") from None
            with zf:
                for f in _shp_features(zf, code):
                    count += 1
                    geom = f.get("geometry")
                    fb = _geom_bbox(geom)
                    if not fb:
                        continue
                    props = f["properties"]
                    key = f"{self.map_name}:{code}:{norm_id(props.get('orbis_id') or props.get('id') or count)}"
                    if _overlaps(fb, query):
                        out.append({"type": "Feature", "geometry": geom, "properties": dict(props), "grado_key": key})
                    if tmp is None:
                        continue
                    small = fb[2] - fb[0] <= _CELL and fb[3] - fb[1] <= _CELL
                    cell = f"{math.floor(fb[0] / _CELL)}_{math.floor(fb[1] / _CELL)}" if small else "big"
                    line = (",".join(repr(v) for v in fb) + "\t" + key + "\t"
                            + json.dumps({"geometry": geom, "properties": props}, ensure_ascii=False, separators=(",", ":")) + "\n")
                    buf.setdefault(cell, []).append(line)
                    size += len(line)
                    if size > 48_000_000:           # ~50–100 МБ строк в памяти, дальше — на диск
                        flush()
            if tmp is not None:
                flush()
                (tmp / "_meta.json").write_text(json.dumps({"code": code, "map": self.map_name, "count": count, "cell": _CELL, "format": "shp"}), "utf-8")
                shutil.rmtree(grid, ignore_errors=True)
                tmp.replace(grid)
                tmp = None
        finally:
            Path(zpath).unlink(missing_ok=True)
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
                    # обрезанный полигон: рёбра на рамке — след обрезки, а не граница объекта (карта их не обводит)
                    clipped = g is not f["geometry"] and "Polygon" in g["type"]
                    cut.append({**f, "geometry": g, **({"grado_clip": list(query)} if clipped else {})})
            feats = cut
        return make_result(feats, {"code": code, "map": self.map_name, "bbox": ",".join(f"{v:.5f}" for v in query)},
                           source_doc=self.source_doc, notes=notes)

    def _cache_path(self, code):
        return self._cache_child(code, f"{code}.shp.gz")

    def _layer_bytes(self, code):
        """Слой целиком: из кэша, иначе скачать и закэшировать (gzip на диске)."""
        path = self._cache_path(code)
        if path and path.exists() and (time.time() - path.stat().st_mtime) < self.ttl:
            try:
                dec = zlib.decompressobj(wbits=31)
                data = _inflate(dec, path.read_bytes(), _MAX_LAYER)
                if not dec.eof:
                    raise EOFError("кэш недописан")
                return data, True
            except (OSError, EOFError, zlib.error, ConnectorError):
                path.unlink(missing_ok=True)       # недописанный кэш — скачать заново, а не падать до конца срока
        url = f"{self.base}/layers/{code}/export/?format=shp"
        if self.progress and self.transport is _http_get:
            raw = _http_get(url, progress=lambda got, total: self.progress(code, got, total, "download"))
        else:
            raw = self.transport(url)
        if self.progress:
            self.progress(code, len(raw), len(raw), "parse")
        if not zipfile.is_zipfile(io.BytesIO(raw)):       # страница ошибки портала не должна лечь в кэш на неделю
            raise ConnectorError(f"ГИС ОГД: слой {code} — ответ портала не архив SHP, попробуйте позже")
        if path:
            with _tmp_beside(path) as tmp:         # свой временный файл: две вкладки не склеят чужие хвосты
                tmp.write_bytes(gzip.compress(raw, 6))
        time.sleep(_PAUSE)
        return raw, False

    @staticmethod
    def _cut(v):
        return isinstance(v, str) and len(v.encode("utf-8")) >= 250

    def _long_texts(self, code, ids):
        """dBASE режет текст на 254 байтах: списки ВРИ ПЗЗ и ограничения ОКН приходят обрезанными. Полные строки
        берутся из выгрузки GeoJSON того же слоя (по orbis_id), но только для объектов ids. GeoJSON читается
        ПОТОКОМ по одному объекту: слой «Земельные участки» целиком в json.loads не помещался в 3 ГБ сервера
        (OOM 25.09.2026). Неудача — пустой словарь: слой всё равно нужен, тексты остаются обрезанными."""
        import codecs
        out = {}
        try:
            dec, text = json.JSONDecoder(), codecs.getincrementaldecoder("utf-8")()
            buf, started = "", False
            for chunk in self._chunks(f"{self.base}/layers/{code}/export/?format=geojson", code):
                buf += text.decode(chunk)
                if not started:
                    k = buf.find('"features"')
                    b = buf.find("[", k) if k >= 0 else -1
                    if b < 0:
                        buf = buf[-64:]
                        continue
                    buf, started = buf[b + 1:], True
                while True:
                    rest = buf.lstrip(" \r\n\t,")
                    if not rest or rest[0] == "]":
                        buf = rest
                        break
                    try:
                        obj, end = dec.raw_decode(rest)
                    except ValueError:              # объект ещё не докачан
                        buf = rest
                        break
                    buf = rest[end:]
                    props = obj.get("properties") or {}
                    oid = str(props.get("orbis_id"))
                    if oid in ids:
                        out[oid] = {k: v for k, v in props.items() if isinstance(v, str) and len(v) > 200}
        except Exception:
            return {}
        finally:
            time.sleep(_PAUSE)
        return out

    def _restore(self, props, full):
        src = full.get(str(props.get("orbis_id")))
        if not src:
            return props
        for k, v in props.items():
            w = src.get(k)
            if self._cut(v) and isinstance(w, str) and len(w) > len(v) and w.startswith(v.rstrip()[:50]):
                props[k] = w
        return props

    def _lines_path(self, code):
        return self._cache_child(code, f"{code}.shp.lines.gz")

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

    def fetch(self, bbox, code):
        """bbox = (west, south, east, north) WGS84; code — код слоя портала."""
        west, south, east, north = map(float, bbox)
        query = (west, south, east, north)
        _check_code(code)
        if self.map_name != "isogd":
            return self._fetch_stream(code, query)
        fast = self._from_lines(code, query)
        if fast is not None:
            return make_result(fast, {"code": code, "bbox": ",".join(f"{v:.5f}" for v in query)},
                               source_doc="ГИС ОГД Москвы (gisogd.mos.ru), выгрузка по экстенту", notes=[])
        raw, cached = self._layer_bytes(code)
        # слой идёт двумя проходами по SHP, без списка всех объектов в памяти: 1) какие объекты с обрезанным текстом;
        # 2) объекты по одному → строка построчного кэша (сразу на диск) и, если в области, в ответ
        out, count = [], 0
        try:
            zf = _zip_of(raw, code)
            _prj, recs = iter_zip(zf)
            cut_ids = {str(_full_names(r["properties"]).get("orbis_id")) for r in recs
                       if any(self._cut(v) for v in r["properties"].values())}
            full = self._long_texts(code, cut_ids) if cut_ids else {}
            lp = self._lines_path(code)
            with (_tmp_beside(lp) if lp else _nowhere()) as tmp, \
                    (gzip.open(tmp, "wt", encoding="utf-8", compresslevel=5) if lp else _nowhere()) as fh:
                for i, f in enumerate(_shp_features(zf, code, full_names=True)):
                    count += 1
                    geom = f.get("geometry")
                    fb = _geom_bbox(geom)
                    if not fb:
                        continue
                    props = self._restore(f.get("properties") or {}, full)
                    key = f"{code}:{norm_id(props.get('orbis_id') or props.get('id') or i)}"
                    if fh:
                        fh.write(",".join(repr(v) for v in fb) + "\t" + key + "\t"
                                 + json.dumps({"geometry": geom, "properties": props}, ensure_ascii=False, separators=(",", ":")) + "\n")
                    if _overlaps(fb, query):
                        out.append({"type": "Feature", "geometry": geom, "properties": dict(props), "grado_key": key})
        except Exception as e:
            if cached and self._cache_path(code):
                self._cache_path(code).unlink(missing_ok=True)   # следующая попытка скачает заново
            if isinstance(e, ConnectorError):
                raise
            if isinstance(e, (ValueError, KeyError, IndexError, struct.error, zipfile.BadZipFile)):
                raise ConnectorError(f"ГИС ОГД: слой {code} — архив SHP повреждён или не разобран") from None
            raise ConnectorError(f"ГИС ОГД: слой {code} не разобран: {clean_msg(e)}") from None

        notes = []
        if not cached:
            notes.append(f"слой {code} загружен целиком ({count} об., "
                         f"{len(raw)/1e6:.0f} МБ) — портал не фильтрует по области; "
                         f"дальше берётся из кэша")
        return make_result(
            out,
            {"code": code, "bbox": ",".join(f"{v:.5f}" for v in query)},
            source_doc="ГИС ОГД Москвы (gisogd.mos.ru), выгрузка по экстенту",
            notes=notes)
