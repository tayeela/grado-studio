"""Ядро студии: черчение (JSON с холста) → проект → ТЭП → альбом.

Клиент рисует в локальных метрах (ось Y вверх); здесь фигуры ложатся в
проект .grado (UTM, смещение ORIGIN), ТЭП считается движком из геометрии,
альбом собирается листами мастера территории.
"""

import math
import os
import ssl
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parents[2]
for mod in ("model", "compute", "reactive", "render", "geom", "layout",
            "connectors"):
    p = str(ROOT / "core" / mod)
    if p not in sys.path:
        sys.path.insert(0, p)
sys.path.insert(0, str(ROOT / "apps" / "wizard"))

from grado_compute.engine import Engine  # noqa: E402
from grado_geom import Path as GPath  # noqa: E402
from grado_geom import CurveError, PathError  # noqa: E402
from grado_layout import Document, render_document_pdf  # noqa: E402
from grado_model import Project  # noqa: E402
from grado_model import geometry  # noqa: E402
from grado_model.classifier import Classifier  # noqa: E402
from grado_model.tep_bridge import apply_to_engine  # noqa: E402
from grado_render import StyleSet  # noqa: E402
from grado_wizard.sheets import (MAP_RECT, apo_sheet,  # noqa: E402
                                 base_plan_sheet, fit_scale, location_sheet,
                                 ortho_sheet, tep_summary_sheet, title_sheet,
                                 SheetHeader, TextFrame)  # for stubs

ORIGIN = (413000.0, 6178000.0)
PRESET = ROOT / "core" / "compute" / "grado_compute" / "presets" / "moscow_krt.json"

# --- единая библиотека стилей (styles/default.json): холст + PDF + DXF ------
from grado_render import merged_library  # noqa: E402
from grado_render import style as _render_style  # noqa: E402
import json as _json  # noqa: E402

# Пользовательские правки эталонных знаков (глобальные для студии) — отдельный
# файл-оверрайд рядом с автосейвом; сам генератор ЛГР и его JSON не трогаем.
STYLE_OVERRIDES_PATH = Path(__file__).parent / "style_overrides.json"


def load_style_overrides():
    """Правки знаков с диска (пусто, если файла нет или он битый)."""
    try:
        with open(STYLE_OVERRIDES_PATH, encoding="utf-8") as fh:
            data = _json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def apply_style_overrides(overrides):
    """Применить правки знаков ко всей библиотеке (холст + PDF + DXF) и
    обновить снимок STYLE_LIB. Не пишет на диск — только в память."""
    global STYLE_LIB
    _render_style.set_style_overrides(overrides)
    STYLE_LIB = merged_library()


def save_style_overrides(overrides):
    """Сохранить правки знаков на диск (атомарно) и применить."""
    if not isinstance(overrides, dict):
        overrides = {}
    tmp = STYLE_OVERRIDES_PATH.with_suffix(".tmp")
    tmp.write_text(_json.dumps(overrides, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(STYLE_OVERRIDES_PATH)
    apply_style_overrides(overrides)


# default.json (базовые стили ГРАДО) + moscow_lgr.json (Эталон ЛГР,
# приказ Москомархитектуры от 10.03.2025 № 65) — единая системная библиотека;
# поверх — пользовательские правки знаков (если есть)
apply_style_overrides(load_style_overrides())
STYLE_LIB = merged_library()

# --- источники: снимки (SnapshotStore) + провенанс + журнал (шаг 6) ---------
# Импорт НСПД/ФГИС ТП фиксирует неизменяемый датированный снимок (sha256),
# каждый объект несёт провенанс (source/date/doc/snapshot), переимпорт
# сравнивается с прошлым снимком (diff). Стор — на диске рядом с кэшем
# тайлов (в .gitignore). Тесты подменяют SOURCE_STORE на временный.
from grado_connectors import (GisogdZip, NspdCapture, SnapshotStore,  # noqa: E402
                              diff as _snap_diff, has_changes as _has_changes)
from grado_connectors.contract import make_result  # noqa: E402
from grado_connectors.fgistp import FgistpConnector  # noqa: E402

SOURCE_STORE = SnapshotStore(Path(__file__).parent / ".sources")
_PROV_SOURCES = {"nspd", "fgistp", "gisogd", "osm", "import"}  # допустимые в модели


def _iter_lonlat(geom):
    """Все пары координат геометрии GeoJSON (любой вложенности)."""
    if not geom:
        return
    stack = [geom.get("coordinates")]
    while stack:
        c = stack.pop()
        if not isinstance(c, (list, tuple)) or not c:
            continue
        if isinstance(c[0], (int, float)):
            yield c[0], c[1]
        else:
            stack.extend(c)


def _territory_key(features):
    """Ключ территории по габаритам (WGS84, ~100 м): один и тот же для
    переимпорта той же территории (даже с иным составом объектов),
    разный — для другой территории. Без него snapshot.latest() сравнивал
    бы НЕсвязанные захваты (НСПД не несёт различающего ключа в params)."""
    xs, ys = [], []
    for f in features:
        for lon, lat in _iter_lonlat(f.get("geometry")):
            xs.append(lon)
            ys.append(lat)
    if not xs:
        return None
    return f"{min(xs):.3f},{min(ys):.3f},{max(xs):.3f},{max(ys):.3f}"


def _snapshot(connector, result):
    """Сохраняет снимок + diff против прошлого снимка того же источника.

    Возвращает (manifest, diff|None). Идемпотентно: тот же контент за тот
    же день — тот же снимок, diff пустой → None."""
    prev = SOURCE_STORE.latest(connector.name, result.get("params"))
    d = None
    if prev is not None:
        d = _snap_diff(SOURCE_STORE.features(prev["id"]), result["features"])
        if not _has_changes(d):
            d = None
    sid = SOURCE_STORE.save(connector, result)
    return SOURCE_STORE.manifest(sid), d


def _prov(manifest):
    """Провенанс объекта из манифеста снимка (для f['prov'] и .grado)."""
    return {"source": manifest["source"],
            "source_date": manifest["fetched_at"][:10],
            "source_doc": manifest.get("source_doc") or manifest["id"],
            "snapshot": manifest["id"]}


def sources_journal():
    """Журнал источников: список манифестов снимков (для UI и /api/sources)."""
    return [{"id": m["id"], "source": m["source"], "connector": m["connector"],
             "count": m["count"], "fetched_at": m["fetched_at"],
             "sha8": m["sha256"][:8], "source_doc": m.get("source_doc"),
             "notes": m.get("notes", [])}
            for m in SOURCE_STORE.list()]


def dxf_layers_from_styles():
    """code классификатора → (имя слоя DXF, цвет ACI) из библиотеки стилей."""
    layers = {}
    for s in STYLE_LIB["styles"].values():
        dxf = s.get("dxf")
        if dxf:
            for code in s.get("codes", []):
                layers[code] = (dxf["name"], dxf["color"])
    fb = STYLE_LIB["fallback"].get("dxf")
    fallback = (fb["name"], fb["color"]) if fb else None
    return layers, fallback


def frontend_styles():
    """Стили для холста студии: style_id → {fill, stroke, width(px), dash(px),
    hatch, label_field, ...}. Прозрачность заливки свёрнута в rgba().

    hatch: true (легаси, 45° цветом обводки) ИЛИ объект Эталона ЛГР
    {angle, cross, spacing_px, color}. Метаданные lgr_* и title/group идут
    в UI (выбор стиля из библиотеки в панели форматирования/свойств)."""
    out = {}
    for sid, s in STYLE_LIB["styles"].items():
        fill, op = s.get("fill"), s.get("fill_opacity")
        if fill and op is not None and op < 1:
            r, g, b = (int(fill[i:i + 2], 16) for i in (1, 3, 5))
            fill = f"rgba({r},{g},{b},{op})"
        entry = {"stroke": s.get("stroke"), "width": s.get("width_px", 1)}
        if fill:
            entry["fill"] = fill
        if s.get("dash_px"):
            entry["dash"] = s["dash_px"]
        h = s.get("hatch")
        if isinstance(h, dict):
            entry["hatch"] = {k: h[k] for k in
                              ("angle", "cross", "spacing_px", "color") if k in h}
        elif h:
            entry["hatch"] = True
        if s.get("label_field"):
            entry["label_field"] = s["label_field"]
        if s.get("line_label"):
            entry["line_label"] = s["line_label"]
        lm = s.get("line_marker")
        if lm:
            entry["line_marker"] = {"shape": lm["shape"],
                                    "period": lm.get("period_px", 40),
                                    "size": lm.get("size_px", 4),
                                    "dir": lm.get("dir", "in")}
        if s.get("double_px"):
            entry["double"] = s["double_px"]
        if s.get("title"):
            entry["title"] = s["title"]
        if s.get("group"):
            entry["group"] = s["group"]
        if s.get("lgr_code") is not None:
            entry["lgr_code"] = s["lgr_code"]
        out[sid] = entry
    return out

# --- тайловая подложка (кэш общий: холст студии и листы альбома) -----------
# Локальный однопользовательский инструмент = «лёгкое использование» по
# Tile Usage Policy OSM; при промышленной нагрузке — платный/self-hosted.
TILE_CACHE = Path(__file__).parent / ".tile_cache"
TILE_UA = "grado-studio/0.1 (local single-user desktop tool for urban planning)"
MAX_UNDERLAY_TILES = 130

# Сборки Python.org для macOS не подхватывают системную цепочку доверия —
# без certifi HTTPS падает с CERTIFICATE_VERIFY_FAILED. Проверка
# сертификата остаётся включённой — меняется только источник CA.
try:
    import certifi
    TILE_SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    TILE_SSL_CTX = ssl.create_default_context()


# Кэш валиден только целиком: «файл существует» — не признак (обрыв записи
# при убитом процессе оставляет обрезанный файл, который иначе никогда не
# перекачается и даёт вечную дырку в мозаике).
_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_PNG_END = b"IEND\xaeB`\x82"


def _valid_png(path):
    try:
        data = path.read_bytes()
    except OSError:
        return False
    return data[:8] == _PNG_SIG and data[-8:] == _PNG_END


def _valid_jpeg(data):
    return data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"


def _tmp_name(path):
    # уникально на поток: параллельные выгрузки не пишут в один файл
    return path.with_name(
        f".{path.stem}-{os.getpid()}-{threading.get_ident()}{path.suffix}")


# Источники подложки (все XYZ/WMTS без авторизации, порядок осей z/y/x у
# растровых спутников, z/x/y у OSM):
#   osm — карта OpenStreetMap (PNG);
#   sat — спутник ESRI World Imagery (JPEG), высокое разрешение (Maxar);
#   s2  — Sentinel-2 cloudless от EOX, программа Copernicus (JPEG): 10 м,
#         безоблачная мозаика 2023 г., свежее ESRI на многих территориях.
#         Тайлы EOX WMTS (GoogleMapsCompatible = EPSG:3857), выше z13 мягко
#         апсемплятся (10 м — предел детализации Sentinel-2).
# Все — для лёгкого локального просмотра; при промышленной нагрузке — свой
# сервер/ключ. Источники добавлены из каталога открытых геоданных
# (bella-mir.github.io/openSpData, раздел «Спутниковые снимки»).
TILE_SOURCES = {
    "osm": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "sat": ("https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"),
    "s2": ("https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/"
           "default/GoogleMapsCompatible/{z}/{y}/{x}.jpg"),
}
TILE_ATTRIBUTIONS = {
    "osm": "© OpenStreetMap contributors",
    "sat": "Esri, Maxar, Earthstar Geographics",
    "s2": "Sentinel-2 cloudless by EOX (Copernicus 2023)",
}


def _valid_tile(path):
    try:
        data = path.read_bytes()
    except OSError:
        return False
    return ((data[:8] == _PNG_SIG and data[-8:] == _PNG_END) or
            (data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"))


def _tile_cache_path(z, x, y, source):
    return TILE_CACHE / source / str(z) / str(x) / f"{y}.img"


def fetch_tile(z, x, y, source="osm"):
    """Тайл подложки выбранного источника (карта OSM | спутник ESRI).

    Формат исходника разный (OSM PNG, ESRI JPEG) — кэшируем байты как есть
    (расширение .img), валидность по сигнатуре обоих форматов. Запись
    атомарна (tmp + os.replace), кэш раздельный по источнику."""
    tmpl = TILE_SOURCES.get(source) or TILE_SOURCES["osm"]
    cache_path = _tile_cache_path(z, x, y, source)
    if not _valid_tile(cache_path):
        req = urllib.request.Request(tmpl.format(z=z, x=x, y=y),
                                     headers={"User-Agent": TILE_UA})
        with urllib.request.urlopen(req, timeout=10,
                                    context=TILE_SSL_CTX) as resp:
            data = resp.read()
        if not (data[:8] == _PNG_SIG or data[:2] == b"\xff\xd8"):
            raise RuntimeError("tile upstream: not an image")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = _tmp_name(cache_path)
        tmp.write_bytes(data)
        os.replace(tmp, cache_path)
    return cache_path


def tile_response(z, x, y, source="osm"):
    """(байты, content-type) тайла подложки для HTTP-ответа."""
    data = fetch_tile(z, x, y, source).read_bytes()
    return data, ("image/png" if data[:8] == _PNG_SIG else "image/jpeg")


def _png_to_jpeg(png_path, out_path):
    """PNG→JPEG кросс-платформенно: Pillow (если есть) → sips (macOS).

    Возвращает True при успехе. Оба пути опциональны: на Windows без Pillow
    OSM-подложка в PDF просто не появится (спутник ESRI уже JPEG и работает),
    экспорт не падает — вызывающий tile_underlay деградирует по OSError."""
    # 1) Pillow — кросс-платформенно (Windows/Linux/macOS), если установлен
    try:
        from PIL import Image
        with Image.open(png_path) as im:
            im.convert("RGB").save(out_path, "JPEG", quality=85)
        return True
    except ImportError:
        pass
    except Exception:
        return False
    # 2) sips — системный конвертер macOS
    try:
        r = subprocess.run(
            ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "85",
             str(png_path), "--out", str(out_path)], capture_output=True)
        return r.returncode == 0 and Path(out_path).exists()
    except FileNotFoundError:
        # нет ни Pillow, ни sips (типично для Windows без Pillow) —
        # сигналим как «тайл недоступен», tile_underlay это ловит (OSError)
        raise OSError("нет конвертера PNG→JPEG (Pillow или sips) для растровой "
                      "подложки в PDF; поставьте Pillow или используйте спутник")


def _tile_jpeg(z, x, y, source="osm"):
    """JPEG тайла для вставки в PDF (DCTDecode кладёт JPEG как есть).

    ESRI (sat) уже отдаёт JPEG — вставляется как есть. OSM (osm) отдаёт PNG —
    конвертирует Pillow или sips (см. _png_to_jpeg), результат кэшируется
    рядом. Запись во временный файл атомарна: два параллельных экспорта с
    одним --out роняли бы один из rename'ов — поэтому цель у каждого вызова
    своя, в кэш её кладёт os.replace."""
    img = fetch_tile(z, x, y, source)
    data = img.read_bytes()
    if data[:2] == b"\xff\xd8":            # уже JPEG (ESRI) — как есть
        return data
    png = img
    jpg = png.with_suffix(".jpg")
    try:
        data = jpg.read_bytes()
    except OSError:
        data = b""
    if _valid_jpeg(data):
        return data
    tmp = _tmp_name(jpg)
    try:
        ok = _png_to_jpeg(png, tmp)
        data = tmp.read_bytes() if ok and tmp.exists() else b""
        if not _valid_jpeg(data):
            raise RuntimeError("конвертация тайла PNG→JPEG не удалась")
        os.replace(tmp, jpg)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return data


def _tile_xy(lon, lat, z):
    n = 2 ** z
    xt = (lon + 180.0) / 360.0 * n
    yt = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return xt, yt


def _tile_lonlat(xt, yt, z):
    n = 2 ** z
    lon = xt / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * yt / n))))
    return lon, lat


