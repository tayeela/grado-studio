"""Листы альбома (grado_layout): штамп, карта с легендой, таблица, PDF и SVG, демо-альбом.

Запуск: python -m unittest discover -s core/layout/tests (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import sys
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).parents[2]
for mod in ("model", "compute", "reactive", "render", "geom", "layout"):
    p = str(CORE / mod)
    if p not in sys.path:
        sys.path.insert(0, p)

from grado_layout import (A3_LANDSCAPE, Document, LegendFrame, MapFrame,  # noqa: E402
                          Page, PageBorder, StampFrame, TableFrame,
                          document_pages_ops, render_document_pdf,
                          render_page_svg)
from grado_model import Project  # noqa: E402


def make_project(tmp):
    p = Project.create(Path(tmp) / "t.grado", "Тест-альбом")
    p.add_layer("tp.func_zone").add_feature(
        {"type": "Polygon", "coordinates": [[
            [413000, 6178000], [413200, 6178000], [413200, 6178150],
            [413000, 6178150], [413000, 6178000]]]},
        attrs={"zone_title": "Ж-1"})
    return p


def make_doc(page_frames):
    page = Page(A3_LANDSCAPE)
    page.frames = [PageBorder(page)] + page_frames(page) + [StampFrame(page)]
    doc = Document("Тест", meta={"code": "ШИФР-01", "object": "Объект",
                                 "stage": "АГК", "org": "Организация"})
    doc.pages = [page]
    doc.sheet_titles = ["Лист-1"]
    return doc


class TestLayout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = make_project(self.tmp.name)

    def tearDown(self):
        self.project.close()
        self.tmp.cleanup()

    def _texts(self, ops):
        return [o["text"] for o in ops if o["op"] == "text"]

    def test_stamp_fields(self):
        doc = make_doc(lambda page: [])
        (w, h, ops), = document_pages_ops(doc, self.project)
        texts = self._texts(ops)
        for expected in ("ШИФР-01", "Объект", "Организация", "АГК",
                         "Лист-1", "1"):
            self.assertIn(expected, texts)
        self.assertEqual((w, h), A3_LANDSCAPE)

    def test_map_and_legend(self):
        doc = make_doc(lambda page: [
            MapFrame((30, 15, 200, 150), scale=2000),
            LegendFrame((250, 15, 120, 80))])
        (_, _, ops), = document_pages_ops(doc, self.project)
        texts = self._texts(ops)
        self.assertIn("Ж-1", texts, "подпись зоны на карте")
        self.assertIn("Условные обозначения", texts)
        self.assertIn("Функциональная зона", texts, "легенда по слоям проекта")
        self.assertIn("М 1:2000", texts)
        self.assertTrue(any(o["op"] == "clip" for o in ops))

    def test_table(self):
        rows = [("Площадь", "15", "га"), ("Население", "4814", "чел")]
        doc = make_doc(lambda page: [
            TableFrame((30, 20, 220, 100),
                       [("Показатель", 150, "left"), ("Значение", 35, "right"),
                        ("Ед.", 30, "left")], rows, title="ТЭП")])
        (_, _, ops), = document_pages_ops(doc, self.project)
        texts = self._texts(ops)
        for cell in ("ТЭП", "Показатель", "Площадь", "4814", "чел"):
            self.assertIn(cell, texts)

    def test_pdf_and_svg_from_same_document(self):
        doc = make_doc(lambda page: [MapFrame((30, 15, 200, 150), scale=2000)])
        pdf = render_document_pdf(doc, self.project)
        svg = render_page_svg(doc, self.project, 0)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"/Count 1", pdf)
        self.assertIn("Ж-1", svg)
        self.assertIn("clip-path", svg)

    def test_demo_album_builds(self):
        from grado_layout.__main__ import build_album, build_demo_project
        from grado_compute.engine import Engine
        from grado_model.tep_bridge import apply_to_engine
        preset = CORE / "compute" / "grado_compute" / "presets" / "moscow_krt.json"
        with tempfile.TemporaryDirectory() as tmp:
            project = build_demo_project(Path(tmp) / "d.grado")
            engine = Engine.from_file(preset)
            inputs = apply_to_engine(project, engine)
            self.assertAlmostEqual(inputs["terr_area"], 15.0)
            self.assertAlmostEqual(inputs["restrict_area"], 2.0)
            doc = build_album(project, engine)
            pdf = render_document_pdf(doc, project, engine=engine)
            project.close()
        self.assertIn(b"/Count 2", pdf)
        self.assertGreater(len(pdf), 10000)


if __name__ == "__main__":
    unittest.main()
