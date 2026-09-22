"""Аффинные преобразования точек: поворот, масштаб, зеркало.

Ось и начало задаёт вызывающий. Функции не пишут проект и не режут топологию.
"""

import math


def _pairs(points):
    out = []
    for pt in points:
        if len(pt) < 2:
            raise ValueError("точка — пара координат")
        x, y = float(pt[0]), float(pt[1])
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("координата не конечна")
        out.append((x, y))
    return out


def rotate(points, origin, degrees):
    """Поворот вокруг origin на degrees против часовой, градусы."""
    ox, oy = float(origin[0]), float(origin[1])
    rad = math.radians(float(degrees))
    c, s = math.cos(rad), math.sin(rad)
    out = []
    for x, y in _pairs(points):
        dx, dy = x - ox, y - oy
        out.append((ox + dx * c - dy * s, oy + dx * s + dy * c))
    return out


def scale(points, origin, factor):
    """Масштаб относительно origin. factor > 0."""
    factor = float(factor)
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError("масштаб должен быть > 0")
    ox, oy = float(origin[0]), float(origin[1])
    return [(ox + (x - ox) * factor, oy + (y - oy) * factor) for x, y in _pairs(points)]


def mirror(points, a, b):
    """Отражение относительно прямой через точки a и b."""
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 == 0 or not math.isfinite(length2):
        raise ValueError("ось зеркала — не прямая")
    out = []
    for x, y in _pairs(points):
        t = ((x - ax) * dx + (y - ay) * dy) / length2
        px, py = ax + t * dx, ay + t * dy
        out.append((2 * px - x, 2 * py - y))
    return out
