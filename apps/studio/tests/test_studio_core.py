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

    def test_make_grado_is_sqlite(self):
        data = studio_core.make_grado(FEATURES, "Тест")
        self.assertTrue(data.startswith(b"SQLite format 3"))


if __name__ == "__main__":
    unittest.main()