def tile_underlay(center_utm, map_rect, scale, dpi=150, source="osm"):
    """Image-операции подложки (карта OSM | спутник ESRI) под карто-фрейм
    листа (мм).

    Точная цепочка: UTM ↔ WGS84 (Snyder), каждый тайл ставится
    параллелограммом по трём углам — Web Mercator повёрнут к сетке UTM
    на сближение меридианов (~1.1° в Москве), осевое размещение дало бы
    швы между тайлами. Сети нет → пустой список, лист без подложки."""
    from grado_connectors.crs import utm37n_to_wgs84, wgs84_to_utm37n

    fx, fy, fw, fh = map_rect
    k = 1000.0 / scale                       # мм листа на метр местности
    cx, cy = center_utm
    hw, hh = fw / 2.0 / k, fh / 2.0 / k      # полурамка в метрах

    def to_mm(pt_utm):
        return (fx + fw / 2.0 + (pt_utm[0] - cx) * k,
                fy + fh / 2.0 - (pt_utm[1] - cy) * k)

    corners = [utm37n_to_wgs84(cx + sx * hw, cy + sy * hh)
               for sx in (-1, 1) for sy in (-1, 1)]
    lon0, lon1 = min(c[0] for c in corners), max(c[0] for c in corners)
    lat0, lat1 = min(c[1] for c in corners), max(c[1] for c in corners)
    lat_mid = (lat0 + lat1) / 2.0
    # зум: разрешение местности ≈ dpi точек на дюйм листа
    m_per_px = scale / 1000.0 * 25.4 / dpi
    z = min(19, max(3, math.ceil(math.log2(
        156543.03392804097 * math.cos(math.radians(lat_mid)) / m_per_px))))
    while True:
        x0t, y1t = _tile_xy(lon0, lat0, z)   # юг → номер строки больше
        x1t, y0t = _tile_xy(lon1, lat1, z)
        if z <= 3 or ((int(x1t) - int(x0t) + 1) * (int(y1t) - int(y0t) + 1)
                      <= MAX_UNDERLAY_TILES):
            break
        z -= 1
    # Политика сбоев: одиночный — дырка в мозаике; сетевая ошибка гасит
    # дальнейшие загрузки (остальное только из кэша, без 10-секундных
    # таймаутов на каждый тайл); больше половины сбоев — лист без
    # подложки целиком (полупустой «Ортофотоплан» хуже его отсутствия).
    xs_range = range(int(x0t), int(x1t) + 1)
    ys_range = range(int(y0t), int(y1t) + 1)
    total = len(xs_range) * len(ys_range)
    ops, failed, net_down = [], 0, False
    for xt in xs_range:
        for yt in ys_range:
            if net_down and not _valid_tile(_tile_cache_path(z, xt, yt, source)):
                failed += 1
                continue
            try:
                data = _tile_jpeg(z, xt, yt, source)
            except OSError:
                net_down = True
                failed += 1
                continue
            except Exception:
                failed += 1
                continue
            tl = to_mm(wgs84_to_utm37n(*_tile_lonlat(xt, yt, z)))
            tr = to_mm(wgs84_to_utm37n(*_tile_lonlat(xt + 1, yt, z)))
            bl = to_mm(wgs84_to_utm37n(*_tile_lonlat(xt, yt + 1, z)))
            ops.append({"op": "image", "data": data, "quad": (tl, tr, bl)})
    if failed * 2 >= total:
        return []
    return ops


def _project_underlay(project, map_rect, scale, source="osm"):
    """Подложка для карто-фрейма, центрированного по габаритам проекта."""
    from grado_render import project_extent
    x0, y0, x1, y1 = project_extent(project)
    return tile_underlay(((x0 + x1) / 2.0, (y0 + y1) / 2.0), map_rect, scale,
                         source=source)

KIND_TO_CODE = {
    "boundary": "terr.boundary",
    "restrict": "terr.restrict",
    "zone": "tp.func_zone",
    "building": "oks.building",
    "redline": "pp.red_line",
    "social": "social.object",
    "public": "pp.placement_zone",
    "parcel": "cad.parcel",
}

