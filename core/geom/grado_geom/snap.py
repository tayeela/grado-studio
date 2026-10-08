"""Движок привязок: конец / пересечение / середина / ближайшая точка.

Приоритет как в CAD: точная характеристическая точка бьёт «ближайшую».
Кандидаты в допуске сортируются по (приоритет, дистанция). Поиск отрезков рядом
с курсором — пространственный индекс shapely 2 (STRtree, GEOS); пересечения и
ближайшая точка — тоже shapely. Пересечение в допуске лежит на двух отрезках,
каждый из которых сам в допуске, поэтому пары перебираются только среди найденных рядом.
Вызывают: закрытая студия; тесты — core/geom/tests/test_snap_coverage.py.
"""

import math

import shapely
from shapely.geometry import LineString, Point

PRIORITY = {"endpoint": 0, "intersection": 1, "midpoint": 2, "nearest": 3}


class SnapResult:
    def __init__(self, point, kind, dist):
        self.point, self.kind, self.dist = point, kind, dist

    def __repr__(self):
        return f"SnapResult({self.kind}, {self.point})"


class Snapper:
    def __init__(self, tolerance=0.5, cell=None):
        # cell — шаг прежней сетки-индекса; оставлен для совместимости вызовов, индекс теперь STRtree
        self.tolerance = tolerance
        self.cell = cell
        self.segments = []
        self._lines = []
        self._tree = None

    def add_segment(self, a, b):
        a, b = (tuple(a), tuple(b))
        self.segments.append((a, b))
        self._lines.append(LineString([a, b]) if a != b else Point(a))
        self._tree = None

    def add_polyline(self, pts):
        for a, b in zip(pts, pts[1:]):
            self.add_segment(a, b)

    def _near(self, p):
        if not self._lines:
            return []
        if self._tree is None:
            self._tree = shapely.STRtree(self._lines)
        return sorted(int(i) for i in self._tree.query(p, predicate="dwithin", distance=self.tolerance))

    def snap(self, x, y):
        p = Point(x, y)
        near = self._near(p)
        candidates = []
        for idx in near:
            a, b = self.segments[idx]
            line = self._lines[idx]
            for pt in (a, b):
                candidates.append((pt, "endpoint"))
            candidates.append((((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), "midpoint"))
            q = line.interpolate(line.project(p)) if a != b else line
            candidates.append(((q.x, q.y), "nearest"))
        for i, ia in enumerate(near):
            for ib in near[i + 1:]:
                hit = shapely.intersection(self._lines[ia], self._lines[ib])
                if hit.geom_type == "Point":   # совпадающие (коллинеарные) отрезки точки пересечения не дают
                    candidates.append(((hit.x, hit.y), "intersection"))

        best = None
        for pt, kind in candidates:
            dist = math.dist((x, y), pt)
            if dist > self.tolerance:
                continue
            key = (PRIORITY[kind], dist)
            if best is None or key < (PRIORITY[best.kind], best.dist):
                best = SnapResult(pt, kind, dist)
        return best
