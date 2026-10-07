"""Проверяет PPTX-бэкенд (grado_render): обрезку по рамке, пакет OOXML, живой текст и ореол PDF.

Запуск: python -m unittest discover -s core/render/tests (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import io
import re
import unittest
import zipfile

from grado_render.backend_pptx import PptxBackend, clip_polygon, clip_polyline, orient


def _slide(data, n=1):
    return zipfile.ZipFile(io.BytesIO(data)).read(f"ppt/slides/slide{n}.xml").decode("utf-8")


class Geometry(unittest.TestCase):
    def test_polyline_is_cut_by_the_frame(self):
        self.assertEqual(clip_polyline([(0, 0), (20, 20), (40, 0)], (10, 0, 30, 30)), [[(10.0, 10.0), (20, 20), (30.0, 10.0)]])

    def test_polygon_is_cut_by_the_frame(self):
        self.assertEqual(clip_polygon([(0, 0), (20, 0), (20, 20), (0, 20)], (10, 10, 30, 30)),
                         [(10.0, 10), (20.0, 10), (20, 20), (10, 20.0)])

    def test_hole_winds_against_its_outer_ring(self):
        area = lambda r: sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]))
        outer, hole = orient([[(0, 0), (10, 0), (10, 10), (0, 10)], [(2, 2), (4, 2), (4, 4), (2, 4)]])
        self.assertLess(area(outer) * area(hole), 0)


class Package(unittest.TestCase):
    OPS = [{"op": "clip", "rect": (10, 10, 100, 80)},
           {"op": "layer", "name": "Зоны"},
           {"op": "path", "rings": [[(0, 0), (50, 0), (50, 50), (0, 50)]], "closed": True, "fill": (1, 0, 0), "stroke": (0, 0, 0), "width": .3},
           {"op": "path", "rings": [[(5, 60), (200, 60)]], "closed": False, "fill": None, "stroke": (0, 0, 1), "width": .3, "dash": [1, .5]},
           {"op": "path", "rings": [[(5, 65), (200, 65)]], "closed": False, "fill": None, "stroke": (0, 0, 1), "width": .3, "dash": [1, .5]},
           {"op": "layer", "name": "Подписи"},
           {"op": "text", "x": 50, "y": 50, "size": 3, "text": "Улица <Новая>", "anchor": "middle", "angle": .3, "halo": .5},
           {"op": "text", "x": 500, "y": 50, "size": 3, "text": "вне рамки"},
           {"op": "unclip"}]

    def test_parts_and_slide_size(self):
        data = PptxBackend("Проверка").render([(420, 297, [("Карта", self.OPS)]), (420, 297, [("Оформление", [])])])
        z = zipfile.ZipFile(io.BytesIO(data))
        names = set(z.namelist())
        for part in ("[Content_Types].xml", "ppt/presentation.xml", "ppt/slides/slide2.xml", "ppt/theme/theme1.xml",
                     "ppt/slideMasters/slideMaster1.xml", "ppt/slideLayouts/slideLayout1.xml"):
            self.assertIn(part, names)
        self.assertIn('<p:sldSz cx="15120000" cy="10692000"/>', z.read("ppt/presentation.xml").decode())   # А3 альбомный

    def test_text_is_live_and_frame_cuts_what_is_outside(self):
        s = _slide(PptxBackend().render([(420, 297, [("Карта", self.OPS)])]))
        self.assertIn("<a:t>Улица &lt;Новая&gt;</a:t>", s)
        self.assertNotIn("вне рамки", s)
        self.assertIn("<a:glow", s)                                       # ореол подписи — свечение
        self.assertIn('name="Зоны"', s)                                   # слой — группа фигур
        self.assertEqual(s.count("<a:custDash>"), 1)                      # две линии одного вида — одна фигура
        xs = [int(v) for v in re.findall(r'<a:off x="(-?\d+)"', s)][1:]          # первое — само дерево слайда
        self.assertGreaterEqual(min(xs), 10 * 36000 - 1)                  # ничего левее рамки

    def test_ring_clip_becomes_white_mask(self):
        ops = [{"op": "clip", "rings": [[(20, 20), (60, 20), (60, 60), (20, 60)]]},
               {"op": "path", "rings": [[(0, 0), (100, 0), (100, 100), (0, 100)]], "closed": True, "fill": (0, 1, 0), "stroke": None},
               {"op": "unclip"}]
        s = _slide(PptxBackend().render([(420, 297, [("Карта", ops)])]))
        self.assertIn('name="Маска"', s)
        self.assertIn('<a:srgbClr val="FFFFFF"/>', s)


if __name__ == "__main__":
    unittest.main()


class PdfHalo(unittest.TestCase):
    def test_halo_is_solid_after_a_dashed_line(self):
        import zlib
        from grado_render import PdfBackend
        ops = [{"op": "path", "rings": [[(10, 10), (90, 10)]], "closed": False, "fill": None, "stroke": (1, 0, 1), "width": 1.1, "dash": [1.1, 1.1]},
               {"op": "text", "x": 20, "y": 40, "size": 4, "text": "СНТ «Космос»", "halo": .55}]
        pdf = PdfBackend().render([(100, 60, ops)])
        streams = [zlib.decompress(m.group(1)) for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S) if m.group(1)[:2] == b"x\x9c"]
        page = next(s for s in streams if b"Tr" in s)
        halo = page[page.index(b"q\n"):page.index(b"1 Tr")]
        self.assertIn(b"[] 0 d", halo)                      # ореол подписи — сплошной, не пунктир границы