# Реестр слоёв (MODEL-01b): layer_id → семантический класс + метаданные.
# Маршрутизация объекта холста в слой модели идёт по layer_id (не по kind);
# kind остаётся транспортом СХЕМЫ атрибутов/геометрии (KIND_ATTRS/_geom_for).
# Два слоя одного класса (source.fgistp.func_zones и project.tp.func_zone)
# теперь живут раздельно. stage/style_id по умолчанию — из классификатора.
LAYER_TEMPLATES = {
    "project.territory.boundary": {"code": "terr.boundary"},
    "project.tp.func_zone":       {"code": "tp.func_zone"},
    "project.apo.public_zones":   {"code": "pp.placement_zone"},
    "source.constraints.restrict": {"code": "terr.restrict"},
    "source.nspd.parcels":        {"code": "cad.parcel"},
    "project.apo.buildings":      {"code": "oks.building"},
    "project.apo.red_lines":      {"code": "pp.red_line"},
    "project.social.objects":     {"code": "social.object"},
    "source.fgistp.func_zones":   {"code": "tp.func_zone", "stage": "existing",
                                   "source_kind": "fgistp",
                                   "title": "ФГИС ТП: функциональные зоны"},
    "source.gisogd.func_zones":   {"code": "tp.func_zone", "stage": "existing",
                                   "source_kind": "gisogd",
                                   "title": "ГИС ОГД: функциональные зоны"},
    "source.gisogd.red_lines":    {"code": "pp.red_line", "stage": "existing",
                                   "source_kind": "gisogd",
                                   "title": "ГИС ОГД: красные линии"},
    "source.gisogd.restrict":     {"code": "terr.restrict", "stage": "existing",
                                   "source_kind": "gisogd",
                                   "title": "ГИС ОГД: зоны с особыми условиями"},
    # приёмники «Данных по области» (прямые открытые источники, fetch_extent)
    "source.nspd.buildings":      {"code": "oks.building", "stage": "existing",
                                   "source_kind": "nspd",
                                   "title": "НСПД: здания"},
    "source.nspd.constructions":  {"code": "generic.line", "stage": "existing",
                                   "source_kind": "nspd",
                                   "title": "НСПД: сооружения"},
    "source.nspd.zouit":          {"code": "terr.restrict", "stage": "existing",
                                   "source_kind": "nspd",
                                   "title": "НСПД: ЗОУИТ"},
    "source.osm.roads":           {"code": "generic.line", "stage": "existing",
                                   "source_kind": "osm",
                                   "title": "OSM: дороги и улицы"},
    "source.osm.buildings":       {"code": "oks.building", "stage": "existing",
                                   "source_kind": "osm",
                                   "title": "OSM: здания"},
    "source.osm.landuse":         {"code": "generic.polygon", "stage": "existing",
                                   "source_kind": "osm",
                                   "title": "OSM: землепользование"},
    "source.osm.water":           {"code": "generic.polygon", "stage": "existing",
                                   "source_kind": "osm",
                                   "title": "OSM: вода"},
}
# слой по умолчанию для kind (legacy-объекты без layer_id)
_KIND_TO_LAYER = {"boundary": "project.territory.boundary",
                  "restrict": "source.constraints.restrict",
                  "zone": "project.tp.func_zone",
                  "building": "project.apo.buildings",
                  "redline": "project.apo.red_lines",
                  "social": "project.social.objects",
                  "public": "project.apo.public_zones",
                  "parcel": "source.nspd.parcels"}
# semantic_class → layer_id для round-trip (какой слой отдать при открытии)
_CODE_TO_LAYER = {t["code"]: lid for lid, t in LAYER_TEMPLATES.items()
                  if lid.startswith("project.")}

KIND_ATTRS = {
    "boundary": lambda p: {"name": p.get("name", "Территория")},
    "restrict": lambda p: {"kind": p.get("kind", "ограничение")},
    "zone": lambda p: {"zone_code": p.get("zone_title", "Ж"),
                       "zone_title": p.get("zone_title", "Ж-1")},
    "building": lambda p: {"purpose": p.get("purpose", "МКД"),
                           "floors": int(p.get("floors", 9))},
    "redline": lambda p: {"status": "устанавливаемая"},
    "social": lambda p: {"kind": p.get("kind", "ОО+ДОО"),
                         "capacity": int(p.get("capacity", 0))},
    "public": lambda p: {"purpose": p.get("purpose", "Общественный центр")},
    "parcel": lambda p: {"cad_num": p.get("cad_num"),
                         "category": p.get("category"),
                         "vri": p.get("vri")},
    # обычный (generic) слой — создан по геометрии без семантической роли;
    # атрибуты классификатора пустые (свои поля живут на холсте), в ТЭП не идёт
    "generic": lambda p: {},
}


def _shift(pts):
    return [[x + ORIGIN[0], y + ORIGIN[1]] for x, y in pts]


def _geom_for(feature):
    kind = feature["kind"]
    if kind == "social":
        x, y = feature["point"]
        return {"type": "Point", "coordinates": [x + ORIGIN[0], y + ORIGIN[1]]}
    if kind == "redline":
        line = [tuple(p) for p in feature["line"]]
        radius = float(feature.get("props", {}).get("radius") or 0)
        if radius > 0 and len(line) >= 3:
            # сопряжение углов тангенциальными дугами (ядро geom)
            try:
                line = GPath.fillet_polyline(line, radius).linearize(0.05)
            except (PathError, CurveError):
                pass  # радиус не помещается — оставляем ломаную
        return {"type": "LineString", "coordinates": _shift(line)}
    if "arc" in feature:
        a = feature["arc"]
        import math
        n = 16
        pts = []
        for i in range(n+1):
            ang = a.get("a0", 0) + a.get("sweep", 0) * i / n
            x = a["cx"] + a["r"] * math.cos(ang)
            y = a["cy"] + a["r"] * math.sin(ang)
            pts.append((x, y))
        return {"type": "LineString", "coordinates": _shift(pts)}
    if "circle" in feature:
        c = feature["circle"]
        import math
        n = 32
        pts = []
        for i in range(n + 1):
            ang = i * 2 * math.pi / n
            x = c["cx"] + c["r"] * math.cos(ang)
            y = c["cy"] + c["r"] * math.sin(ang)
            pts.append((x, y))
        # closed for ring-like use, but as LineString for generic
        return {"type": "LineString", "coordinates": _shift(pts)}
    # generic/неизвестные виды несут геометрию в самом объекте: линия/точка
    # без этих веток падала KeyError 'ring' и молча выпадала из экспорта.
    # Семантические полигональные виды (zone/building/…) сюда не пускаем:
    # зона с line-геометрией — повреждённый объект (v0.42.1), а не линия
    if kind not in KIND_TO_CODE:
        if "line" in feature:
            return {"type": "LineString", "coordinates": _shift(feature["line"])}
        if "point" in feature:
            x, y = feature["point"]
            return {"type": "Point", "coordinates": [x + ORIGIN[0], y + ORIGIN[1]]}
    ring = _shift(feature["ring"])
    if ring[0] != ring[-1]:
        ring.append(list(ring[0]))
    return {"type": "Polygon", "coordinates": [ring]}


def _route(feature, templates):
    """(layer_id, template) объекта холста → слой модели.

    По явному layer_id (реестр — встроенный + пользовательские слои из
    панели студии), иначе legacy по kind. Возвращает (None, None) для
    объектов без слоя (напр. размеры-аннотации)."""
    lid = feature.get("layer_id")
    if lid in templates:
        return lid, templates[lid]
    lid = _KIND_TO_LAYER.get(feature.get("kind"))
    return (lid, templates[lid]) if lid in templates else (None, None)


# пользовательские поля атрибутивной таблицы студии → колонки .grado.
# Тип холста (int/real/text/date/bool) отображается в тип gpkg для колонки
# и используется для приведения значения; дата/булево хранятся как в QGIS
# (ISO-строка / 0|1).
_FIELD_GPKG_TYPE = {"int": "integer", "integer": "integer", "real": "number",
                    "number": "number", "float": "number", "text": "string",
                    "string": "string", "date": "string", "bool": "integer",
                    "boolean": "integer"}


def _field_col_id(name):
    """Имя поля холста → безопасное имя колонки gpkg (кавычки/переводы строк
    убираем, длину ограничиваем; кириллицу оставляем — QGIS её понимает)."""
    s = str(name or "").replace('"', "").replace("\n", " ").replace("\r", " ").strip()
    return s[:60] or None


def _cast_field(ftype, raw):
    """Приведение значения поля к его типу (или None, если пусто/не парсится)."""
    if raw is None or raw == "":
        return None
    ft = str(ftype or "text").lower()
    if ft in ("int", "integer"):
        try:
            return int(float(raw)) if not isinstance(raw, bool) else int(raw)
        except (TypeError, ValueError):
            return None
    if ft in ("real", "number", "float"):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    if ft in ("bool", "boolean"):
        return 1 if raw in (True, 1, "1", "true", "True", "да") else 0
    return str(raw)


def _manifest_fields(spec):
    """fields манифеста слоя [{name, type}] → внутренний формат колонок."""
    fields = []
    for fd in (spec.get("fields") or []):
        col = _field_col_id(fd.get("name"))
        if not col:
            continue
        ftype = fd.get("type", "text")
        fields.append({"id": col, "name": fd.get("name"), "ftype": ftype,
                       "gtype": _FIELD_GPKG_TYPE.get(str(ftype).lower(), "string")})
    return fields


def _user_layer_templates(layers):
    """Слои, созданные в панели студии («+ слой»), → шаблоны маршрутизации.

    layers — [{layer_id, code, title, stage, style_id, fields}], присылается с
    холста при каждом экспорте (там живёт единственная копия). Встроенные
    LAYER_TEMPLATES не переопределяются (code/title/stage builtin — закон);
    исключение — fields: у слоёв-приёмников «Данных по области» появляются
    свои столбцы (полная атрибуция НСПД), они мержатся В КОПИЮ builtin-шаблона.
    fields — [{name, type}] произвольных полей атрибутивной таблицы."""
    out = {}
    for spec in (layers or []):
        lid = spec.get("layer_id")
        code = spec.get("code")
        if not lid or not code:
            continue
        if lid in LAYER_TEMPLATES:
            fields = _manifest_fields(spec)
            if fields:
                out[lid] = {**LAYER_TEMPLATES[lid], "fields": fields}
            continue
        out[lid] = {"code": code, "title": spec.get("title"),
                    "stage": spec.get("stage"), "style_id": spec.get("style_id"),
                    "fields": _manifest_fields(spec)}
    return out


