"""ГРАДО 2 · слои знака в печати (план 08.11.2026, шаг 2: «знак из слоёв, как в QGIS»): поверх основного знака объекта
— стопка частей `parts` стиля слоя или класса (symbology.js cleanParts): линия по контуру, полоса внутрь вдоль границы,
штриховка, значки вдоль линии (штрих, треугольник, кружок, крестик) со стороной — внутрь/наружу у полигона,
справа/слева по ходу у линии. Размеры в пикселях экрана → мм листа (PX_MM), как остальной знак, поэтому лист повторяет карту.
Координаты — мм листа, ось y вниз (как SVG печати и экран). Зовёт print_io.SketchMapFrame; проверяет tests/test_symparts.py.
С модулем grado_rs части знака строит Rust (rust/crates/symbol, план 08.11 шаг 3) — тот же код рисует их на экране
(WebAssembly); здесь — запасной путь без модуля и эталон сверки. GRADO_SYMBOL=py — всегда Python."""
import json
import math
import os

from grado_render import hex_to_rgb
from grado_render.scene import hatch_ops

PX_MM = 0.26                                   # = print_io.PX_MM
ANGLES = {"0": (0,), "90": (90,), "135": (135,), "x45": (45, 135), "x0": (0, 90)}


def _rgb(c, a=1.0):
    v = hex_to_rgb(c or "#333333")
    a = max(0.0, min(1.0, 1.0 if a is None else float(a)))
    return tuple(1 - a * (1 - x) for x in v)          # прозрачность — смешением с белым листом, как print_io._mix


def _area(r):
    return sum(r[i - 1][0] * r[i][1] - r[i][0] * r[i - 1][1] for i in range(len(r))) / 2


def _right_inside(rings):
    """Кольца полигона так, чтобы внутренность была справа по ходу (y вниз: наружное по часовой на листе, дыры — наоборот)."""
    out = []
    for i, r in enumerate(rings):
        want = 1 if i == 0 else -1
        out.append(list(r) if (_area(r) > 0) == (want > 0) else list(reversed(r)))
    return out


def _stations(pts, step, closed):
    """Точки через step мм вдоль ломаной (первая — на step/2): [(x, y, dx, dy)] с единичным направлением хода."""
    seq = list(pts) + ([pts[0]] if closed and pts[0] != pts[-1] else [])
    out, need = [], step / 2
    for (x0, y0), (x1, y1) in zip(seq, seq[1:]):
        d = math.hypot(x1 - x0, y1 - y0)
        if d <= 1e-9:
            continue
        ux, uy, t = (x1 - x0) / d, (y1 - y0) / d, 0.0
        while t + need <= d:
            t += need
            out.append((x0 + ux * t, y0 + uy * t, ux, uy))
            need = step
        need -= d - t
    return out


def _mark(shape, x, y, ux, uy, side, size, color, width):
    """Значок в точке: n — нормаль в сторону side (справа по ходу при side > 0; y вниз: справа = (−uy, ux))."""
    nx, ny = -uy * side, ux * side
    s = size
    if shape == "dot":
        cx, cy = x + nx * s / 2, y + ny * s / 2
        ring = [(cx + s / 2 * math.cos(a * math.pi / 6), cy + s / 2 * math.sin(a * math.pi / 6)) for a in range(12)]
        return {"op": "path", "rings": [ring], "closed": True, "fill": color, "stroke": None, "width": 0, "dash": None}
    if shape == "tri":
        ring = [(x - ux * s / 2, y - uy * s / 2), (x + ux * s / 2, y + uy * s / 2), (x + nx * s, y + ny * s)]
        return {"op": "path", "rings": [ring], "closed": True, "fill": color, "stroke": None, "width": 0, "dash": None}
    if shape == "cross":
        h = s / 2
        return {"op": "path", "rings": [[(x - h, y - h), (x + h, y + h)], [(x - h, y + h), (x + h, y - h)]], "closed": False,
                "fill": None, "stroke": color, "width": width, "dash": None}
    return {"op": "path", "rings": [[(x, y), (x + nx * s, y + ny * s)]], "closed": False,   # tick — штрих поперёк в сторону side
            "fill": None, "stroke": color, "width": width, "dash": None}


