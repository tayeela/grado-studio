"""Rust-движок ТЭП (grado_rs) против Python-эталона: результаты, сырые значения (repr), счётчики пересчётов, ошибки.

Без собранного модуля grado_rs тесты пропускаются (сборка: maturin build --release -m rust/crates/py/Cargo.toml).
Запуск: python -m unittest discover -s core/compute/tests (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import random
import unittest
from pathlib import Path

from grado_compute import ExpressionError, PresetError, PyEngine

try:
    from grado_compute.rust_backend import RustEngine
except ImportError:
    RustEngine = None

PRESETS = Path(__file__).parents[1] / "grado_compute" / "presets"
YAK = {"terr_area": 15.0, "restrict_area": 0.0, "spp_in": 357.0, "ratio_zh": 100.0, "nonres_part": 6.0,
       "education_zone": 1.0, "k1": 0.75, "k2": 0.2, "tinao": 0.0, "territory_mode": 1.0, "unbuilt_share": 25.0}
SCENARIOS = [
    ("moscow_calc2.json", {}, {}),
    ("moscow_calc2.json", YAK, {}),
    ("moscow_calc2.json", {**YAK, "education_zone": 2}, {}),
    ("moscow_calc2.json", {"spp_in": 100.0, "ratio_zh": 100.0, "spp_low_in": 100.0, "nonres_part": 6.0}, {}),
    ("moscow_calc2.json", {"spp_in": 3.30033 / 0.65 / 0.94, "ratio_zh": 100.0, "nonres_part": 6.0}, {}),
    ("moscow_calc2.json", YAK, {"doo_z1": 50.0}),
    ("moscow_calc2.json", YAK, {"doo_plot_m2_2": 30.0, "clinic_plot_norm_ha": 0.5}),
    ("moscow_calc2.json", {"spp_in": 0, "education_zone": 1}, {}),
    ("moscow_krt.json", {}, {}),
]


def snapshot(e):
    return (e.results(), {k: repr(v) for k, v in e._values.items()}, dict(e.eval_counts))


@unittest.skipIf(RustEngine is None, "модуль grado_rs не собран")
class TestRustParity(unittest.TestCase):
    def check_same(self, preset, sets, consts):
        py, rs = PyEngine.from_file(PRESETS / preset), RustEngine.from_file(PRESETS / preset)
        for e in (py, rs):
            if sets:
                e.set_inputs(**sets)
            if consts:
                e.set_constants(**consts)
        self.assertEqual(snapshot(py), snapshot(rs))

    def test_scenarios(self):
        for preset, sets, consts in SCENARIOS:
            with self.subTest(preset=preset, sets=sets, consts=consts):
                self.check_same(preset, sets, consts)

    def test_random_inputs(self):
        rnd = random.Random(20261108)
        inputs = [i["id"] for i in PyEngine.from_file(PRESETS / "moscow_calc2.json").preset["inputs"]]
        for _ in range(200):
            sets = {k: rnd.choice([0, 1, 2, rnd.uniform(0, 500), round(rnd.uniform(0, 100), 3)])
                    for k in rnd.sample(inputs, rnd.randint(1, len(inputs)))}
            with self.subTest(sets=sets):
                self.check_same("moscow_calc2.json", sets, {})

    def test_types_round_trip(self):
        preset = {"inputs": [{"id": "a", "default": 2}], "metrics": [
            {"id": "big", "expr": "a ** 60"}, {"id": "fl", "expr": "a / 3"}, {"id": "b", "expr": "a > 1"}]}
        py, rs = PyEngine(preset), RustEngine(preset)
        for name in ("big", "fl", "b"):
            self.assertEqual((type(py.value(name)), py.value(name)), (type(rs.value(name)), rs.value(name)))

    def test_errors_match(self):
        bad = {"inputs": [{"id": "a"}], "metrics": [{"id": "m", "expr": "a + zzz"}]}
        self.assertRaises(PresetError, PyEngine, bad)
        self.assertRaises(PresetError, RustEngine, bad)
        syntax = {"inputs": [{"id": "a"}], "metrics": [{"id": "m", "expr": "a +"}]}
        self.assertRaises(ExpressionError, PyEngine, syntax)
        self.assertRaises(ExpressionError, RustEngine, syntax)
        div = {"inputs": [{"id": "a", "default": 1}], "metrics": [{"id": "m", "expr": "1 / a"}]}
        for cls in (PyEngine, RustEngine):
            e = cls(div)
            self.assertRaises(ZeroDivisionError, e.set_input, "a", 0)
            self.assertRaises(KeyError, e.set_input, "nope", 1)
            self.assertRaises(KeyError, e.set_inputs, a=2, nope=1)
            self.assertEqual(e.value("a"), 0)   # отказ set_inputs ничего не записал


if __name__ == "__main__":
    unittest.main()
