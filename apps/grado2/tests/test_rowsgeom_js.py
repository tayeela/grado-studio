"""Геометрия рядов «по границе» генератора посадки (ui/src/rowsgeom.js): хорды контура, расстояние между корпусами.

Запускает ui/src/rowsgeom.test.js через `node --test`; библиотеки из ui/node_modules не нужны.
Запуск: python3 -m unittest apps/grado2/tests/test_rowsgeom_js.py
"""
import shutil
import subprocess
import unittest
from pathlib import Path

TEST = Path(__file__).resolve().parents[1] / "ui" / "src" / "rowsgeom.test.js"


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class RowsGeomJs(unittest.TestCase):
    def test_rows_geom(self):
        r = subprocess.run(["node", "--test", str(TEST)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("# fail 0", r.stdout)


if __name__ == "__main__":
    unittest.main()
