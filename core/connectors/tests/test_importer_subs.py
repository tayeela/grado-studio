"""Проверяет импорт снимка в проект (importer) и подписки на изменения источника (Subscriptions).

Без сети: ФГИС ТП подменён функцией-транспортом; снимки и проект — во временной папке.
Запуск: python -m unittest discover -s core/connectors/tests (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import json
import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401
from grado_model import Project
from grado_reactive import Session
from grado_connectors import (FgistpConnector, NspdCapture, SnapshotStore,
                              Subscriptions, import_snapshot)

MERC_SQUARE = [[4187345.5, 7509247.8], [4187445.5, 7509247.8],
               [4187445.5, 7509347.8], [4187345.5, 7509347.8],
               [4187345.5, 7509247.8]]


def nspd_payload():
    return {"type": "FeatureCollection", "grado_source": "nspd",
            "features": [{"type": "Feature",
                          "geometry": {"type": "Polygon", "coordinates": [MERC_SQUARE]},
                          "properties": {"options": {
                              "cad_num": "77:09:0004021:181",
                              "land_record_category_type": "Земли населённых пунктов",
                              "specified_area": 12000}}}]}


class TestImporter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.store = SnapshotStore(root / "snaps")
        self.project = Project.create(root / "p.grado", "Импорт")
        self.session = Session(self.project)
        conn = NspdCapture()
        self.sid = self.store.save(conn, conn.fetch(payload=nspd_payload()))

    def tearDown(self):
        self.project.close()
        self.tmp.cleanup()

    def test_import_with_provenance(self):
        n = import_snapshot(self.store, self.sid, self.project, self.session,
                            "cad.parcel",
                            attr_map={"cad_num": "opt_cad_num",
                                      "category": "opt_land_record_category_type",
                                      "area_doc": "opt_specified_area"})
        self.assertEqual(n, 1)
        layer = self.project.layer("cad.parcel")
        f = next(layer.features())
        self.assertEqual(f["source"], "nspd")
        self.assertEqual(f["attrs"]["cad_num"], "77:09:0004021:181")
        self.assertEqual(f["attrs"]["area_doc"], 12000.0)
        self.assertIn(self.sid, f["source_doc"])
        # координаты в СК проекта (метры UTM 37N)
        x, y = f["geom"]["coordinates"][0][0][0]
        self.assertAlmostEqual(x, 413100, delta=300)
        self.assertAlmostEqual(y, 6179400, delta=500)

    def test_import_is_one_journal_entry_and_undoable(self):
        import_snapshot(self.store, self.sid, self.project, self.session,
                        "cad.parcel", attr_map={"cad_num": "opt_cad_num"})
        log = self.session.log()
        self.assertEqual(len(log), 1)
        self.assertIn("импорт nspd", log[0]["title"])
        self.session.undo()
        self.assertEqual(self.project.layer("cad.parcel").count(), 0,
                         "весь импорт откатился одним undo")


UIN = "2" * 25


def fgistp_transport(wfs_payloads):
    layers = {"layer_stp_list": [
        {"classid": "60107", "class_name": "Функциональные зоны",
         "class_title": "ФЗ", "geom_type": "100", "stp_name": "ГП"}]}

    def transport(url):
        if "json_layers_stp_list" in url:
            return json.dumps(layers).encode()
        return json.dumps(wfs_payloads["current"]).encode()
    return transport


def wfs(features):
    return {"type": "FeatureCollection", "features": features}


def zone(fid, x):
    return {"type": "Feature", "id": f"pol.{fid}",
            "geometry": {"type": "Polygon",
                         "coordinates": [[[x, 54.8], [x + 0.1, 54.8], [x + 0.1, 54.9], [x, 54.8]]]},
            "properties": {"mt_status": 1}}


class TestSubscriptions(unittest.TestCase):
    def test_watch_document_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(Path(tmp) / "snaps")
            payloads = {"current": wfs([zone(1, 37.6)])}
            conn = FgistpConnector(transport=fgistp_transport(payloads))
            subs = Subscriptions(store)
            subs.add("fgistp", {"uin": UIN})

            first = subs.check({"fgistp": conn})
            self.assertEqual(len(first), 1)
            self.assertTrue(first[0]["initial"])

            unchanged = subs.check({"fgistp": conn})
            self.assertEqual(unchanged, [], "без изменений — без снимка и без шума")

            payloads["current"] = wfs([zone(1, 37.65), zone(2, 37.8)])
            changed = subs.check({"fgistp": conn})
            self.assertEqual(len(changed), 1)
            self.assertEqual(changed[0]["diff"]["added"], ["pol.2"])
            self.assertEqual(changed[0]["diff"]["changed"], ["pol.1"])
            self.assertEqual(len(store.list("fgistp")), 2, "новый снимок сохранён")


if __name__ == "__main__":
    unittest.main()
