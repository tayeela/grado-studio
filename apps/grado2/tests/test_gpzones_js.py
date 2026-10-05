"""Функциональные зоны Генплана (web/gpzones.js): цвет по индексу таблицы MapInfo, имя и индекс обоих слоёв."""
import shutil
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class GpZonesJs(unittest.TestCase):
    def test_zone_fill_and_index(self):
        r = subprocess.run(["node", str(HERE / "gpzones_test.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("checks ok", r.stdout)


if __name__ == "__main__":
    unittest.main()
