"""Runs the JavaScript insolation checks (insol_test.js) under node, so they are part of the unittest gate."""

import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Insolation(unittest.TestCase):
    def test_insolation_js(self):
        r = subprocess.run(["node", str(Path(__file__).with_name("insol_test.js"))], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        self.assertIn("все проверки пройдены", r.stdout)


if __name__ == "__main__":
    unittest.main()
