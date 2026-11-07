"""Тесты мини-журнала gravlog.py (аудит 06.11, п. 4.2): формат «ГГГГ-ММ-ДД ЧЧ:ММ:СС [LEVEL] [компонент] текст»,
файл с ротацией и stderr без дублей, молчаливый stderr-режим при нечитаемом ~/.grado2, подключение сервера."""

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gravlog  # noqa: E402

STAMP = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"


class Gravlog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "server.log"

    def tearDown(self):
        gravlog._reset()
        getattr(self, "env", None) and self.env.stop()
        self.tmp.cleanup()

    def to(self, path=None):
        """Собрать журнал заново с путём path (GRADO2_LOG): тесты не пишут в настоящий журнал владельца."""
        self.env = mock.patch.dict(os.environ, {"GRADO2_LOG": str(path or self.path)})
        self.env.start()
        gravlog._reset()
        return gravlog.get("save")

    def test_format_and_both_streams_without_duplication(self):
        with mock.patch("sys.stderr", new=io.StringIO()) as err:
            log = self.to()
            log.info("проект записан")
            gravlog.get("portal").warning("place: портал не ответил")
        text = self.path.read_text("utf-8")
        self.assertRegex(text.splitlines()[0], rf"^{STAMP} \[INFO\] \[save\] проект записан$")
        self.assertRegex(text.splitlines()[1], rf"^{STAMP} \[WARNING\] \[portal\] place: портал не ответил$")
        self.assertEqual(text.count("[save] проект записан"), 1)
        self.assertEqual(err.getvalue().count("[save] проект записан"), 1)   # в stderr тоже ровно один раз, не по два
        self.assertIn("[portal] place: портал не ответил", err.getvalue())

    def test_file_rotates_at_one_megabyte(self):
        with mock.patch("sys.stderr", new=io.StringIO()):                     # шум ротации не сыпется в вывод тестов
            log = self.to()
            line = "заполнение " * 10
            for _ in range(20000):                                            # ~2 МБ — за первый предел
                log.info(line)
        self.assertTrue((self.path.parent / "server.log.1").exists())         # запасные файлы появились

    def test_unwritable_dir_leaves_stderr_only_and_does_not_raise(self):
        deny = Path(self.tmp.name) / "deny"
        deny.mkdir()
        os.chmod(deny, 0o500)
        try:
            with mock.patch("sys.stderr", new=io.StringIO()) as err:
                log = self.to(deny / "server.log")
                log.error("сервер жив")                                       # не падает из-за журнала
            self.assertRegex(err.getvalue(), r"\[ERROR\] \[save\] сервер жив")
            self.assertEqual(list(deny.iterdir()), [])                        # файла не появилось
        finally:
            os.chmod(deny, 0o700)

    def test_server_wires_log_line_and_save_info(self):
        import server as S
        with tempfile.TemporaryDirectory() as d, mock.patch.object(S, "PROJECTS", Path(d)):
            self.to()
            S._log_line("GET /api/x: ValueError: бой", warn=True)
            S.save_project("Про", b'{"v": 1}')
        text = self.path.read_text("utf-8")
        self.assertRegex(text, r"\[WARNING\] \[http\] GET /api/x: ValueError: бой")
        self.assertRegex(text, r"\[INFO\] \[save\] проект «Про» записан: \d+ Б, \d+\.\d+ с")

    def test_human_sizes(self):
        self.assertEqual(gravlog.human(891), "891 Б")
        self.assertEqual(gravlog.human(456_000), "456 КБ")
        self.assertRegex(gravlog.human(12_300_000), r"12\.3 МБ")
