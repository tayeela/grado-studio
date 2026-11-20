"""Площадь объединения полигонов внутри объединения других полигонов.

Нужна ТЭП и доле районов: сколько площади ограничений лежит внутри границы
территории. Ограничения перекрываются (зоны охраны ОКН вложены друг в друга),
бывают дублями и выходят за границу — простая сумма площадей даёт неверный
ответ.

Начиная с шага С2 плана 09.11.2026: если установлен модуль `grado_rs` (и не
задано `GRADO_GEOM=python`), считает планарный движок на Rust
(`rust/crates/geom/src/overlay.rs` — нодинг рёбер и теорема Грина без
квантования). Без модуля или при `GRADO_GEOM=python` считает Python-эталон
на shapely 2 (GEOS): объединение каждой группы, пересечение групп, площадь —
точно, без шага сетки; кольца с самопересечением чинятся `make_valid`.
Вызывают: apps/grado2/server.py (district_shares), закрытая студия; тесты —
core/geom/tests/test_overlay.py.
"""

import math
import os

import shapely
from shapely.geometry import Polygon


def _clean_polys(polygons):
    """Отбирает годные кольца (>= 3 конечных точек) и приводит точки к парам (float, float)."""
    out = []
    for poly in polygons or ():
        if not poly:
            continue
        rings = [[(float(p[0]), float(p[1])) for p in ring] for ring in poly
                 if len(ring) >= 3 and all(math.isfinite(p[0]) and math.isfinite(p[1]) for p in ring)]
        if rings:
            out.append(rings)
    return out


def _union(polygons):
    parts = []
    for rings in _clean_polys(polygons):
        # дыра — разность с внешним кольцом (правило чётности, как у прежнего метода сканирующих строк)
        shell = shapely.make_valid(Polygon(rings[0]))
        for hole in rings[1:]:
            shell = shell.difference(shapely.make_valid(Polygon(hole)))
        parts.append(shell)
    return shapely.union_all(parts) if parts else None


def union_intersection_area_py(regions, clips, max_rows=None, min_step=None):
    """Эталон на Python (shapely 2 / GEOS): площадь (∪ regions) ∩ (∪ clips) в единицах координат²."""
    a = _union(regions)
    b = _union(clips)
    if a is None or b is None or a.is_empty or b.is_empty:
        return 0.0
    if not shapely.intersects(a, b):
        return 0.0
    return float(shapely.intersection(a, b).area)


def _rs_overlay():
    if os.environ.get("GRADO_GEOM", "").strip().lower() == "python":
        return None
    try:
        import grado_rs
        return getattr(grado_rs, "union_intersection_area", None)
    except ImportError:
        return None


def union_intersection_area(regions, clips, max_rows=None, min_step=None):
    """Площадь (∪ regions) ∩ (∪ clips) в единицах координат².

    regions, clips — списки полигонов; полигон — список колец [(x, y), …]
    (первое внешнее, остальные дыры; порядок обхода не важен).
    max_rows, min_step — параметры прежнего приближённого метода, не используются.
    """
    fn = _rs_overlay()
    if fn is not None:
        r = _clean_polys(regions)
        c = _clean_polys(clips)
        if not r or not c:
            return 0.0
        return float(fn(r, c))
    return union_intersection_area_py(regions, clips, max_rows=max_rows, min_step=min_step)
