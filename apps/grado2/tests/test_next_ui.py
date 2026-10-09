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
        new = (src / "maplayers.js").read_text(encoding="utf-8")
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

    def test_graph_nodes_match_working_page(self):
        # схема расчёта: новый интерфейс знает все блоки рабочей страницы (litegraph registerNodeType), схема по умолчанию —
        # та же, что DEFAULT_GRAPH рабочей страницы, и у каждого её блока столько же полей, сколько в описании типа
        web = NEXT.parent
        src = NEXT.parents[1] / "ui" / "src"
        old = set()
        for f in web.glob("*.js"):
            old |= set(re.findall(r'registerNodeType\("([^"]+)"', f.read_text(encoding="utf-8")))
        gf = (src / "graphfile.js").read_text(encoding="utf-8")
        new = set(re.findall(r'^  "([^"/]+/[^"]+)": \{ title', gf, re.M))
        self.assertEqual(old, new)
        g = json.loads((src / "graph_default.json").read_text(encoding="utf-8"))
        self.assertTrue(g["nodes"])
        for n in g["nodes"]:
            self.assertIn(n["type"], new)
        node_ids = {n["id"] for n in g["nodes"]}
        for l in g["links"]:
            self.assertIn(l[1], node_ids)
            self.assertIn(l[3], node_ids)
        exec_src = (src / "graph.js").read_text(encoding="utf-8")
        for t in new:
            self.assertIn(f'"{t}":', exec_src, t)

    def test_sketch_controls_and_windows(self):
        # окно «Эскиз» правит поля блоков схемы по имени: каждое имя есть в описании типов (graphfile.js);
        # каждое окно из меню «Окна» зарегистрировано компонентом в main.js
        src = NEXT.parents[1] / "ui" / "src"
        gf = (src / "graphfile.js").read_text(encoding="utf-8")
        names = set(re.findall(r'\["(?:combo|slider|text|toggle)", "([^"]+)"', gf))
        sk = (src / "sketch.js").read_text(encoding="utf-8")
        used = set(re.findall(r'\bC\(\w+, "([^"]+)"', sk)) | set(re.findall(r'\bwv\(\w+(?:\.\w+)*, "([^"]+)"', sk))
        self.assertTrue(used)
        self.assertLessEqual(used, names)
        app = (src / "App.vue").read_text(encoding="utf-8")
        ids = set(re.findall(r'^  \{ id: "(\w+)", title: "', app, re.M))
        main = (src / "main.js").read_text(encoding="utf-8")
        regs = set(re.findall(r'\.component\("(\w+)"', main))
        self.assertIn("sketch", ids)
        self.assertIn("norms", ids)
        self.assertLessEqual(ids, regs)

    def test_cad_commands_match_work_page(self):
        # черчение нового интерфейса — перенос web/cad.js: те же команды с теми же псевдонимами; на ленте (RIBBON)
        # только существующие команды, у каждой — значок в cadicons.svg
        src = NEXT.parents[1] / "ui" / "src"
        pat = re.compile(r'^def\("(\w+)", "([^"]+)", \[([^\]]*)\]', re.M)
        old = {m[0]: (m[1], m[2]) for m in pat.findall((NEXT.parent / "cad.js").read_text(encoding="utf-8"))}
        cad = (src / "cad.js").read_text(encoding="utf-8")
        new = {m[0]: (m[1], m[2]) for m in pat.findall(cad)}
        self.assertGreater(len(old), 40)
        self.assertEqual(new, old)
        ribbon = re.search(r"export const RIBBON = \{(.*?)\n\};", cad, re.S).group(1)
        ids = set(re.findall(r'"(\w+)"', ribbon))
        self.assertLessEqual(ids, set(new))
        icons = set(re.findall(r'id="ci-(\w+)"', (src / "cadicons.svg").read_text(encoding="utf-8")))
        self.assertLessEqual(ids, icons)

    def test_map_search_matches_working_page(self):
        # поиск над картой — перенос web/app.js: тот же адрес сервера, те же тексты ошибок поиска и вопрос перед заменой границы
        old = (NEXT.parent / "app.js").read_text(encoding="utf-8")
        new = (NEXT.parents[1] / "ui" / "src" / "panels" / "MapSearch.vue").read_text(encoding="utf-8")
        self.assertIn("/api/search?q=", new)
        msgs = lambda t: re.findall(r'\? "([^"]+)"\n', re.search(r"const srchErr = .*?;\s*};", t, re.S).group(0))
        self.assertTrue(msgs(old))
        self.assertEqual(msgs(old), msgs(new))
        for s in ("Заменить вашу границу участками?", "Заменить вашу границу контуром КРТ?", "Сделать границей территории"):
            self.assertIn(s, old)
            self.assertIn(s, new)

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
