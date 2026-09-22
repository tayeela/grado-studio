"""Дуги окружностей — параметрическое хранение, линеаризация по допуску.

Инвариант ядра: кривая хранится параметрами (центр, радиус, углы), а не
ломаной; линеаризация — только на границах (GEOS-операции, экспорт).
Клотоиды (переходные кривые УДС) — в C++ ядре; эталон ограничен дугами.
"""

import math


class CurveError(ValueError):
    pass


class Arc:
    """Дуга: центр, радиус, начальный угол a0, знаковая развёртка sweep.

    sweep > 0 — против часовой (центр слева по ходу), sweep < 0 — по часовой.
    """

    def __init__(self, cx, cy, r, a0, sweep):
        if r <= 0:
            raise CurveError("радиус должен быть > 0")
        if sweep == 0:
            raise CurveError("нулевая развёртка")
        self.cx, self.cy, self.r, self.a0, self.sweep = cx, cy, r, a0, sweep

    @classmethod
    def from_3pts(cls, p0, pm, p1):
        """Дуга по трём точкам (начало, промежуточная, конец)."""
        (x0, y0), (xm, ym), (x1, y1) = p0, pm, p1
        d = 2 * (x0 * (ym - y1) + xm * (y1 - y0) + x1 * (y0 - ym))
        if abs(d) < 1e-12:
            raise CurveError("точки коллинеарны — дуга не определена")
        s0, sm, s1 = x0 ** 2 + y0 ** 2, xm ** 2 + ym ** 2, x1 ** 2 + y1 ** 2
        cx = (s0 * (ym - y1) + sm * (y1 - y0) + s1 * (y0 - ym)) / d
        cy = (s0 * (x1 - xm) + sm * (x0 - x1) + s1 * (xm - x0)) / d
        r = math.hypot(x0 - cx, y0 - cy)
        a0 = math.atan2(y0 - cy, x0 - cx)
        a1 = math.atan2(y1 - cy, x1 - cx)
        am = math.atan2(ym - cy, xm - cx)
        ccw_sweep = (a1 - a0) % (2 * math.pi)
        ccw_mid = (am - a0) % (2 * math.pi)
        sweep = ccw_sweep if ccw_mid <= ccw_sweep else ccw_sweep - 2 * math.pi
        return cls(cx, cy, r, a0, sweep)

    @property
    def start(self):
        return self.point_at(0.0)

    @property
    def end(self):
        return self.point_at(1.0)

    def length(self):
        return self.r * abs(self.sweep)

    def point_at(self, t):
        a = self.a0 + self.sweep * t
        return (self.cx + self.r * math.cos(a), self.cy + self.r * math.sin(a))

    def point_at_length(self, s):
        return self.point_at(min(max(s / self.length(), 0.0), 1.0))

    def tangent_at(self, t):
        """Направление движения по дуге, радианы."""
        a = self.a0 + self.sweep * t
        return a + (math.pi / 2 if self.sweep > 0 else -math.pi / 2)

    def linearize(self, tol=0.01):
        """Ломаная с прогибом (сагиттой) не более tol."""
        if tol >= self.r:
            dphi = math.pi / 2
        else:
            dphi = 2 * math.acos(1 - tol / self.r)
        n = max(2, math.ceil(abs(self.sweep) / dphi))
        return [self.point_at(i / n) for i in range(n + 1)]

    def offset(self, d):
        """Офсет влево по ходу на d (d < 0 — вправо).

        Для дуги против часовой центр слева — радиус уменьшается."""
        r_new = self.r - d if self.sweep > 0 else self.r + d
        if r_new <= 0:
            raise CurveError(f"офсет {d} схлопывает дугу радиуса {self.r}")
        return Arc(self.cx, self.cy, r_new, self.a0, self.sweep)


def _finite(value, name):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise CurveError(f"{name} не число") from None
    if not math.isfinite(number):
        raise CurveError(f"{name} не конечное число")
    return number


def curve_spec(spec):
    """Каноническая схема кривой: arc, circle или path.

    Это запись в колонку curve. Ломаная в geom — только тесселяция для QGIS.
    """
    if not isinstance(spec, dict):
        raise CurveError("схема кривой — словарь")
    kind = spec.get("type")
    if kind == "circle":
        cx, cy, r = _finite(spec.get("cx"), "cx"), _finite(spec.get("cy"), "cy"), _finite(spec.get("r"), "r")
        if r <= 0:
            raise CurveError("радиус должен быть > 0")
        return {"type": "circle", "cx": cx, "cy": cy, "r": r}
    if kind == "arc":
        cx, cy = _finite(spec.get("cx"), "cx"), _finite(spec.get("cy"), "cy")
        r = _finite(spec.get("r"), "r")
        a0, sweep = _finite(spec.get("a0"), "a0"), _finite(spec.get("sweep"), "sweep")
        Arc(cx, cy, r, a0, sweep)
        return {"type": "arc", "cx": cx, "cy": cy, "r": r, "a0": a0, "sweep": sweep}
    if kind == "path":
        radius = _finite(spec.get("radius", 0), "radius")
        if radius < 0:
            raise CurveError("радиус пути < 0")
        raw = spec.get("vertices")
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            raise CurveError("у пути меньше двух вершин")
        vertices = []
        for pt in raw:
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                raise CurveError("вершина пути — пара координат")
            vertices.append([_finite(pt[0], "x"), _finite(pt[1], "y")])
        return {"type": "path", "radius": radius, "vertices": vertices}
    raise CurveError(f"неизвестный тип кривой {kind!r}")


def tessellate_curve(spec, tol=0.05):
    """Ломаная по схеме. Допуск — максимальная сагитта, метры."""
    spec = curve_spec(spec)
    if tol <= 0 or not math.isfinite(tol):
        raise CurveError("допуск тесселяции должен быть > 0")
    if spec["type"] == "circle":
        pts = Arc(spec["cx"], spec["cy"], spec["r"], 0.0, 2 * math.pi).linearize(tol)
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        return pts
    if spec["type"] == "arc":
        return Arc(spec["cx"], spec["cy"], spec["r"], spec["a0"], spec["sweep"]).linearize(tol)
    from .path import Path, PathError
    vertices = [tuple(p) for p in spec["vertices"]]
    if spec["radius"] > 0 and len(vertices) >= 3:
        try:
            return Path.fillet_polyline(vertices, spec["radius"]).linearize(tol)
        except PathError:
            return vertices
    return vertices
