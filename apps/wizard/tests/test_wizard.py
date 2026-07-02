import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from grado_wizard import TerritoryWizard, demo_boundary, ring_area_ha  # noqa: E402
from grado_layout import document_pages_ops  # noqa: E402


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
