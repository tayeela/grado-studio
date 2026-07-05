#!/usr/bin/env python3
"""Каталог условных знаков ЛГР (приказ Москомархитектуры №65) — один лист.

Рисует ВСЕ знаки из moscow_lgr.json теми же примитивами, что и холст
студии (scene.hatch_ops / scene.marker_ops), поэтому лист 1-в-1 совпадает
с тем, как знак выглядит на карте. Нужен для глазной сверки с эталоном:
каждый тайл = образец зоны (контур + штрих засечек + штриховка + подпись
линии) и подпись «код — наименование».

    python3 tools/gen_lgr_sheet.py            # → build/lgr_sheet.pdf + .svg

Печатать листы альбома — отдельная задача; это только справочный каталог.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "render"))

from grado_render.scene import hatch_ops, marker_ops, _inward_sign  # noqa: E402
from grado_render.style import hex_to_rgb                            # noqa: E402
from grado_render.backend_svg import render_svg                      # noqa: E402
from grado_render.backend_pdf import PdfBackend                      # noqa: E402

LIB = ROOT / "core" / "render" / "grado_render" / "styles" / "moscow_lgr.json"

# --- геометрия листа (мм, y вниз — как в scene) --------------------------
COLS = 3
TILE_W = 95.0
TILE_H = 30.0
ZONE_W = 74.0
ZONE_H = 15.0
MARGIN = 12.0
GROUP_GAP = 10.0
INK = (0.12, 0.12, 0.12)
GROUP_ORDER = ["Красные линии", "ЗОУИТ", "Иные территории", "ОКН"]


def zone_rect(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def tile_ops(sign, x, y):
    """Ops одного тайла: заголовок + образец зоны знака в (x,y) — левый верх."""
    ops = []
    code = sign.get("lgr_code")
    title = sign.get("title", "")
    stroke = hex_to_rgb(sign.get("stroke")) or INK
    width = sign.get("width_mm", 0.5)
    dash = sign.get("dash_mm")

    # заголовок «код — наименование»
    head = f"{code} — {title}" if code is not None else title
    ops.append({"op": "text", "x": x, "y": y + 3.2, "size": 2.9,
                "text": head[:56], "color": INK, "anchor": "start"})

    zx, zy = x, y + 8.8
    ring = zone_rect(zx, zy, ZONE_W, ZONE_H)

    # подпись линии (как рисуется на карте) — над зоной, не налезая на контур
    lbl = sign.get("line_label")
    if lbl:
        ops.append({"op": "text", "x": zx + ZONE_W / 2, "y": y + 6.6,
                    "size": 2.0, "text": f"«{lbl}»", "color": stroke,
                    "anchor": "middle"})
    # штриховка зоны
    h = sign.get("hatch")
    if h:
        hc = hex_to_rgb(h.get("color")) or stroke
        ops.extend(hatch_ops([ring], spacing=h.get("spacing_mm", 2.4),
                             stroke=hc, width=0.16,
                             angle=h.get("angle", 45),
                             cross=h.get("cross", False)))
    # контур зоны (штрих линии знака)
    ops.append({"op": "path", "rings": [ring], "closed": True,
                "fill": None, "stroke": stroke, "width": width, "dash": dash})
    # засечки-маркеры внутрь зоны
    lm = sign.get("line_marker")
    if lm:
        ops.extend(marker_ops(ring, lm, stroke, width=width,
                              closed=True, inward=_inward_sign(ring)))
    return ops


def build_sheet():
    data = json.loads(LIB.read_text(encoding="utf-8"))
    styles = data["styles"]
    groups = {}
    for v in styles.values():
        groups.setdefault(v.get("group", "?"), []).append(v)
    order = [g for g in GROUP_ORDER if g in groups] + \
            [g for g in groups if g not in GROUP_ORDER]

    ops = []
    y = MARGIN
    max_x = MARGIN + COLS * TILE_W
    for grp in order:
        items = sorted(groups[grp], key=lambda v: (v.get("lgr_code") or 999))
        ops.append({"op": "text", "x": MARGIN, "y": y + 5.0, "size": 5.0,
                    "text": f"{grp}  ({len(items)})", "color": INK,
                    "anchor": "start"})
        y += GROUP_GAP
        for i, sign in enumerate(items):
            col = i % COLS
            if col == 0 and i > 0:
                y += TILE_H
            x = MARGIN + col * TILE_W
            ops.extend(tile_ops(sign, x, y))
        y += TILE_H + GROUP_GAP

    total = sum(len(v) for v in groups.values())
    W = max_x + MARGIN
    H = y + MARGIN
    ops.insert(0, {"op": "text", "x": MARGIN, "y": MARGIN - 4,
                   "size": 4.0, "color": INK, "anchor": "start",
                   "text": f"Условные знаки ЛГР (приказ №65) — каталог, "
                           f"{total} знаков"})
    return W, H, ops


def main():
    out = ROOT / "build"
    out.mkdir(exist_ok=True)
    w, h, ops = build_sheet()
    svg = render_svg(w, h, ops)
    (out / "lgr_sheet.svg").write_text(svg, encoding="utf-8")
    pdf = PdfBackend().render([(w, h, ops)])
    (out / "lgr_sheet.pdf").write_bytes(pdf)
    print(f"lgr_sheet: {w:.0f}×{h:.0f} мм → {out}/lgr_sheet.pdf (+ .svg)")


if __name__ == "__main__":
    main()
