"""T78: подписи альбома — станции не лежат на железной дороге и границе района, кавычки-ёлочки, выноски не в угловых надписях."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402
import print_io  # noqa: E402

LON, LAT = 37.525, 55.7925
STN = "ст. ж/д Калошино"


def sq(d, e, lon=LON, lat=LAT):
    return {"type": "Polygon", "coordinates": [[[lon - d, lat - e], [lon + d, lat - e], [lon + d, lat + e], [lon - d, lat + e], [lon - d, lat - e]]]}


def hline(lat=LAT, d=.004):
    return {"type": "LineString", "coordinates": [[LON - d, lat], [LON + d, lat]]}


def sheet(layers, **kw):
    return {"title": "Лист", "size": "A3", "scale": 2000, "center": [LON, LAT], "legend": [], "tep": [], "layers": layers, **kw}


def ops_of(sh):
    doc = print_io.build_document({"sheets": [sh]}, S.REDLN, S.LGR_DASH)
    return print_io.document_pages_ops(doc, None)[0][2]


def texts(ops, needle):
    return [o for o in ops if o.get("op") == "text" and needle in str(o.get("text"))]


def crosses(o, y_line, pad=0.0):
    """Подпись (горизонтальная) пересекает горизонтальную линию на высоте y_line (мм)."""
    return o["y"] - o["size"] * 1.0 - pad < y_line < o["y"] + o["size"] * .3 + pad


class StationNotOnRail(unittest.TestCase):
    def _run(self, with_rail):
        area = {"g": sq(.0016, .0006), "fill": "#cccccc", "stroke": "#999999", "w": .5, "a": .3, "label": STN, "ls": 3.8}
        layers = [{"key": "osm.landuse", "title": "Землепользование", "features": [area]}]
        if with_rail:
            layers.append({"key": "yandex.rail", "title": "Железная дорога", "over": True,
                           "features": [{"g": hline(), "stroke": "#1f1f1f", "w": 4}]})
        sh = sheet(layers)
        tr = print_io.MapTransform((0, 0, 400, 277), sh["center"], sh["scale"])
        return ops_of(sh)

    def _line_y(self, ops):
        paths = [o for o in ops if o.get("op") == "path" and o.get("stroke") == (0.12156862745098039, 0.12156862745098039, 0.12156862745098039)
                 and not o.get("closed") and len(o["rings"][0]) == 2]
        return paths[0]["rings"][0][0][1] if paths else None

    def test_label_baseline_sits_on_rail_without_obstacle(self):
        ops = self._run(False)
        t = texts(ops, "Калошино")
        self.assertTrue(t, "подпись станции есть")
        self.assertLess(abs(t[0]["y"] - 122.0), 1.5, "без препятствия подпись стоит на центре (тест чувствителен)")
        self.assertTrue(t[0]["text"].startswith(STN[:9]))

    def test_label_avoids_rail(self):
        ops = self._run(True)
        y_line = self._line_y(ops)
        self.assertIsNotNone(y_line, "линия железной дороги нарисована")
        t = texts(ops, "Калошино")
        self.assertTrue(t, "подпись станции осталась на листе")
        for o in t:
            self.assertFalse(crosses(o, y_line), f"подпись {o['y']:.1f} лежит на линии {y_line:.1f}")


class DistrictBoundaryObstacle(unittest.TestCase):
    def test_label_avoids_district_line(self):
        area = {"g": sq(.0016, .0006), "fill": "#cccccc", "stroke": "#999999", "w": .5, "a": .3, "label": "СНТ Ручеёк", "ls": 3.8}
        layers = [{"key": "osm.landuse", "title": "Землепользование", "features": [area]},
                  {"title": "Граница района", "over": True, "features": [{"g": hline(), "stroke": "#e30613", "fill": "#e30613", "w": 2, "a": 0}]}]
        ops = ops_of(sheet(layers))
        y_line = [o for o in ops if o.get("op") == "path" and o.get("stroke") == (227 / 255, 6 / 255, 19 / 255)][0]["rings"][0][0][1]
        t = texts(ops, "Ручеёк")
        self.assertTrue(t)
        self.assertFalse(crosses(t[0], y_line))


class Quotes(unittest.TestCase):
    def test_guillemets(self):
        self.assertEqual(print_io._guillemets('ЖК "Сиреневый парк"'), "ЖК «Сиреневый парк»")
        self.assertEqual(print_io._guillemets('ГСК "Статор"'), "ГСК «Статор»")
        self.assertEqual(print_io._guillemets('ГСК "Статор'), 'ГСК "Статор')

    def test_label_on_sheet(self):
        pt = {"g": {"type": "Point", "coordinates": [LON, LAT]}, "fill": "#666666", "w": 1, "label": 'ЖК "Сиреневый парк"', "ls": 3.0}
        ops = ops_of(sheet([{"title": "Точки", "features": [pt]}]))
        self.assertTrue(texts(ops, "«Сиреневый парк»"))
        self.assertFalse(texts(ops, '"'))


class LeadersAndCaptions(unittest.TestCase):
    def _marks(self, n=3):
        feats = []
        for i in range(n):
            lon = LON - .0016 + i * .00004                    # три участка рядом: точки ближе 4 мм
            feats.append({"g": sq(.00012, .00012, lon, LAT + .0003 * i), "fill": "#ddeeff", "stroke": "#1f3fbf", "w": .5, "a": 0,
                          "label": str(i + 1), "ls": 3.0, "circle": True, "leader": True, "zone": sq(.00012, .00012, lon, LAT + .0003 * i)["coordinates"]})
        return feats

    def test_leader_dots_spread(self):
        feats = self._marks(3)
        ops = ops_of(sheet([{"title": "Участки", "features": feats}]))
        dots = [(o["x"], o["y"]) for o in ops if o.get("op") == "circle" and abs(o.get("r", 0) - 1.0) < 1e-6]
        for i in range(len(dots)):
            for j in range(i + 1, len(dots)):
                self.assertGreaterEqual(math.hypot(dots[i][0] - dots[j][0], dots[i][1] - dots[j][1]), 2.4)

    def test_leader_does_not_enter_caption(self):
        # крошечный участок сразу под угловой надписью: выноски вверх (в надпись) недопустимы
        sh0 = sheet([], mapNote=[["Северный", "административный округ"], ["район Гольяново"]])
        rect = next(o for o in ops_of(sh0) if o.get("op") == "clip")["rect"]
        tr = print_io.MapTransform(rect, sh0["center"], sh0["scale"])
        x0, y0 = tr.mm(LON, LAT)
        ex, ey = tr.mm(LON + .001, LAT)[0] - x0, tr.mm(LON, LAT + .001)[1] - y0         # мм на градус
        want = (rect[0] + 50, rect[1] + 30)                                              # 4 мм ниже угловой надписи
        lon, lat = LON + (want[0] - x0) / ex * .001, LAT + (want[1] - y0) / ey * .001
        feat = {"g": sq(.00004, .00004, lon, lat), "fill": "#ddeeff", "stroke": "#1f3fbf", "w": .5, "a": 0, "label": "7", "ls": 3.0,
                "circle": True, "leader": True, "zone": sq(.00004, .00004, lon, lat)["coordinates"]}
        ops = ops_of({**sh0, "layers": [{"title": "Участки", "features": [feat]}]})
        n = 3
        cap = (rect[0], rect[1], rect[0] + 102, rect[1] + 7 + 5.4 * n + 3)
        leaders = [o for o in ops if o.get("op") == "path" and not o.get("closed") and o.get("rings") and len(o["rings"][0]) == 2
                   and o.get("width") == 0.5]
        self.assertTrue(leaders, "выноска нарисована")
        for o in leaders:
            for (px, py) in o["rings"][0]:
                self.assertFalse(cap[0] < px < cap[2] and cap[1] < py < cap[3], f"выноска заходит в угловую надпись: {px:.1f},{py:.1f}")
        dot = [o for o in ops if o.get("op") == "circle" and abs(o.get("r", 0) - 1.0) < 1e-6]
        for o in dot:
            self.assertFalse(cap[0] < o["x"] < cap[2] and cap[1] < o["y"] < cap[3])
