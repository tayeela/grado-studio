import unittest

from grado_compute import expressions
from grado_compute.expressions import ExpressionError


class TestExpressions(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(expressions.evaluate("2 + 3 * 4", {}), 14)
        self.assertEqual(expressions.evaluate("(a - b) / 2", {"a": 10, "b": 4}), 3)
        self.assertEqual(expressions.evaluate("-a + 7", {"a": 2}), 5)

    def test_functions(self):
        self.assertEqual(expressions.evaluate("round(2.567, 1)", {}), 2.6)
        self.assertEqual(expressions.evaluate("where(x >= 5, x, 0)", {"x": 3}), 0)
        self.assertEqual(expressions.evaluate("where(x >= 5, x, 0)", {"x": 7}), 7)
        self.assertEqual(expressions.evaluate("clamp(15, 0, 10)", {}), 10)
        self.assertEqual(expressions.evaluate("max(min(3, 5), 1)", {}), 3)

    def test_names(self):
        self.assertEqual(expressions.names("a * b + round(c)"), {"a", "b", "c"})

    def test_missing_name(self):
        with self.assertRaises(ExpressionError):
            expressions.evaluate("a + b", {"a": 1})

    def test_rejects_unsafe(self):
        for expr in [
            "__import__('os')",
            "().__class__",
            "[1,2][0]",
            "'abc'",
            "lambda: 1",
            "open('/etc/passwd')",
            "round(x, n=1)",
        ]:
            with self.assertRaises(ExpressionError, msg=expr):
                expressions.parse(expr)


if __name__ == "__main__":
    unittest.main()