def build_project(path, name, features, layers=None, project_styles=None, project_custom_kinds=None, undo_stack=None, redo_stack=None):
    project = Project.create(path, name)
    if project_styles:
        try:
            project.set_meta("project_styles", _json.dumps(project_styles))
        except Exception:
            pass
    if project_custom_kinds:
        try:
            project.set_meta("project_custom_kinds", _json.dumps(project_custom_kinds))
        except Exception:
            pass
    if undo_stack is not None:
        try:
            project.set_meta("studio_undo_stack", _json.dumps(undo_stack))
        except Exception:
            pass
    if redo_stack is not None:
        try:
            project.set_meta("studio_redo_stack", _json.dumps(redo_stack))
        except Exception:
            pass
    # ensure journal tables for reactive
    try:
        from grado_reactive import Journal
        Journal(project.conn)
    except Exception:
        pass
    # порядок: augmented-копии builtin (builtin+fields) должны победить голый
    # builtin; подмена code/title невозможна — санация в _user_layer_templates
    templates = {**LAYER_TEMPLATES, **_user_layer_templates(layers)}
    made = {}  # layer_id → Layer
    for f in features:
        lid, tmpl = _route(f, templates)
        if lid is None:
            continue
        tfields = tmpl.get("fields") or []
        if lid not in made:
            made[lid] = project.add_layer(
                tmpl["code"], layer_id=lid, title=tmpl.get("title"),
                stage=tmpl.get("stage"), style_id=tmpl.get("style_id"),
                source_kind=tmpl.get("source_kind"),
                fields=[{"id": fd["id"], "type": fd["gtype"]} for fd in tfields])
        # неизвестный вид (напр. из будущей версии) не должен ронять экспорт —
        # пустые атрибуты как у обычного (generic) слоя
        props = f.get("props", {})
        attrs = KIND_ATTRS.get(f["kind"], KIND_ATTRS["generic"])(props)
        # произвольные поля атрибутивной таблицы студии → колонки .grado
        for fd in tfields:
            attrs[fd["id"]] = _cast_field(fd["ftype"], props.get(fd["name"]))
        # провенанс из импорта переносится в модель (source/date/doc),
        # per-object стиль — в колонку style_id
        prov = f.get("prov") or {}
        source = prov.get("source") if prov.get("source") in _PROV_SOURCES else "manual"
        # один повреждённый объект (напр. kind не совпадает с реальной
        # геометрией — старый холст-баг мог такое насохранять) не должен
        # ронять весь экспорт — тот же принцип деградации, что у tile_underlay
        # при сетевых сбоях: пропускаем объект, продолжаем сборку остальных.
        try:
            geom = _geom_for(f)
        except (KeyError, IndexError, TypeError, ValueError) as e:
            print(f"build_project: пропущен повреждённый объект id={f.get('id')} "
                 f"kind={f.get('kind')!r} ({e!r})", file=sys.stderr)
            continue
        # arc / circle params for roundtrip (single JSON attr)
        if "arc" in f:
            try:
                attrs["arc"] = _json.dumps(f["arc"])
            except Exception:
                pass
        if "circle" in f:
            try:
                attrs["circle"] = _json.dumps(f["circle"])
            except Exception:
                pass
        made[lid].add_feature(
            geom, attrs=attrs, source=source,
            source_date=prov.get("source_date"), source_doc=prov.get("source_doc"),
            style_id=f.get("style_id"))
    return project


def _ring_area_ha(feature):
    return geometry.area({"type": "Polygon",
                          "coordinates": [feature["ring"]]}) / 10000.0


# Классификатор — реестр ролей слоёв (tep_role, topology). ТЭП считается
# по ролям, а не по литералам kind (docs/fixes-geometry-layout.md, шаг 4):
# добавление нового слоя-здания = запись в классификаторе, не правка кода.
CLASSIFIER = Classifier.load()


def _class_of(feature):
    """Класс классификатора объекта холста (через мост kind → код)."""
    code = KIND_TO_CODE.get(feature.get("kind"))
    if code is None:
        return None
    try:
        return CLASSIFIER.get(code)
    except Exception:
        return None


def _role_areas(features):
    """{tep_role: суммарная площадь в га} по полигональным слоям с ролью."""
    out = {}
    for f in features:
        cls = _class_of(f)
        if cls and cls.tep_role and "ring" in f:
            out[cls.tep_role] = out.get(cls.tep_role, 0.0) + _ring_area_ha(f)
    return out


def make_engine(features, params=None):
    engine = Engine.from_file(PRESET)
    # площади входов ТЭП — из ролей слоёв, не из kind
    areas = _role_areas(features)
    inputs = {r: round(a, 4) for r, a in areas.items() if r in engine.inputs}
    if inputs.get("terr_area", 0) == 0:
        inputs.pop("terr_area", None)  # пустой холст → дефолт пресета
    engine.set_inputs(**inputs)
    for key in ("density", "ratio_zh", "percent_vpp"):
        if params and params.get(key) is not None:
            engine.set_input(key, float(params[key]))
    return engine


def compute_tep(features, params=None):
    """Живой ТЭП: нормативный расчёт + факт по посадке зданий."""
    engine = make_engine(features, params)
    fact_spp = 0.0
    for f in features:
        cls = _class_of(f)
        if cls and cls.tep_role == "building_footprint" and "ring" in f:
            floors = int(f.get("props", {}).get("floors", 9))
            fact_spp += _ring_area_ha(f) * 10000 * floors / 1000.0  # тыс. м²
    calc_area = engine.value("calc_area")
    results = engine.results()
    # basic rule engine checks (фаза 4)
    checks = []
    dens = round(fact_spp / calc_area, 2) if calc_area > 0 else 0
    if dens > 40:
        checks.append({"title": "Плотность", "ok": False, "msg": f"Высокая {dens} >40 — проверить МНГП и комфорт"})
    if dens < 10:
        checks.append({"title": "Плотность", "ok": False, "msg": f"Низкая {dens} — возможно неэффективно"})
    # пример из констант пресета
    pop = next((r["value"] for r in results if r["id"] == "population"), 0)
    if pop > 0:
        doo_need = round(44 * pop / 1000)
        if doo_need > 0:
            checks.append({"title": "ДОО", "ok": True, "msg": f"Потребность ~{doo_need} мест (порог 100)"})
    # radii thresholds example
    for r in results:
        if r["id"] == "doo_places" and r["value"] == 0 and pop > 1000:
            checks.append({"title": "Радиусы ДОО", "ok": False, "msg": "Потребность ниже порога — проверить размещение"})
        if r["id"] == "school_places" and r["value"] == 0 and pop > 2000:
            checks.append({"title": "Радиусы школ", "ok": False, "msg": "Потребность ниже порога — проверить размещение"})
    return {
        "inputs": {"terr_area": engine.value("terr_area"),
                   "restrict_area": engine.value("restrict_area")},
        "results": results,
        "fact": {
            "spp": round(fact_spp, 1),
            "density": dens,
        },
        "zones": zones_report(features),
        "checks": checks,
    }


def make_album(features, name, params=None, basemap=False, layers=None,
               basemap_source="osm", canvas_styles=None, project_styles=None,
               album_config=None):
    with tempfile.TemporaryDirectory() as tmp:
        project = build_project(Path(tmp) / "studio.grado", name, features, layers, project_styles=project_styles)
        engine = make_engine(features, params)
        apply_to_engine(project, engine)  # уточнение площадей по слоям проекта
        for key in ("density", "ratio_zh", "percent_vpp"):
            if params and params.get(key) is not None:
                engine.set_input(key, float(params[key]))
        doc = Document(name, meta={"org": "ГРАДО", "stage": "АГК"})
        # canvas_styles — inline-знаки «как на холсте» (режим выпуска студии):
        # объекты несут синтетический style_id, а сам знак приходит здесь
        # project_styles — кастомные стили проекта, доступны и в стандартном режиме
        id_styles = {}
        if project_styles:
            id_styles.update(project_styles)
        if canvas_styles:
            id_styles.update(canvas_styles)
        doc.styles = StyleSet(id_styles=id_styles)

        cfg = album_config or {}
        sheet_list = cfg.get('sheets') or ['title', 'location', 'base', 'apo', 'tep']
        title_p = cfg.get('title') or {'org': 'ГРАДО', 'city_year': 'Москва / 2026'}

        page_builders = {
            'title': lambda pno: title_sheet(doc, org=title_p.get('org', 'ГРАДО'), city_year=title_p.get('city_year', 'Москва / 2026')),
            'location': lambda pno: location_sheet(doc, project, engine.value("terr_area"), pno),
            'base': lambda pno: base_plan_sheet(doc, project, pno),
            'apo': lambda pno: apo_sheet(doc, project, engine, pno),
            'tep': lambda pno: tep_summary_sheet(doc, engine, pno),
            'ortho': lambda pno: ortho_sheet(doc, project, pno, underlay, TILE_ATTRIBUTIONS.get(basemap_source, TILE_ATTRIBUTIONS["osm"])) if underlay else None,
            'photo': lambda pno: _photo_sheet(doc, pno),
            'parking': lambda pno: _parking_sheet(doc, pno),
            'greenery': lambda pno: _greenery_sheet(doc, pno),
        }

        pages = []
        underlay = None
        if basemap:
            underlay = _project_underlay(project, MAP_RECT, fit_scale(project), source=basemap_source)
        for s in sheet_list:
            builder = page_builders.get(s)
            if builder:
                p = builder(len(pages) + 1)
                if p:
                    pages.append(p)

        # fallback if empty
        if not pages:
            pages = [
                title_sheet(doc, org=title_p.get('org', 'ГРАДО'), city_year=title_p.get('city_year', 'Москва / 2026')),
                location_sheet(doc, project, engine.value("terr_area"), 2),
                base_plan_sheet(doc, project, 3),
                apo_sheet(doc, project, engine, 4),
                tep_summary_sheet(doc, engine, 5),
            ]

        doc.pages = pages
        doc.sheet_titles = [s for s in sheet_list if page_builders.get(s)]
        pdf = render_document_pdf(doc, project, styles=doc.styles, engine=engine)
        project.close()
    return pdf

# Stub sheets for Phase 3 (extend as needed)
def _photo_sheet(doc, page_no):
    page = Page(A3_LANDSCAPE)
    page.frames = [
        SheetHeader(page, ["Фотофиксация"], page_no),
        TextFrame((28, 80, 350, 180), [
            "Фотофиксация существующих объектов и видовых точек.",
            "(Добавить изображения через редактор альбома или расширения.)"
        ], size=3)
    ]
    return page

def _parking_sheet(doc, page_no):
    page = Page(A3_LANDSCAPE)
    page.frames = [
        SheetHeader(page, ["Схема парковок"], page_no),
        TextFrame((28, 80, 350, 100), ["Парковки и подъезды (данные из слоёв проекта)"], size=3)
    ]
    return page

def _greenery_sheet(doc, page_no):
    page = Page(A3_LANDSCAPE)
    page.frames = [
        SheetHeader(page, ["Озеленение и благоустройство"], page_no),
        TextFrame((28, 80, 350, 100), ["Озеленение, насаждения (из слоёв проекта)"], size=3)
    ]
    return page


CODE_TO_KIND = {v: k for k, v in KIND_TO_CODE.items()}


def _to_local(pts):
    return [[x - ORIGIN[0], y - ORIGIN[1]] for x, y in pts]


