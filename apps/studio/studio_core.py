"""Ядро студии: черчение (JSON с холста) → проект → ТЭП → альбом.

Клиент рисует в локальных метрах (ось Y вверх); здесь фигуры ложатся в
проект .grado (UTM, смещение ORIGIN), ТЭП считается движком из геометрии,
альбом собирается листами мастера территории.
"""

import math
import os
import re
import ssl
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

ROOT = (Path(os.environ["RESOURCEPATH"])
        if getattr(sys, "frozen", False) and os.environ.get("RESOURCEPATH")
        else Path(__file__).parents[2])
DATA_DIR = Path(os.environ.get("GRADO_STUDIO_DATA_DIR", Path(__file__).parent))
for mod in ("model", "compute", "reactive", "render", "geom", "layout",
            "connectors"):
    p = str(ROOT / "core" / mod)
    if p not in sys.path:
        sys.path.insert(0, p)
sys.path.insert(0, str(ROOT / "apps" / "wizard"))

from grado_compute.engine import Engine  # noqa: E402
from grado_geom import Path as GPath  # noqa: E402
from grado_geom import (Arc, CurveError, PathError, Snapper, curve_spec, union_intersection_area,  # noqa: E402
                        mirror, rotate, scale, tessellate_curve)
from grado_layout import Document, render_document_pdf  # noqa: E402
from grado_layout import Page, A3_LANDSCAPE  # noqa: E402  # for stub sheets
from grado_model import Project  # noqa: E402
from grado_model import geometry  # noqa: E402
from grado_model.classifier import Classifier  # noqa: E402
from grado_render import StyleSet  # noqa: E402
from grado_wizard.sheets import (GOST, PRESENTATION, apo_sheet, layout_of,  # noqa: E402
                                 base_plan_sheet, fit_scale, location_sheet,
                                 ortho_sheet, tep_summary_sheet, title_sheet,
                                 TextFrame)  # for stubs

ORIGIN = (413000.0, 6178000.0)
PRESET = ROOT / "core" / "compute" / "grado_compute" / "presets" / "moscow_krt.json"

# --- единая библиотека стилей (styles/default.json): холст + PDF + DXF ------
from grado_render import merged_library  # noqa: E402
from grado_render import load_library  # noqa: E402
from grado_render import style as _render_style  # noqa: E402
import json as _json  # noqa: E402

# Пользовательские правки эталонных знаков (глобальные для студии) — отдельный
# файл-оверрайд рядом с автосейвом; сам генератор ЛГР и его JSON не трогаем.
STYLE_OVERRIDES_PATH = DATA_DIR / "style_overrides.json"


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


def current_style_overrides():
    """Текущие правки в памяти — для временных операций без потери сессии."""
    return _render_style.style_overrides()


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
from grado_connectors import (GISOGD_API_LAYERS, GisogdZip,  # noqa: E402
                              NspdCapture, SnapshotStore,
                              diff as _snap_diff, has_changes as _has_changes)
from grado_connectors.contract import make_result  # noqa: E402
from grado_connectors.fgistp import FgistpConnector  # noqa: E402

