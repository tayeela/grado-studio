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
                                 ortho_sheet, tep_summary_sheet, title_sheet)

ORIGIN = (413000.0, 6178000.0)
PRESET = ROOT / "core" / "compute" / "grado_compute" / "presets" / "moscow_krt.json"

# --- единая библиотека стилей (styles/default.json): холст + PDF + DXF ------
from grado_render import merged_library  # noqa: E402

# default.json (базовые стили ГРАДО) + moscow_lgr.json (Эталон ЛГР,
# приказ Москомархитектуры от 10.03.2025 № 65) — единая системная библиотека
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
_PROV_SOURCES = {"nspd", "fgistp", "gisogd", "import"}  # допустимые в модели


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
                                    "size": lm.get("size_px", 4)}
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
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TILE_ATTRIBUTION = "© OpenStreetMap contributors"
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


def fetch_tile_png(z, x, y):
    """Путь к PNG тайла в дисковом кэше (при промахе/битом кэше — загрузка).

    Запись атомарна (tmp + os.replace): тайлы читают параллельно холст
    (ThreadingHTTPServer) и сборка листов."""
    cache_path = TILE_CACHE / str(z) / str(x) / f"{y}.png"
    if not _valid_png(cache_path):
        req = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y),
                                     headers={"User-Agent": TILE_UA})
        with urllib.request.urlopen(req, timeout=10,
                                    context=TILE_SSL_CTX) as resp:
            data = resp.read()
        if data[:8] != _PNG_SIG:
            raise RuntimeError("tile upstream: not a PNG")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = _tmp_name(cache_path)
        tmp.write_bytes(data)
        os.replace(tmp, cache_path)
    return cache_path


def _tile_jpeg(z, x, y):
    """JPEG тайла для вставки в PDF (DCTDecode кладёт JPEG как есть).

    PNG→JPEG конвертирует системный sips (macOS), результат кэшируется
    рядом с PNG. sips пишет в свой tmp атомарно, но два параллельных
    экспорта с одним --out роняют один из rename'ов — поэтому цель
    у каждого вызова своя, в кэш её кладёт os.replace."""
    png = fetch_tile_png(z, x, y)
    jpg = png.with_suffix(".jpg")
    try:
        data = jpg.read_bytes()
    except OSError:
        data = b""
    if _valid_jpeg(data):
        return data
    tmp = _tmp_name(jpg)
    try:
        r = subprocess.run(
            ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "85",
             str(png), "--out", str(tmp)], capture_output=True)
        data = tmp.read_bytes() if r.returncode == 0 and tmp.exists() else b""
        if not _valid_jpeg(data):
            raise RuntimeError("sips: конвертация тайла не удалась")
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


