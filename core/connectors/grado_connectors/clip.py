"""Обрезка геометрии GeoJSON по прямоугольнику (w, s, e, n) — только стандартная библиотека.

Полигоны режутся по кольцам (Сазерленд — Ходжмен: внешнее кольцо и дыры по отдельности; вогнутый контур даёт
вдоль края рамки нулевые перемычки — для показа и площади это безвредно), линии — отрезками (Лян — Барски) с разбиением
на части, точки — фильтром. Возвращает новую геометрию или None, если от объекта в рамке ничего не осталось.
"""


def _inside(p, box):
    return box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]


def _clip_ring(ring, box):
    """Кольцо (замкнутое или нет) → замкнутое кольцо в рамке или None."""
    pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    w, s, e, n = box
    edges = (
        (lambda p: p[0] >= w, lambda a, b: (w, a[1] + (b[1] - a[1]) * (w - a[0]) / (b[0] - a[0]))),
        (lambda p: p[0] <= e, lambda a, b: (e, a[1] + (b[1] - a[1]) * (e - a[0]) / (b[0] - a[0]))),
        (lambda p: p[1] >= s, lambda a, b: (a[0] + (b[0] - a[0]) * (s - a[1]) / (b[1] - a[1]), s)),
        (lambda p: p[1] <= n, lambda a, b: (a[0] + (b[0] - a[0]) * (n - a[1]) / (b[1] - a[1]), n)),
    )
    for ins, cut in edges:
        if not pts:
            return None
        out, prev = [], pts[-1]
        for cur in pts:
            if ins(cur):
                if not ins(prev):
                    out.append(cut(prev, cur))
                out.append(cur)
            elif ins(prev):
                out.append(cut(prev, cur))
            prev = cur
        pts = out
    uniq = []
    for p in pts:
        p = [p[0], p[1]]
        if not uniq or uniq[-1] != p:
            uniq.append(p)
    if len(uniq) > 1 and uniq[0] == uniq[-1]:
        uniq.pop()
    if len(uniq) < 3:
        return None
    area = sum(uniq[i][0] * uniq[i - 1][1] - uniq[i - 1][0] * uniq[i][1] for i in range(len(uniq)))
    if abs(area) < 1e-18:                      # вырожденное кольцо вдоль края рамки
        return None
    return uniq + [uniq[0]]


def _ring_in_box(ring, box):
    """Кольцо целиком в рамке → оно само, целиком вне → None, иначе — обрезанное. Проверка по габариту сначала:
    у полигона дорог ЕГКО на весь город тысячи дыр-кварталов, и резать каждую незачем."""
    b = _bbox_of(ring, [float("inf"), float("inf"), float("-inf"), float("-inf")])
    if b[2] < box[0] or b[0] > box[2] or b[3] < box[1] or b[1] > box[3]:
        return None
    if b[0] >= box[0] and b[2] <= box[2] and b[1] >= box[1] and b[3] <= box[3]:
        return ring
    return _clip_ring(ring, box)


def _clip_polygon(rings, box):
    if not rings:
        return None
    outer = _ring_in_box(rings[0], box)
    if not outer:
        return None
    return [outer] + [h for h in (_ring_in_box(r, box) for r in rings[1:]) if h]


def _clip_segment(a, b, box):
    """Лян — Барски: отрезок a→b внутри рамки или None."""
    x0, y0, x1, y1 = a[0], a[1], b[0], b[1]
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - box[0]), (dx, box[2] - x0), (-dy, y0 - box[1]), (dy, box[3] - y0)):
        if p == 0:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return None
            t0 = max(t0, r)
        else:
            if r < t0:
                return None
            t1 = min(t1, r)
    return [x0 + t0 * dx, y0 + t0 * dy], [x0 + t1 * dx, y0 + t1 * dy]


def _clip_line(line, box):
    """Линия → список частей в рамке (разрывы там, где линия выходит из рамки)."""
    parts, cur = [], None
    for a, b in zip(line, line[1:]):
        seg = _clip_segment(a, b, box)
        if not seg:
            cur = None
            continue
        p, q = seg
        if cur and cur[-1] == p:
            cur.append(q)
        else:
            cur = [p, q]
            parts.append(cur)
        if q != [b[0], b[1]]:                 # отрезок вышел из рамки — следующая часть начнётся заново
            cur = None
    return [pt for pt in parts if len(pt) > 1 and pt[0] != pt[-1] or len(pt) > 2]


def _bbox_of(coords, acc):
    if coords and isinstance(coords[0], (int, float)):
        acc[0] = min(acc[0], coords[0]); acc[1] = min(acc[1], coords[1])
        acc[2] = max(acc[2], coords[0]); acc[3] = max(acc[3], coords[1])
    else:
        for c in coords or ():
            _bbox_of(c, acc)
    return acc


def clip_geometry(geom, box):
    """GeoJSON-геометрия → обрезанная по рамке box = (w, s, e, n) либо None. Целиком внутри — возвращается как есть."""
    if not geom or not geom.get("coordinates"):
        return None
    t, c = geom.get("type"), geom["coordinates"]
    b = _bbox_of(c, [float("inf"), float("inf"), float("-inf"), float("-inf")])
    if b[0] >= box[0] and b[2] <= box[2] and b[1] >= box[1] and b[3] <= box[3]:
        return geom
    if b[2] < box[0] or b[0] > box[2] or b[3] < box[1] or b[1] > box[3]:
        return None
    if t == "Point":
        return geom if _inside(c, box) else None
    if t == "MultiPoint":
        pts = [p for p in c if _inside(p, box)]
        return {"type": "MultiPoint", "coordinates": pts} if pts else None
    if t in ("LineString", "MultiLineString"):
        parts = [p for line in ([c] if t == "LineString" else c) for p in _clip_line(line, box)]
        if not parts:
            return None
        return {"type": "LineString", "coordinates": parts[0]} if len(parts) == 1 else {"type": "MultiLineString", "coordinates": parts}
    if t in ("Polygon", "MultiPolygon"):
        polys = [p for p in (_clip_polygon(rings, box) for rings in ([c] if t == "Polygon" else c)) if p]
        if not polys:
            return None
        return {"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1 else {"type": "MultiPolygon", "coordinates": polys}
    return geom                                 # GeometryCollection и прочее — как есть (в ЕГКО не встречается)
