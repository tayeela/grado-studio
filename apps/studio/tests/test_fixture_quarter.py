"""Цепочка 1.0 до холста: фикстура квартала, не живой .grado."""

import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parents[1]))
import studio_core  # noqa: E402
from grado_geom import Snapper, mirror  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "quarter.json"


class TestQuarterFixture(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.features = self.payload["features"]

    def test_chain(self):
        tep = studio_core.compute_tep(self.features, {"density": 25})
        self.assertAlmostEqual(tep["inputs"]["terr_area"], 1.0)
        # 20×10 м × 5 этажей = 1.0 тыс. м². Второе здание без этажности не ×9.
        self.assertAlmostEqual(tep["fact"]["spp"], 1.0)
        self.assertEqual(tep["fact"]["floors_unknown"], 1)

        bare = studio_core.compute_tep(
            [f for f in self.features if f["kind"] != "boundary"])
        self.assertIsNone(bare["inputs"]["terr_area"])
        self.assertTrue(all(row["value"] is None for row in bare["results"]))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quarter.grado"
            project = studio_core.build_project(path, self.payload["name"], self.features)
            stored = list(project.layer_by_id("project.apo.buildings").features())
            keys = sorted(f["grado_key"] for f in stored if f["grado_key"])
            self.assertEqual(keys, ["fixture:building"])
            red = next(project.layer_by_id("project.apo.red_lines").features())
            self.assertEqual(red["curve"]["type"], "path")
            self.assertEqual(red["curve"]["radius"], 10)
            self.assertGreater(len(red["geom"]["coordinates"]), 3)
            project.close()

            opened = studio_core.grado_to_features(path)
        by_key = {f.get("srcKey"): f for f in opened["features"]}
        self.assertEqual(by_key["fixture:building"]["props"]["floors"], 5)
        self.assertEqual(by_key["fixture:redline"]["props"]["radius"], 10)
        self.assertEqual(by_key["fixture:redline"]["line"][0], [0, 0])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nobound.grado"
            only_building = [self.features[1]]
            project = studio_core.build_project(path, "Без границы", only_building)
            try:
                engine = studio_core.album_engine(project, only_building)
            finally:
                project.close()
        self.assertEqual(engine.display("population"), "н/д")
        self.assertIsNone(engine.value("terr_area"))

        snap = Snapper(tolerance=1)
        snap.add_polyline([(0, 0), (100, 0), (100, 100)])
        hit = snap.snap(100.2, 0.2)
        self.assertEqual(hit.kind, "endpoint")
        self.assertEqual(mirror([(0, 10)], (0, 0), (1, 0)), [(0, -10)])
