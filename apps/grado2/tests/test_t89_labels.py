"""T89 (#8, #9): подпись улицы у территории — не ближе 1,6 мм к КРАЮ пунктира; стрелка точки съёмки не задевает подпись."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402
import print_io  # noqa: E402

LON, LAT = 37.525, 55.7925
STREET = "1-й Иртышский пр-д"
TW = 2.4                                                              # ширина знака границы территории на листе, мм


def sq(d, e):
    return {"type": "Polygon", "coordinates": [[[LON - d, LAT - e], [LON + d, LAT - e], [LON + d, LAT + e], [LON - d, LAT + e], [LON - d, LAT - e]]]}


def road(dlat, d=.0035):
    return {"g": {"type": "LineString", "coordinates": [[LON - d, LAT + dlat], [LON + d, LAT + dlat]]}, "stroke": "#f5d58a", "w": 1,
            "label": STREET, "ls": 3.8, "lf": "sans-bold"}


def ops_of(layers, **kw):
    sh = {"title": "Лист", "size": "A3", "scale": 2000, "center": [LON, LAT], "legend": [], "tep": [], "terrMask": .6,
          "territory": sq(.0012, .0007), "terrStyle": {"width": TW, "stroke": "#ff00ff", "dash": [2, 2]}, "layers": layers, **kw}
    return print_io.document_pages_ops(print_io.build_document({"sheets": [sh]}, S.REDLN, S.LGR_DASH), None)[0][2]


def label_of(ops):
    return next((o for o in ops if o.get("op") == "text" and STREET in str(o.get("text"))), None)


def terr_edges(ops):
    p = next(o for o in ops if o.get("op") == "path" and o.get("closed") and o.get("width") == TW)
    r = p["rings"][0]
    return list(zip(r, r[1:] + r[:1]))


def box_gap(o, edges):
    """Расстояние от повёрнутой коробки подписи (полувысота 0,6 кегля, как в размещении) до оси пунктира, мм."""
    a, ls = o["angle"], o["size"]
    w = print_io._text_w(o["text"], o.get("font_family"), ls)
    cx, cy = o["x"] + math.sin(a) * ls * .35, o["y"] - math.cos(a) * ls * .35
    best = 9e9
    for (x1, y1), (x2, y2) in edges:
        for k in range(0, 41):
            px, py = x1 + (x2 - x1) * k / 40, y1 + (y2 - y1) * k / 40
            u = (px - cx) * math.cos(a) + (py - cy) * math.sin(a)
            v = -(px - cx) * math.sin(a) + (py - cy) * math.cos(a)
            dx, dy = max(abs(u) - w / 2, 0), max(abs(v) - ls * .6, 0)
            best = min(best, math.hypot(dx, dy))
    return best


class StreetGapFromDash(unittest.TestCase):
    def test_gap_is_measured_from_dash_edge(self):
        # дорога в 1 мм над границей: прежняя проверка (1,6 мм от оси) оставляла ~0,4 мм до квадратиков пунктира
        ops = ops_of([{"key": "osm.roads", "title": "Дороги", "features": [road(.0007 + .00004), road(.0007 + .00004, d=.0036)]}])
        t = label_of(ops)
        if t is None:
            self.skipTest("подписи нет вовсе")
        self.assertGreaterEqual(box_gap(t, terr_edges(ops)), TW / 2 + 1.6 - .05)

    def test_label_exists_even_when_no_room(self):
        ops = ops_of([{"key": "osm.roads", "title": "Дороги", "features": [road(.0007)]}])
        self.assertIsNotNone(label_of(ops), "улица у территории подписана всегда (крайний случай: меньший зазор)")


class StreetAvoidsViewArrow(unittest.TestCase):
    def test_arrow_does_not_touch_label(self):
        r_ = road(.0007 + .00006, d=.0021)
        r_["must"] = True                                              # короткая улица, подпись обязательна
        arrow = {"g": {"type": "Point", "coordinates": [LON, LAT + .0007 + .00006]}, "mk": "view", "dir": 180, "fill": "#1f3fbf", "label": "2"}
        ops = ops_of([{"key": "osm.roads", "title": "Дороги", "features": [r_]},
                      {"title": "Точки", "features": [arrow]}], scale=10000)
        t = label_of(ops)
        self.assertIsNotNone(t)
        arr = next(o for o in ops if o.get("op") == "path" and o.get("fill") and abs(o["fill"][2] - 0xBF / 255) < .01)
        xs, ys = [p[0] for p in arr["rings"][0]], [p[1] for p in arr["rings"][0]]
        a, ls = t["angle"], t["size"]
        w = print_io._text_w(t["text"], t.get("font_family"), ls)
        cx, cy = t["x"] + math.sin(a) * ls * .35, t["y"] - math.cos(a) * ls * .35
        for px, py in zip(xs, ys):
            u = (px - cx) * math.cos(a) + (py - cy) * math.sin(a)
            v = -(px - cx) * math.sin(a) + (py - cy) * math.cos(a)
            self.assertFalse(abs(u) < w / 2 and abs(v) < ls * .45, "вершина стрелки внутри подписи")


if __name__ == "__main__":
    unittest.main()
