"""Кэш округа и углы листа в МСК (web/albumgeo.js): T10/T11."""
import shutil
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class AlbumGeoJs(unittest.TestCase):
    def test_cache_and_corners(self):
        r = subprocess.run(["node", str(HERE / "albumgeo_test.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("checks ok", r.stdout)


if __name__ == "__main__":
    unittest.main()
