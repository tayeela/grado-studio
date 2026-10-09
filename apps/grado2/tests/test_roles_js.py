"""Roles of layers in calculations (web/roles.js): node checks and agreement with server.py (/api/layer_roles)."""
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import server as S  # noqa: E402


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class RolesJs(unittest.TestCase):
    def test_roles_resolver(self):
        r = subprocess.run(["node", str(HERE / "roles_test.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("checks ok", r.stdout)

    def test_source_table_same_as_server(self):
        r = subprocess.run(["node", "-e", "console.log(JSON.stringify(require('./web/roles.js').SOURCE_ROLE))"], cwd=HERE.parent, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), S.SOURCE_ROLES)


class LayerRolesApi(unittest.TestCase):
    def test_codes_follow_sources(self):
        j = S.layer_roles()
        self.assertEqual(set(j), {"sources", "codes", "titles"})
        for src in ("gisogd.pzz_sub", "gisogd.zouit", "gisogd.szz", "gisogd.okn", "gisogd.func_zones_tinao"):
            for code in S.SOURCES[src][1]:
                self.assertEqual(j["codes"][code], S.SOURCE_ROLES[src], (src, code))
        # codes seen in the owner's project (names checked against the layer titles of the Bezobrazovo copy)
        want = {"virtual130": "pzz_zones", "virtual132": "pzz_sub", "virtual1976": "func_zones", "virtual1970": "func_zones", "virtual109": "zouit",
                "virtual111": "zouit", "virtual1521": "zouit", "virtual2383": "zouit", "virtual2386": "zouit", "oozt_08_12_2017": "zouit",
                "virtual123": "zouit", "zu_29_06_2021": "parcels"}
        for code, role in want.items():
            self.assertEqual(j["codes"].get(code), role, code)
        self.assertEqual(j["titles"]["virtual1976"], "Природная зона")

    def test_unverified_and_border_codes_stay_unmapped(self):
        codes = S.layer_roles()["codes"]
        for code in ("l16", "l17", "l41", "l1", "gpzu", "pmtgk", "virtual84", "virtual87"):   # water-zone borders are not red lines; the rest is «не проверено»
            self.assertNotIn(code, codes, code)

    def test_over_http(self):
        import threading
        import urllib.request
        srv = S.Server(("127.0.0.1", 0))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/api/layer_roles", timeout=5) as r:
                j = json.loads(r.read())
            self.assertEqual(j["codes"]["virtual132"], "pzz_sub")
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
