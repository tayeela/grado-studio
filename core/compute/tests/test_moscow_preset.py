"""Золотые числа пресета КРТ Москвы (moscow_krt.json): площади, население, соцнормы, парковки.

Запуск: python -m unittest discover -s core/compute/tests (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import unittest
from pathlib import Path

from grado_compute import Engine

PRESET = Path(__file__).parents[1] / "grado_compute" / "presets" / "moscow_krt.json"


class TestMoscowPreset(unittest.TestCase):
    """Золотые числа: территория 15 га без ограничений, плотность 25 тыс. м²/га,
    жильё 80% СПП, ВПП 6%, вне ТТК (0.5), далеко от ж/д (1.0)."""

    @classmethod
    def setUpClass(cls):
        cls.e = Engine.from_file(PRESET)
        cls.e.set_inputs(terr_area=15, restrict_area=0, density=25,
                         ratio_zh=80, percent_vpp=6, k_rail=1, k_ba=0.5)

    def test_areas(self):
        self.assertAlmostEqual(self.e.value("calc_area"), 15)
        self.assertAlmostEqual(self.e.value("spp"), 375.0)
        self.assertAlmostEqual(self.e.value("np"), 337.5)
        self.assertAlmostEqual(self.e.value("spp_zh"), 300.0)
        self.assertAlmostEqual(self.e.value("spp_nzh"), 75.0)
        self.assertAlmostEqual(self.e.value("spp_vpp"), 18.0)
        self.assertAlmostEqual(self.e.value("spp_zh_net"), 282.0)
        self.assertAlmostEqual(self.e.value("sq_flats"), 183.3)

    def test_population(self):
        self.assertEqual(self.e.value("population"), 5555)
        self.assertEqual(self.e.value("flats"), 2645)

    def test_social(self):
        self.assertEqual(self.e.value("doo_norm"), 244)
        self.assertEqual(self.e.value("doo_places"), 244)
        self.assertEqual(self.e.value("school_norm"), 500)
        self.assertEqual(self.e.value("school_places"), 500)
        self.assertEqual(self.e.value("policlinic_norm"), 106)
        self.assertEqual(self.e.value("policlinic_places"), 106)
        self.assertEqual(self.e.value("retail_nnp_required"), 1500)
        self.assertEqual(self.e.value("services_nnp_required"), 555)

    def test_education_zone_2(self):
        e = Engine.from_file(PRESET)
        e.set_inputs(terr_area=15, restrict_area=0, density=25,
                     ratio_zh=80, percent_vpp=6, education_zone=2,
                     k_rail=1, k_ba=0.5)
        self.assertEqual(e.value("doo_norm"), 350)
        self.assertEqual(e.value("school_norm"), 689)

    def test_2152_territory_modes(self):
        self.assertEqual(self.e.value("green_area_required"), 27773)
        self.assertEqual(self.e.value("playground_area_required"), 0)
        e = Engine.from_file(PRESET)
        e.set_inputs(terr_area=15, restrict_area=0, density=25,
                     ratio_zh=80, percent_vpp=6, territory_mode=2)
        self.assertEqual(e.value("green_area_required"), 37500)
        self.assertEqual(e.value("playground_area_required"), 2777)
        self.assertEqual(e.value("adult_recreation_area_required"), 555)

    def test_parking(self):
        self.assertEqual(self.e.value("parking_perm"), 714)
        self.assertEqual(self.e.value("parking_guest"), 71)
        rows = {row["id"]: row for row in self.e.results()}
        self.assertEqual(rows["parking_perm"]["unit"], "м/м")
        self.assertEqual(rows["parking_guest"]["unit"], "м/м")

    def test_social_need_is_not_hidden_on_small_territory(self):
        e = Engine.from_file(PRESET)
        e.set_inputs(terr_area=1, restrict_area=0, density=10,
                     ratio_zh=80, percent_vpp=6, k_rail=1, k_ba=0.5)
        self.assertGreater(e.value("doo_places"), 0)
        self.assertGreater(e.value("school_places"), 0)

    def test_restrict_area_reduces_everything(self):
        e = Engine.from_file(PRESET)
        e.set_inputs(terr_area=15, restrict_area=0, density=25,
                     ratio_zh=80, percent_vpp=6, k_rail=1, k_ba=0.5)
        base_pop = e.value("population")
        e.set_input("restrict_area", 5)
        self.assertAlmostEqual(e.value("calc_area"), 10)
        self.assertLess(e.value("population"), base_pop)


if __name__ == "__main__":
    unittest.main()
