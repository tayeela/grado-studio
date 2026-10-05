"""Подписи листа (web/labelfmt.js): станции «ст. ж/д …» и кавычки-ёлочки."""
import shutil
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class LabelFmtJs(unittest.TestCase):
    def test_station_and_quotes(self):
        r = subprocess.run(["node", str(HERE / "labelfmt_test.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("checks ok", r.stdout)


if __name__ == "__main__":
    unittest.main()
