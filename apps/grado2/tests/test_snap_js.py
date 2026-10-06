"""Привязка надписей в макете листа (web/snap.js), перенос из DesignCraft."""
import shutil
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class SnapJs(unittest.TestCase):
    def test_snap(self):
        r = subprocess.run(["node", str(HERE / "snap_test.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("checks ok", r.stdout)


if __name__ == "__main__":
    unittest.main()
