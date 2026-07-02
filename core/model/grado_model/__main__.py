"""CLI модели.

    python3 -m grado_model demo /путь/демо.grado   — создать демо-проект
    python3 -m grado_model info /путь/проект.grado — состав проекта
    python3 -m grado_model tep  /путь/проект.grado — ТЭП из геометрии проекта
"""

import argparse
import sys
from pathlib import Path

from .project import Project
from . import tep_bridge


def make_demo(path):
    p = Project.create(path, "Демо-территория 15 га")
    x0, y0 = 413000.0, 6178000.0

    boundary = p.add_layer("terr.boundary")
    boundary.add_feature(
        {"type": "Polygon", "coordinates": [[
            [x0, y0], [x0 + 500, y0], [x0 + 500, y0 + 300], [x0, y0 + 300], [x0, y0]]]},
        attrs={"name": "Демо-территория"})

    restrict = p.add_layer("terr.restrict")
    restrict.add_feature(
        {"type": "Polygon", "coordinates": [[
            [x0, y0], [x0 + 200, y0], [x0 + 200, y0 + 100], [x0, y0 + 100], [x0, y0]]]},
        attrs={"kind": "охранная зона инженерных сетей", "basis": "демо"},
        source="nspd", source_doc="реестровый №77:00-6.999")

    red = p.add_layer("pp.red_line")
    red.add_feature(
        {"type": "LineString", "coordinates": [[x0, y0 + 150], [x0 + 500, y0 + 150]]},
        attrs={"status": "устанавливаемая"})

    bld = p.add_layer("oks.building")
    bld.add_feature(
        {"type": "Polygon", "coordinates": [[
            [x0 + 250, y0 + 180], [x0 + 280, y0 + 180], [x0 + 280, y0 + 210],
            [x0 + 250, y0 + 210], [x0 + 250, y0 + 180]]]},
        attrs={"purpose": "жилой дом", "floors": 12, "gsa": 10800.0})

    soc = p.add_layer("social.object")
    soc.add_feature({"type": "Point", "coordinates": [x0 + 100, y0 + 250]},
                    attrs={"kind": "ДОО", "capacity": 150})
    return p


def print_info(p):
    print(f"Проект: {p.meta('name')}  (grado {p.meta('grado_version')}, srs {p.srs_id})")
    print(f"Файл: {p.path}")
    print("Слои:")
    for info in p.layers():
        layer = p.layer(info["code"])
        cls = p.classifier.get(info["code"])
        extra = ""
        if cls.geom_type in ("Polygon", "MultiPolygon"):
            extra = f", {layer.area_ha():.2f} га"
        elif cls.geom_type in ("LineString", "MultiLineString"):
            extra = f", {layer.length_m():.0f} м"
        role = f"  [ТЭП: {cls.tep_role}]" if cls.tep_role else ""
        print(f"  {info['code']:<18} {info['title']}: {layer.count()} объект(ов){extra}{role}")


def print_tep(p):
    sys.path.insert(0, str(Path(__file__).parents[2] / "compute"))
    from grado_compute.engine import Engine
    preset = Path(__file__).parents[2] / "compute" / "grado_compute" / "presets" / "moscow_krt.json"
    engine = Engine.from_file(preset)
    inputs = tep_bridge.apply_to_engine(p, engine)
    print("Входы ТЭП из геометрии проекта:")
    for k, v in sorted(inputs.items()):
        print(f"  {k} = {v:.4g} га")
    print()
    group = None
    for row in engine.results():
        if row["group"] != group:
            group = row["group"]
            print(f"{group}:")
        unit = f" {row['unit']}" if row["unit"] else ""
        print(f"  {row['title']}: {row['value']}{unit}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="grado_model", description="Проектная БД ГРАДО")
    parser.add_argument("command", choices=["demo", "info", "tep"])
    parser.add_argument("path", help="путь к файлу проекта .grado")
    args = parser.parse_args(argv)

    if args.command == "demo":
        p = make_demo(args.path)
        print(f"Создан демо-проект: {args.path}\n")
        print_info(p)
    elif args.command == "info":
        print_info(Project.open(args.path))
    else:
        print_tep(Project.open(args.path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
