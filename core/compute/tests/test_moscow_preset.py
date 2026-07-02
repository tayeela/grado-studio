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
        self.assertEqual(self.e.value("policlinic_places"), 0,
                         "ниже порога 320 посещений — объект не размещается")

    def test_parking(self):
        self.assertEqual(self.e.value("parking_perm"), 714)
        self.assertEqual(self.e.value("parking_guest"), 71)

    def test_social_thresholds_small_territory(self):
        e = Engine.from_file(PRESET)
        e.set_inputs(terr_area=1, restrict_area=0, density=10,
                     ratio_zh=80, percent_vpp=6, k_rail=1, k_ba=0.5)
        self.assertEqual(e.value("doo_places"), 0, "потребность ниже порога 100 мест")
        self.assertEqual(e.value("school_places"), 0, "потребность ниже порога 150 мест")

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