SOURCE_STORE = SnapshotStore(DATA_DIR / ".sources")
_PROV_SOURCES = {"nspd", "fgistp", "gisogd", "osm", "terrain", "import"}  # допустимые в модели


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
        # Знаки ЛГР: штрих/маркеры в QML заданы в метрах на местности (MapUnit),
        # в px записаны для опорного 1:2000 → холст масштабирует их по зуму.
        if s.get("ground_units"):
            entry["ground_units"] = True
            entry["ref_scale"] = s.get("ref_scale", 2000)
        # Теги OSM highway знака дорог — нужны браузерной редакции: она строит
        # карту «тег → знак» из этих же стилей (свой Python-бэкенд ей недоступен)
        if s.get("osm_highway"):
            entry["osm_highway"] = list(s["osm_highway"])
        h = s.get("hatch")
        if isinstance(h, dict):
            entry["hatch"] = {k: h[k] for k in
                              ("angle", "cross", "spacing_px", "color") if k in h}
        elif h:
            entry["hatch"] = True
        # точечный узор ПОВЕРХ заливки (PointPatternFill эталона) — холст рисует
        # сетку кружков (drawDots): цвет + размер/шаг в px
        d = s.get("dots")
        if isinstance(d, dict):
            entry["dots"] = {"color": d.get("color"),
                             "size_px": d.get("size_px", 2),
                             "spacing_px": d.get("spacing_px", 8)}
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
            # ow — толщина штриха маркера (px); filled=False — контурный треугольник
            if lm.get("ow_px") is not None:
                entry["line_marker"]["ow"] = lm["ow_px"]
            if lm.get("filled") is False:
                entry["line_marker"]["filled"] = False
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
TILE_CACHE = DATA_DIR / ".tile_cache"
# слои ГИС ОГД целиком (портал не фильтрует по bbox) — качаем один раз,
# режем по видимой области локально; в .gitignore рядом с прочими кэшами
GISOGD_CACHE = DATA_DIR / ".gisogd_cache"
# каталог документов ФГИС ТП (вся РФ, ~27 тыс. записей, ~10 МБ JSON) — кэш
FGISTP_CACHE = DATA_DIR / ".fgistp_cache"
_FGISTP_CATALOG_TTL = 7 * 24 * 3600
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
    "source.gisogd.restrict":     {"code": "cad.zouit", "stage": "existing",
                                   "source_kind": "gisogd",
                                   "title": "ГИС ОГД: зоны с особыми условиями"},
    "source.gisogd.other":        {"code": "generic.polygon", "stage": "existing",
                                   "source_kind": "gisogd",
                                   "title": "ГИС ОГД: прочие слои"},
    # приёмники «Данных по области» (прямые открытые источники, fetch_extent)
    "source.nspd.buildings":      {"code": "oks.building", "stage": "existing",
                                   "source_kind": "nspd",
                                   "title": "НСПД: здания"},
    "source.nspd.constructions":  {"code": "generic.line", "stage": "existing",
                                   "source_kind": "nspd",
                                   "title": "НСПД: сооружения"},
    "source.nspd.zouit":          {"code": "cad.zouit", "stage": "existing",
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
    "source.osm.boundaries":      {"code": "generic.polygon", "stage": "existing",
                                   "source_kind": "osm",
                                   "title": "OSM: административные границы"},
    "source.terrain.contours":    {"code": "generic.line", "stage": "existing",
                                   "source_kind": "terrain",
                                   "title": "Рельеф: горизонтали"},
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


def _integer(value, default=0):
    """Безопасное приведение чисел из JSON/HTML к целому без падения API."""
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _known_floors(value):
    """Этажность 1…75. Пустое и негодное значение не подменяется дефолтом."""
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        floors = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None
    return floors if 1 <= floors <= 75 else None


def _building_attrs(props):
    attrs = {"purpose": props.get("purpose", "МКД")}
    floors = _known_floors(props.get("floors"))
    if floors is not None:
        attrs["floors"] = floors
    return attrs

KIND_ATTRS = {
    "boundary": lambda p: {"name": p.get("name", "Территория")},
    "restrict": lambda p: {"kind": p.get("kind", "ограничение")},
    "zone": lambda p: {"zone_code": p.get("zone_title", "Ж"),
                       "zone_title": p.get("zone_title", "Ж-1")},
    "building": _building_attrs,
    "redline": lambda p: {"status": "устанавливаемая"},
    "social": lambda p: {"kind": p.get("kind", "ОО+ДОО"),
                         "capacity": _integer(p.get("capacity"), 0)},
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


def _grado_key_of(feature):
    raw = feature.get("grado_key")
    if raw in (None, ""):
        raw = feature.get("srcKey")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _stored_curve(feature):
    """Схема кривой в СК проекта. None — у объекта нет параметрики."""
    try:
        if "arc" in feature:
            a = feature["arc"]
            return curve_spec({
                "type": "arc",
                "cx": float(a["cx"]) + ORIGIN[0], "cy": float(a["cy"]) + ORIGIN[1],
                "r": a["r"], "a0": a.get("a0", 0), "sweep": a.get("sweep", 0),
            })
        if "circle" in feature:
            c = feature["circle"]
            return curve_spec({
                "type": "circle",
                "cx": float(c["cx"]) + ORIGIN[0], "cy": float(c["cy"]) + ORIGIN[1],
                "r": c["r"],
            })
        props = feature.get("props") or {}
        radius = float(props.get("radius") or 0)
        line = feature.get("line")
        if radius > 0 and isinstance(line, list) and len(line) >= 3:
            return curve_spec({
                "type": "path", "radius": radius,
                "vertices": [[float(x) + ORIGIN[0], float(y) + ORIGIN[1]]
                             for x, y in line],
            })
    except (CurveError, PathError, TypeError, ValueError, KeyError, IndexError):
        return None
    return None


def _canvas_curve(raw):
    if not raw:
        return None
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except _json.JSONDecodeError:
            return None
    if not isinstance(raw, dict) or "type" not in raw:
        return None
    curve = dict(raw)
    if curve["type"] in ("arc", "circle"):
        curve["cx"] = curve["cx"] - ORIGIN[0]
        curve["cy"] = curve["cy"] - ORIGIN[1]
    elif curve["type"] == "path":
        curve["vertices"] = [[x - ORIGIN[0], y - ORIGIN[1]]
                             for x, y in curve.get("vertices") or []]
    return curve


def _geom_for(feature):
    kind = feature["kind"]
    if kind == "social":
        x, y = feature["point"]
        return {"type": "Point", "coordinates": [x + ORIGIN[0], y + ORIGIN[1]]}
    if "arc" in feature:
        a = feature["arc"]
        pts = tessellate_curve({
            "type": "arc", "cx": a["cx"], "cy": a["cy"], "r": a["r"],
            "a0": a.get("a0", 0), "sweep": a.get("sweep", 0),
        }, 0.05)
        return {"type": "LineString", "coordinates": _shift(pts)}
    if "circle" in feature:
        c = feature["circle"]
        pts = tessellate_curve(
            {"type": "circle", "cx": c["cx"], "cy": c["cy"], "r": c["r"]}, 0.05)
        return {"type": "LineString", "coordinates": _shift(pts)}
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
    rings = [ring]
    # Дыры холста → внутренние кольца GeoJSON, иначе выколотый полигон
    # схлопывался бы в сплошной при сохранении .grado (и в печати/экспорте).
    for h in feature.get("holes") or []:
        hr = _shift(h)
        if len(hr) >= 3:
            if hr[0] != hr[-1]:
                hr.append(list(hr[0]))
            rings.append(hr)
    return {"type": "Polygon", "coordinates": rings}


def _dyn_layer_codes(features):
    """Схема (код классификатора) каждого слоя-источника по его объектам.

    Один вид на весь слой → схема этого вида (redline→pp.red_line,
    zone→tp.func_zone, restrict→terr.restrict): KIND_ATTRS даёт атрибуты,
    которые она примет. Смесь видов (слой УДС: красные линии и границы техзон)
    → обычный слой по преобладающей геометрии.
    """
    seen = {}
    for f in features:
        lid = f.get("layer_id")
        if not (isinstance(lid, str) and (lid.startswith("source.gisogd.")
                                          or lid.startswith("source.osm."))):
            continue
        entry = seen.setdefault(lid, {"kinds": set(), "geoms": []})
        entry["kinds"].add(f.get("kind"))
        entry["geoms"].append("generic.polygon" if f.get("ring") else
                              "generic.point" if f.get("point") else "generic.line")
    codes = {}
    for lid, entry in seen.items():
        code = None
        if entry["kinds"] == {"restrict"} and "generic.polygon" in entry["geoms"]:
            # ЗОУИТ портала — зона с особыми условиями, а не «территория,
            # не подлежащая застройке»: что вычитать из площади, решает
            # пользователь своим слоем ограничений
            code = "cad.zouit"
        elif len(entry["kinds"]) == 1:
            kind_lid = _KIND_TO_LAYER.get(next(iter(entry["kinds"])))
            kind_tmpl = LAYER_TEMPLATES.get(kind_lid) if kind_lid else None
            code = kind_tmpl.get("code") if kind_tmpl else None
        codes[lid] = code or max(set(entry["geoms"]), key=entry["geoms"].count)
    return codes


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
        # слой импорта — всегда существующее положение, что бы ни прислал
        # клиент: иначе ЗОУИТ и зоны генплана попадали в раздел легенды
        # «Проектные решения» и в выноски схемы АПО
        stage = "existing" if lid.startswith(_IMPORT_LAYER_PREFIXES) else spec.get("stage")
        out[lid] = {"code": code, "title": spec.get("title"),
                    "stage": stage, "style_id": spec.get("style_id"),
                    "fields": _manifest_fields(spec)}
    return out


MAX_TEP_COORDINATE = 1_000_000_000.0


def _finite_geometry_coordinates(value):
    if isinstance(value, (list, tuple)):
        return bool(value) and all(_finite_geometry_coordinates(item) for item in value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and abs(value) <= MAX_TEP_COORDINATE


def preflight_project(features, layers=None, target="grado"):
    """Проверить, что выпуск не потеряет объекты молча.

    Возвращает структурированный отчёт для интерфейса. Проверка намеренно
    использует ту же маршрутизацию, геометрию и схему атрибутов, что и
    ``build_project``: успешный preflight означает, что все рабочие объекты
    смогут попасть в .grado/PDF/DXF. Размеры — аннотации холста, поэтому в
    модель не экспортируются и показываются только в сводке.
    """
    target = target if isinstance(target, str) and target in {
        "grado", "album", "print", "dxf"
    } else "grado"
    errors, warnings = [], []
    features = features if isinstance(features, list) else []
    layers = layers if isinstance(layers, list) else []
    templates = {**LAYER_TEMPLATES, **_user_layer_templates(layers)}
    broken, unrouted, duplicate_ids = [], [], []
    seen_ids = set()
    exportable = annotations = 0
    has_boundary = False

    def feature_label(feature, index):
        fid = feature.get("id") if isinstance(feature, dict) else None
        return str(fid) if fid not in (None, "") else f"№{index + 1}"

    for index, feature in enumerate(features):
        label = feature_label(feature, index)
        if not isinstance(feature, dict):
            broken.append(label)
            continue
        fid = feature.get("id")
        if fid not in (None, ""):
            fid_key = str(fid)
            if fid_key in seen_ids:
                duplicate_ids.append(fid_key)
            seen_ids.add(fid_key)
        if feature.get("kind") == "dim" or feature.get("layer_id") == "annotation.dimensions":
            annotations += 1
            continue
        explicit_layer = feature.get("layer_id")
        if explicit_layer and (not isinstance(explicit_layer, str) or
                               explicit_layer not in templates):
            unrouted.append(label)
            continue
        try:
            lid, _tmpl = _route(feature, templates)
        except TypeError:
            lid = None
        if lid is None:
            unrouted.append(label)
            continue
        try:
            props = feature.get("props") or {}
            KIND_ATTRS.get(feature.get("kind"), KIND_ATTRS["generic"])(props)
            geom = _geom_for(feature)
            coords = geom.get("coordinates")
            if geom.get("type") == "Point":
                valid = isinstance(coords, list) and len(coords) >= 2
            elif geom.get("type") == "LineString":
                valid = isinstance(coords, list) and len(coords) >= 2
            elif geom.get("type") == "Polygon":
                valid = (isinstance(coords, list) and coords and
                         isinstance(coords[0], list) and len(coords[0]) >= 4)
            else:
                valid = False
            if not valid or not _finite_geometry_coordinates(coords):
                raise ValueError("недостаточно точек")
        except (KeyError, IndexError, TypeError, ValueError, OverflowError):
            broken.append(label)
            continue
        exportable += 1
        if feature.get("kind") == "boundary":
            has_boundary = True

    if not features and target != "grado":
        errors.append({"code": "empty_project", "title": "В проекте нет объектов",
                       "detail": "Добавьте объекты перед выпуском файла."})
    if unrouted:
        errors.append({
            "code": "unrouted_features", "title": "Не найден слой для объектов",
            "detail": "Проверьте, что пользовательские слои проекта не удалены.",
            "feature_ids": unrouted[:12], "count": len(unrouted),
        })
    if broken:
        errors.append({
            "code": "invalid_geometry", "title": "Есть повреждённые объекты",
            "detail": "Исправьте геометрию или атрибуты отмеченных объектов.",
            "feature_ids": broken[:12], "count": len(broken),
        })
    if duplicate_ids:
        warnings.append({
            "code": "duplicate_ids", "title": "Повторяются идентификаторы объектов",
            "detail": "Файл соберётся, но выбор и история изменений могут работать неоднозначно.",
            "feature_ids": duplicate_ids[:12], "count": len(duplicate_ids),
        })
    if target in {"album", "print"} and exportable and not has_boundary:
        warnings.append({
            "code": "missing_boundary", "title": "Не задана граница территории",
            "detail": "Листы будут собраны по общему охвату объектов; ТЭП и компоновка могут быть неточными.",
        })
    if exportable > 8000:
        warnings.append({
            "code": "large_project", "title": "Очень большой проект",
            "detail": "Сборка файла может занять несколько минут.",
        })
    return {
        "target": target, "can_export": not errors,
        "errors": errors, "warnings": warnings,
        "summary": {"total": len(features), "exportable": exportable,
                    "annotations": annotations,
                    "blocked": len(broken) + len(unrouted)},
    }


def build_project(path, name, features, layers=None, project_styles=None,
                  project_custom_kinds=None, undo_stack=None, redo_stack=None,
                  studio_state=None):
    project = Project.create(path, name)
    if layers is not None:
        try:
            project.set_meta("studio_layers", _json.dumps(layers))
        except Exception:
            pass
    if isinstance(studio_state, dict):
        try:
            project.set_meta("studio_state", _json.dumps(studio_state))
        except Exception:
            pass
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
    # Слои-источники (портал ОГД по файлу/области, дороги OSM) заводятся
    # динамически: их id (source.gisogd.*/source.osm.*) нет во встроенных
    # шаблонах, и БЕЗ синтеза _route откатил бы объект по ВИДУ (правило 7),
    # а слой-источник в .grado потерялся бы. Заводим по факту наличия объектов,
    # название — из провенанса (layer_title), код — нейтральный generic.line.
    # Код слоя-источника считается по его объектам и тогда, когда слой пришёл
    # в манифесте клиента: прежние версии отдавали таким слоям generic.line при
    # любой геометрии, и слой функциональных зон не собирался вовсе.
    for lid, code in _dyn_layer_codes(features).items():
        if lid in LAYER_TEMPLATES:
            continue
        if lid in templates:
            templates[lid] = {**templates[lid], "code": code}
            continue
        title = next(((f.get("prov") or {}).get("layer_title") for f in features
                      if f.get("layer_id") == lid and (f.get("prov") or {}).get("layer_title")),
                     None)
        templates[lid] = {"code": code, "title": title or lid,
                          "stage": "existing", "source_kind": "gisogd"}
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
        kind_attrs = KIND_ATTRS.get(f["kind"], KIND_ATTRS["generic"])
        if (KIND_TO_CODE.get(f["kind"]) not in (None, tmpl["code"])
                and not (f["kind"] == "restrict" and tmpl["code"] == "cad.zouit")):
            # вид объекта не совпадает со схемой слоя (смешанный слой-источник):
            # семантические атрибуты вида схема не примет
            kind_attrs = KIND_ATTRS["generic"]
        attrs = kind_attrs(props)
        # произвольные поля атрибутивной таблицы студии → колонки .grado.
        # Пишем только колонки, которые слой реально завёл: служебные имена
        # (id, fid…) и совпадения с атрибутами классификатора он пропускает,
        # и такое поле роняло сборку («неизвестный атрибут 'id'») — у слоёв
        # ГИС ОГД поле id есть почти всегда.
        layer_cols = {u["id"] for u in made[lid].user_fields}
        for fd in tfields:
            if fd["id"] in layer_cols:
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
            style_id=f.get("style_id"), grado_key=_grado_key_of(f),
            curve=_stored_curve(f))
    return project


def _ring_area_ha(feature):
    # Дыры вычитаются: выколотая часть не принадлежит зоне, иначе ТЭП считал бы
    # её площадь своей. geometry.area понимает внутренние кольца Polygon.
    rings = [feature["ring"]] + [h for h in (feature.get("holes") or [])
                                 if len(h) >= 3]
    return geometry.area({"type": "Polygon", "coordinates": rings}) / 10000.0


def _tep_number(value):
    number = float(value)
    if not math.isfinite(number) or abs(number) > MAX_TEP_COORDINATE:
        raise ValueError("coordinate outside supported range")
    return number


def _tep_points(value, minimum):
    if not isinstance(value, (list, tuple)) or len(value) < minimum:
        raise ValueError("invalid point sequence")
    points = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise ValueError("invalid point")
        points.append([_tep_number(point[0]), _tep_number(point[1])])
    return points


def _normalize_tep_features(features):
    """Безопасный числовой снимок геометрии для живого расчёта.

    UI уже санирует проект, но ядро также вызывается напрямую из API и тестов.
    Повреждённые объекты не должны ронять весь расчёт или протаскивать NaN.
    """
    if not isinstance(features, (list, tuple)):
        return []
    normalized = []
    for feature in features:
        if not isinstance(feature, dict) or not isinstance(feature.get("kind"), str):
            continue
        clean = dict(feature)
        clean["props"] = (dict(feature["props"])
                          if isinstance(feature.get("props"), dict) else {})
        try:
            if "ring" in clean:
                clean["ring"] = _tep_points(clean["ring"], 3)
            if "line" in clean:
                clean["line"] = _tep_points(clean["line"], 2)
            if "point" in clean:
                clean["point"] = _tep_points([clean["point"]], 1)[0]
            for key in ("circle", "arc"):
                if key not in clean:
                    continue
                raw = clean[key]
                if not isinstance(raw, dict):
                    raise ValueError("invalid curve")
                curve = dict(raw)
                for field in ("cx", "cy", "r"):
                    curve[field] = _tep_number(curve[field])
                if curve["r"] <= 0:
                    raise ValueError("invalid radius")
                if key == "arc":
                    curve["a0"] = _tep_number(curve.get("a0", 0))
                    curve["sweep"] = _tep_number(curve.get("sweep", 0))
                clean[key] = curve
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        normalized.append(clean)
    return normalized


def _normalized_tep_params(params):
    if not isinstance(params, dict):
        return {}
    limits = {
        # Один источник истины с действующим пресетом moscow_krt: внешние
        # проекты и API не должны обходить диапазоны, которые показывает UI.
        "density": (1, 60), "ratio_zh": (0, 100),
        "percent_vpp": (0, 30), "education_zone": (1, 2),
        "territory_mode": (1, 2), "k_rail": (0.5, 1), "k_ba": (0.1, 1),
    }
    result = {}
    for key, (minimum, maximum) in limits.items():
        try:
            value = float(params.get(key))
        except (TypeError, ValueError, OverflowError):
            continue
        if key in {"education_zone", "territory_mode"} and value not in {1.0, 2.0}:
            continue
        if math.isfinite(value) and minimum <= value <= maximum:
            result[key] = value
    return result


# Классификатор — реестр ролей слоёв (tep_role, topology). ТЭП считается
# по ролям, а не по литералам kind (docs/fixes-geometry-layout.md, шаг 4):
# добавление нового слоя-здания = запись в классификаторе, не правка кода.
CLASSIFIER = Classifier.load()


# Слои импорта (НСПД, OSM, ГИС ОГД, ФГИС ТП, рельеф) — существующее положение.
# В ТЭП они не входят: здания НСПД и OSM — одни и те же дома, и оба попадали в
# факт СПП; ЗОУИТ объекта культурного наследия на весь центр считалась
# «территорией, не подлежащей застройке», и расчётная площадь уходила в минус.
# Что считать ограничением и проектной застройкой, решает пользователь своими
# слоями (source.constraints.restrict — ручной слой ограничений, в него не импортируют).
_IMPORT_LAYER_PREFIXES = ("source.nspd.", "source.osm.", "source.gisogd.",
                          "source.fgistp.", "source.terrain.")


def _from_import(feature):
    lid = feature.get("layer_id")
    return isinstance(lid, str) and lid.startswith(_IMPORT_LAYER_PREFIXES)


def _class_of(feature):
    """Класс классификатора объекта холста (через мост kind → код).

    Объекты слоёв импорта класса для ТЭП не имеют (см. _IMPORT_LAYER_PREFIXES).
    """
    if _from_import(feature):
        return None
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


# --- клип объектов по границе территории разработки (ТЭП считается ВНУТРИ
# границы, а не по всей карте) -------------------------------------------------
def _is_territory(f):
    cls = _class_of(f)
    return bool(cls and cls.tep_role == "terr_area" and "ring" in f)


def _ring_centroid(ring):
    a = cx = cy = 0.0
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        cr = x0 * y1 - x1 * y0
        a += cr
        cx += (x0 + x1) * cr
        cy += (y0 + y1) * cr
    if abs(a) < 1e-9:                      # вырожденное кольцо → среднее вершин
        return [sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n]
    a *= 0.5
    return [cx / (6 * a), cy / (6 * a)]


def _point_in_ring(pt, ring):
    x, y = pt
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and \
                (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _rep_point(f):
    """Представительная точка объекта для теста «внутри территории»."""
    if "ring" in f and f["ring"]:
        return _ring_centroid(f["ring"])
    if "point" in f:
        return f["point"]
    if "line" in f and f["line"]:
        return f["line"][len(f["line"]) // 2]
    if "circle" in f:
        return [f["circle"]["cx"], f["circle"]["cy"]]
    if "arc" in f:
        return [f["arc"]["cx"], f["arc"]["cy"]]
    return None


def _clip_to_territory(features):
    """Оставить только объекты, чья представительная точка внутри границ
    территории разработки (роль terr_area) + сами границы. Территория не
    задана → все объекты (поведение как раньше)."""
    terr_rings = [f["ring"] for f in features if _is_territory(f)]
    if not terr_rings:
        return features
    kept = []
    for f in features:
        if _is_territory(f):
            kept.append(f)
            continue
        pt = _rep_point(f)
        if pt is None or any(_point_in_ring(pt, r) for r in terr_rings):
            kept.append(f)
    return kept


def _polygon_rings(feature):
    return [feature["ring"]] + [h for h in (feature.get("holes") or []) if len(h) >= 3]


def _counts_as_restriction(feature):
    """Вычитается ли объект из площади территории.

    Свои слои ограничений — по роли класса. Объекты импорта (ЗОУИТ, зоны
    генплана) — только если пользователь включил учёт их категории
    (флаг tep_restrict из студии): вид зоны сам по себе не говорит, запрещена
    ли застройка, решает проектировщик.
    """
    if "ring" not in feature:
        return False
    if _from_import(feature):
        return bool(feature.get("tep_restrict"))
    cls = _class_of(feature)
    return bool(cls and cls.tep_role == "restrict_area")


def _restrict_area_ha(features):
    """Площадь ограничений ВНУТРИ границы: объединение без двойного счёта
    перекрытий и с обрезкой по границе (зона на весь город даёт только свою
    часть на участке)."""
    territory = [_polygon_rings(f) for f in features if _is_territory(f)]
    regions = [_polygon_rings(f) for f in features if _counts_as_restriction(f)]
    return union_intersection_area(regions, territory) / 10000.0


def _restriction_candidates(features):
    """Зоны импорта, попадающие в границу, по слою и категории — для блока
    «Ограничения на участке»: площадь внутри границы и включён ли учёт."""
    territory = [_polygon_rings(f) for f in features if _is_territory(f)]
    if not territory:
        return []
    groups = {}
    for f in features:
        if ("ring" not in f or not _from_import(f)
                or f.get("kind") not in ("restrict", "zone")):
            continue
        key = (f.get("layer_id"), str(f.get("tep_cat") or "*"))
        group = groups.setdefault(key, {"rings": [], "on": False})
        group["rings"].append(_polygon_rings(f))
        group["on"] = group["on"] or bool(f.get("tep_restrict"))
    out = []
    for (layer_id, cat), group in groups.items():
        area = union_intersection_area(group["rings"], territory) / 10000.0
        if area >= 0.0001:
            out.append({"layer_id": layer_id, "cat": cat,
                        "area_ha": round(area, 4), "on": group["on"]})
    out.sort(key=lambda row: -row["area_ha"])
    return out


def _make_engine_from_normalized(features, params):
    engine = Engine.from_file(PRESET)
    # ограничения — по ВСЕМ объектам с обрезкой по границе: у зоны на весь
    # город представительная точка вне участка, и обрезка по точке её теряла
    restrict_ha = _restrict_area_ha(features)
    # ТЭП считается ВНУТРИ границы территории разработки, а не по всей карте
    features = _clip_to_territory(features)
    has_territory = any(_is_territory(f) for f in features)
    # площади входов ТЭП — из ролей слоёв, не из kind
    areas = _role_areas(features)
    inputs = {r: round(a, 4) for r, a in areas.items() if r in engine.inputs}
    if has_territory:
        # ноль по геометрии остаётся нулём. Дефолт пресета 15 га сюда не подставляется.
        inputs["terr_area"] = round(areas.get("terr_area", 0.0), 4)
        if "restrict_area" in engine.inputs:
            inputs["restrict_area"] = round(restrict_ha, 4)
    elif "terr_area" in inputs:
        inputs.pop("terr_area")
    if inputs:
        engine.set_inputs(**inputs)
    for key, value in params.items():
        engine.set_input(key, value)
    engine.geometry_bound = has_territory
    return engine


def _withheld_tep(engine):
    """Нет границы — числа пресета не публикуются."""
    return {
        "inputs": {"terr_area": None, "restrict_area": None},
        "results": [{**row, "value": None} for row in engine.results()],
        "fact": {"spp": None, "density": None, "floors_unknown": 0},
        "zones": None,
        "checks": [{
            "title": "Граница территории",
            "ok": False,
            "msg": "не задана — показатели не считаются, пока нет границы территории",
        }],
        "regulatory_profile": engine.preset.get("regulatory_profile", {}),
        "has_territory": False,
    }


class _NdEngine:
    """Альбом печатает «н/д», а не дефолт движка."""

    def __init__(self, engine):
        self.preset = engine.preset
        self._rows = [{**row, "value": "н/д"} for row in engine.results()]

    def display(self, name):
        return "н/д"

    def value(self, name):
        return None

    def results(self):
        return list(self._rows)


def make_engine(features, params=None):
    return _make_engine_from_normalized(
        _normalize_tep_features(features), _normalized_tep_params(params))


def compute_tep(features, params=None):
    """Живой ТЭП: нормативный расчёт + факт по посадке зданий.

    Все показатели считаются ВНУТРИ границы территории разработки (роль
    terr_area): здания/зоны вне границы в ТЭП не входят."""
    features = _normalize_tep_features(features)
    params = _normalized_tep_params(params)
    has_territory = any(_is_territory(f) for f in features)
    restrictions = _restriction_candidates(features)
    engine = _make_engine_from_normalized(features, params)
    features = _clip_to_territory(features)
    if not engine.geometry_bound:
        return _withheld_tep(engine)
    fact_spp = 0.0
    floors_unknown = 0
    for f in features:
        cls = _class_of(f)
        if cls and cls.tep_role == "building_footprint" and "ring" in f:
            floors = _known_floors(f.get("props", {}).get("floors"))
            if floors is None:
                floors_unknown += 1
                continue
            fact_spp += _ring_area_ha(f) * 10000 * floors / 1000.0  # тыс. м²
    calc_area = engine.value("calc_area")
    results = engine.results()
    # Нормативные проверки. Не выдаём эвристические пороги за требования НГП:
    # допустимая плотность определяется ПЗЗ/ГПЗУ и документами участка.
    checks = []
    dens = round(fact_spp / calc_area, 2) if calc_area > 0 else 0
    if dens > 0:
        checks.append({"title": "Плотность по ПЗЗ/ГПЗУ", "ok": False,
                       "msg": f"Факт {dens} тыс. м²/га — требуется сверка с предельными параметрами участка"})
    pop = next((r["value"] for r in results if r["id"] == "population"), 0)
    if pop > 0:
        doo_need = engine.display("doo_norm")
        if doo_need > 0:
            zone = int(engine.value("education_zone"))
            checks.append({"title": "Образование · 2151-ПП", "ok": True,
                           "msg": f"Зона {zone}: потребность ДОО {doo_need} мест, школа {engine.display('school_norm')} мест"})
        checks.append({"title": "Транспорт · 945-ПП", "ok": False,
                       "msg": "Машино-места рассчитаны предварительно; требуется уточнение по ВРИ, территориальной зоне и типам объектов"})
    if pop > 0:
        checks.append({"title": "Территориальная доступность", "ok": False,
                       "msg": "Потребность рассчитана; существующую ёмкость и нормативные радиусы объектов необходимо проверить по окружению"})
    return {
        "inputs": {"terr_area": engine.value("terr_area"),
                   "restrict_area": engine.value("restrict_area")},
        "results": results,
        "fact": {
            "spp": round(fact_spp, 1),
            "density": dens,
            "floors_unknown": floors_unknown,
        },
        "zones": zones_report(features),
        "checks": checks,
        "regulatory_profile": engine.preset.get("regulatory_profile", {}),
        "has_territory": has_territory,
        "restrictions": restrictions,
    }


def album_engine(project, features, params=None):
    """Движок листа. Без границы территории показ — «н/д», не дефолт 15 га."""
    live = compute_tep(features, params)
    # Входы — те же, что у живого ТЭП панели (по объектам внутри границы).
    # Прежде поверх ложились суммы по слоям всего проекта: альбом считал
    # площадь ограничений по всему городу, а панель — внутри участка.
    engine = make_engine(features, params)
    engine.fact = live.get("fact") or {}   # факт по начерченным зданиям — в сводные ТЭП
    for key in ("density", "ratio_zh", "percent_vpp"):
        if params and params.get(key) is not None:
            engine.set_input(key, float(params[key]))
    if not live["has_territory"]:
        return _NdEngine(engine)
    return engine


def _album_meta(cfg, name):
    """Основная надпись из настроек альбома: пустое поле = значение по умолчанию."""
    title = cfg.get("title") if isinstance(cfg.get("title"), dict) else {}
    stamp = cfg.get("stamp") if isinstance(cfg.get("stamp"), dict) else {}

    def text(value, default=""):
        value = str(value).strip() if value is not None else ""
        return (value or default)[:120]

    return {"org": text(stamp.get("org"), text(title.get("org"), "ГРАДО")),
            "stage": text(stamp.get("stage"), "АГК"),
            "code": text(stamp.get("code")),
            "object": text(stamp.get("object"), text(name))}


def make_album(features, name, params=None, basemap=False, layers=None,
               basemap_source="osm", canvas_styles=None, project_styles=None,
               album_config=None, layer_labels=None, hidden_layers=None):
    with tempfile.TemporaryDirectory() as tmp:
        project = build_project(Path(tmp) / "studio.grado", name, features, layers, project_styles=project_styles)
        engine = album_engine(project, features, params)
        cfg = album_config if isinstance(album_config, dict) else {}
        doc = Document(name, meta=_album_meta(cfg, name))
        stamp_cfg = cfg.get("stamp") if isinstance(cfg.get("stamp"), dict) else {}
        doc.layout = GOST if stamp_cfg.get("enabled") else PRESENTATION
        doc.hidden_layers = set(hidden_layers or ())
        # canvas_styles — inline-знаки «как на холсте» (режим выпуска студии):
        # объекты несут синтетический style_id, а сам знак приходит здесь
        # project_styles — кастомные стили проекта, доступны и в стандартном режиме
        id_styles = {}
        if project_styles:
            id_styles.update(project_styles)
        if canvas_styles:
            id_styles.update(canvas_styles)
        doc.styles = StyleSet(id_styles=id_styles, layer_labels=layer_labels)

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
            layout = layout_of(doc)
            underlay = _project_underlay(project, layout.map, fit_scale(project, layout.map), source=basemap_source)
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
        doc.sheet_titles = [getattr(page, "sheet_title", "") for page in pages]
        pdf = render_document_pdf(doc, project, styles=doc.styles, engine=engine)
        project.close()
    return pdf

# Stub sheets for Phase 3 (extend as needed)
def _photo_sheet(doc, page_no):
    page = Page(A3_LANDSCAPE)
    page.frames = [
        *layout_of(doc).header(page, ["Фотофиксация"], page_no),
        TextFrame(layout_of(doc).body(), [
            "Фотофиксация существующих объектов и видовых точек.",
            "(Добавить изображения через редактор альбома или расширения.)"
        ], size=3)
    ]
    return page

def _parking_sheet(doc, page_no):
    page = Page(A3_LANDSCAPE)
    page.frames = [
        *layout_of(doc).header(page, ["Схема парковок"], page_no),
        TextFrame(layout_of(doc).body(), ["Парковки и подъезды (данные из слоёв проекта)"], size=3)
    ]
    return page

def _greenery_sheet(doc, page_no):
    page = Page(A3_LANDSCAPE)
    page.frames = [
        *layout_of(doc).header(page, ["Озеленение и благоустройство"], page_no),
        TextFrame(layout_of(doc).body(), ["Озеленение, насаждения (из слоёв проекта)"], size=3)
    ]
    return page


CODE_TO_KIND = {v: k for k, v in KIND_TO_CODE.items()}
# ЗОУИТ из импорта хранится классом cad.zouit; на холсте это тот же вид «ограничение»
CODE_TO_KIND["cad.zouit"] = "restrict"


def _to_local(pts):
    return [[x - ORIGIN[0], y - ORIGIN[1]] for x, y in pts]


def grado_to_features(path):
    """Открытие .grado обратно в студию: слои проекта → фигуры холста."""
    project = Project.open(path)
    name = project.meta("name")
    stored_layers = project.meta("studio_layers")
    user_layers = None
    if stored_layers:
        try:
            user_layers = _json.loads(stored_layers)
        except Exception:
            pass
    pk = project.meta("project_custom_kinds")
    project_kinds = []
    if pk:
        try:
            project_kinds = _json.loads(pk)
        except Exception:
            pass
    custom_kind_by_code = {
        item.get("semantic_class"): item.get("kind")
        for item in project_kinds if isinstance(item, dict)
    }
    studio_code_by_layer = {
        item.get("layer_id"): item.get("studio_code")
        for item in (user_layers or []) if isinstance(item, dict)
        and item.get("studio_code")
    }
    # ensure journal for reactive undo etc.
    try:
        from grado_reactive import Journal
        Journal(project.conn)
    except Exception:
        pass
    layer_infos = project.layers()
    out = []
    for info in layer_infos:
        studio_code = studio_code_by_layer.get(info["layer_id"], info["code"])
        kind = CODE_TO_KIND.get(studio_code) or custom_kind_by_code.get(studio_code)
        if kind is None:
            code = info["code"]
            if code.startswith("generic."):
                kind = "generic"
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
            if f.get("grado_key"):
                base["grado_key"] = f["grado_key"]
                base["srcKey"] = f["grado_key"]
            curve = _canvas_curve(f.get("curve"))
            if curve and curve.get("type") == "arc":
                arc = {k: curve[k] for k in ("cx", "cy", "r", "a0", "sweep")}
                clean = {k: v for k, v in props.items()
                         if k != "arc" and not str(k).startswith("arc_")}
                out.append({**base, "arc": arc, "props": clean})
                continue
            if curve and curve.get("type") == "circle":
                circ = {k: curve[k] for k in ("cx", "cy", "r")}
                clean = {k: v for k, v in props.items() if k != "circle"}
                out.append({**base, "circle": circ, "props": clean})
                continue
            if curve and curve.get("type") == "path":
                clean = dict(props)
                clean["radius"] = curve.get("radius") or 0
                out.append({**base, "line": curve["vertices"], "props": clean})
                continue
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
                    part = {**base, "ring": ring, "props": dict(props)}
                    holes = _canvas_holes(poly)   # дыры переживают .grado
                    if holes:
                        part["holes"] = holes
                    out.append(part)
    if not isinstance(user_layers, list):
        # Старые .grado не содержали точный манифест интерфейса. Собираем
        # достаточно данных из таблиц, чтобы два слоя одного класса снова
        # открылись как два слоя, а не слились в первый попавшийся.
        type_map = {"string": "text", "integer": "int", "number": "real"}
        user_layers = []
        for info in layer_infos:
            fields = [{"name": f["id"], "type": type_map.get(f["type"], "text")}
                      for f in project.layer_by_id(info["layer_id"]).user_fields]
            user_layers.append({
                "layer_id": info["layer_id"], "code": info["code"],
                "title": info["title"], "stage": info.get("stage"),
                "style_id": info.get("style_id"), "fields": fields,
            })
    saved_studio_state = project.meta("studio_state")
    studio_state = {}
    if saved_studio_state:
        try:
            studio_state = _json.loads(saved_studio_state)
        except Exception:
            pass
    ps = project.meta("project_styles")
    project_styles = {}
    if ps:
        try:
            project_styles = _json.loads(ps)
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
    return {"name": name, "features": out, "userLayers": user_layers,
            "studioState": studio_state, "projectStyles": project_styles,
            "projectCustomKinds": project_kinds, "undo_stack": undo_stack,
            "redo_stack": redo_stack}


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


def fgistp_catalog(force=False):
    """Каталог документов терпланирования ФГИС ТП: [{uin, name}].

    Вся РФ, ~27 000 документов (генпланы, СТП, изменения). Портал отдаёт
    каталог целиком одним запросом (~10 МБ) — кэшируем на диске gzip'ом,
    TTL 7 суток. Поиск/фильтр — на фронте по подстроке названия."""
    import gzip
    import time
    from grado_connectors import FgistpConnector
    path = FGISTP_CACHE / "catalog.json.gz"
    if not force and path.exists() and \
            (time.time() - path.stat().st_mtime) < _FGISTP_CATALOG_TTL:
        try:
            return _json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
        except Exception:
            pass
    rows = FgistpConnector().catalog()
    compact = [{"uin": str(r["uin"]), "name": " ".join((r.get("stp_name") or "").split())}
               for r in rows if r.get("uin")]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(
        _json.dumps(compact, ensure_ascii=False).encode("utf-8")))
    return compact


_FGISTP_UIN_RE = re.compile(r"^\d{5,40}$")


def fgistp_layers(uin):
    """Состав документа ФГИС ТП: [{classid, name, title, geom_type}].

    УИН валидируется (только цифры) — он уходит в URL портала."""
    from grado_connectors import FgistpConnector
    uin = str(uin or "").strip()
    if not _FGISTP_UIN_RE.match(uin):
        raise ValueError("bad uin")
    out = []
    for l in FgistpConnector().discover(uin):
        out.append({"classid": str(l.get("classid") or ""),
                    "name": " ".join((l.get("class_name") or "").split()),
                    "title": " ".join((l.get("class_title") or "").split()),
                    "geom_type": l.get("geom_type") or "100"})
    return out


# geom_type ФГИС ТП → вид объекта холста. Полигон уточняется по смыслу:
# функц. зона (знак Генплана нашёлся) → zone, раздел ЗОУИТ (classid 6030…)
# → restrict, прочее — generic.
_FGISTP_GEOM_KIND = {"010": "generic", "001": "generic"}


def import_fgistp_doc(uin, classids=None):
    """Прямой импорт векторных слоёв документа ФГИС ТП по УИН (протокол v2).

    Раскладка по правилу «слой = слой-источник» (beta.86): каждый classid →
    свой слой source.fgistp.<classid> с названием слоя портала; знак объекта —
    по имени класса (охранные/санитарные зоны → знаки ЛГР через
    _gisogd_style_for, функц. зоны → цвет Генплана через gp_style_for_zone).
    Качаются И существующие, И планируемые объекты (status_name в атрибутах)."""
    from grado_connectors import FgistpConnector
    uin = str(uin or "").strip()
    if not _FGISTP_UIN_RE.match(uin):
        raise ValueError("bad uin")
    conn = FgistpConnector()
    layers = conn.discover(uin)
    sel = {str(c) for c in classids} if classids else None
    result = conn.fetch(uin, classids=sel, layers=layers)
    manifest, d = _snapshot(conn, result)
    prov = _prov(manifest)

    by_class = {str(l.get("classid")): l for l in layers}
    features, notes = [], list(result.get("notes") or [])
    layer_defs, fields = {}, {}
    for f in result["features"]:
        props = dict(f.get("properties") or {})
        classid = None
        # class_name/class_title пришли из коннектора; classid восстановим по имени
        for cid, l in by_class.items():
            if l.get("class_name") == props.get("class_name"):
                classid = cid
                break
        if classid is None:
            continue
        linfo = by_class[classid]
        gt = linfo.get("geom_type") or "100"
        cname = props.get("class_name") or ""
        # знак и вид: функц. зона → цвет Генплана; иначе знак ЛГР по имени класса
        style_id = gp_style_for_zone(props.get("naim")) or gp_style_for_zone(cname)
        if style_id:
            kind = "zone"
        else:
            style_id = _gisogd_style_for(cname)
            kind = ("restrict" if classid.startswith("6030")
                    else _FGISTP_GEOM_KIND.get(gt, "generic"))
        lid = f"source.fgistp.{classid}"
        if lid not in layer_defs:
            layer_defs[lid] = {"id": lid, "title": f"ФГИС ТП: {cname or classid}",
                               "code": "generic.line", "kind": kind,
                               "style_id": style_id, "stage": "existing",
                               "source_kind": "fgistp"}
            fields[lid] = [
                {"name": "naim", "label": "наименование", "type": "text"},
                {"name": "status_name", "label": "статус", "type": "text"},
                {"name": "number", "label": "номер", "type": "text"},
            ]
        sem = {"name": props.get("naim") or cname,
               "status_name": props.get("status_name")}
        if kind == "zone":
            sem["zone_title"] = props.get("naim") or cname
        extra = {k: v for k, v in props.items()
                 if k not in ("class_name", "class_title") and v not in (None, "")}
        for part in _wgs_geom_to_canvas(f["geometry"]):
            feat = {"kind": kind, "layer_id": lid,
                    "props": {**sem, **extra}, "prov": dict(prov), **part}
            if style_id:
                feat["style_id"] = style_id
            features.append(feat)
    if not features:
        notes.append("в выбранных слоях нет объектов с геометрией")
    return {"features": features, "layers": list(layer_defs.values()),
            "fields": fields, "notes": notes,
            "source_doc": result.get("source_doc") or uin,
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
    # «Первый/Второй/Третий пояс…» — формы классов ФГИС ТП (СТП/генпланы)
    (("1 пояса санитар", "зона_1_пояса", "zona_1_poyasa",
      "первый пояс зоны санитарной охраны"), "lgr.sanokhr.1"),
    (("2 пояса санитар", "зона_2_пояса", "zona_2_poyasa",
      "второй пояс зоны санитарной охраны"), "lgr.sanokhr.2"),
    (("3 пояса санитар", "зона_3_пояса", "zona_3_poyasa",
      "третий пояс зоны санитарной охраны"), "lgr.sanokhr.3"),
    (("водоохран", "vodoohran"), "lgr.vodookhr"),
    (("прибрежн", "pribrezh"), "lgr.pribrezh"),
    (("сзз_расчет", "szz_raschet", "расчетн"), "lgr.szz.calc"),
    (("сзз_ориент", "szz_orient", "ориентировоч"), "lgr.szz.orient"),
    (("санитарно-защит", "sanitarno_zash", "сзз"), "lgr.szz.set"),
    # степень подтопления — СВОЙ знак (сильное/слабое ≠ среднему): на портале
    # «Зоны подтопления (сильное подтопление)» и т.п.; раньше все степени
    # сваливались в podtop.mid, а знаки podtop.strong/weak не использовались.
    (("сильного подтоплен", "сильное подтоплен", "подтопления (сильн"), "lgr.podtop.strong"),
    (("слабого подтоплен", "слабое подтоплен", "подтопления (слаб"), "lgr.podtop.weak"),
    (("подтоплен", "podtoplen"), "lgr.podtop.mid"),
    (("затоплен", "zatoplen"), "lgr.zatop"),
    (("защитная зона окн", "защитные зоны окн", "zashitnaya_zona_okn"), "lgr.okn.zashchit"),
    # полное имя без аббревиатуры — класс ФГИС ТП «Охранная зона объекта
    # культурного наследия»
    (("охранная зона окн", "охранные зоны окн", "ohrannaya_zona_okn",
      "охранная зона объекта культурного наследия",
      "охранные зоны объектов культурного наследия"), "lgr.okn.okhr"),
    (("регулирования застройки", "regulirovaniya"), "lgr.okn.reg"),
    (("охраняемого природного ландшафта", "landshaft"), "lgr.okn.landshaft"),
    (("территория окн", "территории окн", "ter_okn", "territoriya_okn",
      "территория объекта культурного наследия",
      "территории объектов культурного наследия"), "lgr.okn.terr"),
    (("охранная зона оопт", "охранные зоны оопт", "ohrannaya_zona_oopt"), "lgr.oopt.okhr"),
    # полные имена портала (без аббревиатуры «ООПТ»/«ООЗТ») — их знаки существуют,
    # но по имени не ловились; «зелёные» (ООЗТ, знак 47) ≠ «природные» (ООПТ, знак 8).
    (("особо охраняемых зеленых", "особо охраняемые зеленые",
      "особо охраняемой зеленой", "охраняемых зеленых территор", "oozt"), "lgr.oozt"),
    (("особо охраняемых природных", "особо охраняемые природные",
      "особо охраняемая природная", "охраняемых природных территор"), "lgr.oopt"),
    (("оопт", "oopt"), "lgr.oopt"),
    # --- Природный комплекс (ЛГР 18 / 21), НЕ «природная зона» Генплана ---
    # «природная зона» / «природно-жилая…» — gp.* (точное имя зоны), сюда не
    # попадают: у них нет «комплекс»/«объектов пк»/«режимы на территор».
    # Сначала режимы (код 21): l21, virtual139, заголовок «Режимы на территориях ПК».
    (("режимы на территор", "режимами регулирования", "с режимами регулирования",
      "участков объектов пк", "объектов пк"), "lgr.pk.rezhim"),
    # Затем объекты/границы ПК (код 18): l18, title библиотеки, формы падежей.
    # Не корень «комплекс» — иначе вокзальные/благоустроительные «комплексы».
    (("объекты природного комплекса", "объектов природного комплекса",
      "природного комплекса", "природный комплекс", "природном комплексе",
      "природных комплексов", "территорий природного комплекса",
      "территории природного комплекса", "prirodnogo kompleksa",
      "prirodnyj kompleks",
      # «Природные и озеленённые территории» (virtual138 + спец.назначения) —
      # это и есть природный комплекс (решение юзера): скверы/бульвары/озеленение
      "природные и озеленен", "природных и озеленен",
      "prirodnye i ozelenen"), "lgr.pk"),
    # --- полигон-знаки по полному имени портала (добавлено по просьбе юзера) ---
    (("транспортных сооружен", "transportnyh sooruzhen"), "lgr.zone.transport"),
    (("линии застройки", "линия застройки", "линий застройки"), "lgr.zastroyka"),
    # «охраняемого объекта» НЕ contiguous в «охраняемого ВОЕННОГО объекта» (то —
    # правило military ниже), поэтому ложно на военный объект не срабатывает
    (("охраняемого объекта",), "lgr.okhr.object"),
    # «пешеходных переход», НЕ «внеуличн»: последнее ловит внеуличный ТРАНСПОРТ
    # (пересадочные узлы, прохождение магистралей) — это не пешеходные переходы
    (("пешеходных переход", "пешеходный переход", "пешеходных перехода"), "lgr.peshekhod"),
    (("лесопарков", "lesopark"), "lgr.lesopark"),
    (("электроэнерг", "лэп", "elektroenerg"), "lgr.energo"),
    # газопроводы/нефтепроводы — тот же знак трубопроводов; полные имена
    # классов ФГИС ТП («Охранная зона газопроводов и систем газоснабжения»,
    # «…нефтепроводов, нефтепродуктопроводов и аммиакопроводов»)
    (("трубопровод", "truboprovod", "газопровод", "нефтепровод"), "lgr.truboprovod"),
    (("теплосет", "тепловых сет", "teplosetey"), "lgr.teplo"),
    (("связи", "svyazi"), "lgr.svyaz"),
    # знак 36 — ТЕХНИЧЕСКАЯ ЗОНА метрополитена, НЕ сама инфраструктура: раньше
    # корень «метро»/«metro» ловил линии/депо/ПП метрополитена и красил их этим
    # знаком. Требуем «техническ… зон… метрополит…»; ДО общего правила техзоны
    # (иначе «Технические зоны метрополитена» уехали бы в lgr.tech.zone).
    (("технических зон метрополит", "технические зоны метрополит",
      "технической зоны метрополит", "tehnicheskih_zon_metro",
      "tehnicheskie_zony_metro"), "lgr.metro"),
    (("железных дорог", "пожд", "zhd_"), "lgr.zhd"),
    (("приаэродром", "priaerodrom"), "lgr.priaero"),
    # корень, а не точная форма: в QML знак назван «Береговая линия», у нас
    # «Береговые полосы», на портале встречается и то и другое во мн. числе.
    # Точная подстрока «береговая полоса» не ловила НИ ОДНО из реальных имён —
    # береговая падала в «прочие слои».
    (("берегов", "beregov"), "lgr.beregovaya"),
    (("военного объекта", "военных объект", "military"), "lgr.military"),
    (("радиотехническ", "radio"), "lgr.radio"),
    # знак — ТЕХНИЧЕСКАЯ ЗОНА инж. коммуникаций: раньше корень «технич» ловил
    # «Объекты среднего ТЕХНИЧеского и высшего образования» (школы!) и схемы
    # «инженерно-ТЕХНИЧеского обеспечения»; «инженерных коммуникаций» ловил сами
    # линии/объекты сетей (это инфраструктура, а не зона). Требуем «техническ… зон…».
    (("технических зон", "техническая зона", "технической зоны",
      "технические зоны", "tehnicheskaya_zona", "tehnicheskih_zon"), "lgr.tech.zone"),
]
# общие ЗОУИТ-термины без точного знака (роутятся в restrict.hatch слоя,
# но не переопределяют style_id) — напр. просто "зоуит_реестр.geojson".
# «охранн» (двойное н), а не «охран»: корень «охран» ложно ловил «здравоОХРАНения»
# (объекты здравоохранения — это НЕ зона с особыми условиями) и «охраняемого».
# «охранная/охранные/охранных зоны» содержат «охранн», «здравоохранения» — нет.
_GISOGD_RESTRICT_HINTS = ("зоуит", "zouit", "охранн", "ohrann", "sanit", "санит")


# ---------------------------------------------------------------------------
# LineCode — ТИП ЛИНИИ ИЗ САМИХ ДАННЫХ, а не угаданный по имени слоя.
#
# Портал отдаёт его в каждом объекте (поле `linelineco` — это «LineLineCode»,
# обрезанный до 10 символов по правилам DBF; в ручном импорте SHP встречается
# «LineCode»). Ровно по нему фильтруют рабочие QML Москвы:
#     array_intersect(string_to_array("LineCode", ','), array(-1,1))
#
# Формат — список кодов через запятую, КАЖДЫЙ СО ЗНАКОМ: «1», «-1», «1,-29»,
# «-1,18,29», «1,-4,-6». Отсюда два следствия:
#   1. ОДНА геометрия может нести НЕСКОЛЬКО знаков сразу («1,-29» — это и
#      красная линия УДС, и граница техзоны инженерных коммуникаций). Поэтому в
#      QML сравнение множеств, а не равенство: объект попадает в оба правила.
#   2. Знак (+/-) различает СТОРОНУ линии, на которой лежит зона этого кода:
#      «1» и «-1» — одна и та же красная линия, но с разных сторон.
_LGR_CODE_STYLE = {s["lgr_code"]: sid for sid, s in STYLE_LIB["styles"].items()
                   if s.get("lgr_code") is not None}
_LINE_CODE_KEYS = ("linelineco", "linecode", "line_code", "lineлinecode")


def parse_line_codes(value):
    """«1,-29» → [(1, 1), (29, -1)]: (код знака ЛГР, сторона +1/-1).

    Порядок сохраняется, дубликаты кода схлопываются по первому вхождению."""
    out, seen = [], set()
    for part in str(value or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            n = int(float(part))
        except ValueError:
            continue
        if n == 0 or abs(n) in seen:
            continue
        seen.add(abs(n))
        out.append((abs(n), 1 if n > 0 else -1))
    return out


def line_codes_of(props):
    """Коды линии из атрибутов объекта (имя поля ищем без учёта регистра)."""
    for k, v in (props or {}).items():
        if k.lower() in _LINE_CODE_KEYS and v not in (None, ""):
            return parse_line_codes(v)
    return []


def lgr_style_for_code(code):
    """Код ЛГР → style_id знака (или None, если такого знака нет в библиотеке)."""
    return _LGR_CODE_STYLE.get(code)


# коды, которые по смыслу — красные линии (свой слой-приёмник студии)
_REDLINE_CODES = {1, 2, 3, 4}


def _linecode_routes(raw_props):
    """Атрибуты объекта → [(код, сторона, style_id, layer_id)] по LineCode.

    Пустой список — в объекте нет LineCode (тогда работает прежняя
    маршрутизация по имени слоя). Коды без знака в библиотеке пропускаем:
    выдумывать знак нельзя, но и молча терять объект тоже — он останется на
    прежнем маршруте, если ни один код не распознан."""
    out = []
    for code, side in line_codes_of(raw_props):
        sid = lgr_style_for_code(code)
        if not sid:
            continue
        # layer_id тут больше НЕ вычисляем: слой берётся у СЛОЯ-ИСТОЧНИКА
        # (см. _extent_spec). Раньше код уводил объект в слой-знак, и объекты
        # одного выгруженного слоя портала разъезжались по чужим слоям.
        out.append((code, side, sid, None))
    return out


def _linecode_kind(code, part):
    """Вид объекта по коду LineCode и по его геометрии.

    Красная линия в модели — только линия (pp.red_line), ограничение — только
    полигон (terr.restrict). Граница техзоны или пешеходного перехода в слое
    УДС приходит линией: с видом restrict она не собиралась ни в один слой,
    и предпроверка блокировала печать всего проекта. Такие объекты — обычная
    линия (или полигон) со своим знаком.
    """
    if code in _REDLINE_CODES:
        return "redline" if "line" in part else "generic"
    return "restrict" if "ring" in part else "generic"


def _norm_ru(s):
    """Имя для сопоставления: регистр + «ё»→«е».

    Правила писались через «е», а заголовки знаков и слои портала встречаются с
    «ё» — из-за этого объект уезжал в ЧУЖОЙ знак (молча, что хуже «прочих»):
    «Жёсткая зона 2 пояса» получала знак обычной 2-й зоны, «СЗЗ (расчётная)» —
    знак установленной СЗЗ, потому что своё правило («жестк», «расчетн») не
    срабатывало и подхватывало следующее, более общее."""
    return str(s or "").lower().replace("ё", "е")


# Правовые акты / документы портала — НЕ геометрия зоны: знак им не присваиваем.
# Иначе подстрока в названии акта ловит чужой знак — напр. «Правовой акт …границ
# территории объектов культурного наследия…» → знак территории ОКН. Документ
# уходит в «прочие» как есть (принцип: неверный знак хуже «прочих»).
_GISOGD_DOC_MARKERS = ("правовой акт", "правовые акты", "правового акта")


def _nspd_zouit_style(props):
    """Знак ЛГР зоны из НСПД по её собственным данным.

    «Вид» НСПД — одна из пяти укрупнённых групп, по нему знак не выбрать.
    Смотрим наименование по документу («Зона регулирования застройки № 1»),
    затем тип зоны по классификатору ЕГРН. Для зон охраны ОКН тип общий на
    охранную зону, зону регулирования застройки и ландшафт — различаем по
    наименованию. Не распознали — знака нет, зона остаётся своей категорией
    по типу, и знак ей назначает пользователь.
    """
    name = props.get("name_by_doc")
    zone_type = props.get("type_zone") or props.get("kind")
    sid = _gisogd_style_for(name) or _gisogd_style_for(zone_type)
    if sid:
        return sid
    # виды ст. 105 ЗК РФ, которые в НСПД названы иначе, чем слои портала
    low_type = _norm_ru(f"{zone_type} {name}")
    for marker, candidate in (("военн", "lgr.military"), ("геодезическ", "lgr.geodez"),
                              ("радиотехническ", "lgr.radio"), ("тепловых сет", "lgr.teplo"),
                              ("трубопровод", "lgr.truboprovod")):
        if marker in low_type:
            return candidate
    if "культурного наследия" in _norm_ru(zone_type):
        low = _norm_ru(name)
        for marker, candidate in (("охранн", "lgr.okn.okhr"), ("защитн", "lgr.okn.zashchit"),
                                  ("ландшафт", "lgr.okn.landshaft"),
                                  ("регулирования", "lgr.okn.reg")):
            if marker in low:
                return candidate
    return None


def _gisogd_is_document(member):
    low = _norm_ru(member)
    return any(m in low for m in _GISOGD_DOC_MARKERS)


def _gisogd_style_for(member):
    if _gisogd_is_document(member):
        return None
    low = _norm_ru(member)
    for keys, style_id in _GISOGD_STYLE_RULES:
        if any(_norm_ru(k) in low for k in keys):
            return style_id
    return None


def _gisogd_is_restrict(member):
    if _gisogd_is_document(member):
        return False
    low = member.lower()
    if any(k in low for k in _GISOGD_RESTRICT_HINTS):
        return True
    return any(any(k in low for k in keys) for keys, _ in _GISOGD_STYLE_RULES)


# Имя функциональной зоны Генплана → знак из moscow_genplan.json. Ключ — само имя
# зоны в нижнем регистре (в QML категории заданы именно по имени: поля name /
# fz_name / fztype / naimfunkzo у разных документов). Строится из библиотеки,
# чтобы не дублировать таблицу цветов: источник правды — tools/gen_moscow_genplan.py.
_GP_ZONE_STYLE = {s["gp_zone"].lower(): sid
                  for sid, s in STYLE_LIB["styles"].items() if s.get("gp_zone")}
# Числовой код типа зоны → имя зоны (из ФЗ ГП Троицк, где категории заданы полем
# fztype=100/200/…, а имя есть только в подписи). Есть документы, где в данных
# лежит код, а не название.
_GP_FZ_CODE = {str(k): v for k, v in
               (load_library("moscow_genplan").get("fz_code") or {}).items()}


# Дороги OSM: тег highway → знак из рабочих QML юзера (osm_highway.json,
# генератор tools/gen_osm_highway.py). Иерархия ширин ровно по QML: магистраль
# 1.6 мм … прочие 0.26 мм. Ключ ТОЧНЫЙ (тег OSM — фиксированный словарь, гадать
# по подстроке нельзя: 'motorway_link' ≠ 'motorway', это разные правила QML,
# хоть и один знак).
_OSM_HW_STYLE = {
    tag: sid
    for sid, s in (load_library("osm_highway").get("styles") or {}).items()
    for tag in (s.get("osm_highway") or [])
}
OSM_ROAD_COLORS = load_library("osm_highway").get("road_colors") or {}


def osm_style_for_highway(tag):
    """Тег OSM highway → style_id знака дороги. Неизвестный тег → «прочие»."""
    if not tag:
        return None
    sid = _OSM_HW_STYLE.get(str(tag).strip().lower())
    return sid or "osm.hw.other"


def gp_style_for_zone(name):
    """Имя ИЛИ числовой код функциональной зоны → style_id знака Генплана.

    Совпадение ТОЧНОЕ (с приведением регистра), по подстроке гадать нельзя:
    «природно-жилая зона» содержит «жилая зона» и увела бы объект в чужой знак.
    Слои ТиНАО названы ровно типом зоны («Жилая зона»), у старой Москвы имя —
    в naimfunkzony, у Троицка вместо имени числовой код."""
    if name in (None, ""):
        return None
    # схлопываем повторные пробелы: в данных портала встречаются «общественно-
    # жилая  зона» / «производственная  зона» с двойным пробелом — точное
    # совпадение по ним не срабатывало, и зона теряла знак (чёрный контур).
    key = " ".join(str(name).split())
    sid = _GP_ZONE_STYLE.get(key.lower())
    if sid:
        return sid
    code = key.split(".")[0]             # «100» и «100.0» из числовых полей
    zone = _GP_FZ_CODE.get(code)
    return _GP_ZONE_STYLE.get(zone.lower()) if zone else None


def gp_zone_frontend_rules():
    """Карта «тип функц. зоны → цвет Генплана» для БРАУЗЕРНОЙ редакции.

    На десктопе цвет зоны ставит сервер (gp_style_for_zone в fetch_extent), а
    браузерная редакция (pages-core.js) импортирует сама и раньше красила
    ТОЛЬКО знаки ЛГР (gisogdStyle), а функц. зоны оставались голым контуром —
    жалоба юзера «функциональные зоны просто обводкой без заливки по типу
    зоны». Печём эту карту в страницу (build_pages), чтобы веб красил как
    десктоп. Ключи name_to_style уже в нижнем регистре (= gp_style_for_zone)."""
    return {"name_to_style": dict(_GP_ZONE_STYLE),
            "code_to_zone": {c: z.lower() for c, z in _GP_FZ_CODE.items()}}


def gisogd_frontend_rules():
    """Правила маршрутизации ОГД для БРАУЗЕРНОЙ редакции — из одного источника.

    У браузера нет Python, поэтому у него была СВОЯ копия правил, и она
    неизбежно расходилась: к beta.83 веб застрял примерно на beta.60 — без
    корня «берегов» (жалоба юзера: «зоны береговых полос уходят в прочие»),
    без нормализации «ё» (жёсткая/расчётная уезжали в ЧУЖОЙ знак) и без гейта
    правовых актов. Теперь build_pages печёт этот словарь в страницу, и правка
    правила на сервере доезжает до веба сама.

    Ключи уже нормализованы (_norm_ru: регистр + «ё»→«е») — на стороне JS
    достаточно применить ту же нормализацию к имени слоя.
    """
    return {
        "layer_rules": [
            {"keys": [_norm_ru(k) for k in keys], "kind": kind, "layer_id": lid}
            for keys, kind, lid in _GISOGD_LAYER_RULES
        ],
        "style_rules": [
            {"keys": [_norm_ru(k) for k in keys], "style_id": sid,
             "layer_id": _zouit_layer_id(sid)}
            for keys, sid in _GISOGD_STYLE_RULES
        ],
        "restrict_hints": [_norm_ru(k) for k in _GISOGD_RESTRICT_HINTS],
        "doc_markers": [_norm_ru(k) for k in _GISOGD_DOC_MARKERS],
        "restrict_layer_id": "source.gisogd.restrict",
        "other_layer_id": "source.gisogd.other",
    }


def _zouit_layer_id(style_id):
    """Знак ЛГР → СВОЙ слой ЗОУИТ: lgr.vodookhr → source.gisogd.zouit.vodookhr."""
    return "source.gisogd.zouit." + style_id[len("lgr."):]


# Каждый РАСПОЗНАННЫЙ знак ЛГР получает собственный слой, а не сваливается в общий
# «ГИС ОГД: зоны с особыми условиями». Прежде водоохранные, СЗЗ, пояса санохраны и
# ООПТ жили в ОДНОМ слое: их нельзя было отключить по отдельности, оформить или
# посчитать — хотя знак у каждого свой. Слои заводятся здесь (после
# _GISOGD_STYLE_RULES), название — из заголовка знака в библиотеке ЛГР.
# _CODE_TO_LAYER считается выше и берёт только project.* — эти записи его не задевают.
for _sid, _s in STYLE_LIB["styles"].items():
    # ВСЕ знаки ЛГР, а не только те, у кого есть правило по имени слоя:
    # маршрутизация по LineCode выдаёт любой из 55 кодов, и без шаблона слой
    # не заведётся ни в модели, ни во фронте — объект молча уедет в чужой слой.
    if not _sid.startswith("lgr.") or _s.get("lgr_code") is None:
        continue
    if _s["lgr_code"] in _REDLINE_CODES:
        continue                          # красные линии — свой слой-приёмник
    _lid = _zouit_layer_id(_sid)
    if _lid not in LAYER_TEMPLATES:
        LAYER_TEMPLATES[_lid] = {"code": "terr.restrict", "stage": "existing",
                                 "source_kind": "gisogd", "style_id": _sid,
                                 "title": f"ГИС ОГД: {_s.get('title', _sid)}"}


def _member_title(member):
    """Имя файла-члена архива → название слоя для панели (без расширения/пути)."""
    import re as _re
    stem = _re.sub(r"\.(geojson|json|shp)$", "", (member or "").strip(),
                   flags=_re.I).rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return f"ГИС ОГД: {stem}" if stem else "ГИС ОГД: слой"


def _member_layer_id(member):
    """Имя члена архива ОГД → id слоя-источника. Слой повторяет файл-источник
    (требование юзера), а не знак: «beregovaya_polosa.geojson» →
    source.gisogd.member.beregovaya_polosa. Латиница/цифры/подчёркивание;
    прочее (в т.ч. кириллица) сворачивается в «_», пустое → «other»."""
    import re as _re
    stem = _re.sub(r"\.(geojson|json|shp)$", "", (member or "").strip(),
                   flags=_re.I).rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    slug = _re.sub(r"[^a-z0-9_]+", "_", stem.lower()).strip("_") or "other"
    return f"source.gisogd.member.{slug}"


def _gisogd_route(member):
    low = member.lower()
    for keys, kind, layer_id in _GISOGD_LAYER_RULES:
        if any(k in low for k in keys):
            return kind, layer_id
    style_id = _gisogd_style_for(member)
    if style_id:                         # знак опознан → свой слой этого знака
        return "restrict", _zouit_layer_id(style_id)
    if _gisogd_is_restrict(member):      # общий ЗОУИТ-термин без точного знака
        return "restrict", "source.gisogd.restrict"
    return None, None


# внутренние ключи, не показываемые как атрибуты объекта
_GISOGD_SKIP_KEYS = {"grado_member"}


def _gisogd_clean_props(raw):
    """Атрибуты объекта ОГД (кроме внутренних/пустых) → (props, [поля-столбцы]).

    Имена берём как есть (в SHP-выгрузке портала это транслит DBF, ≤10 симв.) —
    без потери исходных ключей; тип text, чтобы ничего не отбрасывать."""
    props, fields = {}, []
    for k, v in raw.items():
        if k in _GISOGD_SKIP_KEYS or v in (None, ""):
            continue
        props[k] = v
        fields.append({"name": k, "type": "text"})
    return props, fields


def _safe_stem(name):
    """Имя файла-слоя → безопасный stem для temp (сохраняем кириллицу — по
    имени идёт маршрутизация ОГД, но убираем разделители пути/расширение)."""
    stem = Path(str(name or "layer")).stem
    stem = "".join(c for c in stem if c not in '/\\:*?"<>|').strip()
    return stem or "layer"


def import_gisogd(data_bytes, filename=None):
    """Выгрузка ГИС ОГД → фигуры холста. Принимает ZIP (портал) ИЛИ одиночный
    GeoJSON (напр. экспорт из QGIS) по сигнатуре байтов.

    Для GeoJSON важно исходное имя файла (filename) — по нему идёт
    маршрутизация в слой; сохраняем его в имени temp-файла."""
    is_zip = data_bytes[:2] == b"PK"
    with tempfile.TemporaryDirectory(prefix="grado_ogd_") as td:
        if is_zip:
            p = Path(td) / "vygruzka.zip"
        else:
            # одиночный GeoJSON/JSON — имя определяет слой (маршрутизацию)
            p = Path(td) / f"{_safe_stem(filename)}.geojson"
        p.write_bytes(data_bytes)
        conn = GisogdZip()
        result = conn.fetch(str(p))
    return _gisogd_process(conn, result)


def import_gisogd_path(path):
    """Импорт ОГД по пути: ZIP, папка с распакованными слоями или одиночный
    файл. Сервер отвечает за проверку безопасности пути (см. server.py)."""
    conn = GisogdZip()
    result = conn.fetch(str(path))
    return _gisogd_process(conn, result)


def _gisogd_process(conn, result):
    """Общая раскладка результата коннектора ГИС ОГД по слоям модели.

    Координаты доводятся до локальных метров холста (_wgs_geom_to_canvas), слои
    маршрутизируются по имени члена (_GISOGD_LAYER_RULES); нераспознанные слои
    не теряются — идут в source.gisogd.other; атрибуты сохраняются как поля."""
    result["params"] = {**(result.get("params") or {}),
                        "extent": _territory_key(result["features"])}
    manifest, d = _snapshot(conn, result)
    prov = _prov(manifest)

    features, notes, unknown = [], list(result["notes"]), set()
    layer_fields = {}          # layer_id → [{name,type}] (объединение для таблицы)

    def _add_fields(lid, flds):
        acc = layer_fields.setdefault(lid, [])
        have = {fd["name"] for fd in acc}
        for fd in flds:
            if fd["name"] not in have:
                acc.append(fd)
                have.add(fd["name"])

    for f in result["features"]:
        geom = f.get("geometry")
        if not geom:
            continue
        raw = f["properties"] or {}
        member = raw.get("grado_member", "")
        # СЛОЙ = член архива (слой-источник), а не знак: объекты одного файла
        # остаются в одном слое, знак назначается объекту отдельно (ниже).
        kind, _routed = _gisogd_route(member)
        kind = kind or "generic"
        layer_id = _member_layer_id(member)
        # человекочитаемое имя слоя = имя файла-члена без расширения (для панели
        # слоёв); кладём в провенанс объекта, оттуда его берёт _layer_defs
        fprov = {**prov, "layer_title": _member_title(member)}
        name = raw.get("NAME") or raw.get("name")
        okey = f.get("grado_key")      # стабильный ключ → дедуп повторного ZIP
        extra_props, extra_fields = _gisogd_clean_props(raw)
        # WGS84 → части фигуры холста (точки/линии/кольца) единым путём —
        # не теряем ни точечные слои, ни мультигеометрию
        try:
            parts = _wgs_geom_to_canvas(geom)
        except Exception:
            continue
        if not parts:
            continue

        # LineCode из САМОГО объекта важнее маршрута по имени члена архива:
        # в выгрузке SHP портала поле называется LineCode, и по нему же
        # фильтруют рабочие QML. Одна геометрия несёт несколько кодов
        # («1,-29» — и красная линия УДС, и граница техзоны), знак кода =
        # сторона линии. Объект БЕЗ LineCode идёт прежним путём по имени.
        routes = _linecode_routes(raw)
        if routes:
            for code, side, csid, _clid in routes:
                emitted = 0
                for i, part in enumerate(parts):
                    ckind = _linecode_kind(code, part)
                    if code in _REDLINE_CODES and ckind != "redline":
                        continue
                    sem = ({"status": "существующая"} if ckind == "redline"
                           else {"kind": STYLE_LIB["styles"][csid]["title"],
                                 "basis": "ГИС ОГД"})
                    # слой — от ЧЛЕНА АРХИВА (слоя-источника), а не от знака:
                    # объекты одного выгруженного слоя остаются вместе
                    feat = {"kind": ckind, "layer_id": layer_id, **part,
                            "props": {**sem, **extra_props,
                                      "line_code": code, "line_side": side},
                            "prov": dict(fprov), "style_id": csid}
                    if okey is not None:
                        feat["srcKey"] = f"{layer_id}:{code}:{okey}#{i}"
                    features.append(feat)
                    emitted += 1
                if emitted:
                    _add_fields(layer_id, extra_fields)
            continue

        if kind == "redline":
            emitted = 0
            for i, part in enumerate(p for p in parts if "line" in p):
                feat = {"kind": "redline", "layer_id": layer_id, "line": part["line"],
                        "props": {"status": "существующая", **extra_props},
                        "prov": dict(fprov)}
                if okey is not None:
                    feat["srcKey"] = f"{layer_id}:{okey}#{i}"
                features.append(feat)
                emitted += 1
            if emitted:
                _add_fields(layer_id, extra_fields)
            continue

        if kind in ("zone", "restrict"):
            # точный знак Эталона ЛГР по имени члена архива (per-object)
            style_id = _gisogd_style_for(member)
            if style_id is None and kind == "zone":
                # функциональная зона Генплана → знак по ИМЕНИ зоны. Имя лежит в
                # разных полях у разных документов (name / fz_name / naimfunkzo(ny) /
                # funct_zon / class_name у Химок), а у слоёв ТиНАО зона названа самим
                # слоем — отсюда member в конце. fztype НЕ берём: там числовой код
                # (100/200/300), а не имя. Первое совпадение выигрывает.
                for cand in (name, raw.get("fz_name"), raw.get("naimfunkzony"),
                             raw.get("naimfunkzo"), raw.get("funct_zon"),
                             raw.get("class_name"), member):
                    style_id = gp_style_for_zone(cand)
                    if style_id:
                        break
            style_title = STYLE_LIB["styles"][style_id]["title"] if style_id else None
            emitted = 0
            for i, part in enumerate(p for p in parts if "ring" in p):
                sem = ({"zone_title": name or style_title or "ГИС ОГД"}
                       if kind == "zone"
                       else {"kind": style_title or name or "ЗОУИТ", "basis": "ГИС ОГД"})
                feat = {"kind": kind, "layer_id": layer_id, "ring": part["ring"],
                        "props": {**sem, **extra_props}, "prov": dict(fprov)}
                if style_id:
                    feat["style_id"] = style_id
                if okey is not None:
                    feat["srcKey"] = f"{layer_id}:{okey}#{i}"
                features.append(feat)
                emitted += 1
            if emitted:
                _add_fields(layer_id, extra_fields)
            continue

        # тип слоя не распознан — НЕ теряем: кладём в «прочие» как есть
        # (любая геометрия), с полной атрибутикой. СЛОЙ = файл-источник, а не
        # общая свалка «прочие»: даже без опознанного знака слой повторяет
        # выгруженный файл (требование юзера). Знак объекту не назначаем.
        for i, part in enumerate(parts):
            feat = {"kind": "generic", "layer_id": layer_id, **part,
                    "props": dict(extra_props), "prov": dict(fprov)}
            if okey is not None:
                feat["srcKey"] = f"{layer_id}:{okey}#{i}"
            features.append(feat)
        _add_fields(layer_id, extra_fields)

    return {"features": features, "notes": notes, "fields": layer_fields,
            "source_doc": result.get("source_doc"),
            # слои-приёмники (в т.ч. source.gisogd.zouit.* по LineCode) — фронт
            # их регистрирует, иначе объект молча уедет в слой по ВИДУ (правило 7)
            "layers": _layer_defs(features),
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
    "osm.boundaries": {
        "conn": "osm", "sets": ["boundaries"], "kind": "generic",
        "layer_id": "source.osm.boundaries",
        "title": "Административные границы"},
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
    "terrain.contours": {
        "conn": "terrain", "kind": "generic",
        "layer_id": "source.terrain.contours", "title": "Рельеф: горизонтали"},
}

# ГИС ОГД Москвы по видимой области — из кураторского списка коннектора
# (единый источник правды по кодам слоёв портала). Портал не фильтрует по
# bbox: слой качается целиком один раз в кэш, режем по области сами.
for _k, _spec in GISOGD_API_LAYERS.items():
    EXTENT_SOURCES[_k] = {
        "conn": "gisogd", "codes": _spec["codes"], "kind": _spec["kind"],
        "layer_id": _spec["layer_id"], "title": _spec["title"],
        **({"style_id": _spec["style_id"]} if _spec.get("style_id") else {}),
    }

# Пределы площади запроса, км² (фронт блокирует раньше, сервер — страховка):
# НСПД в плотной застройке тяжёлый (сотни участков на км²), Overpass щедрее,
# рельеф — тайловый DEM (число тайлов ограничено внутри коннектора).
EXTENT_LIMITS_KM2 = {"osm": 60.0, "nspd": 12.0, "terrain": 80.0,
                     # ОГД режется локально из кэша — ограничиваем не сеть,
                     # а объём результата на холсте
                     "gisogd": 80.0}


_GISOGD_CATALOG_TTL = 24 * 3600


def gisogd_catalog(force=False):
    """Каталог слоёв портала ОГД (≈660) с кэшем на диске: [{code,name,path}].

    Нужен, чтобы в «Данных по области» были доступны ВСЕ слои портала, а не
    только кураторские: маршрут слоя (зона/красная линия/ЗОУИТ/прочее) и знак
    ЛГР определяются по его имени — той же логикой, что у ручного импорта ОГД."""
    import time
    from grado_connectors.gisogd_api import catalog as _api_catalog
    path = GISOGD_CACHE / "catalog.json"
    if not force and path.exists() and \
            (time.time() - path.stat().st_mtime) < _GISOGD_CATALOG_TTL:
        try:
            return _json.loads(path.read_text("utf-8"))
        except Exception:
            pass
    rows = [c for c in _api_catalog() if c.get("type") == "layer" and c.get("code")]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(rows, ensure_ascii=False), "utf-8")
    return rows


def _gisogd_layer_name(code):
    for row in gisogd_catalog():
        if row.get("code") == code:
            return row.get("name") or row.get("path", "").split(" / ")[-1]
    return None


def _extent_spec(key):
    """Спец источника: кураторский из EXTENT_SOURCES ИЛИ любой слой портала ОГД
    по ключу вида «gisogd:virtual1742» (маршрут и знак — по имени слоя)."""
    if key in EXTENT_SOURCES:
        return EXTENT_SOURCES[key]
    if not key.startswith("gisogd:"):
        return None
    import re
    code = key.split(":", 1)[1]
    # код из запроса идёт в URL портала → валидируем. Предел 64: в каталоге
    # есть слои-слаги до 44 символов (напр. «Размещение объектов капитального
    # строительства»), прежний предел 40 их молча отсекал — не выгружались.
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", code):
        return None
    name = _gisogd_layer_name(code)
    if not name:
        return None
    kind, _routed = _gisogd_route(name)
    # Слой портала, НАЗВАННЫЙ прямо типом функц. зоны Генплана («Природная зона»,
    # «Природно-жилая зона», «Жилая зона» — так устроены слои Новой Москвы
    # virtual19xx/28xx), правило «функционал» НЕ ловит: у него в имени нет слова
    # «функциональные». Без этого kind оставался generic, gp_style_for_zone не
    # вызывался, и зона шла чёрным контуром — «природный комплекс без авто-стиля».
    # Имя слоя = точный тип зоны → трактуем слой как зону и красим Генпланом.
    gp_sid = gp_style_for_zone(name)
    if gp_sid and not kind:
        kind = "zone"
    # СЛОЙ = СЛОЙ-ИСТОЧНИК, а не знак (требование юзера, повторное). Прежде слой
    # выводился из знака (lgr.beregovaya → source.gisogd.zouit.beregovaya), и
    # «Зоны береговых полос» портала растворялись в чужом по смыслу «ЗОУИТ».
    # Теперь каждый выгруженный слой портала даёт СВОЙ слой с его же названием —
    # ровно как ЗУ из НСПД и ЗУ из ОГД должны быть разными слоями. Знак остаётся
    # у ОБЪЕКТА, а деление по знакам внутри слоя — через категории (fmt.cats_off).
    kind = kind or "generic"
    spec = {"conn": "gisogd", "codes": {code: name}, "kind": kind,
            "layer_id": f"source.gisogd.{code}",
            "title": f"ГИС ОГД: {name}",
            "dyn_layer": True}
    style_id = _gisogd_style_for(name) or (gp_sid if kind == "zone" else None)
    if style_id:
        spec["style_id"] = style_id
    return spec


def _layer_defs(features, specs=None):
    """Описания слоёв, в которые реально попали объекты — для фронта.

    LAYERS_V2 во фронте — СТАТИЧЕСКИЙ список, слоёв source.gisogd.zouit.* там
    нет. Без регистрации объект не находит свой слой и молча откатывается на
    слой по ВИДУ (layerOf → LAYER_BY_KIND), т.е. все ЗОУИТ снова в одной куче
    (железное правило 7). Отдаём ТОЛЬКО встроенные шаблоны: выдумывать слои на
    лету фронт не должен."""
    # Слои источника заводятся ДИНАМИЧЕСКИ: их нет и не может быть в шаблонах
    # (663 слоя каталога портала + любой файл ручного ZIP), но фронт обязан их
    # получить — иначе объект молча уедет в слой по ВИДУ (железное правило 7).
    # dyn_titles: id слоя → человекочитаемое название (из спеков выгрузки ИЛИ,
    # для ручного ZIP, из провенанса объекта).
    dyn = {sp["layer_id"]: sp.get("title")
           for sp in (specs or {}).values()
           if isinstance(sp, dict) and sp.get("dyn_layer")}
    # знак слоя-источника (для превью в списке слоёв): у слоёв, опознанных по
    # имени (ООЗТ→lgr.oozt, зона→gp.*), spec несёт style_id — прежде он терялся
    # (превью слоя рисовалось общим чёрным контуром вместо знака объектов)
    dyn_style = {sp["layer_id"]: sp.get("style_id")
                 for sp in (specs or {}).values()
                 if isinstance(sp, dict) and sp.get("dyn_layer")}
    out = {}
    dyn_codes = _dyn_layer_codes(features)
    for f in features:
        lid = f.get("layer_id")
        if not lid or lid in out:
            continue
        t = LAYER_TEMPLATES.get(lid)
        if t:
            out[lid] = {"id": lid, "title": t.get("title") or lid,
                        "code": t["code"], "kind": f.get("kind"),
                        "style_id": t.get("style_id"),
                        "stage": t.get("stage"),
                        "source_kind": t.get("source_kind")}
        elif lid.startswith("source.gisogd."):
            # слой-источник (портал по области или файл ручного ZIP): название —
            # из спеков выгрузки, иначе из имени члена в провенансе объекта
            title = dyn.get(lid) or (f.get("prov") or {}).get("layer_title")
            if not title:
                title = "ГИС ОГД: " + lid.rsplit(".", 1)[-1]
            code = dyn_codes.get(lid, "generic.line")
            out[lid] = {"id": lid, "title": title, "code": code,
                        "geometry_type": {"generic.polygon": "polygon", "generic.point": "point",
                                          "generic.line": "polyline"}.get(
                            code, "polyline" if code == "pp.red_line" else "polygon"),
                        "kind": f.get("kind"),
                        "style_id": dyn_style.get(lid), "stage": "existing",
                        "source_kind": "gisogd"}
    return list(out.values())


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
    "terrain.contours": [
        {"name": "elev", "label": "высота, м", "type": "real"}],
    # ОГД: суммарный фонд — прямой вход ТЭП, поэтому real, а не text
    "gisogd.func_zones": [
        {"name": "zone_title", "label": "наименование зоны", "type": "text"},
        {"name": "fz_type", "label": "тип функц. зоны", "type": "text"},
        {"name": "summfond", "label": "суммарный фонд, тыс. м²", "type": "real"},
        {"name": "district", "label": "район/поселение", "type": "text"}],
    "gisogd.func_zones_tinao": [
        {"name": "zone_title", "label": "наименование зоны", "type": "text"},
        {"name": "fz_type", "label": "тип функц. зоны", "type": "text"},
        {"name": "district", "label": "район/поселение", "type": "text"}],
    "gisogd.szz": [
        {"name": "kind", "label": "вид зоны", "type": "text"},
        {"name": "basis", "label": "источник", "type": "text"}],
    "gisogd.vodookhr": [
        {"name": "kind", "label": "вид зоны", "type": "text"},
        {"name": "basis", "label": "источник", "type": "text"}],
}


def _real_or_none(v):
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


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
    if src_key == "terrain.contours":
        elev = p.get("elev")
        props = {"elev": elev} if elev is not None else {}
        return props, base
    if src_key.startswith("gisogd:"):
        # Произвольный слой портала: имена полей у 663 слоёв разные — сохраняем
        # все атрибуты как есть (как ручной импорт ОГД), ничего не теряя молча.
        raw = {k: v for k, v in p.items() if k != "grado_layer_title"}
        # Функциональные зоны, выбранные как ПРОИЗВОЛЬНЫЙ слой портала («+ слой
        # портала»), а не кураторским набором gisogd.func_zones: сырой дамп полей
        # НЕ поднимал имя/код зоны в семантику, поэтому «Наименование зоны» было
        # пустым, а знак Генплана не подбирался (gp_style_for_zone получал None)
        # — зона падала в жёлтую заливку слоя по умолчанию. naimfunkzony/naimfunkzo
        # (имя) и fztip/fztype (код типа) встречаются ТОЛЬКО у ФЗ, поэтому промоушен
        # безопасен для прочих слоёв. Поднятые поля убираем из сырого дампа, чтобы
        # не двоить их с семантическими (как в кураторском пути).
        # Имя/тип зоны у ФЗ портала названы ПО-РАЗНОМУ в разных слоях: старая
        # Москва — naimfunkzony (в SHP обрезано до naimfunkzo), Щербинка/ряд ТиНАО
        # — fz_name/fz_type, Троицк — числовой classid (без имени, отдельная
        # схема). Читаем все известные варианты, иначе знак Генплана не
        # подбирается и зона рисуется чёрным контуром слоя.
        zt = (raw.get("naimfunkzony") or raw.get("naimfunkzo")
              or raw.get("fz_name"))
        fz = (raw.get("fztip") or raw.get("fztype") or raw.get("fz_type"))
        promoted, base = {}, []
        if zt not in (None, ""):
            promoted["zone_title"] = zt
            base.append({"name": "zone_title",
                         "label": "наименование зоны", "type": "text"})
            for k in ("naimfunkzony", "naimfunkzo", "fz_name"):
                raw.pop(k, None)
        if fz not in (None, ""):
            promoted["fz_type"] = str(fz)
            base.append({"name": "fz_type",
                         "label": "тип функц. зоны", "type": "text"})
            for k in ("fztip", "fztype", "fz_type"):
                raw.pop(k, None)
        props, fields = _gisogd_clean_props(raw)
        props.update(promoted)
        return props, base + fields
    if src_key.startswith("gisogd."):
        # Старая Москва (virtual1742): naimfunkzony + summfondpersp.
        # ТиНАО (virtual19xx): name/fz_type, суммарного фонда нет — тип зоны
        # подставляет диспетчер из имени слоя (grado_layer_title).
        district = p.get("name_rajon") or p.get("name_raion") or p.get("name_okrug")
        from grado_connectors.gisogd_api import norm_id
        fz = p.get("fz_type") or p.get("fztip")
        props = {k: v for k, v in {
            "zone_title": (p.get("naimfunkzony") or p.get("name")
                           or p.get("grado_layer_title")),
            "fz_type": norm_id(fz) if fz not in (None, "") else None,
            "summfond": _real_or_none(p.get("summfondpersp")),
            "kind": p.get("grado_layer_title"),
            "basis": "ГИС ОГД",
            "district": district,
        }.items() if v not in (None, "")}
        if src_key.startswith("gisogd.func_zones"):
            props.pop("kind", None)
            props.pop("basis", None)
        else:
            props.pop("zone_title", None)
            props.pop("fz_type", None)
            props.pop("summfond", None)
        return props, base
    if src_key == "osm.buildings":
        purpose = p.get("building")
        return {k: v for k, v in {
            "purpose": ("здание" if purpose in (True, "yes") else purpose),
            "floors": _int_or_none(p.get("building:levels")),
            "name": p.get("name")}.items() if v}, base
    if src_key == "osm.boundaries":
        levels = {"4": "субъект РФ", "5": "административный округ",
                  "6": "район области / городской округ",
                  "8": "район / поселение / город"}
        lvl = str(p.get("admin_level") or "")
        props = {k: v for k, v in {
            "name": p.get("name"),
            "level": levels.get(lvl, f"уровень {lvl}" if lvl else None),
        }.items() if v}
        return props, [{"name": "name", "label": "наименование", "type": "text"},
                       {"name": "level", "label": "уровень", "type": "text"}]
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
            part = {"ring": ring}
            holes = _canvas_holes(poly)
            if holes:
                part["holes"] = holes
            out.append(part)
    return out


def _canvas_holes(poly):
    """Внутренние кольца (дыры) полигона GeoJSON → кольца холста.

    poly[0] — внешний контур, poly[1:] — дыры. Прежде дыры молча
    отбрасывались на ВСЕХ путях импорта, и выколотый полигон грузился
    сплошным (жалоба юзера: «дыр нет ни в водоохранных, ни в функц. зонах,
    ни в береговых»). Кольцо холста — незамкнутое (без повтора первой точки),
    как и внешнее.
    """
    holes = []
    for h in poly[1:]:
        hr = _to_local(h)
        if len(hr) >= 2 and hr[0] == hr[-1]:
            hr = hr[:-1]
        if len(hr) >= 3:
            holes.append(hr)
    return holes


def fetch_extent(bbox, sources):
    """Выгрузка выбранных источников по экстенту → группы фигур холста.

    bbox = [west, south, east, north] (WGS84); sources ⊆ EXTENT_SOURCES.
    Возвращает {"groups": [{source, title, layer_id, kind, count, features}],
    "notes": [...], "snapshots": [манифесты для журнала источников]}."""
    from grado_connectors import (GisogdApi, NspdDirect, OsmOverpass,
                                  TerrainContours)

    specs = {k: _extent_spec(k) for k in sources}
    keys = [k for k in sources if specs.get(k)]
    notes = [f"неизвестный источник: {k}" for k in sources if not specs.get(k)]
    if not keys:
        return {"groups": [], "notes": notes or ["не выбраны источники"],
                "snapshots": []}
    area = bbox_km2(bbox)
    for conn_name in {specs[k]["conn"] for k in keys}:
        limit = EXTENT_LIMITS_KM2[conn_name]
        if area > limit:
            raise ValueError(
                f"область {area:.1f} км² больше предела {limit:.0f} км² "
                f"для источника {conn_name.upper()} — приблизьте вид")

    groups = {k: {"source": k, "title": specs[k]["title"],
                  "layer_id": specs[k]["layer_id"],
                  "kind": specs[k]["kind"], "features": [],
                  "fields": []}
              for k in keys}
    snapshots = []

    def _emit(src_key, wgs_features, prov):
        spec = specs[src_key]
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
            # знак объекта: явный из спецификации набора (кураторские слои ОГД
            # несут style_id, напр. lgr.vodookhr), иначе для функциональных зон —
            # знак Генплана по имени/коду зоны. Прежде style_id из спецификации
            # НЕ доходил до объектов вовсе: поле было заведено и не применялось,
            # поэтому зоны рисовались общим стилем слоя.
            sid = spec.get("style_id")
            if not sid and src_key == "osm.roads":
                # класс дороги — из САМИХ данных OSM (тег highway), а не из
                # имени слоя: в одном наборе едут и магистрали, и тротуары.
                # Берём СЫРОЙ тег (f["properties"]), а не props: _extent_props
                # оставляет только семантику для панели атрибутов.
                sid = osm_style_for_highway(
                    (f.get("properties") or {}).get("highway"))
            if not sid and src_key == "nspd.zouit":
                sid = _nspd_zouit_style(props)
            if not sid and spec["kind"] == "zone":
                for cand in (props.get("zone_title"), props.get("fz_type"),
                             spec.get("title")):
                    sid = gp_style_for_zone(cand)
                    if sid:
                        break
            # LineCode из САМОГО объекта — точный тип линии, а не догадка по
            # имени слоя. Одна геометрия может нести несколько кодов («1,-29» —
            # и красная линия УДС, и граница техзоны: 34% объектов слоя УДС),
            # поэтому на каждый код выпускаем СВОЙ объект в СВОЙ слой. Знак кода
            # = сторона линии → направление засечки (см. line_codes_of).
            routes = _linecode_routes(f.get("properties") or {})
            for i, part in enumerate(_wgs_geom_to_canvas(geom)):
                if routes:
                    for code, side, csid, _clid in routes:
                        # line_code/line_side — это ДАННЫЕ объекта (из LineCode),
                        # поэтому в props, а не в fmt: fmt — переопределения стиля,
                        # и сторона протекла бы в сам знак.
                        # вид — по СМЫСЛУ кода, а не по виду слоя-источника:
                        # иначе водоохранная, приехавшая из слоя красных линий,
                        # получала kind=redline и семантику красной линии.
                        # СЛОЙ — слоя-источника (spec["layer_id"]): объекты одного
                        # выгруженного слоя портала не разъезжаются по слоям-знакам,
                        # а различаются знаком (переключаются категориями).
                        cf = {"kind": _linecode_kind(code, part),
                              "layer_id": spec["layer_id"], **part,
                              "props": {**props, "line_code": code, "line_side": side},
                              "prov": dict(prov), "style_id": csid}
                        if key is not None:
                            cf["srcKey"] = f"{spec['layer_id']}:{code}:{key}#{i}"
                        g["features"].append(cf)
                    continue
                feat = {"kind": spec["kind"], "layer_id": spec["layer_id"],
                        **part, "props": dict(props), "prov": dict(prov)}
                if sid:
                    feat["style_id"] = sid
                if key is not None:
                    feat["srcKey"] = f"{spec['layer_id']}:{key}#{i}"
                g["features"].append(feat)

    # --- OSM: один запрос Overpass на все выбранные наборы ------------------
    # Overpass самый медленный (десятки секунд), поэтому запрос уходит сразу,
    # а НСПД, ГИС ОГД и рельеф грузятся, пока он идёт. Порядок групп в ответе
    # задаёт keys, от порядка обработки он не зависит.
    osm_keys = [k for k in keys if specs[k]["conn"] == "osm"]
    osm_job = None
    if osm_keys:
        from concurrent.futures import ThreadPoolExecutor
        osm_sets = sorted({s for k in osm_keys for s in specs[k]["sets"]})
        osm_conn = OsmOverpass()
        osm_pool = ThreadPoolExecutor(max_workers=1)
        osm_job = osm_pool.submit(osm_conn.fetch, bbox, osm_sets)
        osm_pool.shutdown(wait=False)

    # --- НСПД: отдельный запрос на источник (свой снимок и провенанс) -------
    nspd_keys = [k for k in keys if specs[k]["conn"] == "nspd"]
    for i, k in enumerate(nspd_keys):
        if i:
            import time
            time.sleep(0.5)   # бережём лимит частоты геопортала
        conn = NspdDirect()
        try:
            result = conn.fetch(bbox, specs[k]["categories"])
            result["params"]["source"] = k   # разные источники ≠ один снимок
            manifest, d = _snapshot(conn, result)
            if d:
                notes.append(f"{specs[k]['title']}: изменения с "
                             f"прошлого снимка +{len(d['added'])} "
                             f"−{len(d['removed'])} ~{len(d['changed'])}")
            snapshots.append(manifest)
            _emit(k, result["features"], _prov(manifest))
            notes.extend(n for n in (result.get("notes") or [])
                         if not n.endswith("отброшено: 0"))   # шум нормализации
        except Exception as e:
            notes.append(f"{specs[k]['title']}: {e}")

    # --- ГИС ОГД: слой качается целиком в кэш (портал не фильтрует по bbox),
    # режем по области локально. Один источник = несколько слоёв портала
    # (ТиНАО: тип зоны = имя слоя) → сливаем в одну группу.
    for k in [k for k in keys if specs[k]["conn"] == "gisogd"]:
        conn = GisogdApi(cache_dir=GISOGD_CACHE)
        feats, params_codes = [], []
        for code, layer_title in specs[k]["codes"].items():
            try:
                result = conn.fetch(bbox, code)
            except Exception as e:
                notes.append(f"{specs[k]['title']} [{code}]: {e}")
                continue
            for f in result["features"]:
                if layer_title:      # тип зоны/вид ЗОУИТ несёт сам слой портала
                    f["properties"]["grado_layer_title"] = layer_title
            feats.extend(result["features"])
            params_codes.append(code)
            notes.extend(result.get("notes") or [])
        if not params_codes:
            continue
        snap = make_result(feats, {"source": k, "codes": params_codes,
                                   "bbox": ",".join(f"{float(v):.5f}" for v in bbox)},
                           source_doc="ГИС ОГД Москвы (gisogd.mos.ru), выгрузка по экстенту")
        try:
            manifest, d = _snapshot(conn, snap)
            if d:
                notes.append(f"{specs[k]['title']}: изменения с прошлого "
                             f"снимка +{len(d['added'])} −{len(d['removed'])} "
                             f"~{len(d['changed'])}")
            snapshots.append(manifest)
            prov = _prov(manifest)
        except Exception as e:
            notes.append(f"{specs[k]['title']}: снимок не сохранён ({e})")
            prov = {"source": "gisogd"}
        _emit(k, feats, prov)

    # --- Рельеф: горизонтали из тайлового DEM (свой снимок и провенанс) ------
    for k in [k for k in keys if specs[k]["conn"] == "terrain"]:
        conn = TerrainContours()
        try:
            result = conn.fetch(bbox)
            manifest, _ = _snapshot(conn, result)
            snapshots.append(manifest)
            _emit(k, result["features"], _prov(manifest))
            notes.extend(result.get("notes") or [])
        except Exception as e:
            notes.append(f"{specs[k]['title']}: {e}")

    # --- OSM: разбор ответа, запрошенного в начале -------------------------
    if osm_job is not None:
        conn = osm_conn
        try:
            result = osm_job.result()
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
                for s in specs[k]["sets"]:
                    _emit(k, by_set.get(s, []), prov)
            notes.extend(result.get("notes") or [])
        except Exception as e:
            notes.append(f"OSM: {e}")

    out_groups = []
    for k in keys:
        g = groups[k]
        g["count"] = len(g["features"])
        out_groups.append(g)
    return {"groups": out_groups, "notes": notes, "snapshots": snapshots,
            # слои, в которые реально попали объекты (см. _layer_defs): фронт
            # регистрирует незнакомые, иначе объект молча уедет в слой по виду
            "layers": _layer_defs([f for g in out_groups for f in g["features"]],
                                  specs)}


def make_grado(features, name, layers=None, project_styles=None,
               project_custom_kinds=None, undo_stack=None, redo_stack=None,
               studio_state=None):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "studio.grado"
        build_project(path, name, features, layers, project_styles=project_styles,
                      project_custom_kinds=project_custom_kinds,
                      undo_stack=undo_stack, redo_stack=redo_stack,
                      studio_state=studio_state).close()
        return path.read_bytes()


def make_dxf(features, name, layers=None):
    """Чертёж в DXF R12 (координаты — СК проекта, метры UTM).

    Размерные линии — аннотация чертежа: в модель не попадают,
    в DXF выгружаются слоем RAZMERY (линия + текст длины)."""
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
               basemap_source="osm", canvas_styles=None, project_styles=None,
               layer_labels=None, hidden_layers=None):
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
            MapFrame(map_rect, scale=used_scale, underlay=underlay,
                     layers=([i["layer_id"] for i in project.layers()
                              if i["layer_id"] not in set(hidden_layers)]
                             if hidden_layers else None)),
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
        pdf = render_document_pdf(doc, project, styles=StyleSet(
            id_styles=id_styles, layer_labels=layer_labels))
        project.close()
    return pdf, used_scale


def redline_stations(line, radius, step):
    """Пикетаж вдоль красной линии (по сопряжённой кривой, если задан R)."""
    radius = float(radius)
    step = float(step)
    if not math.isfinite(radius) or radius < 0 or radius > 500:
        raise ValueError("radius must be between 0 and 500")
    if not math.isfinite(step) or step <= 0 or step > 500:
        raise ValueError("station step must be between 0 and 500")
    pts = [tuple(p) for p in line]
    path = (GPath.fillet_polyline(pts, radius)
            if radius > 0 and len(pts) >= 3
            else GPath.polyline(pts))
    out = []
    for s, pt in path.stations(step):
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
    radius = float(radius)
    dist = float(dist)
    if not math.isfinite(radius) or radius < 0 or radius > 500:
        raise ValueError("radius must be between 0 and 500")
    if not math.isfinite(dist) or dist == 0 or abs(dist) > 200:
        raise ValueError("offset distance must be between -200 and 200")
    pts = [tuple(p) for p in line]
    path = (GPath.fillet_polyline(pts, radius)
            if radius > 0 and len(pts) >= 3
            else GPath.polyline(pts))
    return [list(p) for p in path.offset(dist).linearize(0.05)]


def make_buffer(features, dist, fillet=0.0, sides="both"):
    """Генерация буферов вокруг объектов.

    dist — расстояние в метрах (положительное).
    fillet — радиус сопряжения на углах (для линий).
    sides — "left" | "right" | "both" | "outer" | "inner" (для полигонов outer=внешний).
    Возвращает список новых фичей (circle для точек, line/ring для остальных).
    """
    out = []
    d = float(dist)
    if not math.isfinite(d) or d <= 0 or d > 2000:
        raise ValueError("buffer distance must be between 0 and 2000")
    fil = float(fillet or 0)
    if not math.isfinite(fil) or fil < 0 or fil > 2000:
        raise ValueError("buffer fillet must be between 0 and 2000")
    if sides not in {"both", "left", "right", "outer", "inner"}:
        raise ValueError("unsupported buffer side")

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
            a = f["arc"]
            pts = [tuple(p) for p in tessellate_curve({
                "type": "arc", "cx": a["cx"], "cy": a["cy"], "r": a["r"],
                "a0": a.get("a0", 0), "sweep": a.get("sweep", 0),
            }, 0.05)]
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


class GeomOpError(ValueError):
    """Операция холста отклонена. В HTTP уходит только ASCII-код."""


def _geom_pair(value):
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise GeomOpError("geometry rejected")
    try:
        x, y = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        raise GeomOpError("geometry rejected") from None
    if not math.isfinite(x) or not math.isfinite(y) or max(abs(x), abs(y)) > 1e7:
        raise GeomOpError("geometry rejected")
    return (x, y)


def _geom_chain(raw, limit=4000):
    if not isinstance(raw, list) or len(raw) > limit:
        raise GeomOpError("geometry rejected")
    return [_geom_pair(p) for p in raw]


def _nearest_on_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return a
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
    return (a[0] + dx * t, a[1] + dy * t)


def _param_on_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return 0.0
    return ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2


def _seg_cross(a, b, c, d):
    den = (b[0] - a[0]) * (d[1] - c[1]) - (b[1] - a[1]) * (d[0] - c[0])
    if abs(den) < 1e-12:
        return None
    t = ((c[0] - a[0]) * (d[1] - c[1]) - (c[1] - a[1]) * (d[0] - c[0])) / den
    u = ((c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0])) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    return None


