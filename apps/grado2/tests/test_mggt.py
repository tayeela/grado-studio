"""The browser copy of the Moscow МГГТ transform (web/mggt.js) must agree with the core (grado_connectors.crs):
the status bar, typed coordinates and drawing lengths use it, and DXF/sheets are written by the core."""
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "core/connectors"))
from grado_connectors.crs import wgs84_to_msk50  # noqa: E402

POINTS = [(37.52, 55.79), (37.265, 55.427), (37.62, 55.75), (37.9, 55.9), (36.9, 55.2)]


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class MggtBrowserCopy(unittest.TestCase):
    def test_matches_core_to_a_millimetre(self):
        js = ("const M=require(%s);console.log(JSON.stringify(%s.map(p=>{const m=M.fromWgs(p);return [m,M.toWgs(m)]})))"
              % (json.dumps(str(ROOT / "apps/grado2/web/mggt.js")), json.dumps(POINTS)))
        out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
        for p, (m, back) in zip(POINTS, out):
            e, n = wgs84_to_msk50(*p)
            self.assertAlmostEqual(m[0], e, delta=0.001)
            self.assertAlmostEqual(m[1], n, delta=0.001)
            self.assertAlmostEqual(back[0], p[0], delta=1e-8)   # about 1 mm
            self.assertAlmostEqual(back[1], p[1], delta=1e-8)


if __name__ == "__main__":
    unittest.main()
