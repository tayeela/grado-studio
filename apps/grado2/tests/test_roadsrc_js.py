"""Источник дорог листа (web/roadsrc.js): полигоны Яндекса или запасной источник."""
import shutil
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class RoadSrcJs(unittest.TestCase):
    def test_pick_road_source(self):
        r = subprocess.run(["node", str(HERE / "roadsrc_test.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("checks ok", r.stdout)


if __name__ == "__main__":
    unittest.main()
