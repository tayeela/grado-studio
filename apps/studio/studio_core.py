"""Ядро студии: черчение (JSON с холста) → проект → ТЭП → альбом.

Клиент рисует в локальных метрах (ось Y вверх); здесь фигуры ложатся в
проект .grado (UTM, смещение ORIGIN), ТЭП считается движком из геометрии,
альбом собирается листами мастера территории.
"""

import sys
import tempfile
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
from grado_wizard.sheets import (apo_sheet, base_plan_sheet,  # noqa: E402
                                 location_sheet, tep_summary_sheet,
                                 title_sheet)

ORIGIN = (413000.0, 6178000.0)
PRESET = ROOT / "core" / "compute" / "grado_compute" / "presets" / "moscow_krt.json"

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
    }


def make_album(features, name, params=None):
    with tempfile.TemporaryDirectory() as tmp:
        project = build_project(Path(tmp) / "studio.grado", name, features)
        engine = make_engine(features, params)
        apply_to_engine(project, engine)  # уточнение площадей по слоям проекта
        for key in ("density", "ratio_zh", "percent_vpp"):
            if params and params.get(key) is not None:
                engine.set_input(key, float(params[key]))
        doc = Document(name, meta={"org": "ГРАДО", "stage": "АГК"})
        doc.styles = StyleSet()
        doc.pages = [
            title_sheet(doc),
            location_sheet(doc, project, engine.value("terr_area"), 2),
            base_plan_sheet(doc, project, 3),
            apo_sheet(doc, project, engine, 4),
            tep_summary_sheet(doc, engine, 5),
        ]
        doc.sheet_titles = [""] * 5
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
    """Чертёж в DXF R12 (координаты — СК проекта, метры UTM)."""
    from grado_model.dxf_export import project_to_dxf
    with tempfile.TemporaryDirectory() as tmp:
        project = build_project(Path(tmp) / "studio.grado", name, features)
        data = project_to_dxf(project)
        project.close()
    return data


def redline_offset(line, radius, dist):
    """Офсет красной линии через ядро geom (fillet + offset G1-цепи).

    dist > 0 — влево по ходу линии. Возвращает полилинию в тех же
    локальных координатах; сопряжение уже вшито в геометрию."""
    pts = [tuple(p) for p in line]
    path = (GPath.fillet_polyline(pts, float(radius))
            if radius and float(radius) > 0 and len(pts) >= 3
            else GPath.polyline(pts))
    return [list(p) for p in path.offset(float(dist)).linearize(0.05)]
