"""Методика «Калькулятора 2.0» (genplan.tech) против его собственного расчёта: Якиманка, 15 га, плотность 23,8.

Эталон снят с калькулятора 23.09.2026 (fixtures/calc2_yakimanka_15ha.json). Там, где правила округления заказчика
(3 знака, показатели СПП — 2, люди и места — вверх) дают другое число знаков, чем показывает калькулятор, сравнение
идёт по значению с этой точностью.
"""

import json
import unittest
from pathlib import Path

from grado_compute import Engine
from grado_compute.expressions import round_half_up

HERE = Path(__file__).parent
PRESET = HERE.parents[0] / "grado_compute" / "presets" / "moscow_calc2.json"
REF = json.loads((HERE / "fixtures" / "calc2_yakimanka_15ha.json").read_text("utf-8"))["expected"]


class TestCalc2Yakimanka(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Engine.from_file(PRESET)
        cls.e.set_inputs(terr_area=15, restrict_area=0, spp_in=357, ratio_zh=100, nonres_part=6,
                         education_zone=1, k1=0.75, k2=0.2, tinao=0, territory_mode=1, unbuilt_share=25)
        cls.r = {m["id"]: m["value"] for m in cls.e.results()}
        cls.r.update({k: cls.e.display(k) for k in ("pop_mkd",)})

    def eq(self, mine, ref, places=None):
        v = self.r[mine]
        if places is None:
            self.assertEqual(v, REF[ref], mine)
        else:
            self.assertAlmostEqual(v, round_half_up(REF[ref], places), places=places, msg=mine)

    def test_areas(self):
        self.eq("spp", "spp_total", 2); self.eq("spp_res_living", "spp_res_living", 2); self.eq("spp_res_nonres", "spp_res_nonres", 2)
        self.eq("np", "np_total", 3); self.eq("np_res_living", "np_res_living", 3); self.eq("np_res_nonres", "np_res_nonres", 3)
        self.eq("flats_area", "flats_area", 3); self.eq("nnp", "nnp", 3)
        self.eq("density_spp", "density_spp", 2); self.eq("density_np", "density_np", 2)

    def test_population_and_flats(self):
        self.eq("population", "population"); self.eq("flats", "flats")

    def test_social(self):
        self.eq("doo_places", "doo_places"); self.eq("school_places", "school_places")
        self.eq("clinic_mixed_visits", "clinic_mixed"); self.eq("clinic_adult_visits", "clinic_adult"); self.eq("clinic_child_visits", "clinic_child")

    def test_services_and_sport(self):
        # калькулятор показывает площадные потребности округлёнными ВВЕРХ (общепит 6,61 × 120 = 0,7932 → «0,794»,
        # спорт до 500 м 2,1152 → «2,116»); по правилу заказчика они округляются математически — сверка с точным значением
        for mine, norm, div in [("retail_nnp", 270, 1e6), ("services_nnp", 100, 1e6), ("catering_nnp", 120, 1e6), ("culture_nnp", 150, 1e6),
                                ("city_services_nnp", 90, 1e6), ("sport_indoor", 800, 1e6), ("sport_indoor_500", 320, 1e6),
                                ("sport_indoor_1500", 480, 1e6), ("sport_flat_ha", 970, 1e7)]:
            self.assertEqual(self.r[mine], round_half_up(norm * REF["population"] / div, 3), mine)
            self.assertLessEqual(abs(self.r[mine] - REF[{"sport_indoor": "sport_indoor_nnp"}.get(mine, mine)]), 0.0011, mine)

    def test_sport_flat_split_sums_to_total(self):
        # 1557-ПП п. 1.3.3.2: 970 = 570 (до 500 м) + 400 (до 1500 м)
        a, b, t = self.r["sport_flat_500_ha"], self.r["sport_flat_1500_ha"], self.r["sport_flat_ha"]
        self.assertEqual(a, round_half_up(570 * REF["population"] / 1e7, 3))
        self.assertEqual(b, round_half_up(400 * REF["population"] / 1e7, 3))
        self.assertLessEqual(abs(a + b - t), 0.0011)

    def test_parking(self):
        self.eq("parking_perm", "parking_perm"); self.eq("parking_guest", "parking_guest"); self.eq("parking_visitor", "parking_visitor")
        self.eq("parking_total", "parking_total"); self.eq("parking_stop", "parking_stop")

    def test_balance_and_green(self):
        self.eq("mkd_plots", "balance_mkd_plots_ha", 3); self.eq("unbuilt", "balance_unbuilt_ha", 3); self.eq("density_mkd_plots", "density_res_plots", 2)
        self.eq("green_zhk_ha", "green_zhk_ha", 3); self.eq("green_planting_ha", "green_planting_ha", 3)
        self.eq("green_playgrounds_ha", "green_playgrounds_ha", 3); self.eq("green_public_ha", "green_public_ha", 3)


class TestCalc2Rules(unittest.TestCase):
    def run_(self, **kw):
        e = Engine.from_file(PRESET); e.set_inputs(**kw); return {m["id"]: m["value"] for m in e.results()}

    def test_people_and_places_round_up(self):
        # 33 м² ровно на человека — не округляется вверх лишний раз; 33,001 — уже ещё один человек
        r = self.run_(spp_in=3.3 / 0.65 / 0.94, ratio_zh=100, nonres_part=6)        # 3 300 м² квартир = ровно 100 человек
        self.assertEqual(r["population"], 100)
        r = self.run_(spp_in=3.30033 / 0.65 / 0.94, ratio_zh=100, nonres_part=6)    # на 0,33 м² больше — уже 101
        self.assertEqual(r["population"], 101)

    def test_lowrise_50_sqm_per_person(self):
        r = self.run_(spp_in=100, ratio_zh=100, spp_low_in=100, nonres_part=6)
        self.assertEqual(r["population"], 1300)                  # 100 000 × 0,65 / 50
        self.assertEqual(r["parking_perm"], 496)                 # 65 000 / (50 × 2,1) × 0,8 = 495,2 → вверх

    def test_zone_2_norms(self):
        r = self.run_(spp_in=357, ratio_zh=100, nonres_part=6, education_zone=2)
        self.assertEqual((r["doo_places"], r["school_places"]), (417, 820))   # 6610 × 63 / 1000 = 416,4; × 124 = 819,6

    def test_half_up_display(self):
        from grado_compute.expressions import round_half_up
        self.assertEqual((round_half_up(2.5), round_half_up(0.0005, 3), round_half_up(2.675, 2)), (3, 0.001, 2.68))


class TestCalc2ConstantsMeta(unittest.TestCase):
    P = json.loads(PRESET.read_text("utf-8"))

    def test_every_constant_has_meta_and_back(self):
        self.assertEqual(set(self.P["constants"]), set(self.P["constants_meta"]))

    def test_meta_is_complete_and_default_inside_limits(self):
        for cid, m in self.P["constants_meta"].items():
            for k in ("title", "unit", "group", "source", "edition", "status", "min", "max"):
                self.assertIn(k, m, cid)
            self.assertTrue(m["title"] and m["unit"] and m["group"] and m["source"], cid)
            self.assertLessEqual(m["min"], self.P["constants"][cid], cid)
            self.assertLessEqual(self.P["constants"][cid], m["max"], cid)

    def test_set_constants_recomputes_and_rejects_unknown(self):
        e = Engine.from_file(PRESET)
        e.set_inputs(spp_in=357, ratio_zh=100, nonres_part=6, education_zone=1)
        school = e.value("school_places")
        e.set_constants(doo_z1=50)
        self.assertEqual(e.value("doo_places"), -(-round(50 * e.value("population") / 1000, 6) // 1))
        self.assertEqual(e.value("school_places"), school)
        with self.assertRaises(KeyError):
            e.set_constants(nope=1)