def _ray_cross(a, b, c, d):
    """Пересечение луча a→b (t >= 1, за концом b) с отрезком c–d."""
    den = (b[0] - a[0]) * (d[1] - c[1]) - (b[1] - a[1]) * (d[0] - c[0])
    if abs(den) < 1e-12:
        return None
    t = ((c[0] - a[0]) * (d[1] - c[1]) - (c[1] - a[1]) * (d[0] - c[0])) / den
    u = ((c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0])) / den
    if t >= 1 - 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    return None


def _boundary_chains(raw):
    if not isinstance(raw, list):
        raise GeomOpError("geometry rejected")
    return [_geom_chain(chain) for chain in raw if isinstance(chain, list) and len(chain) >= 2]


def _trim_line(line, click, boundaries):
    if len(line) < 2:
        raise GeomOpError("geometry rejected")
    best_i, best_d = 0, 1e18
    for i in range(len(line) - 1):
        q = _nearest_on_seg(click, line[i], line[i + 1])
        dist = math.hypot(q[0] - click[0], q[1] - click[1])
        if dist < best_d:
            best_i, best_d = i, dist
    a, b = line[best_i], line[best_i + 1]
    t_click = _param_on_seg(click, a, b)
    best = None
    for chain in boundaries:
        for j in range(len(chain) - 1):
            hit = _seg_cross(a, b, chain[j], chain[j + 1])
            if hit is None:
                continue
            t = _param_on_seg(hit, a, b)
            if best is None or abs(t - t_click) < abs(best[0] - t_click):
                best = (t, hit)
    if best is None:
        raise GeomOpError("geometry rejected")
    t, hit = best
    if t_click > t:
        kept = [list(p) for p in line[:best_i + 1]] + [[hit[0], hit[1]]]
    else:
        kept = [[hit[0], hit[1]]] + [list(p) for p in line[best_i + 1:]]
    if len(kept) < 2:
        raise GeomOpError("geometry rejected")
    return kept


