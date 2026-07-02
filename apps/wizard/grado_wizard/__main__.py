"""CLI мастера территории.

    python3 -m grado_wizard demo /путь/альбом.pdf
    python3 -m grado_wizard build граница.geojson --name "…" --out альбом.pdf
       (граница в WGS84; пересчёт в СК проекта — модуль crs сервиса данных)
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from .wizard import TerritoryWizard


def _boundary_from_geojson(path):
    from grado_connectors import crs
    gj = json.loads(Path(path).read_text(encoding="utf-8"))
    feature = gj["features"][0] if gj.get("type") == "FeatureCollection" else gj
    geom = feature.get("geometry", feature)
    if geom["type"] != "Polygon":
        raise SystemExit("ожидается Polygon с границей территории")
    ring = geom["coordinates"][0]
    return [crs.wgs84_to_utm37n(lon, lat) for lon, lat in ring]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="grado_wizard",
                                     description="Мастер территории ГРАДО")
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo")
    d.add_argument("out")
    b = sub.add_parser("build")
    b.add_argument("boundary")
    b.add_argument("--name", default="Архитектурно-градостроительная концепция")
    b.add_argument("--out", required=True)
    b.add_argument("--density", type=float, default=None)
    args = parser.parse_args(argv)

    if args.cmd == "demo":
        wizard = TerritoryWizard(
            "Архитектурно-градостроительная концепция\n"
            "развития демо-территории (ЖК «Образцовый»)",
            params={"density": 10, "ratio_zh": 66})
        out = Path(args.out)
    else:
        params = {"density": args.density} if args.density else None
        wizard = TerritoryWizard(args.name,
                                 boundary=_boundary_from_geojson(args.boundary),
                                 params=params)
        out = Path(args.out)

    with tempfile.TemporaryDirectory() as tmp:
        project, engine, doc = wizard.run(Path(tmp) / "territory.grado")
        pdf = wizard.render_pdf(project, engine, doc)
        project.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf)
    print(f"Альбом АГК: {out} ({len(pdf) / 1024:.0f} КБ, {len(doc.pages)} листов)")
    print(f"Территория: {engine.display('terr_area')} га, "
          f"ограничения {engine.display('restrict_area')} га")
    print(f"СПП: {engine.display('spp')} тыс. м², "
          f"население {engine.display('population')} чел")
    return 0


if __name__ == "__main__":
    sys.exit(main())
