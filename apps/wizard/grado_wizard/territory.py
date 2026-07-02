"""Построение проекта территории для мастера.

Вход — граница (кольцо в метрах СК проекта) и параметры. Слои опорного
плана в продукте приходят из снимков коннекторов; здесь генерируется
демонстрационное наполнение (застройка, зоны, красные линии) по границе.
"""

import math

from grado_geom import Path as GPath
from grado_model import Project


def ring_area_ha(ring):
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2 / 10000.0


def ring_bbox(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def demo_boundary(x0=413000.0, y0=6178000.0):
    """Нерегулярная граница «по мотивам» реальных территорий (~42 га)."""
    pts = [(0, 0), (650, 0), (650, 180), (520, 180), (520, 420), (300, 420),
           (300, 560), (60, 560), (60, 300), (0, 300)]
    return [(x0 + dx, y0 + dy) for dx, dy in pts]


def _rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]


def _poly(ring):
    ring = [list(p) for p in ring]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def build_project(path, name, boundary):
    p = Project.create(path, name)
    x0, y0, x1, y1 = ring_bbox(boundary)

    p.add_layer("terr.boundary").add_feature(_poly(boundary),
                                             attrs={"name": name})
    # ограничения: ЗОУИТ вдоль юго-восточного края (~2.9 га)
    restrict = p.add_layer("terr.restrict")
    restrict.add_feature(_poly(_rect(x0 + 520, y0, 130, 180)),
                         attrs={"kind": "охранная зона ЛЭП"}, source="nspd")
    restrict.add_feature(_poly(_rect(x0 + 60, y0 + 470, 90, 90)),
                         attrs={"kind": "прибрежная защитная полоса"},
                         source="nspd")

    zouit = p.add_layer("cad.zouit")
    zouit.add_feature(_poly(_rect(x0 + 520, y0, 130, 180)),
                      attrs={"kind": "ЗОУИТ 77:00-6.1"}, source="nspd")

    # функциональные зоны (упрощённо, независимыми полигонами)
    zones = p.add_layer("tp.func_zone")
    zones.add_feature(_poly(_rect(x0 + 60, y0 + 180, 460, 240)),
                      attrs={"zone_code": "Ж", "zone_title": "Ж-1"},
                      source="fgistp")
    zones.add_feature(_poly(_rect(x0, y0, 520, 180)),
                      attrs={"zone_code": "О", "zone_title": "О-1"},
                      source="fgistp")
    zones.add_feature(_poly(_rect(x0 + 60, y0 + 420, 240, 140)),
                      attrs={"zone_code": "Пр", "zone_title": "Пр-1"},
                      source="fgistp")

    # красная линия проезда: сопряжение R=60
    red = GPath.fillet_polyline(
        [(x0 - 30, y0 + 190), (x0 + 400, y0 + 190), (x0 + 400, y0 + 590)],
        radius=60)
    p.add_layer("pp.red_line").add_feature(
        {"type": "LineString",
         "coordinates": [list(pt) for pt in red.linearize(0.05)]},
        attrs={"status": "устанавливаемая"})

    # многоквартирная застройка: сетка корпусов в Ж-1
    bld = p.add_layer("oks.building")
    floors_cycle = [9, 12, 14, 12, 9]
    n = 0
    for row in range(3):
        for col in range(5):
            bx = x0 + 90 + col * 82
            by = y0 + 215 + row * 62
            bld.add_feature(_poly(_rect(bx, by, 30, 17)),
                            attrs={"purpose": "МКД",
                                   "floors": floors_cycle[(n := n + 1) % 5]})
    # блокированная застройка: ряд у западной границы
    for i in range(4):
        bld.add_feature(_poly(_rect(x0 + 80, y0 + 445 + i * 26, 34, 12)),
                        attrs={"purpose": "блокированная", "floors": 3})

    # зоны размещения нежилых ОКС
    place = p.add_layer("pp.placement_zone")
    place.add_feature(_poly(_rect(x0 + 90, y0 + 40, 130, 90)),
                      attrs={"purpose": "Общественный центр"})
    place.add_feature(_poly(_rect(x0 + 300, y0 + 30, 170, 110)),
                      attrs={"purpose": "Производственный комплекс"})

    soc = p.add_layer("social.object")
    soc.add_feature({"type": "Point", "coordinates": [x0 + 470, y0 + 350]},
                    attrs={"kind": "ОО+ДОО", "capacity": 750})
    return p
