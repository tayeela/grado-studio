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
from grado_model.tep_bridge import apply_to_engine  # noqa: E402
from grado_render import StyleSet  # noqa: E402
from grado_wizard.sheets import (MAP_RECT, apo_sheet,  # noqa: E402
                                 base_plan_sheet, fit_scale, location_sheet,
                                 ortho_sheet, tep_summary_sheet, title_sheet)

ORIGIN = (413000.0, 6178000.0)
PRESET = ROOT / "core" / "compute" / "grado_compute" / "presets" / "moscow_krt.json"

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


def build_project(path, name, features):
    project = Project.create(path, name)
    layers = {}
    for f in features:
        code = KIND_TO_CODE.get(f["kind"])
        if code is None:
            continue
        if code not in layers:
            layers[code] = project.add_layer(code)
        attrs = KIND_ATTRS[f["kind"]](f.get("props", {}))
        layers[code].add_feature(_geom_for(f), attrs=attrs)
    return project


def _ring_area_ha(feature):
    return geometry.area({"type": "Polygon",
                          "coordinates": [feature["ring"]]}) / 10000.0


def make_engine(features, params=None):
    engine = Engine.from_file(PRESET)
    terr = sum(_ring_area_ha(f) for f in features if f["kind"] == "boundary")
    restrict = sum(_ring_area_ha(f) for f in features if f["kind"] == "restrict")
    engine.set_inputs(terr_area=round(terr, 4) or engine.value("terr_area"),
                      restrict_area=round(restrict, 4))
    for key in ("density", "ratio_zh", "percent_vpp"):
        if params and params.get(key) is not None:
            engine.set_input(key, float(params[key]))
    return engine


def compute_tep(features, params=None):
    """Живой ТЭП: нормативный расчёт + факт по посадке зданий."""
    engine = make_engine(features, params)
    fact_spp = 0.0
    for f in features:
        if f["kind"] == "building":
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


def make_album(features, name, params=None, basemap=False):
    with tempfile.TemporaryDirectory() as tmp:
        project = build_project(Path(tmp) / "studio.grado", name, features)
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
        for f in project.layer(info["code"]).features():
            geom = f["geom"]
            if not geom:
                continue
            props = {k: v for k, v in f["attrs"].items() if v is not None}
            if geom["type"] == "Point":
                out.append({"kind": kind, "point": _to_local([geom["coordinates"]])[0],
                            "props": props})
            elif geom["type"] == "LineString":
                out.append({"kind": kind, "line": _to_local(geom["coordinates"]),
                            "props": props})
            else:
                polys = ([geom["coordinates"]] if geom["type"] == "Polygon"
                         else geom["coordinates"])
                for poly in polys:
                    ring = _to_local(poly[0])
                    if ring[0] == ring[-1]:
                        ring = ring[:-1]
                    out.append({"kind": kind, "ring": ring, "props": dict(props)})
    project.close()
    return {"name": name, "features": out}


def import_fgistp(payload):
    """Выгрузка ФГИС ТП от браузерного моста → фигуры холста.

    Payload расширения: grado_source=fgis_tp, WGS84, properties с
    class_name/class_title/uin. Полигоны становятся функциональными
    зонами; линейные/точечные слои пока пропускаются с пометкой."""
    from grado_connectors.crs import transform_geom, wgs84_to_utm37n

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
            features.append({"kind": "zone", "ring": ring, "props": {
                "zone_title": props.get("class_name")
                              or payload.get("grado_layer_name", "ФГИС ТП"),
                "zone_code": str(props.get("uin") or payload.get("grado_uin") or ""),
            }})
    if skipped:
        notes.append(f"пропущено не-полигонов: {skipped}")
    return {"features": features, "notes": notes,
            "source_doc": payload.get("grado_uin")}


def import_nspd(payload):
    """Захват НСПД (JSON браузерного моста GRADO) → фигуры холста.

    Коннектор нормализует (options→opt_*, дедуп, 3857→WGS84), здесь
    координаты доводятся до локальных метров холста (UTM − ORIGIN)."""
    from grado_connectors import NspdCapture
    from grado_connectors.crs import transform_geom, wgs84_to_utm37n

    result = NspdCapture().fetch(payload=payload)
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
                             "props": {k: v for k, v in attrs.items() if v}})
    return {"features": features, "notes": result["notes"],
            "source_doc": result.get("source_doc")}


def make_grado(features, name):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "studio.grado"
        build_project(path, name, features).close()
        return path.read_bytes()


def make_dxf(features, name):
    """Чертёж в DXF R12 (координаты — СК проекта, метры UTM).

    Размерные линии — аннотация чертежа: в модель не попадают,
    в DXF выгружаются слоем RAZMERY (линия + текст длины)."""
    import math
    from grado_model.dxf_export import _polyline, _text, project_to_dxf
    with tempfile.TemporaryDirectory() as tmp:
        project = build_project(Path(tmp) / "studio.grado", name, features)
        data = project_to_dxf(project)
        project.close()
    dims = [f for f in features if f["kind"] == "dim"]
    if not dims:
        return data
    text = data.decode("cp1251")
    extra = ""
    for f in dims:
        (ax, ay), (bx, by) = f["line"][0], f["line"][1]
        pts = [[ax + ORIGIN[0], ay + ORIGIN[1]], [bx + ORIGIN[0], by + ORIGIN[1]]]
        extra += _polyline("RAZMERY", pts, closed=False)
        length = math.hypot(bx - ax, by - ay)
        extra += _text("RAZMERY", (pts[0][0] + pts[1][0]) / 2,
                       (pts[0][1] + pts[1][1]) / 2, f"{length:.1f} м", 2.0)
    cut = text.rfind("0\nENDSEC")
    return (text[:cut] + extra + text[cut:]).encode("cp1251", errors="replace")


def make_print(features, name, scale=None, paper="A2", basemap=False):
    """Печать чертежа в масштабе: один лист PDF с рамкой и подписью."""
    from grado_layout import (A1_LANDSCAPE, A2_LANDSCAPE, A3_LANDSCAPE,
                              Document, MapFrame, Page, PageBorder,
                              TextFrame, render_document_pdf)
    from grado_render import StyleSet

    sizes = {"A3": A3_LANDSCAPE, "A2": A2_LANDSCAPE, "A1": A1_LANDSCAPE}
    size = sizes.get(paper, A2_LANDSCAPE)
    with tempfile.TemporaryDirectory() as tmp:
        project = build_project(Path(tmp) / "studio.grado", name, features)
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

    zones = [f for f in features if f["kind"] == "zone"]
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
