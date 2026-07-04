import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401
from grado_model import Project
from grado_reactive import Session, JournalError


def rect(x0, y0, w, h):
    return {"type": "Polygon", "coordinates": [[
        [x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h], [x0, y0]]]}


class SessionBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "t.grado"
        self.p = Project.create(self.path, "Тест")
        self.p.add_layer("terr.boundary")
        self.p.add_layer("terr.restrict")
        self.s = Session(self.p)

    def tearDown(self):
        self.p.close()
        self.tmp.cleanup()


class TestSession(SessionBase):
    def test_insert_journaled(self):
        fid = self.s.insert_feature("terr.boundary", rect(0, 0, 500, 300),
                                    attrs={"name": "Граница"})
        self.assertEqual(fid, 1)
        log = self.s.log()
        self.assertEqual(len(log), 1)
        self.assertTrue(log[0]["applied"])
        self.assertAlmostEqual(self.p.layer("terr.boundary").area_ha(), 15.0)

    def test_update_undo_redo(self):
        fid = self.s.insert_feature("terr.restrict", rect(0, 0, 200, 100),
                                    attrs={"kind": "СЗЗ"})
        self.s.update_feature("terr.restrict", fid, geom=rect(0, 0, 100, 100),
                              attrs={"kind": "охранная зона"})
        layer = self.p.layer("terr.restrict")
        self.assertAlmostEqual(layer.area_ha(), 1.0)
        self.assertEqual(layer.get_feature(fid)["attrs"]["kind"], "охранная зона")

        title = self.s.undo()
        self.assertIn("правка", title)
        self.assertAlmostEqual(layer.area_ha(), 2.0)
        self.assertEqual(layer.get_feature(fid)["attrs"]["kind"], "СЗЗ")

        self.s.redo()
        self.assertAlmostEqual(layer.area_ha(), 1.0)

    def test_style_id_survives_undo_redo(self):
        # per-object style_id должен переживать реплей дельт (MODEL-01)
        fid = self.s.insert_feature("terr.restrict", rect(0, 0, 200, 100),
                                    attrs={"kind": "СЗЗ"}, style_id="restrict.accent")
        layer = self.p.layer("terr.restrict")
        self.assertEqual(layer.get_feature(fid)["style_id"], "restrict.accent")
        self.s.update_feature("terr.restrict", fid, geom=rect(0, 0, 100, 100))
        self.assertEqual(layer.get_feature(fid)["style_id"], "restrict.accent",
                         "правка геометрии не теряет стиль")
        self.s.undo()
        self.assertEqual(layer.get_feature(fid)["style_id"], "restrict.accent")
        self.s.undo()
        self.assertIsNone(layer.get_feature(fid))
        self.s.redo()
        self.assertEqual(layer.get_feature(fid)["style_id"], "restrict.accent",
                         "redo вставки восстанавливает стиль")

    def test_delete_undo_restores_fid_and_provenance(self):
        fid = self.s.insert_feature("terr.restrict", rect(0, 0, 200, 100),
                                    attrs={"kind": "СЗЗ"}, source="nspd",
                                    source_doc="77:00-6.1")
        self.s.delete_feature("terr.restrict", fid)
        layer = self.p.layer("terr.restrict")
        self.assertEqual(layer.count(), 0)
        self.s.undo()
        f = layer.get_feature(fid)
        self.assertIsNotNone(f, "объект должен вернуться с тем же id")
        self.assertEqual((f["source"], f["source_doc"]), ("nspd", "77:00-6.1"))

    def test_undo_at_bottom(self):
        self.assertFalse(self.s.can_undo())
        self.assertIsNone(self.s.undo())

    def test_commit_truncates_redo(self):
        self.s.insert_feature("terr.restrict", rect(0, 0, 100, 100))
        self.s.insert_feature("terr.restrict", rect(200, 0, 100, 100))
        self.s.undo()
        self.assertTrue(self.s.can_redo())
        self.s.insert_feature("terr.restrict", rect(400, 0, 100, 100))
        self.assertFalse(self.s.can_redo(), "новая запись отсекает redo-хвост")
        self.assertEqual(len(self.s.log()), 2)

    def test_persistence_across_reopen(self):
        self.s.insert_feature("terr.boundary", rect(0, 0, 500, 300))
        self.p.close()
        self.p = Project.open(self.path)
        s2 = Session(self.p)
        self.assertTrue(s2.can_undo())
        s2.undo()
        self.assertEqual(self.p.layer("terr.boundary").count(), 0)

    def test_update_missing_feature(self):
        with self.assertRaises(JournalError):
            self.s.update_feature("terr.restrict", 99, attrs={"kind": "х"})

    def test_bulk_single_entry_and_atomic(self):
        with self.s.bulk("импорт 3 объектов"):
            for i in range(3):
                self.s.insert_feature("terr.restrict", rect(i * 200, 0, 100, 100))
        self.assertEqual(len(self.s.log()), 1)
        self.s.undo()
        self.assertEqual(self.p.layer("terr.restrict").count(), 0)

    def test_bulk_rolls_back_on_error(self):
        try:
            with self.s.bulk("сломанный импорт"):
                self.s.insert_feature("terr.restrict", rect(0, 0, 100, 100))
                raise RuntimeError("обрыв")
        except RuntimeError:
            pass
        self.assertEqual(self.p.layer("terr.restrict").count(), 0,
                         "применённые дельты пакета откатились")
        self.assertEqual(self.s.log(), [], "запись в журнал не попала")

    def test_subscribers_notified(self):
        seen = []
        self.s.subscribe(seen.append)
        self.s.insert_feature("terr.boundary", rect(0, 0, 10, 10))
        self.s.undo()
        self.assertEqual(seen, [{"terr.boundary"}, {"terr.boundary"}])


if __name__ == "__main__":
    unittest.main()
