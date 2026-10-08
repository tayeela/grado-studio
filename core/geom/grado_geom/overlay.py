"""Площадь объединения полигонов внутри объединения других полигонов.

Нужна ТЭП и доле районов: сколько площади ограничений лежит внутри границы
территории. Ограничения перекрываются (зоны охраны ОКН вложены друг в друга),
бывают дублями и выходят за границу — простая сумма площадей даёт неверный
ответ.

Считает shapely 2 (GEOS): объединение каждой группы, пересечение групп,
площадь — точно, без шага сетки. Кольца с самопересечением чинятся
`make_valid`; порядок обхода и совпадающие границы на результат не влияют.
Вызывают: apps/grado2/server.py (district_shares), закрытая студия; тесты —
core/geom/tests/test_overlay.py.
"""

import shapely
from shapely.geometry import Polygon


def _union(polygons):
    parts = []
    for poly in polygons:
        rings = [[(p[0], p[1]) for p in ring] for ring in poly if len(ring) >= 3]
        if not rings:
            continue
        # дыра — разность с внешним кольцом (правило чётности, как у прежнего метода сканирующих строк)
        shell = shapely.make_valid(Polygon(rings[0]))
        for hole in rings[1:]:
            shell = shell.difference(shapely.make_valid(Polygon(hole)))
        parts.append(shell)
    return shapely.union_all(parts) if parts else None


def union_intersection_area(regions, clips, max_rows=None, min_step=None):
    """Площадь (∪ regions) ∩ (∪ clips) в единицах координат².

    regions, clips — списки полигонов; полигон — список колец [(x, y), …]
    (первое внешнее, остальные дыры; порядок обхода не важен).
    max_rows, min_step — параметры прежнего приближённого метода, не используются.
    """
    a = _union([p for p in regions if p])
    b = _union([p for p in clips if p])
    if a is None or b is None or a.is_empty or b.is_empty:
        return 0.0
    if not shapely.intersects(a, b):
        return 0.0
    return float(shapely.intersection(a, b).area)
