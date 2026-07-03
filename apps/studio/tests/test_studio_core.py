import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import studio_core  # noqa: E402

FEATURES = [
    {"kind": "boundary", "ring": [[0, 0], [500, 0], [500, 300], [0, 300]],
     "props": {}},
    {"kind": "restrict", "ring": [[0, 0], [200, 0], [200, 100], [0, 100]],
     "props": {}},
    {"kind": "zone", "ring": [[0, 100], [500, 100], [500, 300], [0, 300]],
     "props": {"zone_title": "Ж-1"}},
    {"kind": "building", "ring": [[50, 150], [80, 150], [80, 170], [50, 170]],
     "props": {"floors": 10}},
    {"kind": "redline", "line": [[0, 120], [500, 120]], "props": {}},
    {"kind": "social", "point": [400, 200], "props": {"capacity": 500}},
]


class TestStudioCore(unittest.TestCase):
    def test_build_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "s.grado", "Тест", FEATURES)
            codes = {i["code"] for i in p.layers()}
            self.assertEqual(codes, {"terr.boundary", "terr.restrict",
                                     "tp.func_zone", "oks.building",
                                     "pp.red_line", "social.object"})
            self.assertAlmostEqual(p.layer("terr.boundary").area_ha(), 15.0)
            f = next(p.layer("oks.building").features())
            self.assertEqual(f["attrs"]["floors"], 10)
            # координаты ушли в СК проекта (смещение ORIGIN)
            x = f["geom"]["coordinates"][0][0][0]
            self.assertGreater(x, 400000)
            p.close()

    def test_compute_tep(self):
        out = studio_core.compute_tep(FEATURES, {"density": 25, "ratio_zh": 80})
        self.assertAlmostEqual(out["inputs"]["terr_area"], 15.0)
        self.assertAlmostEqual(out["inputs"]["restrict_area"], 2.0)
        pop = next(r for r in out["results"] if r["id"] == "population")
        self.assertEqual(pop["value"], 4814)
        # факт по посадке: 30×20 м × 10 этажей = 6 тыс. м²
        self.assertAlmostEqual(out["fact"]["spp"], 6.0)
        self.assertAlmostEqual(out["fact"]["density"], round(6.0 / 13.0, 2))

    def test_empty_features_defaults(self):
        out = studio_core.compute_tep([])
        self.assertGreater(out["inputs"]["terr_area"], 0)
        self.assertEqual(out["fact"]["spp"], 0)

    def test_make_album(self):
        pdf = studio_core.make_album(FEATURES, "Тестовая концепция",
                                     {"density": 25, "ratio_zh": 80})
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"/Count 5", pdf)

    def test_redline_fillet_applied(self):
        feat = [{"kind": "redline", "props": {"radius": 20},
                 "line": [[0, 0], [100, 0], [100, 100]]}]
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "r.grado", "Т", feat)
            f = next(p.layer("pp.red_line").features())
            coords = f["geom"]["coordinates"]
            self.assertGreater(len(coords), 3, "угол заменён дугой (линеаризация)")
            self.assertAlmostEqual(p.layer("pp.red_line").length_m(),
                                   2 * 80 + 3.14159 * 20 / 2, delta=0.1)
            p.close()

    def test_redline_radius_too_big_falls_back(self):
        feat = [{"kind": "redline", "props": {"radius": 500},
                 "line": [[0, 0], [100, 0], [100, 100]]}]
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "r.grado", "Т", feat)
            f = next(p.layer("pp.red_line").features())
            self.assertEqual(len(f["geom"]["coordinates"]), 3,
                             "радиус не помещается — ломаная без сопряжения")
            p.close()

    def test_import_nspd_capture(self):
        merc = [[4187345.5, 7509247.8], [4187445.5, 7509247.8],
                [4187445.5, 7509347.8], [4187345.5, 7509247.8]]
        payload = {"type": "FeatureCollection", "grado_source": "nspd",
                   "features": [{"type": "Feature",
                                 "geometry": {"type": "Polygon", "coordinates": [merc]},
                                 "properties": {"options": {
                                     "cad_num": "77:09:0004021:181",
                                     "land_record_category_type": "земли нас. пунктов"}}}]}
        out = studio_core.import_nspd(payload)
        self.assertEqual(len(out["features"]), 1)
        f = out["features"][0]
        self.assertEqual(f["kind"], "parcel")
        self.assertEqual(f["props"]["cad_num"], "77:09:0004021:181")
        x, y = f["ring"][0]
        # локальные метры холста: UTM минус ORIGIN, порядок сотен метров/км
        self.assertAlmostEqual(x, 98, delta=15)
        self.assertAlmostEqual(y, 1371, delta=15)
        # круговой путь: parcel → проект → слой cad.parcel
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "n.grado", "Т", out["features"])
            pf = next(p.layer("cad.parcel").features())
            self.assertEqual(pf["attrs"]["cad_num"], "77:09:0004021:181")
            p.close()

    def test_make_grado_is_sqlite(self):
        data = studio_core.make_grado(FEATURES, "Тест")
        self.assertTrue(data.startswith(b"SQLite format 3"))


if __name__ == "__main__":
    unittest.main()
