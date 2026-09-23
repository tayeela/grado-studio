import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402


class Grado2Server(unittest.TestCase):
    def test_tep_population_only_from_new_buildings(self):
        r = S.tep(terr_ha=10, restrict_ha=1, spp_new_m2=200_000, share=0.8, spp_kept_m2=50_000)
        m = {x["id"]: x["value"] for x in r["metrics"]}
        self.assertEqual(m["spp"], 200)                   # тыс. м², только новая застройка
        self.assertEqual(m["calc_area"], 9)
        self.assertAlmostEqual(r["density_total"], 25.0)  # (200 + 50) / 10 га

    def test_tep_restrict_larger_than_territory_is_safe(self):
        # Restrictions larger than the territory: the area is clamped to 0 and densities do not divide by it.
        # Population follows the flats area («Калькулятор 2.0»), not the territory: 611 m² of flats / 33 = 18.5, rounded up to 19.
        m = {x["id"]: x["value"] for x in S.tep(1, 5, 1000, 1)["metrics"]}
        self.assertEqual(m["calc_area"], 0)
        self.assertEqual(m["density_spp"], 0)
        self.assertEqual(m["population"], 19)

    def test_clean_props_renames_and_parses_numbers(self):
        p = S.clean_props({"opt_floors": "9-12", "opt_cad_num": "77:1", "grado_set": "x", "name": ""})
        self.assertEqual(p, {"Этажность": 9, "Кадастровый номер": "77:1"})

    def test_nspd_keeps_only_named_fields(self):
        p = S.clean_props({"opt_floors": "9", "systemInfo": {"inserted": "x"}, "interactionId": "1", "opt_cost_index": "5"}, None, True)
        self.assertEqual(p, {"Этажность": 9})

    def test_area_limit_blocks_before_network(self):
        layers, errors = S.fetch([37.0, 55.0, 37.5, 55.5], ["nspd.parcels", "unknown"])
        self.assertEqual(layers, {})
        self.assertIn("nspd.parcels", errors)


class Projects(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.old, S.PROJECTS = S.PROJECTS, Path(self.tmp.name) / "p"

    def tearDown(self):
        S.PROJECTS = self.old
        self.tmp.cleanup()

    def test_save_list_and_autosave_apart(self):
        S.save_project("Хорошёво", b'{"format": "grado2"}')
        S.save_project(".autosave", b'{"format": "grado2"}')
        r = S.list_projects()
        self.assertEqual([p["name"] for p in r["projects"]], ["Хорошёво"])
        self.assertIsNotNone(r["autosave"])
        self.assertEqual(S.project_path("Хорошёво").read_bytes(), b'{"format": "grado2"}')

    def test_names_cannot_escape_the_folder(self):
        for bad in ("../x", "a/b", "", ".hidden", "c:x"):
            with self.assertRaises(ValueError):
                S.project_path(bad)

    def test_broken_json_is_not_written(self):
        with self.assertRaises(ValueError):
            S.save_project("x", b"{not json")
        self.assertFalse(S.project_path("x").exists())


if __name__ == "__main__":
    unittest.main()
