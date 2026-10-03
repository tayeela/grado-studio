"""T5: контрольный пример участков социальных объектов (docs/team/spec-T5-social-objects.md, п. 4).

Часть 1 проверяет то, что пресет moscow_calc2 уже считает (потребность, число объектов, участок при дефиците = потребности).
Часть 2 — эталонная арифметика резервирования при свободных местах (п. 4.2 спецификации): функций для неё в коде ещё нет,
T6 заменяет `reserve` вызовом программы и оставляет те же ожидаемые числа."""

import json
import unittest
from pathlib import Path

from grado_compute import Engine
from grado_compute.expressions import round_half_up

PRESET = Path(__file__).resolve().parents[1] / "grado_compute" / "presets" / "moscow_calc2.json"
C = json.loads(PRESET.read_text("utf-8"))["constants"]


def engine(spp, zone):
    e = Engine.from_file(PRESET)
    e.set_inputs(terr_area=20, restrict_area=0, spp_in=spp, ratio_zh=100, nonres_part=6, education_zone=zone)
    return e


def doo_m2(places):
    return C["doo_plot_m2_1"] if places <= C["doo_plot_cap1"] else C["doo_plot_m2_2"]


def school_m2(places):
    if places <= C["school_plot_cap1"]:
        return C["school_plot_m2_1"]
    return C["school_plot_m2_2"] if places <= C["school_plot_cap2"] else C["school_plot_m2_3"]


def reserve(doo_demand, school_demand, clinic_demand, free_doo=0, free_school=0, free_clinic=0):
    """Эталон спецификации п. 3: возвращает (участки ДОО в м² по объектам, школа м², поликлиника м²)."""
    d, s, c = (max(doo_demand - free_doo, 0), max(school_demand - free_school, 0), max(clinic_demand - free_clinic, 0))
    n = -(-d // C["doo_plot_cap2"]) if d else 0
    doo = [(d // n + (1 if i < d % n else 0)) for i in range(n)] if n else []
    return ([p * doo_m2(p) for p in doo], s * school_m2(s) if s else 0, round(C["clinic_plot_norm_ha"] * 10000) if c else 0)


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

    def test_reference_matches_program_when_nothing_is_free(self):
        for spp, zone in ((450, 2), (150, 1)):
            e = engine(spp, zone)
            doo, school, clinic = reserve(e.value("doo_places"), e.value("school_places"), e.value("clinic_mixed_visits"))
            self.assertAlmostEqual(sum(doo) / 10000, e.value("doo_plot_ha"), places=9)
            self.assertAlmostEqual(school / 10000, e.value("school_plot_ha"), places=9)
            self.assertAlmostEqual(clinic / 10000, e.value("clinic_plot_ha"), places=9)

    def test_deficit_table(self):
        doo, school, clinic = reserve(525, 1034, 159)                       # B0
        self.assertEqual((doo, school, clinic), ([8416, 8384], 16544, 3500))
        self.assertEqual(round_half_up(sum(doo) / 10000 + school / 10000 + clinic / 10000, 3), 3.684)
        self.assertEqual(round_half_up(sum(doo) / 10000, 3), 1.68)
        doo, school, clinic = reserve(525, 1034, 159, 175, 400, 100)        # B1
        self.assertEqual((doo, school, clinic), ([11200], 12046, 3500))
        tot = sum(doo) + school + clinic
        self.assertEqual((tot, round_half_up(tot / 10000, 3), round_half_up(tot / 10000 / 20 * 100, 3)), (26746, 2.675, 13.373))
        doo, school, clinic = reserve(123, 251, 53, 40, 100, 20)            # A1
        self.assertEqual((doo, school, clinic), ([2905], 2869, 3500))
        tot = sum(doo) + school + clinic
        self.assertEqual((tot, round_half_up(tot / 10000, 3), round_half_up(tot / 10000 / 20 * 100, 3)), (9274, 0.927, 4.637))
        self.assertEqual(reserve(100, 200, 50, 100, 200, 50), ([], 0, 0))   # дефицита нет — участков нет


if __name__ == "__main__":
    unittest.main()