def grado_to_features(path):
    """Открытие .grado обратно в студию: слои проекта → фигуры холста."""
    project = Project.open(path)
    name = project.meta("name")
    # ensure journal for reactive undo etc.
    try:
        from grado_reactive import Journal
        Journal(project.conn)
    except Exception:
        pass
    out = []
    for info in project.layers():
        kind = CODE_TO_KIND.get(info["code"])
        if kind is None:
            code = info["code"]
            if code.startswith("generic."):
                kind = code.split(".")[-1]  # "point" etc, or keep generic
            else:
                continue
        # layer_id из модели → холст; если слой не из реестра, отдаём его id
        layer_id = info["layer_id"]
        style_of_layer = info.get("style_id")
        for f in project.layer_by_id(layer_id).features():
            geom = f["geom"]
            if not geom:
                continue
            props = {k: v for k, v in f["attrs"].items() if v is not None}
            # провенанс из модели → холст (source != manual означает импорт)
            prov = None
            if f.get("source") and f["source"] != "manual":
                prov = {"source": f["source"], "source_date": f.get("source_date"),
                        "source_doc": f.get("source_doc")}
                # если source_doc — это id снимка, восстановим ссылку на снимок
                doc = f.get("source_doc") or ""
                if doc.count("-") == 2 and doc.split("-")[0] in _PROV_SOURCES:
                    prov["snapshot"] = doc
            base = {"kind": kind, "layer_id": layer_id, "props": props}
            if f.get("style_id"):
                base["style_id"] = f["style_id"]
            if prov:
                base["prov"] = prov
            # reconstruct arc / circle if params were stored in attrs (for roundtrip)
            arc = None
            if "arc" in props:
                val = props["arc"]
                try:
                    arc = _json.loads(val) if isinstance(val, (str, bytes)) else val
                except Exception:
                    arc = None
            if not arc and "arc_cx" in props:
                # legacy multi-key storage
                arc = {"cx": props["arc_cx"], "cy": props["arc_cy"], "r": props["arc_r"],
                       "a0": props.get("arc_a0", 0), "sweep": props.get("arc_sweep", 0)}
            if arc:
                out.append({**base, "arc": arc, "props": {k:v for k,v in props.items() if k != "arc" and not k.startswith("arc_") }})
                continue
            circ = None
            if "circle" in props:
                val = props["circle"]
                try:
                    circ = _json.loads(val) if isinstance(val, (str, bytes)) else val
                except Exception:
                    circ = None
            if circ:
                out.append({**base, "circle": circ, "props": {k:v for k,v in props.items() if k != "circle" }})
                continue
            elif geom["type"] == "Point":
                out.append({**base, "point": _to_local([geom["coordinates"]])[0]})
            elif geom["type"] == "LineString":
                out.append({**base, "line": _to_local(geom["coordinates"])})
            else:
                polys = ([geom["coordinates"]] if geom["type"] == "Polygon"
                         else geom["coordinates"])
                for poly in polys:
                    ring = _to_local(poly[0])
                    if ring[0] == ring[-1]:
                        ring = ring[:-1]
                    out.append({**base, "ring": ring, "props": dict(props)})
    ps = project.meta("project_styles")
    project_styles = {}
    if ps:
        try:
            project_styles = _json.loads(ps)
        except Exception:
            pass
    pk = project.meta("project_custom_kinds")
    project_kinds = []
    if pk:
        try:
            project_kinds = _json.loads(pk)
        except Exception:
            pass
    undo = project.meta("studio_undo_stack")
    redo = project.meta("studio_redo_stack")
    undo_stack = []
    if undo:
        try:
            undo_stack = _json.loads(undo)
        except Exception:
            pass
    redo_stack = []
    if redo:
        try:
            redo_stack = _json.loads(redo)
        except Exception:
            pass
    project.close()
    return {"name": name, "features": out, "projectStyles": project_styles, "projectCustomKinds": project_kinds, "undo_stack": undo_stack, "redo_stack": redo_stack}


def import_fgistp(payload):
    """Выгрузка ФГИС ТП от браузерного моста → фигуры холста.

    Payload расширения: grado_source=fgis_tp, WGS84, properties с
    class_name/class_title/uin. Полигоны становятся функциональными
    зонами; линейные/точечные слои пока пропускаются с пометкой."""
    from grado_connectors.crs import transform_geom, wgs84_to_utm37n

    # снимок источника: контрактные объекты WGS84 с grado_key (для diff)
    uin = payload.get("grado_uin")
    src_features = []
    for i, f in enumerate(payload.get("features") or []):
        if not f.get("geometry"):
            continue
        props = f.get("properties") or {}
        # ключ объекта: id источника, иначе uin+индекс — НЕ голый uin,
        # иначе все объекты документа схлопнутся в один ключ (потеря diff)
        src_features.append({
            "type": "Feature",
            "grado_key": str(f.get("id") or f"{uin}:{i}"),
            "geometry": f["geometry"], "properties": props})
    result = make_result(src_features,
                         params={"uin": uin,
                                 "layer": payload.get("grado_layer_name")},
                         source_doc=uin)
    manifest, d = _snapshot(FgistpConnector(), result)
    prov = _prov(manifest)

    features, notes = [], []
    skipped = 0
    for f in payload.get("features") or []:
        geom = f.get("geometry")
        props = f.get("properties") or {}
        if not geom:
            continue
        if geom["type"] not in ("Polygon", "MultiPolygon"):
            skipped += 1
            continue
        utm = transform_geom(geom, wgs84_to_utm37n)
        polys = ([utm["coordinates"]] if utm["type"] == "Polygon"
                 else utm["coordinates"])
        for poly in polys:
            ring = _to_local(poly[0])
            if ring[0] == ring[-1]:
                ring = ring[:-1]
            # ФГИС ТП — исходные данные: в выделенный source-слой, НЕ в
            # проектные зоны (MODEL-01b; kind zone нужен только для схемы)
            features.append({"kind": "zone",
                             "layer_id": "source.fgistp.func_zones",
                             "ring": ring, "props": {
                "zone_title": props.get("class_name")
                              or payload.get("grado_layer_name", "ФГИС ТП"),
                "zone_code": str(props.get("uin") or uin or ""),
            }, "prov": dict(prov)})
    if skipped:
        notes.append(f"пропущено не-полигонов: {skipped}")
    return {"features": features, "notes": notes, "source_doc": uin,
            "snapshot": manifest, "diff": d}


def import_nspd(payload):
    """Захват НСПД (JSON браузерного моста GRADO) → фигуры холста.

    Коннектор нормализует (options→opt_*, дедуп, 3857→WGS84), здесь
    координаты доводятся до локальных метров холста (UTM − ORIGIN)."""
    from grado_connectors import NspdCapture
    from grado_connectors.crs import transform_geom, wgs84_to_utm37n

    conn = NspdCapture()
    result = conn.fetch(payload=payload)
    # НСПД не различает территории в params (всегда path=None) — добавляем
    # ключ по габаритам, иначе diff сравнит захваты разных территорий
    result["params"] = {**(result.get("params") or {}),
                        "extent": _territory_key(result["features"])}
    manifest, d = _snapshot(conn, result)   # фиксация снимка + diff
    prov = _prov(manifest)
    features = []
    for f in result["features"]:
        geom = transform_geom(f["geometry"], wgs84_to_utm37n)
        props = f["properties"]
        attrs = {"cad_num": props.get("opt_cad_num") or props.get("cad_num")
                 or f["grado_key"],
                 "category": props.get("opt_land_record_category_type"),
                 "vri": props.get("opt_permitted_use_established_by_document")}
        rings = ([geom["coordinates"]] if geom["type"] == "Polygon"
                 else geom["coordinates"] if geom["type"] == "MultiPolygon"
                 else [])
        okey = f["grado_key"]                 # кадномер/устойчивый ключ объекта
        for i, ring in enumerate(rings):
            local = [[x - ORIGIN[0], y - ORIGIN[1]] for x, y in ring[0]]
            if local[0] == local[-1]:
                local = local[:-1]
            features.append({"kind": "parcel",
                             "layer_id": "source.nspd.parcels", "ring": local,
                             "props": {k: v for k, v in attrs.items() if v},
                             "prov": dict(prov),
                             "srcKey": f"source.nspd.parcels:{okey}#{i}"})
    return {"features": features, "notes": result["notes"],
            "source_doc": result.get("source_doc"),
            "snapshot": manifest, "diff": d}


# ГИС ОГД отдаёт произвольный набор слоёв в одном ZIP (имя = grado_member
# из имени файла-члена архива, портал не стандартизирует состав выгрузки).
# Распознаём по подстроке в имени только слои с уже готовой моделью/стилем;
# остальные не теряются молча — попадают в notes для показа в UI.
_GISOGD_LAYER_RULES = [
    (("функционал", "funkcional"), "zone", "source.gisogd.func_zones"),
    (("красн", "krasn"), "redline", "source.gisogd.red_lines"),
]

