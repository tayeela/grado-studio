"""The browser copy of the working МСК (web/msk.js — the owner's QGIS «МСК», MSK_PROJ4) must agree with PROJ and with
the core (grado_connectors.crs): the status bar, typed X;Y and drawing lengths use it; DXF and sheets are written by the core."""
import json
import math
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "core/connectors"))
sys.path.insert(0, str(ROOT / "core/connectors/tests"))
from grado_connectors.crs import wgs84_to_msk  # noqa: E402
from test_crs import MSK_PROJ  # noqa: E402  (эталон PROJ, 20 точек Москвы)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class MskBrowserCopy(unittest.TestCase):
    def run_js(self):
        pts = [p for p, _ in MSK_PROJ]
        js = ("const M=require(%s),P=%s,X=%s;console.log(JSON.stringify(P.map((p,i)=>[M.fromWgs(p),M.toWgs(X[i])])))"
              % (json.dumps(str(ROOT / "apps/grado2/web/msk.js")), json.dumps(pts), json.dumps([m for _, m in MSK_PROJ])))
        return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)

    def test_matches_proj_to_a_millimetre(self):
        for ((lon, lat), (ex, ey)), (m, back) in zip(MSK_PROJ, self.run_js()):
            self.assertLess(math.hypot(m[0] - ex, m[1] - ey), 0.001, f"{lon},{lat}")
            d = math.hypot((back[0] - lon) * 111320 * math.cos(math.radians(lat)), (back[1] - lat) * 110540)
            self.assertLess(d, 0.001, f"{lon},{lat} обратно")

    def test_matches_core(self):
        for ((lon, lat), _), (m, _b) in zip(MSK_PROJ, self.run_js()):
            x, y = wgs84_to_msk(lon, lat)
            self.assertLess(math.hypot(m[0] - x, m[1] - y), 0.0001)


if __name__ == "__main__":
    unittest.main()
