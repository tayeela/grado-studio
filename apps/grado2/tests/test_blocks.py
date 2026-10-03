"""Runs the JavaScript urban-block insolation checks (blocks_test.js) under node, so they are part of the unittest gate."""

import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class UrbanBlocks(unittest.TestCase):
    def test_blocks_js(self):
        r = subprocess.run(["node", str(Path(__file__).with_name("blocks_test.js"))], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        self.assertIn("все проверки пройдены", r.stdout)


if __name__ == "__main__":
    unittest.main()