def _extend_line(line, click, boundaries, tolerance):
    if len(line) < 2 or not math.isfinite(tolerance) or tolerance <= 0:
        raise GeomOpError("geometry rejected")
    start = line[0]
    end = line[-1]
    d_start = math.hypot(click[0] - start[0], click[1] - start[1])
    d_end = math.hypot(click[0] - end[0], click[1] - end[1])
    if min(d_start, d_end) > tolerance:
        raise GeomOpError("geometry rejected")
    at_end = d_end <= d_start
    a = line[-2] if at_end else line[1]
    b = end if at_end else start
    best = None
    for chain in boundaries:
        for j in range(len(chain) - 1):
            hit = _ray_cross(a, b, chain[j], chain[j + 1])
            if hit is None:
                continue
            dist = math.hypot(hit[0] - b[0], hit[1] - b[1])
            if best is None or dist < best[0]:
                best = (dist, hit)
    if best is None:
        raise GeomOpError("geometry rejected")
    out = [list(p) for p in line]
    out[-1 if at_end else 0] = [best[1][0], best[1][1]]
    return out


def _join_lines(lines, tolerance):
    if not math.isfinite(tolerance) or tolerance < 0:
        raise GeomOpError("geometry rejected")
    items = [[list(p) for p in line] for line in lines if len(line) >= 2]
    if len(items) < 2:
        raise GeomOpError("geometry rejected")
    chain = items[0]
    rest = items[1:]
    merged = 1
    while rest:
        cs, ce = chain[0], chain[-1]
        found = None
        for i, part in enumerate(rest):
            ps, pe = part[0], part[-1]
            if math.hypot(ce[0] - ps[0], ce[1] - ps[1]) <= tolerance:
                found = chain + part[1:]
            elif math.hypot(ce[0] - pe[0], ce[1] - pe[1]) <= tolerance:
                found = chain + part[-2::-1]
            elif math.hypot(cs[0] - pe[0], cs[1] - pe[1]) <= tolerance:
                found = part[:-1] + chain
            elif math.hypot(cs[0] - ps[0], cs[1] - ps[1]) <= tolerance:
                found = part[:0:-1] + chain
            if found is not None:
                chain = found
                rest.pop(i)
                merged += 1
                break
        if found is None:
            break
    if merged < 2:
        raise GeomOpError("geometry rejected")
    return chain


