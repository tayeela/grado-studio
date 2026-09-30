import time
import unittest

from grado_compute import expressions
from grado_compute.expressions import ExpressionError


class TestExpressionLimits(unittest.TestCase):
    def test_pow_bomb_rejected_fast(self):
        t = time.time()
        for expr in ("9**9**9", "2**65", "2**-65", "(2**60)**60**60"):
            with self.assertRaises(ExpressionError, msg=expr):
                expressions.evaluate(expr, {})
        self.assertLess(time.time() - t, 1.0)

    def test_pow_normal_works(self):
        self.assertEqual(expressions.evaluate("x ** 2", {"x": 12}), 144)
        self.assertEqual(expressions.evaluate("2 ** 10", {}), 1024)
        self.assertEqual(expressions.evaluate("4 ** 0.5", {}), 2.0)

    def test_nonfinite_base_rejected(self):
        with self.assertRaises(ExpressionError):
            expressions.evaluate("x ** 2", {"x": float("inf")})

    def test_length_limit(self):
        with self.assertRaises(ExpressionError):
            expressions.parse("1" + "+1" * 300)

    def test_depth_limit(self):
        with self.assertRaises(ExpressionError):
            expressions.parse("-" * 100 + "1")
        with self.assertRaises(ExpressionError):
            expressions.parse("abs(" * 60 + "1" + ")" * 60)

    def test_nul_byte(self):
        with self.assertRaises(ExpressionError):
            expressions.parse("1\x00+2")

    def test_shared_tree_not_mutated(self):
        tree = expressions.parse("x ** 2")
        self.assertEqual(expressions.evaluate(tree, {"x": 3}), 9)
        self.assertEqual(expressions.evaluate(tree, {"x": 4}), 16)


if __name__ == "__main__":
    unittest.main()
