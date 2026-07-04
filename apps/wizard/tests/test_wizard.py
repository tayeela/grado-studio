import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from grado_wizard import TerritoryWizard, demo_boundary, ring_area_ha  # noqa: E402
from grado_wizard.sheets import _source_table, layerset_layers  # noqa: E402
from grado_layout import document_pages_ops  # noqa: E402
from grado_model import Project  # noqa: E402
from grado_render import StyleSet  # noqa: E402

_Z = {"type": "Polygon", "coordinates": [[
    [413000, 6178000], [413200, 6178000], [413200, 6178150],
    [413000, 6178150], [413000, 6178000]]]}
_B = {"type": "Polygon", "coordinates": [[
    [413000, 6178000], [413500, 6178000], [413500, 6178300],
    [413000, 6178300], [413000, 6178000]]]}


class TestSameClassLayers(unittest.TestCase):
    """MODEL-01: два слоя одного класса — источники/легенда без дублей,
    счётчики берутся с нужного слоя (регресс на layer(code) LIMIT 1)."""

    def _project(self, tmp):
        p = Project.create(Path(tmp) / "sc.grado", "Два слоя")
        p.add_layer("terr.boundary", layer_id="project.territory.boundary")
        p.add_layer("tp.func_zone", layer_id="project.tp.func_zone",
                    title="ФЗ проектные")
        p.add_layer("tp.func_zone", layer_id="source.fgistp.func_zones",
                    stage="existing", source_kind="fgistp", title="ФГИС ТП: зоны")
        p.layer_by_id("project.territory.boundary").add_feature(_B, attrs={"name": "Гр"})
        p.layer_by_id("project.tp.func_zone").add_feature(_Z, attrs={"zone_title": "Ж-пр"})
        p.layer_by_id("source.fgistp.func_zones").add_feature(_Z, attrs={"zone_title": "Ж1"})
        p.layer_by_id("source.fgistp.func_zones").add_feature(_Z, attrs={"zone_title": "Ж2"})
        return p

    def test_layerset_no_duplicate_layer_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._project(tmp)
            try:
                lids = layerset_layers(p, "existing_position")
            finally:
                p.close()
        self.assertEqual(len(lids), len(set(lids)), "нет дублей layer_id")
        self.assertIn("project.tp.func_zone", lids)
        self.assertIn("source.fgistp.func_zones", lids)

    def test_source_table_per_layer_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._project(tmp)
            try:
                lids = layerset_layers(p, "existing_position")
                rows = _source_table(p, lids, (0, 0, 106, 100)).rows
            finally:
                p.close()
        counts = {name: cnt for name, cnt, _ in rows}
        self.assertEqual(counts.get("ФЗ проектные"), "1", "счётчик проектного слоя")
        self.assertEqual(counts.get("ФГИС ТП: зоны"), "2", "счётчик исходного слоя")
        titles = [name for name, _, _ in rows]
        self.assertEqual(len(titles), len(set(titles)), "нет дублирующих строк")

    def test_legend_entries_both_same_class_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._project(tmp)
            try:
                titles = [t for _, t, _ in StyleSet().legend_entries(p)]
            finally:
                p.close()
        # оба слоя класса tp.func_zone в легенде, ни один не потерян
        self.assertIn("ФЗ проектные", titles)
        self.assertIn("ФГИС ТП: зоны", titles)


class TestWizard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.wizard = TerritoryWizard("Тестовая концепция\nразвития территории")
        cls.project, cls.engine, cls.doc = cls.wizard.run(
            Path(cls.tmp.name) / "t.grado")

    @classmethod
    def tearDownClass(cls):
        cls.project.close()
        cls.tmp.cleanup()

    def test_tep_from_geometry(self):
        expected = ring_area_ha(demo_boundary())
        self.assertAlmostEqual(self.engine.value("terr_area"), expected, places=6)
        self.assertGreater(self.engine.value("restrict_area"), 0)
        self.assertGreater(self.engine.value("population"), 0)

    def test_album_structure(self):
        self.assertEqual(len(self.doc.pages), 5)
        pages = document_pages_ops(self.doc, self.project,
                                   styles=self.doc.styles, engine=self.engine)
        texts = ["\n".join(o["text"] for o in ops if o["op"] == "text")
                 for _, _, ops in pages]
        self.assertIn("ТЕСТОВАЯ КОНЦЕПЦИЯ", texts[0], "титул капсом")
        self.assertIn("Расположение рассматриваемой", texts[1])
        self.assertIn("Опорный план.", texts[2])
        self.assertIn("архитектурно-планировочной", texts[3])
        self.assertIn("технико-экономические", texts[4])

    def test_page_numbers(self):
        pages = document_pages_ops(self.doc, self.project,
                                   styles=self.doc.styles, engine=self.engine)
        for expected_no, (_, _, ops) in zip(["2", "3", "4", "5"], pages[1:]):
            texts = [o["text"] for o in ops if o["op"] == "text"]
            self.assertIn(expected_no, texts)

    def test_callout_values_live_from_engine(self):
        pages = document_pages_ops(self.doc, self.project,
                                   styles=self.doc.styles, engine=self.engine)
        apo_texts = "\n".join(o["text"] for o in pages[3][2] if o["op"] == "text")
        self.assertIn(str(self.engine.display("spp_zh")), apo_texts)
        self.assertIn(str(self.engine.display("population")), apo_texts)

    def test_pdf_renders(self):
        pdf = self.wizard.render_pdf(self.project, self.engine, self.doc)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"/Count 5", pdf)


if __name__ == "__main__":
    unittest.main()
