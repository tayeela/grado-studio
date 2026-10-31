"""Проверяет, что новый импорт сохраняет ручные изменения и удаления объектов.

Запуск: python -m pytest apps/grado2/tests/test_sushpol_jobs.py.
"""
import copy
import unittest
from sushpol_jobs import _merged


def feature(key,value,x=37.6):
    return {'type':'Feature','geometry':{'type':'Point','coordinates':[x,55.7]},'properties':{'_key':key,'value':value}}


class ManualImportMerge(unittest.TestCase):
    def test_refresh_preserves_edit_delete_manual_insert_and_outside_objects(self):
        original=[feature('edited','source-old'),feature('deleted','source-old'),feature('outside','old',38.5)]
        current=[feature('edited','owner'),feature('outside','old',38.5),feature('inserted','owner')]
        before={'fc':{'features':current},'original':{'features':original}}
        untouched=copy.deepcopy(before)
        incoming=[feature('edited','source-new'),feature('deleted','source-new'),feature('new','source-new')]
        merged,base=_merged(before,incoming,[37.5,55.6,37.7,55.8])
        actual={f['properties']['_key']:f['properties']['value'] for f in merged}
        self.assertEqual(actual,{'edited':'owner','outside':'old','inserted':'owner','new':'source-new'})
        self.assertEqual({f['properties']['_key'] for f in base},{'edited','deleted','new','outside'})
        self.assertEqual(before,untouched)


class SourceFootprints(unittest.TestCase):
    def test_large_district_is_explicitly_deferred_without_shrinking_fine_maps(self):
        from shapely.geometry import box,mapping
        import preparation as P
        from sushpol_jobs import _source_bounds
        project={"territory":mapping(P.to_wgs(box(0,0,200,100))),"album":{"meta":{},"sheets":[]},
                 "data":{"gisogd.admin":{"fc":{"features":[{"geometry":mapping(P.to_wgs(box(-40000,-40000,40000,40000))),"properties":{"Уровень":"район"}}]}}}}
        deferred=[]
        bounds=_source_bounds(project,"egko.roads",2400,deferred)
        self.assertEqual(len(deferred),1)
        self.assertEqual(deferred[0]["reasonCode"],"budget_exceeded")
        self.assertGreater(deferred[0]["actualAreaKm2"],2400)
        self.assertLess(P.to_msk(box(*bounds)).area/1e6,40)
        self.assertTrue(P.to_msk(box(*bounds)).buffer(.01).covers(box(0,0,200,100)))

    def test_yandex_district_context_is_deferred_at_tile_budget(self):
        # Яндекс режется на 16 частей по 30 км² (TILE_KM2×MAX_TILES = 480): контекст района 3624 км² откладывается явно,
        # а не валит весь источник (прогон Безобразово 29.10).
        from shapely.geometry import box,mapping
        import preparation as P
        from sushpol_jobs import _source_bounds
        project={"territory":mapping(P.to_wgs(box(0,0,200,100))),"album":{"meta":{},"sheets":[]},
                 "data":{"gisogd.admin":{"fc":{"features":[{"geometry":mapping(P.to_wgs(box(-40000,-40000,40000,40000))),"properties":{"Уровень":"район"}}]}}}}
        deferred=[]
        bounds=_source_bounds(project,"yandex.green",480.0,deferred)
        self.assertEqual(len(deferred),1)
        self.assertEqual(deferred[0]["reasonCode"],"budget_exceeded")
        self.assertGreater(deferred[0]["actualAreaKm2"],480)
        self.assertLess(P.to_msk(box(*bounds)).area/1e6,40)


class IssueSummary(unittest.TestCase):
    def test_owner_input_is_counted_separately_from_pipeline_problems(self):
        from sushpol_jobs import _issue_summary
        s=_issue_summary([{"reasonCode":"missing_field","kind":"land_rights"},
                          {"reasonCode":"manual_conflict","kind":"parcels_oks"},
                          {"reasonCode":"source_unavailable","kind":"territory_ortho"},
                          {"reasonCode":"budget_exceeded","kind":"project"}])
        self.assertEqual(s["ownerInput"],2)          # ЕГРН-поля и связь ОКС–ЗУ — владелец, не сборка
        self.assertEqual(s["pipeline"],2)
        self.assertEqual(s["total"],4)
        self.assertEqual(s["byCode"]["missing_field"],1)


class PartialImportMerge(unittest.TestCase):
    def test_unreceived_objects_are_not_deleted_by_partial_response(self):
        old=[feature("received","old"),feature("unreceived","old")]
        merged,base=_merged({"fc":{"features":old},"original":"=fc"},[feature("received","new")],
                            [37.5,55.6,37.7,55.8],preserve_absent=True)
        self.assertEqual({f["properties"]["_key"]:f["properties"]["value"] for f in merged},
                         {"received":"new","unreceived":"old"})


class FrozenRasters(unittest.TestCase):
    def test_export_uses_captured_bytes_and_rejects_tampering(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from sushpol_jobs import Runs
        import preparation as P
        source=lambda *args:b"original image bytes"
        with tempfile.TemporaryDirectory() as root:
            server=SimpleNamespace(CACHE=Path(root),esri_tile=source)
            runs=Runs(server);runs._check=lambda job:None
            job={"path":Path(root)/"run"}
            tiles,finish=runs._capture_tiles(job)
            self.assertEqual(tiles(10,100,200),b"original image bytes")
            self.assertIsNone(tiles.ysat(10,100,200))
            revision=finish()
            server.esri_tile=lambda *args:b"new portal version"
            export=runs._frozen_tiles(job["path"],revision,False)
            self.assertEqual(export(10,100,200),b"original image bytes")
            self.assertIsNone(export.ysat(10,100,200))
            stored=next((job["path"]/"rasters").glob("*.bin"));stored.write_bytes(b"corrupted")
            with self.assertRaises(P.PreparationError):export(10,100,200)