# Точное соответствие имени члена архива конкретному знаку Эталона ЛГР
# (moscow_lgr.json, приказ ММА №65) — используется и для маршрутизации
# (любое совпадение здесь означает "это ЗОУИТ", см. _gisogd_route), и для
# per-object style_id: без этого распознанная зона получала бы общий
# restrict.hatch, хотя в библиотеке уже есть точный знак. Порядок важен:
# сперва более специфичные пояса/варианты СЗЗ, затем общие.
_GISOGD_STYLE_RULES = [
    (("1а пояса", "зона_1а", "zona_1a", "sanokhr_1a"), "lgr.sanokhr.1a"),
    (("1б пояса", "зона_1б", "zona_1b", "sanokhr_1b"), "lgr.sanokhr.1b"),
    (("жестк", "zhestk"), "lgr.sanokhr.2hard"),
    (("1 пояса санитар", "зона_1_пояса", "zona_1_poyasa"), "lgr.sanokhr.1"),
    (("2 пояса санитар", "зона_2_пояса", "zona_2_poyasa"), "lgr.sanokhr.2"),
    (("3 пояса санитар", "зона_3_пояса", "zona_3_poyasa"), "lgr.sanokhr.3"),
    (("водоохран", "vodoohran"), "lgr.vodookhr"),
    (("прибрежн", "pribrezh"), "lgr.pribrezh"),
    (("сзз_расчет", "szz_raschet", "расчетн"), "lgr.szz.calc"),
    (("сзз_ориент", "szz_orient", "ориентировоч"), "lgr.szz.orient"),
    (("санитарно-защит", "sanitarno_zash", "сзз"), "lgr.szz.set"),
    (("подтоплен", "podtoplen"), "lgr.podtop.mid"),
    (("затоплен", "zatoplen"), "lgr.zatop"),
    (("защитная зона окн", "zashitnaya_zona_okn"), "lgr.okn.zashchit"),
    (("охранная зона окн", "ohrannaya_zona_okn"), "lgr.okn.okhr"),
    (("регулирования застройки", "regulirovaniya"), "lgr.okn.reg"),
    (("охраняемого природного ландшафта", "landshaft"), "lgr.okn.landshaft"),
    (("территория окн", "ter_okn", "territoriya_okn"), "lgr.okn.terr"),
    (("охранная зона оопт", "ohrannaya_zona_oopt"), "lgr.oopt.okhr"),
    (("оопт", "oopt"), "lgr.oopt"),
    (("лесопарков", "lesopark"), "lgr.lesopark"),
    (("электроэнерг", "лэп", "elektroenerg"), "lgr.energo"),
    (("трубопровод", "truboprovod"), "lgr.truboprovod"),
    (("теплосет", "teplosetey"), "lgr.teplo"),
    (("связи", "svyazi"), "lgr.svyaz"),
    (("метрополит", "metro"), "lgr.metro"),
    (("железных дорог", "пожд", "zhd_"), "lgr.zhd"),
    (("приаэродром", "priaerodrom"), "lgr.priaero"),
    (("береговая полоса", "beregovaya"), "lgr.beregovaya"),
    (("военного объекта", "military"), "lgr.military"),
    (("радиотехническ", "radio"), "lgr.radio"),
    (("технич", "инженерных коммуникаций", "tehnicheskaya_zona"), "lgr.tech.zone"),
]
# общие ЗОУИТ-термины без точного знака (роутятся в restrict.hatch слоя,
# но не переопределяют style_id) — напр. просто "зоуит_реестр.geojson"
_GISOGD_RESTRICT_HINTS = ("зоуит", "zouit", "охран", "ohran", "sanit", "санит")


def _gisogd_style_for(member):
    low = member.lower()
    for keys, style_id in _GISOGD_STYLE_RULES:
        if any(k in low for k in keys):
            return style_id
    return None


def _gisogd_is_restrict(member):
    low = member.lower()
    if any(k in low for k in _GISOGD_RESTRICT_HINTS):
        return True
    return any(any(k in low for k in keys) for keys, _ in _GISOGD_STYLE_RULES)


def _gisogd_route(member):
    low = member.lower()
    for keys, kind, layer_id in _GISOGD_LAYER_RULES:
        if any(k in low for k in keys):
            return kind, layer_id
    if _gisogd_is_restrict(member):
        return "restrict", "source.gisogd.restrict"
    return None, None


def import_gisogd(zip_bytes):
    """Выгрузка ГИС ОГД Москвы (ZIP с портала) → фигуры холста.

    Коннектор распаковывает ZIP-в-ZIP и SHP (МСК-50 → WGS84 через ogr2ogr);
    здесь координаты доводятся до локальных метров холста, а слои архива
    маршрутизируются в модель по имени члена (см. _GISOGD_LAYER_RULES)."""
    from grado_connectors.crs import transform_geom, wgs84_to_utm37n

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(zip_bytes)
        tmp_path = tmp.name
    try:
        conn = GisogdZip()
        result = conn.fetch(tmp_path)
    finally:
        os.unlink(tmp_path)
    result["params"] = {**(result.get("params") or {}),
                        "extent": _territory_key(result["features"])}
    manifest, d = _snapshot(conn, result)
    prov = _prov(manifest)

    features, notes, unknown = [], list(result["notes"]), set()
    for f in result["features"]:
        geom = f.get("geometry")
        if not geom:
            continue
        member = (f["properties"] or {}).get("grado_member", "")
        kind, layer_id = _gisogd_route(member)
        if kind is None:
            if member not in unknown:
                notes.append(f"«{member}»: тип слоя не распознан, объекты пропущены")
                unknown.add(member)
            continue
        name = f["properties"].get("NAME") or f["properties"].get("name")
        # точный знак Эталона ЛГР по имени члена архива (поверх грубого kind
        # выше) — назначается per-object, не меняет layer_id/маршрутизацию
        style_id = _gisogd_style_for(member) if kind in ("restrict", "zone") else None
        style_title = STYLE_LIB["styles"][style_id]["title"] if style_id else None
        # стабильный ключ источника (член архива + id объекта) → фронт
        # дедуплицирует повторный импорт того же ZIP
        okey = f.get("grado_key")
        try:
            utm = transform_geom(geom, wgs84_to_utm37n)
        except Exception:
            continue
        if kind == "redline":
            if utm["type"] != "LineString":
                continue
            feat = {"kind": "redline", "layer_id": layer_id,
                    "line": _to_local(utm["coordinates"]),
                    "props": {"status": "существующая"}, "prov": dict(prov)}
            if okey is not None:
                feat["srcKey"] = f"{layer_id}:{okey}"
            features.append(feat)
            continue
        polys = ([utm["coordinates"]] if utm["type"] == "Polygon"
                 else utm["coordinates"] if utm["type"] == "MultiPolygon" else [])
        for i, poly in enumerate(polys):
            ring = _to_local(poly[0])
            if ring[0] == ring[-1]:
                ring = ring[:-1]
            props = ({"zone_title": name or style_title or "ГИС ОГД"} if kind == "zone"
                     else {"kind": style_title or name or "ЗОУИТ", "basis": "ГИС ОГД"})
            feat = {"kind": kind, "layer_id": layer_id, "ring": ring,
                    "props": props, "prov": dict(prov)}
            if style_id:
                feat["style_id"] = style_id
            if okey is not None:
                feat["srcKey"] = f"{layer_id}:{okey}#{i}"
            features.append(feat)
    return {"features": features, "notes": notes,
            "source_doc": result.get("source_doc"),
            "snapshot": manifest, "diff": d}


# --- «Данные по области»: прямые открытые источники по экстенту холста ------
# Без браузерного моста, без портала и без скачивания файлов: сервер сам
# ходит в OSM (Overpass) и НСПД (intersects-API геопортала), а фигуры
# раскладываются по слоям-приёмникам source.* по явному layer_id (правило 7).
# ГИС ОГД Москвы здесь нет намеренно: его API за SSO mos.ru (проверено
# 07.2026) — остаётся импорт ZIP/по ссылке.

EXTENT_SOURCES = {
    "osm.roads": {
        "conn": "osm", "sets": ["roads"], "kind": "generic",
        "layer_id": "source.osm.roads", "title": "Дороги и улицы"},
    "osm.buildings": {
        "conn": "osm", "sets": ["buildings"], "kind": "building",
        "layer_id": "source.osm.buildings", "title": "Здания (OSM)"},
    "osm.landuse": {
        "conn": "osm", "sets": ["landuse"], "kind": "generic",
        "layer_id": "source.osm.landuse", "title": "Землепользование"},
    "osm.water": {
        "conn": "osm", "sets": ["water"], "kind": "generic",
        "layer_id": "source.osm.water", "title": "Вода"},
    "nspd.parcels": {
        "conn": "nspd", "categories": [36368], "kind": "parcel",
        "layer_id": "source.nspd.parcels", "title": "Участки ЕГРН"},
    "nspd.buildings": {
        "conn": "nspd", "categories": [36369], "kind": "building",
        "layer_id": "source.nspd.buildings", "title": "Здания (ЕГРН)"},
    "nspd.constructions": {
        "conn": "nspd", "categories": [36383], "kind": "generic",
        "layer_id": "source.nspd.constructions", "title": "Сооружения (ЕГРН)"},
    "nspd.zouit": {
        "conn": "nspd", "categories": [469038, 469039, 469040, 469041, 469042],
        "kind": "restrict",
        "layer_id": "source.nspd.zouit", "title": "ЗОУИТ"},
}

# Пределы площади запроса, км² (фронт блокирует раньше, сервер — страховка):
# НСПД в плотной застройке тяжёлый (сотни участков на км²), Overpass щедрее.
EXTENT_LIMITS_KM2 = {"osm": 60.0, "nspd": 12.0}


def bbox_km2(bbox):
    west, south, east, north = map(float, bbox)
    lat_mid = math.radians((south + north) / 2.0)
    return abs(north - south) * 111.32 * abs(east - west) * 111.32 * math.cos(lat_mid)


