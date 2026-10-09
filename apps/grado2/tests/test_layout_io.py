"""«Макет листа» нового интерфейса в печать (layout_io.py): лист редактора с картой, легендой, надписью, картинкой,
стрелкой, линейкой, таблицей и фигурами собирается в PDF и SVG; карта стоит в своём блоке в заданном масштабе."""

import base64
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402
import layout_io  # noqa: E402

LON, LAT = 37.803, 55.827


def square(d):
    return {"type": "Polygon", "coordinates": [[[LON - d, LAT - d / 2], [LON + d, LAT - d / 2], [LON + d, LAT + d / 2], [LON - d, LAT + d / 2], [LON - d, LAT - d / 2]]]}


def png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGBA", (40, 20), (200, 30, 30, 255)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def spec(**sheet_kw):
    blocks = [
        {"id": "map-1", "kind": "map", "x": 25, "y": 10, "w": 270, "h": 224, "scale": 2000, "center": [LON, LAT], "frame": {"on": True, "color": "#1a1a1a", "width": .35}},
        {"id": "legend-1", "kind": "legend", "x": 305, "y": 10, "w": 105, "h": 120, "title": "Условные обозначения",
         "items": [{"t": "Здания", "s": "fill", "c": "#4d4d4d", "f": "#cbc6be"}, {"t": "Красные линии", "s": "line", "c": "#d03a2f"}]},
        {"id": "text-1", "kind": "text", "x": 305, "y": 140, "w": 100, "h": 20, "text": "Проект планировки территории", "size": 14, "font": "PT Serif", "bold": True, "align": "center"},
        {"id": "picture-1", "kind": "picture", "x": 305, "y": 165, "w": 40, "h": 20, "src": png(), "rotation": 15},
        {"id": "north-1", "kind": "north", "x": 30, "y": 14, "w": 10, "h": 16, "map": "map-1"},
        {"id": "scalebar-1", "kind": "scalebar", "x": 30, "y": 220, "w": 60, "h": 8, "map": "map-1"},
        {"id": "table-1", "kind": "table", "x": 350, "y": 165, "w": 55, "h": 30, "rows": 3, "cols": 3, "title": "ТЭП", "frame": {"on": True, "width": .25}},
        {"id": "ellipse-1", "kind": "ellipse", "x": 100, "y": 100, "w": 20, "h": 10, "bg": {"on": True, "color": "#ffee00"}, "frame": {"on": True, "width": .3}, "opacity": .5},
        {"id": "line-1", "kind": "line", "x": 100, "y": 120, "w": 30, "h": 4, "arrow": True, "frame": {"on": True, "color": "#0050c8", "width": .5}},
        {"id": "text-hidden", "kind": "text", "x": 0, "y": 0, "w": 50, "h": 10, "text": "Скрытая надпись", "hidden": True},
    ]
    sheet = {"format": "A3", "orient": "L", "stamp": True, "title": "Схема планировочной организации", "blocks": blocks}
    sheet.update(sheet_kw)
    maps = {"map-1": {"layers": [{"title": "Здания", "features": [{"g": square(.0005), "fill": "#cbc6be", "stroke": "#4d4d4d", "w": 1, "a": 1}]}]}}
    return {"sheet": sheet, "meta": {"object": "Тестовый объект", "code": "ППТ-01"}, "maps": maps}


