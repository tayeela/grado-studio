"""Сверка пластины карты (rust/crates/plate) с векторной печатью: сцены карты блока из образца проекта
(apps/grado2/tests/fixtures/next_ui_project.grado2) с заливками, прозрачностью, штриховкой, штрихом, линиями и точками
→ out/<сцена>.png (Rust) и out/<сцена>.svg (тот же список операций SVG-бэкендом, без подписей).
Запуск: PYTHONPATH=<папка с grado_rs> ~/.grado2/venv/bin/python rust/parity/plate/dump.py; сравнение — compare.mjs."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/grado2"))
import server as S  # noqa: E402
import layout_io  # noqa: E402
from grado_render import render_svg  # noqa: E402

OUT = Path(__file__).parent / "out"
DPI = 150
proj = json.loads((ROOT / "apps/grado2/tests/fixtures/next_ui_project.grado2").read_text("utf-8"))
D = proj["data"]


def feats(key, **st):
    return [{"g": f["geometry"], **st} for f in D[key]["fc"]["features"] if f.get("geometry")]


def scenes():
    base = {"w": 180, "h": 120, "center": [37.803, 55.826], "basemap": "none"}
    layers = [
        {"title": "Участки", "features": feats("egrn.parcels", fill="#f1ead9", stroke="#4a4a4a", w=1, a=1)},
        {"title": "ЗОУИТ", "features": feats("zouit", fill="#7a4ab0", stroke="#7a4ab0", w=1.5, hatch=True, hp="x45", hs=8)},
        {"title": "Здания", "features": feats("egko.buildings", fill="#8c817c", stroke="#3c3c3c", w=0.6, a=.8)},
        {"title": "Эскиз", "features": feats("sketch.blocks", fill="#ddebd3", stroke="#2e7d32", w=2, a=.5, dash=[6, 4], hatch=True, hp="45", hc="#2e7d32")},
        {"title": "Улицы", "features": feats("osm.roads", stroke="#a0a0a0", w=3, a=1)},
        {"title": "Соцобъекты", "features": feats("social", fill="#1baf7a", stroke="#ffffff", w=4)},
    ]
    yield "m2000", {"block": {**base, "scale": 2000}, "layers": layers}
    yield "m5000", {"block": {**base, "scale": 5000}, "layers": layers}
    yield "m1000", {"block": {**base, "scale": 1000, "w": 120, "h": 160}, "layers": layers}


def main():
    OUT.mkdir(exist_ok=True)
    meta = {}
    for name, sp in scenes():
        png, info = layout_io.map_plate(sp, S.REDLN, S.LGR_DASH, None, DPI)
        (OUT / f"{name}.png").write_bytes(png)
        b, ops = layout_io._map_ops(sp, S.REDLN, S.LGR_DASH, None)
        svg = render_svg(b["w"], b["h"], [o for o in ops if o.get("op") != "text"])
        svg = re.sub(r'width="[\d.]+mm" height="[\d.]+mm"', f'width="{b["w"]}mm" height="{b["h"]}mm"', svg)
        (OUT / f"{name}.svg").write_text(svg, "utf-8")
        meta[name] = {"w": b["w"], "h": b["h"], "dpi": DPI, **info}
        print(name, meta[name])
    (OUT / "meta.json").write_text(json.dumps(meta), "utf-8")


if __name__ == "__main__":
    main()