def _int_or_none(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


# Полная атрибуция НСПД: options-ключ геопортала → (русское имя поля, тип).
# Ключи с латинскими именами (cad_num, category, vri, purpose, floors, name,
# address) остаются семантикой холста (их ждут KIND_ATTRS/ТЭП) и в этот
# словарь не входят — здесь ДОПОЛНИТЕЛЬНЫЕ столбцы. Неизвестные ключи
# добавляются как есть (text): состав options у геопортала меняется.
NSPD_EXTENT_FIELDS = {
    "area": ("площадь (ЕГРН), м²", "real"),
    "declared_area": ("декларированная площадь, м²", "real"),
    "land_record_area": ("площадь по документам, м²", "real"),
    "build_record_area": ("площадь застройки, м²", "real"),
    "area_value": ("площадь, м²", "real"),
    "cost_value": ("кадастровая стоимость, ₽", "real"),
    "cost_index": ("УПКС, ₽/м²", "real"),
    "cost_application_date": ("стоимость: дата применения", "text"),
    "cost_determination_date": ("стоимость: дата определения", "text"),
    "cost_registration_date": ("стоимость: дата внесения", "text"),
    "cost_approvement_date": ("стоимость: дата утверждения", "text"),
    "determination_couse": ("основание определения стоимости", "text"),
    "land_record_type": ("вид объекта", "text"),
    "land_record_subtype": ("вид участка", "text"),
    "land_record_reg_date": ("дата постановки на учёт", "text"),
    "build_record_registration_date": ("дата постановки на учёт", "text"),
    "build_record_type_value": ("вид ОКС", "text"),
    "building_name": ("наименование", "text"),
    "materials": ("материал стен", "text"),
    "year_built": ("год постройки", "int"),
    "year_commisioning": ("год ввода", "int"),
    "floors": ("этажность", "text"),
    "underground_floors": ("подземных этажей", "text"),
    "purpose": ("назначение", "text"),
    "permitted_use_name": ("разрешённое использование", "text"),
    "permitted_use_established_by_document": ("ВРИ по документу", "text"),
    "ownership_type": ("форма собственности", "text"),
    "right_type": ("вид права", "text"),
    "status": ("статус", "text"),
    "previously_posted": ("ранее учтённый", "text"),
    "quarter_cad_number": ("кадастровый квартал", "text"),
    "readable_address": ("адрес", "text"),
    "cultural_heritage_val": ("объект культурного наследия", "text"),
    "facility_cad_number": ("кадастровый номер сооружения", "text"),
    "specified_area": ("уточнённая площадь, м²", "real"),
    "depth": ("глубина, м", "real"),
    "height": ("высота, м", "real"),
    "extension": ("протяжённость, м", "real"),
    "zone_kind": ("вид зоны", "text"),
    "content_restrictions": ("ограничения использования", "text"),
    "registration_date": ("дата внесения", "text"),
    "number": ("реестровый номер", "text"),
}
# семантические ключи, уже занятые схемой холста (не дублировать столбцами)
_NSPD_SEMANTIC = {
    "nspd.parcels": {"cad_num", "land_record_category_type",
                     "permitted_use_established_by_document",
                     "readable_address"},
    "nspd.buildings": {"cad_num", "building_name", "floors",
                       "readable_address"},
    "nspd.constructions": {"cad_num", "building_name"},
    "nspd.zouit": set(),
}


def _nspd_extra_fields(src_key, p, props):
    """Все прочие options-поля НСПД → props с русскими именами.

    Возвращает [{name, type}] реально добавленных полей (для колонок)."""
    fields = []
    for key, val in p.items():
        if not key.startswith("opt_") or val in (None, ""):
            continue
        okey = key[4:]
        if okey in _NSPD_SEMANTIC.get(src_key, ()):
            continue
        label, ftype = NSPD_EXTENT_FIELDS.get(okey, (okey, "text"))
        if ftype == "real":
            try:
                val = float(val)
            except (TypeError, ValueError):
                ftype = "text"
        elif ftype == "int":
            iv = _int_or_none(val)
            if iv is None:
                ftype = "text"
            else:
                val = iv
        if label not in props:
            props[label] = val
            fields.append({"name": label, "type": ftype})
    return fields


# базовые (семантические) ключи каждого источника: как показать их колонками
# в таблице атрибутов (label — русская подпись, name — ключ props).
# floors у зданий не колонка — его уже показывает семантика oks.building.
_EXTENT_BASE_FIELDS = {
    "nspd.parcels": [
        {"name": "cad_num", "label": "кадастровый номер", "type": "text"},
        {"name": "category", "label": "категория земель", "type": "text"},
        {"name": "vri", "label": "ВРИ", "type": "text"},
        {"name": "address", "label": "адрес", "type": "text"}],
    "nspd.buildings": [
        {"name": "purpose", "label": "наименование/назначение", "type": "text"},
        {"name": "cad_num", "label": "кадастровый номер", "type": "text"},
        {"name": "address", "label": "адрес", "type": "text"}],
    "nspd.constructions": [
        {"name": "name", "label": "наименование", "type": "text"},
        {"name": "cad_num", "label": "кадастровый номер", "type": "text"}],
    "nspd.zouit": [
        {"name": "kind", "label": "вид ЗОУИТ", "type": "text"},
        {"name": "number", "label": "реестровый номер", "type": "text"},
        {"name": "basis", "label": "источник", "type": "text"}],
    "osm.buildings": [
        {"name": "purpose", "label": "назначение", "type": "text"},
        {"name": "name", "label": "название", "type": "text"}],
}


def _extent_props(src_key, p):
    """Свойства источника → (атрибуты объекта холста, доп. поля-столбцы)."""
    base = [dict(fd) for fd in _EXTENT_BASE_FIELDS.get(src_key, [])]
    if src_key == "nspd.parcels":
        props = {k: v for k, v in {
            "cad_num": p.get("opt_cad_num") or p.get("cad_num"),
            "category": p.get("opt_land_record_category_type"),
            "vri": p.get("opt_permitted_use_established_by_document"),
            "address": p.get("opt_readable_address")}.items() if v}
        return props, base + _nspd_extra_fields(src_key, p, props)
    if src_key == "nspd.buildings":
        props = {k: v for k, v in {
            "purpose": p.get("opt_building_name") or p.get("opt_purpose") or "здание",
            "floors": _int_or_none(p.get("opt_floors")),
            "cad_num": p.get("opt_cad_num"),
            "address": p.get("opt_readable_address")}.items() if v}
        return props, base + _nspd_extra_fields(src_key, p, props)
    if src_key == "nspd.constructions":
        props = {k: v for k, v in {
            "name": p.get("opt_building_name") or p.get("label") or "сооружение",
            "cad_num": p.get("opt_cad_num")}.items() if v}
        return props, base + _nspd_extra_fields(src_key, p, props)
    if src_key == "nspd.zouit":
        # categoryName вида «ЗОУИТ природных территорий_» (хвост «_» —
        # артефакт геопортала), label — реестровый номер зоны
        props = {k: v for k, v in {
            "kind": (p.get("categoryName") or "ЗОУИТ").rstrip("_ "),
            "number": p.get("label"), "basis": "НСПД"}.items() if v}
        return props, base + _nspd_extra_fields(src_key, p, props)
    if src_key == "osm.buildings":
        purpose = p.get("building")
        return {k: v for k, v in {
            "purpose": ("здание" if purpose in (True, "yes") else purpose),
            "floors": _int_or_none(p.get("building:levels")),
            "name": p.get("name")}.items() if v}, base
    # osm.roads / osm.landuse / osm.water / прочее — свои поля generic-слоя
    keep = ("name", "highway", "surface", "lanes", "landuse", "leisure",
            "natural", "water", "waterway")
    props = {k: p[k] for k in keep if p.get(k)}
    return props, [{"name": k, "type": "text"} for k in props]


def _wgs_geom_to_canvas(geom):
    """Геометрия WGS84 → части фигуры холста [{'ring'|'line'|'point': ...}]."""
    from grado_connectors.crs import transform_geom, wgs84_to_utm37n
    utm = transform_geom(geom, wgs84_to_utm37n)
    t = utm["type"]
    if t == "Point":
        return [{"point": _to_local([utm["coordinates"]])[0]}]
    if t in ("LineString", "MultiLineString"):
        lines = [utm["coordinates"]] if t == "LineString" else utm["coordinates"]
        return [{"line": _to_local(ln)} for ln in lines if len(ln) >= 2]
    polys = ([utm["coordinates"]] if t == "Polygon"
             else utm["coordinates"] if t == "MultiPolygon" else [])
    out = []
    for poly in polys:
        ring = _to_local(poly[0])
        if len(ring) >= 2 and ring[0] == ring[-1]:
            ring = ring[:-1]
        if len(ring) >= 3:
            out.append({"ring": ring})
    return out


def fetch_extent(bbox, sources):
    """Выгрузка выбранных источников по экстенту → группы фигур холста.

    bbox = [west, south, east, north] (WGS84); sources ⊆ EXTENT_SOURCES.
    Возвращает {"groups": [{source, title, layer_id, kind, count, features}],
    "notes": [...], "snapshots": [манифесты для журнала источников]}."""
    from grado_connectors import NspdDirect, OsmOverpass

    keys = [k for k in sources if k in EXTENT_SOURCES]
    unknown = [k for k in sources if k not in EXTENT_SOURCES]
    notes = [f"неизвестный источник: {k}" for k in unknown]
    if not keys:
        return {"groups": [], "notes": notes or ["не выбраны источники"],
                "snapshots": []}
    area = bbox_km2(bbox)
    for conn_name in {EXTENT_SOURCES[k]["conn"] for k in keys}:
        limit = EXTENT_LIMITS_KM2[conn_name]
        if area > limit:
            raise ValueError(
                f"область {area:.1f} км² больше предела {limit:.0f} км² "
                f"для источника {conn_name.upper()} — приблизьте вид")

    groups = {k: {"source": k, "title": EXTENT_SOURCES[k]["title"],
                  "layer_id": EXTENT_SOURCES[k]["layer_id"],
                  "kind": EXTENT_SOURCES[k]["kind"], "features": [],
                  "fields": []}
              for k in keys}
    snapshots = []

    def _emit(src_key, wgs_features, prov):
        spec = EXTENT_SOURCES[src_key]
        g = groups[src_key]
        seen_fields = {fd["name"] for fd in g["fields"]}
        for f in wgs_features:
            geom = f.get("geometry")
            if not geom:
                continue
            props, fields = _extent_props(src_key, f.get("properties") or {})
            for fd in fields:              # union столбцов по группе
                if fd["name"] not in seen_fields:
                    g["fields"].append(fd)
                    seen_fields.add(fd["name"])
            # стабильный ключ источника → фронт дедуплицирует повторную
            # выгрузку той же территории (не плодит дубликаты)
            key = f.get("grado_key")
            for i, part in enumerate(_wgs_geom_to_canvas(geom)):
                feat = {"kind": spec["kind"], "layer_id": spec["layer_id"],
                        **part, "props": dict(props), "prov": dict(prov)}
                if key is not None:
                    feat["srcKey"] = f"{spec['layer_id']}:{key}#{i}"
                g["features"].append(feat)

    # --- OSM: один запрос Overpass на все выбранные наборы ------------------
    osm_keys = [k for k in keys if EXTENT_SOURCES[k]["conn"] == "osm"]
    if osm_keys:
        sets = sorted({s for k in osm_keys for s in EXTENT_SOURCES[k]["sets"]})
        conn = OsmOverpass()
        try:
            result = conn.fetch(bbox, sets)
            manifest, d = _snapshot(conn, result)
            if d:
                notes.append(f"OSM изменился с прошлого снимка: "
                             f"+{len(d['added'])} −{len(d['removed'])} "
                             f"~{len(d['changed'])}")
            snapshots.append(manifest)
            prov = _prov(manifest)
            by_set = {}
            for f in result["features"]:
                by_set.setdefault(
                    (f.get("properties") or {}).get("grado_set"), []).append(f)
            for k in osm_keys:
                for s in EXTENT_SOURCES[k]["sets"]:
                    _emit(k, by_set.get(s, []), prov)
            notes.extend(result.get("notes") or [])
        except Exception as e:
            notes.append(f"OSM: {e}")

    # --- НСПД: отдельный запрос на источник (свой снимок и провенанс) -------
    nspd_keys = [k for k in keys if EXTENT_SOURCES[k]["conn"] == "nspd"]
    for i, k in enumerate(nspd_keys):
        if i:
            import time
            time.sleep(0.5)   # бережём лимит частоты геопортала
        conn = NspdDirect()
        try:
            result = conn.fetch(bbox, EXTENT_SOURCES[k]["categories"])
            result["params"]["source"] = k   # разные источники ≠ один снимок
            manifest, d = _snapshot(conn, result)
            if d:
                notes.append(f"{EXTENT_SOURCES[k]['title']}: изменения с "
                             f"прошлого снимка +{len(d['added'])} "
                             f"−{len(d['removed'])} ~{len(d['changed'])}")
            snapshots.append(manifest)
            _emit(k, result["features"], _prov(manifest))
            notes.extend(n for n in (result.get("notes") or [])
                         if not n.endswith("отброшено: 0"))   # шум нормализации
        except Exception as e:
            notes.append(f"{EXTENT_SOURCES[k]['title']}: {e}")

    out_groups = []
    for k in keys:
        g = groups[k]
        g["count"] = len(g["features"])
        out_groups.append(g)
    return {"groups": out_groups, "notes": notes, "snapshots": snapshots}


def make_grado(features, name, layers=None, project_styles=None, project_custom_kinds=None, undo_stack=None, redo_stack=None):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "studio.grado"
        build_project(path, name, features, layers, project_styles=project_styles, project_custom_kinds=project_custom_kinds, undo_stack=undo_stack, redo_stack=redo_stack).close()
        return path.read_bytes()


def make_dxf(features, name, layers=None):
    """Чертёж в DXF R12 (координаты — СК проекта, метры UTM).

    Размерные линии — аннотация чертежа: в модель не попадают,
    в DXF выгружаются слоем RAZMERY (линия + текст длины)."""
    import math
    from grado_model.dxf_export import _polyline, _text, project_to_dxf
    dxf_layers, dxf_fallback = dxf_layers_from_styles()
    with tempfile.TemporaryDirectory() as tmp:
        project = build_project(Path(tmp) / "studio.grado", name, features, layers)
        data = project_to_dxf(project, layers=dxf_layers,
                              fallback_layer=dxf_fallback)
        project.close()
    dims = [f for f in features if f["kind"] == "dim"]
    if not dims:
        return data
    dim_layer = dxf_layers.get("annot.dim", ("RAZMERY", 3))[0]  # имя из JSON
    text = data.decode("cp1251")
    extra = ""
    for f in dims:
        (ax, ay), (bx, by) = f["line"][0], f["line"][1]
        pts = [[ax + ORIGIN[0], ay + ORIGIN[1]], [bx + ORIGIN[0], by + ORIGIN[1]]]
        extra += _polyline(dim_layer, pts, closed=False)
        length = math.hypot(bx - ax, by - ay)
        extra += _text(dim_layer, (pts[0][0] + pts[1][0]) / 2,
                       (pts[0][1] + pts[1][1]) / 2, f"{length:.1f} м", 2.0)
    cut = text.rfind("0\nENDSEC")
    return (text[:cut] + extra + text[cut:]).encode("cp1251", errors="replace")


def make_print(features, name, scale=None, paper="A2", basemap=False, layers=None,
               basemap_source="osm", canvas_styles=None, project_styles=None):
    """Печать чертежа в масштабе: один лист PDF с рамкой и подписью."""
    from grado_layout import (A1_LANDSCAPE, A2_LANDSCAPE, A3_LANDSCAPE,
                              Document, MapFrame, Page, PageBorder,
                              TextFrame, render_document_pdf)
    from grado_render import StyleSet

    sizes = {"A3": A3_LANDSCAPE, "A2": A2_LANDSCAPE, "A1": A1_LANDSCAPE}
    size = sizes.get(paper, A2_LANDSCAPE)
    with tempfile.TemporaryDirectory() as tmp:
        project = build_project(Path(tmp) / "studio.grado", name, features, layers, project_styles=project_styles)
        page = Page(size)
        ix, iy, iw, ih = page.inner_rect()
        map_rect = (ix + 8, iy + 16, iw - 16, ih - 24)
        used_scale = int(scale) if scale else fit_scale(project, map_rect)
        underlay = (_project_underlay(project, map_rect, used_scale, source=basemap_source)
                    if basemap else None)
        attribution = TILE_ATTRIBUTIONS.get(basemap_source, TILE_ATTRIBUTIONS["osm"])
        caption_extra = f" · подложка {attribution}" if underlay else ""
        import datetime
        page.frames = [
            PageBorder(page),
            MapFrame(map_rect, scale=used_scale, underlay=underlay),
            TextFrame((ix + 8, iy + 2, iw - 16, 10),
                      [f"{name} — чертёж, М 1:{used_scale}, "
                       f"{datetime.date.today().isoformat()}{caption_extra}"],
                      size=3.6),
        ]
        doc = Document(name)
        doc.pages = [page]
        doc.sheet_titles = [""]
        id_styles = {}
        if project_styles:
            id_styles.update(project_styles)
        if canvas_styles:
            id_styles.update(canvas_styles)
        # canvas_styles — inline-знаки «как на холсте» (иначе стандарт ЛГР)
        pdf = render_document_pdf(doc, project, styles=StyleSet(id_styles=id_styles))
        project.close()
    return pdf, used_scale


def redline_stations(line, radius, step):
    """Пикетаж вдоль красной линии (по сопряжённой кривой, если задан R)."""
    pts = [tuple(p) for p in line]
    path = (GPath.fillet_polyline(pts, float(radius))
            if radius and float(radius) > 0 and len(pts) >= 3
            else GPath.polyline(pts))
    out = []
    for s, pt in path.stations(float(step)):
        _, tangent = path.point_at_station(s)
        out.append({"s": round(s, 3), "x": pt[0], "y": pt[1],
                    "a": round(tangent, 6)})
    return out


def zones_report(features):
    """Функциональные зоны как топологическое покрытие (ядро geom).

    Зоны, нарисованные с привязкой повершинно, образуют покрытие: общие
    границы совпадают, дырок и нахлёстов нет — validate() сверяет сумму
    площадей с внешним контуром. Любое расхождение — внятный диагноз."""
    from grado_geom import Coverage, CoverageError

    # покрытие проверяется для слоёв с topology="coverage", не для kind=="zone"
    zones = [f for f in features
             if (_class_of(f) and _class_of(f).topology == "coverage"
                 and "ring" in f)]
    if len(zones) < 2:
        return None
    polys = {}
    for i, f in enumerate(zones):
        title = f.get("props", {}).get("zone_title") or f"зона {i + 1}"
        polys[f"{title} [{i + 1}]"] = [tuple(p) for p in f["ring"]]
    try:
        cov = Coverage.from_polygons(polys)
        cov.validate()
        return {"ok": True, "zones": len(zones),
                "total_ha": round(sum(cov.areas().values()) / 10000.0, 2),
                "shared_edges": len(cov.shared_edges())}
    except CoverageError as e:
        return {"ok": False, "zones": len(zones), "error": str(e)}


def redline_offset(line, radius, dist):
    """Офсет красной линии через ядро geom (fillet + offset G1-цепи).

    dist > 0 — влево по ходу линии. Возвращает полилинию в тех же
    локальных координатах; сопряжение уже вшито в геометрию."""
    pts = [tuple(p) for p in line]
    path = (GPath.fillet_polyline(pts, float(radius))
            if radius and float(radius) > 0 and len(pts) >= 3
            else GPath.polyline(pts))
    return [list(p) for p in path.offset(float(dist)).linearize(0.05)]


def make_buffer(features, dist, fillet=0.0, sides="both"):
    """Генерация буферов вокруг объектов.

    dist — расстояние в метрах (положительное).
    fillet — радиус сопряжения на углах (для линий).
    sides — "left" | "right" | "both" | "outer" | "inner" (для полигонов outer=внешний).
    Возвращает список новых фичей (circle для точек, line/ring для остальных).
    """
    import math
    out = []
    d = float(dist)
    if d == 0:
        return out
    fil = float(fillet or 0)

    for f in features or []:
        props = dict(f.get("props") or {})
        kind = f.get("kind", "generic")
        layer_id = f.get("layer_id")
        prov = f.get("prov")

        if f.get("point"):
            # точка → окружность-буфер (используем circle примитив)
            x, y = f["point"]
            circ = {"cx": x, "cy": y, "r": abs(d)}
            newf = {"circle": circ, "props": props, "kind": kind}
            if layer_id:
                newf["layer_id"] = layer_id
            if prov:
                newf["prov"] = prov
            out.append(newf)
            continue
        if f.get("circle"):
            # окружность → концентрический буфер
            c = f["circle"]
            new_r = max(0.1, abs(c["r"] + d)) if sides != "inner" else max(0.1, abs(c["r"] - d))
            circ = {"cx": c["cx"], "cy": c["cy"], "r": new_r}
            newf = {"circle": circ, "props": {**props, "_buffer_dist": d}, "kind": kind}
            if layer_id:
                newf["layer_id"] = layer_id
            if prov:
                newf["prov"] = prov
            out.append(newf)
            continue

        # линии, дуги, полигоны → офсет
        pts = None
        is_ring = False
        if f.get("ring"):
            pts = [tuple(p) for p in f["ring"]]
            is_ring = True
        elif f.get("line"):
            pts = [tuple(p) for p in f["line"]]
        elif f.get("arc"):
            # sample arc to pts
            a = f["arc"]
            n = 24
            pts = []
            for i in range(n + 1):
                ang = a.get("a0", 0) + a.get("sweep", 0) * i / n
                pts.append((a["cx"] + a["r"] * math.cos(ang), a["cy"] + a["r"] * math.sin(ang)))
        if not pts or len(pts) < 2:
            continue

        closed = is_ring or (pts[0] == pts[-1])
        path = (GPath.fillet_polyline(pts, fil) if fil > 0 and len(pts) >= 3 else GPath.polyline(pts, closed=closed))

        sides_list = []
        if sides in ("both", "left", "outer"):
            sides_list.append(("left", d))
        if sides in ("both", "right", "inner"):
            sides_list.append(("right", -d))
        if sides == "outer" and is_ring:
            sides_list = [("outer", d)]
        if sides == "inner" and is_ring:
            sides_list = [("inner", -d)]

        for side_name, sign_d in sides_list:
            try:
                off_pts = [list(p) for p in path.offset(sign_d).linearize(0.05)]
                if closed and not (off_pts[0] == off_pts[-1]):
                    off_pts.append(off_pts[0][:])
                newf = {
                    "ring" if (closed or is_ring) else "line": off_pts,
                    "props": {**props, "_buffer_dist": d, "_buffer_side": side_name},
                    "kind": kind
                }
                if layer_id:
                    newf["layer_id"] = layer_id
                if prov:
                    newf["prov"] = prov
                out.append(newf)
            except Exception:
                # если офсет схлопывается — пропускаем
                continue
    return out
