"""Слои знака в печати (symparts.py): полоса внутрь — внутри контура и нужной ширины, значки вдоль линии — с шагом и
на нужной стороне (внутрь полигона при side > 0, наружу при side < 0, справа по ходу у линии), штриховка и линия по контуру;
print_io рисует части поверх объекта карты листа."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402,F401  пути к core (grado_render)
import symparts  # noqa: E402

SQ = [[(0, 0), (40, 0), (40, 40), (0, 40)]]        # квадрат 40 мм, ось y вниз


def inside(x, y):
    return 0 < x < 40 and 0 < y < 40


class SymParts(unittest.TestCase):
    """Эталон на Python (parts_ops_py) — по нему сверяется Rust (класс ниже)."""
    def test_band_is_inside_and_as_wide_as_asked(self):
        from shapely.geometry import Polygon
        ops = symparts.parts_ops_py("poly", [SQ], [{"k": "band", "c": "#ff0000", "a": .5, "b": 10}])
        self.assertEqual(len(ops), 1)
        band = Polygon(ops[0]["rings"][0], ops[0]["rings"][1:])
        b = 10 * symparts.PX_MM
        self.assertAlmostEqual(band.area, 40 * 40 - (40 - 2 * b) ** 2, delta=0.5)
        self.assertTrue(Polygon(SQ[0]).buffer(1e-6).contains(band))
        self.assertGreater(min(ops[0]["fill"]), 0.4)                 # 50 % красного поверх белого — светлее чистого

    def test_marks_face_inside_or_outside_whatever_the_ring_direction(self):
        for ring in (SQ[0], list(reversed(SQ[0]))):
            for side, want in ((1, True), (-1, False)):
                ops = symparts.parts_ops_py("poly", [[ring]], [{"k": "marks", "shape": "tick", "step": 40, "size": 10, "side": side}])
                self.assertGreater(len(ops), 4)
                for o in ops:
                    (x0, y0), (x1, y1) = o["rings"][0]
                    self.assertEqual(inside(x1, y1), want, (ring[:2], side, o["rings"][0]))

    def test_marks_step_along_a_line_and_right_side(self):
        step = 20 * symparts.PX_MM
        ops = symparts.parts_ops_py("line", [[(0, 0), (100, 0)]], [{"k": "marks", "shape": "tick", "step": 20, "size": 5, "side": 1}])
        xs = [o["rings"][0][0][0] for o in ops]
        self.assertAlmostEqual(xs[0], step / 2, places=6)
        self.assertAlmostEqual(xs[1] - xs[0], step, places=6)
        self.assertTrue(all(o["rings"][0][1][1] > 0 for o in ops))   # y вниз: справа по ходу на восток — ниже линии

    def test_hatch_and_outline(self):
        ops = symparts.parts_ops_py("poly", [SQ], [{"k": "hatch", "c": "#000000", "hp": "x0", "hs": 8, "w": 1}, {"k": "line", "c": "#0000ff", "w": 2, "dash": [6, 4]}])
        self.assertGreaterEqual(len(ops), 3)                         # штриховка сеткой (2 направления) + линия
        last = ops[-1]
        self.assertEqual(last["stroke"], (0.0, 0.0, 1.0))
        self.assertEqual(last["dash"], [6 * symparts.PX_MM, 4 * symparts.PX_MM])

    def test_polygon_parts_skip_lines(self):
        for f in (symparts.parts_ops, symparts.parts_ops_py):
            self.assertEqual(f("line", [[(0, 0), (10, 0)]], [{"k": "band", "b": 5}, {"k": "hatch"}]), [])

    def test_print_map_draws_parts_on_top(self):
        import print_io
        import server as S
        lon, lat, d = 37.803, 55.827, .0005
        sq = {"type": "Polygon", "coordinates": [[[lon - d, lat - d / 2], [lon + d, lat - d / 2], [lon + d, lat + d / 2], [lon - d, lat + d / 2], [lon - d, lat - d / 2]]]}
        feat = {"g": sq, "fill": "#cccccc", "stroke": "#000000", "w": 1, "a": 1,
                "parts": [{"k": "marks", "c": "#e34948", "shape": "tri", "step": 16, "size": 5, "side": 1}]}
        spec = {"block": {"w": 100, "h": 80, "scale": 2000, "center": [lon, lat]}, "layers": [{"title": "Зона", "features": [feat]}]}
        import layout_io
        _, ops = layout_io._map_ops(spec, S.REDLN, S.LGR_DASH, None)
        red = [o for o in ops if o.get("op") == "path" and o.get("fill") == print_io.hex_to_rgb("#e34948")]
        self.assertGreater(len(red), 4)


RS = symparts._rust()
HOLE = [[(0, 0), (40, 0), (40, 40), (0, 40)], [(15, 15), (15, 25), (25, 25), (25, 15)]]


@unittest.skipUnless(RS, "нет модуля grado_rs 0.2+")
class RustSameAsPython(unittest.TestCase):
    """Слои знака на Rust (rust/crates/symbol) дают то же, что эталон: линия, штриховка, значки — те же операции;
    полоса — та же картинка (на Rust она обрезанный контур, на Python — буфер shapely)."""

    def same_ops(self, kind, shapes, parts):
        a, b = symparts.parts_ops(kind, shapes, parts), symparts.parts_ops_py(kind, shapes, parts)
        self.assertEqual(len(a), len(b), parts)
        for x, y in zip(a, b):
            self.assertEqual((x["closed"], x["width"] is not None), (y["closed"], y["width"] is not None))
            self.assertAlmostEqual(x["width"], y["width"], places=9)
            for k in ("fill", "stroke"):
                self.assertEqual(x[k] is None, y[k] is None, k)
                if x[k] is not None:
                    for u, v in zip(x[k], y[k]):
                        self.assertAlmostEqual(u, v, places=9)
            self.assertEqual(len(x["rings"]), len(y["rings"]))
            for r1, r2 in zip(x["rings"], y["rings"]):
                self.assertEqual(len(r1), len(r2))
                for p1, p2 in zip(r1, r2):
                    self.assertAlmostEqual(p1[0], p2[0], places=6)
                    self.assertAlmostEqual(p1[1], p2[1], places=6)

    def test_lines_hatch_marks(self):
        for shape in ("tick", "tri", "dot", "cross"):
            for side in (1, -1):
                self.same_ops("poly", [HOLE], [{"k": "marks", "c": "#e34948", "shape": shape, "step": 18, "size": 6, "side": side, "w": 1.5}])
                self.same_ops("line", [[(0, 0), (30, 5), (60, -10)]], [{"k": "marks", "shape": shape, "step": 12, "size": 4, "side": side}])
        for hp in ("0", "90", "45", "135", "x45", "x0"):
            self.same_ops("poly", [HOLE], [{"k": "hatch", "c": "#000000", "hp": hp, "hs": 9, "w": 1}])
        self.same_ops("poly", [HOLE], [{"k": "line", "c": "#0000ff", "w": 2, "dash": [6, 4], "a": .5}])
        self.same_ops("line", [[(0, 0), (30, 5)]], [{"k": "line", "c": "#0000ff", "w": 2}])

    def test_band_same_picture(self):
        import json
        import grado_rs
        part = [{"k": "band", "c": "#ff0000", "a": 1, "b": 12}]

        def ink(ops):
            png, *_ = grado_rs.render_plate(json.dumps(ops), 40, 40, 200)
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(png)).convert("L")
            return {i for i, v in enumerate(im.tobytes()) if v < 200}
        a, b = ink(symparts.parts_ops("poly", [HOLE], part)), ink(symparts.parts_ops_py("poly", [HOLE], part))
        self.assertGreater(len(a & b) / len(a | b), 0.95)

    def test_lgr_linetypes(self):
        """Все типы линий REDLN97 на Rust (print_io.linetype_ops) — те же операции, что Python-эталон: штрихи, точки,
        знаки своей толщиной; по ломаной с изломами, в масштабе печати и легенды (shape_k)."""
        import print_io
        lib = server.REDLN
        self.assertIsNotNone(print_io._rs_linelib(lib), "модуль grado_rs без LineLib")
        line = [(0, 0), (40, 3), (55, 30), (20, 60), (21, 61)]
        for name in lib["linetypes"]:
            for k, sk in ((print_io.LT_MM, print_io.LT_SHAPE_MM), (0.2, None)):
                a = print_io.linetype_ops(line, name, k, (0.8, 0.1, 0.1), 0.5, lib, shape_k=sk)
                b = print_io.linetype_ops_py(line, name, k, (0.8, 0.1, 0.1), 0.5, lib, shape_k=sk)
                self.assertEqual(len(a), len(b), name)
                for x, y in zip(a, b):
                    self.assertEqual(x.get("join"), y.get("join"), name)
                    self.assertAlmostEqual(x["width"], y["width"], places=9, msg=name)
                    self.assertEqual(tuple(x["stroke"]), tuple(y["stroke"]))
                    self.assertEqual(len(x["rings"]), len(y["rings"]), name)
                    for r1, r2 in zip(x["rings"], y["rings"]):
                        self.assertEqual(len(r1), len(r2), name)
                        for p1, p2 in zip(r1, r2):
                            self.assertAlmostEqual(p1[0], p2[0], places=6, msg=name)
                            self.assertAlmostEqual(p1[1], p2[1], places=6, msg=name)


if __name__ == "__main__":
    unittest.main()
