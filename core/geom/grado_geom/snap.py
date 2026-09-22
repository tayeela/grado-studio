"""Движок привязок: конец / пересечение / середина / ближайшая точка.

Приоритет как в CAD: точная характеристическая точка бьёт «ближайшую».
Кандидаты в допуске сортируются по (приоритет, дистанция).
"""

import math

PRIORITY = {"endpoint": 0, "intersection": 1, "midpoint": 2, "nearest": 3}


class SnapResult:
    def __init__(self, point, kind, dist):
        self.point, self.kind, self.dist = point, kind, dist

    def __repr__(self):
        return f"SnapResult({self.kind}, {self.point})"


def _seg_intersect(a0, a1, b0, b1):
    d0 = (a1[0] - a0[0], a1[1] - a0[1])
    d1 = (b1[0] - b0[0], b1[1] - b0[1])
    det = d0[0] * d1[1] - d0[1] * d1[0]
    if abs(det) < 1e-12:
        return None
    t = ((b0[0] - a0[0]) * d1[1] - (b0[1] - a0[1]) * d1[0]) / det
    u = ((b0[0] - a0[0]) * d0[1] - (b0[1] - a0[1]) * d0[0]) / det
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return (a0[0] + d0[0] * t, a0[1] + d0[1] * t)
    return None


def _nearest_on_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return a
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    return (a[0] + dx * t, a[1] + dy * t)


class Snapper:
    def __init__(self, tolerance=0.5, cell=None):
        self.tolerance = tolerance
        self.cell = cell if cell and cell > 0 else max(float(tolerance) * 10.0, 1.0)
        self.segments = []
        self._grid = {}
        self._intersections = None

    def add_segment(self, a, b):
        a, b = (tuple(a), tuple(b))
        idx = len(self.segments)
        self.segments.append((a, b))
        for key in self._segment_cells(a, b):
            self._grid.setdefault(key, []).append(idx)
        self._intersections = None

    def add_polyline(self, pts):
        for a, b in zip(pts, pts[1:]):
            self.add_segment(a, b)

    def _segment_cells(self, a, b):
        c = self.cell
        minx, maxx = (a[0], b[0]) if a[0] <= b[0] else (b[0], a[0])
        miny, maxy = (a[1], b[1]) if a[1] <= b[1] else (b[1], a[1])
        ix0, ix1 = math.floor(minx / c), math.floor(maxx / c)
        iy0, iy1 = math.floor(miny / c), math.floor(maxy / c)
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                yield (ix, iy)

    def _near(self, x, y):
        c = self.cell
        pad = self.tolerance
        ix0, ix1 = math.floor((x - pad) / c), math.floor((x + pad) / c)
        iy0, iy1 = math.floor((y - pad) / c), math.floor((y + pad) / c)
        seen = set()
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                for idx in self._grid.get((ix, iy), ()):
                    if idx not in seen:
                        seen.add(idx)
                        yield idx

    def _all_intersections(self):
        if self._intersections is None:
            self._intersections = []
            pairs = set()
            for bucket in self._grid.values():
                for i in range(len(bucket)):
                    for j in range(i + 1, len(bucket)):
                        a, b = bucket[i], bucket[j]
                        if a > b:
                            a, b = b, a
                        if a == b or (a, b) in pairs:
                            continue
                        pairs.add((a, b))
                        hit = _seg_intersect(*self.segments[a], *self.segments[b])
                        if hit:
                            self._intersections.append(hit)
        return self._intersections

    def snap(self, x, y):
        p = (x, y)
        candidates = []
        for idx in self._near(x, y):
            a, b = self.segments[idx]
            for pt in (a, b):
                candidates.append((pt, "endpoint"))
            candidates.append((((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), "midpoint"))
            candidates.append((_nearest_on_seg(p, a, b), "nearest"))
        for pt in self._all_intersections():
            candidates.append((pt, "intersection"))

        best = None
        for pt, kind in candidates:
            dist = math.dist(p, pt)
            if dist > self.tolerance:
                continue
            key = (PRIORITY[kind], dist)
            if best is None or key < (PRIORITY[best.kind], best.dist):
                best = SnapResult(pt, kind, dist)
        return best
