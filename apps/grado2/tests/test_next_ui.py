"""Новый интерфейс (/next/, #69): собранная страница лежит в web/next и проходит CSP сервера.

Запуск: PYTHONPATH=apps/grado2 python -m unittest apps/grado2/tests/test_next_ui.py
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402

NEXT = Path(__file__).resolve().parents[1] / "web" / "next"


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


if __name__ == "__main__":
    unittest.main()
