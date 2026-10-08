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

    def test_saves_like_working_page(self):
        # новый интерфейс пишет проект теми же адресами, что рабочая страница: под именем и автосохранение
        js = (NEXT / "assets" / "index.js").read_text(encoding="utf-8")
        self.assertIn("/api/projects", js)
        self.assertIn("/api/project?autosave=1", js)
        self.assertIn("/api/project?name=", js)
        self.assertRegex(js, r"method:\s*[\"'`]POST")

    def test_save_keeps_unknown_fields(self):
        # запись идёт из полного файла (project.raw): граф, альбом и виды, которых новый интерфейс не знает, не теряются
        src = (NEXT.parents[1] / "ui" / "src" / "project.js").read_text(encoding="utf-8")
        self.assertIn("...raw,", src)
        self.assertIn("data: project.data", src)          # данные слоёв — тот же объект, что прочитан из файла (store.setProject)
        self.assertIn("territory: project.territory", src)

    def test_symbology_matches_working_page(self):
        # оформление нового интерфейса рисует файл проекта теми же цветами: палитры категорий и шкал как в web/layers.js
        old = (NEXT.parent / "layers.js").read_text(encoding="utf-8")
        new = (NEXT.parents[1] / "ui" / "src" / "symbology.js").read_text(encoding="utf-8")
        for name in ("CAT", "RAMPS"):
            m = re.search(r"const " + name + r" = (\[[^\]]+\]|\{[^;]+\})", old)
            self.assertTrue(m, name)
            flat = lambda t: re.findall(r"#[0-9a-f]{6}", t)
            self.assertEqual(flat(m.group(1)), flat(re.search(r"export const " + name + r" = (\[[^\]]+\]|\{[^;]+\})", new).group(1)), name)

    def test_basemaps_and_exports_match_working_page(self):
        # подложки — те же адреса плиток, выгрузка — те же адреса сервера, что у рабочей страницы (web/app.js)
        old = (NEXT.parent / "app.js").read_text(encoding="utf-8")
        src = NEXT.parents[1] / "ui" / "src"
        new = (src / "panels" / "MapPanel.vue").read_text(encoding="utf-8")
        tiles = lambda t: sorted(set(re.findall(r'url: "(https://[^"]+)"', t)))
        self.assertEqual(tiles(old), tiles(new))
        exp = (src / "exports.js").read_text(encoding="utf-8")
        for path in ("/api/export/dxf", "/api/export/geojson"):
            self.assertIn(path, old)
            self.assertIn(path, exp)

    def test_data_window_matches_working_page(self):
        # окно «Данные»: тот же опорный порядок слоёв (web/layers.js PREFERRED), те же адреса сервера и те же правила
        # перевыгрузки (ваши правки сильнее источника, удалённое не возвращается), что у рабочей страницы
        web = NEXT.parent
        new = (NEXT.parents[1] / "ui" / "src" / "data.js").read_text(encoding="utf-8")
        pref = lambda t: re.search(r"const PREFERRED = (\[[^\]]+\])", t).group(1)
        self.assertEqual(re.findall(r'"([^"]+)"', pref((web / "layers.js").read_text(encoding="utf-8"))), re.findall(r'"([^"]+)"', pref(new)))
        old = (web / "app.js").read_text(encoding="utf-8")
        for s in ("/api/fetch", "/api/progress", "/api/import/files", "/api/search/cadastral" if "/api/search/cadastral" in new else "/api/search",
                  "ваши правки (", "удалённые вами (", "Нет в источнике"):
            self.assertIn(s.split("/cadastral")[0], old, s)
            self.assertIn(s, new, s)

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
