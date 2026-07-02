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
}


def _shift(pts):
    return [[x + ORIGIN[0], y + ORIGIN[1]] for x, y in pts]


def _geom_for(feature):
    kind = feature["kind"]
    if kind == "social":
        x, y = feature["point"]
        return {"type": "Point", "coordinates": [x + ORIGIN[0], y + ORIGIN[1]]}
    if kind == "redline":
        return {"type": "LineString", "coordinates": _shift(feature["line"])}
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


def make_grado(features, name):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "studio.grado"
        build_project(path, name, features).close()
        return path.read_bytes()
