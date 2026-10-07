"""Проверяет разбор типов линий .LIN и фигур .SHX (AutoCAD) и сопоставление кодов ЛГР.

Запуск: python -m unittest discover -s core/render/tests (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import json
import unittest
from pathlib import Path

from grado_render.acad_lin import (linetypes_for_codes, missing_codes, parse_line_codes,
                                   read_lin, read_shx)

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "docs/standards/redln97"


class AcadLin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lin = read_lin((SRC / "REDLN97.LIN").read_bytes().decode("cp866"))
        cls.shx = read_shx((SRC / "RED_LNS.SHX").read_bytes())

    def test_catalog_sizes(self):
        self.assertEqual(len(self.lin), 500)
        self.assertEqual(len(self.shx), 38)
        used = {e["shape"].upper() for lt in self.lin.values() for e in lt["pattern"] if "shape" in e}
        self.assertTrue(used <= {n.upper() for n in self.shx})   # every shape referenced by LIN is decoded

    def test_water_protection_zone_matches_qml(self):
        # QML of the portal: code 16 — dash 6 m, gap 4 m, chevron; LIN: 3,-4,3 around the shape
        p = self.lin["L00s16b"]["pattern"]
        self.assertEqual([e.get("d") for e in p if "d" in e], [3.0, -4.0, 3.0, 3.0, -4.0, 3.0])
        self.assertEqual(self.lin["L00s16b"]["length"], 20.0)

    def test_triangle_shape_decoded(self):
        self.assertEqual(self.shx["TRNF"]["no"], 163)
        self.assertEqual(self.shx["TRNF"]["paths"][0][:3], [[0.0, 0.0], [0.5, 1.0], [1.0, 0.0]])

    def test_codes_to_linetypes(self):
        self.assertEqual(parse_line_codes("1,-18,-29"), [(1, 1), (18, -1), (29, -1)])
        self.assertEqual(linetypes_for_codes([(16, 1)], self.lin), ["L00s16b"])     # «+» → right → b
        self.assertEqual(linetypes_for_codes([(16, -1)], self.lin), ["L00s16t"])
        self.assertEqual(linetypes_for_codes([(1, 1), (18, -1)], self.lin), ["L01s18t"])  # on the red line
        self.assertEqual(linetypes_for_codes([(7, 1), (8, 1)], self.lin), ["L07b08b"])   # pair without carrier
        self.assertEqual(missing_codes([(1, 1), (29, -1)], self.lin), [(29, -1)])


if __name__ == "__main__":
    unittest.main()
