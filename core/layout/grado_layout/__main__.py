"""Демо-альбом: все модули ядра в одном сценарии.

geom (покрытие зон, красная линия с сопряжениями) → model (.grado) →
compute+connectors-мост (ТЭП из геометрии) → render (стили) → layout
(листы, легенда, штамп) → PDF.

    python3 -m grado_layout demo /путь/альбом.pdf
"""

import sys
import tempfile
from pathlib import Path

CORE = Path(__file__).parents[2]
for mod in ("model", "compute", "reactive", "render", "geom", "layout"):
    p = str(CORE / mod)
    if p not in sys.path:
        sys.path.insert(0, p)

from grado_compute.engine import Engine  # noqa: E402
from grado_geom import Coverage, Path as GPath  # noqa: E402
from grado_model import Project  # noqa: E402

from .compose import render_document_pdf  # noqa: E402
from .frames import (LegendFrame, MapFrame, PageBorder, StampFrame,  # noqa: E402
                     TableFrame)
from .model import A3_LANDSCAPE, Document, Page  # noqa: E402

PRESET = CORE / "compute" / "grado_compute" / "presets" / "moscow_krt.json"
X0, Y0 = 413000.0, 6178000.0


def ring(x0, y0, w, h):
    return [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]


def build_demo_project(path):
    p = Project.create(path, "Демо-территория 15 га")

    p.add_layer("terr.boundary").add_feature(
        {"type": "Polygon", "coordinates": [ring(X0, Y0, 500, 300) + [(X0, Y0)]]},
        attrs={"name": "Демо-территория"})
    p.add_layer("terr.restrict").add_feature(
        {"type": "Polygon", "coordinates": [ring(X0, Y0, 200, 100) + [(X0, Y0)]]},
        attrs={"kind": "охранная зона"}, source="nspd")

    # функциональные зоны — топологическое покрытие с общей границей
    cov = Coverage.from_polygons({
        "Ж-1": ring(X0, Y0, 300, 300),
        "О-1": ring(X0 + 300, Y0, 200, 300)})
    cov.validate()
    zones = p.add_layer("tp.func_zone")
    for fid in ("Ж-1", "О-1"):
        pts = [list(pt) for pt in cov.polygon(fid)]
        zones.add_feature({"type": "Polygon", "coordinates": [pts + [pts[0]]]},
                          attrs={"zone_code": fid, "zone_title": fid},
                          source="fgistp")

    # красная линия: полилиния с тангенциальным сопряжением R=50
    red = GPath.fillet_polyline(
        [(X0 - 20, Y0 + 150), (X0 + 250, Y0 + 150), (X0 + 250, Y0 + 330)],
        radius=50)
    p.add_layer("pp.red_line").add_feature(
        {"type": "LineString",
         "coordinates": [list(pt) for pt in red.linearize(0.05)]},
        attrs={"status": "устанавливаемая"})

    bld = p.add_layer("oks.building")
    for i, (dx, dy, floors) in enumerate([(60, 190, 12), (140, 200, 9), (90, 40, 3)]):
        bld.add_feature(
            {"type": "Polygon",
             "coordinates": [ring(X0 + dx, Y0 + dy, 40, 25) + [(X0 + dx, Y0 + dy)]]},
            attrs={"purpose": "жилой дом", "floors": floors})

    p.add_layer("social.object").add_feature(
        {"type": "Point", "coordinates": [X0 + 380, Y0 + 220]},
        attrs={"kind": "ДОО", "capacity": 150})
    return p


def build_album(project, engine):
    doc = Document(
        "Демо-альбом ГРАДО",
        meta={"code": "ГРАДО-АГК-2026-01", "object": "Демо-территория, 15 га",
              "stage": "АГК", "org": "ГРАДО Студия"})

    page1 = Page(A3_LANDSCAPE)
    page1.frames = [
        PageBorder(page1),
        MapFrame((30, 15, 230, 215), scale=2500),
        LegendFrame((270, 15, 135, 120)),
        StampFrame(page1),
    ]

    rows = [(r["title"], str(r["value"]), r["unit"])
            for r in engine.results()]
    page2 = Page(A3_LANDSCAPE)
    page2.frames = [
        PageBorder(page2),
        TableFrame((30, 15, 220, 250),
                   [("Показатель", 150, "left"), ("Значение", 35, "right"),
                    ("Ед. изм.", 30, "left")],
                   rows, title="Технико-экономические показатели"),
        StampFrame(page2),
    ]

    doc.pages = [page1, page2]
    doc.sheet_titles = ["Опорный план. М 1:2500",
                        "Технико-экономические показатели"]
    return doc


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2 or argv[0] != "demo":
        print(__doc__)
        return 2
    out_pdf = Path(argv[1])

    sys.path.insert(0, str(CORE / "connectors"))
    from grado_model.tep_bridge import apply_to_engine

    with tempfile.TemporaryDirectory() as tmp:
        project = build_demo_project(Path(tmp) / "demo.grado")
        engine = Engine.from_file(PRESET)
        inputs = apply_to_engine(project, engine)
        doc = build_album(project, engine)
        pdf = render_document_pdf(doc, project, engine=engine)
        project.close()

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    out_pdf.write_bytes(pdf)
    print(f"Альбом: {out_pdf} ({len(pdf) / 1024:.0f} КБ, {len(doc.pages)} листа)")
    print(f"ТЭП из геометрии: {inputs}")
    print(f"Население: {engine.display('population')} чел")
    return 0


if __name__ == "__main__":
    sys.exit(main())
