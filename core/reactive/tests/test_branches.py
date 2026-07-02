import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401
from grado_model import Project
from grado_reactive import Session, JournalError


def rect(x0, y0, w, h):
    return {"type": "Polygon", "coordinates": [[
        [x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h], [x0, y0]]]}


class TestBranches(unittest.TestCase):
    """Вариант концепции = ветка журнала."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Project.create(Path(self.tmp.name) / "t.grado", "Ветки")
        self.p.add_layer("terr.restrict")
        self.s = Session(self.p)
        self.s.insert_feature("terr.restrict", rect(0, 0, 200, 100))  # 2 га

    def tearDown(self):
        self.p.close()
        self.tmp.cleanup()

    def area(self):
        return self.p.layer("terr.restrict").area_ha()

    def test_branch_switch(self):
        self.s.create_branch("вариант-Б")
        self.s.checkout("вариант-Б")
        self.s.insert_feature("terr.restrict", rect(300, 0, 100, 100))  # +1 га
        self.assertAlmostEqual(self.area(), 3.0)

        self.s.checkout("main")
        self.assertAlmostEqual(self.area(), 2.0, msg="main не видит правок ветки")

        self.s.checkout("вариант-Б")
        self.assertAlmostEqual(self.area(), 3.0, msg="ветка восстановилась из журнала")

    def test_main_advances_after_fork(self):
        self.s.create_branch("вариант-Б")
        self.s.checkout("вариант-Б")
        self.s.insert_feature("terr.restrict", rect(300, 0, 100, 100))
        self.s.checkout("main")
        self.s.insert_feature("terr.restrict", rect(500, 0, 50, 100))  # +0.5 га
        self.assertAlmostEqual(self.area(), 2.5)

        self.s.checkout("вариант-Б")
        self.assertAlmostEqual(self.area(), 3.0, msg="ветка растёт от своей базы, не от новой main")

        self.s.checkout("main")
        self.assertAlmostEqual(self.area(), 2.5)

    def test_branch_to_branch(self):
        self.s.create_branch("Б")
        self.s.insert_feature("terr.restrict", rect(500, 0, 50, 100))  # main: 2.5
        self.s.create_branch("В")
        self.s.checkout("Б")
        self.assertAlmostEqual(self.area(), 2.0)
        self.s.checkout("В")
        self.assertAlmostEqual(self.area(), 2.5)

    def test_undo_confined_to_branch(self):
        self.s.create_branch("Б")
        self.s.checkout("Б")
        self.assertFalse(self.s.can_undo(), "undo не пересекает базу ветки")

    def test_orphan_guard(self):
        self.s.insert_feature("terr.restrict", rect(300, 0, 100, 100))
        self.s.create_branch("Б")  # база = 2-я запись main
        self.s.undo()  # head main ниже базы Б
        with self.assertRaises(JournalError):
            self.s.insert_feature("terr.restrict", rect(500, 0, 50, 100))

    def test_create_branch_only_from_main(self):
        self.s.create_branch("Б")
        self.s.checkout("Б")
        with self.assertRaises(JournalError):
            self.s.create_branch("В")

    def test_checkout_unknown(self):
        with self.assertRaises(JournalError):
            self.s.checkout("нет-такой")


if __name__ == "__main__":
    unittest.main()
