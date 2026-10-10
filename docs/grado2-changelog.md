# ГРАДО 2 — журнал изменений

New entries go on top. Moved out of CLAUDE.md on 2026-09-24 (it was loaded into every agent turn).

- **2026-10-10, ГРАДО 2 v0.99.79: установщик Windows проверяется на чистой машине в CI (шаг 4 плана, приёмка).**
  - `packaging/windows_install_check.ps1`: после сборки Inno Setup раннер Windows ставит `.exe` без вопросов для текущего
    пользователя, проверяет папку, версию в списке программ и значки («Пуск», рабочий стол), дважды запускает установленную
    программу (первый раз с пустой папкой данных), удаляет её и проверяет, что программы и значков нет, а папка данных осталась.
  - `packaging/installed_check.py`: проверки запущенной программы с временем каждой — версия, новый и прежний интерфейс с файлами,
    ТЭП, DXF (чертёж, red_lns.shx, REDLN97.LIN), GeoJSON, XLSX, лист альбома в PDF (текст выделяется) и PPTX; `--portals` —
    выгрузка маленького участка Хорошёво (не обязательна). Тот же скрипт идёт в задаче `test` против сервера из исходников.
  - Ручной запуск «ГРАДО 2 release» умеет собрать одну систему (`windows`, `macos`, `both`). Замеры — в Summary запуска.

- **2026-10-10, ГРАДО 2 v0.99.78: правки по снимку владельца — шапка, окно «Данные», командная строка, список листов.**
  - Шапка: «Проект», «Окна», «Выгрузка» и «Листы и альбом» — без стрелок, тем же кеглем, что «ГРАДО 2» и название проекта,
    текст всей строки стоит на одной линии; отступы ровные.
  - Лента: «Оформление» — только значком (подпись в подсказке), группа «Рисование» больше не разъезжается.
  - Окно «Данные»: размеры рамки не переносятся («1,1 × 0,9 км», «46,09 га»); «Свой файл…» во всю ширину, под ним подпись
    «координаты DXF» и выбор «МСК (как в QGIS)» / «система ГИС ОГД» — текст не обрезается; раздел 3 «В проекте» свёрнут
    в строку «6 слоёв · 55 объектов», таблица слоёв открывается стрелкой.
  - Карта: подсказка «Команда:» без команды не висит — строка появляется, когда команда идёт, и на 8 секунд после сообщения
    (владелец зачеркнул её на снимке; прежний ответ «всегда видна» отменён).
  - «Листы и альбом»: название листа в списке целиком, длинное — в две строки; номер, формат и масштаб стоят на линии первой строки названия.
  - Совместный режим: после «Выйти» и пока висит «Вход закончился» страница не шлёт пересчёт ТЭП на сервер (`web/hub.js`):
    раньше между выходом и перезагрузкой успевал уйти запрос с ответом 401, и проверка совместной работы изредка падала.

- **2026-10-10, ГРАДО 2 v0.99.78: «Листы и альбом» — вкладка нового интерфейса, без отдельного окна браузера (шаг 2 плана, фаза 1, #94).**
  - Кнопка «Листы и альбом» в шапке (и Ctrl+P) открывает вкладку справа от карты: строка альбома, «Добавить лист», «Собрать»
    (альбом ППТ КРТ, ситуационный план, раздел 1, «Обновить листы»), PDF и PPTX; штамп; список листов с форматом, масштабом и значком
    «не готов»; свойства листа (название, формат, масштаб, легенда, ТЭП), просмотр картинкой, PDF листа, выше, удалить.
  - Ход сборки и выгрузки виден во вкладке («Лист 1 из 1: Ситуационный план — загрузка… · 12 с», «PDF: лист 3 из 9»), «Остановить» —
    где сборка это позволяет. Вопросы «заменить или добавить листы» и «не всё готово — выгрузить всё равно?» задаются там же; строка
    «не готово» щелчком выбирает лист или открывает штамп. PDF и PPTX из меню «Выгрузка» идут через вкладку.
  - Собирает и печатает тот же движок рабочей страницы, скрытый в странице (`web/albumapi.js`), поэтому PDF и PPTX выходят прежними
    лист в лист. «Подробно» открывает прежнее окно для рамок листов на карте, «Слоёв и листов», макета надписей и фотографий.
  - Сервер разрешает встраивать свои страницы в рамку только самому себе (`frame-ancestors 'self'`, было `'none'`): чужой сайт их не встроит.

- **2026-10-09, docs: шаблон задания агенту и форма задачи GitHub — в устройстве подробного ТЗ.**
  - `docs/team/prompts/implement.md`: разделы в тегах по образцу промпта Nate Parrott (Anthropic), который прислал владелец:
    цель (результат — это …, а не …), окружение (стек, сначала готовая библиотека, свои — команды в духе AutoCAD, координаты,
    инсоляция, правила альбома), архитектура (один источник правды, железные правила), модель данных (старые проекты
    открываются), фаза 1 с проверкой до фазы 2, фаза 2, вне объёма («Пока нет» вместо пустых кнопок), проверка (запустить
    самому), результат («Работает (проверено)» / «Не сделано» / «Известные ограничения»), источники (требования важнее; неясно —
    спросить, не угадывать).
  - `.github/ISSUE_TEMPLATE/task.yml`: те же разделы, обязательны цель, проверка и результат; задача переносится в задание как есть.

- **2026-10-10, ГРАДО 2 v0.99.77: new interface (/next/) — «Свойства» panel reworked, layer swatch matches the map (owner's screenshot 10.10.2026).**
  - «Свойства» no longer breaks in a narrow window: below 280 px the label goes above the field and the field takes the full width
    (`@container` on `.pane`, theme.css); a slider with its value and a number with its unit stay together; long list values end with «…».
    Before, at ~180 px the labels overlapped the fields, «штриховка» and «Показывать на карте» were cut, the lists were empty boxes.
  - Panel structure like the QGIS layer styling panel: header (swatch, name, type and count, eye instead of the switch at the bottom);
    «Оформление» (method, classes, fill colour and fill opacity in one row, hatch as a list «нет / косая / сетка…» with step,
    contour colour and width, line type «сплошная / штриховая / пунктир / штрихпунктир»); «Подписи» (field, colour, size);
    «Слой» (layer opacity, scale visibility, role). Contour colour of a hatched polygon shows what the map draws (hatch colour) and
    becomes its own colour once changed.
  - Layer swatch in «Слои», the «Свойства» header and the «Виды» legend is drawn by the map's own OpenLayers style (`LayerSwatch.vue`,
    `symbolStyle` in symbology.js via `ol/render` toContext): fill opacity, hatch pattern and step, contour width, colour and dash,
    layer opacity. Categories, ranges and rules show up to three first classes side by side.
  - `tools/ui_layout_check.mjs` also narrows the right group to 190 px and checks «Свойства» (the old build gives 4 strict «outside» violations).
- **2026-10-09, ГРАДО 2 v0.99.74: new interface (/next/) — floating windows follow the mouse, larger targets, readable «Схема расчёта», automatic layout check (step 1 of plans/plan-dalshe-2026-10-09.md).**
  - Floating windows: in dockview 8.4.1 a window lagged the cursor by the first mouse move (a quick grab left it 10–20 px behind), and
    the corner handle moved the opposite edge by 4–5 px. Fixed by a patch of dockview-core (`apps/grado2/ui/patches/`, applied by
    patch-package on `npm ci`): the grab point stays under the cursor, the corner stretches the window only.
  - Targets and text (WCAG 2.2, `docs/ux/ui-grid.md`): checkboxes and switches are 24 px rows, layer-tree icons have a 22 px target,
    map zoom buttons 24 px, the status bar is 26 px with 20 px buttons; no text below 11 px (ribbon group names, section titles, drawing
    modes, the time in «Объём»).
  - «Схема расчёта» opens fitted but not smaller than 60 % (block labels were unreadable at 15 %); «Вся схема» still fits everything.
    «Эскиз»: a unit no longer wraps alone onto the next line. New floating windows step 46 px down so the tabs of the one below stay visible.
  - «Данные» (owner: «вкладка данные вообще непонятна и невозможно отследить процесс выгрузки»): three numbered steps — boundary,
    download, what is in the project. A download shows a card: overall bar, elapsed time and a row per layer (spinner and the
    portal step with its own bar, then a check with the object count, «пусто» or the error in red); after the end only errors and
    empty layers stay in view, the loaded ones open on a click. «В проекте» is a table: layer, objects, download date. ФГИС ТП folds.
  - «Объект» (owner: «выглядит пустой и непонятно какое значение к какому полю относится»): fields are a table «Поле | Значение»
    with editable value cells (as «Определить объекты» in QGIS); with nothing selected the window says how to select, with keys.
  - Scale in the status bar (owner: «не оптимизировано окно для масштаба»): «1 :» and the number in one compact box, an arrow opens
    the standard scales (1:500 … 1:50 000), the current one is marked.
  - `tools/ui_layout_check.mjs` (gate with `E2E=1`, CI): every window at 1280 and 1920 in both themes with visible scrollbars; drags a
    floating window by its strip and corner, a splitter, hovers every button and row; fails on horizontal or nested scrollbars, controls
    outside a window, jumps of the header, ribbon or status bar, windows not following the mouse, hover shifts, monospace.
  - Rules: journal `docs/team` reaches `main` only through landing (owner «1 а»); water colour on white schemes and the map label font
    become album settings (owner «настраиваемый»; rules in album-rules.md and label-rules.md, code in a separate issue).

- **2026-10-09, ГРАДО 2 v0.99.73: new interface (/next/) tidied after the owner's screenshot («элементы не по уровню, скачут, не влезают, ползунки, перемещение окон криво»).**
  - Scrollbars: every window had a 2 px overflow (the window frame was a border inside dockview's size) and showed scrollbars at all
    edges; the frame is now an outline, only content that really scrolls (layer list, table, help) has a bar, and bars are thin and
    themed (`theme.css`).
  - One grid for fields, as inspectors of Figma and Blender: in «Свойства» every row is label on the left (one column width), control on
    the right, all controls 26 px high, 6 px between rows; units and percentages in a fixed column. Number fields show their number again
    (empty slots of Web Awesome took the width). Section titles are the same small capitals in every window.
  - «Данные» and «Эскиз»: action buttons sit in equal columns instead of a ragged row; long buttons take the full width; the coordinate
    system list is no longer cut.
  - Windows: clicking a short tab («Виды») closed the window, because the hidden close cross lay over the label; inactive tabs have no
    cross now, the active tab keeps a small one. Floating windows move by a thin strip with a grip above the tabs (dockview `titlebar`),
    so dragging a tab moves only the tab; Shift + strip docks the window back. Drop zones and splitters are drawn in the accent colour.
    The right group is a little wider by default so all four tabs fit at 1280.
  - Status bar: the message sits on the left, so layer, coordinates and scale on the right no longer jump when it appears or goes;
    coordinates and scale use same-width digits; the scale field always shows its frame.

- **2026-10-09, ГРАДО 2 v0.99.72: new interface (/next/) audit fixes — six Haiku 5.5 auditors by area, fixes by four Opus 5.5 agents.**
  - Shell (`App.vue`, `theme.css`): theme button shows its icon; OpenLayers map buttons follow the dark theme; window gaps are 8 px on
    every side; default widths of «Слои» and the right group fit all tabs on 1280; floating windows stay inside the screen and lose the
    empty title strip; a window reopened from «Окна» goes back to its group; scale in the status bar is an input (1:2000, list of scales);
    status messages open in full on click; «Восстановлена последняя работа» goes away; with the map closed the ribbon says how to open it.
  - Drawing (`cad.js`, `CadModes.vue`, `MapSearch.vue`): «X,Y» after the first point is an absolute МСК point; command messages only in the
    command line (no duplicate in the status bar); command line is one line wide as its text and lets clicks through to the map; F2 history
    sits above it; polygon takes a map click as the centre; «Выбор» and «Оформление» on the ribbon; mode buttons in Onest and clearly on.
  - Panels: a layer dropped onto a row of another group joins that group; full names in tooltips; hidden group dims its layers; table fills
    the window, sort arrow only on the sorted column, no white line in the dark theme; «Оформление» is a list instead of wrapping buttons;
    «Виды» rows readable; no abbreviations («24 объекта», «6 слоёв»); source names in «Данные» match layer names.
  - Sheet layout: the ribbon fits 1280 (arrange buttons fold into three lists); legend marks rows that do not fit; same-kind items are
    numbered; grid visible; sheet delete asks in a dialog; sheet fonts are the server's PT Sans files (as in PDF). Album window: «Масштаб
    схем» label and the «В шапке не заполнено» line are no longer cut.

- **2026-10-09, ГРАДО 2 v0.99.71 (on its branch v0.99.57): the server runs on Starlette and uvicorn, request bodies are checked by pydantic (part of #69).**
  - `apps/grado2/server.py`: the hand-written `http.server` handler (one long chain of `if self.path == …` for GET and for POST) is gone.
    Each address is now one small function in `GET_ROUTES` / `POST_ROUTES`; access checks, foreign-site refusal and the security headers
    live in one wrapper (`Guard`) in front of every answer; files from `web/` come from Starlette `StaticFiles`.
  - Bodies of `/api/fetch`, `/api/tep`, `/api/rail_route` and the sheet area of «Всё из ГИС ОГД» are described as pydantic models: a wrong
    field is refused with 400 and the field name, as before. A body sent in pieces without a length is now cut at the same size limit.
  - The hub event stream is a Starlette streaming answer; a closed tab ends it as before. Stopping the server (Ctrl+C, or a newer version
    replacing it) now lets running requests finish for up to 5 s.
  - New dependencies in `apps/grado2/requirements.txt` and the spec: `starlette` (BSD), `uvicorn` (BSD), `pydantic` (MIT); all pure Python
    except pydantic-core, which has wheels for macOS arm64, x86_64 and Windows. The launchers and the server timer install them by themselves.
  - Browser scenario «свободные места снова 0 / 0 / 0» waited a fixed 1.2 s after each field; it now waits until the number reaches the
    project (at most 3 s) and prints what it got when it fails (it failed once in CI, never in five local runs).
- **2026-10-08, ГРАДО 2 v0.99.71 (on its branch v0.99.56): checks run under pytest, browser scenarios start Chrome through Playwright (part of #69).**
  - `tools/gate.sh` and CI run the same unit tests with pytest (`apps/grado2/requirements-dev.txt`, not part of the program); without
    pytest the gate falls back to unittest and says how to install it.
  - Browser scenarios: `apps/grado2/tests/e2e/browser.mjs` starts the local Chrome with Playwright (`playwright-core`, Apache-2.0, in
    `tools/package.json`; `(cd tools && npm ci)`); `driver.mjs` and `collab_scenarios.mjs` no longer spawn Chrome and talk to its socket
    themselves. Mouse and keyboard still go over the DevTools protocol, so the scenarios are unchanged.
  - T36 «during PDF build the menu is grey» waited a fixed 0.9 s for the build to end; it now waits for the end of the build
    (at most 5 s): under Playwright the autosave of the project in the same second made the fixed wait too short.
- **2026-10-08, ГРАДО 2 v0.99.71 (on its branch v0.99.55): the album PPTX package is assembled by python-pptx instead of hand-written zip parts (part of #69).**
  - `core/render/grado_render/backend_pptx.py`: slides, pictures, slide notes, the one blank layout, theme and embedded fonts go through
    python-pptx; shapes are still written as DrawingML (custom outlines, dashes, glow of labels) and placed into each slide.
    `print_io.pptx_notes` (re-zipping the file to add notes) is gone: the note «карта вставлена картинкой» is set on the slide directly.
  - Checked on copies of Гольяново and Безобразово: both presentations converted by LibreOffice are pixel-identical to v0.99.54,
    slide by slide; the file is 4 KB larger (standard notes and print settings parts).
  - New dependency `python-pptx>=1.0.2` (MIT; brings lxml, BSD, wheels for every platform) in both requirements files and the spec.
- **2026-10-08, ГРАДО 2 v0.99.71 (on its branch v0.99.54): clipping and «point inside an outline» on shapely instead of hand-written copies (#71, part of #69).**
  - `core/connectors/grado_connectors/clip.py` (layers of ГИС ОГД cut to the area or the sheet) is GEOS `clip_by_rect`: a concave outline
    now splits into real parts instead of zero-width bridges along the frame, holes stay holes; whole-inside and whole-outside fast paths kept.
  - Hand-written point-in-polygon loops replaced by `shapely.contains_xy`: district of the area (`server.py`), «inside the TTK» for K2,
    side of a natural-complex border (`ogd_all.orient_lines`, now with an STRtree), OSM holes to their outer ring, dot pattern fill of
    zones (`scene.dots_ops`, one vectorised call per polygon). Label placement in `print_io` keeps its own loop (thousands of calls per sheet).
  - Checked on copies of Гольяново and Безобразово: all 18 album pages are pixel-identical to v0.99.53.
- **2026-10-08, ГРАДО 2 v0.99.71 (on its branch v0.99.53): album PDF is written by ReportLab instead of our own PDF writer (part of #69).**
  - `core/render/grado_render/backend_pdf.py`: the same list of drawing operations goes to a ReportLab canvas (paths with holes by
    even-odd, clips, dashes, translucent plates, label halo, underlined legend headers, JPEG tiles as is). Fonts are embedded as
    subsets with /ToUnicode, so text is still found and copied; line widths for labels are still measured by `ttf.py`.
  - Checked on copies of Гольяново and Безобразово (9 sheets each, PDF): the text of every page is the same, pixels differ only
    in letter edges (at most 0.004 % of a page differs strongly); the file is smaller (Гольяново 827 KB → 310 KB, Безобразово
    4.8 MB → 4.6 MB). PPTX is unchanged.
  - New dependency `reportlab>=4.2` (BSD), wheels for every platform; in both requirements files and `packaging/grado2.spec`.
  - Tests read the PDF through `core/render/tests/_pdfread.py` (objects, page streams, text via /ToUnicode) instead of byte patterns.
- **2026-10-08, agent instructions (no program change): owner's glossary, new task template, contradictions removed (step 4 of the plan, #69).**
  - `docs/wiki/glossary.md`: the owner's terms and abbreviations (АГК, АГР, сущпол, СПРИТ, ЛГР, ЗОУИТ, СПП, K1/K2…) with where they appear and what
    not to confuse them with; four traps first (sheet numbers, «эталон», «подзона», «ПП»). Linked from `CLAUDE.md`, `AGENTS.md`, wiki index.
  - Issue template «Задача»: «что сейчас / что должно быть / образец / что владелец увидит на экране».
  - Contradictions fixed: role reports in Russian (were English); `docs/team/README.md` no longer says the site is deployed from the Mac;
    `recipes.md` urgent fix goes through a PR and «выкладывай» (was a direct commit to main); RULE in PROGRESS.md names `team/t60`, not
    `team/grado2`; `DECISIONS.md` — a decision is cancelled by an issue, not `OWNER.md`; agents' test servers — port 8660 and up everywhere
    (8651 is `grado2-test`); BANS and the architect role no longer forbid new dependencies (owner 08.10, #69); progress notes go to issue
    comments, not `/tmp`; stale album lines (yellow calculated СЗЗ, «Территория рассмотрения», district map «в конец альбома»,
    district border 1,2 mm on the district map) marked by the later owner words.
- **2026-10-08, ГРАДО 2 v0.99.71 (on its branch v0.99.52): requests to the portals on httpx and tenacity, one retry rule for all of them (part of #69).**
  - `core/connectors/grado_connectors/netutil.py` is now the only network code: `request` (whole body, size cap) and `stream`
    (large layers, gzip unpacked by the caller with the bomb guard). Redirects only to https, certifi roots, certificate check
    never switched off (НСПД adds the Минцифры roots, the explicit `GRADO_NSPD_INSECURE=1` stays as it was).
  - One retry rule instead of eleven hand-written loops (НСПД ×2, Overpass, Yandex vmap, ГИС ОГД ×2, terrain, Yandex sat, Esri):
    at most three attempts, retry on 429, 500, 502, 503, 504, a dropped connection or a timeout, pause 1 s then 2 s or what
    Retry-After asks (at most 30 s); a certificate error and other 4xx are not retried. Yandex vmap: a captcha instead of a tile
    is retried, not cached. Overpass mirrors race as before; the losing mirror stops retrying.
  - Changed on the way: Yandex vmap did up to four attempts and Nominatim keeps its own loop under the 1 request per second lock;
    ГИС ОГД, terrain and НСПД extent now also retry 5xx (they failed at once); Esri no longer retries a 404.
  - New dependencies `httpx>=0.28` (BSD-3) and `tenacity>=9.0` (Apache-2.0), pure Python, wheels for every platform; in
    `apps/grado2/requirements.txt`, `requirements-cloud.txt`, `packaging/grado2.spec`.
  - Tests: `test_netutil.py` (policy, Retry-After, redirect, size cap, stream), connector tests use `_fakenet.FakeNet`
    (httpx.MockTransport) instead of patching urllib.
- **2026-10-08, ГРАДО 2 v0.99.48: geometry core on shapely 2 instead of hand-written code (#71, part of #69).**
  - `core/geom`: `overlay.union_intersection_area` (union of each group, intersection, area), the area and integrity check of
    `Coverage` (`shapely.coverage_is_valid`) and the spatial index of `Snapper` (STRtree) now run on shapely 2 (GEOS). Function
    names, arguments and results stay the same; the shared-edge model of `Coverage` stays ours (shapely has none).
  - Fixed on the way: the shares of districts under the boundary (`server.district_shares`, they choose the district, okrug, K2
    and the education zone of ТЭП) were computed by scan lines with a 0.05 step in degrees — about 5 km, so a small boundary on
    the edge of two districts got one or two lines and errors up to 300 %. Now exact. Golyanovo is unchanged (one district, 100 %).
  - New dependency `shapely>=2.1` (BSD-3, GEOS LGPL-2.1 as a shared library; brings numpy): wheels for macOS arm64 and x86_64
    and Windows; in `apps/grado2/requirements.txt`, `requirements-cloud.txt`, `packaging/grado2.spec`.
  - Installers: `packaging/grado2.spec` now ships `docs/standards/admin` (districts) and the album slide header; without them the
    packaged program answered «внутренняя ошибка» on the district lookup and could not print the PPTX header.
- **2026-10-09, ГРАДО 2 v0.99.70: адрес сайта открывает новый интерфейс; «Листы и альбом» — отдельным окном на движке рабочей страницы (шаг 3 плана замен, #69).**
  - The site address (`/`) now opens the new interface (`/next/`); the former working page stays at `/old`. Login, the token
    gate and share links (`#join=`, `#p=`) lead to the new interface; `/next/` and `/old` count as pages for the token gate.
  - «Листы и альбом» (header button or Ctrl+P): the album ППТ КРТ opens as a separate browser window, like the print layout
    in QGIS. It is the working page's own album engine (`web/sheets.js`, `albums.js`, `frames.js`, `layout.js`, `ogdpick.js`)
    unchanged, at `/old?embed=album` (`web/embed.js`): sheet frames on the map, the «Лист» tool, stamp, album build,
    «Слои и листы», label layout, PDF and PPTX, ГИС ОГД in DXF. The header, ribbon and side panels of the old page are hidden there.
  - The window gets the project from the new interface (`applyProject`) whenever the new interface has an edit it has not seen;
    edits made in the window (sheets, downloaded layers, views, groups) come back by sections (`ui/src/albumhost.js`,
    `collab.js adopt`) and are saved, autosaved and sent to the shared server as usual. Ctrl+S in the window saves the project.
  - «Выгрузка» in the new interface: PDF and PPTX of the album and «ГИС ОГД в DXF» are enabled and run in that window.
  - Check on a project copy: `albumSpec` of all sheets in the window equals the one of the standalone old page character for
    character, and the album PDF from both is byte-identical (2 pages compared).
  - Tests: `tests/test_server.py` (redirect, `/old`, token gate), `tests/test_next_ui.py` (`gradoEmbed` calls on both sides);
    E2E scenarios of the old page now open `/old`.
- **2026-10-09, ГРАДО 2 v0.99.69: графический язык «Синька» в новом интерфейсе.**
  - Owner's choices of 09.10.2026 (1Б 2А 3Б 4А): one toolbar without workflow stages, the command line always visible,
    ТЭП stays a table at the bottom, the font is Onest (shipped in the build, `@fontsource/onest`, OFL); no monospace font anywhere.
  - Windows are cards with rounded corners on a grey desk with 8 px gaps; one blue accent for the current tool, selection,
    focus and the main button; green, amber and red only for norms; light and dark themes.
  - The command line under the map is shown without a command too («Команда — наберите L, PL, C, TR…»); a click on it opens
    command input. The status bar shows the cursor coordinates in МСК (X east, Y north). Map zoom buttons moved to the top right.
  - Drawing tools (AutoCAD-style ribbon) are unchanged.

- **2026-10-09, ГРАДО 2 v0.99.68: «Макет листа» в новом интерфейсе вместе с перенесёнными окнами; листы сохраняются вместе с проектом (шаг 2 плана замен, #21, #24, #69).**
  - Редактор листов (v0.99.50–0.99.52 ветки редактора) соединён с перенесёнными окнами: «Окна → Макет листа» открывает его
    вкладкой рядом с картой во всё окно.
  - Листы теперь — часть проекта, как слои: правка листа ставит «•» у названия проекта, автосохранение держит её,
    «Проект → Сохранить» пишет в файл (ключ `layouts`, всегда последним). Отдельная запись листов
    `POST /api/project/layouts` убрана. Рабочая страница о листах по-прежнему не знает, и её сохранение их не стирает
    (`server.py` `save_project`).
  - «Как на карте» берёт середину и масштаб окна «Карта» из общего вида карты (`store.js` `viewNow`, `scale`), штамп —
    поля альбома из файла проекта.
  - Проверки: `tests/test_layout_io.py` (листы из записи нового интерфейса, сохранение рабочей страницы их не стирает).

- **2026-10-09, ГРАДО 2 v0.99.67: совместная работа в новом интерфейсе (#69).**
  - On the shared server the new interface now has the login screen, the project button in the header (open, create,
    upload, copy, star, rename, delete), the role and «сохранено / отправляю» next to it, faces of who is in the project,
    «Доступ» (members, roles, link, team), «История» (versions and actions, restore), teams, users and invites for the
    administrator, password change and logout.
  - Edits go to the server by themselves and others' edits appear without reloading; the new interface and the working page
    can edit one project together. Others' cursors and selection are shown in their colour.
  - Comments: a button in the header, then a click on the map or «К выбранному объекту»; numbered pins on the map, the
    «Комментарии» window with replies, «Решено» and delete.
  - Someone else's edit resets undo: Ctrl+Z then undoes only your next edits.

- **2026-10-09, ГРАДО 2 v0.99.66: «Упорядочить слои» в новом интерфейсе (#69).**
  - A button in the «Слои» window puts downloaded layers in the reference-plan order (your own layers and imports stay on
    top as they were) and leaves one buildings layer visible out of several. Nothing is deleted; Ctrl+Z undoes it.

- **2026-10-09, ГРАДО 2 v0.99.65: ФГИС ТП в окне «Данные» нового интерфейса (#69).**
  - Section «ФГИС ТП — документы территориального планирования» in «Данные»: «Найти по территории» lists the documents
    whose coverage includes the territory (most local first), or search the whole catalogue by name; pick a document,
    tick its layers, «Загрузить выбранные». Layers empty in the area are not added; loading a layer again keeps your edits
    and its name, as for the other sources.

- **2026-10-09, ГРАДО 2 v0.99.64: поиск над картой в новом интерфейсе (#69).**
  - A search field on top of the map, as in the working page: an address (OpenStreetMap), a cadastral number (several
    separated by commas) or a КРТ number, then Enter. An address puts a marker and frames it; parcels can be shown on the
    map (into «Земельные участки (ЕГРН)» without duplicates) or made the territory boundary; a КРТ becomes the boundary
    and its number goes to the album header. Replacing an existing boundary asks again on the button for 5 seconds.
  - Ctrl+F jumps to the field, arrows move through the results, Esc closes them.

- **2026-10-09, ГРАДО 2 v0.99.63: выгрузка в Excel в новом интерфейсе (#69).**
  - Menu «Выгрузка» → «Excel: показатели ТЭП и листы»: the same workbook as the working page (sheet «ТЭП» with the
    territory, sketch and «Калькулятор 2.0» metrics, sheet «Листы» with the album sheets). A sheet scale picked
    automatically by the working page is left empty here; a scale set on the sheet is filled in.
  - PDF, PPTX and ГИС ОГД in DXF stay in the working page until the sheets move (they need sheet frames).

- **2026-10-09, ГРАДО 2 v0.99.62: черчение как в AutoCAD в новом интерфейсе (#69).**
  - The ribbon now runs the real commands of the working page instead of sample buttons: drawing (line, polyline,
    circle, arc, ellipse, rectangle, polygon, point), «Оформление» (hatch, dimension, text), editing (move, copy,
    rotate, mirror, scale, offset, trim, extend, fillet, array, stretch), «Ещё» (chamfer, break, join, explode,
    lengthen, array edit, erase, and the polygon and attribute commands: split, merge, subtract, buffer, simplify,
    reverse, align, match properties, divide, measure, select similar, select by condition, to current layer,
    line ↔ polygon, boundary by click), measure distance and area, territory boundary.
  - Same keyboard as the working page: aliases (L, PL, C, M, TR…) and Enter, the input box at the cursor (length,
    length<angle, @dx;dy, X;Y in МСК), the command line over the map with clickable options, Enter/space/right
    button, Backspace, Esc, F2 command history; grips on selected objects (drag a vertex, add one on a side).
  - Status bar: ПРИВЯЗКА with the set of snaps, ОТСЛЕЖ, ПОЛЯР with the angle step, ОРТО, ДИН, ТОПО (F3, F8, F10, F11, F12).
  - Every command edit is one step of the common undo (Ctrl+Z). The window «Свойства» now updates the object count
    after edits.
  - The commands are a port of web/cad.js (same file of geometry web/cadcore.js); a test keeps the command list and
    aliases equal to the working page.

- **2026-10-08, ГРАДО 2 v0.99.61: окна «Варианты», «Сравнение» и «Объём» в новом интерфейсе (#69).**
  - «Варианты»: «Подобрать варианты» tries typologies × building width × direction inside the constraints, floors fit
    the density goal; six best as cards with a plan picture, all in a table (density, floors, insolation of new
    houses, population, kindergarten places); «Стоп» keeps what is counted; a click moves the variant into the scheme;
    «Сохранить слоем». The numbers are recounted when norms or territory parameters change.
  - Saved variants (same format as the working page): «Сохранить как вариант…» in «Эскиз» and «Варианты»; open
    (becomes the sketch layer «Вариант: …»), rename, delete (second click confirms).
  - «Сравнение»: two maps side by side with the main map's view — existing situation and the sketch or a saved variant.
  - «Объём»: buildings of the sketch and saved sketch layers with kept buildings, shadows for the chosen date and time.
  - Floating windows open in a cascade, not on top of each other.

- **2026-10-08, ГРАДО 2 v0.99.60: окна «Эскиз», «Показатели (ТЭП)» и «Нормативы расчёта» в новом интерфейсе (#69).**
  - «Эскиз»: typology buttons, floors by a number or by the density goal, the sliders the chosen typology uses,
    «Построить эскиз» / «Остановить», «Сохранить слоем» (buildings, plots and streets as layers of the group
    «Эскиз: …»), «Проверить нормы» (insolation of new and neighbouring houses, buildings on no-build zones, gaps
    between buildings; layer «Проверка норм», re-checked 1,5 s after an edit of a saved sketch layer). Every control
    is a field of a scheme block: an edit here changes the scheme and back.
  - «Показатели (ТЭП)»: the real calculation instead of the sample table. District, zone, K1, K2, ТиНАО, type of
    territory and percentages are edited right there; «по району», reset, the ПЗЗ density goal; the sketch summary
    and the «Калькулятор 2.0» metrics by groups; «Эскиз не построен» until there is a sketch.
  - «Нормативы расчёта»: project conditions (education zone, free places nearby) and the preset norms with their
    sources; a changed norm is marked, can be reverted one by one or all at once, wrong numbers are not accepted.
  - The map shows reserve plots for kindergartens, schools and clinics while the sketch or scheme window is open.
  - Speed: the reserve plot search no longer freezes the page for minutes on ИЖС (hundreds of houses): obstacles are
    subtracted in one pass and the «within R of houses» zone is buffered in two steps. Same fix in the working page.
  - Not yet here: saved sketch variants, «Сравнение», «Объём» (next steps).

- **2026-10-08, ГРАДО 2 v0.99.59: окно «Схема расчёта» в новом интерфейсе на Rete.js (#69).**
  - The calculation scheme is drawn by Rete.js 2 (engine map: a maintained library instead of the frozen litegraph).
    Blocks keep the same look by kind (data, operations, sketch, ТЭП, numbers) and links are coloured by data type.
  - The scheme is the same object as in the project file and the working page (litegraph format): a project edited
    in one program opens in the other; a project without a scheme gets the default one of the working page.
  - All blocks of the working page are calculated the same way: territory, layer with a condition, «Ограничения»,
    number, buffer, subtract, union, intersect, «Посадка застройки» (the generator moved unchanged), ТЭП (district
    lookup, server ТЭП, manual norms) and four analysis blocks. Each block recalculates only when its inputs, fields
    or data change.
  - Editing: library on the left, link from socket to socket (one link per input, only matching types), drag,
    rename by double click on the title, Del removes a block, fields of blocks right on the block; all of it goes
    into Ctrl+Z. «Вся схема», «Пересчитать», «В слой» (the output of the selected block as a project layer).
  - The map shows the building area, the sketch and the output of the selected block while the window is open.
    After «Рассчитать ограничения» the «Ограничения» block is added to the scheme, as in the working page.
  - New dependencies (MIT, exact versions, in the Vite build only): rete 2.0.6, rete-area-plugin 2.3.2,
    rete-connection-plugin 2.0.5, rete-vue-plugin 2.1.3, rete-render-utils 2.0.3.
  - Not yet here: the «Эскиз», «Показатели» and «Нормативы» windows (next step).

- **2026-10-08, ГРАДО 2 v0.99.58: окно «Ограничения» в новом интерфейсе (#69).**
  - Same calculation as the working page: no-build zones from ЗОУИТ, СЗЗ, water protection and ОКН zones, the red line
    setback, kept buildings with fire gaps (СП 4.13130), ПЗЗ subzones without new construction, natural zones of the
    Генплан; insolation points on the facades of kept residential houses and the height ceiling grid by the sun.
  - What to use and the parameters (setback, norm, window height, point step, reveal angle, floor height, grid step)
    are kept between sessions; the log says which layers each result came from. Results are layers of the group
    «Ограничения» in «Слои» and are saved in the project file.
  - Not yet here: the «Ограничения» node of the calculation scheme and the norms check (they move with the scheme).

- **2026-10-08, ГРАДО 2 v0.99.57: окно «Данные» в новом интерфейсе — граница, область загрузки, выгрузка источников, импорт файлов (#69).**
  - Boundary: draw on the map (double click finishes, Esc cancels), edit vertices (drag, click on a side adds,
    Alt+click removes), from a file (largest closed contour), by cadastral numbers (loaded parcels or НСПД search),
    from the objects selected on the map (new), example (second click confirms). Boundary edits go into Ctrl+Z.
  - The data loading area (sheet frames and the boundary + 60 m) is shown as a blue dashed frame while the window is
    visible; size and area in the window.
  - «Выбрать и загрузить…»: the source tree like «Исходные данные» (ЕГРН, ГИС ОГД selections and all portal layers,
    ЕГКО, OSM, Yandex, relief), ready sets, search, object counts of portal layers in the area. Loading goes through
    the same `/api/fetch` with progress; a repeat download merges with manual edits the same way as the working page
    (your edits win, deleted stays deleted, drawn stays; new and changed objects are selected). Portal layers get the
    portal look.
  - «Файл…» and a file dropped on the map: a new layer (DXF, DWG, GeoJSON, KML/KMZ, Shapefile), МСК or ГИС ОГД metres.
  - Loaded layers by source with count, date, error and re-download history; summary of the existing situation inside
    the boundary (buildings, СПП, density, coverage, parcels; areas in МСК).
  - New dependency `@turf/turf` 7.1.0 (MIT, same version as `web/vendor`), in the Vite build only.
  - Not yet here: ФГИС ТП documents and the address and cadastral search over the map.

- **2026-10-08, ГРАДО 2 v0.99.56: «Виды», подложка, граница территории, «Справка» и выгрузка DXF и GeoJSON в новом интерфейсе (#69).**
  - Window «Виды» (like QGIS map themes and the working page): save visible layers, styles, opacity, groups, basemap
    and, if ticked, the scale under a name; a click on the name brings the map back; refresh and delete (second click
    confirms; sheets on a deleted view switch to the current map, as before); legend of the shown view. Views go into
    the same `views` field of the project file and into Ctrl+Z.
  - Basemap in the status bar: OSM scheme, Esri satellite, Sentinel-2; remembered in the browser and in the project.
  - The territory boundary from the project file is drawn on the map (red dash-dot); a project without a saved view
    opens framed on it.
  - Window «Справка» (F1 or «?» in the header): what already works in the new interface, keys, search by words.
  - Menu «Выгрузка»: «Чертёж DXF» and «GeoJSON для QGIS» work (same server routes, МСК, with the boundary); PDF, PPTX,
    ГИС ОГД and Excel are marked as still in the working page.
  - Fix: the autosave right after opening a project no longer writes the default map view of Moscow into the file.
  - Windows added since the browser saved its layout («Объект», «Таблица атрибутов», «Виды») appear on their own once.

- **2026-10-08, ГРАДО 2 v0.99.55: objects on the map, window «Объект» and «Таблица атрибутов» in the new interface (#69).**
  - Selection like the working page: click an object, Shift+click adds or removes, Shift+frame selects many, Ctrl+A
    selects the whole current layer, Esc clears, Del deletes the selected objects (Ctrl+Z returns them).
  - Window «Объект»: layer, area or length in МСК, attributes with editing, a new field; for many objects the total
    area and length, common editing for one layer («разные» stays as is until filled), «Только он» per layer,
    «Решение» buttons for buildings and floors ± for own buildings.
  - Window «Таблица атрибутов» on Tabulator: sort by header, search, «только выбранные», edit a cell by double click,
    a row click selects the object and zooms to it. New dependency `tabulator-tables` 6.6.1 (MIT), in the Vite build only.
  - The map redraws only changed objects after an edit; the saved map view no longer jumps to the whole Earth when
    the project opens in a hidden window.

- **2026-10-08, ГРАДО 2 v0.99.54: window «Слои» in full and one common undo in the new interface (#69).**
  - «Слои»: «+» new layer (name; polygons, lines or points), new group from the current layer, drag layers and groups
    to reorder or move a layer into a group (SortableJS), double click renames a layer or group, layer menu (button
    «⋯» or right click): zoom to layer, copy and paste style, rename, up, down, out of group, into a group, into a new
    group, return the original download, delete; group menu: zoom, rename, ungroup, delete with layers.
  - One undo for the whole project (`ui/src/edit.js`): Ctrl+Z / Ctrl+Shift+Z and header buttons undo layer and group
    changes, styles and data replacements; edits in a row without a pause (slider, typing) are one step.
  - New dependency `sortablejs` 1.15.7 (MIT), in the Vite build only.

- **2026-10-08, ГРАДО 2 v0.99.53: window «Свойства» moved to the new interface in full (#69).**
  - All style modes of the working page: «Единое», «Категории» (field, «Классифицировать», colour and show/hide per
    value), «Диапазоны» (field, 3–6 classes, quantiles or equal intervals, four colour ramps), «Правила» (field,
    condition, value, colour, hatch, count; «Остальные» colour or hide), «ЛГР» (REDLN97 line types by line code).
  - Outline colour and width, fill and layer opacity, «Виден крупнее 1:…», role in calculations, hatch pattern and
    step, label field and size, floor labels by scale.
  - The map draws every mode the way the working page does (`ui/src/symbology.js`, a port of `web/layers.js` and
    `web/app.js`; REDLN97 signs through the same `web/linetype.js`). Large layers are drawn on canvas only for now
    (the working page switches to WebGL above ~15 000 objects in view).

- **2026-10-08, ГРАДО 2 v0.99.52: the new interface saves the project (#69, step 3 of the engines plan).**
  - «Проект» menu in `/next/`: «Сохранить» (Ctrl+S), «Сохранить как…» (asks before replacing a project with the same
    name), «Новый проект», «Открыть файл .grado2 с диска…», «Скачать файл проекта». Opening another project or a new
    one with unsaved changes asks «Сначала сохранить / Не сохранять / Отмена».
  - Autosave like the working page: edits quiet for 1,5 s or every 15 s, `POST /api/project?autosave=1`; the header
    shows «•» while there are changes not saved under the name.
  - The whole file is kept as read (`project.raw`): only layers, groups, current layer and map view change; graph,
    album, territory, sources and views go back unchanged, so the working page opens the file as before.
  - On the shared server (hub) saving is off in `/next/` until the shared-work window moves over.

- **2026-10-08, ГРАДО 2 v0.99.52: листы «Макета листа» сохраняются в проект; все листы одним PDF (шаг 2 плана замен, #21, #24).**
  - Над редактором — список листов проекта (как «Менеджер макетов» QGIS): выбрать, «Новый», «Копия», «Удалить».
    Любая правка через секунду пишется в файл открытого проекта, справа видно «Сохранено в проект». Открыть проект
    заново — листы на месте.
  - Листы лежат в файле проекта ключом `layouts`, всегда последним; пишет их только `POST /api/project/layouts`.
    Слои, данные и альбом новый интерфейс по-прежнему не меняет. Рабочая страница о листах не знает, но её сохранение
    их не стирает: сервер переносит листы из прежнего файла (`server.py` `save_project`). В совместном режиме запись
    закрыта, как и для проектов.
  - «Все листы в PDF» — листы по порядку одним файлом; в штампе «Лист» и «Листов» — номер листа в списке (и у PDF
    одного листа тоже).
  - Проверки: `tests/test_layout_io.py` (листы в файле проекта, сохранение страницы их не стирает, PDF из нескольких листов).

- **2026-10-08, ГРАДО 2 v0.99.51: «Макет листа» — настоящая карта в масштабе и печать листа в PDF (шаг 2 плана замен, #21, #24).**
  - Блок карты показывает карту открытого проекта в своём масштабе и охвате: её рисует сервер тем же кодом, что печатает
    альбом (`/api/print/map_svg`, `apps/grado2/layout_io.py`), поэтому на экране и в PDF одно и то же. Слои — видимые,
    в порядке окна «Слои», с их оформлением; подложка — без неё, светлая карта или снимок.
  - Место карты: «Как на карте» в свойствах берёт середину и масштаб окна «Карта»; инструмент «Сдвиг карты в рамке» (C)
    двигает карту мышью, колесо над картой меняет масштаб по стандартному ряду. Новый лист сразу встаёт туда, где открыт
    проект, легенда собирается из его слоёв («Из слоёв карты» — пересобрать).
  - «Лист в PDF» на ленте: весь лист (рамка и штамп по ГОСТ, карты, легенда, надписи, картинки, стрелка, линейка, таблица,
    фигуры, с поворотом и непрозрачностью) через `/api/print/layout`. Сверено картинкой: PNG редактора и PDF совпадают.
  - Проверки: `tests/test_layout_io.py`, новые случаи в `ui/src/sheet/model.test.js`.

- **2026-10-08, ГРАДО 2 v0.99.50: редактор раскладки листа на Konva, как «Макет» QGIS (шаг 2 плана замен, #21, #24, #69).**
  - Окно «Макет листа» нового интерфейса (`/next/`, «Окна → Макет листа»): открывается вкладкой рядом с картой во всё
    окно. Код — `apps/grado2/ui/src/sheet/`, окно — `ui/src/panels/SheetPanel.vue`; Konva 10.7.1 (MIT). Рабочая страница
    `web/` не меняется; лист живёт только в окне и в проект не пишется (новый интерфейс — только просмотр).
  - Как в QGIS и образце интерфейса: лента (выбор, добавить, правка, упорядочить, вид, выгрузка), «Элементы» (глаз,
    замок, имя), «Свойства» (лист, сетка, привязки, направляющие; у элемента — положение с опорной точкой, размер, поворот,
    рамка, фон, непрозрачность, свои настройки), линейки в мм, строка состояния с координатами курсора; светлая и тёмная тема.
  - Элементы: карта (масштаб, охват на местности; содержимое пока заглушка), легенда, надпись, картинка, стрелка севера,
    масштабная линейка по карте, таблица, прямоугольник, эллипс, линия со стрелкой. Добавление рамкой мышью или щелчком.
  - Направляющие тянутся от линеек; привязка к направляющим, сетке, рамке, штампу и другим элементам (общий `web/snap.js`),
    в том числе для ручек размера. Выбор рамкой и с Shift, выравнивание, распределение, одинаковый размер, порядок,
    закрепление, копирование, вставка, дубль, отмена. Лист картинкой PNG 300 dpi. Штамп берёт поля альбома проекта.
  - Модель листа `ui/src/sheet/model.js`: А4–А0, рамка по ГОСТ или поля 2 %, штамп 185×55 как `StampFrame`; карта и колонка
    легенды нового листа стоят там же, где их ставит `print_io.layout()`. Замечания «за рамкой», «на штампе», «нет масштаба».
    Проверки — `ui/src/sheet/model.test.js` через `tests/test_sheetmodel_js.py`.

- **2026-10-08, ГРАДО 2 v0.99.49: the new interface shows the real project; window «Слои» moved over (#69).**
  - `/next/` opens the last autosave (what the working page had open), else the newest project; «Проект → Открыть…»
    lists the projects folder. View only: the new page sends nothing to the server, the project file is unchanged.
  - «Слои»: project groups and layers in file order, eye on a layer and on a group, folding a group, current layer from
    the file, search. «Карта» draws the project layers in that order with the working page's «единое» style
    (other style modes come with the «Свойства» move). «Свойства» shows the current layer's colours, width and opacity.
  - Test project `apps/grado2/tests/fixtures/next_ui_project.grado2`; tests in `tests/test_next_ui.py`.

- **2026-10-08, ГРАДО 2 v0.99.48: sample page of the new interface on ready-made engines (#69).**
  - Owner's decision «1А 2Б 3А 4А» (`docs/product/engine-map.md`): Vue 3 + dockview + Web Awesome, built with Vite.
    Sources `apps/grado2/ui/`, the build lives in the repo at `apps/grado2/web/next/` (no Node on the Mac, the server or
    the installer). The working page `web/index.html` is unchanged.
  - `/next/index.html`: header menus «Проект», «Окна», «Выгрузка»; tool ribbon; dockable windows «Карта», «Слои»,
    «Свойства», «Показатели (ТЭП)» that float, dock and tab; the layout is remembered; light and dark theme.
    Layers and numbers are a sample, not project data.
  - CSP: `connect-src 'self' data:` (Web Awesome reads its icons from data: URLs). Test `tests/test_next_ui.py`.
  - `tools/ui_check.sh`: the build matches the sources; step `ui` in `tools/gate.sh` (skipped without
    `apps/grado2/ui/node_modules`) and a step in CI.

- **2026-10-08, ГРАДО 2 v0.99.47: TypeScript type check of the interface without a build step (#70, part of #69).**
  - TypeScript 7.0.2 is a developer tool in `tools/` (`tools/package.json`, `tools/ts/tsconfig.json`); it is not shipped
    in the program or the installers. Files stay `.js` and opt in with `// @ts-check`.
  - Checked now: `msk.js`, `labelfmt.js`, `uisize.js`, `cadcore.js`. Baseline with every file checked: 1027 findings,
    most in `app.js` (271), `layers.js` (158), `hub.js` (124), `sheets.js` (110).
  - `tools/gate.sh` step `types`; skipped with a note when `tools/node_modules` is absent (`cd tools && npm ci`).
  - Project rule changed by the owner: ready libraries over hand-written code (`CLAUDE.md`). Engine survey:
    `docs/product/research-2026-10-08-engines.md`.

- **2026-10-08, ГРАДО 2 v0.99.46: album design audit fixes (#53: #56, #57, #58, #60, #61, #62).**
  - Ortho territory callout «Проектируемая территория – N га» is never dropped: its box is reserved before street labels,
    it is placed first among point labels and moves aside if taken (`print_io._callout_box`, `_callout_steps`) (#57).
  - The legend plate on the ortho and district sheets is an obstacle for map labels (`album_io.ortho_legend_box`) (#58).
  - That legend has the same groups as the column legend: underlined «Границы», «Транспорт», no colon. One «Транспорт»
    group holds the railway too. The district swatch takes the colour and width of the sheet's own line style (#61).
  - PZZ sub-zones: «0» explained in the legend; density unit «тыс. кв. м/га» (#60, #61).
  - Typography on output of all album text, PDF and PPTX (`album_io.typo`, `typo_ops`): non-breaking spaces after «№»,
    before «га» and «г.», in «тыс. кв. м», after «ул.», «вл.», «ст.», «ж/д». A spaced «—» becomes «–» before wrapping.
    «ё» is untouched (#54) (#60).
  - Sheet 2 callout line keeps 1.5 mm off map labels (#62).
  - An address auto-filled from the registry marks the title sheet «адрес из реестра — сверьте с письмом ДГП» and shows a note under «Адрес» in «Штамп…»
    (`AlbumMeta.addrWhy`) (#56).
  - Not changed, see the PR:
    - the ВАО enclave Восточный (0.2 km from the main part, 2 % of its area — not «далёкий» by lr 18; owner question);
    - number «2» inside its ГПЗУ (owner rule 30.09);
    - ГПЗУ numbers (they match ГИС ОГД).
  - Tests: test_print (callout, ortho legend, typography), test_t80 (legend height, callout clearance), albummeta_test (addrWhy).
- **2026-10-07, tests only: T27 wheel measurement (#40).** The step «десять щёлок колеса меняют масштаб не более чем вдвое, точка под курсором на месте» failed once more on a slow GitHub runner (run 47 of PR #52, a docs-only commit; the same code passed in runs 44, 45, 46, 48): the ratio was fine (1.735), so the drift of the point under the cursor was ≥ 1.5 px. The point is now read after `renderSync()` together with the map frame box; if the box changed between the two reads the measurement is repeated once, and a real failure prints the ratio, the drift in px and both boxes. 48 local runs under CPU contention: drift 0.00 px, box stable. The cause of the CI failure is not proven — issue #40 stays open until the numbers of the next failure or ten green runs.
- **2026-10-07, album design audit and rules against repeats (no program change).** Audit of the Golyanovo album (11 sheets, issue #53): 13 Haiku auditors, 103 raw findings → 26 causes (P0 3, P1 12, P2 11), 6 findings dropped after a visual check; fixes are separate issues #55–#63, questions to the owner — #54. `tools/album_lint.py` now also checks the map frame (`frame`), line breaks (`hang`, `widow`), «ё» and dashes across the album (`yo`, `dash`), non-breaking spaces in the PPTX (`nbsp`) and control strings (`expect`); overlaps are counted on the middle of a word box (dense document lists no longer give false errors). New `tools/album_expect/` (`all.json`, `gol.json`: required and forbidden text with a reason — the address `вл. 8` on the title, the callout «Проектируемая территория – 1,66 га» on sheets 3 and 4, 11 pages); `tools/album_check.py` prints the PPTX, runs the lint and the strings on every comparison and exits with code 3 on errors. `docs/standards/albums/layout-qa.md` is rebuilt (order, 30 checks, codes, known non-defects, proposals waiting for the owner); audit template, skill `owner-remark` and `album-rules.md` updated (the calculated СЗЗ colour and the mask lines were stale: the code draws the later words of the owner). Section banners in `ogd_all.py`. Tests: `test_album_lint.py` (28).
- **2026-10-07, repo order (no program change): documents on shelves, navigation for agents, self-updating wiki, album lint.** `docs/` now has
  shelves (`wiki`, `standards`, `specs`, `product`, `ux`, `guides`, `team`, `archive`; map — `docs/INDEX.md`), 65 files moved with `git mv`
  (closed studio, executed plans, old audits, the old board and owner notes → `docs/archive/`), all references fixed. Root: new `README.md`
  (ГРАДО 2, no longer the closed studio), `INDEX.md` (map of the repository), `AGENTS.md`, updated `CLAUDE.md`; every top-level folder and every docs shelf has a `README.md`,
  nested `CLAUDE.md` in `docs/`, `apps/grado2/`, `core/`. `tools/docs_check.py` (in `tools/gate.sh` and the new CI `docs.yml`) checks links, paths,
  shelves, the map of the root and a header comment in every code file (32 test files and `packaging/build_icon.sh` got one). Wiki: `sheets.md` is built from
  `albums.js` run in Node (`tools/wiki_albums.mjs`; it was stale: 11 sheets of the album in the real order), `modules.md` covers all core packages and tools,
  new hand-written `conventions.md`; `.github/workflows/wiki.yml` rebuilds the wiki on every push to `team/t60` and `main` and mirrors it to
  `tayeela/grado-wiki` (needs the secret `WIKI_TOKEN`, steps in `.github/workflows/README.md`); `tools/wiki_publish.sh` works from CI and cloud sessions.
  New: issue and PR templates, `tools/album_lint.py` (PDF checks: overlaps, edges, tiny text, fonts, low-ppi rasters; test `test_album_lint.py`),
  `docs/standards/albums/layout-qa.md` (checklist before «готово»), prompt template of the design audit, `tools/prune-merged-branches.sh`.
  Found on the way and fixed: the tests of `core/compute`, `geom`, `layout`, `model`, `reactive`, `render` (232 tests) were run by nobody — `tools/gate.sh` has a `core` step
  now and CI runs them; `album-rules.md` described a Genplan sheet of the sit.-plan series that is not in the album; `sources.md` listed the wrong keys under SIT_FILTER.
  The five biggest files (`server.py`, `print_io.py`, `album_io.py`, `sheets.js`, `albums.js`) got section banners `# ---------- Название ----------` (comments only);
  `modules.md` lists the sections of every file in order.
  New hand-written wiki pages `conventions.md` (how to read and write code and docs) and `howto.md` (step-by-step: add a data source, a route, an album sheet, a label rule, a page module, a test).
- **2026-10-07, ГРАДО 2 v0.99.45: НСПД через релей для облачных сессий; корни Минцифры принимаются в формате .cer.**
  Облако не достаёт `nspd.gov.ru` (портал рвёт соединение с иностранных адресов), поэтому коннектор умеет ходить
  через релей на российском сервере: `GRADO_NSPD_BASE` (вместо `https://nspd.gov.ru`) и `GRADO_NSPD_RELAY_TOKEN`
  (заголовок `X-Grado-Relay-Token`; токен уходит только на релей, на сам НСПД не отправляется). Без переменных
  поведение прежнее. Релей — Caddy на msk, конфиг и установка в `tools/nspd_relay/`; он пропускает только GET/POST на
  `/api/geoportal/*` с токеном, проверка сертификата НСПД по корням Минцифры включена. Заодно исправлена подсказка
  `_CERT_HELP` (актуальные имена `russian_trusted_root_ca.cer` / `russian_trusted_sub_ca.cer`), а `~/.grado2/ca/`
  принимает `.cer` и в DER, и в PEM. Тесты: `core/connectors/tests/test_nspd_relay.py`.
- **2026-10-07, tests (#40): two browser steps no longer depend on timing.** T27 (wheel zoom keeps the point under the cursor) reads
  the resolution and the point after the map has stopped (the resolution stays unchanged for 300 ms) instead of after a fixed 0.9 s; T61 (no
  answer from `/api/place`) waits for the real district lookup of the opened window to finish, cancels the deferred repeat, counts the
  30 s timers of its own lookup only and waits for the substituted lookup to end. The third step of the issue (collab «A: список проектов
  пуст») was already fixed in v0.99.44. Open until ten CI runs in a row stay green.
- **2026-10-07, ГРАДО 2 v0.99.44 (#48): documentation sheet split in two.** Sheet «Схема … документацией по планировке
  территории» now shows only ППТ and ПМТ; ГПЗУ moved to a new template sheet 14 «Схема с отображением границ территорий с
  выданными градостроительными планами земельных участков» (same light base, numbers and list), placed right after it
  (`PPTKRT_ORDER` = 0, 1, 9, 2, 3, 4, 8, 10, 13, 12, 5). Lists, legend and «не готов» follow the sheet's own layers. Tests T91, T92.
- **2026-10-07, ГРАДО 2 v0.99.44 (#47, evening remarks): toponyms from Yandex and sheet fixes.** Street labels — Yandex `road_label`
  lines (`yandex.road_labels`, z18; `sit.road_labels`, z16 on the district map; `road_label`/`place_label` no longer skipped by
  yandex_vmap), «МКАД», «МСД» (СВХ not labelled), Yandex «Наримановская ул.» → «ул. Наримановская»; OSM labels only as fallback
  (district map: OSM city streets whose name Yandex lacks). District map: one label per street on the middle of its longest straight
  run (turn ≤ 10° from the run start, along the road), no small water labels, «Национальный парк «Лосиный остров»» from the Yandex
  poi `vegetation-natpark` (`sit.places`), district names in one or two lines and mostly inside their district or dropped. Railway
  station labels snapped to the nearest railway line (≤ 500 m); Yandex station points used where they exist. Ortho: railway line.
  Photo numbers within 4 mm of their arrow. Land use: SZZ thinner, calculated SZZ black dash-dot, non-residential zones «… вида».
  Documentation: hatch step 3 mm, at least two numbered documents of each kind (ПМТ list too), 7 in all. ПЗЗ: square schemes, black
  thin zone and subzone lines, labels wherever they fit, subzone parameters in three lines, КРТ blue hatch on both, only street
  names, common legend under the left scheme and parameters under the right. Genplan: forecast fund for the developed territory
  (zone fund × territory share of the zone area), legend only zones visible ≥ 25 mm² and not white. «разрабатываемая территория»
  instead of «территория рассмотрения». Print: label halo colour (`lhc`) passed on in all label paths.
- **2026-10-07, ГРАДО 2 v0.99.44 (#45, #47): album ППТ КРТ by the owner's remarks of 07.10.** Sheet order and set by the owner
  (`PPTKRT_ORDER` in `TPL_SETS.pptkrt_.order`, ids and `tpl.i` stay by template so photos and edits of old projects keep their
  sheets): title, location, district map, ortho, photos, land use, land users, documentation, ПЗЗ, Генплан; no «ППТ и ПМТ», «ГПЗУ и
  АГР», second Генплан. Scheme frame by the owner's outline (`ALBUM.meta.area`): every template map sheet except location and district
  map covers it (centre — outline centre, scale from the series). Ortho and district map look like the owner's samples: white veil outside
  the territory's district (`distMask`), district names in capitals, callout «Проектируемая территория – N га» in a magenta box; district
  map — names without «район» with a thin black outline, exact scale (district whole, fills the sheet), thin district border. Land use:
  OSM `residential` in old Moscow → apartment housing (not individual), legend «производственного вида». Documentation sheet: no АГР and
  КРТ, Сводный план lines (СПРИТ) under the hatches with their legend. ПЗЗ — two schemes on one sheet (`twin`; album_io
  `TwinCaptionFrame`): zones with ВРИ codes and subzones (`gisogd.pzz_sub`) with density / height / coverage in three lines.
  Photo sheet: 8 Yandex panorama frames from the owner's links, the link is stored with each photo (`photo.link`);
  `tools/panorama_shot.mjs` takes `CHROME` (cloud). Rules: album-rules § 5, § 9; label-rules.
- **2026-10-07, ГРАДО 2 v0.99.43: sheet 11 «Схема с отображением границ территорий … документацией по планировке территории и ГПЗУ» (#37, п. 2).**
  New concept `docs` in `PPTKRT_D` (between the district map and the Genplan, `sit: true`, `fit: "cover"`): ППТ, ПМТ, ГПЗУ (with АГР
  as the second line of its item) and КРТ on one light base by the analogue ДПТ «Профсоюзная» — buildings light grey without outline,
  roads white, water and green pale, parcel boundaries thin blue (`nspd.parcels`), no white mask. `conceptDocs(out, bb, groups, { total })`
  now takes an optional global cap: numbers and lists only for the nearest `DOCS_TOTAL` = 8 documents of all kinds together (the column
  holds about eight items), the others are drawn without a number as in the analogue; groups of sheets 7–8 moved to `PPT_GROUP`,
  `PMT_GROUP`, `gpzuGroup` (no change for them). КРТ of the territory itself is not hatched, neighbours' are. The sheet is «не готов»
  when no document of any kind is in the frame (`legendrules.js` concept `docs`, `joinRu`; unit test). The title of the owner is cut
  («градостроительных планов земельных участков» → «ГПЗУ»): 176 characters do not fit two lines of 18 pt. E2E group `t92`.
- **2026-10-07, ГРАДО 2 v0.99.42: sheets 12 «Генеральный план» and 13 «ПЗЗ» in the sit-plan bounds (#37, п. 3).** `PPTKRT_D` (albums.js) gets two
  more sheets with the flag `sit: true` and `fit: "cover"` (frame = `coverFrameBox`, v0.99.40): sheet 12 is a copy of the template of sheet 6
  (`concept: "gp"`: colours by the MapInfo table, number and index, legend, table of zones) with the title «Размещение территории в
  материалах территориального планирования (Генеральный план города Москвы)»; sheet 13 is the new concept `pzz` (branch in
  `conceptSheet`): boundaries of the territorial zones (`gisogd.pzz_zones`, #6a3d9a 0,5 mm) with the VRI codes (`LABEL_FN.vri`) on the
  base of sheets 7–8, legend only of what is visible; title «Размещение территории в материалах градостроительного зонирования (ПЗЗ
  города Москвы)». The `sit` sheets never take the project's numeric «Масштаб схем 5–9» (`isScheme`, sheets.js). Subzones of the PZZ
  (`gisogd.pzz_sub`) are not on the sheet: a separate sheet only on the owner's word. E2E group `t91`.
- **2026-10-07, ГРАДО 2 v0.99.41: sheet 10 «Фрагмент карты административно-планировочной структуры города Москвы» (#37, п. 1).** New
  `PPTKRT_D` in albums.js (appended to `PPTKRT` after sheet 9, so sheets 1–9 keep their numbers): concept `district`, Yandex satellite
  on the whole sheet under the header (`bleed`, rect 0,44,420,253 like sheet 3), frame = the district of the territory (`fit: "district"`,
  scale from the ladder, 1:20000 for a ≈ 4 × 3.5 km district), OSM roads as yellow lines by class (`osm.roads`, motorway … tertiary,
  width on paper 2,2 … 0,7 mm, only motorway/trunk/primary named), red district boundary 1,2 mm (`gisogd.admin`), names of the district
  and its neighbours (`conceptDistricts`), metro stations, the territory callout and a legend of what is visible (`conceptSheet`
  branch `ortho || district`). `cSheet(sh, { places: false })` leaves out village and address labels. The E2E T62 checks use
  `PPTKRT.length` instead of 9. E2E group `t90` (synthetic districts and roads; the server draws the sheet). Not checked on the real
  Гольяново data: the cloud session cannot reach ГИС ОГД, НСПД, Overpass.
- **2026-10-07, ГРАДО 2 v0.99.40: frame «по границам выгрузки» (#37).** Owner on the three sit-plan sheets: «см карту границы выгрузки, не
  менее этого». `coverFrameBox()` (sheets.js): the smallest rectangle centred on the territory's bbox centre (rule 3.4) that holds the
  data-loading area (`coverBox()`, the blue dashed «область загрузки данных»), the frame of sheet 3 «Ортофотоплан» (without it:
  territory × 2,2) and the territory × 1,25. `fitBox` returns it for a sheet with `fit: "cover"` (new sheets of #37) and for the
  five scheme sheets when the project setting «Масштаб схем 5–9» is «по границам выгрузки» (`ALBUM.meta.schemeScale === "cover"`,
  second item of the list). `sheetScale` then takes the smallest scale of the row that fits it (sit plan 840 × 506 m → 1:4000 on the
  279 × 239 mm map), «Собрать» loads data by the same frames. The sheet's properties show «как в проекте». E2E group `t89`
  (130 m territory, a hand-drawn sheet widening the loading area, the list, the project file). Rules: label-rules «Общие» 8,
  album-rules, spec `docs/team/spec-37-sitplan-sheets.md`.
- **2026-10-07, ГРАДО 2 v0.99.39: «Масштаб схем 5–9» is a project setting (#31).** Owner: «Переделай листы 5-9 в 1:2000» (КРТ 3229
  Гольяново gave 1:1000 there), then «масштаб для каждого проекта должен быть настраиваемым». A line «Масштаб схем 5–9» under
  «Штамп» in «Листы и альбом»: «авто по территории» (default, as before) or 1:500 … 1:10 000; it is `ALBUM.meta.schemeScale`
  (in the project file, reset when another project opens). `sheetScale` (sheets.js) for the five scheme sheets (`concept` use, gp,
  ppt, gpzu, parcels; sheets 3–4 do not take it) = the scale chosen in the sheet's properties, else the project's one but never
  larger than the territory needs (a territory that does not fit gets a larger scale, border not cut, rule 3.2); a value outside the
  scale row is ignored. Because the build plan (`planUnits`) reads the same `sheetScale`, «Собрать» loads the data for the new
  frames; the sheet's properties show «как в проекте 1:2 000» instead of «авто». Rules: label-rules «Общие» 8, album-rules,
  slide-layout-rules 3.3. Test: E2E group `t88` (scales on a 130 m and a 650 m territory, the window, the project round-trip).
- **2026-10-07, ГРАДО 2 v0.99.38: ready-made source sets in «Исходные данные» (audit #27).** A row «Готовые наборы» above the
  tree: «Существующее положение» (13 layers), «Ограничения» (7), «Градостроительная документация» (8), «Альбом ППТ КРТ» (24 —
  exactly the layers of the album sheets, taken from `PPTKRT`). A click checks the set, a second click unchecks it; the
  tooltip lists the layers; the tree stays for fine-tuning. Checked on a screenshot at 1365 × 923.
- **2026-10-07, ГРАДО 2 v0.99.37: room for the map and the whole «Схема расчёта» (audit #26).** On 1365 × 923 with the
  graph docked at the bottom (233–262 px) 8–9 of 14 nodes were outside. Now: first open fits the graph down to 0.45; «Вся
  схема» first press — readable (0.6), second press in a row — the whole graph (0.22 here, 0 nodes outside); while the view
  is untouched the graph refits when its window changes size; when part of it is outside, the button reads «Вся схема
  (часть за краем)» in the warning colour. New map button «Широкая карта» (top right, next to the basemap) hides both side
  panels at once (map 795 → 1365 px) and brings them back as they were. Checked on screenshots at 1365 × 923.
- **2026-10-07, ГРАДО 2 v0.99.36: keyboard (audit #30).** Enter and Space on a focused button, link, menu item or tab press
  it: before, the AutoCAD-style «repeat last command» took them (after drawing a line, Enter on «Виды» restarted the line
  instead of opening the window — checked before/after in the browser). The first Tab shows «К карте», «К слоям»,
  «Таблица объектов слоя» (visible only in focus); the map takes focus (outline, arrows pan, + and − zoom) and is labelled
  for screen readers, pointing to the attribute table as the text way to the objects. Page Tab order already started at
  «Проект» and the header sections; the audit's «ПРИВЯЗКА» came after a click on the map.
- **2026-10-07, ГРАДО 2 v0.99.35: short sheet labels on the map (audit #29).** A sheet frame on the map is labelled
  «Лист N «first 28 characters…» · format · scale»; the full title stays in the field above the selected sheet (and in its
  tooltip) and in «Листы». The «область загрузки данных» caption is not drawn when the area is the sheet frames themselves
  — it lay on top of the sheet label (seen on the screenshot).
- **2026-10-07, ГРАДО 2 v0.99.34: «Показатели» before a sketch say «ещё не рассчитано» instead of zeros (audit #28).**
  While there are no new buildings (`t.n === 0`), the «Эскиз» section opens with «Эскиз не построен — показатели новой
  застройки появятся после расчёта…» and an «Открыть «Эскиз»» button; zero values of new-building metrics, new SPP, density
  and coverage show «—» (tooltip «Ещё не рассчитано»). Territory and kept buildings stay as computed.
- **2026-10-06, ГРАДО 2 v0.99.33: guest entry to the shared site without a password.** Owner: «открой доступ к программе
  без пароля и логина» → chose «гостевой вход». Server env `GRADO2_GUEST=1`: `/api/hub/me` without a session signs in as the
  built-in account `guest` («Гость», no known password, not admin; `hub.guest_session`), so the site opens at once; the guest
  sees own projects and those it is invited to («Доступ» → guest). «Выйти» sets the browser-session cookie `grado_noguest`,
  so the login screen stays for the administrator; it has «Войти гостем, без пароля» (`POST /api/hub/guest`). A normal
  account already named `guest` is never handed out (409); a disabled guest gets 403. Off by default: nothing changes until
  the env is set. Test `HubHttp.test_guest_mode`; how-to in `docs/grado2-collab.md`.
- **2026-10-06, ГРАДО 2 v0.99.32: «Нормативы расчёта» no longer say «район определяется…» forever.** When the OSM portal
  does not answer (or there is no territory yet) the district lookup ends without a district, and the zone source line
  kept saying «район определяется…»; now it says «район не определён — выберите зону» once the lookup is over, as
  «Показатели» does. E2E «Условия проекта» waits for the lookup to end instead of 0.5 s (it failed on CI when the portal
  was slow). Two more timing-only E2E steps made robust: «GeoJSON для QGIS» looks for «GeoJSON готов» among all toasts
  shown during the export (a «Создан слой…» toast could replace it at once), T62 «секунды растут» waits up to 6 s for
  «· 2 с» instead of reading one point after 2.2 s (each download counts its own seconds). T38 (theme → basemap) waits up to 3 s for
  the basemap source to change instead of 0.2 s and names the failed condition; T27 (theme → graph canvas) waits for the
  canvas colour the same way; «Условия проекта» waits until the district lookup has finished for the current boundary
  (`tp.rev === TERR_REV`), not only while it is busy — it starts after 0.4 s and used to end in the middle of the next step. Collab
  «B: открыл «Проверка»» waits up to 5 s for the header (name, role), which updates just after `Collab.pid`.
- **2026-10-06, ГРАДО 2 v0.99.31: sheet layout editor snaps like InDesign (ported from DesignCraft).** Owner: «используй
  код этой программы для нашего редактора листов — вёрстка» (https://github.com/storytold/designcraft, Rust, MIT). Rust
  cannot be linked in (no new dependencies), so its alignment pass (`crates/tools/src/snap.rs`: pass_align, offer_box,
  offer, push_alignment_guide) is ported to `web/snap.js`: a dragged label in «Макет листа» meets the edges and centres of
  other labels and of the sheet within 4 screen pixels, nearest hit per axis, magenta guide while dragging; Alt drags
  without snapping. Snapshot history of the sheet's edits/items: Ctrl+Z / Ctrl+Shift+Z (and header buttons), typing in
  one field or arrow nudges in a row are one step. Stored edits format unchanged, PDF/PPTX pipeline untouched. Tests:
  `tests/snap_test.js`, e2e step in the layout block. License: `web/vendor/LICENSE-designcraft`.
- **2026-10-06, ГРАДО 2 v0.99.30: ППТ КРТ sheets share one style table; okrugMain cached; corner districts by the МСК
  frame (#10, #11).** `C_VEC`/`C_BODY`/`C_TAIL`/`C_RAIL` and `cSheet` replace per-sheet copies (PPTKRT_C content
  identical, sha256); `albumgeo.js`: `memoByGeometry`, `cornerPoints`. album_check gol and bez: no differences.
- **2026-10-06, ГРАДО 2 v0.99.29: «Понижать этажность ради инсоляции соседей» — switch in «Эскиз», off by default
  (#12, owner «А»).** Node «Посадка застройки» gets a `relax` toggle (urban blocks only); the T56 lowering in
  `urbanBlocks` runs only when it is on (`relaxIf` in blocks.js); old projects open with it off. Безобразово, 18 floors:
  off 931 743 m² / max 17 floors, on 925 864 m² with sections 17→10.
- **2026-10-06, ГРАДО 2 v0.99.28: street labels keep 1.6 mm from the territory dashes, labels clear photo arrows
  (#8, #9).** The 1.6 mm gap was measured from the dash axis while the territory sign is 2.4 mm wide (0.4 mm left to
  the squares): now from the edge of the dashes, relaxed step by step only when there is no other place. Photo sheet:
  labels avoid arrows by their rotated outline and the arrow numbers, the far side of the road is tried; touching an
  arrow is the last resort. album_check: Cyrillic captions on crops, moved labels are not reported as text changes.
- **2026-10-06, ГРАДО 2 v0.99.27: title as one text block, photo arrows, export progress.** Title sheet: «Об утверждении
  проекта планировки территории по адресу:», address and district are one text block — in PPTX one text box with
  paragraphs (`block`/`para` on text ops, `textblock` in backend_pptx), in PDF the same lines. Photo sheet: labels avoid
  view arrows, a street at the territory may touch an arrow only when there is no other place; arrows are drawn above
  labels. Export shows «PDF/PPTX: лист N из M» from `GET /api/print/progress` (T87).
- **2026-10-06, ГРАДО 2 v0.99.26: ВРИ first, no agriculture in old Moscow.** Owner 06.10: «не может быть в старой
  москве территорий сельскохозяйственного назначения, приоритет всегда у ври, если благоустройство то это
  благоустройство». Old Moscow classifier codes «1.2.9», «1.2.13» (warehouses, railway) are no longer cut to federal «1.2»
  (grain growing) — class by words; outside Новомосковский/Троицкий okrugs agricultural classes 25–28 are never used (ВРИ
  or OSM); «благоустройство» → природно-рекреационная. КРТ 3229: railway strip is railway, :28 is storage.
- **2026-10-06, ГРАДО 2 v0.99.25: owner remarks on the Гольяново album, round 3.** Land use: ВРИ with «завод/фабрика/
  комбинат/цех» is production (class 14); OSM `commercial` is business (class 8), only `retail` is trade — the pink
  «торгово-бытовой» strip by ул. Тагильская is gone. Territory boundary is drawn above every layer (over layers go
  between the white veil and the boundary). The SZZ footnote is not printed. Sheet 9 veil 0.35 → 0.15 (Yandex z18
  is the finest imagery there, same as on yandex.ru). Photo sheet: panoramas captured without house-number tags.
- **2026-10-06, ГРАДО 2 v0.99.24: existing-use legend by the owner's sample, bolder lines.** Sheet 5 legend: groups
  «Функциональные зоны специализированного назначения» and «Транспортная инфраструктура», names and colours from the
  owner's picture (`SPEC_ZONES`, label-rules 21); classification by ВРИ is unchanged. District boundary bold (1.2 mm),
  ЛГР and red lines 1.5× thicker (≥ 0.5 mm) and drawn above the white veil, ЛГР signs larger on the map and in the
  legend (`LT_SHAPE_MM`, `linetype_ops(shape_k=…)`); «территории автодорог, улиц и местных проездов» on all sheets.
- **2026-10-06, ГРАДО 2 v0.99.23: owner remarks on the Гольяново album.** Sanitary zones: established — solid black,
  indicative — black dashed, drawn above the white veil outside the territory (layer `gisogd.szz.lines`, over).
  Sheet 5 land use: Voronoi gap fill no longer leaves a saw of triangles — seed points every 2 m (was 8 m), cells of
  one colour dissolved and simplified. Photo sheet: 8 Yandex panorama frames from the owner's links with view points
  and directions (data in the project, label-rules 14).
- **2026-10-06, ГРАДО 2 v0.99.22: Гольяново album check, last fixes (F7, F9).** Sheet 2: callout lines route around
  district and okrug captions (`_callout_route` in album_io, map frames remember their text ops). Genplan zone number:
  deepest spot also away from the territory border (≥ 4 mm) and not on or inside a building. Street labels keep
  1.6 mm from the territory dashes when placed along a road. Checked on КРТ 3229 rebuilt with owner data (lease rows
  from ЕГРН extracts, address «вл. 8» from the ДГП letter): PDF 18 s, PPTX 20 s with Montserrat embedded.
- **2026-10-06, ГРАДО 2 v0.99.21: full check of the Гольяново album, sheet fixes (F1–F6, F10–F12).** Sheet 5: each
  sanitary zone drawn by its own border (established ones were lost in a merged outline), one note on all SZZ kinds
  with a full stop (`LegendRules.szzNote`), «охранная зона электроэнергетики» without the stray «О» and not inside the
  corner caption reserve. Sheet 6: one legend row per sign (`gpzones.legendRows`). Roads: Yandex road polygons fill
  gaps where ЕГКО has none (`RoadClean.gapFill`) — the road south of НИКИЭТ is back on sheets 4, 6–8. Sheet 9: wider
  ВРИ column, capital first letter, short prepositions bound by a non-breaking space. Sheet 3: «ЖК «…»» (rule 17).
  «вл.1» → «вл. 1». label-rules item 20.
  PowerPoint export: was ~20 min for КРТ 3229, now 112 s cold / 22 s warm (PDF 128 s / 16 s): ЕГКО base of the
  okrug map cached on disk (`~/.grado2/cache/print_ops`, 12 h), PPTX raster fills polygons only within their extent,
  sub-0.1 mm outlines skipped; Montserrat embedded into PPTX (`ppt/fonts/*.fntdata`); `GET /api/print/progress`.
- **2026-10-06, ГРАДО 2 v0.99.20: fixes from the live album rebuild check.** ЕГКО road polygon with a hole touching the
  outer ring (clip by the request box) collapsed in `RoadClean.clean` (JSTS buffer on an invalid polygon) and sheet 4 lost
  its roads: normalise with `union(f,f)` before buffering, and fall back to the unbuffered shape if cleaning loses > 50 %
  of the area (fixture `egko_road_hole_on_edge.json`). Station labels: `station_spot` in print_io picks the best place by
  penalty (never across rails, road polygons, other labels or corner captions; penalty for district/territory borders
  and distance), Безобразово unchanged on all 21 pages. Empty downloads record their request area (`emptyCover`), so the
  «оценка» note disappears after a fresh download.
- **2026-10-06, ГРАДО 2 v0.99.19: manual sheet composition survives any rebuild (T86e).** `carryManual` keeps roles that
  differ from the sheet template (moves, copies, added layers, source order, eye) through «Обновить листы» and
  «Собрать заново» with replace; «Вернуть лист к образцу» still restores the template. E2E group `t86` covers the window.
- **2026-10-06, ГРАДО 2 v0.99.18: collaboration by role groups, download by roles, keyboard and narrow window (T86e, T86f).**
  `mergeSheet` (collab.js) merges `sheet.layout` groups by id and items by key, so two people editing different roles
  of one sheet no longer conflict. `fetchPlan` (sheetlayout.js) drives `buildSection0`: only roles switched on are
  downloaded, the fallback road source is fetched in a second phase only where the main one covers < 90 % of the
  frame. «Слои и листы»: Tab between columns, M «Перенести на лист…» (Enter move, Alt+Enter copy); under 1100 px the
  project layers column folds into a button.
- **2026-10-06, ГРАДО 2 v0.99.17: manual edits, return to template, working copy, own layers (T86d).** «Слои и листы»:
  blue «изменено вручную» on a role differing from the template (`diffFromSeed`) and a dot on the sheet; R / link
  «Вернуть автоматический выбор»; «Вернуть весь лист к образцу» with confirmation; locked sheet + Alt drop or
  «Скопировать как рабочий» makes a working copy next to it, original untouched (deep-equal test). Own layers
  («Свои слои», user:/import:) go onto any working sheet above data, under labels, and into the legend. Station
  label search radius widened (print_io) so «ст. ж/д …» leaves the rail line on sheets 5–9.
- **2026-10-06, ГРАДО 2 v0.99.16: drag and drop in «Слои и листы» (T86c).** Project layer onto a sheet or a role row
  (joins the role group, or a new group in template order if the role is allowed by the sheet template; otherwise a
  plain-language refusal); role onto another sheet moves it, Alt copies; road source queue reorders by grip or
  Alt+↑/↓ and `roadSource` follows the sheet `src` only when the owner changed it. One undo entry per action; edited
  layouts survive «Обновить листы» (`carryLayout`). Golden 59/59 unchanged on untouched sheets.
- **2026-10-06, ГРАДО 2 v0.99.15: window «Слои и листы» (T86b).** Menu «Окна» → «Слои и листы»: album sheets (lock,
  «не готов» with reason), roles of the selected sheet top to bottom (eye hides a role on this sheet only, source,
  frame coverage, badges; road source queue unfolds), project layers grouped by role with sheet numbers. One row per
  role; eye writes `item.on` in `sheet.layout` with undo («layout» kind in layers.js) and survives template refresh
  (`carryOn`). Layer download bbox is now saved in the project (coverage). Golden 59/59 unchanged. `sheetlayers.js`.
- **2026-10-06, ГРАДО 2 v0.99.14: sheet layout by roles (T86a, invisible step).** Owner 06.10 chose variant А (window
  «Слои и листы»). New `sheetlayout.js`: `sheet.layout = {groups:[{id,title,role,items:[{key,on,style?,only?,src?}]}]}`;
  ППТ КРТ template seeds it (`seedLayout`), `viewLayers`/`sheetSpec` read it through `SheetLayout.resolve` while it
  matches `keys` (otherwise old fields). Golden check: 59/59 sheet specs identical on КРТ 3229 and Безобразово (copy).
- **2026-10-06, ГРАДО 2 v0.99.13: legend only from what is drawn (T85a), river labels independent of sheet order (T85b).**
  Album ППТ КРТ: sheets 5–9 list only signs whose objects are inside the frame (parcels, buildings, zone number/index,
  ППТ/ПМТ, ГПЗУ/АГР, parcels inside/outside); empty legend groups are dropped; a documentation sheet with no documents in
  the frame is «не готов» with the reason (`conceptWhy` in albums.js, used by `notReadyWhy`). River labels use roads
  from project data by the vector-sheet rule (`sharedRoads`), so places match on all sheets. Pure rules in
  `legendrules.js`, tests `legendrules_test.js`.
- **2026-10-06, ГРАДО 2 v0.99.12: ЕГКО road polygons on vector sheets, cleaned up.** Owner 06.10: «сделай на всех
  векторных схемах дороги ЕГКО, чтобы остались только полигональные, сделай красиво». Vector sheets (4–8): ЕГКО road
  polygons first, Yandex polygons only where ЕГКО has less than 20 % of Yandex's area in the frame; satellite sheets
  (3, 9): Yandex first, ЕГКО as fallback; roads built from axes are never drawn (`roadsrc.js`). Cartographic cleanup
  per sheet (`roadclean.js`): clip to the frame + 5 %, dissolve into one shape (no seams or hairline gaps; closing
  +0,4/−0,4 м), fragments < 10 м² and holes < 25 м² removed, simplify 0,3 м; colours and outlines unchanged (rule 13). The
  same shape feeds the white «roads» plots, the photo-sheet outline and label obstacles. Checked: КРТ 3229 (ЕГКО 4340 м²
  in the 1:1000 frame chosen, junctions clean at 300 dpi) and the «Безобразово» copy (ЕГКО only on Калужское ш.; village
  streets stay white road plots, as in the owner's sample); unit and E2E green.
- **2026-10-06, ГРАДО 2 v0.99.11: station names always red and always placed.** Owner 06.10: «у метро, МЦД и МЦК
  название всегда красное с белым контуром», «название всегда должно быть со значком». МЦД names are red #FF0013 with a
  white halo like metro and МЦК (the diameter colour stays only in the parallelogram); a station name is never dropped:
  when no free place is found it is put where it covers other labels least (among the places inside the frame).
  Icons stay on every map sheet (owner: «да»). Tests updated; unit, E2E green.
- **2026-10-06, ГРАДО 2 v0.99.10: metro, МЦК and МЦД stations with icons; nested quotes.** Team cycle 24, owner's rules
  16–17. T82: new source `yandex.stations` (Yandex `transport_p` points from the same tiles as the roads, no extra
  downloads): `ft_type_name = transport-metro-station`, `network`/`line` tell metro, МЦК (`moscow_metro-14`) and МЦД
  D1–D5; the name comes in the field «Название» (found on live data — the first version read `name` and drew nothing).
  On album map sheets a metro or МЦК station gets the red «М» (owner's SVG) and its name in red with a white halo, an
  МЦД station its diameter's parallelogram and the name in that colour; a metro and an МЦД station of one name within
  700 m — both icons, one name; the duplicate ЕГКО «ст. ж/д …» label is dropped. Icons are vector paths in PDF, SVG and
  PPTX (`rail_icons.py`); the legend «Транспорт» lists only icons on the sheet. T83: quotes by Russian typography —
  outer «ёлочки», nested „лапки“, on the page (`labelfmt.js`) and in print (`print_io._guillemets`). Checked: a test
  territory at metro «Перово» — «М Перово» in red on sheets 3–9, legend «станция метро»; unit tests, connectors, E2E.
- **2026-10-05, ГРАДО 2 v0.99.9: station labels «ст. ж/д …», labels off the railway, Генплан legend and colours,
  coarse-imagery note, album tests.** Team cycle 23. T78 + owner's rule 15: railway stations (OSM land use «railway»
  with a name, railway=station/halt/yard, Yandex station types, ЕГКО «ст. …»/«станция …») are labelled «ст. ж/д
  Калошино» (non-breaking spaces, no double prefix; platforms, depots, works, ТЭЦ, parks, posts and «СТ …» garden
  partnerships are not stations — `web/labelfmt.js`); the railway and the district boundary are obstacles for
  territory names and numbers (streets unchanged); leaders do not enter the corner captions; leader points closer than
  4 mm are spread; straight quotes in sheet labels become «ёлочки». OSM keeps the `railway` tag (no new queries). T79:
  the Old-Moscow Генплан layer keeps the zone name in `naimfunkzony` and the index in `fztip` — the code read only the
  ТиНАО fields, so zones got the fallback grey and the legend lost its swatches; now both layers are coloured by the
  MapInfo index table (130 — #AD84AE) and the legend shows each zone type in the frame with its index in the swatch
  (`web/gpzones.js`). T81: a sheet whose imagery had to be taken at a coarser zoom (> 600 tiles) gets one grey note
  «снимок грубее обычного…»; the Esri 600 limit counts only tiles under Yandex holes. T80: tests for `over` layers,
  corner captions, the rail swatch, ЛГР marks, the Yandex/Esri basemap (python) and okrugMain/keepParts, СЗЗ order,
  district corners (E2E group t80). Checked: КРТ 3229 rebuilt on the test copy — «ст. ж/д Калошино» beside the track,
  sheet 6 purple with 130 swatches; unit 461 OK with and without PYTHONPATH, connectors OK, E2E green.
- **2026-10-05, ГРАДО 2 v0.99.8: check before export; sturdier Yandex satellite; roads where Yandex has none.** Team
  cycle 22. T74: before «PDF», «PPTX» (window, «Выгрузка ▾», one-sheet PDF) the album is checked — no territory, empty
  header fields (№ КРТ, округ/район, адрес), sheets «не готов» with reasons, «Фотофиксация: снимков нет», layers empty in
  their sheet's frame; if anything is found the window shows one choice bar «не всё готово» with «Выгрузить всё равно» /
  «Отмена» and up to 6 lines (a line selects its sheet or opens «Штамп…»); only one choice bar is open at a time, Esc
  answers the visible one; `albumFile(kind, only, force)`. T75: a Yandex 404 is «no imagery», not a failure (does not
  trip the 10-minute breaker; `sat_io.YandexSat.last_status`); Esri is requested only under missing Yandex tiles, not
  under the whole sheet; more than 600 tiles → a coarser zoom instead of an empty basemap; `_YSAT` under a lock, expired
  entries pruned. Older and frozen sheets also get the Yandex satellite (owner 05.10.2026, Безобразово). T76: where a sheet
  frame has no Yandex road polygons (ТиНАО villages) the sheet takes ЕГКО road polygons, else roads built from axes
  (`roadsrc.js pickRoadSource`); the «территории автодорог» legend item only when roads are on the sheet. Checked: owner
  path on a copy of «Безобразово» (30.09): 9 sheets with roads on all of them; КРТ 3229 path from cycle 21; unit 437 OK
  with and without PYTHONPATH, connectors OK, E2E 375 steps green.
- **2026-10-05, ГРАДО 2 v0.99.7: territory by КРТ number; album header filled from data; failed tiles cached; big
  territories; light «Месторасположение».** Team cycle 21 (audit of the КРТ 3229 album, `docs/ux/audit-2026-10-05-krt3229.md`).
  T72: the map search understands «КРТ 3229» / «3229»: the server finds the object in the ГИС ОГД layer «Комплексное
  развитие территорий» (whole layer cached 30 min in memory), the card reads «КРТ № 3229 · ВАО, Гольяново · 2187-ПП от
  12.08.2026 · 1,66 га» with «Показать на карте» and «Сделать границей территории» (a second click replaces an existing
  boundary); the KRT number goes into the album header. «Свойства» of any single polygon: «Сделать границей территории» /
  «Заменить границу территории». T73: «Штамп…» has «№ КРТ», «Округ, район», «Адрес» and «Заполнить по данным»; empty
  fields are filled at album assembly and before PDF/PPTX — KRT number from the loaded КРТ layer, okrug and district
  from the administrative layer (no longer from Overpass), address from ЕГКО address points inside the territory
  («г. Москва, 1-й Иртышский проезд, д. 8»); typed values are never overwritten (`meta.auto`), an import from a file
  replaces auto-filled values; a title sheet without an address is «не готов: нет адреса» in the window (nothing on
  paper). T69: a satellite tile that failed is not requested again for an hour (`.fail` marks, `TileGuard`); the Yandex
  path skips these marks without counting them as failures. T70: OSM and ЕГКО for large frames are fetched for the
  territory plus a margin, in parts (the page now sends the territory). T71: okrug/district outlines of
  «Месторасположение» simplified to the sheet scale along shared edges (sheet spec 0,26 MB instead of 2,4 MB). Checked:
  owner path on the test copy — «КРТ 3229» in the search → boundary 1,66 га → «Собрать альбом ППТ КРТ» → 9 sheets with
  «№ 3229», «ВАО, район Гольяново», «д. 8» in the header; unit 431 OK; E2E.
- **2026-10-04, ГРАДО 2 v0.99.6: album assembly shows its progress; saved variants; reserve plot colours; wording.**
  Album (T62): while a section is built the status line and the busy toast read «Лист 3 из 9: Ортофотоплан —
  загрузка … · 12 с»; «Остановить» finishes the current sheet and keeps the ones built («Сборка остановлена: готово
  N из 9»); PDF/PPTX export shows «вёрстка N листов на сервере» with elapsed seconds; Overpass timeouts and
  429/502/503/504 are retried on the server (3 attempts, 2 s then 4 s; SSL/connection errors are not retried; a
  losing mirror stops retrying once another answered) and the sheet is built without OSM with the note «улицы OSM не
  загрузились (портал ответил 504) — повторите сборку позже»; the page does not repeat a portal failure itself;
  «не поместились» reasons come back from the server («лист 6: легенда из 23 позиций не помещается — уменьшите число
  слоёв или шрифт») into the row tooltip, the status line and the PDF message. Profile on the Безобразово copy (warm
  caches): a combined Overpass request missed the per-set cache and cost 30 of 33 s — `osm_fetch` now assembles the
  sets from the cached parts; sheet 2 «Месторасположение» still takes 8–9 s of the PDF (5 MB SVG). Variants (T59):
  «Сохранить как вариант…» in «Эскиз» / «Сохранить текущий эскиз…» in «Варианты» → group «Сохранённые» (up to 20,
  buildings and floors with 6-decimal coordinates, stored in the ТЭП node, synced) with «Открыть» (two-click when the
  current sketch has unsaved edits, one reused «Вариант: …» layer), «Переименовать», «Удалить» (two-click); numbers
  are «на момент сохранения», «Открыть» recomputes; «Сравнение» can show a saved variant; viewers cannot change them;
  the third-window toast shows once per session. Reserve plots (T67): per-theme fills (`--res-doo/-school/-clinic`,
  light ДОО salmon, school lilac, clinic muted ochre; dark desaturated with lighter outlines), captions «ДОО / школа /
  поликлиника» from 1:5 000, «Предпросмотр схемы» rows «Резерв: ДОО / школа / поликлиника» with swatches. T68: the
  «не готов» icon in the warning colour, right-pane labels not truncated at 1440, «проектное допущение — в
  постановлениях нет» instead of repository wording in «Нормативы», the standards path removed from the «Показатели»
  note. Open: failed Esri tiles are retried on every render (a sheet took 398 s offline); OSM/ЕГКО refuse territories
  over ~300 ha because the «Ортофотоплан» frame exceeds 150 km²; «Открыть» of a saved variant stays enabled for a
  viewer (local only).
- **2026-10-04, ГРАДО 2 v0.99.5: plots for kindergartens, schools and clinics on the sketch (T6 steps 3–4); block
  insolation pass; album smalls.** «Показатели» show «Резерв: ДОО n, школа 1, поликлиника 1 · X,XXX га (YY %)» above
  the metrics; the sketch gets plots of the exact required area («участок ДОО» / «участок школы» / «участок
  поликлиники», pale salmon, lilac, teal; `m2`, «Места», «Дефицит») placed in the free land of the site outside
  building buffers, streets and plots, within the service radius (ДОО 300 m / ЦАО 500, school 1 000 m / ЦАО none),
  slid from the corner nearest the houses; a plot that does not fit is never shrunk — the note says «ДОО №1
  (0,842 га) не помещается в свободной земле пятна (в радиусе N м от домов) — освободите землю» and a warning line
  appears in «Резерв участков». The search is deterministic (fixed budgets of grid nodes, cheap checks and exact
  tests, no wall-clock), «поиск места прерван: слишком сложное пятно» when the budget runs out; СПП and density do not
  change; «Сохранить слоем» keeps the plots in the plots layer without a duplicate preview. Example B1 of
  `spec-T5-social-objects.md`: school 12 046 m², ДОО 11 200 m², clinic 3 500 m², all within ±0,3 %. On the Безобразово
  copy with the КРТ 3141 boundary nothing fits (130 houses fragment the free land) — reported, not shrunk. Urban
  blocks (T56, partial): after a block is placed, `blocks.js` lowers floors of the section that buys the most light
  per lost m² until the north wing meets the 50 % facade rule (closed 12-storey ring: 35 % → 100 % at −3 % floor
  area); on the example nothing changes — its 66 failing sections are shadowed by neighbouring blocks across the
  streets, which a per-block pass cannot fix (a site-wide pass costs −15 % and 11 s — owner's decision). Album
  (T65/T66): building «Альбом ППТ КРТ» or «Ситуационный план A4» with other sheets present asks «Заменить / Добавить /
  Отмена»; «Листы обновлены по новым показателям» only when a sheet or the ТЭП numbers changed; a legacy sheet keeps
  its changed size after «Обновить листы»; «Подписи этажности: всегда / от 1:2 000 / от 1:5 000» per layer in the
  style panel. Open: a renamed sketch layer falls back to «всегда»; the block pass ignores existing buildings and
  relief; the third-window toast shows once ever.
- **2026-10-04, ГРАДО 2 v0.99.4: template sheets refresh themselves; re-download updates the layer; honest status line.**
  Album (T55): sheets built from templates («Альбом ППТ КРТ» sections, «Ситуационный план A4», ТЭП sheets) carry
  `tpl = {set, i, size, base}` — the template values they were built with. When the ТЭП, the norms, an accepted sketch
  or layer styles change, the template part is rebuilt through the same code that built it (debounced; only when the
  signature changed) and everything the owner changed by hand — title, frame, scale, note, layers, view, photos,
  «Макет» texts — is kept; status line «Листы обновлены по новым показателям»; «не готов: слой «X» не загружен» in the
  sheet note, a warning icon on the row. Sheets from older projects (no `tpl`) are never rebuilt by themselves: only
  «Собрать ▾ → Обновить листы» with a two-click confirmation («Обновить N старых листов по шаблону? Ваши названия,
  рамки и фото сохранятся, набор слоёв и легенда — по шаблону»). Frozen (imported) sheets are untouched. ТЭП rows and
  legends were always computed live at print time; what could go stale was the layer set, the frame and the open
  preview. Data (T61): one portal layer has two keys — `gisogd.<name>` in the «Данные» pick list and `ogd.<code>` in
  the catalog tree — so a re-download from the tree added a duplicate; a pick from the catalog window now updates the
  layer already in the project (merge path, manual edits and `_uid` kept), album loads keep exact keys. The status
  line names the layer and the progress: «ГПЗУ (ОГД): 42 % · 1,8 МБ из 4,3 МБ», «3 из 7: Зоны (актуальные)…».
  «Район определяется…» ends within 30 s: the district comes from the local polygon when OSM is down, K1 stays
  unknown with the note «район не определён: портал OSM не ответил — задайте зону вручную»; raw portal errors are
  replaced by plain Russian («область слишком большая — уменьшите рамку» / «портал не ответил — подождите минуту»),
  the raw text goes to the log. Open: the «Листы обновлены» line also shows when only the signature changed; a legacy
  sheet's changed size is lost on the confirmed rebuild.
- **2026-10-04, ГРАДО 2 v0.99.3: PPTX — satellite tiles clipped to the frame, heavy slides rasterised.** QA on the
  owner's album found satellite tiles running under the legend and the title of the «Ортофотоплан» slide, and slide 2
  of a normal «Альбом ППТ КРТ» with 244 000 shapes / 159 MB of XML (every ЕГКО building, lawn and forest a filled shape)
  that LibreOffice could not open in 9 minutes. Now, for PPTX only (`print_io.py`, PDF untouched): tile quads are
  clipped to the map frame (near-straight ones become cropped images, rotated ones are redrawn inside the frame);
  closed shapes under 0.25 pt without a visible stroke are dropped and rings of 20+ points simplified
  (Douglas–Peucker 0.25 pt = 0.35 m at 1:4 000); when a slide exceeds 20 000 shapes or ~16 MB of XML its heaviest map
  frame becomes one 200 dpi PNG (texts and markers stay vector; frame, legend and stamp untouched) and the slide notes
  say the map is a picture. Synthetic 48 000-building slide: 31.7 MB / 44 000 shapes → 4 shapes + a 0.86 MB PNG,
  LibreOffice 11.2 s → 1.3 s. Not measured on the real ЕГКО slide; not opened in PowerPoint.
- **2026-10-03, ГРАДО 2 v0.99.2: the dock no longer crowds out the map; CSS smalls.** Team decision (council 03.10,
  option А, reversible): a zone holds at most two docked windows when opened from a button — a third opens floating
  with a one-time toast («Третье окно открыто плавающим: в зоне уже два. Поменять — в меню «Окна»»); «Окна» → «Окон в
  зоне: Не больше двух / Без ограничения»; dragging, Alt+arrows, saved layouts and start-up restore are not capped.
  The bottom zone is 32 % of the map-area height by default (a dragged or saved height wins). Dock tabs always show
  their labels (smaller font, ellipsis + tooltip when tight), the active tab has an accent edge, the ribbon button of
  an open window is tinted. «Нормативы» opens docked on the right; «Показатели» stays in the top bar from 1400 px.
  Smalls: a thin scrollbar and edge shadow on overflowing dock panels; the «Варианты» header in one row («Перебор
  типологий», hidden under 520 px); «Листов пока нет. Добавьте лист или соберите альбом», «ППТ КРТ» non-breaking, the
  «Штамп» row as a heading; floor labels «N эт.» only from 1:2 000; `--site-hatch` token lighter in both themes;
  «Слоёв пока нет (эскиз ещё не сохранён)». Open: the toast is shown once ever (localStorage), the 1:2 000 cutoff
  applies to any user layer labelled «Этажность» and is not configurable.
- **2026-10-03, ГРАДО 2 v0.99.1: parking as required area in «Показатели» (server part).** New ТЭП group «Стоянки —
  площадь»: permanent places split by two project conditions «доля подземных, %» and «доля многоуровневых, %» (whole
  numbers, defaults 0, sum ≤ 100, sent in `/api/tep`), the rest ground; places per kind, «наземные стоянки, га»,
  «подземные, м²», «многоуровневые, м²» (floor area), «всего, га»; guest and visitor places are not included (note).
  Area per place: 945-ПП gives only counts (appendix 1 line 1046 — a place per 2 000 m² of park; appendix 6 note 1 —
  90 m² ННП per visitor place), so the three constants `park_m2_ground` 25, `park_m2_underground` 30, `park_m2_multi`
  25 are project assumptions, editable in «Нормативы» and marked «нет в текстах репозитория». Якиманка, 2 519 permanent
  places: 0/0 → 6.298 ha ground; 40/0 → 1 008 underground places 30 240 m², 1 511 ground 3.778 ha, total 6.802 ha.
  Existing fixture numbers unchanged.
- **2026-10-03, ГРАДО 2 v0.99.0: layers are found by role — constraints and the sketch work on real projects.** The timed
  run on a copy of the owner's site project (`docs/ux/run-2026-10-03-bezobrazovo.md`) showed «Ограничения», the
  buildings register and analysis looking for fixed keys (`gisogd.pzz_sub`, `nspd.zouit`, `osm.roads`, `nspd.buildings`…)
  while a real project stores catalog layers as `ogd.<code>` and ЕГКО as `egko.*`: all seven constraint layers were
  empty, 3 566 buildings ignored, the sketch stood on the river. New `web/roles.js` (`window.Roles`): a layer fills a
  role (ЗОУИТ, СЗЗ, ОКН, красные линии, ПЗЗ подзоны/зоны, функциональные зоны Генплана, здания, дороги, вода, зелень,
  соцобъекты, участки) by a manual «Роль в расчётах» set in its style panel (saved with the layer, synced in
  collaboration), else by its source key, else by its catalog code (`GET /api/layer_roles`, built from `SOURCES`;
  `l16/l17/l41`, `gpzu`, `pmtgk`, `virtual84/87` left unmapped until their names are checked). `constraints.js` and
  `analysis.js` use roles and name the layers they used; new sketch bans: water and existing buildings not marked
  «сносим». `robust()` rejects a geometry result with a ring under 4 positions (turf.difference on ЕГКО layers gave
  2-point rings and the sketch came out empty); `EXIST_KEY` → `Roles.existingBuildingsKey()`. Checked on the
  Безобразово copy with the КРТ 3141 boundary: ЗОУИТ 8 zones from 9 layers, water 3, buildings 1 541 kept, 13
  buildings placed with zero overlap of water and buildings; console clean. Open: ПЗЗ from the catalog carries raw
  portal fields, so heights and zero-parameter subzones are not derived from it; `NLayer` graph nodes still look up
  layers by title; `Roles.keys()` is not cached; the building ban depends on the fire-gap layer switch.
- **2026-10-03, ГРАДО 2 v0.98.5: the album is its own section of a shared project.** In hub mode the album sat inside
  the `meta` section, so every edit of any shared parameter (ТЭП node params, views, groups) re-sent the whole album —
  19.5 MB with the owner's nine frozen sheets, on every push and autosave. Now `album` is a section of its own
  (`hub.py` `SECTION_RE`, `split_project`/`join_sections`, `LAYOUT` marker `layout: 2`; `collab.js` split/join/merge3 —
  the sheet-by-sheet merge of v0.98.1 now runs on that section). Measured on the Безобразово copy: a meta edit sends
  7.9 KB instead of 19.5 MB; the album goes only when the album changes. Old projects open as before (the server
  splits the album on read; a `meta.json` without the marker gets the album revision set to the current one, so a
  stale push conflicts instead of overwriting). A page of an older version against the new server gets 426 on a meta
  push and changes nothing; reload open tabs after the deploy. Tests: test_hub 152 (17 MB album, meta push < 100 KB,
  old layout, 426, album 409), collab 84; the collab browser scenario green on a snapshot.
- **2026-10-03, ГРАДО 2 v0.98.4: «Условия проекта» in the «Нормативы» window — norms zone and free places in existing
  social objects (T6, step 2).** Owner's decisions 1В and 2А. At the top of «Нормативы»: «Образовательная зона» (зона 1 /
  зона 2 of 2151-ПП) with its source beside it — «по району <X>», «выбрана вручную · [по району]» or «зона 2 принята:
  район не в списках 2151-ПП» for a district outside the lists; three whole-number fields 0–100000 with one-line hints:
  «Свободные места в ДОО», «Свободные места в школах», «Свободные посещения в смену в поликлиниках» (default 0). Any
  change recalculates the ТЭП; the group «Резерв участков» shows the deficit per type, the number and areas of plots to
  reserve and the total in m² / га / % of the territory (example B: 175 / 400 / 100 free → 2,675 га, none → 3,684 га).
  Values are stored in the project (graph node of the ТЭП, `tp.free`, `tp.zoneSet`), survive save/reopen and
  collaboration; old projects get 0 and the automatic zone. «Вернуть все действующие» resets norms only, not these
  conditions. Choosing a zone no longer freezes K1, K2 and ТиНАО (the old «Образование» select in «Показатели» did);
  «по району» returns to the district's zone. A viewer of a shared project sees the fields disabled. Nothing is drawn
  on the map yet — the reserved plots are the next step.
- **2026-10-03, ГРАДО 2 v0.98.3: a dark basemap in the dark theme; social-object deficit and plot sizes on the server
  (T6, step 1).** Owner 03.10: «карта Б, Carto». CARTO's tiles now need an API key (every tile comes back as an «API KEY
  REQUIRED» placeholder), so the dark theme uses Esri's dark basemap instead (Canvas World_Dark_Gray_Base, same provider
  and terms as the satellite layer, no key, Russian street names): «Схема OSM» swaps to it when the theme is dark and
  back to OSM in the light theme, at once on the theme button and on the OS setting, without marking the project
  unsaved; satellite basemaps unchanged; attribution «Подложка © Esri, HERE, Garmin, © OpenStreetMap contributors».
  Social objects (owner's answers 1В 2А 3А 4А 5А; plan `docs/team/plan-T6.md`): the preset `moscow_calc2.json` gets
  three project inputs `free_doo`, `free_school`, `free_clinic` (free places in existing ДОО, schools, clinics; default
  0) and the metric group «Резерв участков»: deficit per type, number of ДОО plots (split above 350 places, q+1 first),
  plot areas by the 2151-ПП tiers (ДОО ≤150 → 35, else 32 m²/place; school by the deficit: ≤900 → 19, ≤1500 → 16, else
  14; clinic 0,35 га when the deficit > 0), totals in m² / га / % of the territory. `/api/tep` accepts the three numbers
  (0–100000, else 400) and returns `social: [{kind, places, m2}]`. `place_info`: a district outside the 2151-ПП lists
  gets зона 2 with `zone_note`. Fixture numbers (20 га, СПП 450/150 тыс. м²): B0 36 844 m², B1 26 746, A1 9 274 — asserted
  through the engine (`test_social_fixture.py`, `test_server.py`). Nothing changes on screen for the social objects
  yet: the «Нормативы» inputs and the plots in the sketch are the next steps.
- **2026-10-05, ГРАДО 2 v0.98.14: okrug map drops only small distant pieces.** `okrugMain` also keeps every part of
  at least 2 % of the main part's area, whatever its distance (whole districts such as a separate Крюково or Молжаниновский
  stay). Checked on all 12 okrugs: every okrug panel shows all its districts (САО 16/16, ЗАО 12/12, ВАО 16/16); ВАО still
  drops only its two tiny northern pieces (2 and 17 га).
- **2026-10-05, ГРАДО 2 v0.98.13: okrug map keeps its districts.** v0.98.10 clipped the districts of the okrug panel to
  the okrug's main part with `turf.intersect`, which failed on complex outlines and dropped whole districts (САО showed
  4 of 16; found by the team's E2E). Now each district keeps the parts whose inner point lies in the main part
  (`keepParts`): САО 15 of 16 (Молжаниновский, the distant part, is left out by design), СВАО 17/17, ВАО 16/16. The part
  of the okrug that holds the territory is always kept (team architect).
- **2026-10-05, ГРАДО 2 v0.98.12: СЗЗ in ГИС ОГД symbology.** Owner after the team audit: «рисуй, но возьми условные
  для СЗЗ как на ГИС ОГД». On the use sheet all sanitary zones are drawn by the portal layer styles (CartoCSS of
  virtual1743 / 1745 / 1746): established — solid #00FFC5, calculated — solid #F3F707, orientative — red #DF1A07 dashed
  9/7 px; boundary only, 1,4 px (~0,36 mm); legend «line» swatches in the same order. Orientative zones are drawn again
  (the morning's «hide» is cancelled). Owner's other answers: the photo sheet is printed as is; ownership is entered by
  the owner in the parcel's properties. A СЗЗ whose boundary does not cross the frame (the whole sheet inside the zone,
  as КРТ 3229 in the orientative СЗЗ) gets no legend swatch but a note under the legend.
- **2026-10-05, ГРАДО 2 v0.98.11: Yandex road polygons on every album sheet; district captions by corner.** Owner:
  «для всех схем используй полигональные дороги яндекс», «в верхнем левом углу район Метрогородок, в правом нижнем
  Гольяново, одинаковый кегль у подписей». Sheets 3–9 draw roads from `yandex.hd_roads` only (no `calc.uds_ya` axis
  driveways, no `egko.roads`); the use sheet's «roads» share test, the photo sheet casing and the label obstacles use
  the same polygons. When the frame's top-left and bottom-right corners lie in different districts, the top-left
  caption names that corner's district (with its okrug) and a new bottom-right caption (`mapNoteBR`,
  `album_io.MapNoteFrame(corner="br")`, above the legend plate on the ortho sheet; print reserves the space for map
  labels) names the other, both 14,3 pt; a district without a corner gets a 14,3 pt label inside its part.
- **2026-10-05, ГРАДО 2 v0.98.10: album ППТ КРТ after the owner's review of КРТ 3229 (Гольяново).** Rules first:
  `docs/standards/albums/label-rules.md` item 14. Print: REDLN97 line marks (СЗЗ «Т», природный комплекс triangles)
  were stroked with the line width (0,3 mm) on ~0,6 mm glyphs and came out as blobs with spikes — marks now get their
  own width (0,15 of the glyph scale) and round joins, in the legend and on the map; this fixes Безобразово too on its
  next PDF export (its frozen sheets are rendered by the server). Legend: «граница объектов природного комплекса»
  (also «режимов», «памятников»); orientative СЗЗ (code 63) are not drawn and not listed, other СЗЗ kinds sit together.
  Satellite on sheets 3 and 9 — Yandex (`server.yandex_sat_tile`, EPSG:3395 grid in `print_io.tile_ops(proj="3395")`,
  z ≤ 18, the cache of the AutoCAD export); Esri goes underneath only when a Yandex tile is missing. This reverses the
  old «Yandex imagery not in deliverables» rule (owner 05.10.2026). Sheet 3 roads — Yandex road-surface polygons only
  (`yandex.hd_roads`), no axis-built driveways or ЕГКО roads. Railway main tracks on sheets 4–8: new source
  `yandex.rail` (z18, `transport-railway`), black line with white dashes, legend «Транспорт → железнодорожные пути»
  only when visible. Neighbouring districts in the frame: red district boundary on sheets 4–9 (as on sheet 3) and
  «район …» labels deep inside each neighbour's part; layers with `over` (district boundary, railway) are drawn above
  the white mask. Sheet 2 okrug map: parts farther than 3 km from the main body are dropped (`okrugMain`; ВАО's
  northern exclave), so the okrug is drawn larger; the Moscow-wide panel is unchanged. Deploy script goes Mac → msk →
  grado (was via AEZA-US). Note: branch `team/t60` (v0.98.3–0.99.6, unmerged) also edits `albums.js`, `print_io.py`,
  `server.py`, `sat_io.py` — reconcile on its merge. Tests: print (thin round marks, 3395 rows), server source list.
- **2026-10-03, ГРАДО 2 v0.98.2: dark theme polish, help texts, graph labels scale with the interface.** Second-pass
  leftovers (`docs/ux/audit-2026-10-03-pass2.md`, creative spec `docs/ux/spec-2026-10-03-dark-theme.md`). Dark theme:
  the scale line and the map attribution sit on a panel-coloured plate instead of a white one; the halves of
  «Сравнение» are dark with a thin frame; sheet previews and the layout keep white paper but get a frame and shadow on
  a dark area; selected and hovered rows reach 4.5:1 (`--accent` #6aa8f2, `--bad` #f5806f, `--selrow` #203550), field
  borders 3:1 (`--line-2` #6a6a6a). The light theme is untouched. The map itself stays light — whether to dim the OSM
  basemap in the dark theme is the owner's choice (BOARD «Ждёт владельца»). «Схема расчёта»: node text, title and row
  heights follow the interface size (`--k`: 13/12 from 1700 px, 7/6 from 2200 px); the saved graph is identical at any
  size (sizes and the truncated layer-node title are stored at scale 1; pasted and cloned nodes too). Help F1: the
  tables of keys share one first-column width; «Как начать» and «Новое» name «Листы и альбом», the «Выгрузка ▾» menu
  and «Собрать ▾» → «Из файла…». The long status hint is shorter. Norms: `docs/team/spec-T5-social-objects.md` — the
  social-object specification (ДОО, школа, поликлиника by 2151-ПП and 2150-ПП) with a worked 20-га example and
  `core/compute/tests/test_social_fixture.py`; five norm questions wait for the owner before plots are reserved in
  the sketch.
- **2026-10-03, ГРАДО 2 v0.98.1: shared album merged sheet by sheet; «Выгрузка» menu leftovers.** Shared project: when two
  people change the album at the same time, `collab.js` merged the key `album` as one value and one side's sheets vanished
  silently. Now `mergeAlbum` merges sheets by `id` (order via `mergeOrder`; a sheet changed on one side is taken from
  there, the same change on both from either, different changes on both — theirs with the conflict «альбоме (лист N)»; a
  sheet one side removed and the other edited stays with the edit; new sheets of both sides are kept); `meta` and the
  other album keys merge per key as before. Old projects whose sheets have no `id`, or a list with a repeated `id`, are
  merged as one value with the old rule. 13 new checks in `tests/collab_test.js` (79). Menu «Выгрузка ▾»: after an item
  is chosen (mouse or Enter) the focus returns to the «Выгрузка» button unless the item moved it into a window or
  tool; during a DXF / GeoJSON / Excel export the button is disabled and focus comes back afterwards; while a PDF or PPTX
  of the album builds the items «PDF альбома» / «PPTX альбома» are grey with «Идёт сборка…» (`window.albumBuilding`);
  `ALBUM.meta.peak` keeps the largest sheet count ever saved («Раньше в проекте было N листов»), not the last one.
  Enter or Space on an item of an open menu («Выгрузка», «Окна») chooses the item: the map's «repeat the last command» key
  handler (`cad.js`) no longer swallows it while the focus is inside a menu. E2E: three T36 steps; the T34 status-line step no longer depends on the clock (`editedAt` is cleared before comparing
  with sample dates — it broke after 13:07 MSK on 03.10).
- **2026-10-03, ГРАДО 2 v0.98.0: the «Листы и альбом» window rebuilt; one «Выгрузка» menu.** Owner 03.10: «окно листы и
  альбом неудобное и странно свёрстано»; «три кнопки очень похожи по смыслу и не понятны интуитивно». Spec:
  `docs/ux/spec-2026-10-03-sheets-and-exports.md`. Top bar: «Листы и альбом» (sheet-count badge, Ctrl+P) and
  «Выгрузка ▾» with six items and a one-line explanation each (Чертёж DXF, ГИС ОГД в DXF, GeoJSON для QGIS, Excel: ТЭП и
  листы, PDF альбома, PPTX альбома); «DXF ГИС ОГД» is «ГИС ОГД в DXF» everywhere; keyboard: Enter/Space/↓ open, ↑↓,
  Home/End, Esc, Tab. «Слои» and «Свойства» are back in the bar from 1560 px. The window: status line («Альбом: 7
  листов · собран 03.10 12:40 · PDF 03.10 12:41», «Раньше в проекте было N листов (дд.мм)» when empty), «Добавить лист
  ▾» (A3 / A1 / слайд 16:9), «Собрать ▾» (Альбом ППТ КРТ, Ситуационный план A4, Раздел, Из файла…), «PDF», «PPTX», a
  collapsible «Штамп…», one line per sheet (number, name, format · scale, content icons, «готовая»), the selected
  sheet's settings beside the list from 640 px and below it when narrower; no horizontal scrolling in any dock. The
  «Проекты» list shows «Альбом: N листов · собран дд.мм» (server `list_projects` returns `album_n`/`album_at` read from
  the file without parsing it; cache keyed by mtime_ns + size). `ALBUM.meta.peak`/`editedAt` recorded on save.
  Open: focus does not return to the button after choosing a menu item; `peak` is the last count, not the maximum;
  PDF/PPTX in the menu do not grey out while a build runs.
- **2026-10-03, ГРАДО 2 v0.97.0: an album can be imported from a project file («Листы» → «Из файла…»).** Owner 03.10:
  his finished КРТ layout (9 sheets) lived only in a backup folder; the live project showed «Лист 1». «Из файла…»
  reads a `.grado2` in the browser — a whole project (its `album`) or a bare `{meta, sheets}` album — and either
  replaces the current sheets or appends them (in-place choice bar: focus on its first button, Esc cancels). Sheets
  that carry their own layers with geometry (a rendered print spec) become «готовая вёрстка»: they draw from their
  own data without project layers, format, scale and legend are locked, they have no frame on the map and are left
  out of frames / ГИС ОГД / DXF. Imported sheets get ids `imp_<time>_<n>`; empty album meta fields are filled from the
  file; `builtAt` is the import time with «импортирован из файла …» in the status line; missing project layers or
  views are listed in a toast («в N л. нет слоёв: …») instead of being dropped silently. A viewer of a shared project
  cannot import. Files over 25 MB ask first («проект станет большим…»); over 400 MB are refused; a project with the
  owner's 9 frozen sheets is 17.4 MB and the status line says so. Checked with the owner's real files: 9 sheets, PDF
  of 9 A3 pages whose page 2 is pixel-identical to his finished PDF; the full 30.09 project gives 21 sheets. Not
  checked: PPTX of frozen sheets; collaboration with an 18 MB album (the whole album is re-sent on each meta edit).
- **2026-10-03, ГРАДО 2 v0.96.3: dragging never selects text; the album status line.** Owner 03.10: «при растягивании
  окна или вообще при протаскивании мышкой выделяется беспорядочно текст». While a mouse button is held outside
  fields and table cells, `<html>` carries `.nosel` (user-select none for the whole page, including the table cells a
  window or splitter is dragged across); it is removed on release, cancel, context menu, loss of window focus and on a
  move without buttons. Window headers, tab strips, splitters and resize grips do not start a selection at all. Help
  text stays selectable; a click on a button keeps a selection made in a table. «Листы»: a status line «Альбом: N
  листов · собран дд.мм.гггг чч:мм» / «Альбом ещё не собирался», plus «PDF/PPTX: сохранён … в папку загрузок»;
  `builtAt`, `pdfAt`, `pptxAt` live in `ALBUM.meta` and sync in collaboration. Where the album is stored: only in the
  project file (`album` section); PDF and PPTX go to the browser's downloads folder. Found (not fixed): in a shared
  project two people editing the album at the same time keep one side's whole album (`mergeMeta` treats `album` as
  one key) — the other side's sheets are dropped silently.
- **2026-10-03, ГРАДО 2 v0.96.2: document titles are never shortened in the album.** `docTitle` (albums.js) no longer
  adds «…» to titles over 120 characters. On the КРТ document slides the lists «Проекты планировки территории» /
  «Проекты межевания территории» wrap every title in full; when the list does not fit, the item font steps down
  (10 → 9 → 8 → 7.2 → 6.4 → 2.0 mm) and the frame grows with it; if it still does not fit the sheet is marked «не
  готов» with the reason (continuation slides are not made). Legend labels on sheets wrap fully instead of being cut
  at the third line; the legend stops between items, never inside a label. Checked with a real 498-character title
  (three of them on one slide). Open: a list that does not fit at 2.0 mm still has no continuation slide.
- **2026-10-03, ГРАДО 2 v0.96.1: full ППТ titles from ГИС ОГД.** Owner 03.10: in the КРТ presentation near
  д. Безобразово the ППТ title was cut («…от газорегулято…»); «название ППТ всегда должно быть написано полностью и как
  на ГИСОГД». Cause: the portal's shapefile DBF caps text fields at 254 bytes (UTF-8 → about 127 Cyrillic characters);
  216 of 530 «ПП территорий» titles in the cache were cut. The connector (`gisogd_api.py`) now detects capped values
  in any field and refills them from the portal's CSV attribute export, one request per layer per TTL, cached as
  `<code>.csv.gz`, matched by `gisguid` (then `orbis_id`); on the cache of «ПП территорий» all 521 objects with geometry
  got the full title (up to 498 characters). If the CSV fails the shapefile value stays, the layer note says «названия
  документов могли быть обрезаны порталом…», the next attempt waits an hour (`<code>.csv.fail`). The lines cache is
  renamed (`.shp.lines2.gz`) so layers loaded earlier are rebuilt at once. Re-download the document layer and rebuild
  the album to get the full titles; the «…» added by the album for titles over 120 characters is removed in the next
  version.
- **2026-10-03, ГРАДО 2 v0.96.0: dark node graph, help with contents, first-run path, calmer wheel.** The «Схема расчёта»
  canvas follows the theme (background, nodes, text, links) and switches live; theme colours stay out of the saved
  project (the saved graph is identical in both themes, a toggle marks nothing dirty and pushes nothing). F1 help: a
  search field, a contents list with jump links, «Наверх» in every section, a first section «Как начать» (boundary →
  data → constraints → sketch → indicators and norms → sheet and PDF / exports) and a «Новое» line; the search resets
  on reopen; F1 from the search field toggles the window. The first-run card «С чего начать» is one phrase with
  «Нарисовать границу» and «Пример» and never returns once a boundary exists; the status hint leads on: «Граница задана.
  Загрузите данные или постройте эскиз.» → «Эскиз готов. Откройте «Листы», чтобы собрать лист и PDF.»; the idle hint at
  1280 is «Начните с границы: «Данные» → «Нарисовать границу».» (full text in the tooltip). Layer search works in the
  by-sheet tree. Default floating-window sizes grow on large screens (`uiK()` reads the real font size). Mouse wheel:
  one notch ×1.07, ten notches ×1.8 (was ×10), anchored at the cursor; trackpad scroll and pinch unchanged (measured
  through CDP). The changed-field marker in «Нормативы» is stronger. Pass 2 of the windows: an automated check of all
  20 windows at 1280×720 and 2560×1440 (light) found nothing cut or off-screen; the remaining items are in
  `docs/ux/audit-2026-10-03-pass2.md` (light map in the dark theme, dark-theme pass by eye, legend/3D previews, help
  table columns, graph labels at 2560, grips on satellite basemaps).
- **2026-10-03, ГРАДО 2 v0.95.1: text in the PDF album can be searched and copied.** The PDF writer
  (`core/render/grado_render/backend_pdf.py`) embeds its TrueType font as Type0 / Identity-H; it now adds a `/ToUnicode`
  CMap built from the glyphs actually used. Before, `pdftotext` on a test sheet gave «ŘůŹźŧŽůŵ…»; now «Ситуационный
  план», «Технико-экономические показатели», «25,0 тыс. м²/га». The picture is identical (0 different pixels at
  100 dpi), the file grew by 567 bytes. Limits: the reading order is the drawing order; legend symbols drawn as paths
  carry no text; not checked by hand in a PDF viewer.
- **2026-10-03, ГРАДО 2 v0.95.0: exports for QGIS and Excel, district by area share, layer search.** A small arrow next
  to «DXF» opens «GeoJSON для QGIS» (the same layers as the DXF export plus the boundary → zip with one МСК file per
  layer) and «Excel: ТЭП и листы» (numbers as numeric cells, empty values as empty cells, the sheet list, the project
  name and the note «Нормативы изменены вручную: N»); DXF stays one click. The territory polygon goes to `/api/place`
  (one request 0.4 s after the last boundary edit): «Показатели» shows under «Район» «по большей доле площади: Беговой
  51 %, Хорошёвский 49 %»; a failed lookup clears the old shares. The new ТЭП group «Участки социальных объектов» of
  v0.94.1 appears in «Показатели» by itself. All variants get «Население» and «ДОО, мест» (four requests at a time).
  The node graph view scales with the interface size on large screens. «Слои» has a search field («ё» = «е», Esc
  clears; not in the by-sheet mode). The status hint is fitted by a binary search. Between 1481 and 2000 px «Слои» and
  «Свойства» moved from the top bar into «Окна»: the bar did not fit at 1920 before. Opening the export menu closes
  «Окна». E2E: the export steps wait up to 40 s (the 100 000-object test layer took over 5 s on a busy machine —
  one false failure). Open: layer search in the by-sheet mode; `uiK()` reads a `calc()` and returns 1, so default
  floating-window sizes do not grow on large screens; hidden layers are exported like in DXF; hub project list after
  login was checked only by the collab scenario.
- **2026-10-02, ГРАДО 2 v0.94.1: plot areas of social objects in ТЭП; sturdier GeoJSON export (server part).**
  New ТЭП group «Участки социальных объектов»: «Число ДОО», «Участок ДОО, га (не менее)», «Число школ», «Участок
  школы, га (не менее)», «Число поликлиник», «Участок поликлиники, га (не менее)», from the demand already computed.
  Norms from the texts in `docs/standards/moscow-ngp`: 2151-ПП table 1.4.1 rows 3.1–3.2 (ДОО: up to 150 places 35 m²
  per place, 151–350 — 32), table 1.4.2 rows 3.1–3.3 (schools: up to 900 — 19, 901–1500 — 16, over 1501 — 14),
  2150-ПП table 1.4.1 п. 2.1 (clinic 0.35 ha per object); all ten numbers are constants with sources, editable in
  «Нормативы». Rules where the text is silent (stated in the metric notes): a ДОО demand over 350 places is split into
  equal objects of at most 350; a school is one object of any capacity; exactly 1501 places counts as «свыше»; one
  clinic. Not computed: built-in ДОО (20 m²), cadet schools, +0.2 ha for a dormitory, the reductions of up to 10 %.
  Якиманка: 291 × 32 = 0.931 ha, 595 × 19 = 1.131 ha, clinic 0.35 ha; earlier fixture numbers unchanged. GeoJSON
  export: a GeometryCollection is flattened, empty geometry skipped (counts in README.txt), Windows reserved file names
  get «_», at most 200 000 objects per export. `/api/place` keeps its last 256 answers.
- **2026-10-02, ГРАДО 2 v0.94.0: the interface scales with the screen; narrow window; variants follow the norms.**
  Owner 02.10: «продолжай оптимизировать интерфейс и для удобства пользователя и для разных экранов». One factor `--k`
  drives the size tokens (heights, fonts, icons, top and status rows): 1 below 1700 px (1280×720 screenshots are
  pixel-identical to before), 13/12 from 1700 (font 13 px, ribbon 30 px), 7/6 from 2200 (font 14 px, ribbon 33 px, layer
  rows 28 px). Side panels are `clamp(280px, 14vw, 380px)`; a width set by dragging still wins. «Окна» → «Размер
  интерфейса: Авто / Обычный / Крупный», kept in localStorage and applied before the first paint by `web/uisize.js` (a
  separate file: the page's CSP `script-src 'self'` does not run inline scripts — the first version was inline and
  failed the lead's browser run). The map is not scaled (the same click gives the same МСК coordinate within 0.01 m);
  printed sheets do not depend on `--k`. At ≤ 900 px wide the bottom dock takes at most 40 % of the height by default
  and its tabs scroll sideways; the status hint is shortened by whole words (the «F1 — клавиши» tail first) with the
  full text in a tooltip. The empty «Слои» panel says «Слоёв нет. Нарисуйте объект или загрузите данные.» with a link
  to «Данные». The variants table recomputes its ТЭП when norms or territory parameters change (`syncVarTep`,
  debounced, stale answers dropped) and shows «Население, чел.» and «ДОО, мест». Open: only the first six variants get
  the new columns («—» for the rest); the node graph canvas font stays 11 px on large screens; `fitHint` measures
  once per dropped word; Retina and Windows 125 % not checked; boundary grips not checked in the dark theme.
- **2026-10-02, ГРАДО 2 v0.93.1: server part for exports, districts by area, sport split (no buttons yet).**
  `POST /api/export/geojson` — layers `{layers:[{name, features}]}` in lon/lat → `grado2-geojson-msk.zip`: one
  `.geojson` per layer in МСК (same transform as DXF, a `crs` member with the МСК definition, Russian field names kept)
  and `README.txt`. `POST /api/export/xlsx` — `{tep:[{group,title,value,unit}], sheets:[{n,title,format,scale}], note?,
  project?}` → `grado2-tep.xlsx` with worksheets «ТЭП» and «Листы», written with the standard library; numbers are
  numeric cells, text starting with = + - @ stays text; opened in LibreOffice by the reviewer, not in Excel.
  `POST /api/place` takes an optional territory `polygon`: district, education zone, K2, okrug and ТиНАО follow the
  district with the largest area share (local reference `docs/standards/admin/moscow-adm.geojson`, no portal traffic);
  the answer adds `districts:[{name, share}]` and `chosen_by`; `inside_ttk`, K1 and the rail distance still use the
  centre. Flat sport facilities are split by 1557-ПП п. 1.3.3.2: 570 m² within 500 m and 400 m² within 1500 m per
  1000 people (two constants, two metrics). The note «Нормативы изменены вручную» reaches PDF, SVG and PPTX (rows come
  from the client — test); DXF has no ТЭП table. `core/geom` is now on the server's import path and in the installer
  spec (the first version worked only with PYTHONPATH set — found by the lead's run without it). Open: a
  GeometryCollection makes the GeoJSON export answer 400; no feature-count cap; the frontend still sends a centre
  point only and has no buttons for the two exports (next step).
- **2026-10-02, ГРАДО 2 v0.93.0: window «Нормативы расчёта»; floating windows stay on screen; nothing cut at 1280.**
  Owner 02.10: «нормативы постоянно меняются, поэтому должна быть возможность их вручную менять перед расчётом, но поля
  должны быть предзаполнены нынешними нормативами». «Показатели» → «Нормативы…» opens a window (new module
  `web/norms.js`, `norms.css`): collapsible groups, each field prefilled with the current value from the preset, the
  decree, clause and edition under it (or «проектное допущение»), search by title. A changed field has an accent bar,
  «действующее: 44» and a return button; «Вернуть все действующие»; a value outside the limits is not applied
  («Допустимо от N до M»). Overrides are kept as differences in the ТЭП node parameters (`tepParams(node).constants`),
  so they are saved with the project and synced — no format change; single ТЭП and the variant search send the same
  ones. «Показатели» and the ТЭП table of a sheet show «Нормативы изменены вручную: N». A viewer sees the window
  read-only. Seven green-area and playground norms (0.25, 0.02, 5, 3.5, 0.6, 1.5, 0.7 by 2152-ПП table 1.4.2) moved
  from metric expressions into `constants`; the Якиманка fixture is unchanged. Norms are fetched on the first
  calculation or when the window opens (an early fetch before login in hub mode gave 401 and broke the project list).
  Screens (audit `docs/ux/audit-2026-10-02-screens.md`): a floating window is kept inside the map area while dragged,
  on a browser resize and when restored from a layout, shrunk if larger, never under 160 × 120 px; «Построить эскиз»,
  «Сохранить слоем», graph buttons wrap instead of being cut, typologies are an even two-column grid, the project
  button shows «Без названия» in full at 1280, layer names in «Ограничения» wrap; the hub sync label has a fixed width.
  Open: the variants table keeps old numbers after a norm change until the search is run again; the note line in
  DXF/other exports of the ТЭП table is not checked; dark theme and hub header not checked for the CSS fixes.
- **2026-10-02, ГРАДО 2 v0.92.0: the territory boundary can be edited, and drawing snaps to it.** Owner 02.10: «до сих
  пор нет возможности редактирования границы территории, при черчении должна работать привязка и к вершинам
  территории». Click the red dashed boundary (within 6 px) or «Изменить границу» in «Данные»: square grips on
  vertices, triangles on side midpoints, area and vertex count in the right panel. A grip is moved by click–click or
  drag (snaps and typed МСК `X;Y` work), a triangle adds a vertex, a grip + Del removes one (not below three per
  contour); Ctrl+Z / Ctrl+Shift+Z; Esc deselects. Multi-part boundaries and holes are editable. Every edit goes through
  `setTerritory` (area, graph nodes, autosave, collaboration). An edit that makes the boundary cross itself, have zero
  area or push a hole outside its contour is refused with a reason in the status line. Replacing the boundary («Из
  файла», «По участкам», «Пример», another person's change) drops the undo entries of vertex edits, so Ctrl+Z cannot
  bring an old boundary back over the new one. A viewer of a shared project cannot edit (guard in `CAD.terrEdit`, the
  selection is cleared when the role becomes viewer). Object snap (`gather()` in cad.js) now takes the boundary too:
  vertices «конечная точка», side midpoints, edges — while drawing, in «Вершины» and for the boundary's own grips;
  0.13 ms per call on a 5 000-vertex boundary. Open: «ТОПО» does not drag neighbouring objects with a boundary vertex;
  a click within 6 px of the boundary selects the boundary rather than a parcel under it; not checked with a second
  live collaborator.
- **2026-10-02, ГРАДО 2 v0.91.4: norm constants can be overridden in the ТЭП request (server part).** Owner 02.10: norms
  change all the time, so they must be editable before a calculation, prefilled with the current ones. The preset
  `moscow_calc2.json` has a `constants_meta` block: for each of the 31 constants a title, unit, group, decree and
  clause, edition and limits (sources from `docs/standards/moscow-ngp/preset-audit-2026-10-02.md`; project assumptions
  are marked as such). `GET /api/tep/norms` returns them with current values; `POST /api/tep` accepts
  `constants: {id: number}` and answers `constants_changed`. Without overrides the answer is the same as before.
  Not yet: the window with the fields (next step); green-area and playground norms (0.25, 0.02, 3.5, 0.6, 1.5, 0.7)
  are still written inside metric expressions and are not editable.
- **2026-10-02, ГРАДО 2 v0.91.3: objects keep their identity on a re-download.** «Выгрузить заново» matched objects by
  their stable key (the cadastral number for ЕГРН parcels) but gave every unedited object a new internal `_uid`, derived
  from its place in the list and its geometry — only 2 of 1122 unchanged parcels kept it. Now a matched object carries
  its old `_uid` (`Collab.keepUid`), also when its geometry was updated by the portal; new objects get a new one as
  before. Collaboration merges and selections that rely on `_uid` no longer lose such objects. Test: 120 synthetic
  parcels with new portal ids, noise and another order (`tests/collab_test.js`). The collaboration browser scenario
  no longer clicks «Доступ» while the header buttons shift for ~30 ms after a project opens (the sync label changes
  width) — it waits for a steady button and a visible window. Open: the shift itself (a fixed width for the sync label).
- **2026-10-02, ГРАДО 2 v0.91.2: project event stream keeps its own hub.** The live event stream of a shared project
  (`/api/hub/project/<id>/events`) now holds the hub it started with. During the unit tests a stream from an earlier
  test outlived the test's hub and logged a 500 «'NoneType' object has no attribute 'session_user'»; three runs of the
  355 unit tests are now clean. Nothing changes for people using the program. Still open: the collaboration browser
  scenario sometimes fails at «A: нет элемента #hubShareLogin» (1 of 3 runs on 02.10).
- **2026-10-02, ГРАДО 2 v0.91.1: review fixes for v0.89–0.91.** Messages and the busy bar now show above the layout editor
  (its «Сбросить всё» asks to confirm through a message that was hidden behind it). A viewer of a shared project cannot
  use «Из файла». A file with one broken polygon still gives a boundary from its other contours. The situational plan
  reloads OSM street names when the loaded area is too short north–south too, not only east–west. In the layout editor
  Tab, Enter and Space on its buttons work, and no key (Ctrl+Z included) reaches the map underneath; an own text cannot
  be emptied into an invisible one. The Data window names the `sit.*` group. Edits from a hand-edited project file with
  wrong types no longer break printing.
- **2026-10-02, ГРАДО 2 v0.91.0: sheet layout editor («Макет», like the QGIS print layout).** Third feature of the
  unmerged branch of 25.09 (v0.54.2), redone on the current program.
  - «Листы» → pencil-ruler button in a sheet row (or double click on the sheet preview) opens the finished sheet full screen.
    Any text of the sheet — title, header, map labels, legend lines — is picked with a click and edited in the side panel:
    text, font (PT Sans, PT Serif, Montserrat, each also bold — the fonts the PDF embeds, so screen and PDF match), size in
    points, colour, halo (colour and width in mm), rotation; drag with the mouse or move with the arrows (0,5 mm, Shift 5 mm);
    Delete hides it; «Сбросить правку» restores it; «Скрытые» brings hidden texts back; «Текст» adds an own text by a click.
    Zoom: buttons and Ctrl + wheel. «PDF листа» saves this sheet with the edits. While the editor is open its keys are taken
    first (app.js, `LAYKEYS`), so Delete or letters never reach the map commands underneath.
  - Edits are stored in the sheet (`edits` by key «text#n» — the n-th text with that wording on the page; `items` — own
    texts) and applied by the print renderer to every output — preview, PDF and PPTX (`print_io.apply_edits`). Keys carry
    no coordinates: an edit survives rebuilding the sheet while the text stays the same; rebuilt sections and albums keep
    the edits of their sheets. The automatic label rules are unchanged — an edit is a manual correction on one sheet.
  - Core SVG renderer: `data-key` on texts. Checked on the situational plan: label moved, enlarged, rotated, recoloured,
    bold Montserrat with a white halo; own text added; a label hidden with Delete; PDF and PPTX built with the edits.
    Tests: print (edits by key, own text, SVG, PDF, PPTX), e2e (edit reaches the redrawn sheet, Delete, Esc).
- **2026-10-02, ГРАДО 2 v0.90.0: situational plan A4.** Second feature of the unmerged branch of 25.09 (v0.54.0–0.54.1),
  redone on the current program. «Листы» → «Ситуационный план А4»: a picture on the whole A4 sheet without stamp (format «А4
  без штампа»), with only a thin frame — no title, legend, north arrow, scale bar or corner caption. Content: Yandex green,
  water, buildings and road surface (+ driveways from axes, «Ситплан: УДС»), main railway tracks (black line with white
  dashes, sidings dropped), district boundaries (purple dash-dot) and district names on the part of each district inside the
  sheet, street names (OSM, names only), the boundary. Scale is auto (territory + 900 m), changeable in the sheet row; the
  frame can be dragged; a row button saves this sheet alone as PDF. Without a boundary the button first asks for its file.
  - Data: new sources `sit.*` (kind `yandex_sit`) — Yandex tiles at z16 (16 times fewer tiles than z18, steps ~1,3 m =
    0,1 mm at 1:10 000), one download thread, own keys so the detailed canvas layers are not replaced. Administrative
    division is taken for all Moscow as for section 1 (`ensureAdmin`, shared).
  - Canvas: the coarse `sit.*` layers are overview layers — new style key `minDen`, visible only at 1:7 500 and smaller (the
    reverse of «Виден крупнее»; tree tooltip «Обзорный: виден мельче…», name greyed out of scale). Around the territory
    (boundary + 300 m) detailed Yandex z18 layers are loaded and limited to 1:7 500 and larger, so zooming in swaps the
    coarse picture for the exact one. Yandex buildings stay off where ЕГКО or ЕГРН buildings cover the territory. Street
    names, OSM axes and districts loaded for the sheet stay off on the canvas.
  - Checked on the example territory: 1:15 000, Хорошёвский district with its neighbours, railway, street names — on
    screen as intended; one-sheet PDF saved. Tests: server (z16, one thread, main tracks only), print (bare full-page
    sheet), e2e (sheet content, overview visibility, button).
- **2026-10-02, ГРАДО 2 v0.89.0: boundary from a file.** Owner: bring back the three features of the unmerged branch
  `claude/stoic-mirzakhani-92ecaa` (v0.54.0–0.54.2 of 25.09, never merged; redone on the current program, not merged).
  First of them: «Данные» → «Из файла» next to «Нарисовать границу» takes the largest closed contour of a DXF, DWG,
  GeoJSON, KML/KMZ or Shapefile as the territory boundary — polygons, multipolygon parts and lines whose ends meet within
  0,5 m; local metres are read in the system chosen in «Файлы в метрах» (МСК by default), as on import. The hint names the
  file, the area and how many contours there were. Checked: a DXF in МСК with two closed polylines and a line gave the
  larger one, 6,06 га as computed from its vertices; e2e step with a GeoJSON through the real import.
- **2026-10-01, ГРАДО 2 v0.88.3: leftover edits of earlier sessions committed.** `tests/test_server.py`
  (`HttpHardening`): the server under test gets a temporary projects folder, so the POST /api/project test no longer
  writes into the real one. `print_io.py`: the street-label comment now matches the code — a required street with no
  clean place gets no label; there is no last pass without the boundary check (rule 1). `CLAUDE.md`: the test command
  uses `~/.grado2/venv/bin/python`. Program behaviour unchanged.
- **2026-10-01, ГРАДО 2 v0.88.2: collaboration test — failures now show their cause; no `_uid` divergence found.**
  The e2e collab scenario failed in 2 of 4 full runs on 01.10 and the check «наборы постоянных номеров у A и B
  совпадают» (collab_scenarios.mjs:154) was blamed, but that was never shown: one failed run kept no output, the other
  only `AssertionError: 1 != 0 : нет)` — the blind tail `r.stdout[-4000:]` began inside a line ending «(двойников нет)»,
  which is either the passed «ok - …» line (then the cause was ~660 characters further on) or a «STEP FAILED» line
  followed by ~4000 characters of console errors. Which check failed cannot be recovered (the total time, 293 s against
  288 s for a passing run, hints the collab scenario ran to its end, but proves nothing). No divergence in
  `web/collab.js` was found: with temporary logging at every place a `_uid` is given or changed (`ensureUids`,
  `setLayerData`, `syncFromSource`) the numbers were made once per new polygon on the drawing side and never renamed;
  B renamed nothing, `ensureUids` never fired; 56 repeats of the concurrent step (B's delay swept 0–1.5 s; normal CPU,
  slowed 4× and 8×) and 8 full collab runs (6 of them three at a time next to the owner scenarios, one at 6× CPU) all
  gave equal sets. Changes, tests only: `test_e2e.py` reports every line that is not «ok - …» (STEP FAILED, console
  errors) instead of a blind tail; the uid check now waits up to 6 s for both sides to agree (agreement within 6 s, as
  the collaboration contract promises, not at the same instant) and prints both lists if they do not. Found, not fixed,
  harmless today: `mergeFC` numbers a feature without `_uid` with the salt `layer:<key>`, `normSection`/`diffApply` with
  `<key>`; a pushed feature always has a number already (`syncFromSource`), so the two never meet. Program code unchanged.
- **2026-10-01, ГРАДО 2 v0.88.1: «потолок» → «предельная высота» in data and the calculation scheme, old projects
  converted.** Owner: rename the remaining «Потолок, м», «Потолок, эт.» fields and the «потолок» sockets, with migration
  of saved projects. The ceiling layer now writes «Предельная высота, м» / «Предельная высота, эт.» (the default
  graduated style uses the new field); the «Ограничения» block output and the «Посадка застройки» input are named
  «предельная высота». `web/migrate.js` (`renameCeiling`) runs at the end of `migrate()` on every load, hub projects
  included (join → applyProject): it renames the fields in the `cons:ceiling` data (fc and a separate original, field
  order kept), in that layer's style (label, category, graduated and rule fields) and the socket names of those two
  program blocks only; user layers with a «Потолок» field stay untouched; idempotent, project format stays 2. The
  building cap still reads «Потолок, м» as a fallback, for a collaborator whose tab runs the old version. Tests:
  `tests/migrate_test.js` via `test_migrate_js.py`. Real project copy: the «Посадка застройки» input became
  «предельная высота» after loading.
- **2026-10-01, ГРАДО 2 v0.88.0: first-run audit — search on the map, boundary by cadastral numbers, AutoCAD
  coordinates, clearer words.** Owner: full UX audit through the eyes of a first-time user (a planner colleague who knows
  QGIS and AutoCAD); report and fix the obvious at once, texts and first steps by the owner. Three novice agents that may
  not read code or docs walked real goals on an empty install — `docs/ux/first-run-audit-2026-10-01.md`. Where they gave
  up: no way to get a boundary by cadastral numbers (dead end «По участкам»), no place search, «0,0» rejected, drawings
  out of view, no visible file after export. Fixed: search field over the map «Адрес или кадастровый номер» (Ctrl+F;
  НСПД search by number `/api/search/cadastral`, OpenStreetMap Nominatim for addresses with its rules — 1 request a
  second, only on Enter, cache, Moscow first, then the region; `/api/search` dispatcher); found parcels can be shown or
  turned into the territory boundary; «По участкам» works without loaded parcels (live: 50:27:0000000:126 +
  77:22:0030223:315 = 48,52 га). Coordinates «0,0», «@120,0» and «12345.6,6789.1» accepted besides «X;Y» (after the
  first point «25,5» stays a length). ZE / Z / ZOOM — show all. Esc closes windows, docked ones too. The command input
  selects the text after an error. Focus returns to the map after a new layer. «Проекты» lists saved files after a
  reload. «Листы» buttons wrap. «Пример» asks before replacing a boundary. Disabled «Выбрать и загрузить…» says why.
  Download toasts say the file went to the browser's downloads. Empty states for «Показатели» and «Сравнение».
  «Слои по листам» without sheets explains itself. Words (owner's choice): «Граф» → «Схема расчёта», «Принять в проект»
  → «Сохранить слоем», «потолок» → «предельная высота», «конточка» → «конечная точка»; the first screen stays as it is.
- **2026-10-01, ГРАДО 2 v0.87.0: interface audit — layer tree, ribbon, windows, feedback, one visual system, light
  motion.** Owner: full UI audit, better interaction, «наведи красоту»; start with the ribbon, layers and properties,
  work windows; choose taste from interface catalogues (Mobbin MCP found, paid, not connected; references gathered from
  Figma UI3, QGIS, AutoCAD, Felt, ArcGIS Pro, Rhino 8, Carbon, Atlassian, Fluent 2, Linear), «слегка анимирован».
  Audit by four independent passes (references, 136 screenshots at 1280/840 px in both themes, code, scenarios walked as a
  planner) — `docs/ux/audit-2026-10-01.md`. Fixed: layer tree — right click opens the row menu, rename by double click
  and F2, keyboard (arrows, Space, Delete, Shift+F10), arrows no longer move objects while the tree has focus, delete
  layer with an in-menu confirm and Ctrl+Z restore (data, style, place, group), drawing into a hidden current layer
  shows it, full names in tooltips, «Реестр зданий» only on building layers, Russian plurals; the tree waits for an
  open rename before re-rendering. Visual system — tokens for heights 20/24/28/32, radii 3/6, fonts 11/12/13, three
  shadows, z-index scale; contrast of secondary text ≥ 4,5:1 in both themes; complete hover/press/focus/disabled states
  (primary buttons had no hover); one 28 px ribbon that fits one row at 1280; menus highlight with the selection colour,
  destructive items red; aligned symbols in the tree. Motion (Carbon «productive»): windows fade/scale in 150 ms when
  opened (not on restore), menus 90 ms, toasts, button press scale .97; nothing on tools, keys, map or tree; reduced
  motion respected. Windows: «Данные» buttons no longer cut, «Листы» table scrolls, form grids in «Ограничения» and
  «Показатели», «Проекты» wording, «Справка» fits, titles start with the button word, tooltips on fields (no invented
  norms). Feedback: one result line after drawing and edits («Создан полигон в слое …, 4 вершины, … м². Ctrl+Z —
  отменить.»), a note when drawing into a portal download, short status in command mode and at 840 px (full text in
  the tooltip), Russian scale line, toast above the command line.
- **2026-10-01, ГРАДО 2 v0.86.0: search, favourites, copy and link access in hub mode.** Owner's choices: search and
  order, «Сделать копию», favourites and link access «для своих» now; adding to a team stays immediate. Contract first
  (`docs/grado2-collab-spec.md`, «Projects window and link access»), checked with the advisor: the link token lives in
  the URL fragment (`/#join=…`), so it never reaches the server log or a Referer; bad links have their own throttle keys
  and never lock the password login; favourites live in `stars.json`, not in `users.json` rewritten by the CLI.
  `hub.py`: `stars.json`, `copy_project` (shared `_make_project` with creation), `link`/`link_users` in meta as the third
  source of the role in `_role` (strongest wins), `set_link`/`get_link`/`join`; turning the link off, rotating or
  lowering it goes through `_access_changed`. Review debts of v0.85.0: team and meta writes are copy-then-assign, disabled
  people do not count as owners, `list_teams` keeps a pid → team map instead of re-reading every project file. Routes
  `…/star`, `…/copy`, `…/link` (GET/POST), `/api/hub/join`. Client: search field and order (remembered per browser),
  star and group «Избранное», «Сделать копию» row form, block «Доступ по ссылке» with copy/rotate and «Вошли по ссылке»,
  opening `/#join=…` through the login screen. `test_server.py` now points `PROJECTS` at a temp folder when
  `GRADO2_PROJECTS` is unset (a run without it had written `zzz.grado2` into the owner's folder). Tests: `Stage2` in
  `test_hub.py`, new `HubHttp` cases including «token never in the log», 19 new checks in the two-browser scenario.
  After the review: a person whose role is already as strong as the link is not recorded as a link user (otherwise,
  removed from members, they would keep access unseen by the owner); a star can be removed without access; the page
  keeps the link token on network errors and «повторите позже», and drops it only on a final answer.
- **2026-10-01, ГРАДО 2 v0.85.0: teams (workspaces) in hub mode.** Owner: «разные команды пользователей с доступами
  к разным проектам, как в Miro, Google Документах, Canva». Owner's decisions: new accounts still only by an admin
  invite, a new team project is edited by the whole team by default, link sharing later. Contract first
  (`docs/grado2-collab-spec.md`, «Teams»). `hub.py`: `teams.json` (re-read like `users.json`), team roles owner/member,
  projects carry `team` and `team_access` (edit/view/none; old projects are personal, no migration); the single access
  point `_role` takes the strongest of the personal share and the team role (team owner = project owner); last-owner
  rule counts team owners; `set_project_team` moves a project between spaces; any change of team membership, team
  role, team access or space closes the event streams of people who lost access on every affected project
  (`_access_changed`). Routes `/api/hub/teams`, `/api/hub/team/<tid>[/members|/delete]`,
  `/api/hub/project/<pid>/team`, `team` in project creation. Client: «Совместные проекты» grouped into «Личные», one
  group per team and «Доступные мне», «Где создать»; window «Команды»; «Доступ» gains «Где лежит проект» and «Вся
  команда …». Tests: `Teams` in `test_hub.py`, new `HubHttp` cases, 8 team steps in the two-browser scenario. Work
  split between worker agents (hub, routes, UI, scenario) with an independent review and a verifier run.
- **2026-10-01, ГРАДО 2 v0.84.9: owner's decisions on the album rule register (8.50–8.66) and fixes found by the
  reviewers.** Rules first: label-rules.md rule 13, slide-layout-rules.md items 1.20, 1.27–1.29, 1.43, 2.17, 2.22, 2.35,
  3.13, 3.14, 3.24, 3.28, 3.47–3.49, 6.11, 6.12, 7.10, 7.11, register items closed. Sheet title is always 18 pt: a
  long one (sheet 5) goes into two lines of about equal width centred on the template arrow (`_title_lines`), never
  smaller; more than two lines marks the sheet «не готов». Genplan zones (sheet 6) take all colours from the owner's
  MapInfo table of ТиНАО functional zones (`ФункциональныеЗоны_ПрисоединенныеТер.TAB`, read with the ogrinfo that ships
  with QGIS, no new dependency), keyed by the zone type index `fz_type`; the six «Хатминки» colours are dropped.
  Roadway on sheets 5–8 is one solid grey #B4B4B4 (owner picked it from three variants). Planning documents (ППТ, ПМТ,
  ГПЗУ, АГР) are drawn above roads and buildings, under the territory boundary. Buildings on sheets 4–8 are filled
  white. Line widths are exact: parcel boundaries on sheet 5 0.20 mm, Genplan zone boundaries 0.35 mm (`MM()`). Legend,
  table, lists and cards no longer stop silently: the sheet gets a grey 9 pt «Лист не готов: …» note under the map, the
  server returns `X-Grado-Not-Ready` and the export message names those sheets. «№» is followed by a non-breaking
  space in document lists; the last line of a legend label, list box or block heading is never a lone word shorter
  than 8 characters (`_wrap_mm`, rule 2.22). Table columns are never narrower than their longest unbreakable word +
  2 mm (`_col_widths`); in table cells a compound word wider than its column breaks after its own hyphen
  («природно-/жилая зона», owner's choice when the sheet 6 table needed 122 mm of 120); «функц. зоны» never splits.
  Посёлок in area names is «пос.». Existing projects get the new look after the album is rebuilt («План реализации ППТ
  КРТ» again): sheets keep the styles they were built with.
- **2026-09-30, ГРАДО 2 v0.84.8: street labels on the road axis, never across the boundary.** Owner, again: «ул.
  Придорожная криво и залезает на границу». Causes: the street had no straight run between junctions long enough, so
  the label fell back to a spot beside the road (over the houses) and, for an obligatory street, to a last pass
  without the boundary check. Now: street lines are merged into chains (`_chains`) and searched for near-straight
  windows as long as the label (`_axis_windows`, deviation ≤ ¼ of the text size, ½ for obligatory streets); an
  obligatory street prefers windows nearest the territory, tries on-road spots at 1, 0.9 and 0.8 size before any
  spot beside the road, and when the street is shorter than the label in the frame continues along the adjoining
  road; the boundary-free pass is gone. Side streets that only join the street no longer block it. Rules first.
- **2026-09-30, ГРАДО 2 v0.84.7: one outline for outline-only roads; photo numbers tight in the corner.** Owner: roads
  drawn as outlines looked like many small pieces (the source polygons are cut), make the outline common, graphically
  is fine; the number plate on the photos left a thin strip of the photo at the top and left. Print: layers listed in
  `sheet.casing` (sheet 4: `calc.uds_ya`, `egko.roads`) are drawn in two passes — all outlines at double width, then
  all fills in the background colour — so inner seams disappear. The photo number plate extends 0.4 mm past the
  photo corner. Rules first.
- **2026-09-30, ГРАДО 2 v0.84.6: photo points on sheet 4 always numbered and on top.** The owner sent 8 Yandex panorama
  links for sheet 4. Frames were cut from the panoramas (point and direction from each link, tiles one by one with a
  pause, perspective view 85°, GPS and direction written to EXIF) and added through the ordinary photo button path —
  the program read coordinates and directions itself. On the map the view arrows sat under the 55 % mask and the
  territory dashes, and the numbers next to them were dropped near the boundary: arrows are now drawn after the mask
  and boundary, numbers try positions up to 8.5 mm around the arrow and are always shown (as in «ГК Царицыно»).
- **2026-09-30, ГРАДО 2 v0.84.5: sheet 7 title by content.** The same rule as for АГР on sheet 8: «…документацией ППТ и
  ПМТ» loses «и ПМТ» when no ПМТ is in the frame (and «ППТ и» when no ППТ). Full album built on the test copy: PDF and
  PPTX, 9 sheets each. Rules first.
- **2026-09-30, ГРАДО 2 v0.84.4: titles by content, index in the zone swatch, uniform swatches, typography.** Owner:
  sheet 8 has only ГПЗУ — drop АГР from the names; sheet 6 — write the type index into the zone swatch instead of a
  separate list; legend swatches must be the same size on all sheets (sheets 5/6 differed, the boundary sample length
  jumped); no hanging prepositions or orphaned abbreviations anywhere («г.» alone on a line on sheet 7); sheet 9 sign
  «порядковый номер земельного участка в таблице». Rules first (rule 12). Sheet title and list title lose «и АГР» when
  no АГР is in the frame. Zone swatches carry the index (`num`), the index list is gone. All legend swatches 13 × 3 mm
  (`SW_W`) in the column and on the satellite plate; dashed samples are fitted to whole dashes. `_glue()` puts
  non-breaking spaces after prepositions, conjunctions and short words, around «№», «г.», «га», «тыс. кв. м», «ул.»,
  «р.», «д.» and before dashes; `_wrap` and `_wrap_mm` wrap only at ordinary spaces.
- **2026-09-30, ГРАДО 2 v0.84.3: fixes after the multi-agent album review.** 10 Sonnet agents reviewed sheets 1–9
  (8 lenses, 2 verifiers): 134 findings, 58 confirmed. Owner: keep the header image, sheet 6 and sheet 5 proposals
  approved. Rules first (rule 11). Print: labels keep 2.5 mm from the map edge; obligatory moved labels search up to
  25 mm (sheet 4 lost «д. Безобразово»); street labels do not cross other named OSM streets; territory names prefer
  spots without driveways under the text; numbered-circle anchors keep off the territory boundary, never share a point
  (sheet 8: 9/8/10 met in one dot), circles keep 1 mm from other labels; multi-line labels take per-line sizes
  (`lss`); Genplan zone numbers sit at the deepest point of the visible zone away from the frame edge and water,
  tiny pieces get no number. Albums: lakes (and wide river water) labelled along the axis of the water area, not of
  its vertices, and never leaning past vertical; river labels from project data; legends only for what is in the
  frame (ПМТ, АГР, Genplan zones in the sample order), index block «Индекс типа функционального назначения территории»
  from the zones' own data, Genplan labels a third smaller with the index 15 % larger, zone edges not drawn along the
  territory boundary, table widths; ZOUIT outlines smoothed (closing/opening 1.5 m, simplify 1.5 m); «минимальных»
  spelled out; one wording «территории автодорог, улиц, местных проездов»; document titles cut at 128 chars by ГИС
  ОГД get «…» and « — »; document layers under roads and buildings; sheet 9 legend has the numbered-circle sign and
  «с/по» dates do not break. Legend: line-type swatches 13 mm when the sheet has ЗОУИТ lines. Column: text centred in
  list boxes, equal corner-inscription spacing, callout box on sheet 2 as wide as its text, title date aligned,
  short words do not hang at line ends.
- **2026-09-30, ГРАДО 2 v0.84.2: labels stay in place across sheets of the same frame.** Owner: on sheets with the
  same frame and scale labels must be in exactly the same places so they do not jump when paging; «р. Моча» moved
  and vanished between sheets; «Калужское ш.» sat low; leader 12 on sheet 8 was illogically far. Print keeps a label
  memory per document, keyed by map rect, centre and scale (`SketchMapFrame.memo`): placed names, street labels and
  area labels first try the place they got on an earlier sheet of the group; a sheet-specific leader or number can
  still push one aside. River labels are computed from project data (not the sheet's layer set) and cached per frame
  (`WL_MEMO`), so sheets 5–9 get identical river labels. Non-obligatory streets prefer the straight run nearest the
  frame centre. Street label angle is normalised to ±90° (a remembered angle was flipped upside down). Numbered
  circles: 11 radii from 7 mm, 24 directions, and on every radius strict and relaxed checks before farther radii.
  Known limit: the on-screen preview of a single sheet has no earlier sheets and may place names differently from the
  PDF/PPTX. Rules first.
- **2026-09-30, ГРАДО 2 v0.84.1: river labels lie on the channel along their whole length.** Owner: «р. Вороновка
  подписана криво». The label centre was mid-channel, but the direction was the average of the river within 200 m, so
  on a meandering river the straight label left the water. Now each candidate spot is tried with the direction turned
  by up to ±24°, and the spot is scored by road/boundary crossings first, then by the share of the label axis on the
  water (11 points; for thin ЕГКО rivers — within half a letter height of the line), then by the turn and the distance
  to the territory. Rules first.
- **2026-09-30, ГРАДО 2 v0.84.0: collaboration (hub mode).** Off by default: the owner's Mac and grado.tailink.tech
  work as before until the server runs with `GRADO2_HUB=1` (or `--hub`). Hub mode: accounts with invite-only
  registration (`apps/grado2/hub.py`, scrypt, sessions, login throttling, admin CLI `hub.py adduser|passwd|invite|list`),
  projects stored on the server with roles owner/editor/viewer, live sync of several people in one project
  (sections `meta` and `layer:<key>`, section revisions, server-sent events, 3-way merge by stable object ids `_uid`
  in `web/collab.js`), presence (avatars, cursors with names, outlines of what others selected, dots on layers),
  comments pinned to the map or an object with replies and «решено», version history with restore, activity feed,
  admin window for users and invites (`web/hub.js`, `hub.css`). Security review of the new backend: throttling
  race, CLI vs server file sync, password change drops other sessions, storage quotas, SSE caps, strict JSON-only
  POST and Sec-Fetch-Site checks in hub mode. Tests: `test_hub.py`, `HubHttp` in `test_server.py`, `collab_test.js`,
  two-browser e2e `tests/e2e/collab_scenarios.mjs`. Contract `docs/grado2-collab-spec.md`, owner guide
  `docs/grado2-collab.md`.
- **2026-09-30, ГРАДО 2 v0.83.7: thin parcel lines inside the territory on sheet 9.** Owner: make the parcel
  boundaries inside the territory as thin as outside. Blue lines now have the same width as the light ones outside
  (1 instead of 2.6), legend sample 0.35 mm. Rules first.
- **2026-09-30, ГРАДО 2 v0.83.6: areas exactly as in AutoCAD and ЕГРН; sheet 9 table as in the customer's sheet.**
  Owner: the area on the drawing and by НСПД must match; count areas the way AutoCAD and КУГИС do. `m2` is now the
  exact polygon area of the vertices converted to МСК (AutoCAD computes a polyline area the same way), remembered per
  geometry (WeakMap); the per-cell correction of v0.83.5 is gone. Album build on the test project: 6.5 s. Sheet 9
  table: area from «Площадь уточнённая, м²» (47,2765 and 1,2415 га, as in the customer's sheet; «Площадь участка» was
  the declared 47,2008), ownership kept as written (no lowercase). The owner's values are entered in the parcel
  properties; a manual edit survives a НСПД reload. Checked against 57 parcels near КРТ 3141: large parcels come out
  0.0013–0.0015 % smaller than their ЕГРН area, a steady scale difference between our МСК and the one НСПД used to
  publish the geometry, not the formula (not calibrated: iron rule 3); small parcels scatter by rounding.
- **2026-09-30, ГРАДО 2 v0.83.5: territory from cadastral numbers; areas in the МСК plane.** Owner sent the customer's
  sheet: the КРТ 3141 territory is parcels 50:27:0000000:126 (47,2765 га) and 77:22:0030223:315 (1,2415 га), 48,5180 га.
  New button «По участкам» next to «Нарисовать границу»: paste cadastral numbers (any separators), the territory becomes
  the union of those НСПД parcels; missing numbers are named and nothing changes. Found on the way: every area was
  `turf.area` on a sphere, 0.46 % low near Moscow (48,29 instead of 48,52 га). `m2` now multiplies it by a cached
  correction per 0.01° cell (ratio of МСК plane area to sphere area for a small square): 48,5174 га, the same as an
  exact МСК computation to 1e-6; the territory area uses `m2` too.
- **2026-09-30, ГРАДО 2 v0.83.4: leader point of a parcel that only touches the territory.** Parcel 2 on sheet 9 lies
  mostly outside the territory; inside it is a sliver along the boundary, so its dot sat on the boundary line. The
  albums also pass the whole parcel (`zone2`); when the part in the territory is shallower than 0.6 mm, print anchors
  the number in the deepest point of the whole parcel. The deepest-point search retries on a 4× finer grid for thin
  strips.
- **2026-09-30, ГРАДО 2 v0.83.3: Минцифры root certificates in the repo.** `russian_trusted_root_ca_pem.crt` and
  `russian_trusted_sub_ca_pem.crt` from gu-st.ru in `core/connectors/grado_connectors/certs/`. SHA-256 936a43fe…6504 and
  f0ae589f…4ea6, the same when downloaded from the Mac and from a host in Russia; the sub CA verifies against the root;
  nspd.gov.ru passes full verification with them and fails without. NSPD downloads work again with TLS checked.
- **2026-09-30, ГРАДО 2 v0.83.2: security hardening after the audit.** No visible change in the UI. NSPD: the silent
  fallback to an unverified TLS connection is gone; the Минцифры root certificates are read from `GRADO_NSPD_CA`,
  `~/.grado2/ca/` or `core/connectors/grado_connectors/certs/` (see its README.txt), no certificate gives a clear error,
  `GRADO_NSPD_INSECURE=1` is the explicit old behaviour. Web: every value from a project file that goes into HTML is
  escaped or coerced to a number (`fetched_at`, view ids, scale, style numbers), project load sanitises ids and skips
  `__proto__`. Server: CSP (`script-src 'self'`), X-Frame-Options, nosniff, per-path body limits (32 / 250 / 400 MB),
  socket timeout, generic text for unexpected errors (details to the log), `saved` returns only the project name,
  pid check before replacing an old server, projects folder quota 20 GB, optional access token `GRADO2_TOKEN`
  (login page `/login.html`, off when the variable is empty). Import and connectors: size ceilings for files, tiles,
  photos and downloads, zip and SHP bounds checks (`read_shp` could loop forever), https-only redirects
  (`netutil.py`), layer code and snapshot id validated. Core: SQL identifiers quoted, `.grado` opened with
  `trusted_schema=OFF`, expression length/depth/exponent limits, finite coordinates, SVG/PPTX attribute escaping.
  Repo: `.env`/keys in `.gitignore`, `pillow>=11.3`, release workflow permissions, `.claude/launch.json` untracked.
  litegraph.min.js is patched locally (demo nodes via `new Function` off) so the CSP needs no `unsafe-eval`.
- **2026-09-30, ГРАДО 2 v0.83.1: street labels off the territory boundary, readable number leaders.** Owner: street
  names still sit on the boundary; leaders unreadable, unclear which number belongs to which parcel, circles and
  leaders cross. Street labels: the boundary is checked against the rotated label box (`_obox_hit`), candidates are
  every straight run of the street with shifts along it, then beside the road on both sides; a non-obligatory street
  without a clean spot is not labelled. Numbers: the albums pass the largest part of each document/parcel (`zone`);
  print finds its deepest point (`_pole`), skips points already covered by labels, and other labels may not cover
  these points; the circle goes inside only if it fits, else on a leader 0.5 mm with a white halo and a 1 mm dot;
  circles stay off other parcels and other dots, leaders do not cross each other, other circles or labels
  (`_seg_cross`); graded fallbacks keep every number visible. Rules first.
- **2026-09-30, ГРАДО 2 v0.83.0: sheet 6 like «Хатминки», circled numbers on sheets 7–9.** Owner: callouts unreadable,
  text competes; the Генплан sheet is wrong — zone boundaries must be on top, colours wrong. Analysed the owner's
  «Хатминки» Генплан sheet (same Новая Москва zones): zone colours sampled from its map (общественно-жилая #ff9062,
  жилая #fed44c, природно-жилая #c8c64f, природная #2ad092, общественно-производственно-жилая #d67c7c,
  общественно-производственная #bb84b0), black zone boundaries drawn above roads and buildings (separate layer),
  black bold labels with the number underlined (`ul0`), water #00689d. Owner chose «Хатминки» numbering for sheets 7–9:
  a short number in a white circle with an outline (`circle` in print), inside the object or on a leader; the cadastral
  plates on sheet 9 are gone; parcel numbers blue #1f3fbf at the centre of mass of the largest part. Rules first.
- **2026-09-30, ГРАДО 2 v0.82.0: sheets 6–9 after the owner's review.** Sheet 6: colours were the Новая Москва pastel at 80 %;
  now the base (saturated) Эталон Генплана palette at 100 %, map and legend (`GPZ` by zone name). Sheets 7–8: document numbers
  5 mm (were 10) with leader callouts — inside the document when it fits, otherwise placed around it (radii 9–32 mm, 16
  directions) with a thin line and a dot on the document (new `leader`/`inside` in the label loop of print). Sheet 9: every
  parcel of the territory has its cadastral plate with a leader; all parcels in one table (№, cadastral number, area, ВРИ,
  ownership; `gpTable` gets `fs`, wrapped title) instead of cards; a 35 % white veil over the satellite (`veil`). Rules first.
- **2026-09-30, ГРАДО 2 v0.81.2: no mask on the documentation sheets.** Comparing sheets 6–9 with «ГК Царицыно»: documents
  on sheets 7–8 lie almost all outside the territory and faded under the mask; neither sample masks these sheets. Owner
  chose: mask only on sheets 4 and 5.
- **2026-09-30, ГРАДО 2 v0.81.1: parcels numbered in the cards; design rules summarised.** Owner: «пронумеруй, но не
  отображай; запомни и сформулируй основные правила оформления». Sheet 9 cards start with «Участок №N» (largest first,
  like «Хатминки»); numbers are not drawn on the map. `label-rules.md` opens with a summary «Основные правила оформления»:
  working order (analyse the owner's samples first, ask when unclear, invent nothing), list of samples, seven main rules.
- **2026-09-30, ГРАДО 2 v0.81.0: flooding signs from «Хатминки», pipeline zones, airfield note; layers audit.** Owner:
  copy the flooding legend from «Хатминки», check which layers are missing, check sanitary protection zones in the frame.
  Flooding (codes 64/65/66) is drawn with the example's signs (green #038240, 0.35 mm; strong — solid with dense ticks,
  moderate — 3/1 mm dashes with two ticks, weak — 2/1.2 mm dashes; ticks inside the zone) by `flood_ops` in print and in
  the legend, in its own legend group with the example's labels. `gisogd.zouit` adds pipeline protection zones
  (`virtual521`) and minimum-distance zones (`virtual`), Эталон signs 35/39 (Сводный план layers 2.16/2.19 answer HTTP
  500). New `gisogd.airfield` (Внуково, Шереметьево, Остафьево subzones): a note under the legend, like the example,
  only for subzones that cross the territory; legend items of kind `note` have no sample. Audit of КРТ 3141 frame: no
  СЗЗ in ГИС ОГД (Генплан, Сводный план) nor ЕГРН (nearest of 9 СЗЗ is 2.1 km away); ЕГРН has Внуково airfield
  territory and subzones 3 and 5 (the territory itself is outside), two gas main minimum-distance zones, a power line
  zone. Rules first.
- **2026-09-30, ГРАДО 2 v0.80.0: gaps continue the nearest zones; light-grey carriageway.** After analysing the examples
  (IRGA «Хатминки» sheet 5 and MapInfo «ЗУ_ФЗ» leave land without parcels and streets unfilled; only parcels are coloured,
  no outlines on fills) the owner decided: land without parcels — by OSM where it knows, elsewhere extrapolate the
  nearest zones; carriageway without a parcel — light grey like the base; parcels outside the territory stay coloured
  under the mask. Sheet 5: points every ≥8 m (≤6000 per sheet, deduplicated to ~1 m) along the boundaries of coloured
  parcels and OSM areas → Voronoi cells (turf) in the colour of their outline, drawn under all fills, so only gaps show
  them; bbox padded 2 % (points on the edge or coincident points break turf.voronoi). Carriageway #e3e3e3 (the owner's
  «внутриквартальные проезды» colour). Rules first.
- **2026-09-30, ГРАДО 2 v0.79.1: no white band around roads.** Owner: «убери обводку у всех дорог, белым должны быть только
  зоны, если для дороги сформирован земельный участок». The 6 m white buffer around the carriageway (v0.79.0) is removed;
  only parcels formed for roads are white, above other fills.
- **2026-09-30, ГРАДО 2 v0.79.0: no «no activity» fill, road corridor on top, white mask outside the territory.** Owner
  (with example «Хатминки», IRGA): no class 24 and no white spots, green zones still covered white road land, add an
  automatic semi-transparent white mask outside the territory. Default land without parcels/OSM is now class 18
  (natural-recreational); class 24 only for parcels with code 12.3. Road land is on top: white road parcels plus a white
  6 m buffer around the carriageway (bridge over the river at Калужское шоссе had no parcel). New `terrMask` (0.55): frame
  minus territory, white with alpha, even-odd, drawn under the territory boundary and labels — on white-base sheets
  4–8 except the Генплан fragment and satellite sheets (the example masks the same sheets). Key is `terrMask`, not
  `mask` (taken by the ЕГКО base mask of the okrug scheme). Checked in PDF and PPTX. Rules first.
- **2026-09-30, ГРАДО 2 v0.78.0: sheet 5 coloured by the owner's ВРИ template; names off the territory boundary.** Owner:
  «крась по вот этому шаблону и включи его в программу и запомни» (layer «plan_organiz_ex» of «ВРИ земельных
  участков_RGB»), water still wrong, some names lie over the boundary. Both owner DXF templates are stored in
  `docs/standards/albums/`. Land use now uses the template's 28 classes (`VRI_T`: colour, ВРИ codes) — a parcel's class
  comes from the ВРИ code in its text (4.9.1.1 → 4.9.1 → 4.9), else from ordered words (`VRI_WORDS`; fixed traps:
  «физкультурно» is sport not culture, «транспортировки» is not sport, Latin «C» in «Cадоводство», АЗС, gas). Water
  is class 22 #336699; land without parcels: OSM forest/meadow → 18, fields → 25, the rest → 24 «отсутствие
  хозяйственной деятельности». Legend «Виды разрешённого использования земельных участков, территорий» in template
  order. Print: names of territories and villages avoid the territory boundary (`take(..., avoid)` with Liang–Barsky
  segment test, padding by boundary width), nudged labels have a last try without it. Memory note written.
- **2026-09-30, ГРАДО 2 v0.77.1: palette from «ВРИ земельных участков_RGB» first.** Owner sent the second DXF and said
  «ВРИ РГБ приоритет»; ИЖС and gardening are there. The file has coded functional zones (1001…7000) and a «ВРИ_NN» colouring;
  order of sources now: its coded zones, then its ВРИ_NN, then the «ЗИО сущ» legend. Changes: ИЖС #e5e57f (2001), gardening
  #e5e57f (ВРИ_13, same as ИЖС), agriculture #d2e19f (ВРИ_32), natural #c0e3b5 (4001), sport #b9e592 (ВРИ_9), health
  #b0d9d5 (ВРИ_4), external transport #ada4a0 (ВРИ_19); new class «специального назначения» #c7d1c7 (3003; cemeteries,
  communications, defence). Buildings stay white with grey outline (owner). Rules first.
- **2026-09-30, ГРАДО 2 v0.77.0: land-use palette from the owner's legend; no thin rivers on the ortho sheet.** Owner sent
  «УСЛОВКИ от Генплана.dxf» (ten legend columns; «Схема ЗИО» and «ЗИО сущ» match sheet 5) and MapInfo examples
  «Функц_зонир_Хатминки» (Генплан-type zones by FZtip) and «ЗУ_ФЗ» (parcels coloured by actual functional use, not by
  the ВРИ text). The legend and «ЗУ_ФЗ» agree; sheet 5 now uses their colours: многоквартирные #f9e79f, учебно-
  воспитательного #cde1b7, культурно-просветительского #f99f9f, торгово-бытового #f4b598, административно-делового
  #cbb2cc, производственного #cfd1eb, коммунально-складского #dcd5b6, жилищно-коммунального #d7c6c1 (garages, fuel
  stations), лечебно-оздоровительного #a5e5df, внешнего транспорта #999999, природных #9ab970; new classes смешанного
  общественно-производственного #ad84ae and смешанно-производственного #b1b5e1. Classes absent from the legend (ИЖС,
  gardening, agriculture, sport) keep their colours. Owner: blue lines appeared on sheet 3 — ЕГКО thin-river lines
  (v0.70.0) are no longer drawn on satellite sheets, only used to place stream names. Rules first.
- **2026-09-30, ГРАДО 2 v0.76.0: obligatory street names straight on their road.** Owner: street names must lie wholly on
  straight road parts or deviate minimally; «ул. Придорожная» was crooked. Streets missing in OSM are no longer placed as a
  point with the angle of a point cloud: every ЕГКО address votes for its nearest OSM road (up to 60 m), the winning roads
  get the name (in Безобразово the village part of OSM «Сипягинское шоссе» is Придорожная by the addresses) and the usual
  street rule places the label — straight run without junctions, along it. Obligatory streets (`must`) are never dropped:
  runs where the whole label fits come first, nearest to the street's houses (`mustAt`), and the label slides along the run
  towards the houses and into the frame; runs near the frame edge count too.
- **2026-09-30, ГРАДО 2 v0.75.1: shore strip is natural territory.** Owner: «внутри береговой все природные и озеленённые
  территории». On sheet 5 the shore-strip polygons of ГИС ОГД («Береговая полоса») are filled as natural and green
  territory over parcels and OSM land use; water and carriageway stay on top. Rule first.
- **2026-09-30, ГРАДО 2 v0.75.0: obligatory village and street names, smaller names, thinner parcels.** Owner: «д.
  Безобразово и ул. Придорожная обязательно на всех листах», «топонимы и гидронимы кегль чуть меньше», «границы ЗУ чуть
  тоньше». OSM has only a hamlet point and no Придорожная street at all (checked). New source `egko.place_labels`
  (ЕГКО «Пояснительные подписи»: «Д. БЕЗОБРАЗОВО»): villages are labelled «д. Безобразово», bold 4.6 mm, first on every
  concept sheet. Streets that OSM lacks are taken from ЕГКО building addresses («Придорожная улица 7 соор.1») and
  labelled along the nearest OSM road within 60 m of those buildings (else along the row of buildings) — «ул.
  Придорожная», «ул. Центральная». Names of territories, streets and rivers 3.8 mm (was 4.3). Parcel boundaries on sheet
  5 width 0.7 px. Rules first.
- **2026-09-30, ГРАДО 2 v0.74.1: flooding ticks on one side, more road parcels white.** Owner: weak flooding had ticks on
  both sides, some parcels under roads were still not white. Zones of one kind are merged within the frame before their
  boundary is drawn; flooding zones are nested (weak ⊇ moderate ⊇ strong), and because ГИС ОГД outlines do not match
  exactly, boundary pieces of a weaker zone closer than 3 m to a stronger zone's boundary are dropped. Parcels more than
  half under the carriageway are road territory at any ВРИ (SNT internal driveways are registered «для ведения
  садоводства»); without ВРИ from a tenth (narrow strips along the highway). Legend keeps the Эталон line text only when
  it fits the 8 mm sign. ГИС ОГД has no УДС red lines inside the sheet 5 frame (checked, see v0.74.0).
- **2026-09-30, ГРАДО 2 v0.74.0: sheet 5 roads and all Сводный план lines.** Owner: roads were grey outlines without fill,
  parcels under roads were not white, УДС red lines, техзоны and others missing. Now: carriageway filled grey (#b4b4b4, no
  outline) as in «ГК Царицыно»; a parcel without ВРИ (NSPD «обособленный участок» of a single land use — the ВРИ is on
  the parent card, checked on 50:27:0030236:16) lying more than a third under the carriageway is a road territory, white.
  `gisogd.red_lines` now loads all 14 line layers of Сводный план (l1 l2 l3 l4 l25 l16 l17 l7 l57 l8 l41 l18 l21 l29), not
  only l1; a zone that has its own Сводный план line is not drawn again by its outline. Codes without a REDLN97
  linetype (29 техзоны, 41 береговые and others) get the Эталон dash plus the Эталон line text along the line
  («техническая зона», «береговая»; core `line_label_ops`), also in the legend sample, fitted to the sign width.
  Legend label of code 1 as in the sample. Checked on КРТ 3141: inside the sheet 5 frame ГИС ОГД has 28 shore-strip
  lines, but no УДС red lines and no техзоны — the nearest (16 and 8 lines) are 1.5–2 km north and south of the frame.
- **2026-09-30, ГРАДО 2 v0.73.1: flooding zones told apart.** Owner: moderate and weak flooding looked the same. In the
  Эталон ЛГР codes 64/65/66 differ only by hatch colour, and hatches are gone from sheet 5. Now all three use the ticked
  linetype of code 64; strong stays red, moderate is blue #2f7fd8, weak green #2e9e78 (each sign's hatch colour,
  darkened), on the map and in the legend (`ZONE_LINE` in albums.js). Rule written first.
- **2026-09-30, ГРАДО 2 v0.73.0: sheet 5 ЗОУИТ and legend like «ГК Царицыно».** Owner: «условки должны быть как в примере
  по Царицыно, названий штриховок не должно быть». In the sample the zones are boundaries only (red REDLN97 lines with
  ticks) listed under «Линии градостроительного регулирования, действующие» as «граница …». Now: ГИС ОГД zones are
  drawn as their boundaries with the REDLN97 linetype of their Эталон ЛГР code (ring counter-clockwise, ticks inward,
  variant «t»), codes without a linetype — dashed in the sign colour; no hatches, no separate zone group; legend labels
  in the genitive («граница водоохранных зон»). ЛГР linetypes on sheets are now constant on paper (`LT_MM` = 0.25 mm
  per pattern unit, ticks every 5 mm as in the sample); before, the pattern was in ground metres and at 1:10 000 a zone
  boundary merged into a solid line. Legend samples fit two patterns into the 8 mm sign. Rules updated first.
  Yandex satellite tiles for AutoCAD are downloaded one by one again (project rule: no parallel portal requests).
- **2026-09-30, ГРАДО 2 v0.72.0: satellite for AutoCAD in full detail and without extra steps.** Owner: the script worked,
  but «разрешение плохое» and everything must load automatically. Detail: always Yandex z18 (the finest real level
  around Moscow, ~0.34 m; z19 is z18 stretched, checked near Вороново), output 0.3 m per pixel, cut into pieces of at
  most 4096 px, each with its own world file; tiles in three threads with pauses (sheet 3, 4.2 × 2.5 km: 12 pieces,
  40 MB, 2.5 min first time). Automatic: AutoCAD shows a DXF raster on opening only with a full path (relative →
  «Unreferenced» until reload; ezdxf discussion #845), so the DXF links the pieces by full path «downloads folder /
  archive name / file». The app asks the browser downloads folder once (Shift+click changes it), names the archive
  uniquely (`sputnik_<sheet>_<time>`) with one folder inside, so a double click in the downloads folder unpacks it
  exactly where the DXF looks. `$PROJECTNAME` is blank; the `-IMAGE` script stays as a fallback. Confirmed by the owner
  in AutoCAD 2025 (Mac): the image opens at once, in place.
- **2026-09-30, ГРАДО 2 v0.71.1: satellite for AutoCAD placed by a script, not by an IMAGE entity in DXF.** Owner: AutoCAD
  2025 (Mac) opened `sputnik_yandex.dxf` with the image «Unreferenced», Reload did not help — AutoCAD dropped the IMAGE
  entity on load. The archive now has `sputnik_yandex.scr` (`-IMAGE` Attach, insertion point = lower-left frame corner
  in МСК, scale = image width in metres, rotation 0, then ZOOM E); the DXF holds only the red frame of the image. Manual
  IMAGEATTACH values are in README. Not yet confirmed in AutoCAD by the owner.
- **2026-09-30, ГРАДО 2 v0.71.0: Yandex satellite of a sheet frame for AutoCAD in МСК.** Owner: «придумай выгрузку листа
  спутника яндекс в автокад в координатах, как делали из QGIS». New button on every map sheet; `POST /api/export/sat`
  (`sat_io.py`). Yandex tiles are EPSG:3395 and turned against МСК, so the image is rebuilt on the МСК grid block by
  block (corners МСК → WGS84 → 3395 → tile pixels, Pillow MESH, error under a pixel). The zip holds
  `sputnik_yandex.dxf` (IMAGE entity in place), the JPEG, the world file `.jgw` and a README; DWG too if ODA File
  Converter is installed. Pixel 0.5–4 m chosen so the image stays under 25 Mpx; tiles cached for 90 days, downloaded
  one by one with pauses. Checked on sheet 3 of КРТ 3141: Yandex road polygons fall exactly on the roads of the image.
  For working drawings only, like the other Yandex layers. Tests `test_sat.py`.
- **2026-09-30, ГРАДО 2 v0.70.0: owner's remarks on sheets 4–5.** Rules first (`docs/standards/albums/label-rules.md`),
  then code. Place names wrap into two lines of about equal length (never more than two). River names sit on the
  channel itself: the centre is the middle of the channel cross-section (perpendicular to the local direction), the
  label follows the channel; no more sideways offsets. Narrow streams without a water polygon are labelled on the ЕГКО
  thin-river lines (`tonkie_reki`, now part of `egko.water`). Sheet 5 has no white patches: the whole frame is natural
  land, OSM land use goes over it (large first), ЕГРН parcels by ВРИ on top, only roads are white. All ГИС ОГД zones
  (СПРИТ `gisogd.zouit`, `gisogd.szz`, `gisogd.vodookhr`) are drawn with the Эталон ЛГР sign of each kind (stroke colour
  and dash, hatch colour, angle and spacing); the legend lists the kinds visible on the sheet. Test run on КРТ 3141.
- **2026-09-30, ГРАДО 2 v0.69.7: NSPD area limit 250 km².** Owner's decision after a 195 km² sheet failed: NSPD
  takes up to 250 km² (still in 4 km² tiles with pauses, so a large first load takes many minutes).
- **2026-09-30, ГРАДО 2 v0.69.6: load message names the failed layers and why.** Owner: NSPD layers did not load on a
  sheet A3 at 1:38 216 (0 loaded, 3 errors). Cause: the sheet covers about 195 km² and NSPD is limited to 150 km²
  (`LIMIT_KM2`); a small NSPD request from the server works. The message said only «с ошибкой: 3»; it now lists up to
  three layers with the reason.
- **2026-09-30, ГРАДО 2 v0.69.5: sheets 4–5 checked against the label rules.** Water is drawn light blue (#bfe0f5)
  under the roads on the white schemes (sheets 4–8) — the river names no longer hang over empty paper; on the ortho
  sheets water stays invisible (only for placing names). River labels also avoid the territory boundary
  («р. Вороновка» crossed it on sheet 4). Sheet 5: legend «Природные объекты — водные объекты» when water is on the
  sheet; land use by ВРИ checks agriculture first — «для ведения сельскохозяйственного производства» was coloured as
  industrial and «ЛПХ на полевых участках (1.16)» as housing. Rules file updated.
- **2026-09-30, ГРАДО 2 v0.69.4: territory callout larger and above the territory.** Owner: «выноска крупнее и сверху
  от территории, там больше места». The callout plate goes above the territory unless the top edge of the sheet is
  closer than 35 mm (then below), text 4.5 mm; the dashed leader starts at the plate edge facing the territory and
  ends at a point inside the territory near that edge. Rule updated in `docs/standards/albums/label-rules.md`.
- **2026-09-30, ГРАДО 2 v0.69.3: label rules written down and applied; Tsaritsyno-style territory callout.** Owner:
  the legend showed a district boundary that is not on the sheet; «ул. Речная» crossed roads — small streets may stay
  unlabelled; formulate the graphic label rules including his remarks and apply them; the area callout differs from
  the sample. Rules: `docs/standards/albums/label-rules.md` (fonts, white halo, inside the frame, no overlaps, no road
  crossings, priority order, rivers, streets, territory names, corner note, callout, boundary). Street labels
  (print_io `_straight_runs`): the label sits on the longest straight stretch (vertices within 0.6 mm of the chord)
  with no junction inside (a vertex shared by two street lines) and must fit it with 10 % to spare — short streets are
  not labelled, labels never run across a side street. Priority: labels at fixed places (rivers, document numbers,
  ГИС ОГД) first, then streets, then area names largest first. Legend «района» only when the district boundary
  crosses the sheet. Callout like «ГК Царицыно»: translucent white plate without border (`lboxAlpha` 0.75), grey
  text in three lines, white dashed leader with a dot to a point inside the territory near its south edge (`lead`).
- **2026-09-30, ГРАДО 2 v0.69.2: labels stay in the frame and off the roads; every large СНТ named; translucent ortho
  legend.** Owner on sheet 3: «р. Вороновка» crossed roads; some large СНТ were not labelled; a label on the left ran
  past the frame; the legend plate should be wider (one line per item) and more transparent. River labels (albums.js
  `waterLabels`) now search along the river for a spot whose text rectangle (label length at the sheet scale) lies
  inside the frame and crosses no road polygon (`calc.uds_ya`, `egko.roads`), shifting up to 50 m off the course if
  needed. Map labels (print_io): widths measured with the real font (`_text_w`); area labels sorted largest first, an
  occupied spot is retried at offsets inside the label's own polygon, every label is pulled fully inside the frame;
  street and ГИС ОГД labels that would leave the frame are skipped. КРТ 3141: СНТ «Победа», «Поляница-2», «Родничок»,
  «Пролетарий» are back (they collided with street labels and the corner note). Fill transparency: path `alpha`
  (PDF ExtGState `/ca`, SVG `fill-opacity`, PPTX `a:alpha`); the ortho legend plate is 72 % white and widens left so
  each item is one line clear of the page-number plate. Tests `LabelsInFrame`.
- **2026-09-29, ГРАДО 2 v0.69.1: river names along the water, on the larger water body; bolder boundary.** Owner: the
  river name must run parallel to the river, names are better tied to larger water bodies (the big pond), the boundary
  bolder still. `waterLabels` (albums.js): per ЕГКО name, the largest ЕГКО water polygon within 400 m of that name's
  label points (a polygon with another name is skipped, one polygon — one name) gets the label; a pond or lake gets it
  at its centre along its principal axis, a river at the ЕГКО label point along the local course (principal axis of
  river vertices within 200 m); near-vertical names read bottom to top. КРТ 3141: «р. Поляница» now sits along the
  17.6 ha pond (ЕГКО has no name for it; the nearest labels there are generic «пр.»). `egko.water` is loaded invisibly
  for this. Territory boundary 2.4 mm, dash 2.4/2.4.
- **2026-09-29, ГРАДО 2 v0.69.0: ППТ КРТ album — sheet 3 remarks applied to all sheets.** Owner on sheet 3: roads as
  polygons from Yandex or ЕГКО; rivers labelled blue with a white outline; Montserrat everywhere; okrug and district in
  the corner dark red, «Троицкий» and «административный округ» on separate lines; thicker territory boundary. Roads:
  `calc.uds_ya` (Yandex carriageway, axes widened by class where there is no HD) under `egko.roads` instead of the
  OSM-axis bands; ЕГКО has only 4 road polygons in the КРТ 3141 frame, so Yandex carries the rural roads. The album now
  loads Yandex roads for the sheet frames (within the 40 km² limit), not only 400 m around the territory. Rivers: new
  source `egko.water_labels` (ЕГКО «Подписи к водной поверхности», «Подписи к тонким рекам и ручьям»), one label per
  name nearest to the territory, generic «пр.»/«ручей» dropped; blue #1f8fe0 with white halo. The Century Gothic family
  is removed: every album text is Montserrat (PDF and PPTX). Corner note blocks `[[«Троицкий», «административный
  округ»], [«район Вороново»]]`, dark red #9e1717. Territory 1.6 mm, dash 1.6/1.6. Ortho legend wraps its labels clear of
  the page-number plate.
- **2026-09-28, ГРАДО 2 v0.68.1: label halos are solid again.** Owner: place-name labels had a dotted white outline
  instead of a plain one. The PDF halo strokes the glyphs (text render mode 1) inside q…Q and inherited the dash pattern
  of the previous path — the dotted territory boundary [1.1, 1.1]. The halo now resets the dash (`[] 0 d`). Test
  `PdfHalo`.
- **2026-09-27, ГРАДО 2 v0.68.0: ППТ КРТ album sheets 3–9 exactly like «ГК Царицыно» under the template header.**
  Owner: «делай в точь как в Царицыно», then chose «шапка ППТ КРТ, остальное как Царицыно»; sheets 1–2 (approved)
  unchanged. Layout measured from the sample PDF: map without frame at 7, 44, 279 × 239 mm (sheets 5–9 share frame and
  scale), right column from x 293: «Условные обозначения» Century Gothic 12 pt bold, underlined group titles, 8 × 3 mm
  swatches, 10 pt text; okrug and district in the map corner. Sheet 3 ortho bleeds under the header, white legend plate
  bottom-right, «Территория рассмотрения (S га)» plate under the territory. Sheet 4: map 198 × 152, photos 94 × 71 in
  the sample grid (2 + 2 right, 4 below, cropped to fill), number plates, blue view arrows (EXIF GPSImgDirection, else
  towards the territory). Sheet 5: land use coloured by ЕГРН parcel ВРИ (Moscow functional-use classes, sample colours),
  roads grey, buildings outlined, parcels blue, ЛГР by REDLN97 with titles from the ЛГР catalogue. Sheet 6: zone number
  and index large on the zone, legend samples, table «Функциональные зоны и их параметры». Sheets 7–8: every document its
  own colour, big numbers, list items boxed in the document colour; АГР joined to the ГПЗУ it lies on (second line).
  Sheet 9: parcels inside thick blue with «Кадастровый номер» plates, outside light, cards of parcel data. Map labels:
  streets abbreviated («ул. Садовая», «Калужское ш.»), territory names from OSM landuse. New font family `gothic`
  (PPTX: Century Gothic, PDF: bundled Montserrat), text `underline` in PDF/SVG/PPTX, label options `lbox`, `ldy`, `lfs`,
  `lhc`, `nodot`, line `nl`, view marker `mk: "view"`. Tests `ConceptSheets`.
- **2026-09-27, ГРАДО 2 v0.67.0: album «План реализации ППТ КРТ» — sheets 3–9 by the composition of «ГК Царицыно».**
  Owner: keep the ППТ КРТ template design, take the sheet list from the Царицыно concept. New sheets (definitions in
  albums.js, layers and styles as in section 1): 3 Ортофотоплан (streets, district boundary red dashed), 4 Материалы
  фотофиксации (map left, photos right), 5 Схема существующего использования территорий с границами ЗОУИТ, 6 Генплан —
  фрагмент «Карта функциональных зон» (table of zones), 7 Обеспеченность документацией ППТ и ПМТ, 8 … ГПЗУ и АГР,
  9 Существующие землепользователи (table of parcels). Layout (album_io): map in the frame of template slide 4
  (24, 44, 263 × 233 mm), legend and lists in a right column, okrug and district in the map corner (MapNoteFrame),
  long red titles shrink to fit (down to 12 pt). New ГИС ОГД sources `gisogd.pmt` (pmtgk, quarters with ПМТ) and
  `gisogd.agr` (suagr). Sheets 7 and 8: documents crossing the frame are numbered from the territory outwards, numbers
  on the map (moved off occupied places), numbered list «Название №… от … г.» in the column (`docsSheet`, `lists` in
  ColumnFrame). Callout «Рассматриваемая территория S = … га» and legend «Граница территории рассмотрения» as in the
  template; legend titles without source tags for template albums; `legendTitle` override. Satellite tiles overlap by
  one pixel — white specks at tile corners are gone. Tests `PptKrtSheets`.
- **2026-09-27, ГРАДО 2 v0.66.0: album to editable PPTX; rounded joins on map outlines.** Owner: the presentation must
  be available not only as PDF but as a live, editable PPTX. New `core/render/grado_render/backend_pptx.py` runs the
  same op list as the PDF and SVG backends and writes an OOXML package with zipfile (no new dependencies): paths become
  freeform shapes (custGeom), labels real text boxes (font, size, rotation, halo as glow), tiles and photos pictures.
  Each frame of the sheet is a named group (Карта, Легенда, Оформление, Выноска…), inside the map one group per layer
  (new no-op `layer` marker in SketchMapFrame, ignored by PDF/SVG). PowerPoint has no clipping, so clips are done by
  geometry: polygons cut by the frame rectangle (fill and outline separately, no false edges along the frame),
  polylines cut, pictures cropped with srcRect, labels and points outside dropped; a ring clip (ЕГКО basemap inside the
  okrug) becomes a white mask on top (rectangle with the okrug cut out). Hole rings wind opposite to outer rings, so holes
  stay empty under any fill rule. Consecutive unfilled lines of one style merge into one shape (hatches). Button «PPTX»
  next to «PDF альбома», endpoint `/api/print/pptx`. Checked: LibreOffice renders the album like the PDF. The PowerPoint
  check did not run (the app waited on a dialog; control of it was not granted). Owner: the okrug nodes on the Moscow
  scheme looked too sharp — map outlines now use round joins (`join: "round"`, PDF `1 j`, SVG `stroke-linejoin`);
  PDF default miter joins drew spikes up to 10× the half-width at acute nodes. Tests `test_pptx.py`, `Pptx`.
- **2026-09-27, ГРАДО 2 v0.65.7: administrative boundaries from the owner's reference.** The owner supplied his QGIS
  set «Новые районы и округа» (МСК of ГИС ОГД, OGD_PROJ4): 12 okrugs and 132 districts after the ТиНАО reform (ЗАО has
  12 districts — «Внуково» went to НАО). Checked before use: per-okrug district files equal «Границы_исх», every okrug
  equals the union of its districts, the districts cover «Москва» with no gaps or overlaps. Converted once with QGIS
  ogr2ogr to WGS84 (6 decimals) into `docs/standards/admin/moscow-adm.geojson` (2.9 MB). `run_admin` now serves this
  file (no portal downloads, 0.03 s) with the tag `ADMIN_REV`; albums.js `ADM_REV` is the same tag, so projects with
  the old layer reload it. The browser assembly `okrugsByDistricts` (v0.65.4–0.65.6) is removed: its gap rule gave
  wrong okrugs (ЗАО 203.0 vs the reference 188.8 km², ЮЗАО 110.9 vs 103.8). Test `AdminReference`.
- **2026-09-27, ГРАДО 2 v0.65.6: okrug = sum of its districts, a district is in one okrug only.** Owner's rule and
  marks: the ЗАО boundary at Солнцево runs along the НАО line (the 10.5 km² strip south of Солнцево is ЗАО), the НАО
  boundary at Бутово runs along the ЮЗАО edge, ЗАО «Внуково» stays in ЗАО. `okrugsByDistricts`: old-Moscow districts
  as in ГИС ОГД; new ТиНАО districts minus the old districts they overlap; okrug = union of its districts; land inside
  ТиНАО (precise ЕГКО settlements) covered by no district goes to the okrug with the longest common border (area of a
  30 m band around the gap inside the okrug) — gives both of the owner's marks. `turf.union` of all 125 districts at
  once fails (SweepLine error) and `booleanIntersects` on big outlines cost 39 s: step-by-step differences with a
  bounding-box check instead — the whole assembly 6.8 s. ЗАО 203.0, НАО 359.2, ТАО 1 070.0, ЮЗАО 110.9 km².

- **2026-09-26, ГРАДО 2 v0.65.5: okrug boundaries by a reference assembly — no crossings at Солнцево and
  Ново-Переделкино.** Owner: okrug boundaries cross wrongly there. The new ТиНАО districts of ГИС ОГД (virtualterr_*)
  are schematic (straight lines across the land): they overlap old Moscow and leave a gap at Московский (25 % of it
  in no new district); they also re-cut settlements (Первомайское NAO/TAO, Десеновское → ТАО). No precise layer of
  the new districts exists (checked both portal maps; other map codes 404/403). Assembly now (`okrugsByDistricts`):
  ТиНАО = precise settlements of ЕГКО «Границы районов» (server adds them as «поселение») + old districts lying ≥ 90 %
  inside new ТиНАО districts (ЗАО «Внуково» → НАО); ТАО = ТиНАО ∩ new ТАО districts, НАО = ТиНАО − ТАО (outer outline
  and the joint with old Moscow precise, the ТАО/НАО line inside by the new districts); new districts clipped to
  their okrug; old-Moscow okrugs = union of their districts as in ГИС ОГД (the partial cut of Южное Бутово in v0.65.4
  was an artefact of the schematic line and is gone). ТАО 1 070 km², НАО 384.8 km², ЗАО 177.5 km², ЮЗАО 110.9 km².

- **2026-09-26, ГРАДО 2 v0.65.4: ЗАО and ЮЗАО boundaries without the territory given to НАО.** Owner: ЗАО and ЮЗАО
  boundaries on the Moscow scheme are old. The old-Moscow district layers of ГИС ОГД were not updated after the
  ТиНАО district reform: ЗАО «Внуково» (two parts, 15 km²) lies wholly inside the new НАО «Внуково», ЮЗАО «Южное
  Бутово» overlaps НАО «Щербинка» by 7.8 km². `trimOldDistricts` (albums.js): where a new ТиНАО district
  (`virtualterr_*`) overlaps an old one, the new one wins — the overlap is subtracted (turf.difference), scraps
  under 1 ha dropped, a district with less than 5 ha left removed; districts that only touch keep their outline.
  Okrugs are then unions of the trimmed districts (ЗАО 177.5 km², ЮЗАО 103 km²). Build marker `ADM_REV` reloads
  older data.

- **2026-09-26, ГРАДО 2 v0.65.3: okrug map without basemap tiles — white outside the okrug** (owner).

- **2026-09-26, ГРАДО 2 v0.65.2: okrug map of the location sheet as in the template.** Owner: the right scheme is
  wrong, check the template. The template shows a detailed colour base map inside the okrug (grey buildings, green,
  blue water, white streets) and a washed-out one outside, district boundaries in black. Now: `print_io.egko_ops`
  draws ЕГКО base2 (forest, lawns, water, road polygons, buildings) from the server cache, clipped to the okrug
  outline (`mask`), over a light fill; the Esri light grey tiles stay outside. Buildings under 0.3 mm on paper are
  skipped, outlines simplified to 0.12 mm (`_simplify`, Douglas–Peucker; closed rings split at the farthest point):
  ТАО at 1:243 000 — 9.5 k shapes, 136 k vertices, 7.6 s. Backends gained a clip by rings (PDF `W*`, SVG clipPath).
  `esri_tile.egko` hands `egko_features` to the printer. District lines black.

- **2026-09-26, ГРАДО 2 v0.65.1: okrug boundary = union of its districts (ТАО/НАО).** Owner: the ТАО/НАО boundary
  is wrong. In ГИС ОГД the okrug layers (`prefect_*`, and ЕГКО «Границы административных округов») are made of the
  old 21 settlements of ТиНАО, while the ТиНАО districts («Территория / районы ТАО / НАО»: Бекасово, Вороново,
  Краснопахорский, Троицк; Внуково, Коммунарка, Щербинка, Филимонковский) are new — the two disagree by 56–90 km².
  The owner chose the district version. `okrugsByDistricts` (albums.js) rebuilds every okrug polygon by `turf.union`
  of its districts when «Административные округа и районы» is loaded (holes under 0.5 km² — gaps between old-Moscow
  districts — dropped); marker «Граница: по районам» makes albums reload older data. ТАО 1 070 km², НАО 382 km².

- **2026-09-26, ГРАДО 2 v0.65.0: album «План реализации ППТ КРТ» by the owner's PowerPoint template — title and
  location sheets.**
  - The owner gave two references: a ППТ КРТ template (.pptx, A3 landscape, red header) and the concept «ГК Царицыно»
    (PDF). Decision: both as separate albums, built sheet by sheet with the owner. The Moscow scheme was already to
    scale (checked: transform error 0.00 mm; ТАО 1 077 km², НАО 357 km² by ГИС ОГД) — the template picture is to
    scale too; its layout is what was missing.
  - `album_io.py`: ППТ КРТ page — header wave (image from the template, `docs/standards/albums/pptkrt-header.jpg`),
    «ППТ КРТ … (АО, район)», red Montserrat title with arrow, page number on the red tab; title page (red block,
    white frame). Location sheet: whole Moscow (districts thin grey, okrugs black with one label each, own okrug red),
    own okrug with districts on the Esri light grey basemap and its name top right, dotted callout «рассматриваемая
    территория / Район …» with leaders to both maps. Montserrat (SIL OFL, downloaded with the owner's consent from
    JulietaUla/Montserrat) in `docs/standards/fonts`.
  - `albums.js`: templates `PPTKRT`, button «Альбом ППТ КРТ» in «Листы»; `buildSection(tpl, prefix, size, name)`
    generalised. Schemes (`adm`) fill their frame with an exact scale; territory drawn as a point on small-scale maps.
  - Print: label halo (PDF text stroke), label font and colour per feature, one label per multi-part polygon at the
    centroid of its largest part, maps without frame (`noFrame`), Esri light basemap (`esri_tile(kind="light")`).
  - Administrative division loads districts of all okrugs over the whole of Moscow (137); «Районы …» panels keep
    only the own okrug by «Округ».

- **2026-09-26, ГРАДО 2 v0.64.1: PDF printing on the server — bundled fonts.** AEZA-GRADO has no system fonts at
  all, so `find_font` raised «не найден TTF с кириллицей» and «PDF альбома» failed on grado.tailink.tech. PT Sans and
  PT Serif (regular and bold, ParaType free licence, extracted from the macOS copies) now live in
  `docs/standards/fonts` and are found first: the same sheet on Mac and server. New families `ui-bold` and
  `serif-bold` for the album templates (PT Serif stands in for Palatino of the ППТ КРТ template).

- **2026-09-26, ГРАДО 2 v0.64.0: section «Существующее положение» checked end to end on КРТ 3141 (Вороново, ТАО).**
  - Run on a copy of the owner's project, territory = КРТ 3141 (54.61 ha): 11 slides, first build 2 min 48 s, PDF
    11 pages 2.6 MB in 2 s. Found and fixed:
  - Districts of ТАО, НАО and ЮЗАО were missing (slide «Районы ТАО» empty): their portal folder is «районы …» in
    lower case and ТАО/НАО district layers are `virtual`; the match is now case-insensitive and takes both types.
  - A failed source vanished silently: `loadKeys` clears ERRORS, so an Overpass failure in an earlier group was lost
    and OSM roads were missing on three slides. `buildSection` keeps errors of every group, retries each failed layer
    once and names what still did not load.
  - Restrictions slide had no ГИС ОГД zones in ТиНАО (Генплан «Водоохранная зона» virtual1747 is empty there). New
    source `gisogd.zouit` — 17 СПРИТ layers (water protection, coastal and shore strips, flooding, power, communication,
    ООЗТ, military, radio …) with «Вид зоны» and Эталон colours; a layer the portal refuses is skipped with a note
    (`ZONES_TOLERANT`). On the restrictions slide and in the «Ограничения» window.
  - Genplan table of ТиНАО: number from `number_fz`, index `fz_type`, fund `interval_fo` (was «—»); labels likewise.
  - Social slide with no OSM objects now says so instead of an empty radius legend.
  - Tables fit their cells (smaller type down to 65 %, then «…»; cadastral numbers stay whole), ownership kinds
    abbreviated; white outlines in the legend of satellite slides drawn grey.

- **2026-09-26, ГРАДО 2 v0.63.1: readiness check before real work; project versions.**
  - Check on a copy of the owner's project «Безобразово» (36 layers, sheet A1 1:5053) on the test server: opens in
    7 s, Эталон styles and label angles applied, PDF 14 s (6 272 objects), «DXF ГИС ОГД» of 34 layers 85 s — ezdxf
    audit 0 errors, 125 labels all rotated, 20 hatches; save and reopen 3 s, 16 MB.
  - Project versions: before a project file is overwritten the previous one is kept gzip-compressed in
    `.versions/<project>/YYYYMMDD-HHMM.grado2.gz` (manual save at most every 10 min, autosave every hour, last 40).
  - Print: hatch lines 0.13 mm (were tied to the outline width and came out heavy); client runs the portal-style and
    label-angle pass once at a time (it ran twice on project open).

- **2026-09-26, ГРАДО 2 v0.63.0: sheet print and DXF look like the map; ГИС ОГД labels run along their borders.**
  - Owner: the sheet export has other styles; labels are not everywhere parallel to the lines.
  - Labels: `ogd_all.label_angles` — angle of the nearest segment (≤ 30 m) of the layers in the same portal folder
    (borders and zone outlines), counter-clockwise, upright; stored as `_angle`. Set on load of `ogd.*` label layers,
    for older projects by `POST /api/ogd_all/label_angles` (client `labelAngles()` once per layer), and in
    «DXF ГИС ОГД». Map, print and DXF read `_angle`, else −textangle.
  - Print (`print_io` + `sheetSpec`): outline dash, outline colour next to hatch (`strokeOwn`), hatch step as on the
    map (Эталон 2 mm), outline drawn over hatch, label layers without markers — text on the point, in the sign colour,
    at its angle, without overlaps.
  - DXF: Эталон zones get a HATCH in the hatch colour and angle, 2 mm on paper at the sheet scale (ANSI31/ANSI37).

- **2026-09-26, ГРАДО 2 v0.62.0: layer tree «По листам» — a folder per sheet with exactly that sheet's layers.**
  - Owner: the functional-zoning slide should have its own folder with only the layers shown on it; a layer used by
    several sheets sits in several folders.
  - Button «По листам» over the tree (`bBySheet`, saved as `ALBUM.meta.treeBySheet`). Folder content: section sheet —
    its keys (panels — union), sheet with a view — visible layers of the view, «текущая карта» — visible map layers
    (menu «Закрепить состав листа» turns them into the sheet's own view). Same layer object in every folder
    (visibility and style shared). Eye — show only that sheet's layers; «…» — add a layer to the sheet; cross at a
    row — remove it from the sheet (keys or view change, the layer stays in the project). «Не на листах» — the rest.
  - `rowHTML` extracted from `renderTree`; frames re-render the tree in this mode.

- **2026-09-26, ГРАДО 2 v0.61.0: ЛГР layers of ГИС ОГД drawn by the ЛГР Эталон (приказ № 65).**
  - Owner: береговые полосы — blue dashed outline, no fill, labels in the same colour; everything by the СПРИТ Эталон.
  - `ogd_all.etalon_code`: ГИС ОГД layer → Эталон code from `zonelineco`/`textlineco`, else by layer and folder name
    (red-line folders 1.1–1.4.1 by number). `etalon_style`: outline in the sign colour with its dash (dash_px), hatch
    in the Эталон hatch colour and angle, labels («Надписи …») in the sign colour without a point marker, rotated by
    `textangle` (clockwise in ГИС ОГД, turned upright). Береговые полосы (41): no hatch (`ETALON_NO_FILL`).
  - Client style gained `dash`, `strokeOwn` (outline keeps its colour next to the hatch), `marker:false`,
    `labelColor`, `labelAngle`. `/api/ogd_all/styles` takes `[geom, code field]` and answers `rev` 3 for Эталон
    layers — layers styled by v0.60 restyle once on project open.
  - «DXF ГИС ОГД»: layer colour of zones and labels from the Эталон; zone outlines get the sign linetype.

- **2026-09-26, ГРАДО 2 v0.60.2: land parcels (zu_29_06_2021) — pure blue outline, no hatching.** Owner's choice
  instead of the portal pattern: `ogd_all.OWN_STYLE` (rgb 0 0 255, fill 0, width 1) for the project and the layer
  colour of «DXF ГИС ОГД». Own styles carry a revision: `/api/ogd_all/styles` returns `rev`, the client restyles a
  layer once when its `style.portal` is older (so parcels already styled by v0.60.1 turn blue on project open).

- **2026-09-26, ГРАДО 2 v0.60.1: ГИС ОГД portal layers in the project look as on the portal map.**
  - Owner: layers loaded from «Исходные данные» got random palette colours with 70 % fill and covered the map.
  - `ogd_all.portal_style(css, geom)`: CartoCSS of the layer → ГРАДО style: block of the geometry type, fill and
    polygon-opacity (solid portal fill shown at 35 %), outline colour and width, hatching for pattern fills (angle from
    the sign description in the CSS comment; image pattern without colour — hatch in the outline colour), rgb()/rgba()
    colours, categories `[field='value']`, label field of point layers («Надписи …»). `POST /api/ogd_all/styles`.
  - Client `portalStyles()` applies it once per `ogd.*` layer after loading and on project open (mark `style.portal`
    saved with the project; later changes are yours). Lines with a ГИС ОГД line code use the ЛГР mode (REDLN97).

- **2026-09-26, ГРАДО 2 v0.60.0: one «Исходные данные» window; large areas loaded by parts.**
  - `web/ogdpick.js` is now the single source picker: one tree — ЕГРН · НСПД, ГИС ОГД curated sets, all 716 layers of
    the ГИС ОГД portal in its order (key `ogd.<code>`), ЕГКО, OpenStreetMap, Яндекс, relief; search, folder checkboxes,
    object counts of portal layers in the area. Buttons «Загрузить в проект» (sheet or coverage of all sheets) and
    «DXF ГИС ОГД» (portal layers, sheet). Opened by «Выбрать и загрузить…» in «Данные», «Загрузить сюда» on a sheet
    and «DXF ГИС ОГД». Selection lives in CHECKED (saved with the project); the former DXF choice
    (`ALBUM.meta.ogdCodes`) is taken over. «Данные» lists what is already in the project, without checkboxes.
  - Server: any catalog layer loads by `ogd.<code>` (registered in SOURCES on first use, loaded one after another).
  - Area limits: НСПД and Overpass over TILE_KM2 (4 and 25 km²) are fetched in equal parts one by one and merged
    (`split_bbox`, `merge_layers`: object on a seam once, by `_key`); progress «часть i из n». Limits now 150 km²
    (Яндекс 40 km²: it glues tiles itself, the limit is the first-load time). Sheets no longer shrink the НСПД frame.

- **2026-09-26, ГРАДО 2 v0.59.1: ГИС ОГД labels at their own height.** Owner: labels scaled up for the sheet
  (×4.8 at 1:9542) crowd the drawing in AutoCAD. Labels now keep textheight of ГИС ОГД as is (metres in the model);
  the portal places them for that size.

- **2026-09-26, ГРАДО 2 v0.59.0: «DXF ГИС ОГД» — technical zones in colour and dashed, СПРИТ labels as text.**
  - Layer colour from the portal CartoCSS now comes from the block of the layer's geometry type
    (`['mapnik::geometry_type'=N]`), white skipped: technical zones (l29) were white because the first colour in their
    CSS is the white fill of the point marker.
  - Line codes without a REDLN97 linetype (29 technical zones, 3, 41, 45 …) get a dashed `LGR_NN` linetype from the
    ЛГР Эталон (dash_mm × 2 m, same as the PDF print) and the ЛГР colour.
  - Label layers «Надписи …» (points with text, textangle, textheight) become TEXT at the point, centred, style
    GISOGD (arial.ttf, Cyrillic). The ГИС ОГД angle is clockwise (checked against the nearest border line: −textangle
    matches in 115–139 of 150 samples); upside-down labels are turned. Height textheight is metres for 1:2000 and is
    scaled up on smaller-scale sheets to keep 2 mm on paper.

- **2026-09-26, ГРАДО 2 v0.58.9: natural complex border signs face their territory.**
  - Owner: some ПК triangles still look outward. In ГИС ОГД the sign of code 18 does not tell the side: across Moscow
    the polygon of «Природные и озеленённые территории» lies to the right of nearly every l18 line, both «18» and
    «−18» (10 762 of 12 215 «−18» lines disagree with the geometry).
  - `ogd_all.orient_lines`: before drawing, each l18 line is tested against virtual138 polygons (l21 against
    virtual139, code 21): points 0.5 m left and right of the midpoints of the longest segments. When the territory is
    clearly on the other side of the code's sign, the line is reversed (other codes keep their relative side).
    Lines with both signs (18,−18) or without a clear answer stay as in ГИС ОГД. Polygons come from the cache even
    when their layer is not selected. Owner's sheet 1:9542: 327 borders inward, 56 unclear, 0 outward.

- **2026-09-26, ГРАДО 2 v0.58.8: REDLN97 signs run continuously along ГИС ОГД lines in AutoCAD.**
  - Owner: natural complex markers point in different directions and break off. Cause: polylines had no «linetype
    generation» flag, so AutoCAD restarted the 20 m pattern at every vertex; ГИС ОГД boundaries have segments of
    0.2–1 m, so the triangles vanished or turned along random short segments. Lines with a REDLN97 linetype now carry
    PLINEGEN (flag 128) in both «DXF ГИС ОГД» and the plain DXF export.

- **2026-09-26, ГРАДО 2 v0.58.7: «DXF ГИС ОГД» draws СПРИТ lines with the owner's REDLN97 linetypes.**
  - Objects with a ГИС ОГД line code (`linelineco`/`LineCode`: layers l1…l57 and virtual2950 — red lines, building
    regulation lines, zone borders of section 11) get the REDLN97 linetype and the ЛГР colour, exactly like the plain
    DXF export (one polyline per linetype when a line carries several codes); `red_lns.shx` and `REDLN97.LIN` go into
    the archive next to the drawing. Codes without a REDLN97 linetype stay plain lines of their layer.
  - Checked on the owner's sheet 1:9542: 13 СПРИТ layers, 3 723 objects, 21 linetypes (L00s01s red lines, L00s06s
    railway right-of-way, L00s18t/b natural complex …).

- **2026-09-26, ГРАДО 2 v0.58.6: DXF opens in AutoCAD — no commas in layer names; extents and view set.**
  - AutoCAD (Mac and Windows) did not open the DXF at all, without an error, while QGIS read it: 6 of 68 layer names
    had commas («…геодезической, нивелирной, …»), and AutoCAD forbids `,` in symbol table names just like
    `< > / \ " : ; ? * | = \``. v0.55 had wrongly allowed the comma. The plain DXF export had the same hole
    («Школы, детсады, поликлиники (OSM)»). Now one rule, `dxf_io.acad_name`, for both exports and the sheet layout:
    forbidden characters and control codes → «_», repeated spaces collapsed, length limit.
  - Also: `$EXTMIN/$EXTMAX` and limits are set from the model (ezdxf rewrites the header from the model on save, so
    `msp.reset_extents`), the model view opens on the data (the sheet frame for «DXF ГИС ОГД»), and the sheet layout
    reuses the default «Layout1» (renamed) instead of deleting it (tab order 1, no *Paper_Space swap).

- **2026-09-26, ГРАДО 2 v0.58.5: the server keeps the ГИС ОГД cache warm by itself.**
  - `apps/grado2/ogd_warm.py`: walks the catalogue, re-downloads layers older than 6 days (TTL is 7) one by one with
    the connector's pause, skips fresh ones without reading them, waits while the program itself is downloading, and
    records layers the portal refuses in the same failure list as «DXF ГИС ОГД». Run nightly by the `grado-warm`
    timer on grado.tailink.tech. The Mac's cache (716 layers) was copied to the server once.

- **2026-09-26, ГРАДО 2 v0.58.4: a running ГИС ОГД export is always visible.**
  - Progress lived only in the tab that started the export: after a reload (or from another tab) the page showed
    nothing, and a new click answered «Выгрузка не началась: выгрузка уже идёт». Now the page picks up a running
    export on open and on that answer; the button shows «ГИС ОГД N/M · стоп», the status line names the sheet
    (`where` kept in the server job), and the archive downloads when it ends.

- **2026-09-26, ГРАДО 2 v0.58.3: big ГИС ОГД layers no longer run the server out of memory.**
  - On grado.tailink.tech (3 GB limit) «Земельные участки» (`zu_29_06_2021`, 71 MB zip) was OOM-killed four times:
    `GisogdApi.fetch` kept every object in a list, parsed the layer's whole GeoJSON with `json.loads` to restore texts
    cut by dBASE at 254 bytes, and built a second list for the line cache.
  - Now: pass 1 over the SHP finds objects with cut texts; the GeoJSON is read as a stream (one object at a time,
    `raw_decode` over incremental UTF-8) keeping only those objects' long strings; pass 2 writes the line cache
    straight to disk and keeps only objects in the area. Measured on the same layer: peak 810 MB (was >3 GB + 1.9 GB
    swap). Test: GeoJSON in 7-byte pieces restores a 1 000-character ВРИ list.

- **2026-09-26, ГРАДО 2 v0.58.2: scale hints no longer hang on the map; one-command server update.**
  - The sheet bar's scale field had a `datalist`; the bar is re-rendered on change, and Yandex Browser left the open
    hint list (5000, 25000) floating over the map. Now: a plain field plus a small «▾» select of standard scales.
  - `tools/deploy-server.sh`: sends HEAD (apps/grado2, core, docs/standards) to grado.tailink.tech via AEZA-US, swaps
    `/opt/grado/app`, installs requirements when they change, restarts `grado`, waits for `/api/health` with the new
    version and rolls back to the previous copy if it does not come up.

- **2026-09-26, ГРАДО 2 v0.58.1: the server can run behind a reverse proxy (`GRADO2_PUBLIC_HOST`).**
  - The Host/Origin guard accepted only 127.0.0.1/localhost. With `GRADO2_PUBLIC_HOST=grado.tailink.tech` it also accepts
    that Host and the `https://` origin of it; other hosts and pages are still refused. Used by the server deployment
    at grado.tailink.tech (password on the proxy).

- **2026-09-25, ГРАДО 2 v0.58.0: «Слои ГИС ОГД в DXF» — choose the layers; DXF layers in the portal's folder order.**
  - «DXF ГИС ОГД» (sheet bar or header) opens a dialog (`web/ogdpick.js`): the ГИС ОГД catalogue as a folder tree in
    the portal's own order (roots «Слои» with sections 1–21 and «Территория»), checkboxes on layers and folders
    (a folder toggles its shown layers and stays open), search, «только с объектами на листе», «С объектами (N)»,
    «Снять все», and the number of objects of each layer on this sheet. Counts come from the disk cache only
    (`POST /api/ogd_all/scan`, ~9 s for 716 layers; «?» — layer not cached). Default: the project's previous choice
    (`album.meta.ogdCodes`), else the layers with objects on the sheet. Only the chosen layers are fetched and drawn.
  - DXF layer names carry the tree number: `ОГД 11.01.01.02 <folder> - <layer>` («Т.» for «Территория»), so
    AutoCAD's alphabetical layer list follows the ГИС ОГД order; long folder names are shortened, the number and the
    layer name stay. `catalog()` now also returns `id` and `parent_id`; `GET /api/ogd_all/tree` gives the tree
    (catalogue cached in memory for an hour).

- **2026-09-25, ГРАДО 2 v0.57.0: one kind of sheet — a sheet drawn on the map is an album sheet; loading follows the sheets.**
  - The «Лист» tool now creates an album sheet (`ALBUM.sheets`), not a separate map frame: it appears in «Листы» at once,
    prints to PDF and exports to DXF. Every map sheet of the album is a frame on the map with grips and the bar
    (name, format, orientation, scale, «Загрузить сюда», «DXF ГИС ОГД», preview, delete); dragging sets
    `sheet.center`, resizing sets `sheet.scale` (any value; the table keeps a non-standard scale). Section sheets
    (built from the territory) show dashed grey only while «Листы» is open; overview schemes, ТЭП and title sheets
    have no frame. The old per-sheet «рамка» button now selects that sheet's frame and zooms to it.
  - New formats «А4–А0 без штампа» (`BA4`…`BA0`, `orient` L/P): the map fills the page with 2 % margins (paper
    proportions kept), thin frame and a caption «название · М 1:…» (print_io `PAPER`, `PaperFrame`). The tool draws
    А3 without stamp by default, or the format of the last own sheet.
  - DXF of a sheet: the layout page is the paper (plain sheets) or the map field (ГОСТ, slides); the viewport is the
    map field at the sheet scale (checked: page 420 × 297, viewport 403.2 × 285.1 mm, 1:1612).
  - «Загрузить» covers the frames of all own map sheets (plus boundary + 60 m when there is a boundary); without sheets
    — the A3 frame around the territory. Sheets from v0.56 (`album.frames`) migrate to album sheets on open.

- **2026-09-25, ГРАДО 2 v0.56.0: «Лист» — a sheet drawn on the map, the DXF of ГИС ОГД is cut by it; «Листы» button fixed.**
  - «Листы» in the header did nothing: it stands outside the «Окна» group and only that group had the click handler.
    The handler now sits on the whole header.
  - New ribbon tool «Лист» (`web/frames.js`, like a Figma frame / AutoCAD viewport): drag a rectangle on the map — the
    paper proportions (A3 landscape by default) hold, the scale follows the size; a click makes a sheet 60 % of the
    screen. A selected sheet moves by dragging inside, resizes by a corner (opposite corner stays), and shows a bar
    above it: format А4–А0, orientation, scale (typed or from the list), «Загрузить сюда», «DXF ГИС ОГД», delete.
    A click inside a sheet selects it unless a drawing object is under the cursor; Esc deselects, Del deletes.
    Sheets live in МСК (centre and size in metres) and are saved in the project (`album.frames`). No boundary needed.
  - «DXF ГИС ОГД» (bar and header button — the selected or last sheet; none → the tool starts): all ГИС ОГД layers
    cut exactly by the sheet in МСК, layer colours from the portal CartoCSS (`/layers/{code}/css_style`, cached
    30 days), frame on «Рамка листа», boundary clipped to the sheet, and a paper layout «Лист N 1-M» of the sheet
    format with a viewport at the sheet scale (checked: A3, viewport 420 × 297 mm on 840 × 594 m = 1:2000).
  - «Загрузить» covers the sheets on the map too and works without a boundary.
  - The frame interaction sits right under the CAD command interceptor (`gradoTop` mark in cad.js); both keeping
    themselves last looped forever.

- **2026-09-25, ГРАДО 2 v0.55.0: data and the ОГД drawing follow the sheet frames, not the site boundary; DXF opens in AutoCAD.**
  - «Всё ОГД в DXF» made a drawing AutoCAD refused to open: XDATA strings were cut at 250 characters, and Cyrillic takes
    2 bytes, so 90 strings were up to 464 bytes (AutoCAD limit 255 bytes). Now cut by bytes without splitting a letter;
    layer names ≤ 100 characters.
  - The drawing is for handing over, so its area is the sheet frame: the first map sheet of the album (format, scale,
    shift), or, with no sheets, an A3 sheet at auto scale around the territory. Only ОГД layers, clipped to the frame,
    plus «Рамка листа» and «Граница территории». The archive is named after the sheet and scale.
  - «Загрузить» (and ФГИС ТП documents) cover all sheet frames of the album instead of boundary + 60 m: union of the
    frames of map sheets (overview schemes of Moscow/district and two-map sheets load their own data when a section is
    built), or the A3 frame when there are no sheets. The area is drawn as a blue dashed rectangle «область загрузки
    данных» while «Данные» is open (the map zooms out if it is off screen), and the window says its size in km.
    Large frames can exceed a source's area limit (НСПД, Яндекс 4 km²); that source then reports the limit.

- **2026-09-25, ГРАДО 2 v0.54.1: button renamed «Всё ОГД в DXF».**
  - opendesign.com answers «Access restricted» from Russia (browser and curl, 2026-09-25), so ODA File Converter cannot be
    installed here; the owner chose to keep DXF. The button and the final message now say DXF and point to «Сохранить как»
    in AutoCAD. The DWG branch stays: if ODA File Converter is ever installed, DWG is added to the archive by itself.

- **2026-09-25, ГРАДО 2 v0.54.0: «Всё ОГД в DWG» — every ГИС ОГД layer inside the territory in one drawing.**
  - Button «Всё ОГД в DWG» next to DXF. Takes the territory boundary + 60 m, walks the whole ИСОГД catalogue (layers and
    «virtual» layers, 716 on 2026-09-25) and writes one drawing in МСК: each portal layer on its own drawing layer
    `ОГД-<ИСОГД section number>-<parent folder>-<layer>` (e.g. `ОГД-11-Приаэродромная территория аэропорта Внуково-Пятая
    подзона`), empty layers skipped, objects clipped to the frame, boundary on «Граница области».
    Attributes go to XDATA (app `GISOGD`, `field=value`) and to one CSV per layer (`атрибуты/*.csv`, column Handle).
    DWG is added next to DXF when ODA File Converter is installed.
  - Runs in the background on the server (`apps/grado2/ogd_all.py`, `/api/ogd_all/start|status|file|cancel`), one job at a
    time; the status line shows layer N of M and the time left, a second click stops it.
  - Why not the portal's own area export: `POST /isogd/front/api/orbisclient/export` needs a mos.ru login (401), and the open
    API ignores `bbox` (rechecked 2026-09-25). So layers are fetched whole once via `GisogdApi` (one by one, with pauses)
    and cut locally. First full download on 2026-09-25: 69 min, 1.6 GB cache; after that 716 layers take ~10 s.
  - Six layers the portal does not give (HTTP 500: t_1320, t_1321, virtual125, virtual3185; engineering networks
    lines_pp/polygon_pp — connection dropped at 10 min) are remembered in `ogd_all_failed.json` in the cache and skipped
    for a day; the final message names them.

- **2026-09-25, ГРАДО 2 v0.53.0: tidy canvas — reference-plan layer order, one buildings layer, УДС as polygons.**
  - New default order (`PREFERRED`, top to bottom): red lines and annotations, buildings, transport points and axes, constraint
    zones (hatch/outline), parcels, surfaces (road surface, water, green), planning zones at the bottom. The old order put the
    Yandex road surface under every zone, so it was never visible.
  - «Упорядочить слои» button in the layers panel: re-sorts downloads by that order (own layers and imports stay on top), and
    of several buildings layers (ЕГКО, НСПД, Яндекс, OSM) keeps one visible — ЕГКО first. Nothing is deleted.
  - Building section 1 now leaves the canvas as a reference plan: section layers used only by slides (zones, ПЗЗ, Genplan,
    documentation, social objects, administrative division) are switched off; red lines, buildings, УДС, water, green and
    parcels stay on.
  - УДС as polygons. Canvas: «УДС: проезжая часть и проезды (Яндекс)» — Yandex HD road surface plus, where there is none
    (`hd_covered = 0`), driveways buffered from Yandex axes by road class (6–14 m). HD surface covers only major streets, the
    axes fill in the driveways. Slides: «УДС по осям (OSM)» — OSM axes buffered by highway type (5–24 m), white over the
    zones on the restrictions slide: Yandex is a user map and its data is not put into delivered sheets.
  - Road surface on the canvas is a cool grey with an edge (`#d5dae0`), no longer the invisible `#e6e3dc`.
  - Re-downloading a layer for a different frame keeps the objects of the earlier download outside the new frame and does not
    count them as «исчезло»; objects beyond the earlier area are not flagged as new in the source (`DATA[k].bbox` keeps the
    covered area). Before, rebuilding the section in another slide format dropped thousands of buildings outside the new frame.

- **2026-09-25, ГРАДО 2 v0.52.0: slides in А4, А3 and А2 as well as 16:9, chosen in «Листы».**
  - New sheet formats «слайд А4 / А3 / А2» (`SLIDES` in `print_io.py`: landscape 297 × 210, 420 × 297, 594 × 420 mm) with the
    same design as 16:9: title with arrow, project header, legend column, slide number. Margins and header type grow with the
    sheet width; map labels and the legend keep their size in mm, so a bigger sheet shows more of the map at the same scale.
  - A select next to «Раздел 1: существующее положение» sets the slide format of the section; changing it converts the section
    slides already built (scale re-picked for the new frame). Each sheet's «Формат» offers the same formats plus А3/А1 by ГОСТ.
  - Frame sizes on the map follow the format (`frameMM` in `sheets.js` mirrors `layout`, `panel_rects`, `photo_map_rect`).
    Two-map captions get three lines. Scales 1:15 000 and 1:20 000 added.

- **2026-09-25, ГРАДО 2 v0.51.0: slides without north arrow and scale bar; boundary in the legend as a line with its area.**
  - 16:9 slides draw only the map frame — no north arrow, no scale bar (owner's request, as in the section example); A3/A1
    sheets by ГОСТ keep both.
  - The legend shows the project boundary as a magenta line «Граница разработки проекта планировки (S = 16,64 га)», area in
    hectares to two decimals; non-breaking spaces keep «S = … га» on one line when the entry wraps.
  - Genplan table: shorter title, «тыс. м²» header, names cut to fit the column.

- **2026-09-25, ГРАДО 2 v0.50.0: street names along the streets, a callout for the territory, legend lines wrap.**
  - Line labels on sheets (streets on the ortho slides, any labelled line on A3/A1) run along the line on its longest segment
    inside the frame, never upside down; one label per name; skipped where the segment is shorter than half the label. On
    satellite slides labels are white.
  - The districts map of «Месторасположение» has a callout: a framed «проектируемая территория / район …» beside the territory
    with a leader line; map labels keep clear of it.
  - Long legend entries and group titles wrap (up to three lines, then «…») instead of being cut.

- **2026-09-25, ГРАДО 2 v0.49.0: section 1 slides closer to the owner's example — two maps on one slide, photo slide,
  Genplan table.**
  - A slide can hold several maps side by side (`panels`, `print_io.panel_rects` / `PanelFrame`), each with its own layers,
    frame and scale and a caption over it; the legend is shared. «Месторасположение» is now Moscow okrugs + the districts of
    the territory's okrug, and the ПЗЗ slides are merged into one: zones with ВРИ codes on the left, subzones with
    «density / height / coverage» on the right (as in 120-ПП fragments).
  - The okrug and the district containing the territory are filled pink (`hilite`); okrugs are labelled by abbreviation.
  - ПЗЗ zones are labelled by ВРИ codes only («3.5.1, 4.4 …», wrapped); subzones without parameters read «Ф».
  - Genplan: each zone labelled «number / index» in large type; a table of the zones on the territory (number, index, name,
    total floor area) in the right column.
  - New slide «Материалы фотофиксации»: map on the left, photos in a grid on the right with numbers. Photos are added with the
    camera button in the sheet row (up to 12, reduced to 1600 px JPEG, kept in the project and across section rebuilds); the
    shooting point comes from the photo's EXIF GPS and is drawn on the map with the same number.
  - Sheet labels may span several lines and have their own size; scale 1:7 500 and 1:1 000 000 added; scale bar text
    without exponent notation.
  - «Листы» window: the table scrolls sideways instead of squeezing the title column to nothing; section sheets show
    «слои раздела» instead of a misleading «текущая карта»; the title slide and two-map slides have no frame button.

- **2026-09-25, ГРАДО 2 v0.48.0: presentation slides 16:9 and section 1 «Существующее положение» by the owner's example
  (ППТ Мытищинская).** «Листы» → «Раздел 1: существующее положение» builds 11 slides and downloads what they need.
  - Format «16:9» (338,67 × 190,5 mm, `SIZES["P"]`): arrow and title top-left, project short name and place top-right, slide
    number bottom-right, map left, legend right; title slide with the object name, place and month. No ГОСТ stamp.
  - Satellite basemap on sheets: Esri World Imagery JPEG tiles (`server.esri_tile`, cache `~/.grado2/cache/tiles/esri`, 90 days,
    one at a time with a pause), each tile as an image quad in sheet mm (МСК is rotated to Mercator); zoom from the scale.
  - Slides (SEC1 in `sheets.js`): location (okrugs and districts), district ortho, territory ortho with main streets, existing
    use with restrictions, land use with numbered ЕГРН parcels and their table, Genplan, ПЗЗ zones/ВРИ, ПЗЗ subzones labelled
    «density / height / coverage» (Ф — by the existing use), approved and developing documentation (ПП, ГПЗУ, КРТ), social
    objects with Moscow service radii. Each slide has its own layers, overrides of their style, basemap and content frame
    (territory with margins, the district, the okrug); the scale is picked to fit the frame.
  - Downloads cover the whole slide frame, not the boundary + 60 m: per layer the largest frame where it is used, layers with the
    same frame in one request (`loadKeys(keys, bbox)` extracted from «Загрузить»).
  - New ОГД sources: «Проекты планировки» (9 portal layers, kind in «Вид зоны»), «ГПЗУ», «КРТ», and «Административные округа
    и районы» (all 12 prefect layers + the districts of the okrug containing the area, from the portal catalog).
  - Print: a fully transparent fill no longer prints white; on satellite slides fills under 60 % are outline only (the core
    PDF writer has no alpha); sheet tables (`table`) and a note under the legend; territory outline configurable (`terrStyle`).
  - Checked on the example area (16,6 ha, СВАО, Алексеевский): all layers downloaded, 11 slides, PDF 2,8 MB in ~11 s. Not done:
    photo fixation slide (needs photos), Genplan zone number/index table, two ПЗЗ maps on one slide.
  - Test: test_print +1 (slides, satellite quads, table, page number).

- **2026-09-25, ГРАДО 2 v0.47.0: region from lines (BOUNDARY), hatch patterns, arrow-key nudge.**
  - BPOLY «Контур по щелчку»: a click inside an area bounded by lines and polygon edges makes a polygon. Segments near the point
    (window 150 → 400 → 1200 m, up to 3 000 objects) are cut at their intersections (50 m grid), joined into a planar graph
    (vertices at 1 mm), and the face containing the point is walked (face on the left, clockwise-next edge at each vertex),
    starting from the first edge east of the point; a clockwise result means the point is outside. H (hatch) uses the same
    fallback when no closed contour is found.
  - Hatch pattern and step per layer (style panel, when hatching is on): «／», «＼», horizontal, vertical, diagonal grid,
    square grid, dots; `hatch(color, pat, step)` caches tiles per combination. Sheets/PDF draw the same directions
    (grids as two families; dots as «／»).
  - ← → ↑ ↓ move the selection 0,1 m (Shift — 1 m) along МСК axes, undoable; handled in the capture phase so the map does
    not pan. F1 rows added.
  - e2e +2 steps (BPOLY 450 m² between crossing lines, nudge 1,1 m). Hatch grid checked by screenshot.

- **2026-09-25, ГРАДО 2 v0.46.0: copy/paste between layers, move to current layer, line ↔ polygon, vertex coordinates.**
  - Ctrl/⌘+C / Ctrl/⌘+V: selected objects to the program's clipboard and into the current layer at the same place (QGIS
    behaviour), attributes kept, `_key` dropped; `geomFor` adapts the geometry to the layer (polygon → closed lines,
    closed line → polygon, points only to points); objects that do not fit are counted in the toast. F1 row added.
  - LMC «В текущий слой» (LAYMCUR): move the selection into the current layer with the same adaptation.
  - CONV «Линия ↔ полигон»: closed lines become polygons in the own polygon layer and polygons become closed lines.
  - «Объект»: table «Вершины, МСК» (up to 300 vertices; rings, holes and parts labelled) — typing X or Y moves the vertex,
    the closing vertex follows the first, undoable.
  - e2e +3 steps.
  - UX audit: «Объект» showed 597,2 м² for a 30 × 20 m rectangle drawn in МСК (ellipsoid area) — `sizeOf` now measures
    in МСК like drawing, DXF and sheets (600,0 м²). ТЭП and the graph keep their own area measure.

- **2026-09-25, ГРАДО 2 v0.45.0: select by condition, ALIGN, topological vertex editing, DXF dimensions.**
  - QS «Выбрать по условию»: «Этажность > 9 и Решение = сносим», «Наименование ~ школ» (contains), «Адрес пусто»; = ≠ > < >= <=,
    «и» / «или», field names case-insensitive and by prefix, «ё» = «е»; current layer or «Все слои». The command box shows an
    example as its placeholder (`CMD.placeholder`).
  - AL «Выровнять»: first pair moves, second pair rotates; «Да» scales by the pairs; Enter after the first pair — move only.
  - ТОПО (status bar): dragging a grip moves the same vertex (within 1 mm on the ground) of every visible line/polygon —
    neighbouring parcels keep one boundary; preview shows all affected objects. Off by default, remembered.
  - DXF: a ГРАДО 2 dimension (4-point line with «Размер») is written as a linear DIMENSION (angle of the dimension line,
    2 decimals, comma separator) instead of a polyline + text; DIMENSION types 0/1 are read back as the same 4-point line
    with «Размер». test_dxf round trip.
  - DIV/ME no longer switch the current layer to «Точки».
  - e2e +3 steps. **Pitfall in the check:** extents of a map (Mercator) bbox converted to МСК are inflated by meridian
    convergence (40 × 20 m read as 40,00 × 20,07) — compare МСК vertices, not bbox corners.

- **2026-09-24, ГРАДО 2 v0.44.0: reverse, simplify, delete ring.** REV «Развернуть» reverses lines; for REDLN97 red lines the
  side goes with the direction («+» — object to the right), so `_lt` names swap b ↔ t (also paired `LxxBxxT`), «Тип линии»
  follows and LineCode signs flip (1,-18 → -1,18). SIMP «Упростить»: tolerance in metres on the ground (Mercator scale
  at the object's latitude), OpenLayers simplify, vertices before/after reported. DR «Удалить дыру»: click inside a hole —
  polygons are looked up by bbox, since a point in a hole does not intersect the geometry. All three in «▾ → Полигоны и
  атрибуты». e2e +3 steps.

- **2026-09-24, ГРАДО 2 v0.43.0: vector work like QGIS — split, merge, subtract, buffer, match properties, divide, measure,
  select similar.** New commands in `web/cad.js` (menu «▾» of the ribbon, section «Полигоны и атрибуты»; the ribbon stays one
  row at 1280 px — a separate button made it two rows, checked):
  - SPL «Разрезать»: selected polygons by a drawn polyline. The cut side is a large polygon left of the line (ends extended
    20 km), parts = intersect / difference in Turf — no gap along the cut; every part keeps the attributes; parts selected.
  - UNI «Объединить»: polygons of one layer into one (MultiPolygon when they do not touch), attributes of the first.
  - SU «Вычесть»: from the selected polygons cut the clicked ones (cutters stay; holes appear).
  - BUF «Буфер»: distance in metres on the ground (minus — inward), result in the polygon layer with «Буфер, м».
  - MA «Копировать свойства»: attributes of a sample object to clicked objects (like MATCHPROP).
  - DIV «Поделить» / ME «Разметить»: points along a line or contour into «Точки» (N parts / every d m), numbered.
  - SS «Выбрать подобные»: the same layer and the same category value (or REDLN97 linetype).
  - e2e +5 steps (SPL 400 + 400 m², UNI 800, BUF 2 m ≈ 1053 m², SU hole, DIV 4 points). **Pitfall in the test:** REC repeats
    until Esc, so typed commands went into its input.

- **2026-09-24, ГРАДО 2 v0.42.0: guest parking of ИЖС and blocked houses by 945-ПП (owner: «все по 945»).** Permanent places
  1,6 per house (Прил. 5 п. 2, coefficient C for ИЖС and blocked houses; a blocked unit is a house) stay on the own plot (the
  outbuilding/garage); guest places = 10 % of them, rounded up (п. 6.2.3.2), per проезд for the houses facing it (edge rows go
  to the nearest проезд). They are 2,5 m lay-bys along the проезд, 6 m per place, in groups at most 400 m apart so that no house
  is farther than 200 m (п. 6.1.2.5.2); a local street allows guest places on the adjacent side (Прил. 7). What does not fit is
  said in the node note. The accepted streets layer is styled by «Вид» and carries «Мест» and «Норма». Node info counts plots
  without outbuildings and shows «гостевых мест N (945-ПП)». Test site: ИЖС 49 places for 289 houses, blocked 173.
  e2e +1 check. The ТЭП «Гостевые парковки» still comes from the preset formula (flat area / 50 / 2,1 × 0,8 × 10 %).

- **2026-09-24, ГРАДО 2 v0.41.0: UX queue — owner's decisions and the rest.**
  - ТЭП: «Площадь сохранения и ограничений» = ЗОУИТ and other bans ∪ footprints of kept buildings (owner, 24.09.2026); density
    from SPP is new SPP over the land that is really free.
  - Insolation: schools and kindergartens (Назначение/Тип/Наименование: школа, гимназия, лицей, детский сад, ясли, OSM school,
    kindergarten) are protected like housing. Relief: `groundAt` interpolates «Рельеф: горизонтали» (6 nearest vertices, IDW,
    50 m index); prisms carry `g` and `h = g + height`, front points sit at `g + z`, the ceiling is computed in absolute marks
    and each cell subtracts its own ground. Without relief the ground is flat as before. insol tests +2.
    **Pitfall:** `const GROUND` already existed in app.js (ground colours); all scripts share one global scope — the relief
    cache is `RELIEF_G`. Check top-level names across scripts before adding one.
  - DWG through the free ODA File Converter: import (.dwg → DXF → import_dxf) and export (grado2.dwg next to grado2.dxf);
    without the converter a clear message. Not verified with a real converter here.
  - Windows dock from the keyboard: Tab to a header, Alt+← → ↓ / Alt+↑. F1 text updated. UX check: moving the header to another zone dropped keyboard focus — it is restored at once.
  - UX check (screenshots): ИЖС sketch shows outbuildings at the back of plots; one-building «Объём» shadow follows the shape.
  - ИЖС: an outbuilding 4 × 6 m at the back of each plot (ground layer, not in SPP). Blocked rows start at half the leftover of
    a dry run, so the strip is centred; plot clipping is memoised between passes. e2e: ИЖС check counts outbuildings.

- **2026-09-24, ГРАДО 2 v0.40.0: UX queue — audit leftovers.** «Объём» shadows are the footprint plus one quad per edge,
  filled once (nonzero, quads oriented one way) — courtyards and L/C buildings no longer darken the whole yard. The solar
  ceiling protects neighbours within height/tan 10° (tallest ПЗЗ height in the boundary, 75 m without ПЗЗ), 200…600 m; the log
  says that houses beyond the 60 m download strip are not loaded. TR preview on closed contours shows exactly what G.trim
  removes (two cuts needed, wrapping piece in two lines). Yandex polygons reaching the edge of the fetched tiles carry
  `grado_clip` (frame in the same rounded coordinates, so the cut is not stroked) and «Площадь: только в области выгрузки».
  «Показатели» says «маршрут по улицам считается…» while `/api/rail_route` runs. DXF: a dimension's value is written as TEXT
  over the dimension line. «Моя раскладка» remembers window sizes in zones (`_sz`). Tests: DXF +1 check.
  - **Bug found in the UX check:** graph «Слой» (and «Объединить») set `properties = {_src}` on the union result, and the union
    of one object is that object itself — a layer with one building lost its «Этажность», so ТЭП and «Объём» took it as
    1 floor. The result is now a copy.

- **2026-09-24, ГРАДО 2 v0.39.0: whole-program audit fixed (45 confirmed findings plus most unverified ones).** Audit by
  parallel reviewers (backend, connectors, ТЭП, front, security, data), verified 3 votes each; fixed by hand in four commits.
  - Import/export: DXF LINE no longer crashes, bulges flattened (5 cm), Z ignored, points/«Текст» exported as POINT/TEXT;
    SHP Cyrillic field names, deleted records, NULL dates, upper-case extensions; foreign projections (UTM, ГК, МСК-50) refused
    instead of landing abroad; cp866/UTF-8 zip names; same stems from two folders kept; repeated import makes a new layer.
  - Connectors: ОГД zip validated before caching, dBASE 254-byte text restored from the portal GeoJSON by `orbis_id`, NSPD
    failure raises (no empty layer wiping edits), contours at integer heights, Overpass «runtime error» is a failure, OSM
    courtyard buildings, Yandex tiles decoded before caching.
  - Server: zone 2 for Бирюлёво/Бутово (ё, word order), place caches expire (90 days), stale ФГИС ТП catalog as fallback, launcher
    stamp includes core, clamps; preset: ИЖС SPP not cut by the housing share, plots ≤ residential territory; legend fits the sheet.
  - Front: downloads and variant search bound to their project (`PROJ_EPOCH`), empty re-download keeps edits, ФГИС ТП reload
    merges, «Показатели» by the accepted sketch layer, restored unsaved autosave asks before «Новый»/«Открыть», XSS sinks escaped,
    litegraph demo nodes unregistered, CAD Backspace/grip/TR/J/AR fixes, annotation layers not used for drawing, constraints
    step/cache/sampling/rounding fixes.
  - **Pitfall (twice in this batch):** inserting a `//` comment into a one-line statement comments out the rest of the line —
    use `/* */` in edits of long lines, and run `node --check` right after each edit.
  - Not fixed (UX queue): kept buildings in the restricted area (owner's decision), 3D shadow hull, 200 m protection radius, TR
    preview on closed contours, partial Yandex areas.
  - UX audit: a Russian reason of a refused request (e.g. a UTM file) reaches the toast without the English «bad request:» prefix.
  - Token budget: CLAUDE.md files cut from ~440 KB to ~3 KB per turn (`claudeMdExcludes` for the taiLink file).

- **2026-09-24, ГРАДО 2 v0.38.0: UX queue, batch 4 (ТЭП and analysis).** Density target from ПЗЗ (`pzzTarget`: subzones with a
  number inside the boundary, area-weighted, 0 counts) — set on the ПЗЗ download while the slider is the untouched 25,
  «взять цель» in «Показатели». K1 by walking route: `server.rail_route` — Overpass `way(around:2400)` walkable highways
  (cached `~/.grado2/cache/place/walk_*.json.gz`), graph on shared OSM nodes, Dijkstra from the territory centre to the nearest
  entrance/station (snap ≤ 150 m); `/api/rail_route` runs after `/api/place`, K1 follows it while «по району» is on.
  Measured at Владыкино: 323 m by streets vs 280 m straight (first call ~2 min of Overpass, then from disk). Four points inside
  the boundary are checked for other districts → a note. «Радиусы обслуживания»: Moscow 2151-ПП / 2152-ПП options with the radius
  by okrug (ЦАО school «в границах ЦАО» — no radius). Tests: server +1 (route 700 m around a block vs 500 m straight).

- **2026-09-24, ГРАДО 2 v0.37.0: UX queue, batch 3 (drawing).** New commands in `web/cad.js`: REC options «Сопряжение»/«Фаска»
  (remembered like AutoCAD, `RECC`; `G.filletAll`/`chamferAll` on the rectangle), EL (`G.ellipsePts`, cadcore +2 checks),
  H/BH (click inside a contour → the smallest polygon or closed line around the point is copied into layer «Штриховка»;
  «Выбрать объекты»), DIM/DAL/DLI (aligned / horizontal / vertical; a line выносная–размерная–выносная in «Размеры», value in
  «Размер» shown as the layer label), T/DT/TEXT (point + text typed into the command box, need "text", layer «Надписи»).
  Annotation layers are created on demand without changing the current layer (`annoLayer`). AR marks copies `_arr {id, i}`
  and the sources `_arr {…params, src}` (edit() now takes `props`); AE (ARRAYEDIT) picks a member, asks the same numbers with
  the old values and rebuilds the copies (copyFeat drops `_arr` for ordinary copies). F2 — command history of the session
  (`.cmdhist`). Osnap «Параллельно»: dwell 0.4 s on a segment captures its direction, then a tracking ray from the last
  point runs parallel to it. Ribbon: ellipse in «Рисование», annotation tools in one «▾» button, AE in the «▾» of editing;
  group captions hide below 1560 px and the layer select narrows below 1380 px — one ribbon row from 1280 to 1920 px.
  - **Point labels were hidden** whenever the label's box touched its own marker (the marker is a declutter obstacle): the
    offset now follows marker size and font size.
  - **Pitfall:** `forEachFeatureIntersectingExtent` with a point extent does not return a closed LineString around the
    point (the line does not touch it) — contour lookup uses `forEachFeatureInExtent` (bbox).
  - e2e +9 steps (REC R3 area, EL area, DIM 40,00, TEXT, H, AR mark, AE 4 × 2 → 7 copies, F2, «Параллельно»).

- **2026-09-24, ГРАДО 2 v0.36.0: UX queue, batch 2 (speed).** `projectJSON` (project.js) writes each layer's `fc`/`original` from a
  WeakMap cache keyed by the object itself (the lazy `fc` getter returns a new object after an edit, the original never
  changes): autosave of an unchanged 100 000-object project 111 → 5 ms, output identical to `JSON.stringify` (checked without
  `saved_at`). `ruleCount` caches «Правила» counts by `DATA.rev` + rules. `checkNorms`: evaluation in chunks of 300 points with
  yields, the neighbours' state before development cached by kept buildings + parameters (a re-check after an edit skips it),
  `checkGen` interrupts a stale run («перепроверка прервана» is silent).

- **2026-09-24, ГРАДО 2 v0.35.0: UX queue, batch 1 (small items).**
  - Old ОГД/ЕГКО layers: `_layer` marks gisogd/egko layers `shp: true`, the project keeps it; opening a project saved by ≤ 0.31
    lists such layers without the mark (`STALE_OGD`) — toast + a «Данные» note with «Выгрузить заново» (checks them, loads).
  - DXF: export writes the header custom property `GRADO_CRS=MSK`; import (`written_system`) takes the file's own system over
    the «Файлы в метрах» choice; an older ГРАДО 2 DXF ($LASTSAVEDBY ezdxf + «red_lns.shx» in the file, no mark) is read as ОГД.
    **Pitfall:** ezdxf does not list shape-file styles in `doc.styles` after reading — the name is looked up in the bytes.
  - ЕГКО clip: a clipped polygon carries `grado_clip` (the query box) → `_clip`; the map strokes it through `frameless`
    (a geometry function dropping ring edges that lie on the frame — cut points sit exactly on it, so equality is exact).
  - Status line «портал готовит файл…» while 0 bytes arrived; the re-download toast counts unchanged layers instead of listing
    them; an empty first download adds no layer and says «Нет объектов в области».
  - v0.33 Yandex styles left untouched (width 0) get the outline on re-download. Menus (`.menu`) sit above toasts (85 > 80).
  - Sketch: touching spots of sections dropped under a low ceiling merge (`unionAll`) into kind «свет соседям» (yellow, with
    «Причина» in the accepted layer); node line shortened. ARRAY/typed box opens mid-map without a mouse position.
  - «Показатели»: «сбросить тип и проценты» (преобразование, 6 %, 25 %).
  - Tests: DXF +1, e2e adapted (merged yards ≤ dropped sections); headless check of the stale note and the frame outline.

- **2026-09-24, ГРАДО 2 v0.34.0: Yandex pieces dissolved along tile edges (no shapely).** All pieces of an object go to one
  integer grid of the zoom (`GX = x·8192 + 4096 + px`, 4095 → 4096; a tile edge is a multiple of 8192). Polygon rings are
  oriented (outer positive, holes negative); edges lying on a tile edge are summed per edge line as signed intervals, and only
  what is covered in one direction stays (neighbouring pieces run opposite ways there), then rings are walked from the edges
  (at a touching vertex the leftmost turn keeps contours apart). The cancellation keeps the area exactly — if not, the object
  stays as pieces. Then steps of 1–2 cells (≈2 cm) on the edge line, where neighbouring tiles rounded the cut point
  differently, are removed with collinear vertices. Holes are assigned to the outer that contains them (a courtyard cut by an
  edge comes back as a hole). Lines: pieces are joined end to start on an edge within 2 cells.
  - Checked on 37.576 55.843 37.594 55.852 against yaexport.py (shapely union): parts per id equal for all 321 building ids and
    157 road-surface ids, holes 1/1 and 17/17, all 405 buildings valid in shapely, area sums equal (< 0.001 %); lines 3175
    pieces → 1749, 0 unjoined ends on edges; tiles + dissolve of the area 0.22 s.
  - Buildings and road surfaces have their thin outline back (no seams). Tests: +7 (`TestDissolve`, part counts from yaexport in
    `yaexport_ref.json`).

- **2026-09-24, ГРАДО 2 v0.33.1: UX audit of v0.33.0.** A first download with no objects in the area (e.g. «Вода (Яндекс)» at
  Владыкино) no longer adds an empty layer to the tree; the load toast says «Нет объектов в области: …». Yandex road axes are
  one calm tone instead of random colours by Yandex classes («4_link», «8») that mean nothing to the owner.

- **2026-09-24, ГРАДО 2 v0.33.0: Яндекс Карты (векторные тайлы vmap3) — new source group, nine layers, stdlib only.**
  - Connector `core/connectors/grado_connectors/yandex_vmap.py` (decoder ported from the owner's `~/yandex-hdroads`): tiles z18
    from `core-renderer-tiles.maps.yandex.net/vmap3` (User-Agent + Referer yandex.ru/maps, no key), disk cache
    `~/.grado2/cache/yandex/{z}_{x}_{y}.pbf` (TTL 30 days), 3 threads, 0.3 s pause after each downloaded tile, 4 attempts
    with growing pauses, SSL as in gisogd_api. Tile grid EPSG:3395 (NOT 3857), inverse ellipsoidal Mercator by iteration;
    grid 8192 centred, y down, 4095 on the right/bottom edge = 4096. Service layers are never exported (SKIP).
  - **The reference decoder had a bug:** attribute value type 2 is a zigzag signed integer. Proof: building `feature_id` equals
    the object id only after decoding (287 of 376), all raw values even, `z_level` −1 appears. yaexport.py reports heights
    doubled (median 1.7 × ЕГКО h; decoded 0.85 — Yandex height is floors × 3 m).
  - **An id groups the parts of a complex** (towers + stylobate, each with its own height, type and feature_id): an object is
    the pieces of one id with equal attributes (as yaexport.py does); a part's key gets `:feature_id`. Pieces become one
    MultiPolygon / MultiLineString (no shapely); «Площадь, м²» / «Длина, м» on the ground = sum of pieces / Mercator scale.
    Objects are kept when their bbox touches the request; pieces beyond the covering tiles are cut at the tile edge.
  - Server: `yandex.hd_roads` (hd_road_surface; «Тип», «Конструкция», «Уровень»), `yandex.buildings` («Высота, м»,
    «Назначение»), `yandex.roads`, `yandex.road_edges`, `yandex.landuse`, `yandex.green` (vegetation, vegetation_planned,
    hd_road_vegetation), `yandex.water` (hydro_a + hydro_l), `yandex.parking`, `yandex.transport` (transport_p +
    transport_way); all attributes kept; LIMIT 4 km²; all Yandex keys in one job (tiles fetched once); progress «тайлы N из M».
    No POI or organisations (owner's decision). Not in CHECKED by default; group title in «Данные» says «Яндекс Карты, для
    анализа и эскиза; в сдаваемые материалы не включать».
  - Front: styles after OSM in PREFERRED; area layers without outline — each tile piece would draw a seam across the building
    (checked by screenshot); a mixed layer draws points as points and lines in a polygon layer in the outline colour.
  - Checked: area 37.576 55.843 37.594 55.852 via /api/fetch against yaexport.py (EPSG:4326): buildings 345 (270 ids),
    hd_road_surface 144, road 1289 (1273 ids) — equal; area/length sums differ < 0.001 %; tiles byte-identical to the
    reference cache. WGS84 of tile points against pyproj < 1 cm (test). First download 182 tiles 23.4 s, repeat 0.21 s.
    Shift of Yandex buildings (median of centroids): to OSM X +1.0 m Y +0.6 m, to ЕГРН X +4.3 m Y +3.9 m — source
    discrepancy, NOT compensated.
  - Tests: connectors +16 (`test_yandex_vmap.py`, fixtures: three z18 tiles + `yaexport_ref.json` from yaexport code and
    pyproj), server +2.

- **2026-09-23, ГРАДО 2 v0.32.0: coordinates as in the owner's QGIS («МСК»); ГИС ОГД and ЕГКО read from SHP.** Owner's scheme,
  not to be discussed or «calibrated»: two Moscow systems on one datum — «МСК (как в QGIS)» (`crs.MSK_PROJ4`, x_0 = y_0 = 0) and
  «система ГИС ОГД (Бессель со смещением)» (`OGD_PROJ4`, x_0 = 16.098, y_0 = 14.512); МСК = ОГД − `OGD_SHIFT` exactly.
  - `crs.py`: `MSK_PROJ4`, `OGD_SHIFT`, `msk_to_wgs84` / `wgs84_to_msk` / `ogd_to_msk` built on the ОГД pair plus the shift (no second
    copy of the formulas); `OGD_PROJ4`, `msk50_to_wgs84`, `wgs84_to_msk50` unchanged.
  - Everything the user sees, types and exports is МСК: `web/mggt.js` → `web/msk.js` (`X0 = Y0 = 0`, `window.MSK`), cad.js, layers.js
    (status bar «МСК X … Y …»), `dxf_io.py`, `print_io.py`; interface texts say «МСК», not «МГГТ». Project geometry stays WGS84 and
    does not move on the map; shown/typed/exported coordinates change by −16.098 m X, −14.512 m Y.
  - Import of local metres (`file_io.LOCAL`): МСК by default; a `.prj` with MOSCOW_BESSEL means ОГД; the «Данные» window has
    «Файлы в метрах: МСК (как в QGIS) / ГИС ОГД» for files without .prj (DXF, GeoJSON in metres); `/api/import/files` takes
    `local`, `/api/import/dxf?local=ogd`.
  - **The portal's GeoJSON export is ~7.7 m off** (median 7.66, p95 7.84 against its own SHP; ЕГКО the same, 7.74). `gisogd_api.py`
    now asks `format=shp` (zip: .shp/.dbf/.prj «Moscow_bessel»/.cpg UTF-8, native ОГД coordinates) and converts with
    `msk50_to_wgs84` through `shp_reader` (`iter_zip`, `iter_records`: records one by one, date fields as ISO). DBF truncates field
    names to 10 characters — `DBF_FULL_NAMES` restores the ones PRESENT uses. Cache names changed (`{code}.shp.gz`,
    `{code}.shp.lines.gz`, `base2.{code}.shp.grid`), so old GeoJSON caches are ignored (left on disk, not deleted: ~297 MB isogd,
    ~704 MB egko). All 41 SOURCES layers checked as SHP zips. ЕГКО downloads the zip to a temp file and streams records.
  - Checked: МСК against pyproj on 20 points max 0.74 mm; `msk.js` against PROJ < 1 mm; virtual1681 (591 884 vertices) WGS84
    against PROJ max 0.47 mm; DXF export equals native minus shift to 0.00 mm; status bar on an ОГД vertex X 7 112,69 Y 11 037,70
    = native 7112.692 / 11037.698 minus shift. ЕГКО virtual6 via SHP: first download 364 s (portal preparation most of it), peak
    173 MB, 428 buildings at Пушкинская (as before), grid 150 MB, repeat 0.03 s.
  - **Owner-visible consequences:** ОГД/ЕГКО layers in projects saved before v0.32 stay ~7.7 m off until re-downloaded («Данные» →
    tick the layer → «Загрузить»; edited objects keep their geometry). DXF written before v0.32 are in the ОГД system — import them
    with «ГИС ОГД».
  - Tests: connectors 70 (PROJ fixtures, SHP fixture `_shpfix.py`), grado2 44 with e2e.

- **2026-09-23, ГРАДО 2 v0.31.0: ЕГКО Москвы (картооснова ГИС ОГД, карта base2) — new source group, seven layers.**
  - Connector (`core/connectors/grado_connectors/gisogd_api.py`): `GisogdApi(map_name="base2", clip=True)`; `MAPS` holds both maps
    (the base2 catalog answers only with `?type=full&returnCss=0`). isogd is unchanged: same URLs, keys «код:id», slurp + `.lines.gz`.
    base2 streams: `_http_stream` (15 min socket timeout — the portal first assembles a big layer: gazons started after ~3–4 min,
    buildings after ~2 min) → incremental UTF-8 → `_FeatureStream` (C `raw_decode` per feature, waits for the next chunk on a
    split) → every feature goes to a grid on disk `~/.grado2/cache/egko/base2.<code>.grid/<ix>_<iy>.lines.gz` (0.01° cells by
    the south-west corner of its bbox; bigger than a cell → `big.lines.gz`), buffered ≤ 48 M chars then appended as gzip
    members; written to a `.part` folder and renamed. A query reads its cells plus the neighbours to the west/south and `big`.
    Keys «base2:код:id» (base2 codes are spelled like isogd codes). One lock per layer; TTL 30 days (`EGKO_TTL`).
  - `clip.py` (stdlib): polygons ring by ring (Sutherland–Hodgman; a ring wholly inside/outside is kept/dropped by its bbox
    first — the city-wide road polygon has thousands of block holes), lines by Liang–Barsky split into parts, points filtered.
    Applied only to egko.*.
  - Server: `egko.buildings` (virtual6/15/16/17 → «Состояние»), `egko.roads` (dorogi_pol), `egko.paths` (tropinki),
    `egko.green` (gazons, forest → «Вид»), `egko.water` (hidrograf), `egko.fences` (fence2k), `egko.addresses` (adres); limit
    25 km²; all egko keys run one after another in one job (portal and memory). PRESENT per layer; the portal's " " is empty.
    Building address is built like `full_addr` of «Адреса» («Научный проезд 20 стр.4», «… 11 к.1»; the строение prefix comes
    from `is_struct`, «стр.» or «соор.») — 156 of 159 addresses of the Пушкинская area match the address layer.
  - **Field h = height in metres** («Высота, м»): 244 buildings matched with ЕГРН «Этажность» at Пушкинская give
    h / floors median 4.11 m (quartiles 2.96–4.83; historic centre, high ceilings). «Этажность» is NOT derived from it.
  - Measured (first download, M-series Mac): virtual6 650 MB / 782 642 objects — 149 s (≈125 s portal preparation), peak
    RSS 471 MB, grid 170 MB in 4 296 files; gazons 1 295 MB / 915 090 — 233 s (≈180 s preparation), peak 143 MB, grid 389 MB;
    whole egko cache 704 MB. Repeat from cache: 0.02–0.4 s per layer.
  - Пушкинская (37.600, 55.760, 37.612, 55.766): 428 buildings (426 of virtual6, as the bbox selection gave: clipping keeps every
    object that really enters the box), roads 1 clipped piece 0.02 MB instead of 2 whole polygons 18 MB. In the app the
    territory is buffered by 60 m, so the same box shows 605 buildings.
  - UI: group «ЕГКО Москвы» with the warning about the first download; egko goes in its own `/api/fetch` request; progress
    for egko too («раскладка по сетке» stage). Default styles in the OSM/НСПД palette, places in `PREFERRED` next to analogues.
  - Tests: connectors +12 (`test_egko.py`), server +6.

- **2026-09-23, ГРАДО 2 v0.30.0: window layouts for tasks; a splitter between windows under the map.** The «Окна ▾» button is
  now always shown: above the windows that did not fit the header it lists «Раскладка окон» — «Существующее положение»
  (Данные left, Таблица below), «Ограничения и анализ» (Ограничения, Показатели right; Граф below), «Эскиз и варианты»
  (Эскиз, Показатели right; Варианты below), «Листы и альбом» (Виды left; Листы below) — and «Запомнить текущую…», which
  saves open windows with their zones as «Моя раскладка N» (× deletes; `WST.layouts`). `applyLayout` closes the other
  windows. Two windows side by side under the map share the width by a draggable border (`.dresv`, `WST[id].bw`); a tabbed
  side zone is resized as a whole (`--dzh`, `WST.zhl/zhr`). Menu icons are drawn after each render (the menu is rebuilt on
  open); the short polar label at ≤ 1180 px had lost to a later CSS rule. e2e +3 steps.

- **2026-09-23, ГРАДО 2 v0.29.1: layout audit (parallel reviewer, 17 findings) fixed.**
  - Several windows in one zone become tabs (`syncZones`): side zones always, the bottom zone when windows get < 340 px each;
    a tab drags out to float (`dragWin` shared by headers and tabs), × closes; crowded tabs keep only the icon. The layer
    tree and the style pane keep ≥ 150 px (docked windows were squeezing «Стиль» to 0 px). Windows with header controls
    («Объём») keep their header in a tab (`.hctl`).
  - ≤ 1000 px: windows meant for the side panels dock as tabs under the map (drawers must not cover the map); only one drawer
    is open at a time; crossing the width moves them back. Floating windows are re-clamped on resize; default positions are
    inside the map field, not over the side panels.
  - **The style pane's `.modes` class also matched the status-bar mode buttons** (grey box, border, 8 px margin — the buttons
    sat 2 px high and were clipped): renamed `.stmodes`.
  - «С чего начать» hides while a command runs (a click on the map under it hit «Чертить с нуля» and restarted PL).
  - Esc order: open menu → variant search → selection/tool → front floating window → «С чего начать».
  - Below 1080 px all window buttons move into «Окна ▾» with labels (icons alone were unreadable); status bar mode labels are
    shortened below 1180 px so the next-step hint keeps room; toasts sit over the map (above the bottom zone and command line).
  - Dark theme: graph menus, search box, map notes, variant thumbnails and the ТЭП warning colour use theme variables.
  - Rules: the field picker gets its own row; «Категории» picks a text field with 2–30 values by default; «в слой» empty text
    «новый слой» with the full name in its tooltip; «Объём» always shows the time. e2e +4 steps.

- **2026-09-23, ГРАДО 2 v0.29.0: windows dock into the workspace; layout defects from the owner's screenshots.** Owner: «значки
  скачут, нет отступов, кривая вёрстка; окно должно не прилипать, а встраиваться в панель; приветственное окно нельзя закрыть;
  эскиз строится без границы без ошибки; боковая панель неверно ведёт себя при сужении».
  - Docking (QGIS panels / AutoCAD palettes): three zones — under the layer tree (`#dzL`), under the properties pane (`#dzR`),
    under the map (`#dzB`, the map column is now `.center` = map + bottom zone). Drag a window header onto a side panel, the
    map's left/right edge or its bottom edge — a blue drop indicator shows where; release docks it (the section is moved into
    the zone, `.docked`: static, no shadow, no CSS resize), the map shrinks. Drag a docked header > 6 px — it floats again at
    its floating size. Double click on the header toggles. Side zone windows share the panel height (`flex-basis`, top edge
    resizes, `WST[id].dh`); bottom zone windows share the width, the zone height is dragged by its top edge (`WST.hb`).
    Defaults: Таблица, Варианты, Листы, Граф — bottom; Эскиз, Показатели, Ограничения — right; Данные, Виды — left; Проекты,
    Справка, Объём, Сравнение float. `WST[id].dock` (null = float); old `anchor` is read as a dock side.
    **Pitfall:** moving a section to another parent drops pointer capture — the header drag listens on `window`, not on the header.
  - **Narrow window (≤ 1000 px) drawers were 1 px wide:** an absolutely positioned grid item takes its grid area as the
    containing block, and the side columns are 0 there, so `width:min(300px,85%)` was 0. Drawers now span `grid-column:1/-1`.
  - Toolbar and status bar no longer shift: the «в слой» select has a fixed width (its text changed the ribbon length); the
    status bar layer name, scale and МГГТ coordinates have fixed widths with tabular digits; the polar button keeps its width.
  - Properties pane fits 220 px: style mode buttons are a wrapping grid, row labels shrink, fields may shrink. The attribute
    table's «только выбранные» checkbox was 160 px wide (the filter input rule hit it); window bars keep one line with «…».
  - «С чего начать» has a close button and closes on Esc (remembered: `grado2.start`); its actions are in F1.
  - «Построить эскиз» without a territory boundary does nothing and says so (toast + a warning line in «Эскиз»; the node says
    «нет границы территории»); an empty site says to check «Ограничения». «Объём» without a boundary shows an explanation
    instead of an empty grey canvas. e2e +6 steps.

- **2026-09-23, ГРАДО 2 v0.28.0 (Э10, owner's decision 3): buildings under a low solar ceiling are dropped when the density
  goal is met without them.** In «цели плотности» mode, after the water-fill, capped buildings (ceiling below the planned
  floors) are removed one by one from the lowest ceiling up while the rest still reach the goal (≥ 97 %); their footprints
  stay as «двор» plots with «Причина: низкий потолок: свет соседям». Urban blocks, blocked rows and ИЖС are not thinned
  (their buildings carry `grp`). The graph node and the «Эскиз» window say how many were dropped.
  - Water-fill fix: one common floor count was rounded, which at ~5 floors lost up to 10 % of the goal («цель не достигнута»
    at 14.1 of 15); now the largest buildings with headroom get one more floor until the goal is reached.
  - Test site: goal 25 — 86 sections instead of 103 at 24.6; goal 15 — 84 sections and 19 yards at 15.6; neighbours lose no
    insolation in both.
  - e2e: two tracking steps were timing-flaky under load (the check ran before the map handled the last mouse move; the
    first point of a line can also be acquired, as in AutoCAD) — they now wait for the state instead of a fixed pause.

- **2026-09-23, ГРАДО 2 v0.27.0: array preview, grips limit said aloud.** ARRAY shows its copies as ghosts from the first
  number on: rectangular copies at the current rows/columns/spacings, and the number being typed is applied live before Enter
  (`CMD.still(typedNum())`, drawn by `refresh()` without a mouse move; up to 400 ghost objects). Polar: before the centre is
  picked, copies turn around the cursor. A selection whose grips would exceed 3 000 now says so in the status bar
  («ручек было бы больше 3 000…») instead of showing nothing; `CAD.grips()` runs before `syncStatus()`. e2e +2 steps.
  **Note:** the in-app browser pane's «type» does not send keydown, so drawing by typed commands cannot be checked there —
  use the headless driver (`tests/e2e/driver.mjs`, `W=840 H=760`).

- **2026-09-23, ГРАДО 2 v0.26.0: ortho fixed, AutoCAD grips, narrow-window layout, command line.** Owner (screenshot at a
  ~840 px pane): «в орто линия получается под углом; уйма косяков в вёрстке; не получается выбрать вершину фигуры».
  - Ortho: tracking beat ortho — a tracking line gave a slanted segment. Now with ortho on the point stays on the X or Y axis
    from the last point and a tracking line only tells where on the axis to stop (AutoCAD behaviour); two-line tracking and
    «nearest» are off under ortho; osnap still wins.
  - Grips in selection mode: blue squares on vertices, triangles at segment midpoints of selected objects (up to 3 000).
    Click a grip, then click the new place, or drag it; snaps, tracking, ortho, typed @dx;dy / X;Y all work (command
    «grip»); a midpoint grip inserts a vertex; «У» or Delete removes the hot vertex (keeps ≥ 2 / 3 vertices). Closed rings keep
    the closing vertex in sync. OpenLayers Modify («Вершины») stays for bulk editing of a layer.
  - Narrow window (≤ 1000 px): the ribbon wraps into two rows at group boundaries (grid row `auto`); header window labels hide
    only below 1080 px; the layer and properties panels become drawers over the map (closed at start, opened from «Окна ▾»),
    instead of disappearing below 900 px; the project button stays; windows are placed below the ribbon (`mapBox().top`).
  - Command line at the bottom of the map: command name, prompt, clickable option chips, command messages (`note()` —
    errors were visible only in the truncated status bar); toasts move above it; typology segments fill the last row.
  - Testing note: the owner's pane was ~840 CSS px (screenshot at 1.4×); audit at that width, not only 1280.
  - e2e +2 steps: ortho with tracking stays horizontal; grip + @0;-5 moves a vertex exactly.

- **2026-09-23, ГРАДО 2 v0.25.0: more AutoCAD commands.** PLINE option «Дуга (Д)» / «Линейный (Л)»: arc segments tangent to
  the previous segment (`CG.tangentArc`, `arcEndDir`), undo removes a whole arc step. CHA — chamfer (two lengths, «Полилиния» for
  all corners). AR — array: rectangular (columns, rows, spacings, defaults 1.5 × selection size) and polar (centre, count,
  fill angle, rotate items). S — stretch by a crossing window in МГГТ axes: vertices inside move, objects fully inside move
  whole. LEN — lengthen by a delta (minus shortens across vertices) or to a total length. Polar tracking can count angles from
  the last segment (polar menu). Grips show the adjacent segment lengths and МГГТ coordinates while a vertex is dragged.
  Rare Modify commands (chamfer, break, join, explode, lengthen, erase) sit in a «▾» menu so the ribbon fits 1280 px.
  cadcore checks 40, e2e +5 steps.

- **2026-09-23, ГРАДО 2 v0.24.0: drawing rebuilt after AutoCAD.** Owner: «в прошлой версии черчение было лучше, ориентируйся
  на автокад (пунктирные продолжающие линии и пр), мало инструментов, значок линии похож на дугу — скопируй инструменты из
  автокад». OpenLayers Draw/Translate are gone from drawing; OpenLayers only shows. Grips («Вершины») stay on OL Modify.
  - `web/cadcore.js` (`CG`, no DOM, 33 checks in `tests/cadcore_test.js` via `test_cadcore.py`): intersections, foot,
    tangents, circle/arc by three points, regular polygon, offset (miter), cuts along a chain, trim (open and closed), break,
    extend, fillet of a corner and of all corners, join by common ends, move/rotate/scale/mirror.
  - `web/cad.js` rewritten as a command engine: commands by ribbon button or AutoCAD alias typed + Enter/Space (layout
    independent by `e.code`; autocomplete list): L, PL, C, A, REC, POL, PO, M, CO/CP, RO, SC, MI, O, TR, EX, F, BR, J, X, E,
    DI, AA, BO. Enter/Space/right click finish a step; Enter/Space with no command repeats the last one; Backspace removes
    the last point; Esc cancels. Options in brackets are typed as letters (Russian, or the same key in the Latin layout,
    or the AutoCAD English letter). Pick-first or command-first selection (Shift+frame works in the selection step).
  - Own snapping (F3, menu of modes: endpoint, midpoint, center, quadrant, intersection, extension, perpendicular,
    tangent, nearest) with AutoCAD markers; object tracking (F11): hover a snap point 0.38 s → green «+», then dotted
    alignment lines (0/90° or polar angles) and extension lines, the crossing of two lines snaps; polar tracking (F10, step
    90/45/30/15/10/5°) with a dotted ray; ortho (F8, МГГТ axes); dynamic input (F12). Snap search reads only features in
    a 10 px box (≤ 300) and converts only nearby vertices to МГГТ.
  - Circles and arcs keep `_cad` {t, c, r, a0, sw} in МГГТ (hidden field) for center/quadrant/tangent snaps and exact offset;
    transforms update it; grips editing drops it. Closed figures go to the current polygon layer (in a line layer — as a
    closed line); open ones to lines. Trim/extend/break cut in map coordinates (Mercator keeps angles; < 1 cm over 1 km),
    so untouched vertices stay bit-exact; trimmed pieces become separate objects with the same attributes.
  - Ribbon: own SVG icons (sprite `#ci-*` in index.html, grips drawn in the accent colour); status bar mode buttons.
  - **Pitfalls:** OpenLayers fires `dblclick` for any two clicks within 250 ms, wherever they are — fast vertices ended the
    polyline; the engine detects its own double click (same spot, < 0.4 s). `RegularShape` in OL 10 has no `radius1` —
    crosses drawn with it were invisible. A command object replaced after the selection step must become `CMD` itself;
    merging it into the old object left closures pointing to the inner object, so commands never finished.
  - e2e: A/B adapted (Space repeats PL for the second polygon), +8 steps: TR, EX, O, F R=3, RO 90 and Ctrl+Z, tracking line.

- **2026-09-23, ГРАДО 2 v0.23.0: precise drawing like AutoCAD; server listen queue.** Owner: «улучши элементы черчения,
  сделай их понятнее и точнее для черчения».
  - `web/mggt.js`: the core МГГТ transform (`crs.py` msk50 ↔ WGS84) ported one to one; `tests/test_mggt.py` checks it against
    the core (< 1 mm). All drawing lengths, angles and areas are in МГГТ — the system of the DXF and sheets (X east, Y north,
    angle from east counter-clockwise). Status bar shows МГГТ X/Y (WGS84 in its tooltip).
  - `web/cad.js` (IIFE, `window.CAD`), wired from `setTool`: a tooltip at the cursor with the current segment length and
    angle, total length or area, and the snap kind; typed input while drawing — a digit, «@» or «-» opens a box at the
    cursor: `25` (length along the cursor), `25<90` (length and angle), `@dx;dy`, `X;Y` (МГГТ, also the first point and the
    point tool); Enter finishes a line/polygon; ortho (F8, toolbar «орто», Shift held) keeps segments along or across the
    previous one (the first along the axes; snap still wins, as osnap over ortho in AutoCAD). The rectangle is built along the
    МГГТ axes (`CAD.boxM`), so it is square in the DXF. Snaps got midpoints (zero-length segments from custom `segmenters`),
    intersections (`intersection: true`) and a marker: square vertex, triangle midpoint, cross intersection, diamond on a line.
  - **Pitfall:** OpenLayers' polygon sketch ring is `[v0, cursor]` after the first click and `[v0, …, cursor, v0]` later — the
    closing point appears only from the second vertex (`openRing`). The Draw default `condition` ignores Shift clicks and
    Shift+drag is freehand: both are switched off so Shift can be the temporary ortho.
  - **Server bug found by the headless runs:** `ThreadingHTTPServer` has a listen queue of 5; the ~15 parallel script requests
    on start sometimes got «connection refused» and the page came up without app.js or layers.js (3 of 225 parallel curls
    failed). `Server.request_queue_size = 128`: 0 of 450 fail. **Backend change: the owner must restart server.py.**
  - e2e +6 steps (typed polygon 40×25 m to a millimetre, ortho angles, rectangle @30;20 on МГГТ axes, point by МГГТ
    coordinates, tooltip and vertex snap, МГГТ in the status bar).

- **2026-09-23, ГРАДО 2 v0.22.0: acceptance run Э8 on ТиНАО; Genplan nature zones become a ban.** Owner decisions of the
  day: push to GitHub (private), rounding as implemented, drop buildings under a low ceiling (Э10), no DWG, old studio /
  wizard / calc-web closed (launchers and `windows-release.yml` removed), ОВЗ places inside the norm, ВРИ cost postponed —
  recorded in `docs/grado2-plan.md`. `main` pushed (69 commits were local only); `grado2-release.yml` run on GitHub green for
  tests, Windows installer and macOS DMG. ТиНАО site (Краснопахорский, 44 ha): whole chain to PDF + DXF works, 24 s of
  program time on warm caches. New constraint «Запрет: природные зоны Генплана» (`CK.gp`, both Genplan layers; natural,
  green, park, ООПТ; «природно-жилая» is allowed). **Pitfall:** saved `grado2.cons` replaced the whole `use` object, so a new
  switch came in as off for existing users — `use` is now merged key by key.
  **Pitfall:** `.claude/launch.json` of the repo points `grado2-test` to the main checkout; for a worktree session it is
  edited locally and marked `git update-index --skip-worktree` — do not commit it.

- **2026-09-23, ГРАДО 2 v0.21.0: ТЭП по методике «Калькулятор 2.0» (genplan.tech/calc) с московскими нормами.**
  Owner sent the calculator's methodological reference and the rounding rule: math rounding to 3 decimals (SPP to 2),
  people and parking places always up to a whole number.
  - New preset `core/compute/grado_compute/presets/moscow_calc2.json` (ГРАДО 2 only; `moscow_krt.json` stays for the studio,
    wizard and calc-web). Chain: СПП → жилая/нежилая, МКД/ИЖС, нежилая часть МКД 6 % → НП ×0.9 → квартиры ×0.65 → население
    ceil(S/33) (ИЖС and blocked S/50) → квартиры ceil(pop/2.1) → ДОО/школы by zone, поликлиники, спорт, обслуживание, машино-места
    (945-ПП: постоянные S/(33×2.1)×0.8 without K1/K2, гостевые 10 %, приобъектные ×K1×K2, остановка with the 4-place cap for
    built-in premises), озеленение by territory mode, баланс.
  - Engine: `round` is now half-up (`expressions.round_half_up`, Decimal; Python round is banker's) and display uses it;
    `results()` returns each metric's `precision`; new `div(a, b)` because `where()` evaluates both branches.
  - Verified against the calculator's own output for Якиманка 15 ha (`core/compute/tests/fixtures/calc2_yakimanka_15ha.json`):
    6610 people, 3148 flats, parking 2804/2519/252/33, stop 14, ДОО 291, школы 595 — all equal.
    The calculator shows service areas rounded up (0.794); ГРАДО 2 keeps math rounding (0.793) by the owner's rule.
  - District parameters: `regulations/moscow_districts.json` (2151-ПП zones for 132 districts, 945-ПП K2 incl. 11 districts
    split by ТТК, ТТК hull from OSM). `/api/place` finds the district of the territory centre via Overpass `is_in` (cached in
    `~/.grado2/cache/place`), plus rail stations within 3 km for K1 (straight distance × 1.3 — an estimate).
  - «Показатели» window: block «Территория расчёта» (district, zone, K1, K2, ТиНАО, territory mode, nonresidential part of
    МКД, unbuilt share); a manual change turns off «по району», the button returns it. Values are shown with their precision.
  - Not done: ВРИ change cost and social compensation (P, Kp, УПКС missing), placement of social objects, population by flat
    count, parking by flat mix (АГР).

- **2026-09-23: Moscow НГП for ТЭП extracted — `docs/standards/moscow-ngp/`.** Owner sent 945-ПП (transport, parking), 2150-ПП
  (health), 2151-ПП (education), 2152-ПП (retail, services, residential territories) as RTF. MarkItDown does not read RTF
  (it passed the raw RTF through); conversion is `textutil -convert html` then `markitdown` (tables kept). Four parallel
  reviewers extracted every calculation rule with clause numbers (`*-алгоритмы.md`); the parking formulas of 945-ПП are images
  in the original — pulled out of the RTF (`\pngblip` hex) into `945-формулы/` and checked by eye: Nп = S/(S₁×2,1)×D, D = 0,8;
  Nв = X/X₂×K1×K2; Nк = S/S₁. `README.md` holds the calculation chain, the norms and a check of the ТЭП preset:
  **errors in `moscow_krt.json`: residents' parking is population × 257/1000 × K1 × K2, the decree gives 381 per 1000 and no
  K1/K2 (K1, K2 are for visitor parking at non-residential objects); reconstruction playgrounds use the low-rise complex rows
  (0,5 + 0,1) instead of 1,5 m²/person; ИЖС/blocked population must use 50 m²/person.** Missing: catering 120, culture 150,
  city services 90 per 1000; additional education 6/8/4; ОВЗ 5 places; ОТОП 0,7; visitor and stop parking; land plots.
  The preset is not changed yet — waiting for the owner.

- **2026-09-23, ГРАДО 2 v0.20.1: UX audit of v0.20.0.** The «квартал, м» slider went down to 60 m while a 16 m section
  depth needs ≥ 65 m (two sections + 20 m courtyard, short side 0.8) — the slider minimum now follows the section width.

- **2026-09-23, ГРАДО 2 v0.20.0: new typologies on a real site (Хорошёво with ЕГРН, OSM, ЗОУИТ, ПЗЗ, constraints).**
  Buildable spot 13.2 ha in 6 irregular parts. Found and fixed:
  - Urban blocks: no 110 m block fitted whole, and the fallback «perimeter of the part» wrapped ribbons around existing
    houses; streets were drawn with no blocks. Now `cutBlock` takes the grid cell ∩ site when ≥ 60 % of a block, runs the
    sections along the outer contour only (no ribbons around kept houses), cuts the front into 45 m sections, and places the
    block only with a courtyard ≥ 20 % and ≥ 600 m²; streets only between placed blocks (and crossings); the too-small-block
    note says the minimum («нужно от 65 м» for 16 m depth). Variants try blocks of 80 and 110 m. Result: 80–90 m blocks give
    5–6 blocks, 18–24 sections.
  - ИЖС / blocked: plots clipped by the boundary are accepted when ≥ 70 % / 60 % remain and the house fits (`clipped`) — use of
    the site 30 → 45 %, ИЖС 33 → 55 houses, blocked 32 → 45 rows. Blocked row search caches unit plots (1.8 → 1.1 s).
  - Node info notes (`out.note`) survive `generate`.

- **2026-09-23, ГРАДО 2 v0.19.1: UX audit of v0.19.0.** After a typology click the panel said «Корпусов: 130» while the
  map had 300 — the panel was drawn before the recompute; now recompute first. The typology hint described all eight
  typologies in five lines; now one line about the selected one (`TYP_HINT`).

- **2026-09-23, ГРАДО 2 v0.19.0: new typologies — ИЖС, «Блокированные», «Урбан-блоки».** Owner: «проработай генерацию ижс,
  блокированных домов и урбан блоков».
  - `place()` returns buildings plus `out.plots` (участки, дворы) and `out.streets` (проезды, улицы); `generate` keeps them.
    Buildings carry `grp` (one house / one blocked row / one urban block) and low-rise ones `maxF: 3`, `minF: 1`.
  - ИЖС: strips «plot row — plot row — 12 m проезд», plots back to back, facing their проезд (edge rows face the site edge);
    plot area from the new widget «участок, соток» (4–20, frontage √(area/1.6), 18–40 m); house ≤ 12×12 m, 5 m from the
    проезд, ≥ 3 m from neighbours; ≤ 3 floors (ГрК РФ ст. 1 п. 39).
  - Блокированные: unit 7 m, depth = «ширина корпуса» clamped 10–14 m, front yard 5 m, garden 12 m (24 m between rear
    facades ≥ 15 m for 2–3 floors), up to 6 units per row (ГрК ст. 49 ч. 2 п. 2 allows 10), 10 m between rows; one plot per
    unit; ≤ 3 floors.
  - Урбан-блоки: grid of blocks «квартал, м» × 0.8 (new widget, 60–200) with 20 m streets; perimeter sections of depth
    «ширина корпуса», continuous street front («1 этаж: нежилой, на улицу»), north corners ×1.4 floors, the side facing
    south ×0.6 (its corners at the base height), 12 m passage in the east/west sides, courtyard as a plot. **First version
    put the accents on all four corners — the check found 48 east/west sections below 50 % insolated facades; with accents
    only on the north corners: 0.** A part too small for a block gets a perimeter.
  - Insolation (`insol.js` `frontPoints`): points on a wall shared with another building (sections of a block, blocked
    houses, fire walls in ЕГРН) are dropped — they sat inside the neighbour and counted as shaded facades.
  - Norms check skips the 6 m fire gap between buildings of the same `grp` (the baked layer keeps it as «Блок»).
  - Panel: controls depend on the typology (plot size only for ИЖС, block size only for urban blocks, «Глубина дома» for
    blocked, no «разрыв/высота» for these three); floors 1–3 for low-rise; switching between low-rise and high-rise sets
    2 or 12 floors. Variant search adds urban blocks always and low-rise only when the target density ≤ 10.
  - Preview layer «Участки и улицы эскиза»; «Принять в проект» makes a group «Эскиз: …» with the buildings, «участки и
    дворы» and «улицы и проезды» layers (buildings on top). 3D ignores the plot and street layers. Node info in Russian
    plural forms (`plural`).
  - Example site: ИЖС 378 houses on 10-sotka plots, 2.4 тыс. м²/га; blocked 234 rows / 1404 units, 9.0; urban blocks at 8 floors
    300 sections in 30 blocks, 25.7 — all three «нарушений нет». e2e +3 steps.

- **2026-09-23, ГРАДО 2 v0.18.2: v0.18.1 shipped a syntax error in app.js** — a `//` comment placed inside a one-line object
  literal commented out the rest of the line («Unexpected token ':'»), the page did not start. The commit ran in parallel with
  the `node --check` that caught it. **Rule: commit only after the syntax check and tests of that exact tree have passed —
  never in the same parallel batch.** Fixed; graph opens at 0.8, «Весь граф» fits at 0.6; all tests and scenarios green.

- **2026-09-23, ГРАДО 2 v0.18.1: UX audit of v0.18.0.** The overwrite confirmation carried over to another project (asked
  for one, «Новый», then the same name saved without asking) — `clearProject` resets it. Save toast shows the folder name, not
  the full path. The OSM-fallback note in the graph node was cut and hidden under the next node: shorter text, and the default
  graph's left column is spaced (no node overlaps, checked). «Весь граф» now works, so the first opening fitted the graph at
  0.6 — too small to read; the automatic fit stops at 0.8, the button still fits everything.

- **2026-09-23, ГРАДО 2 v0.18.0: weak-point audit (three parallel reviewers) and fixes.** Owner: «определи слабые места и исправь».
  **Server (apps/grado2):**
  - **Any web page could overwrite projects** (no Host/Origin check, body parsed as JSON whatever the Content-Type — a
    `no-cors` text/plain POST from another site replaced a project; DNS rebinding could read them). `Handler._foreign`: Host
    must be `127.0.0.1|localhost|[::1]:<port>`, a present Origin must be the app's own → 403 for GET/HEAD/POST.
  - **Two saves at once corrupted the file** (shared `.tmp`, truncating write: 36 of 200 runs left invalid JSON). `atomic_write`
    (mkstemp beside + `os.replace`) + `_SAVE_LOCK`; the same for the ФГИС ТП catalog (a half-written one broke search for
    a week with no response — now it is deleted and downloaded again, and any GET error answers 500 with the reason).
  - Caches: the OSM cache lock was per request (new connector each time) → one lock per folder, unique file names, orphans
    evicted, a cache failure never fails the download. ГИС ОГД: unique `.part` names (`_tmp_beside`), a broken layer or line
    cache is deleted and rebuilt instead of failing for the whole 7-day TTL.
  - Limits: request body ≤ 1.5 GB and non-negative; zip/KMZ refuse > 1 GB unpacked or ratio > 200 over 50 MB (a 438 KB
    bomb used to reach 786 MB of memory). GeoJSON GeometryCollection is split into features instead of failing the drop.
  - DXF import: encoding from `$DWGCODEPAGE` via `ezdxf.recover`, plus cp1251 fallback when names look like «Êðàñíûå»;
    polyline vertices through OCS → WCS (mirrored polylines landed 20 km away).
  - Sheets: second-order transform (Jacobian + curvature) — A1 1:25 000 error 13.9 m → 1 cm on the ground.
  **Front:**
  - Undo after a re-download re-added the old object next to the merged one (double СПП) — `setLayerData` drops feature
    undo records of that layer (not for «Вернуть исходную выгрузку», which records the old objects itself).
  - Re-download kept the server title → a renamed layer vanished from graph nodes; now the user's title stays. Merge keeps
    objects you edited that the source dropped («Нет в источнике»), and objects you drew when the source has no keys.
  - Only OSM buildings loaded → graph «Сохраняемые здания» took nothing, the sketch sat on houses and ТЭП counted all as
    demolished; the node now falls back to OSM buildings and says so.
  - Analysis nodes and «Слой» key on `TERR_REV` (redrawn boundary recomputes). Deleting a view moves its sheets to the current
    map (with a toast); sheets treat layers newer than the view as hidden, like «Показать».
  - Frame select and Ctrl/⌘+A skip objects hidden by category/rules and out-of-scale layers; «Этажность ±» only on own
    layers; «Весь граф» worked again (its code sat in a comment since v0.4); variants without a ТЭП node say so.
  - «Сохранить» under the name of another existing project (case-insensitive) asks for a second press within 8 s;
    `PROJ.file` tells your own file from a same-named one; a file opened from disk is never «own».
  - Start runs on DOMContentLoaded: autosave restore raced script loading («ALBUM is not defined»).
  - `writeFC` writes `{}` for objects without attributes (null crashed the style panel).
  **Speed:** autosave skips `original` when equal to `fc`, waits for 1.5 s of quiet (max 15 s), one save at a time with a
  queued follow-up; graph «Слой» keeps its union when the geometry fingerprint (order-independent) is unchanged — attribute
  edit on 3 000 buildings 267 → 9 ms; snapping stays on the map and is toggled (OpenLayers re-indexes a Snap on every
  `setMap`) — select in «Перенос» on 3×15 000 objects 386 → 12–23 ms; layers > 5 000 objects snap to the view only; bulk
  attribute edit silent + one refresh; sorted table cached by rev; GPU style slider throttled to 120 ms.
  - Checked: auditor scripts (CSRF 403, 0/200 corrupt, cache, bomb), headless scenarios for each front fix, snapping still
    exact, all tests green. Not done → UX queue: per-layer autosave cache, «Правила» counting, norms re-check chunking.

- **2026-09-23, ГРАДО 2 v0.17.1: UX audit of v0.15–0.17 (dark theme, 1280 px).** The empty sheet preview left a light
  strip under the sheets list (`.sheetprev:has(img[hidden])` hides it); the scale and content selects of a sheet row were
  cut at 1280 px (column widths). Menu «Окна ▾», segments, sheet frame and scale visibility checked in the dark theme.

- **2026-09-23, ГРАДО 2 v0.17.0: scale-dependent visibility of a layer (QGIS «Видимость в зависимости от масштаба»).**
  Style panel row «Виден»: on any scale or larger than 1:1000…1:25 000 (`style.maxDen`, saved with the style, undoable).
  `olLayersFor` sets `maxResolution` from the denominator (`denToRes`, latitude of the view centre) on the canvas and GPU
  layers; `restyle` rebuilds the layer when `maxDen` changes (`l._maxDen`). The tree shows an out-of-scale layer's name in
  grey italics (`outscale`, refreshed on every zoom); sheets drop layers whose limit is below the sheet scale. It does not
  touch calculations: the «Ограничения» node reads `shown(l)` (checkbox and group), not the zoom. The insolation front layer
  gets 1:2500 by default for newly computed constraints (existing projects keep their style).
  - Also tried and **not adopted**: shifting the row grid under the solar ceiling (see the UX queue: +0–8 % at 5× the time).

- **2026-09-23, ГРАДО 2 v0.16.0: «Окна ▾» menu on a laptop, sheet frame on the map, ТЭП-only sheet.**
  - Below 1480 px the `.btn.opt` window buttons are hidden and a «Окна ▾» menu lists them with labels and check marks
    (`role=menuitemcheckbox`, `aria-checked` set by `syncWinButtons`; arrows, Enter, Esc, outside click).
  - Sheets: button «Рамка» shows the sheet's map frame (map size × scale) as a blue layer on the main map with
    `ol.interaction.Translate`; `translateend` stores `sheet.center` (lon/lat), «Вернуть» deletes it (then the territory
    centroid is used as before). The view is fitted so the frame lies in the part of the map not covered by the «Листы»
    window. The frame goes away when the window closes (MutationObserver on `hidden`) or a project is opened.
  - Content «таблица ТЭП (все показатели)» → `sheet.kind = "tep"`; `print_io.TepSheetFrame` fills the area above the stamp with
    all rows in up to three columns of at most 180 mm; the map sheet still takes the first 30 rows. Old projects need no
    migration (the fields are optional).
  - «Листы» opens as a strip at the bottom (like «Варианты»); the sheets table is `table-layout: fixed` with a colgroup —
    before, the row buttons were outside the window at 1280 px and checkboxes stretched to the cell width.
  - Checked headless at 1280×800: frame dragged, centre stored, ТЭП sheet preview and PDF; e2e +2 steps, print +1 test.

- **2026-09-23, ГРАДО 2 v0.15.0: small queue items — ОГД download percent, ФГИС ТП search by name, toasts, segments, GPU note.**
  - ГИС ОГД: `_http_get(url, progress=)` streams in 256 KB chunks and decompresses gzip on the fly, so progress counts
    uncompressed bytes; the total comes from Content-Length (no gzip) or the middle number of the portal's ETag
    («mtime-size-inode», checked: 22 099 748 = the real size of `virtual132`). `GisogdApi(progress=)` reports
    `(code, got, total, "download"|"parse")`; the server keeps `PROGRESS` per source key, `GET /api/progress`; «Загрузить»
    polls it every 0.8 s while a ГИС ОГД source is pending and shows ««ПЗЗ: подзоны…» — 62 % (13,8 из 22 МБ)».
  - ФГИС ТП: `GET /api/fgistp/docs?q=` searches the whole catalog by name (all words, case and «ё» ignored, most local
    first, 100 max); the catalog stays in memory keyed by the file mtime. The search field keeps what was typed while an
    answer was on its way. **Finding:** the Moscow genplan is not in the ФГИС ТП catalog at all (27 993 documents, «москв»
    gives Троицк and federal schemes only) — for a territory inside Moscow the window says so and points to ГИС ОГД.
  - Toasts move to the top of the map when a window covers their bottom-centre spot.
  - `.ctl .seg` is an even grid (`auto-fit, minmax(90px,1fr)`, lines by box-shadow so an empty last cell stays clean);
    buttons carry the full name as a tooltip.
  - Style panel of a GPU layer: labels appear from 1:N (from `glSwitchRes`), hatches are a translucent fill at overview.
  - Checked headless on grado2-test at 1280×800 and against the live portal (progress 1.6 → 13.8 → 22.1 MB, then parse);
    connectors +2 tests, grado2 e2e green.

- **2026-09-23, ГРАДО 2 v0.14.1: UX audit of v0.14.0.** The cached-OSM note repeated the date and ran to three lines per
  layer; now «с диска, ответ в ЧЧ:ММ (повторно Overpass не запрашивался)». During the variant search the list said «Нажмите
  «Подобрать варианты»» while that button was hidden, and «Принять в проект» stayed active; now the list explains the run and
  the bake button is disabled until it ends; an empty result says why. Queue: toasts cover a window docked at the bottom.

- **2026-09-23, ГРАДО 2 v0.14.0: OSM answer cache, split download, «Стоп» for the variant search, long names in graph nodes.**
  Owner's queue items after v0.13.1.
  - **Overpass measured:** overpass-api.de refused the connection, maps.mail.ru answered in 21 s, kumi and private.coffee
    gave 504 after 50–77 s. The mirror race was already right; the fix is not to ask again. `OsmOverpass(cache_dir=…)`
    keeps raw answers in `~/.grado2/cache/osm` (index.json + gz, up to 40): an answer younger than 24 h whose area contains
    the request and whose sets cover it is used without the network (features outside the request are cut by bbox);
    when Overpass fails, an answer up to 90 days old is used with a note. `fetched_at` of a cached layer = the cache date.
    The studio still calls the connector without a cache (unchanged).
  - «Загрузить»: OSM goes in its own `/api/fetch` request in parallel, so ЕГРН/ОГД/relief appear without waiting for it;
    the status line says when only OSM is left.
  - «Варианты»: progress bar under the bar, «Стоп» (and Esc) in place of «Подобрать»; a stopped run keeps the ranked
    variants computed so far and says which have no insolation yet.
  - Graph: litegraph draws a combo value unclipped. If `options.values` is an object, it draws `values[value]` and lists the
    keys in the menu, so `fitCombo` returns a Proxy {full name → name cut to the node width}; a value outside the list
    (empty, deleted layer) is drawn too («—» for empty) without entering the menu. Node title and info line are also cut.
  - **Pitfall:** `typeof lgc` on a `let` still in its temporal dead zone throws — graph fonts are the constant `GFONT`.
  - Checked headless on grado2-test; e2e +2 steps (stop, long name), all green; connectors +3 cache tests.

- **2026-09-23, ГРАДО 2 v0.13.0 (stage Э7): product — project format with migrations, browser scenarios in CI, installers, help.**
  - Version: single source `apps/grado2/web/version.json` (0.13.0, project format 2); `/api/health` returns it, the brand shows it.
  - Project format 2 with migrations (`project.js` `MIGRATIONS`, `migrate`): a format-1 file gets groups, views, album and the
    sixth «Посадка» widget; a file newer than the program is refused with a clear reason instead of silently dropping fields.
  - Browser scenarios in the repo: `tests/e2e/driver.mjs` (headless Chrome over the DevTools protocol, node only) and
    `tests/e2e/scenarios.mjs` — offline (synthetic buildings), mouse and keys like the owner: first-run panel, F1, drawing,
    frame selection, batch edit, Del/undo/redo, style undo, groups, register, constraints, goal-density sketch within 10 %,
    neighbours keep insolation, ceiling switched off, view, PDF album, save/new/open, format-1 migration, newer file refused,
    100 000 objects. `tests/test_e2e.py` runs them on a throw-away server with a temp projects folder when `GRADO2_E2E=1` (~18 s).
  - Packaging: `server.main()`; frozen paths via `sys._MEIPASS` (server and dxf_io); `packaging/grado2_entry.py` (crash log +
    message box on Windows), `packaging/grado2.spec` (one-folder build, .app bundle on macOS with `.grado2` document type),
    `packaging/grado2-installer.iss` (Inno Setup), `.github/workflows/grado2-release.yml` (unit + browser tests on Ubuntu, builds on
    windows-latest and macos-latest with a smoke test of `/api/health`, installer and DMG, release on tag `grado2-v*`).
    **Not verified here:** a local macOS build stops at `lipo` because the Xcode licence is not accepted on this Mac
    (`sudo xcodebuild -license` — the owner's password); the Windows build needs the CI run. Launchers without an installer:
    `ГРАДО 2.command` (macOS) and `ГРАДО 2.bat` (Windows) create the venv on first start.
  - Help: F1 window «Справка и клавиши» starts with «Как работать» in nine steps and states that insolation is a design-stage
    estimate and radii are federal СП 42.13330.

- **2026-09-23, ГРАДО 2 v0.12.0 (stage Э6): sheets and a PDF album through the core renderer.**
  - Window «Листы» (header): album meta for the title block (object, code, short stage ПП/П/Р, organisation) and a list of
    sheets — title, A3 or A1 landscape, content (a saved view or the current map), scale (auto by the territory or
    1:500…1:25 000), legend and ТЭП switches, preview (SVG) and «PDF альбома».
  - The client resolves every object's symbol with the same `symbolOf` that draws the layers (a view's styles if the sheet
    uses a view), clips to the frame and sends WGS84 + symbols; `apps/grado2/print_io.py` builds pages with the core layout
    (`PageBorder`, `StampFrame` form 3 ГОСТ Р 21.101, `TableFrame`) and renders with the core PDF writer / SVG backend.
    Map in МГГТ metres (exact transform at the sheet centre + its Jacobian; < 1 cm on the ground), REDLN97 linetypes from the
    same LIN/SHX data as the screen (`linetype_ops`), red-line codes without a linetype dashed by the ЛГР library, hatches,
    opacity mixed with white (the core PDF writer has no alpha), north arrow, scale bar, labels without overlaps, legend of the
    view, ТЭП table (overflow is noted). Layout: map 275×224 mm on A3, 636×521 on A1, above the 185×55 stamp.
  - **Pitfall (performance):** the first album of two sheets took 3 minutes — `hatch_ops` walked every vertex of whole
    water-protection and sanitary zones (kilometres of outline) for each hatch line. Zones are clipped to the frame first
    (`clip_ring`, Sutherland–Hodgman): 84 s → 0.08 s for an A3 sheet. The per-point Newton transform was replaced by the
    Jacobian and the linetype walker by a moving pointer for the same reason.
  - Tests: `tests/test_print.py` (two-sheet PDF, SVG with frame and legend, 100 m = 50 mm at 1:2000, a REDLN97 linetype with
    shapes, ring clipping). The album and the sheets list are saved in the project (`album`).

- **2026-09-23, ГРАДО 2 v0.11.0 (stage Э3): analysis nodes that explain themselves, «В слой», views of the map.**
  - OSM set `social` in the core connector (nodes, ways and relations with amenity school / kindergarten / clinic / doctors /
    hospital / pharmacy → points; a school's outline stays in `buildings` too). ГРАДО 2 source «Школы, детсады, поликлиники (OSM)»
    with «Вид» in Russian.
  - Graph group «Анализ» (`web/analysis.js`): «Радиусы обслуживания» (ДОО 300 м, школы 500 м, поликлиники 1000 м, аптеки 500 м —
    СП 42.13330.2016 табл. 10.1/10.2, checked against the text of the code; −30 % switch for dense high-rise), «Пешая
    доступность» (Dijkstra over OSM streets without motorways, 4.5 km/h, reachable pieces buffered 30 m), «Показатели кварталов»
    (per block: area, buildings, СПП, density, coverage, mean floors; without an input the blocks are the territory between
    OSM streets), «Баланс территории» (area and share inside the boundary by a field of the input layer).
  - Every analysis node keeps a feature list `_fc` with «Пояснение»; while the node is selected the preview labels it on the map.
    «В слой» in the graph window bakes the selected node's output as a project layer with that table.
  - Window «Виды» (like QGIS map themes): a view stores visible layers, their styles and opacity, group visibility, the basemap
    and optionally the extent; «Показать» switches the map, the legend of the view is built from its visible layers. Saved in
    the project (`views`). Sheets of Э6 will take their content from views.
  - Header and tool strip keep fitting at 1280 px: labels of Таблица, Показатели, Длина, Площадь become icons below 1480 px.
  - Checked in headless Chrome on Хорошёво with real OSM (Overpass answered in ~60 s): 8 social objects, school radius leaves
    9.9 ha outside, walking 10 min to kindergartens 23.8 ha (0.6 s, 1939 street nodes), 5 blocks between streets, ПЗЗ balance
    by ВРИ — 16 values covering 100 %, bake, two views switch, views survive save/open.

- **2026-09-23, ГРАДО 2 v0.10.0 (stage Э5): generation — typologies, floors to the density goal, variant search, norms check, 3D shadows.**
  - Typologies: Секции, Квартал, Башни, «Точка + секция» (a tower between sections in each row), «Смешанная» (sections on the edge
    rows along streets, towers inside). Every building knows its kind («Корпус» in the accepted layer). Rotation −90…90 (90 = across).
  - «Этажность по: цели плотности» (new 6th widget of «Посадка»): floors are water-filled so the new СПП reaches the ТЭП node's
    target (target × territory − kept СПП), never above a building's ceiling; the node says «цель не достигнута: не хватает N тыс. м²»
    when the ceiling does not allow it. «ниже по потолку» now means the ceiling is below the planned floors.
  - «Подобрать варианты»: 5 typologies × 2 widths × along/across = 20 candidates with the density goal, ranked by density error
    plus own insolation (share of non-north facades of the new buildings with the norm on 22.04, coarse), ТЭП from the server for
    the top six; cards + a full comparison table; a click moves the parameters into the graph. ~25 s for Хорошёво.
  - «Проверить нормы» (window «Эскиз», or layer menu of an accepted sketch): own insolation of new buildings (a building with < 50 %
    facades at the norm is flagged), neighbours that lose the norm (checked against the state before development), buildings on
    switched-on ban layers, gaps < 6 m between new buildings. Result — point layer «Проверка норм» with the reason on each point.
    An accepted sketch that was checked is re-checked 1.5 s after every edit (`window.onLayerEdited` from `syncFromSource`).
  - «Объект» for sketch buildings: «Этажность − / +» for the selection (undoable, recomputes «СПП, м²»).
  - «Объём»: ground shadows for 22.04 / 22.06 / 22.08 / 22.12 and a solar-time slider 6–18; accepted sketch layers are drawn too.
  - `fits` now needs 99.7 % of a building on the site (was 98.5 %): 1.5 % let sections poke into a water-protection zone.
  - Window headers ignore drags that start on their own inputs and selects.

- **2026-09-23, ГРАДО 2 v0.9.0 (stage Э4): constraints for generation — window «Ограничения», insolation front, solar ceiling.**
  - Window «Ограничения» (header button) builds ordinary layers in the group «Ограничения» from loaded data: «Запрет: ЗОУИТ и
    охранные зоны» (ЕГРН ЗОУИТ, СЗЗ, водоохранные, ОКН except development-regulation zones; each zone keeps «Причина»),
    «Запрет: N м от красных линий» (СП 42.13330.2016, N adjustable, default 5), «Запрет: сохраняемые здания и пожарные разрывы»
    (all buildings except «сносим»; 6/8/10 m by wall material, СП 4.13130.2013 table 1), «Запрет: ПЗЗ без нового строительства»
    (0/0/0 subzones), «Инсоляция: окна соседей (фронт)» and «Потолок застройки (инсоляция соседей, ПЗЗ)».
  - Graph node «Ограничения» (`constraints.js`) reads only the layers of the group that are switched on: what is visible is what
    generation respects. On the first calculation it is inserted between «Пятно застройки» and «Посадка» («Пятно с ограничениями» =
    site − bans; «потолок» → the new third input of «Посадка»). A building never exceeds the lowest ceiling under its footprint and
    is dropped below 2 floors (`generate` → `place` + cap). Layer visibility toggles bump `dataRev`, so the sketch follows at once.
  - **Insolation (`web/insol.js`, no DOM, tested under node):** sun by Spencer declination, solar time, 22.04 and 22.08; window
    sunrise+1 h … sunset−1 h rounded to half an hour = 6:00–18:00 at 55.75° N, exactly the МАрхИ (Поповский) 55° ruler; norm
    2 h continuous or 2.5 h intermittent with one period ≥ 1 h (СанПиН 1.2.3685-21). Front points every 4 m on facades of kept
    residential buildings (ЕГРН «Назначение» жилой/многоквартирный, OSM residential), 0.2 m outside, at 2 m; courtyard facades
    included. Facades that cannot reach the norm by orientation even unobstructed are marked «не нормируется (фасад на север)»
    and not protected. Points already failing are protected entirely («не ухудшать»).
  - **Solar ceiling:** per 8 m cell the highest top that keeps every protected sun ray: a passing point protects one norm-long
    window inside its lit period, chosen so its rays cross the site the least. Any mass under the ceiling keeps all neighbours
    compliant regardless of order (fixes the order dependence of greedy growth). Exact grid traversal (Amanatides–Woo) and a 1 cm
    margin: half-cell stepping skipped cell corners and float32 rounding let a random test building break a window.
  - Validation (`tests/insol_test.js`, run by `test_insol.py`): 6:00–18:00 window; declination 22.04 = 11.92°; noon altitude
    46.2°, 10 m pole shadow 9.60 m; east facade 6:00–12:00; south facade symmetric; a 30 m wall 20 m south matches the analytic
    shading formula in all 145 samples; norm rules; 6 random developments under the ceiling lose no compliant facade; a 120 m tower
    in a low cell does; a courtyard is shaded by its own walls. Хорошёво: 1328 points on 24 houses, whole calculation ~1 s.
  - **Pitfall:** Turf `difference`/`union` throw «Unable to find segment … SweepLine» on nearly coincident edges and the whole site
    silently became empty. `robust()` retries with coordinates rounded to ~1 cm, then with a 1 cm buffered subtrahend.
  - **Pitfall:** a canvas stroke of width 0 is ignored (the previous width stays) — a layer with «Контур 0» drew a white grid.

- **2026-09-23, ГРАДО 2 v0.8.0 (stage Э2): existing situation — ПЗЗ, ОКН, demolition notices, relief, file import, satellite, re-download diff, buildings register.**
  - ГИС ОГД layers (codes checked against the live catalog 23.09.2026): ПЗЗ subzones `virtual98` (old Moscow) + `virtual132`
    (new Moscow) → «ПЗЗ: подзоны» with numeric «Плотность, тыс. м²/га», «Высота, м», «Застроенность, %» and a text «Регламент»;
    ПЗЗ zones `virtual90` + `virtual130` → «ПЗЗ: территориальные зоны и ВРИ» (ВРИ codes and names, link to the regulation PDF);
    ОКН `virtual500/502/504/508` (territory, protection zone, development regulation zone, protective zone) → one layer by «Вид зоны»;
    demolition notices `t_1322`. Readable fields are built in `server.py` (`PRESENT`), technical portal fields are dropped.
  - **Meaning of ПЗЗ values:** «-» = not set, «Ф» = by the existing state, 0/0/0 = «нулевые параметры: новое строительство не
    предусмотрено». In old Moscow height is a number in only ~1 % of subzones, density in ~22 %; the default style is ranges by density.
  - **Core connector:** `GisogdApi` writes a line cache `<code>.lines.gz` («w,s,e,n<TAB>key<TAB>json» per object) next to the full
    layer and reads it line by line: the 221 MB zones layer goes from 7.4 s / ~1.5 GB to 0.5 s. First download still takes 1–2 min.
  - Relief: «Рельеф: горизонтали (SRTM)» from the core `TerrainContours` (needs **Pillow**, added to `apps/grado2/requirements.txt`
    and installed into `~/.grado2/venv`); terrain tiles now retry the TLS handshake 3 times.
  - Import (button «Файл…» in «Данные» or drag files onto the map, like QGIS): GeoJSON, KML/KMZ, Shapefile (zip or .shp+.dbf+.prj),
    DXF — `apps/grado2/file_io.py`, `/api/import/files`. Coordinates recognised as WGS84 / МГГТ / Web Mercator.
    **Bug fixed in the DXF import too:** it decided «degrees» by x alone, but МГГТ easting near the central meridian is below 180
    (37.5° E is x ≈ 115 m) — a drawing in that strip was read as degrees. Now both x within ±180 and y within ±90 are required.
  - Basemap switch on the map: OSM scheme (grey), Esri satellite, Sentinel-2 cloudless (EOX), none; kept in the project.
  - ФГИС ТП in «Данные»: documents whose extent covers the territory (catalog 28 000 docs cached a week, country-wide schemes cut off),
    a document's layers, load the checked ones clipped to the territory. No DNS problem now; Moscow's own genplan is not found by extent.
  - Re-download: each object carries the source key `_key`; a second download is compared with the previous one (+new, −gone,
    changed) and merged with manual work — your edited objects win, objects you deleted stay deleted, objects you drew stay,
    fields you added (e.g. «Решение») carry over. New and changed objects are selected; the history shows in «Данные».
  - Buildings register: layer menu «Реестр зданий: сохраняем / сносим» adds «Решение» to every building, colours by it, and puts
    buttons «сохраняем / реконстр. / сносим» into «Объект» for the selection. The graph node feeding «сохраняемые» into ТЭП gets the
    filter «Решение ≠ сносим», so demolished buildings free the site and go to «Под снос».
  - НСПД: only fields with a Russian name are kept (was: `systemInfo` as «[object Object]», `interactionId`, `opt_cost_*`, …).
  - Checked in headless Chrome: load of ПЗЗ/ОКН/relief for Хорошёво, register + demolition marks + ТЭП «под снос 3», re-download merge,
    GeoJSON import, satellite; scenarios A–I again; console clean. Tests: grado2 26, connectors green.

- **2026-09-23, ГРАДО 2 v0.7.0 (stage Э1): layer groups, multi-select, batch attributes, undo/redo for styles, keys window, 100 000 objects.**
  - Groups as in QGIS: `GROUPS` + `layer.group`; a group's layers stay contiguous in `LYR` (`normGroups`, empty groups vanish).
    Drag a layer onto a layer = its group; onto the lower half of a group header = into it; a group drags as a block.
    Group visibility hides its layers (`shown(l)`). Saved in `.grado2` (`groups`, `layers[].group`).
    **Pitfall:** during `applyProject` layers arrive one by one, and `normGroups` inside `ensureLayer` would drop the not yet
    filled groups — groups and `layer.group` are restored after the layer loop.
  - Selection is a list `SEL = [{key, f}]` from one or several layers, highlighted by its own overlay layer (canvas up to
    5 000, WebGL above). Click, Shift+click toggles, Shift+drag adds a frame, Ctrl/⌘+drag a new frame; AutoCAD direction:
    left→right only objects fully inside, right→left everything touched. `shiftDragZoom` is off for this. Ctrl/⌘+A = all
    of the current layer. Del deletes all selected; M/E work on the selection (grips like AutoCAD).
  - «Объект» with several objects: summary (area/length) and, for one layer, batch edit — an entered value goes to all,
    «разные (N)» marks mixed values. Table: Shift/Ctrl+click adds rows, «только выбранные».
  - Undo/redo (`UNDO`/`REDO`, Ctrl/⌘+Z, Ctrl/⌘+Shift+Z, Ctrl+Y): records keep only the touched objects (geometry clone +
    properties), style records keep the style JSON; a slider drag is one record (same field within 1.5 s). The inverse record
    is captured at undo time. Undo of a 100k layer edit takes ~20 ms (was a full-layer JSON copy per edit).
  - Keys window (F1, «?», header button) is generated from `KEYS`/`TOOLS`, so it cannot drift from the handlers.
    First run shows «С чего начать» on the map instead of opening «Данные».
  - Performance: OpenLayers 10.2.1 → **10.10.0** (has `ol.layer.WebGLVector`). A layer over 20 000 objects is drawn by the
    GPU at overview and by the normal canvas when zoomed in (switch resolution = ~15 000 objects in view, `glSwitchRes`).
    Measured on 100 000 polygons (M3, headless Chrome): canvas 140 ms/frame at overview → GPU ~40 ms; zoomed ~20 ms;
    select all 0.1 s; restyle 0.2 s. `DATA[key].fc` is now a lazy getter rebuilt from the map objects on first read after
    an edit (`bindFC`); graph «Слой» nodes recompute by per-layer `d.rev`, not by any edit anywhere.
  - **Pitfall:** WebGL shader names are built from property names, and `_sym` gave `a_prop__sym` («__» is reserved in GLSL,
    the shader does not compile). The class property is `gradosym`, hidden from tables and stripped on write.
  - **Pitfall:** `$("bUndo").onclick = undo` before `const undo = …` threw a TDZ error and silently stopped the rest of
    layers.js. Keep top-level handler wiring after the definitions.
  - **Pitfall:** without a doctype tables do not inherit the font size (quirks mode) — `table{font:inherit}`.
  - Point labels sit above the marker and markers are declutter obstacles, otherwise labels hid the points.
  - Checked in headless Chrome (CDP driver in the session scratchpad; the browser pane was hidden and does not render):
    scenarios A, B, D, D2, E, F, G, H, I pass, console clean, fits 1280×800. C: NSPD loads; Overpass timed out (external).

- **2026-09-23, ГРАДО 2 v0.6: sketch only on demand, edge-aligned placement, Preview/Bake, style fixes.**
  Owner: "style settings do not work; the boundary fills at once with random rows of houses; look at
  analogous programs and adopt their logic". Diagnosis: style controls worked, but graph results
  (site hatch, node output, sketch grid) were drawn over every layer, so style changes were invisible.
  Adopted logic (research: Grasshopper Preview/Disable/Bake, TestFit/Forma opt-in generation, QGIS styling):
  - «Посадка застройки» has `properties.run` (Data Dam): nothing is placed until «Построить эскиз» in
    the «Эскиз» window; «Остановить» freezes it. Picking a variant turns it on.
  - Generator: each part of the buildable area separately, oriented to its minimum-area rectangle
    (rotating calipers over the convex hull), whole buildings only (≥98.5 % inside), rows centred,
    long-side gap = max(gap×H, 15 m for 2–3 fl. / 20 m for 4+ fl., СП 42.13330 п. 7.1). Widget
    «ориентация» became «поворот, °» (−45…45, relative to the part). Insolation/fire gaps not computed.
  - Default graph keeps ALL ЕГРН buildings (no «≥ 9 floors» demolition), so houses do not land on houses.
  - Preview: graph layers are visible only while Граф/Эскиз/Варианты/Объём/Сравнение are open
    (`syncPreview`), node output only with «Граф». «Принять в проект» (`bakeSketch`) makes a normal layer
    «Эскиз: …» with Этажность/СПП attributes; DXF export now takes only project layers (+ Этажность → thickness).
  - Graduated breaks collapse duplicates (one value → one class, mid ramp colour); line swatches in the
    tree got CSS; QGIS wording «Классифицировать».
  - **Pitfall:** renaming a node widget breaks `publishedControls` lookups by name and old projects;
    `applyProject` fills missing widget values with a safe default.

- **2026-09-23, ГРАДО 2 v0.5: projects — save, open, new, autosave with restore after reload.**
  A project is a `.grado2` file (JSON) in `~/Documents/ГРАДО 2` (env `GRADO2_PROJECTS` overrides): territory,
  layers (order, style, visibility, opacity), their data with the original download, import sources,
  graph (`graph.serialize()`), map view. Server: `GET /api/projects`, `GET|POST /api/project?name=…`,
  `?autosave=1` → hidden `.autosave.grado2`; names are file names (no path characters, no leading dot),
  writes are atomic (tmp + `os.replace`), non-JSON is refused. Client `web/project.js`: window «Проекты»
  (name + Сохранить, Новый проект, Открыть файл…, Скачать копию, list), header button with «•» for unsaved
  changes, Ctrl/⌘+S, autosave ~2 s after an edit, restore on start. Unsaved work is not dropped silently:
  «Новый»/«Открыть» need a second press within 4 s.
  - **Pitfall:** litegraph does not serialize widget values unless `serialize_widgets` is true — floors,
    buffers and the layer names of «Слой» nodes were lost on reopen. Set on `LGraphNode.prototype`.
  - **Pitfall:** start-up recomputes marked a fresh page as edited, and autosave wrote an empty project
    over the real one. `PROJ.loading` stays true until `projectStart` has finished.
  - Test server `grado2-test` (port 8651, `GRADO2_NO_BROWSER=1`, temp project folder) in `~/.claude/launch.json`.
  - Checked: 9 real layers + territory + graph edits → save → new → open: order, counts, styles, original,
    graph values all equal. Tests grado2 10 green. **Backend change: the owner must restart server.py.**

- **2026-09-23, ГРАДО 2 v0.4: no stages — one workspace, AutoCAD tool strip, floating windows; self-audit hooks.**
  The owner: "I created a layer and cannot see how to add objects; where is the AutoCAD tool strip; why
  the stages on top — work should be free, in pop-up windows". The three stages are gone. Layout:
  header with window toggles → tool strip → layers | map | style/object → status bar.
  - Tool strip (`layers.js` `TOOLS`/`setTool`): select, point, line, polygon, rectangle, vertices, move,
    delete, undo, snap, length, area, territory boundary. Hotkeys by `e.code` (work in the Russian
    layout): V P L G R E M D A B, Esc, Del, Backspace removes the last vertex, Ctrl/⌘+Z.
  - Drawing goes into the current layer when its geometry fits, else into the owner's own layer of that
    geometry, else a new «Точки/Линии/Полигоны» is created with a toast. «+ Слой» turns the drawing tool
    on at once. A map click selects but does NOT change the current layer (QGIS identify), otherwise the
    next polygon could land in a download. The `editing` mode flag is gone: attributes are always editable.
  - Floating windows (`app.js` `winOpen`): Данные, Граф, Эскиз, Варианты, Показатели, Объём, Сравнение,
    Таблица; drag by the header, resize by the corner, position/size/open state in localStorage
    `grado2.win`. Docks «Слои»/«Свойства» toggle from the header. Graph results (site, kept, sketch,
    selected-node output) are layers on the main map with toggles under «Результат графа» in the tree.
  - Status bar: what the tool expects next, the target layer, scale, coordinates.
  - **Hooks** (`.claude/settings.json`): PostToolUse `grado2_check.py` runs `node --check`/py_compile on
    edited grado2 files (exit 2 shows the error); Stop `grado2_ux_gate.py` blocks the first stop after any
    change to `apps/grado2` (hash of HEAD tree + diff) and sends Claude to `docs/ux/grado2-ux.md`
    (owner's principles, scenarios A–H, queue). `stop_hook_active` lets the second stop pass.
  - **Pitfall:** the browser pane's `navigate` to the same URL reused the cached page — check with
    `location.reload()`. Litegraph at scale < 0.6 is unreadable → `fitGraph` clamps to 0.6.
  - Checked in the browser (1440×900): scenarios A–H, console clean; grado2 tests 7 green.

- **2026-09-23, ГРАДО 2 v0.3: step 1 «Существующее положение» works like QGIS; exports are editable.**
  `web/layers.js` — layer model (top to bottom): tree with drag-and-drop draw order (zIndex on all maps),
  visibility, legend children (categories toggle on/off), layer menu (zoom, table, edit, rename,
  up/down, «Вернуть исходную выгрузку», delete), new empty layer (polygons/lines/points).
  Style: single / categories / ranges / rules / ЛГР (REDLN97), outline, fill and layer opacity, labels.
  Editing: vertices (ol Modify), new objects (Draw), delete, attributes in «Объект» and in the table
  (double-click a cell), snapping, Ctrl+Z; edits go to `DATA[key].fc` → the graph sees them; the original
  download is kept in `DATA[key].original`. Maps register in `ALLMAPS`; layers attach to each one.
  Checked in the browser: drag → zIndex, cat/grad, attribute edit (badge «изм.»), delete+undo, table.
  **Pitfall:** without `Cache-Control: no-cache` the browser kept the old app.js after an update — the
  server now sends it. **Not done:** saving the project to a file (edits live only until reload).

- **2026-09-23, ГРАДО 2 v0.2: AutoCAD red-line standard REDLN97 (LIN+SHX) — screen, DXF export/import; New Moscow pastel.**
  The owner sent `REDLN97.LIN` + `RED_LNS.SHX` (now in `docs/standards/redln97`) and three Genplan QMLs.
  - **Naming decoded, not guessed from docs:** `L00sNNx` = code NN alone; `LCCsNNx` = code NN on
    carrier line CC (01 УДС, 02 ТОП, 04 ОДМС, 06 railway right-of-way); `LAAxBBy` = two codes without
    a carrier. `x`: b/t/s. **Sign of ОГД LineCode verified on 585 real red lines:** «+» = object to the
    right of the line → `b`, «−» → `t` (203:58 and 168:36). Codes 29 and 45 have no REDLN97 linetype;
    they are drawn with the ЛГР library (dash + color), with no markers.
  - Core: `core/render/grado_render/acad_lin.py` (SHX decoder per the AutoCAD shape spec, LIN parser,
    LineCode→linetype `linetypes_for_codes`). `tools/gen_redln97.py` → `styles/redln97.json` (rule 2,
    in the generator gate). `crs.wgs84_to_msk50` — inverse Moscow local (МГГТ) by Newton iteration.
  - ГРАДО 2: ОГД red-lines layer `gisogd.red_lines` (l1, first download ~105 MB). Server attaches `_lt`
    and `_miss`. JS renderer `web/linetype.js` (at 1:10000 and smaller: plain line, like the portal).
    Catalog of all 500 types: `/linetypes.html`.
  - DXF (`apps/grado2/dxf_io.py`, **ezdxf in venv `~/.grado2/venv`**, `requirements.txt`): export R2018
    in МГГТ with complex linetypes (ezdxf needs the SHAPE NUMBER from the .shx index, not the name),
    zip with `red_lns.shx`; import DXF → LineCode back, МГГТ/WGS84 detected automatically.
    DWG is not supported (needs the ODA converter).
  - Functional zones: Moscow and Nekrasovka QMLs match the library 1:1. New Moscow: owner's choice is
    the pastel QML → a separate palette `nm_zone` (gp.nm.*); the legacy studio routing by gp_zone is unchanged.
  - **Not done:** printing with REDLN97 (ГРАДО 2 has no sheets stage yet; the data is in core JSON).
  - Tests: core 523 + grado2 7, green.

- **2026-09-22, ГРАДО 2 v0.1: new app `apps/grado2` on the core + real exports; core audit.**
  The owner rejected the old studio (design, logic, convenience) and QGIS as a base. The new flow:
  existing situation from real sources → Grasshopper-like node graph (litegraph.js) → generative
  TestFit-like sketch with variants and ТЭП. Run: `python3 apps/grado2/server.py` (port 8650,
  preview config `grado2`).
  - Backend `server.py` (stdlib only): `/api/fetch` = the core connectors NspdDirect/OsmOverpass/
    GisogdApi, WGS84 output. `/api/tep` = the core `Engine` with the KRT preset. Population is
    counted only from new buildings. The ТЭП copy in JS is gone.
  - Front `web/app.js`: OpenLayers (EPSG:3857, OSM basemap), Turf.js for graph geometry.
    Placement and the 3D view work in a local metric frame around the territory.
  - Core fixes: atomic `set_inputs`; `calc_area` clamped to 0; OSM keeps holes in multipolygons.
    Audit and the list of bugs NOT fixed: `docs/audits/2026-09-22-grado2-core.md`.
  - Verified live (Khoroshevo, 45.9 ha): 8 layers loaded, buildable area 20.7 ha, 57 buildings,
    6 variants. Tests 513 green.
  - **NOTE:** this file claims the Moscow regulatory profile is "connected to compute_tep". It is
    not true: `moscow_urban_planning.json` is not loaded by any code.

