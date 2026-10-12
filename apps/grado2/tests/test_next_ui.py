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
        blds = lambda t: re.search(r"const BUILDINGS = (\[[^\]]+\])", t).group(1)
        self.assertEqual(blds((web / "layers.js").read_text(encoding="utf-8")), blds(new))   # «Упорядочить слои»: те же слои застройки
        self.assertEqual(re.findall(r'"([^"]+)"', pref((web / "layers.js").read_text(encoding="utf-8"))), re.findall(r'"([^"]+)"', pref(new)))
        old = (web / "app.js").read_text(encoding="utf-8")
        for s in ("/api/fetch", "/api/progress", "/api/import/files", "/api/search/cadastral" if "/api/search/cadastral" in new else "/api/search",
                  "ваши правки (", "удалённые вами (", "Нет в источнике", "/api/fgistp/docs", "/api/fgistp/layers", "/api/fgistp/fetch"):
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

    def test_collab_matches_working_page(self):
        # совместная работа: та же чистая часть (web/collab.js), те же поля данных слоя и те же адреса общего сервера,
        # иначе новая и рабочая страницы перебрасывались бы одним проектом
        web, src = NEXT.parent, NEXT.parents[1] / "ui" / "src"
        new, old = (src / "collab.js").read_text(encoding="utf-8"), (web / "collab.js").read_text(encoding="utf-8")
        self.assertIn('from "../../web/collab.js"', new)
        fields = lambda t, rx: re.findall(r'"([a-z_]+)"', re.search(rx, t).group(1))
        self.assertLessEqual(set(fields(old, r'for \(const f of (\[[^\]]+\])\) if \(!same\(d\[f\]')), set(fields(new, r"const DATA_F = (\[[^\]]+\])")))
        for k in ('P("/push")', 'P("/sections?names=', 'P("/presence")', 'P("/events")', "canonGraph("):
            self.assertIn(k, new, k)
        ends = lambda t: sorted(set(re.findall(r"\}/([a-z_]+)", t)))
        self.assertEqual(ends((web / "hub.js").read_text(encoding="utf-8")), ends((src / "hub.js").read_text(encoding="utf-8")))

    def test_album_window_is_the_working_page_engine(self):
        # «Листы и альбом» — вкладка нового интерфейса (AlbumPanel.vue); собирает и печатает альбом рабочая страница
        # /old?embed=album — скрытой рамкой iframe или окном «Подробно»; связь — gradoEmbed с обеих сторон и albumApi движка
        web, src = NEXT.parent, NEXT.parents[1] / "ui" / "src"
        host, page = (src / "albumhost.js").read_text(encoding="utf-8"), (web / "project.js").read_text(encoding="utf-8")
        bridge, panel = (web / "albumapi.js").read_text(encoding="utf-8"), (src / "panels" / "AlbumPanel.vue").read_text(encoding="utf-8")
        self.assertIn("/old?embed=album", host)
        self.assertIn('createElement("iframe")', host)                      # обычно движок скрыт внутри страницы, без окна браузера
        called = set(re.findall(r"gradoEmbed\?\.(\w+)\(", page)) | {"toast", "download"}   # albumapi.js: сообщения и файлы
        block = re.search(r"window\.gradoEmbed = \{(.*?)\n\};", host, re.S).group(1)
        given = set(re.findall(r"^  (?:async )?(\w+)\(", block, re.M))
        self.assertEqual(set(re.findall(r"gradoEmbed\?\.(\w+)\(", page)), {"ready", "changed", "focus", "closed", "save", "open"})
        self.assertLessEqual(called, given)
        for fn in ("applyProject", "collectProject", "setTheme"):   # что новый интерфейс зовёт у рабочей страницы
            self.assertIn(f"win.{fn}", host)
        api = set(re.findall(r"^    (?:async )?(\w+)\(", bridge, re.M))
        used = set(re.findall(r"a => a\.(\w+)\(", panel))
        self.assertTrue(used and used <= api, used - api)                   # вкладка зовёт только то, что движок отдаёт
        html = (web / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index('src="embed.js"'), html.index('src="app.js"'))      # класс embed и EMBED — до скриптов страницы
        self.assertLess(html.index('src="albums.js"'), html.index('src="albumapi.js"'))
        app = (src / "App.vue").read_text(encoding="utf-8")
        for k in ("albumFile(v)", "ogdDxf()", "winApi.open('album')", '{ id: "album", title: "Листы и альбом" }'):
            self.assertIn(k, app)

    def test_one_logic_for_sheets_and_frames(self):
        # одна логика везде (владелец 12.10.2026): «Листы и альбом» показывает и создаёт те же листы, что «Макет листа»
        # (project.layouts, новый — пустой, без заготовок по формату); область загрузки — рамка, как рамка вида
        src = NEXT.parents[1] / "ui" / "src"
        panel = (src / "panels" / "AlbumPanel.vue").read_text(encoding="utf-8")
        self.assertIn("blank: true", panel)
        self.assertIn('winApi.open("sheet")', panel)
        self.assertNotIn('value="A1">Лист A1', panel)                    # прежнее «Добавить лист» по формату ушло
        self.assertIn("sheetNav.tick", (src / "panels" / "SheetPanel.vue").read_text(encoding="utf-8"))
        frames, data = (src / "viewframesmap.js").read_text(encoding="utf-8"), (src / "data.js").read_text(encoding="utf-8")
        self.assertIn("setCover(f)", frames)
        self.assertIn("project.raw.cover = { center: f.center, w: f.w, h: f.h }", data)
        self.assertIn("coverOwn() ? frameBbox(project.raw.cover) : autoCoverBox()", data)

    def test_album_frames_on_the_new_map(self):
        # рамки листов альбома на карте нового интерфейса (шаг 2 фаза 2, #94): рамки считает движок (albumapi state().frames —
        # те же sheetCenter, sheetScale, frameMM, что у frames.js), карта рисует их, пока вкладка на виду; сдвиг и угол пишут
        # center и scale листа в раздел album проекта
        web, src = NEXT.parent, NEXT.parents[1] / "ui" / "src"
        bridge = (web / "albumapi.js").read_text(encoding="utf-8")
        for k in ("frames: frames()", "sheetOnMap(s, true)", "sheetCenter(s)", "sheetScale(s)", "frameMM(s)"):
            self.assertIn(k, bridge)
        # с v0.99.96 рамки листов — те же рамки, что у видов (viewframesmap.js, id «alb:…»): одна логика на карте
        frames = (src / "viewframesmap.js").read_text(encoding="utf-8")
        self.assertIn('export const ALB = "alb:"', frames)
        self.assertIn("editSheet(f.i, patch)", frames)
        self.assertIn("sheetFromCorners(drag.a, m, v.mm)", frames)              # угол листа держит пропорции карты листа
        self.assertIn('get("gradoTop")', frames)                           # под перехватом команд черчения, как frames.js
        # #29: на рамке — короткое имя «Лист 5 · А3 · 1:2000», полное название — подсказкой над рамкой
        self.assertIn("label: `${n} · ${fmtT(s)} · 1:${fmt(Math.round(sc))}`, title:", bridge)
        self.assertIn("tip: f.title", frames)
        self.assertIn("watch(() => album.fit", frames)
        self.assertFalse((src / "albumframes.js").exists())
        self.assertIn("export function editSheet(", (src / "albumhost.js").read_text(encoding="utf-8"))
        self.assertIn("export function wantFrames(", (src / "albumhost.js").read_text(encoding="utf-8"))
        panel = (src / "panels" / "AlbumPanel.vue").read_text(encoding="utf-8")
        self.assertIn("album.tab = e.isVisible", panel)
        self.assertIn("album.fit++", panel)

    def test_album_sheet_roles(self):
        # «Слои листа» во вкладке (шаг 2 фаза 2): роли листа считает окно «Слои и листы» движка (SheetLayers.rows — те же
        # roleRows, queueRows, покрытие рамки), глаз и «вернуть к образцу» — его toggleRole и resetRoleUI (с отменой Cmd+Z)
        web, src = NEXT.parent, NEXT.parents[1] / "ui" / "src"
        sl = (web / "sheetlayers.js").read_text(encoding="utf-8")
        self.assertIn("function rows(idx)", sl)
        self.assertRegex(sl, r"window\.SheetLayers = \{[^}]*\brows\b")
        bridge = (web / "albumapi.js").read_text(encoding="utf-8")
        for k in ("SheetLayers?.rows(i)", "SheetLayers?.toggleRole(i, gid)", "SheetLayers?.resetRoleUI(i, gid)"):
            self.assertIn(k, bridge)
        panel = (src / "panels" / "AlbumPanel.vue").read_text(encoding="utf-8")
        for k in ("a.roles(i)", "a.role(cur.value, r.id)", "a.resetRole(cur.value, r.id)"):
            self.assertIn(k, panel)

    def test_album_photos_and_satellite(self):
        # фотофиксация и спутник во вкладке (шаг 2 фаза 2, #94): снимки — тем же addPhotoFiles движка (1600 px, GPS из EXIF, до 12),
        # спутник — тем же satFile, только папку загрузок спрашивает окно нового интерфейса, а не prompt скрытой страницы
        web, src = NEXT.parent, NEXT.parents[1] / "ui" / "src"
        bridge = (web / "albumapi.js").read_text(encoding="utf-8")
        for k in ("photos(i)", "addPhotoFiles(i, [...files])", "dropPhoto(i, k)", "satFile(i, false, dir)", "dlDir()"):
            self.assertIn(k, bridge)
        self.assertIn("async function satFile(i, ask, dir0)", (web / "sheets.js").read_text(encoding="utf-8"))
        panel = (src / "panels" / "AlbumPanel.vue").read_text(encoding="utf-8")
        for k in ("a.addPhotos(cur.value, files)", "a.dropPhoto(cur.value, k)", "a.sat(cur.value, dir)", 'data-act="sat"', 'data-act="photo"', "/api/progress"):
            self.assertIn(k, panel)

    def test_album_sheet_layers_drag(self):
        # перетаскивание во вкладке: роль на лист, слой проекта на лист или строку роли, очередь источников — правила и действия
        # с отменой берутся у окна «Слои и листы» движка (SheetLayout.dropCheck, dropRole, dropLayer, reorderQueue)
        web, src = NEXT.parent, NEXT.parents[1] / "ui" / "src"
        sl = (web / "sheetlayers.js").read_text(encoding="utf-8")
        for k in ("function check(to, w, copy)", "function drop(to, w, copy)", "function bank()", "reorderQueue(i, gid, from, to)"):
            self.assertIn(k, sl)
        self.assertRegex(sl, r"window\.SheetLayers = \{[^}]*\bcheck, drop, bank, reorder\b")
        bridge = (web / "albumapi.js").read_text(encoding="utf-8")
        for k in ("SheetLayers?.check(to, what, copy)", "SheetLayers?.drop(to, what, copy)", "SheetLayers?.bank()", "SheetLayers?.reorder(i, gid, from, to)"):
            self.assertIn(k, bridge)
        panel = (src / "panels" / "AlbumPanel.vue").read_text(encoding="utf-8")
        for k in ("a.dropCheck(i,", "a.drop(i, w, copy)", "a.reorderSrc(cur.value, r.id, from, to)", "a.bank()", '@drop="e => dropOn(e, i)"'):
            self.assertIn(k, panel)

    def test_album_without_popup_window(self):
        # окна браузера «Подробно» больше нет (шаг 2 фаза 2, #94): импорт из файла, содержание листа, «В центр», масштаб схем,
        # формат слайдов и «ГИС ОГД в DXF» — во вкладке и окне «Данные»; движок по-прежнему скрытая рамка (лист в лист прежний PDF)
        web, src = NEXT.parent, NEXT.parents[1] / "ui" / "src"
        host = (src / "albumhost.js").read_text(encoding="utf-8")
        self.assertNotIn("openAlbum", host)
        self.assertNotIn("window.open(", host)
        panel = (src / "panels" / "AlbumPanel.vue").read_text(encoding="utf-8")
        self.assertNotRegex(panel, r"<wa-button[^>]*>[^<]*Подробно")
        for k in ("a.importFile(f)", "a.importAnswer('replace')", "a.importAnswer('add')", "a.setView(cur, e.target.value)",
                  "a.resetCenter(cur)", "a.setScheme(v)", "a.setSlide(e.target.value)"):
            self.assertIn(k, panel)
        bridge = (web / "albumapi.js").read_text(encoding="utf-8")
        for k in ("importFile(file) { return readAlbumFile(file); }", "importAnswer(mode) { return importAlbum(mode); }",
                  "setView(i, v)", "resetCenter(i)", "setSlide(v)", "setScheme(v)", "ogdSheet(i)", "keepOgd(codes)"):
            self.assertIn(k, bridge)
        # «ГИС ОГД в DXF»: лист из движка, выбор слоёв портала в окне «Данные», выгрузка фоном на сервере, ход после перезагрузки
        self.assertIn("a.ogdSheet(album.cur)", host)
        data = (src / "data.js").read_text(encoding="utf-8")
        for k in ('"/api/ogd_all/start"', '"/api/ogd_all/status"', '"/api/ogd_all/cancel"', '"/api/ogd_all/file"', "export function ogdResume()"):
            self.assertIn(k, data)
        dp = (src / "panels" / "DataPanel.vue").read_text(encoding="utf-8")
        for k in ('data-act="ogd-dxf"', "a.keepOgd(codes)", "startOgd(", 'class="job ogdjob"'):
            self.assertIn(k, dp)
        self.assertIn("ogdResume();", (src / "App.vue").read_text(encoding="utf-8"))

    def test_album_label_layout_window(self):
        # «Макет надписей» (шаг 2 фаза 2): лист — картинка печати по запросу движка (albumApi.spec), правки — в лист альбома
        # (edits, items, layGuides) через editSheet; направляющие переживают пересборку листа по шаблону (sheets.js carryHand)
        web, src = NEXT.parent, NEXT.parents[1] / "ui" / "src"
        self.assertIn("spec(i) {", (web / "albumapi.js").read_text(encoding="utf-8"))
        self.assertIn("if (old.layGuides) fresh.layGuides = old.layGuides;", (web / "sheets.js").read_text(encoding="utf-8"))
        lay = (src / "panels" / "AlbumLayout.vue").read_text(encoding="utf-8")
        for k in ("a.spec(idx.value)", "/api/print/svg", "Snap.snap(", "editSheet(idx.value, patch)", "layGuides", "function alignSel"):
            self.assertIn(k, lay)
        self.assertIn('.component("albumlay", AlbumLayout)', (src / "main.js").read_text(encoding="utf-8"))
        self.assertIn('{ id: "albumlay", title: "Макет надписей" }', (src / "App.vue").read_text(encoding="utf-8"))
        self.assertIn('winApi.open("albumlay")', (src / "panels" / "AlbumPanel.vue").read_text(encoding="utf-8"))
        host = (src / "albumhost.js").read_text(encoding="utf-8")
        # правка листа сначала принимает отложенную правку окна: иначе pull() заменит раздел album и унесёт её
        self.assertRegex(host, r"export function editSheet\(i, patch\) \{\s*//[^\n]*\n\s*if \(timer\) \{ clearTimeout\(timer\); timer = null; pull\(\); \}")

    def test_floating_windows_follow_the_mouse(self):
        # плавающее окно идёт ровно за мышью, угол не сдвигает край (docs/ux/ui-grid.md): заплатка dockview ставится при npm ci
        # и попадает в сборку; без неё окно отставало на первое движение мыши (владелец 09.10.2026: «окна перемещаются криво»)
        ui = NEXT.parents[1] / "ui"
        pkg = json.loads((ui / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(pkg["scripts"]["postinstall"], "patch-package")
        patch = (ui / "patches" / "dockview-core+8.4.1.patch").read_text(encoding="utf-8")
        self.assertIn("track(dragTarget, event.pointerId, event)", patch)
        js = "".join(p.read_text(encoding="utf-8") for p in (NEXT / "assets").glob("*.js"))
        self.assertIn("originalTop", js)

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
