"""Площадь объединения полигонов внутри объединения других полигонов.

Нужна ТЭП: сколько площади ограничений лежит внутри границы территории.
Ограничения перекрываются (зоны охраны ОКН вложены друг в друга), бывают
дублями и выходят за границу — простая сумма площадей даёт неверный ответ.

Метод — сканирующие строки: на каждой горизонтали берём отрезки внутри
полигонов (правило чётности, дыры учитываются), объединяем их по каждой
группе и пересекаем группы. Совпадающие и смежные границы на результат не
влияют. Внутри полосы ширина меняется линейно, поэтому погрешность есть
только у вершин и порядка шага², то есть сотые доли м² на вершину.
"""

import math


def _edges(polygon):
    out = []
    for ring in polygon:
        n = len(ring)
        if n < 3:
            continue
        for i in range(n):
            x0, y0 = ring[i][0], ring[i][1]
            x1, y1 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
            if y0 != y1:
                out.append((x0, y0, x1, y1))
    return out


def _bbox(polygons):
    xs = [p[0] for poly in polygons for ring in poly for p in ring]
    ys = [p[1] for poly in polygons for ring in poly for p in ring]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _merge(intervals):
    intervals.sort()
    out = []
    for a, b in intervals:
        if out and a <= out[-1][1]:
            if b > out[-1][1]:
                out[-1][1] = b
        else:
            out.append([a, b])
    return out


def _intersect_len(a, b):
    i = j = 0
    total = 0.0
    while i < len(a) and j < len(b):
        lo = max(a[i][0], b[j][0])
        hi = min(a[i][1], b[j][1])
        if hi > lo:
            total += hi - lo
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return total


def union_intersection_area(regions, clips, max_rows=4000, min_step=0.05):
    """Площадь (∪ regions) ∩ (∪ clips) в единицах координат².

    regions, clips — списки полигонов; полигон — список колец [(x, y), …]
    (первое внешнее, остальные дыры; порядок обхода не важен).
    """
    regions = [p for p in regions if p]
    clips = [p for p in clips if p]
    if not regions or not clips:
        return 0.0
    cb, rb = _bbox(clips), _bbox(regions)
    if cb is None or rb is None:
        return 0.0
    x0, y0 = max(cb[0], rb[0]), max(cb[1], rb[1])
    x1, y1 = min(cb[2], rb[2]), min(cb[3], rb[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    step = max(min_step, (y1 - y0) / max_rows)
    rows = max(1, math.ceil((y1 - y0) / step))
    step = (y1 - y0) / rows

    def bucket(polygons):
        # рёбра по строкам: ребро попадает в каждую строку, чью середину пересекает
        per_row = [[] for _ in range(rows)]
        for index, poly in enumerate(polygons):
            for e in _edges(poly):
                lo, hi = min(e[1], e[3]), max(e[1], e[3])
                if hi <= y0 or lo >= y1:
                    continue
                first = max(0, math.ceil((lo - y0) / step - 0.5))
                last = min(rows - 1, math.ceil((hi - y0) / step - 0.5) - 1)
                for r in range(first, last + 1):
                    per_row[r].append((index, e))
        return per_row

    def spans(row_edges, y):
        by_poly = {}
        for index, (xa, ya, xb, yb) in row_edges:
            if (ya <= y < yb) or (yb <= y < ya):
                by_poly.setdefault(index, []).append(xa + (y - ya) * (xb - xa) / (yb - ya))
        out = []
        for xs in by_poly.values():
            xs.sort()
            out.extend([xs[k], xs[k + 1]] for k in range(0, len(xs) - 1, 2))
        return _merge(out)

    reg_rows, clip_rows = bucket(regions), bucket(clips)
    total = 0.0
    for r in range(rows):
        if not reg_rows[r] or not clip_rows[r]:
            continue
        y = y0 + (r + 0.5) * step
        total += _intersect_len(spans(reg_rows[r], y), spans(clip_rows[r], y)) * step
    return total
