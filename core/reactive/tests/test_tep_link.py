import tempfile
import unittest
from pathlib import Path

import _paths
from grado_compute.engine import Engine
from grado_model import Project
from grado_reactive import Session, TepLink


def rect(x0, y0, w, h):
    return {"type": "Polygon", "coordinates": [[
        [x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h], [x0, y0]]]}


class TestTepLink(unittest.TestCase):
    """Правка геометрии → журнал → пересчёт ТЭП. Без ручного ввода площадей."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Project.create(Path(self.tmp.name) / "t.grado", "ТЭП")
        self.p.add_layer("terr.boundary")
        self.p.add_layer("terr.restrict")
        self.s = Session(self.p)
        self.s.insert_feature("terr.boundary", rect(0, 0, 500, 300))   # 15 га
        self.rid = self.s.insert_feature("terr.restrict", rect(0, 0, 200, 100))  # 2 га
        self.engine = Engine.from_file(_paths.PRESET)
        self.link = TepLink(self.s, self.engine)

    def tearDown(self):
        self.p.close()
        self.tmp.cleanup()

    def test_initial_sync(self):
        self.assertAlmostEqual(self.engine.value("terr_area"), 15.0)
        self.assertAlmostEqual(self.engine.value("restrict_area"), 2.0)
        self.assertAlmostEqual(self.engine.value("calc_area"), 13.0)
        self.assertEqual(self.engine.value("population"), 4814)

    def test_edit_recomputes(self):
        self.s.update_feature("terr.restrict", self.rid, geom=rect(0, 0, 100, 100))
        self.assertAlmostEqual(self.engine.value("calc_area"), 14.0)
        self.assertEqual(self.engine.value("population"), 5184)

    def test_undo_recomputes_back(self):
        self.s.update_feature("terr.restrict", self.rid, geom=rect(0, 0, 100, 100))
        self.s.undo()
        self.assertAlmostEqual(self.engine.value("calc_area"), 13.0)
        self.assertEqual(self.engine.value("population"), 4814)

    def test_delete_gives_zero_not_stale(self):
        self.s.delete_feature("terr.restrict", self.rid)
        self.assertAlmostEqual(self.engine.value("restrict_area"), 0.0)
        self.assertEqual(self.engine.value("population"), 5555)

    def test_branch_switch_recomputes(self):
        self.s.create_branch("вариант-Б")
        self.s.checkout("вариант-Б")
        self.s.insert_feature("terr.restrict", rect(300, 0, 100, 100))  # 3 га
        self.assertEqual(self.engine.value("population"), 4444)
        self.s.checkout("main")
        self.assertEqual(self.engine.value("population"), 4814)

    def test_unrelated_layer_does_not_resync(self):
        self.p.add_layer("pp.red_line")
        before = dict(self.engine.eval_counts)
        self.s.insert_feature("pp.red_line",
                              {"type": "LineString", "coordinates": [[0, 0], [10, 0]]})
        self.assertEqual(self.engine.eval_counts, before,
                         "красная линия не входит в ТЭП — пересчёта нет")


if __name__ == "__main__":
    unittest.main()
