"""Составной путь: отрезки и дуги. Пикетаж, офсеты, сопряжения.

Это геометрия красных линий: полилиния с тангенциальными дугами в углах
(fillet), точка на заданном пикете, офсет всей линии. G1-непрерывная цепь
(стыки по касательной) офсетится поэлементно и остаётся непрерывной —
свойство, на котором держится офсет красных линий с кривыми.
"""

import math

from .curves import Arc, CurveError


class PathError(ValueError):
    pass


def _line_intersect(p0, d0, p1, d1):
    """Пересечение прямых точка+направление; None для параллельных."""
    det = d0[0] * d1[1] - d0[1] * d1[0]
    if abs(det) < 1e-12:
        return None
    t = ((p1[0] - p0[0]) * d1[1] - (p1[1] - p0[1]) * d1[0]) / det
    return (p0[0] + d0[0] * t, p0[1] + d0[1] * t)


class Path:
    def __init__(self, elements, closed=False):
        self.elements = list(elements)
        self.closed = closed
        if not self.elements:
            raise PathError("пустой путь")

    # --- конструкторы ----------------------------------------------------

    @classmethod
    def polyline(cls, pts, closed=False):
        if len(pts) < 2:
            raise PathError("нужно >= 2 точек")
        elems = [("seg", tuple(a), tuple(b)) for a, b in zip(pts, pts[1:])]
        if closed and tuple(pts[0]) != tuple(pts[-1]):
            elems.append(("seg", tuple(pts[-1]), tuple(pts[0])))
        return cls(elems, closed=closed)

    @classmethod
    def fillet_polyline(cls, pts, radius):
        """Полилиния с тангенциальными дугами в углах (сопряжение).

        Классика красных линий: прямые участки + скругления радиусом R."""
        if len(pts) < 3:
            return cls.polyline(pts)
        elems = []
        cur = tuple(pts[0])
        for prev, v, nxt in zip(pts, pts[1:], pts[2:]):
            v1 = (v[0] - prev[0], v[1] - prev[1])
            v2 = (nxt[0] - v[0], nxt[1] - v[1])
            l1, l2 = math.hypot(*v1), math.hypot(*v2)
            u1 = (v1[0] / l1, v1[1] / l1)
            u2 = (v2[0] / l2, v2[1] / l2)
            cross = u1[0] * u2[1] - u1[1] * u2[0]
            dot = u1[0] * u2[0] + u1[1] * u2[1]
            theta = math.pi - math.atan2(abs(cross), dot)  # внутренний угол
            if abs(cross) < 1e-9:
                continue  # прямой участок без излома
            t = radius / math.tan(theta / 2)
            if t > l1 - 1e-9 or t > l2 - 1e-9:
                raise PathError(f"радиус {radius} не помещается в вершине {v}")
            tp1 = (v[0] - u1[0] * t, v[1] - u1[1] * t)   # точка схода с первой прямой
            tp2 = (v[0] + u2[0] * t, v[1] + u2[1] * t)   # точка входа на вторую
            # центр — на биссектрисе, на расстоянии r от обеих прямых
            n1 = (-u1[1], u1[0]) if cross > 0 else (u1[1], -u1[0])
            cx, cy = tp1[0] + n1[0] * radius, tp1[1] + n1[1] * radius
            a0 = math.atan2(tp1[1] - cy, tp1[0] - cx)
            a1 = math.atan2(tp2[1] - cy, tp2[0] - cx)
            sweep = (a1 - a0) % (2 * math.pi) if cross > 0 \
                else (a1 - a0) % (2 * math.pi) - 2 * math.pi
            elems.append(("seg", cur, tp1))
            elems.append(("arc", Arc(cx, cy, radius, a0, sweep)))
            cur = tp2
        elems.append(("seg", cur, tuple(pts[-1])))
        return cls(elems)

    # --- базовые свойства -------------------------------------------------

    def _elem_len(self, e):
        if e[0] == "seg":
            return math.hypot(e[2][0] - e[1][0], e[2][1] - e[1][1])
        return e[1].length()

    def length(self):
        return sum(self._elem_len(e) for e in self.elements)

    def linearize(self, tol=0.01):
        pts = []
        for e in self.elements:
            chunk = [e[1], e[2]] if e[0] == "seg" else e[1].linearize(tol)
            if pts and pts[-1] == chunk[0]:
                chunk = chunk[1:]
            pts.extend(chunk)
        return pts

    def area(self, tol=0.01):
        pts = self.linearize(tol)
        s = 0.0
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
            s += x1 * y2 - x2 * y1
        return abs(s) / 2

    # --- пикетаж ----------------------------------------------------------

    def point_at_station(self, s):
        """Точка и касательная (рад) на пикете s от начала пути."""
        s = max(0.0, s)
        for e in self.elements:
            el = self._elem_len(e)
            if s <= el or e is self.elements[-1]:
                t = min(s / el, 1.0)
                if e[0] == "seg":
                    (x0, y0), (x1, y1) = e[1], e[2]
                    return ((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t),
                            math.atan2(y1 - y0, x1 - x0))
                return e[1].point_at(t), e[1].tangent_at(t)
            s -= el
        raise PathError("пустой путь")

    def stations(self, step):
        """Точки пикетажа через step метров: [(ПК, точка)]."""
        total = self.length()
        out = []
        s = 0.0
        while s < total - 1e-9:
            out.append((s, self.point_at_station(s)[0]))
            s += step
        out.append((total, self.point_at_station(total)[0]))
        return out

    # --- офсет -------------------------------------------------------------

    def _tangents(self, e):
        if e[0] == "seg":
            a = math.atan2(e[2][1] - e[1][1], e[2][0] - e[1][0])
            return a, a
        return e[1].tangent_at(0.0), e[1].tangent_at(1.0)

    def _ends(self, e):
        if e[0] == "seg":
            return e[1], e[2]
        return e[1].start, e[1].end

    def is_g1(self, tol=1e-6):
        for a, b in zip(self.elements, self.elements[1:]):
            if math.dist(self._ends(a)[1], self._ends(b)[0]) > tol:
                return False
            da = (self._tangents(b)[0] - self._tangents(a)[1]) % (2 * math.pi)
            if min(da, 2 * math.pi - da) > tol:
                return False
        return True

    def _offset_seg(self, e, d):
        (x0, y0), (x1, y1) = e[1], e[2]
        length = math.hypot(x1 - x0, y1 - y0)
        nx, ny = -(y1 - y0) / length * d, (x1 - x0) / length * d
        return ("seg", (x0 + nx, y0 + ny), (x1 + nx, y1 + ny))

    def offset(self, d):
        """Офсет влево по ходу на d. G1-цепь — поэлементно; ломаная — со
        стыковкой соседних офсетов по пересечению (miter)."""
        if all(e[0] == "seg" for e in self.elements) and not self.is_g1():
            return self._offset_miter(d)
        if not self.is_g1():
            raise PathError("офсет цепи с дугами требует G1-непрерывности")
        out = []
        for e in self.elements:
            out.append(self._offset_seg(e, d) if e[0] == "seg"
                       else ("arc", e[1].offset(d)))
        return Path(out, closed=self.closed)

    def _offset_miter(self, d):
        segs = [self._offset_seg(e, d) for e in self.elements]
        n = len(segs)
        joints = {}
        pairs = list(range(n - 1)) + ([n - 1] if self.closed else [])
        for i in pairs:
            a, b = segs[i], segs[(i + 1) % n]
            da = (a[2][0] - a[1][0], a[2][1] - a[1][1])
            db = (b[2][0] - b[1][0], b[2][1] - b[1][1])
            p = _line_intersect(a[1], da, b[1], db)
            joints[i] = p if p else a[2]
        out = []
        for i, s in enumerate(segs):
            start = joints[(i - 1) % n] if (i > 0 or self.closed) and (i - 1) % n in joints else s[1]
            end = joints[i] if i in joints else s[2]
            out.append(("seg", start, end))
        return Path(out, closed=self.closed)
