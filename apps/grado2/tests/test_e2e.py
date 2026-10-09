"""Browser scenarios of docs/ux/grado2-ux.md in headless Chrome (tests/e2e/scenarios.mjs).

Opt-in because it takes about a minute: set GRADO2_E2E=1 (CI does). Needs node 22+ and Chrome
(env CHROME or the default macOS path). A throw-away server runs on a free port with a temporary projects folder,
so the owner's projects are never touched.
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHROME = os.environ.get("CHROME") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _failure(r):
    """Why a scenario failed: the full list of failed steps (STEP FAILED / FAILED #k / SUMMARY lines, none cut), then every other
    line that is not "ok - …" (console errors), the last 4000 characters of stdout and the tail of stderr.
    A plain tail of stdout cut the cause off once the output grew past it, and a passed check got the blame."""
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    steps = [ln for ln in lines if ln.startswith(("STEP FAILED", "  FAILED #", "SUMMARY:"))]
    other = [ln for ln in lines if not ln.startswith("ok - ") and ln not in steps]
    return ("\n".join(steps)[-20000:] + "\n--- other non-ok lines ---\n" + "\n".join(other)[-4000:]
            + "\n--- last 4000 chars of stdout ---\n" + r.stdout[-4000:] + "\n--- stderr ---\n" + r.stderr[-2000:])


def _summary(r):
    """SUMMARY line and failed step names, printed even when the run passes."""
    return "\n".join(ln for ln in r.stdout.splitlines() if ln.startswith(("SUMMARY:", "  FAILED #")))


@unittest.skipUnless(os.environ.get("GRADO2_E2E") == "1" and shutil.which("node") and Path(CHROME).exists(),
                     "set GRADO2_E2E=1; needs node and Chrome")
class BrowserScenarios(unittest.TestCase):
    def test_owner_scenarios(self):
        port = _free_port()
        with tempfile.TemporaryDirectory() as projects:
            env = {**os.environ, "GRADO2_NO_BROWSER": "1", "GRADO2_PROJECTS": projects}
            srv = subprocess.Popen([sys.executable, str(HERE.parent / "server.py"), str(port)], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(100):
                    try:
                        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)
                        break
                    except Exception:
                        time.sleep(0.1)
                r = subprocess.run(["node", str(HERE / "e2e/driver.mjs"), f"http://127.0.0.1:{port}/old", str(HERE / "e2e/scenarios.mjs")],
                                   capture_output=True, text=True, timeout=600, env={**os.environ, "CHROME": CHROME})
                print(r.stdout[-4000:])
                print(_summary(r))
                self.assertEqual(r.returncode, 0, _failure(r))
            finally:
                srv.terminate()
                srv.wait(10)

    def test_collab_scenario(self):
        """Два браузера, один общий проект (tests/e2e/collab_scenarios.mjs): вход, доступ, живая синхронизация, комментарии, история, роли."""
        port = _free_port()
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "GRADO2_NO_BROWSER": "1", "GRADO2_PROJECTS": str(Path(tmp) / "projects"), "GRADO2_HUB_DIR": str(Path(tmp) / "hub")}
            hub = str(HERE.parent / "hub.py")
            admin_pw = "e2e-admin-pass-1"
            subprocess.run([sys.executable, hub, "adduser", "anna", "--admin", "--name", "Анна"], input=admin_pw + "\n", env=env,
                           text=True, check=True, capture_output=True)
            invite = subprocess.run([sys.executable, hub, "invite"], env=env, text=True, check=True, capture_output=True).stdout.strip()
            srv = subprocess.Popen([sys.executable, str(HERE.parent / "server.py"), str(port), "--hub"], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(100):
                    try:
                        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)
                        break
                    except Exception:
                        time.sleep(0.1)
                r = subprocess.run(["node", str(HERE / "e2e/collab_scenarios.mjs"), f"http://127.0.0.1:{port}/old"],
                                   capture_output=True, text=True, timeout=600,
                                   env={**os.environ, "CHROME": CHROME, "E2E_ADMIN_PW": admin_pw, "E2E_INVITE": invite})
                print(r.stdout[-4000:])
                print(_summary(r))
                self.assertEqual(r.returncode, 0, _failure(r))
            finally:
                srv.terminate()
                srv.wait(10)


if __name__ == "__main__":
    unittest.main()
