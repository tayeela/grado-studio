import unittest

from grado_compute import Engine, PresetError


def make_engine():
    return Engine({
        "title": "test",
        "inputs": [
            {"id": "a", "default": 10},
            {"id": "b", "default": 2},
        ],
        "constants": {"k": 3},
        "metrics": [
            {"id": "m3", "expr": "m1 + m2"},
            {"id": "m1", "expr": "a * k"},
            {"id": "m2", "expr": "b + 1"},
        ],
    })


class TestEngine(unittest.TestCase):
    def test_topo_evaluation(self):
        e = make_engine()
        self.assertEqual(e.value("m1"), 30)
        self.assertEqual(e.value("m2"), 3)
        self.assertEqual(e.value("m3"), 33)

    def test_incremental_recompute(self):
        e = make_engine()
        counts = dict(e.eval_counts)
        e.set_input("b", 5)
        self.assertEqual(e.value("m2"), 6)
        self.assertEqual(e.value("m3"), 36)
        self.assertEqual(e.eval_counts["m1"], counts["m1"], "m1 не зависит от b")
        self.assertEqual(e.eval_counts["m2"], counts["m2"] + 1)
        self.assertEqual(e.eval_counts["m3"], counts["m3"] + 1)

    def test_unknown_input(self):
        e = make_engine()
        with self.assertRaises(KeyError):
            e.set_input("zzz", 1)

    def test_cycle_detection(self):
        with self.assertRaises(PresetError):
            Engine({
                "inputs": [{"id": "a", "default": 1}],
                "metrics": [
                    {"id": "x", "expr": "y + 1"},
                    {"id": "y", "expr": "x + a"},
                ],
            })

    def test_unknown_reference(self):
        with self.assertRaises(PresetError):
            Engine({"metrics": [{"id": "x", "expr": "nope + 1"}]})

    def test_duplicate_id(self):
        with self.assertRaises(PresetError):
            Engine({
                "inputs": [{"id": "a", "default": 1}],
                "metrics": [{"id": "a", "expr": "1 + 1"}],
            })



class SetInputsAtomic(unittest.TestCase):
    def test_unknown_key_changes_nothing(self):
        e = make_engine()
        with self.assertRaises(KeyError):
            e.set_inputs(a=99, bogus=1)
        self.assertEqual(e.value("a"), 10)

if __name__ == "__main__":
    unittest.main()
