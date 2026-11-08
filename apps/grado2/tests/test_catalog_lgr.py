"""Выгрузка из каталога ГИС ОГД со стилями сами (владелец 08.11.2026): линии границ ПК — полигонами того же объекта,
полигоны зон ЛГР — контуром знаком ЛГР (знаки внутрь), сторона линий границ ПК — по их полигонам, и тот же знак — в печати листа.

Запуск: ~/.grado2/venv/bin/python -m pytest apps/grado2/tests/test_catalog_lgr.py
"""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402
import ogd_all  # noqa: E402
import print_io  # noqa: E402

CAT = [{"id": 1, "parent_id": 0, "code": "f0", "name": "Слои", "type": "folder"},
       {"id": 2, "parent_id": 1, "code": "f36", "name": "3.6 Природный комплекс", "type": "folder"},
       {"id": 3, "parent_id": 2, "code": "l18", "type": "layer", "name": "Границы объектов природного комплекса"},
       {"id": 4, "parent_id": 2, "code": "virtual138", "type": "virtual", "name": "Природные и озеленённые территории"},
       {"id": 5, "parent_id": 2, "code": "l21", "type": "layer", "name": "Границы режимов регулирования"},
       {"id": 6, "parent_id": 1, "code": "virtual109", "type": "virtual", "name": "Водоохранная зона",
        "path": "Слои / 2.6 Водоохранные зоны / Водоохранная зона"}]
SMALL = {"type": "Polygon", "coordinates": [[[37.604, 55.7545], [37.606, 55.7545], [37.606, 55.7555], [37.604, 55.7555], [37.604, 55.7545]]]}
SQ = {"type": "Polygon", "coordinates": [[[37.60, 55.75], [37.61, 55.75], [37.61, 55.76], [37.60, 55.76], [37.60, 55.75]]]}


class Catalog(unittest.TestCase):
    def test_border_lines_point_to_their_polygons_in_the_tree(self):
        leaves = {}

        def walk(ns):
            for n in ns:
                if n.get("code"):
                    leaves[n["code"]] = n
                walk(n["children"])
        walk(ogd_all.catalog_tree(CAT))
        self.assertEqual(leaves["l18"]["instead"], "virtual138")
        self.assertEqual(leaves["l21"]["instead"], "virtual139")
        self.assertNotIn("instead", leaves["virtual138"])
        self.assertEqual([x["code"] for x in ogd_all.layer_list(CAT, {"l18", "l21"})], ["virtual138"])   # в DXF — полигоны, не линии

    def test_nature_border_lines_are_turned_by_their_polygons_on_download(self):
        edge = [[37.60, 55.75], [37.61, 55.75]]                       # нижний край квадрата, на восток: ПК слева
        lines = [{"geometry": {"type": "LineString", "coordinates": list(edge)}, "properties": {"linelineco": "18"}}]
        api = mock.Mock()
        api.fetch.return_value = {"features": [{"geometry": SQ}]}
        self.assertEqual(S.orient_by_areas(api, (37.5, 55.7, 37.7, 55.8), "l18", lines), 1)
        api.fetch.assert_called_once_with((37.5, 55.7, 37.7, 55.8), "virtual138")
        self.assertEqual(lines[0]["geometry"]["coordinates"], edge[::-1])
        api.fetch.side_effect = S.ConnectorError("портал не ответил")
        self.assertEqual(S.orient_by_areas(api, (37.5, 55.7, 37.7, 55.8), "l18", lines), 0)   # без полигонов — как есть

    def test_lgr_zone_polygons_get_their_sign_on_the_contour(self):
        c = mock.Mock()
        c.obj.return_value = {"layers": {"virtual109": ["poly", None], "virtual138": ["poly", None], "l1": ["line", "1"]}}
        with mock.patch.object(S, "ogd_catalog", return_value=CAT), \
                mock.patch.object(ogd_all, "portal_styles", return_value=lambda code: ""):
            r = json.loads(S.post_ogd_styles(c).body)
        self.assertEqual(r["styles"]["virtual109"]["lgrLine"], 16)    # водоохранная зона — её знаком, знаки внутрь
        self.assertEqual(r["styles"]["virtual138"]["lgrLine"], 18)
        self.assertNotIn("lgrLine", r["styles"]["l1"])                # линии ЛГР — режим lgr по своим кодам, не знак слоя
        self.assertGreaterEqual(r["rev"]["virtual109"], 4)             # слои проекта перекрасятся один раз
        self.assertTrue(S.lgr_has_linetype(18))
        self.assertFalse(S.lgr_has_linetype(29))                      # техзоны — штрих Эталона, без знаков


class PrintContour(unittest.TestCase):
    def frame(self, lsign):
        name = S.acad_lin.linetypes_for_codes([(18, 1)], S.REDLN["linetypes"], S.REDLN_IDX)[0]
        sheet = {"size": "A3", "title": "Лист", "scale": 2000, "center": [37.605, 55.755], "basemap": "none", "noFrame": True,
                 "layers": [{"title": "ПК", "features": [{"g": SMALL, "fill": "#88cc88", "stroke": "#00aa00", "w": 1, "a": .3,
                                                           "lt": [name], "lsign": lsign}]}]}
        return print_io.SketchMapFrame((0, 0, 400, 280), sheet, S.REDLN, S.LGR_DASH).ops({})

    def test_zone_contour_is_drawn_with_lgr_marks_inside(self):
        ins, outs = self.frame(1), self.frame(-1)
        tr = print_io.MapTransform((0, 0, 400, 280), [37.605, 55.755], 2000)
        xs = [tr.mm(p[0], p[1])[0] for p in SMALL["coordinates"][0]]
        ys = [tr.mm(p[0], p[1])[1] for p in SMALL["coordinates"][0]]
        box = (min(xs), min(ys), max(xs), max(ys))

        def inside_share(ops):                                         # доля точек знаков внутри квадрата
            pts = [p for o in ops if o["op"] == "path" and o.get("stroke") and not o.get("fill") for r in o["rings"] for p in r]
            pts = [p for p in pts if not (abs(p[0] - box[0]) < .05 or abs(p[0] - box[2]) < .05 or abs(p[1] - box[1]) < .05 or abs(p[1] - box[3]) < .05)]
            return sum(box[0] < p[0] < box[2] and box[1] < p[1] < box[3] for p in pts) / max(1, len(pts))
        self.assertGreaterEqual(sum(o["op"] == "path" and not o.get("fill") for o in ins), 2)   # контур и его знаки
        self.assertGreater(inside_share(ins), .9)
        self.assertLess(inside_share(outs), .1)


if __name__ == "__main__":
    unittest.main()