def geom_op(body):
    """Привязка, дуга, окружность и аффинные преобразования. Без записи файла."""
    if not isinstance(body, dict):
        raise GeomOpError("geometry rejected")
    op = body.get("op")
    try:
        if op == "snap":
            tol = float(body.get("tolerance") or 0.5)
            if not math.isfinite(tol) or tol <= 0 or tol > 100:
                raise GeomOpError("geometry rejected")
            snapper = Snapper(tolerance=tol)
            lines = body.get("polylines") or []
            if not isinstance(lines, list) or len(lines) > 2000:
                raise GeomOpError("geometry rejected")
            for line in lines:
                pts = _geom_chain(line)
                if len(pts) >= 2:
                    snapper.add_polyline(pts)
            x, y = _geom_pair([body.get("x"), body.get("y")])
            hit = snapper.snap(x, y)
            if hit is None:
                return {"hit": None}
            return {"hit": {"x": hit.point[0], "y": hit.point[1], "kind": hit.kind}}
        if op == "arc3":
            pts = _geom_chain(body.get("points"), 3)
            if len(pts) != 3:
                raise GeomOpError("geometry rejected")
            arc = Arc.from_3pts(*pts)
            return {"cx": arc.cx, "cy": arc.cy, "r": arc.r,
                    "a0": arc.a0, "sweep": arc.sweep,
                    "preview": [[round(x, 3), round(y, 3)]
                                for x, y in arc.linearize(0.05)]}
        if op == "circle":
            center = _geom_pair(body.get("center"))
            edge = _geom_pair(body.get("edge"))
            radius = math.hypot(edge[0] - center[0], edge[1] - center[1])
            if radius <= 0:
                raise GeomOpError("geometry rejected")
            spec = {"type": "circle", "cx": center[0], "cy": center[1], "r": radius}
            return {"cx": spec["cx"], "cy": spec["cy"], "r": spec["r"],
                    "preview": [[round(x, 3), round(y, 3)]
                                for x, y in tessellate_curve(spec, 0.05)]}
        if op == "fillet":
            pts = _geom_chain(body.get("line"))
            radius = float(body.get("radius"))
            if len(pts) < 3 or not math.isfinite(radius) or radius <= 0 or radius > 500:
                raise GeomOpError("geometry rejected")
            path = GPath.fillet_polyline(pts, radius)
            return {"radius": radius,
                    "vertices": [[p[0], p[1]] for p in pts],
                    "preview": [[round(x, 3), round(y, 3)]
                                for x, y in path.linearize(0.05)]}
        if op == "tessellate":
            pts = tessellate_curve(body.get("curve"), 0.05)
            return {"preview": [[round(x, 3), round(y, 3)] for x, y in pts]}
        if op == "rotate":
            degrees = float(body.get("degrees"))
            if not math.isfinite(degrees) or abs(degrees) > 3600:
                raise GeomOpError("geometry rejected")
            pts = rotate(_geom_chain(body.get("points")),
                         _geom_pair(body.get("origin")), degrees)
            return {"points": [[x, y] for x, y in pts]}
        if op == "scale":
            factor = float(body.get("factor"))
            if not math.isfinite(factor):
                raise GeomOpError("geometry rejected")
            pts = scale(_geom_chain(body.get("points")),
                        _geom_pair(body.get("origin")), factor)
            return {"points": [[x, y] for x, y in pts]}
        if op == "mirror":
            pts = mirror(_geom_chain(body.get("points")),
                         _geom_pair(body.get("a")), _geom_pair(body.get("b")))
            return {"points": [[x, y] for x, y in pts]}
        if op == "rectangle":
            a, b = _geom_pair(body.get("a")), _geom_pair(body.get("b"))
            x0, x1 = sorted((a[0], b[0]))
            y0, y1 = sorted((a[1], b[1]))
            if x1 - x0 < 1e-9 or y1 - y0 < 1e-9:
                raise GeomOpError("geometry rejected")
            return {"ring": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}
        if op == "measure":
            pts = _geom_chain(body.get("points"))
            if len(pts) < 2:
                raise GeomOpError("geometry rejected")
            length = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                         for i in range(len(pts) - 1))
            area = 0.0
            if len(pts) >= 3:
                acc = 0.0
                for i in range(len(pts)):
                    x0, y0 = pts[i]
                    x1, y1 = pts[(i + 1) % len(pts)]
                    acc += x0 * y1 - x1 * y0
                area = abs(acc) / 2.0
            return {"length_m": round(length, 3), "area_m2": round(area, 3)}
        if op == "trim":
            return {"line": _trim_line(_geom_chain(body.get("line")),
                                       _geom_pair(body.get("click")),
                                       _boundary_chains(body.get("boundaries")))}
        if op == "extend":
            return {"line": _extend_line(_geom_chain(body.get("line")),
                                         _geom_pair(body.get("click")),
                                         _boundary_chains(body.get("boundaries")),
                                         float(body.get("tolerance") or 1))}
        if op == "join":
            chains = body.get("lines")
            if not isinstance(chains, list) or len(chains) < 2:
                raise GeomOpError("geometry rejected")
            tol = float(body.get("tolerance") or 0.5)
            return {"line": _join_lines([_geom_chain(c) for c in chains], tol)}
        if op == "buffer":
            dist = float(body.get("dist"))
            feats = body.get("features")
            if not isinstance(feats, list) or not feats:
                raise GeomOpError("geometry rejected")
            made = make_buffer(feats, dist, fillet=float(body.get("fillet") or 0))
            return {"features": made}
        if op == "vertex":
            pts = [list(p) for p in _geom_chain(body.get("points"))]
            index = int(body.get("index"))
            point = _geom_pair(body.get("point"))
            if index < 0 or index >= len(pts):
                raise GeomOpError("geometry rejected")
            pts[index] = [point[0], point[1]]
            return {"points": pts}
        if op == "grid":
            step = float(body.get("step"))
            if not math.isfinite(step) or step <= 0 or step > 1000:
                raise GeomOpError("geometry rejected")
            x, y = _geom_pair([body.get("x"), body.get("y")])
            return {"x": round(x / step) * step, "y": round(y / step) * step}
    except GeomOpError:
        raise
    except (CurveError, PathError, TypeError, ValueError, OverflowError):
        raise GeomOpError("geometry rejected") from None
    raise GeomOpError("geometry rejected")
