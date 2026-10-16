"""Ночная выгрузка ГИС ОГД и ЕГКО (ogd_warm.py): порядок слоёв, утренний стоп, список неудач, один прогон за раз,
запуск сайтом сразу (16.10.2026)."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ogd_warm as W  # noqa: E402
from grado_connectors.contract import ConnectorError  # noqa: E402


class Warm(unittest.TestCase):
    def test_stale_layers_oldest_first_fresh_skipped(self):
        items = [{"code": c} for c in ("fresh", "old", "none", "older")]
        ages = {"fresh": 3600, "old": 30 * 3600, "none": float("inf"), "older": 90 * 3600}
        self.assertEqual([it["code"] for it in W.stale(items, ages.get)], ["none", "older", "old"])

    def test_morning_stops_new_layers(self):
        at = lambda h: datetime(2026, 10, 17, h, 0, tzinfo=timezone.utc)
        self.assertFalse(W.late(at(0)))
        self.assertTrue(W.late(at(W.UNTIL)))
        self.assertFalse(W.late(at(15)))            # запуск вручную днём не ограничен

    def test_run_counts_failures_and_respects_limit(self):
        got = []

        class Api:
            def fetch(self, bbox, code):
                got.append(code)
                if code == "bad":
                    raise ConnectorError("портал не ответил")
        failed, st = {"skip": {"at": 9e18, "why": "x"}}, {"got": 0, "err": 0, "left": 0}
        todo = [{"code": c} for c in ("skip", "a", "bad", "b", "c")]
        with mock.patch.object(W, "busy", return_value=False), mock.patch.object(W, "late", return_value=False):
            W.run(todo, Api(), failed, 0, 3, 1, "тест", st)
        self.assertEqual(got, ["a", "bad", "b"])         # «skip» сутки не повторяется, после трёх — предел
        self.assertEqual(st, {"got": 2, "err": 1, "left": 1})
        self.assertIn("bad", failed)


class WarmStart(unittest.TestCase):
    def test_second_run_exits_while_lock_held(self):
        import fcntl
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            held = open(Path(d) / "warm.lock", "w")
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with mock.patch.object(sys, "argv", ["ogd_warm.py", "--cache", d]), \
                 mock.patch.object(W, "catalog", side_effect=AssertionError("второй прогон пошёл на портал")):
                W.main()
            self.assertFalse((Path(d) / "warm_status.json").exists())
            held.close()

    def test_site_starts_warm_only_when_no_fresh_result(self):
        import os
        import tempfile
        import server
        with tempfile.TemporaryDirectory() as d, mock.patch("subprocess.Popen") as popen:
            env = {"GRADO2_PUBLIC_HOST": "grado.example"}
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GRADO2_PUBLIC_HOST", None)
                self.assertIsNone(server.start_warm(8650, d))        # программа на Маке — не начинает
            with mock.patch.dict(os.environ, env), mock.patch.object(server, "GUEST", True):
                self.assertIsNone(server.start_warm(8650, d))        # гостевая копия — не начинает
            with mock.patch.dict(os.environ, env):
                server.start_warm(8650, d)
                self.assertEqual(popen.call_count, 1)
                args = popen.call_args[0][0]
                self.assertTrue(args[1].endswith("ogd_warm.py"))
                self.assertEqual(args[2:], ["--cache", d, "--port", "8650"])
                (Path(d) / "warm_status.json").write_text("{}")
                self.assertIsNone(server.start_warm(8650, d))        # итог свежий — второй раз не начинает
                self.assertEqual(popen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