def _band(rings, b):
    """Полоса шириной b мм внутрь вдоль границы полигона (shapely): кольца полосы или []."""
    from shapely.geometry import Polygon
    try:
        p = Polygon(rings[0], rings[1:]).buffer(0)
        band = p.difference(p.buffer(-b))
    except Exception:                          # noqa: BLE001 — кривой контур: полоса не рисуется, остальной знак есть
        return []
    out = []
    for g in getattr(band, "geoms", [band]):
        if g.is_empty or g.geom_type != "Polygon":
            continue
        out.append([list(g.exterior.coords)[:-1]] + [list(i.coords)[:-1] for i in g.interiors])
    return out


def _rust():
    """parts_ops модуля grado_rs (0.2+) или None."""
    if os.environ.get("GRADO_SYMBOL", "").strip().lower() == "py":
        return None
    try:
        import grado_rs
    except ImportError:
        return None
    return getattr(grado_rs, "parts_ops", None)


def parts_ops(kind, shapes, parts):
    """Операции печати частей знака. kind — "poly" (shapes — кольца каждого полигона) или "line" (shapes — ломаные)."""
    rs = _rust() if parts else None
    if rs:
        try:
            ops = json.loads(rs(kind, json.dumps(shapes), json.dumps(parts), PX_MM))
            for o in ops:                       # цвета — кортежи; прозрачность части — смешением с белым листом, как прежде
                a = o.pop("alpha", None)
                for k in ("fill", "stroke"):
                    if isinstance(o.get(k), list):
                        o[k] = tuple(o[k]) if a is None else tuple(1 - a * (1 - x) for x in o[k])
            return ops
        except (ValueError, TypeError):         # кривые данные — тем же путём, что без модуля
            pass
    return parts_ops_py(kind, shapes, parts)


def parts_ops_py(kind, shapes, parts):
    """Эталон на Python (без модуля grado_rs)."""
    out = []
    for p in parts or []:
        k, c, w = p.get("k"), p.get("c"), max(0.05, float(p.get("w") or 1) * PX_MM)
        col = _rgb(c, p.get("a", 1))
        dash = [max(0.1, float(d) * PX_MM) for d in p["dash"]] if p.get("dash") else None
        if k == "line":
            for s in shapes:
                out.append({"op": "path", "rings": s if kind == "poly" else [s], "closed": kind == "poly", "fill": None,
                            "stroke": col, "width": w, "dash": dash})
        elif k == "band" and kind == "poly":
            b = max(0.1, float(p.get("b") or 6) * PX_MM)
            for rings in shapes:
                for br in _band(rings, b):
                    out.append({"op": "path", "rings": br, "closed": True, "fill": col, "stroke": None, "width": 0, "dash": None})
        elif k == "hatch" and kind == "poly":
            step = max(0.8, float(p.get("hs") or 8) * PX_MM)
            for rings in shapes:
                for ang in ANGLES.get(p.get("hp"), (45,)):
                    out.extend(hatch_ops(rings, spacing=step, stroke=col, angle=ang, width=max(0.08, w / 2)))
        elif k == "marks":
            step = max(0.5, float(p.get("step") or 16) * PX_MM)
            size = max(0.3, float(p.get("size") or 5) * PX_MM)
            side = -1 if (p.get("side") or 1) < 0 else 1
            lines = [r for rings in shapes for r in _right_inside(rings)] if kind == "poly" else shapes
            for ln in lines:
                if len(ln) < 2:
                    continue
                for x, y, ux, uy in _stations(ln, step, kind == "poly"):
                    out.append(_mark(p.get("shape") or "tick", x, y, ux, uy, side, size, col, w))
    return out
