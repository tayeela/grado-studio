"""Album settings (#89): water colour on white schemes and map label font live in album.meta and change only water and map labels."""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402
import print_io  # noqa: E402
from test_print import sheet  # noqa: E402

SQ = {"type": "Polygon", "coordinates": [[[37.524, 55.792], [37.526, 55.792], [37.526, 55.793], [37.524, 55.793], [37.524, 55.792]]]}
PT = {"type": "Point", "coordinates": [37.525, 55.7925]}


def layers():
    return [{"key": "egko.water", "features": [{"g": SQ, "fill": "#BFE0F5", "stroke": "#bfe0f5", "a": 1}]},
            {"key": "egko.water", "title": "Вода сущпола", "features": [{"g": SQ, "fill": "#336699", "stroke": "#336699", "a": 1}]},
            {"key": "osm.roads", "features": [{"g": PT, "nm": True, "label": "ул. Тверская", "lf": "sans-bold"},
                                              {"g": PT, "nm": True, "label": "12"},
                                              {"g": PT, "nm": True, "label": "П1\nЖ", "lfs": ["sans-bold", None]}]}]


class AlbumSettings(unittest.TestCase):
    def test_default_is_identity(self):
        L = layers()
        self.assertIs(print_io.album_settings({}, L), L)
        self.assertIs(print_io.album_settings({"waterColor": "#bfe0f5", "labelFont": "base"}, L), L)
        spec = {"meta": {"object": "x"}, "sheets": [sheet()]}
        self.assertIs(print_io._with_settings(spec), spec)

    def test_water_only_white_scheme(self):
        out = print_io.album_settings({"waterColor": "#88AAFF".lower()}, layers())
        self.assertEqual((out[0]["features"][0]["fill"], out[0]["features"][0]["stroke"]), ("#88aaff", "#88aaff"))
        self.assertEqual(out[1]["features"][0]["fill"], "#336699")          # сущпол — класс 22, не меняется
        self.assertEqual(out[2], layers()[2])                                # подписи не тронуты
        self.assertEqual(print_io.album_settings({"waterColor": "red"}, layers()), layers())   # не цвет — без изменений

    def test_label_font(self):
        pt = print_io.album_settings({"labelFont": "pt-sans"}, layers())[2]["features"]
        self.assertEqual([f.get("lf") for f in pt], ["ui-bold", None, None])
        self.assertEqual(pt[2]["lfs"], ["ui-bold", None])
        ms = print_io.album_settings({"labelFont": "montserrat"}, layers())[2]["features"]
        self.assertEqual([f.get("lf") for f in ms], ["sans-bold", "sans", "sans"])
        self.assertEqual(print_io.album_settings({"labelFont": "montserrat"}, layers())[0], layers()[0])   # вода не тронута

    def test_print_changes_only_water(self):
        base = sheet(layers=[{"key": "egko.water", "title": "Вода", "features": [{"g": SQ, "fill": "#bfe0f5", "stroke": "#bfe0f5", "w": 0, "a": 1}]}])
        a = print_io.render_preview_svg({"meta": {}, "sheets": [base]}, S.REDLN, S.LGR_DASH)
        b = print_io.render_preview_svg({"meta": {"waterColor": "#123456"}, "sheets": [base]}, S.REDLN, S.LGR_DASH)
        a, b = (re.sub(r"clip\d+", "clip", t) for t in (a, b))                # номер обрезки растёт от вызова к вызову
        diff = [(x, y) for x, y in zip(a.splitlines(), b.splitlines()) if x != y]
        self.assertEqual(len(a.splitlines()), len(b.splitlines()))
        self.assertEqual(len(diff), 1)                                       # отличается одна заливка воды
        self.assertIn('fill="rgb(191,224,245)"', diff[0][0])

if __name__ == "__main__":
    unittest.main()
