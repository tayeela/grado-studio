"""Легенда листов только из нарисованного и общие препятствия подписей рек (web/legendrules.js), T85a/T85b."""
import shutil
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class LegendRulesJs(unittest.TestCase):
    def test_legend_rules(self):
        r = subprocess.run(["node", str(HERE / "legendrules_test.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("checks ok", r.stdout)


if __name__ == "__main__":
    unittest.main()