def tile_underlay(center_utm, map_rect, scale, dpi=150):
    """Image-операции подложки ОСМ под карто-фрейм листа (мм).

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
            if net_down and not _valid_png(
                    TILE_CACHE / str(z) / str(xt) / f"{yt}.png"):
                failed += 1
                continue
            try:
                data = _tile_jpeg(z, xt, yt)
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


def _project_underlay(project, map_rect, scale):
    """Подложка для карто-фрейма, центрированного по габаритам проекта."""
    from grado_render import project_extent
    x0, y0, x1, y1 = project_extent(project)
    return tile_underlay(((x0 + x1) / 2.0, (y0 + y1) / 2.0), map_rect, scale)

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


def _user_layer_templates(layers):
    """Слои, созданные в панели студии («+ слой»), → шаблоны маршрутизации.

    layers — [{layer_id, code, title, stage, style_id}], присылается с
    холста при каждом экспорте (там живёт единственная копия). Встроенные
    LAYER_TEMPLATES не переопределяются: пользовательский layer_id либо
    новый, либо (при коллизии, не должно случаться) проигрывает builtin."""
    out = {}
    for spec in (layers or []):
        lid = spec.get("layer_id")
        code = spec.get("code")
        if not lid or not code or lid in LAYER_TEMPLATES:
            continue
        out[lid] = {"code": code, "title": spec.get("title"),
                    "stage": spec.get("stage"), "style_id": spec.get("style_id")}
    return out


def build_project(path, name, features, layers=None):
    project = Project.create(path, name)
    templates = {**_user_layer_templates(layers), **LAYER_TEMPLATES}
    made = {}  # layer_id → Layer
    for f in features:
        lid, tmpl = _route(f, templates)
        if lid is None:
            continue
        if lid not in made:
            made[lid] = project.add_layer(
                tmpl["code"], layer_id=lid, title=tmpl.get("title"),
                stage=tmpl.get("stage"), style_id=tmpl.get("style_id"),
                source_kind=tmpl.get("source_kind"))
        attrs = KIND_ATTRS[f["kind"]](f.get("props", {}))
        # провенанс из импорта переносится в модель (source/date/doc),
        # per-object стиль — в колонку style_id
        prov = f.get("prov") or {}
        source = prov.get("source") if prov.get("source") in _PROV_SOURCES else "manual"
        made[lid].add_feature(
            _geom_for(f), attrs=attrs, source=source,
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
    return {
        "inputs": {"terr_area": engine.value("terr_area"),
                   "restrict_area": engine.value("restrict_area")},
        "results": engine.results(),
        "fact": {
            "spp": round(fact_spp, 1),
            "density": round(fact_spp / calc_area, 2) if calc_area > 0 else 0,
        },
        "zones": zones_report(features),
    }


def make_album(features, name, params=None, basemap=False, layers=None):
    with tempfile.TemporaryDirectory() as tmp:
        project = build_project(Path(tmp) / "studio.grado", name, features, layers)
        engine = make_engine(features, params)
        apply_to_engine(project, engine)  # уточнение площадей по слоям проекта
        for key in ("density", "ratio_zh", "percent_vpp"):
            if params and params.get(key) is not None:
                engine.set_input(key, float(params[key]))
        doc = Document(name, meta={"org": "ГРАДО", "stage": "АГК"})
        doc.styles = StyleSet()
        pages = [
            title_sheet(doc),
            location_sheet(doc, project, engine.value("terr_area"), 2),
            base_plan_sheet(doc, project, 3),
        ]
        if basemap:
            underlay = _project_underlay(project, MAP_RECT, fit_scale(project))
            if underlay:  # сети нет — альбом собирается без ортофото
                pages.append(ortho_sheet(doc, project, len(pages) + 1,
                                         underlay, TILE_ATTRIBUTION))
        pages.append(apo_sheet(doc, project, engine, len(pages) + 1))
        pages.append(tep_summary_sheet(doc, engine, len(pages) + 1))
        doc.pages = pages
        doc.sheet_titles = [""] * len(pages)
        pdf = render_document_pdf(doc, project, styles=doc.styles, engine=engine)
        project.close()
    return pdf


CODE_TO_KIND = {v: k for k, v in KIND_TO_CODE.items()}


def _to_local(pts):
    return [[x - ORIGIN[0], y - ORIGIN[1]] for x, y in pts]


def grado_to_features(path):
    """Открытие .grado обратно в студию: слои проекта → фигуры холста."""
    project = Project.open(path)
    name = project.meta("name")
    out = []
    for info in project.layers():
        kind = CODE_TO_KIND.get(info["code"])
        if kind is None:
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
            if geom["type"] == "Point":
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
    project.close()
    return {"name": name, "features": out}


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
        for ring in rings:
            local = [[x - ORIGIN[0], y - ORIGIN[1]] for x, y in ring[0]]
            if local[0] == local[-1]:
                local = local[:-1]
            features.append({"kind": "parcel", "ring": local,
                             "props": {k: v for k, v in attrs.items() if v},
                             "prov": dict(prov)})
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
    (("зоуит", "zouit", "охран", "ohran", "sanit", "санит"), "restrict",
     "source.gisogd.restrict"),
]


def _gisogd_route(member):
    low = member.lower()
    for keys, kind, layer_id in _GISOGD_LAYER_RULES:
        if any(k in low for k in keys):
            return kind, layer_id
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
        try:
            utm = transform_geom(geom, wgs84_to_utm37n)
        except Exception:
            continue
        if kind == "redline":
            if utm["type"] != "LineString":
                continue
            features.append({"kind": "redline", "layer_id": layer_id,
                             "line": _to_local(utm["coordinates"]),
                             "props": {"status": "существующая"}, "prov": dict(prov)})
            continue
        polys = ([utm["coordinates"]] if utm["type"] == "Polygon"
                 else utm["coordinates"] if utm["type"] == "MultiPolygon" else [])
        for poly in polys:
            ring = _to_local(poly[0])
            if ring[0] == ring[-1]:
                ring = ring[:-1]
            props = ({"zone_title": name or "ГИС ОГД"} if kind == "zone"
                     else {"kind": name or "ЗОУИТ", "basis": "ГИС ОГД"})
            features.append({"kind": kind, "layer_id": layer_id, "ring": ring,
                             "props": props, "prov": dict(prov)})
    return {"features": features, "notes": notes,
            "source_doc": result.get("source_doc"),
            "snapshot": manifest, "diff": d}


def make_grado(features, name, layers=None):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "studio.grado"
        build_project(path, name, features, layers).close()
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


def make_print(features, name, scale=None, paper="A2", basemap=False, layers=None):
    """Печать чертежа в масштабе: один лист PDF с рамкой и подписью."""
    from grado_layout import (A1_LANDSCAPE, A2_LANDSCAPE, A3_LANDSCAPE,
                              Document, MapFrame, Page, PageBorder,
                              TextFrame, render_document_pdf)
    from grado_render import StyleSet

    sizes = {"A3": A3_LANDSCAPE, "A2": A2_LANDSCAPE, "A1": A1_LANDSCAPE}
    size = sizes.get(paper, A2_LANDSCAPE)
    with tempfile.TemporaryDirectory() as tmp:
        project = build_project(Path(tmp) / "studio.grado", name, features, layers)
        page = Page(size)
        ix, iy, iw, ih = page.inner_rect()
        map_rect = (ix + 8, iy + 16, iw - 16, ih - 24)
        used_scale = int(scale) if scale else fit_scale(project, map_rect)
        underlay = (_project_underlay(project, map_rect, used_scale)
                    if basemap else None)
        caption_extra = f" · подложка {TILE_ATTRIBUTION}" if underlay else ""
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
        pdf = render_document_pdf(doc, project, styles=StyleSet())
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
