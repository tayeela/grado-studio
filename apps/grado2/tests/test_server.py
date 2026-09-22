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
        m = {x["id"]: x["value"] for x in S.tep(1, 5, 1000, 1)["metrics"]}
        self.assertEqual(m["calc_area"], 0)
        self.assertEqual(m["population"], 0)

    def test_clean_props_renames_and_parses_numbers(self):
        p = S.clean_props({"opt_floors": "9-12", "opt_cad_num": "77:1", "grado_set": "x", "name": ""})
        self.assertEqual(p, {"Этажность": 9, "Кадастровый номер": "77:1"})

    def test_area_limit_blocks_before_network(self):
        layers, errors = S.fetch([37.0, 55.0, 37.5, 55.5], ["nspd.parcels", "unknown"])
        self.assertEqual(layers, {})
        self.assertIn("nspd.parcels", errors)


if __name__ == "__main__":
    unittest.main()
