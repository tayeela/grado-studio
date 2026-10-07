"""T5: контрольный пример участков социальных объектов (docs/specs/T5-social-objects.md, п. 4).

Часть 1 проверяет то, что пресет moscow_calc2 уже считает (потребность, число объектов, участок при дефиците = потребности).
Часть 2 — резерв при свободных местах (п. 4.2 спецификации): считает пресет (T6), числа те же."""

import json
import unittest
from pathlib import Path

from grado_compute import Engine

PRESET = Path(__file__).resolve().parents[1] / "grado_compute" / "presets" / "moscow_calc2.json"
C = json.loads(PRESET.read_text("utf-8"))["constants"]


def engine(spp, zone, free_doo=0, free_school=0, free_clinic=0):
    e = Engine.from_file(PRESET)
    e.set_inputs(terr_area=20, restrict_area=0, spp_in=spp, ratio_zh=100, nonres_part=6, education_zone=zone,
                 free_doo=free_doo, free_school=free_school, free_clinic=free_clinic)
    return e


def reserve(spp, zone, free_doo=0, free_school=0, free_clinic=0):
    """T6: резерв считает пресет (метрики группы «Резерв участков»); возвращает (м² по участкам ДОО, школа м², поликлиника м², показ)."""
    e = engine(spp, zone, free_doo, free_school, free_clinic)
    n, q, r = e.value("doo_res_n"), e.value("doo_res_q"), e.value("doo_res_r")
    doo = [(q + 1 if i < r else q) * (C["doo_plot_m2_1"] if (q + 1 if i < r else q) <= C["doo_plot_cap1"] else C["doo_plot_m2_2"]) for i in range(n)]
    assert sum(doo) == e.value("doo_res_m2")
    return doo, e.value("school_res_m2"), e.value("clinic_res_m2"), e


class TestSocialFixture(unittest.TestCase):
    def check(self, e, want):
        for k, v in want.items():
            self.assertEqual(e.display(k), v, k)

    def test_B_zone2_450(self):
        e = engine(450, 2)
        self.check(e, {"calc_area": 20, "spp_res_living": 423, "flats_area": 274.95, "population": 8332, "density_spp": 22.5,
                       "doo_places": 525, "doo_count": 2, "doo_plot_ha": 1.68, "school_places": 1034, "school_count": 1,
                       "school_plot_ha": 1.654, "clinic_mixed_visits": 159, "clinic_count": 1, "clinic_plot_ha": 0.35})

    def test_A_zone1_150(self):
        e = engine(150, 1)
        self.check(e, {"flats_area": 91.65, "population": 2778, "density_spp": 7.5, "doo_places": 123, "doo_count": 1,
                       "doo_plot_ha": 0.431, "school_places": 251, "school_plot_ha": 0.477, "clinic_mixed_visits": 53,
                       "clinic_plot_ha": 0.35})

    def test_preset_matches_plot_metrics_when_nothing_is_free(self):
        for spp, zone in ((450, 2), (150, 1)):
            doo, school, clinic, e = reserve(spp, zone)
            self.assertAlmostEqual(sum(doo) / 10000, e.value("doo_plot_ha"), places=9)
            self.assertAlmostEqual(school / 10000, e.value("school_plot_ha"), places=9)
            self.assertAlmostEqual(clinic / 10000, e.value("clinic_plot_ha"), places=9)

    def test_deficit_table(self):
        doo, school, clinic, e = reserve(450, 2)                                   # B0
        self.assertEqual((doo, school, clinic), ([8416, 8384], 16544, 3500))
        self.check(e, {"doo_deficit": 525, "doo_res_n": 2, "school_deficit": 1034, "clinic_deficit": 159,
                       "social_res_m2": 36844, "social_res_ha": 3.684, "social_res_share": 18.422})
        doo, school, clinic, e = reserve(450, 2, 175, 400, 100)                    # B1
        self.assertEqual((doo, school, clinic), ([11200], 12046, 3500))
        self.check(e, {"doo_deficit": 350, "doo_res_n": 1, "school_deficit": 634, "clinic_deficit": 59,
                       "social_res_m2": 26746, "social_res_ha": 2.675, "social_res_share": 13.373})
        doo, school, clinic, e = reserve(150, 1, 40, 100, 20)                      # A1
        self.assertEqual((doo, school, clinic), ([2905], 2869, 3500))
        self.check(e, {"doo_deficit": 83, "school_deficit": 151, "clinic_deficit": 33,
                       "social_res_m2": 9274, "social_res_ha": 0.927, "social_res_share": 4.637})

    def test_no_deficit_and_surplus(self):
        doo, school, clinic, e = reserve(150, 1, 200, 300, 100)                    # свободных больше потребности
        self.assertEqual((doo, school, clinic), ([], 0, 0))
        self.check(e, {"doo_deficit": 0, "doo_res_n": 0, "school_deficit": 0, "clinic_deficit": 0,
                       "social_res_m2": 0, "social_res_ha": 0, "social_res_share": 0})

if __name__ == "__main__":
    unittest.main()
