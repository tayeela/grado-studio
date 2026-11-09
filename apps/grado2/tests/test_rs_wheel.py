"""Модуль Rust ставится сам (rs_wheel.py): версия совпадает с крейтом, колёса берутся из релиза, pip выбирает колесо
под систему без интернета (--no-index), неудача не роняет запуск, /api/health показывает grado_rs."""

import json
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rs_wheel  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]


def fake_wheel(d, tag="py3-none-any"):
    """Колесо-пустышка grado_rs WANT: pip примет его как настоящее."""
    name = f"grado_rs-{rs_wheel.WANT}-{tag}.whl"
    di = f"grado_rs-{rs_wheel.WANT}.dist-info"
    with zipfile.ZipFile(d / name, "w") as z:
        z.writestr("grado_rs/__init__.py", f"__version__ = '{rs_wheel.WANT}'\n")
        z.writestr(f"{di}/METADATA", f"Metadata-Version: 2.1\nName: grado_rs\nVersion: {rs_wheel.WANT}\n")
        z.writestr(f"{di}/WHEEL", f"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: {tag}\n")
        z.writestr(f"{di}/RECORD", "")
    return d / name


class RsWheel(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        p = mock.patch.object(rs_wheel, "LOCK", self.tmp / "lock")
        p.start()
        self.addCleanup(p.stop)

    def release(self, *wheels):
        rel = {"assets": [{"name": w.name, "browser_download_url": w.as_uri()} for w in wheels]
               + [{"name": "notes.txt", "browser_download_url": "file:///nope"}]}
        f = self.tmp / "release.json"
        f.write_text(json.dumps(rel))
        return f.as_uri()

    def test_want_is_the_crate_version(self):
        toml = (ROOT / "rust/crates/py/Cargo.toml").read_text("utf-8")
        self.assertEqual(rs_wheel.WANT, re.search(r'^version = "([^"]+)"', toml, re.M).group(1))

    def test_release_lists_only_wheels(self):
        d = self.tmp / "w"
        d.mkdir()
        api = self.release(fake_wheel(d))
        self.assertEqual([n for n, _ in rs_wheel.wheel_urls(api)], [f"grado_rs-{rs_wheel.WANT}-py3-none-any.whl"])

    def test_install_downloads_and_pip_picks_the_wheel_offline(self):
        d = self.tmp / "w"
        d.mkdir()
        api = self.release(fake_wheel(d), fake_wheel(d, "cp310-abi3-win_amd64"))
        seen, real = {}, subprocess.run

        def run(cmd, **kw):
            seen["cmd"] = cmd
            # тот же вызов pip, но без установки: проверка, что колесо из скачанной папки подходит
            return real(cmd + ["--dry-run", "--target", str(self.tmp / "t")], **kw)

        logs = []
        with mock.patch.object(rs_wheel, "installed", return_value=None), mock.patch.object(rs_wheel.subprocess, "run", run):
            ok = rs_wheel.install(api=api, log=logs.append)
        self.assertTrue(ok, logs)
        self.assertIn("--no-index", seen["cmd"])
        self.assertIn(f"grado_rs=={rs_wheel.WANT}", seen["cmd"])
        self.assertFalse(rs_wheel.LOCK.exists())

    def test_no_release_means_python_and_a_log_line(self):
        logs = []
        with mock.patch.object(rs_wheel, "installed", return_value=None), mock.patch.object(rs_wheel.time, "sleep"):
            ok = rs_wheel.install(api=(self.tmp / "missing.json").as_uri(), log=logs.append)
        self.assertFalse(ok)
        self.assertIn("работаю на Python", logs[0])
        self.assertFalse(rs_wheel.LOCK.exists())

    def test_second_copy_waits_for_the_first(self):
        rs_wheel.LOCK.write_text("")
        logs = []
        with mock.patch.object(rs_wheel, "installed", return_value=None):
            self.assertFalse(rs_wheel.install(api="file:///nope", log=logs.append))
        self.assertIn("другая копия", logs[0])

    def test_background_is_skipped_when_not_needed(self):
        with mock.patch.object(rs_wheel, "installed", return_value=rs_wheel.WANT):
            self.assertIsNone(rs_wheel.ensure_background())
        with mock.patch.object(rs_wheel, "installed", return_value=None):
            self.assertIsNone(rs_wheel.ensure_background(frozen=True))
            with mock.patch.dict("os.environ", {"GRADO_RS_AUTO": "0"}):
                self.assertIsNone(rs_wheel.ensure_background())

    def test_health_names_the_module(self):
        import server as S
        r = S.get_health(None)
        self.assertIn("grado_rs", json.loads(r.body))


if __name__ == "__main__":
    unittest.main()
