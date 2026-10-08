"""Новый интерфейс (/next/, #69): собранная страница лежит в web/next и проходит CSP сервера.

Запуск: PYTHONPATH=apps/grado2 python -m unittest apps/grado2/tests/test_next_ui.py
"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402

NEXT = Path(__file__).resolve().parents[1] / "web" / "next"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "next_ui_project.grado2"


class NextUi(unittest.TestCase):
    def test_page_and_assets_exist(self):
        html = (NEXT / "index.html").read_text(encoding="utf-8")
        for ref in re.findall(r'(?:src|href)="\./([^"]+)"', html):
            self.assertTrue((NEXT / ref).is_file(), ref)
        self.assertIn("./assets/index.js", html)

    def test_no_inline_script(self):
        # CSP script-src 'self': встроенный скрипт браузер не выполнит
        html = (NEXT / "index.html").read_text(encoding="utf-8")
        for tag in re.findall(r"<script\b[^>]*>", html):
            self.assertIn("src=", tag)

    def test_csp_allows_icon_data_urls(self):
        # значки Web Awesome читаются fetch из data:-адресов
        connect = next(p for p in S.CSP.split(";") if p.strip().startswith("connect-src"))
        self.assertIn("data:", connect)
        self.assertNotIn("unsafe-eval", S.CSP)

    def test_reads_projects_never_writes(self):
        # новый интерфейс пока только просматривает проект: читает список и файл, ничего не отправляет на сервер
        js = (NEXT / "assets" / "index.js").read_text(encoding="utf-8")
        self.assertIn("/api/projects", js)
        self.assertIn("/api/project?autosave=1", js)
        self.assertNotRegex(js, r"method:\s*[\"']POST")

    def test_fixture_project_shape(self):
        # тестовый проект для снимков нового окна «Слои»: у каждого слоя есть данные и известная группа
        p = json.loads(FIXTURE.read_text(encoding="utf-8"))
        groups = {g["id"] for g in p["groups"]}
        self.assertTrue(p["layers"])
        for l in p["layers"]:
            self.assertIn(l["key"], p["data"], l["key"])
            self.assertIn(l["group"], groups, l["key"])
            self.assertIn(l["geom"], ("point", "line", "poly"))


if __name__ == "__main__":
    unittest.main()
