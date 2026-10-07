"""Мост от геометрии проекта к расчёту ТЭП (grado_model.tep_bridge): площади входов и движок КРТ.

Запуск: python -m unittest discover -s core/model/tests (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import sys
import tempfile
import unittest
from pathlib import Path

from grado_model import Project
from grado_model import tep_bridge

sys.path.insert(0, str(Path(__file__).parents[2] / "compute"))
from grado_compute.engine import Engine  # noqa: E402

PRESET = Path(__file__).parents[2] / "compute" / "grado_compute" / "presets" / "moscow_krt.json"


def rect(x0, y0, w, h):
    return {"type": "Polygon", "coordinates": [[
        [x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h], [x0, y0]]]}


class TestTepBridge(unittest.TestCase):
    """Сквозной сценарий: геометрия проекта → входы ТЭП → расчёт.

    Граница 500×300 м = 15 га, ограничения 200×100 м = 2 га.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Project.create(Path(self.tmp.name) / "t.grado", "Мост")
        self.p.add_layer("terr.boundary").add_feature(rect(413000, 6178000, 500, 300))
        self.p.add_layer("terr.restrict").add_feature(rect(413000, 6178000, 200, 100))

    def tearDown(self):
        self.p.close()
        self.tmp.cleanup()

    def test_collect_inputs(self):
        inputs = tep_bridge.collect_inputs(self.p)
        self.assertAlmostEqual(inputs["terr_area"], 15.0)
        self.assertAlmostEqual(inputs["restrict_area"], 2.0)

    def test_engine_integration(self):
        engine = Engine.from_file(PRESET)
        applied = tep_bridge.apply_to_engine(self.p, engine)
        self.assertEqual(set(applied), {"terr_area", "restrict_area"})
        self.assertAlmostEqual(engine.value("calc_area"), 13.0)
        # плотность 25 по умолчанию: СПП = 25 × 13 = 325 тыс. м²
        self.assertAlmostEqual(engine.value("spp"), 325.0)
        self.assertGreater(engine.value("population"), 0)

    def test_restrict_layer_grows(self):
        self.p.layer("terr.restrict").add_feature(rect(413300, 6178200, 100, 100))
        inputs = tep_bridge.collect_inputs(self.p)
        self.assertAlmostEqual(inputs["restrict_area"], 3.0)


if __name__ == "__main__":
    unittest.main()