class LayoutPrint(unittest.TestCase):
    def test_sheet_renders_to_pdf_with_stamp_and_all_elements(self):
        pdf = layout_io.render_pdf(spec(), S.REDLN, S.LGR_DASH)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"/DCTDecode", pdf)                              # картинка листа встроена JPEG

    def test_svg_has_texts_of_elements_and_stamp_but_not_hidden_ones(self):
        svg = layout_io.render_page_svg(spec(), S.REDLN, S.LGR_DASH)
        for t in ("Условные обозначения", "Здания", "Проект планировки", "ТЭП", "1:2 000", "Схема планировочной организации", "Тестовый объект"):
            self.assertIn(t, svg)
        self.assertNotIn("Скрытая надпись", svg)
        self.assertIn('width="420mm" height="297mm"', svg)

    def test_map_is_clipped_to_its_block_and_drawn_at_its_scale(self):
        w, h, ops = layout_io.build_page(spec(), S.REDLN, S.LGR_DASH)
        clip = next(o for o in ops if o["op"] == "clip")
        self.assertEqual(tuple(clip["rect"]), (25, 10, 270, 224))
        # здание 2 × 0,0005° долготы ≈ 62,6 м; в 1:2 000 — около 31 мм на листе
        fills = [o for o in ops if o["op"] == "path" and o.get("closed") and o.get("fill") and abs(o["fill"][0] - 0xcb / 255) < .02]
        xs = [x for x, _ in fills[0]["rings"][0]]
        self.assertAlmostEqual(max(xs) - min(xs), 2 * .0005 * 111320 * 0.5622 / 2, delta=1.0)
        cx = (max(xs) + min(xs)) / 2
        self.assertAlmostEqual(cx, 25 + 270 / 2, delta=.5)               # центр карты — в середине блока

    def test_scalebar_follows_the_map_scale(self):
        s = spec()
        s["sheet"]["blocks"][0]["scale"] = 10000
        svg = layout_io.render_page_svg(s, S.REDLN, S.LGR_DASH)
        self.assertIn("1:10 000", svg)
        self.assertEqual(layout_io.scalebar_step(60, 10000), 100)
        self.assertEqual(layout_io.fmt_m(1500), "1,5 км")

    def test_rotation_and_opacity_are_applied(self):
        w, h, ops = layout_io.build_page(spec(), S.REDLN, S.LGR_DASH)
        img = next(o for o in ops if o["op"] == "image")
        self.assertIn("quad", img)                                     # повёрнутая картинка — параллелограммом
        yellow = next(o for o in ops if o["op"] == "path" and o.get("fill") and o["fill"][2] < .6 and o["fill"][0] > .9)
        self.assertAlmostEqual(yellow["fill"][2], .5, delta=.02)       # жёлтый на 50 % — бледнее

    def test_all_sheets_print_as_one_pdf_with_sheet_numbers_in_the_stamp(self):
        one = spec()
        two = spec(title="Второй лист")
        both = {"meta": one["meta"], "sheets": [{"sheet": one["sheet"], "maps": one["maps"]}, {"sheet": two["sheet"], "maps": {}}]}
        pages = layout_io.build_pages(both, S.REDLN, S.LGR_DASH)
        self.assertEqual(len(pages), 2)
        texts = lambda ops: [o["text"] for o in ops if o["op"] == "text"]
        self.assertIn("Второй лист", texts(pages[1][2]))
        self.assertIn("2", texts(pages[1][2]))                          # «Лист 2» в штампе
        pdf = layout_io.render_pdf(both, S.REDLN, S.LGR_DASH)
        self.assertEqual(pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages"), 2)
        with self.assertRaises(ValueError):
            layout_io.render_pdf({"sheets": []}, S.REDLN, S.LGR_DASH)

    def test_single_sheet_keeps_its_number(self):
        s = {**spec(), "page": {"page_no": 3, "page_total": 4}}
        texts = [o["text"] for o in layout_io.build_page(s, S.REDLN, S.LGR_DASH)[2] if o["op"] == "text"]
        self.assertIn("3", texts)
        self.assertIn("4", texts)

    def test_sheet_without_stamp_has_thin_border_and_no_stamp(self):
        svg = layout_io.render_page_svg(spec(stamp=False, format="A4", orient="P"), S.REDLN, S.LGR_DASH)
        self.assertIn('width="210mm" height="297mm"', svg)
        self.assertNotIn("Тестовый объект", svg)

    def test_map_without_place_is_a_placeholder_and_map_svg_needs_center(self):
        s = spec()
        s["sheet"]["blocks"][0].pop("center")
        self.assertIn("укажите место", layout_io.render_page_svg(s, S.REDLN, S.LGR_DASH))
        with self.assertRaises(ValueError):
            layout_io.map_svg({"block": {"w": 100, "h": 80, "scale": 2000}}, S.REDLN, S.LGR_DASH)

    def test_map_svg_is_the_block_alone(self):
        svg = layout_io.map_svg({"block": {"w": 100, "h": 80, "scale": 2000, "center": [LON, LAT]}, "layers": spec()["maps"]["map-1"]["layers"]}, S.REDLN, S.LGR_DASH)
        self.assertTrue(re.search(r'width="100(\.0)?mm" height="80(\.0)?mm"', svg))
        self.assertIn("<path", svg)
        self.assertNotIn("М 1:", svg)                                  # своей линейки и стрелки у карты нет — они элементы листа

    def test_bad_values_do_not_break_the_sheet(self):
        s = spec()
        s["sheet"]["blocks"].append({"id": "x", "kind": "text", "x": "a", "w": None, "text": 5, "size": "big"})
        s["sheet"]["blocks"].append("not a block")
        s["sheet"]["blocks"].append({"id": "p", "kind": "picture", "src": "data:image/png;base64,!!!"})
        self.assertTrue(layout_io.render_pdf(s, S.REDLN, S.LGR_DASH).startswith(b"%PDF"))


class LayoutsInProject(unittest.TestCase):
    """Листы макета живут в файле проекта последним ключом layouts; запись рабочей страницы (без этого ключа) их не стирает."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old, S.PROJECTS = S.PROJECTS, Path(self.tmp.name) / "p"

    def tearDown(self):
        S.PROJECTS = self.old
        self.tmp.cleanup()

    def read(self, name="Проект"):
        return json.loads(S.project_path(name).read_bytes())

    def test_page_save_keeps_layouts_and_new_interface_save_replaces_them(self):
        page = {"format": "grado2", "name": "Проект", "layers": [{"key": "a"}], "data": {"a": {"fc": {"features": []}}}}
        sheets = [{"id": "s1", "format": "A3", "title": "Лист 1", "blocks": [{"id": "m", "kind": "map"}]}]
        S.save_project("Проект", json.dumps({**page, "layouts": sheets}, ensure_ascii=False, separators=(",", ":")).encode())   # новый интерфейс (JSON.stringify): листы последним ключом
        self.assertEqual(self.read()["layouts"], sheets)
        page["layers"].append({"key": "b"})                            # рабочая страница сохраняет — о листах не знает
        S.save_project("Проект", json.dumps(page, ensure_ascii=False, indent=1).encode())
        self.assertEqual(self.read()["layouts"], sheets)
        self.assertEqual(len(self.read()["layers"]), 2)
        S.save_project("Проект", json.dumps({**page, "layouts": []}, separators=(",", ":")).encode())   # листы удалены в новом интерфейсе
        self.assertEqual(self.read()["layouts"], [])
        self.assertEqual(len(self.read()["layers"]), 2)

    def test_split_and_join_are_inverse_and_ignore_lookalikes(self):
        body = b'{"a": 1, "note": ",\\"layouts\\": in a string"}'
        self.assertEqual(S.split_layouts(body), (body, None))
        joined = S.with_layouts(b'{"a": 1}', b'[{"id": "x"}]')
        self.assertEqual(json.loads(joined), {"a": 1, "layouts": [{"id": "x"}]})
        self.assertEqual(S.split_layouts(joined), (b'{"a": 1}', b'[{"id": "x"}]'))
        self.assertEqual(json.loads(S.with_layouts(b"{}", b"[]")), {"layouts": []})


if __name__ == "__main__":
    unittest.main()
