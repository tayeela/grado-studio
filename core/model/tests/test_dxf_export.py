"""Выгрузка проекта в DXF R12 (grado_model.dxf_export): структура, слои, cp1251, дыры полигонов.

Запуск: python -m unittest discover -s core/model/tests (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import tempfile
import unittest
from pathlib import Path

from grado_model.__main__ import make_demo
from grado_model.dxf_export import project_to_dxf


class TestDxfExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.project = make_demo(Path(cls.tmp.name) / "d.grado")
        cls.dxf = project_to_dxf(cls.project)
        cls.text = cls.dxf.decode("cp1251")

    @classmethod
    def tearDownClass(cls):
        cls.project.close()
        cls.tmp.cleanup()

    def test_r12_structure(self):
        self.assertTrue(self.text.startswith("0\nSECTION"))
        self.assertIn("AC1009", self.text)
        self.assertIn("ANSI_1251", self.text)
        self.assertTrue(self.text.rstrip().endswith("EOF"))
        self.assertEqual(self.text.count("0\nSECTION"), 3)  # HEADER/TABLES/ENTITIES
        self.assertEqual(self.text.count("0\nENDSEC"), 3)

    def test_layers_and_entities(self):
        for layer in ("GRANICA_TERRITORII", "KRASNYE_LINII", "ZDANIYA",
                      "SOC_OBEKTY", "OGRANICHENIYA"):
            self.assertIn(layer, self.text)
        # полилинии закрыты для полигонов: у каждого POLYLINE есть SEQEND
        self.assertEqual(self.text.count("0\nPOLYLINE"), self.text.count("0\nSEQEND"))
        # демо-проект: граница + ограничение + здание (полигоны) + красная линия
        self.assertEqual(self.text.count("0\nPOLYLINE"), 4)
        self.assertIn("0\nPOINT", self.text, "соцобъект — точка")

    def test_cyrillic_labels_cp1251(self):
        self.assertIn("Демо-территория", self.text, "подпись читается из cp1251")

    def test_coordinates_in_project_crs(self):
        self.assertIn("413", self.text.split("ENTITIES")[1][:2000],
                      "координаты в СК проекта (UTM), не локальные")


if __name__ == "__main__":
    unittest.main()


class TestDxfHoles(unittest.TestCase):
    def test_polygon_holes_exported_as_closed_polylines(self):
        # Прежде выгружалось только внешнее кольцо (ring = poly[0]) — выколотый
        # полигон приходил в DXF сплошным, расходясь с .grado и печатью.
        import tempfile
        from pathlib import Path
        from grado_model import Project
        from grado_model.dxf_export import project_to_dxf
        with tempfile.TemporaryDirectory() as tmp:
            p = Project.create(Path(tmp) / "h.grado", "Дыры")
            p.add_layer("tp.func_zone").add_feature(
                {"type": "Polygon", "coordinates": [
                    [[0, 0], [100, 0], [100, 80], [0, 80], [0, 0]],
                    [[30, 20], [70, 20], [70, 60], [30, 60], [30, 20]],
                ]}, attrs={"zone_title": "с дырой"})
            dxf = project_to_dxf(p).decode("cp1251")
            p.close()
        # обе полилинии замкнуты: вершины внешнего кольца и дыры присутствуют
        self.assertIn("100.0000", dxf, "внешнее кольцо в DXF")
        self.assertIn("30.0000", dxf, "кольцо дыры в DXF")
        self.assertIn("70.0000", dxf, "кольцо дыры в DXF")
        # подпись зоны — одна (не дублируется на кольцо дыры)
        self.assertEqual(dxf.count("с дырой"), 1)
