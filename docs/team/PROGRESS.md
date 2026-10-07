# Журнал команды ГРАДО 2

Новые циклы сверху. Строки `RULE:` — уроки, которые обязана прочитать каждая следующая задача.

RULE: Navigation is checked by `python3 tools/docs_check.py` (in `tools/gate.sh` and CI `docs.yml`): a document is moved with `git mv` and the checker
runs at once; a new `.md` under `docs/` is named in the README of its shelf (`docs/CLAUDE.md`); every code file starts with a «what it is» header; a new top-level
file or folder is named in `INDEX.md` (07.10.2026, issue #50).

RULE: Every package with tests is in `tools/gate.sh` and in `.github/workflows/grado2-release.yml`: the tests of `core/compute`, `geom`, `layout`, `model`, `reactive`,
`render` (232) were run by nobody until 07.10.2026; a new tests folder gets a line in both files the same day.

RULE: A browser step waits for the element or text it checks (`until`), never reads it right after a window becomes visible:
the collab step «A: список проектов пуст» read `hubProjList` before `loadProjects()` drew it and failed on the slow GitHub
runner; T27 and T61 failed the same way on other runs of one PR (07.10.2026, issue #40).

RULE: Album changes are verified with `tools/album_check.py` against `~/.grado2/album-baseline/{gol,bez}` (pixels and page
text, crops in summary.png) — skill `album-verify`; owner remarks follow skill `owner-remark`; landing — skill `land`.

RULE: A script started from a git hook inherits GIT_DIR/GIT_INDEX_FILE: before running git in another repository, unset
them and check `git rev-parse --show-toplevel` (06.10.2026 the wiki publisher committed wiki pages over the program on
team/t60; caught by `git show --stat`, branch restored to the previous commit, main untouched).

RULE: A change to album download or label placement is accepted only after a real album rebuild with network on a
fresh project copy plus a page-by-page PDF comparison with the previous baseline on two territories (T86: mocked
download and spec-JSON golden both passed while sheet 4 lost roads and the station label moved onto a road).

RULE: Cycle start = `git merge main` in the team branch → `tools/gate.sh` → read `docs/wiki/INDEX.md` and `docs/wiki/team.md`;
agent briefs come from `docs/team/prompts/` and cite wiki pages instead of pasting file ranges.

RULE: A feature that reads portal data is checked on one live (cached) object before it is accepted: unit tests on
fake data passed for T82 while the real Yandex points carry the name in «Название», not `name`, and no icon was drawn.

- 07.10.2026, наведение порядка в репозитории (задача #50, PR #52; по просьбе владельца): влиты в `team/t60` PR #46 (альбом по замечаниям 07.10, #45 #47 #48 #44), #36 (релей НСПД)
  и #49 (версия 0.99.45, устойчивые T27 и T61, #40). `docs/` разложен по полкам (`wiki`, `standards`, `specs`, `product`, `ux`, `guides`, `team`, `archive`, карта `docs/INDEX.md`), 65 файлов
  перенесены `git mv`; новые `README.md`, `INDEX.md`, `AGENTS.md`, `CLAUDE.md` и README в каждой папке; `tools/docs_check.py` в gate и CI; вики сама пересобирается (`wiki.yml`) и
  берёт состав листов из `albums.js`; тесты остального ядра в gate и CI. Проверка: `tools/gate.sh` зелёный, CI. Не сделано без вашего действия: секрет `WIKI_TOKEN` (вики в `tayeela/grado-wiki`
  всё ещё версии 0.99.27 до первой выкладки), удаление 21 влитой ветки (облачной сессии запрещено; команда `tools/prune-merged-branches.sh --yes` на Mac), решение по PR #34. Аудит оформления
  презентации по Гольяново (огрехи и правила) — отдельной задачей GitHub, итог в `docs/standards/albums/layout-qa.md`.
- 07.10.2026, выкладка по слову владельца («выкладывай») — v0.99.43: три листа «в границах сит. плана» (#37, PR #38 и #39,
  v0.99.40–0.99.43): рамка «по границам выгрузки» и третье значение настройки «Масштаб схем 5–9»; новые листы 10–13 в конце
  альбома ППТ КРТ — карта района, схема документации (ППТ, ПМТ, ГПЗУ, АГР, КРТ), Генплан и ПЗЗ в рамке сит. плана. Настройка
  «Масштаб схем» (#31) ушла в main раньше, PR #35 (v0.99.39). Проверка: wiki, unit, connectors; браузерные сценарии на GitHub
  зелёные (451 ok; у PR три красных запуска на посторонних шагах T27, T61, collab — гонки по времени в тестах, задача #40,
  упавшее перезапущено один раз); локально сбой только T68 (шрифты облачной среды, то же на чистой team/t60). Листы нарисованы
  сервером и выгружены в PDF (4 страницы А3) и PPTX (4 слайда) на синтетических данных, страницы просмотрены.
  НЕ сделано: пересборка альбома и сравнение страниц на Гольяново и Безобразово (`album-verify`, `tools/album_check.py
  --name gol|bez`) — в облаке нет проектов, ГИС ОГД, ЕГКО, НСПД и Overpass не отвечают; владелец знает и выложить велел.
  После выкладки на Mac: листы 1–9 не должны измениться, листы 10–13 сравнить с образцами `docs/team/samples/2026-10-07`;
  первая загрузка слоёв для листа 10 (район около 40 км²) заметно дольше прежней. Сайт: из облака выкладка недоступна.
  07.10 около 12:00 UTC прежний сервер AEZA-GRADO перестал отвечать (сайт давал 503 и таймауты); соседняя сессия на Mac
  перенесла ГРАДО на msk (службы grado и grado-guest, Caddy с прежним паролем, grado.tailink.tech → 93.88.203.245; у клиента кэш
  адресов мог держать старый — переподключить VPN, «Clear host cache» в браузере), там стояла 0.99.39. Скрипт выкладки под msk
  (Mac → msk без перехода на другой хост, перезапуск обеих копий, при сбое возврат прежней версии) — PR #41, выложен в main
  второй короткой выкладкой по тому же слову владельца. Версия 0.99.43 попадает на сайт командой `git pull` в `~/grado-studio` на
  Mac: хук запускает `tools/deploy-server.sh`; «Сервер занят выгрузкой… отложено» или ошибка — на сайте прежняя версия, повторить.
- 06.10.2026, цикл 27 — полная проверка альбома Гольяново (нормы, оформление, данные: AUD-*.md в /tmp/grado-team/2026-10-06),
  сводный список F1–F12 + PPTX. Сделано v0.99.21–0.99.22: СЗЗ установленные, дорога-пробел ЕГКО, легенда генплана,
  таблица участков, ЖК, выноски листа 2, номер зоны, PPTX 20 мин → 20 с и встроенный Montserrat. Данные владельца:
  аренда :85/:86 из выписок ЕГРН, адрес «вл. 8» по письму ДГП. Новые PDF/PPTX/проект — в папке выдачи, прежние в
  «прежняя версия/выдача 05.10». Осталось: строка «лист N из 9» при выгрузке (сервер готов, UI нет), подпись улицы у
  границы (F8 не сработал: подпись ставится другим путём), лист 4 без снимков (ждём владельца).
- 06.10.2026, цикл 26 — T86a–f в копии `.claude/worktrees/t86` (team/t86), каждый шаг: эталон спецификаций листов
  59/59 (КРТ 3229 + Безобразово копия, `/tmp/grado-team/2026-10-06/T86a-golden/dump.js`), живая проверка со снимками,
  gate; ревью руководителя по снимкам дало правки T86b (дубли ролей, обрезка, «Границы», «100 % + в рамке нет») и
  баг подписи станции на добавленной ж/д (T86d). Ждёт «выкладывай».
- 06.10.2026, цикл 25 и выкладка («выкладывай и продолжай»). Совет по единой логике листов (продакт, архитектор,
  креативный директор) → T86, макет одобрен владельцем (А). T85a/b приняты: легенда из нарисованного, подписи рек от
  данных проекта; причина «не готов» для листов документации перенесена в `notReadyWhy` вызовом `window.conceptWhy`
  (без подмены функции). Полный gate с E2E зелёный; main ff до 3c25040, сайт: версия 0.99.13. T86a идёт в отдельной
  копии `.claude/worktrees/t86` (ветка team/t86) с эталоном спецификаций листов до/после.
- 06.10.2026, цикл 24 — правила владельца 16–18 (значки станций, кавычки, анклав) и «МЦК как метро». Сессия
  обрывалась (у подагентов истёк вход) — задачи перезапущены с нуля, рабочее дерево было чистым. T82 (значки метро/МЦК/МЦД,
  источник — точки Яндекса transport_p), T83 (кавычки); руководитель перенёс глубину кавычек в печать. Ревью архитектора —
  PASS обе. Проверка на живых данных у метро «Перово» нашла ошибку (имя в «Название») — исправлено, тест добавлен; лист 3
  и 5 — «М Перово» красным, легенда «станция метро». Unit OK, connectors OK, E2E зелёный (до последней правки в JS —
  правка покрыта unit-тестом). v0.99.10 на team/t60 — ждёт «выкладывай».
- 05.10.2026, цикл 23 — слово владельца: «подписи станций ж/д начинаются с «ст. ж/д»», «команда, продолжай по плану».
  T78 (подписи + правило 15), T80 (тесты), затем T79 (Генплан), T81 (пометка о грубом снимке). Ревью архитектора — все
  PASS; по его замечаниям руководитель сузил признак станции («СТ Ромашка» и «Платформа …», ТЭЦ, депо — не станции).
  Проверка: КРТ 3229 пересобран на тестовой копии — «ст. ж/д Калошино» рядом с путями, лист 6 по таблице MapInfo;
  unit 461 OK с PYTHONPATH и без, connectors OK, E2E зелёный. v0.99.9 на team/t60 — ждёт «выкладывай».
  Остались: T77 (кэш okrugMain, анклав на карте Москвы, углы по рамке МСК).
RULE: Any new choice bar in «Листы и альбом» closes the pending one (only one bar at a time) and old E2E steps that
export on purpose pass `force` — T74's export gate broke t62/t66 until then.

- 05.10.2026, цикл 22 и выкладка (слово владельца «команда за работу дальше по очереди и выкладывай»). T74 (проверка
  перед выгрузкой), T75 (снимок Яндекса: 404, Esri только под дырами, >600 плиток), T76 (дороги без полигонов Яндекса) —
  три роли параллельно. Ревью архитектора: T74, T76 PASS; T75 FAIL по пункту «старые листы — Esri» — снят руководителем
  (владелец 05.10: Безобразово тоже на снимке Яндекса), предупреждение о >600 плитках вынесено в T81. Общий прогон
  упал на t62/t66 (строка T74 перехватывала выгрузку и не закрывалась) — исправлено исполнителем, E2E 375 шагов
  зелёный; unit 437 OK с PYTHONPATH и без, connectors OK. Реальный сценарий: копия «Безобразово» (30.09) — 9 листов,
  дороги на всех (полигонов Яндекса в ТиНАО нет, взяты ЕГКО/оси). Выкладка: main ff → a172ee2 v0.99.8; первая отправка
  оборвалась по сети (msk), повтор `tools/deploy-server.sh` — «Готово: на сервере версия 0.99.8».
RULE: An E2E check must not assume where the territory lies: earlier steps move it (T71 expected ≥ 5 okrug districts,
the run had the territory in a 4-district okrug). Compare with the data of the current territory instead.
RULE: Direct owner-requested changes land on main between cycles; the cycle starts by merging main into the team branch
and resolving conflicts in albums.js / print_io.py by hand (cycle 21: Yandex satellite vs TileGuard, okrugMain vs
simplifyAdm). Never assume the team branch is ahead of main.

- 05.10.2026, цикл 21 — по аудиту КРТ 3229 (`docs/ux/audit-2026-10-05-krt3229.md`). Довели T69–T71 (были не
  закоммичены): ревью архитектора — T69, T71 PASS, T70 FAIL (страница не передавала территорию) — исправлено
  руководителем. Слили main (v0.98.10–0.98.14) в team/t60 с ручным сведением конфликтов. Задачи T72 (граница по номеру
  КРТ, кнопка в «Свойствах») и T73 (поля шапки и автозаполнение) — фронтенд, параллельно; руководитель связал их (номер
  КРТ из поиска — в шапку). Найдена и выложена на сайт ошибка руководителя из main: карта округа теряла районы
  (turf.intersect) — v0.98.13 и v0.98.14. Проверка: путь владельца на тестовой копии (поиск «КРТ 3229» → граница
  1,66 га → «Собрать альбом ППТ КРТ» → 9 листов, шапка «№ 3229 / ВАО, район Гольяново / д. 8»), unit 431 OK с
  PYTHONPATH и без, E2E зелёный (4 прогона: столкновения T73 со старыми шагами T34b/T55/T66 исправлены, T71 — проверка
  переписана, один раз — медленный старт страницы под нагрузкой). Итог v0.99.7 на team/t60, готово к выкладке.
  Дальше: T74 (проверка перед PDF), T75 (снимок Яндекса: 404 и Esri под пропусками), T76 (дороги без полигонов Яндекса).
RULE: The owner's program and the site change only after the owner's word «выкладывай»; all program work happens in
the team worktree `.claude/worktrees/team` on branch `team/grado2`.

RULE: Before taking a status claim from a role, check the changelog entry it cites: the changelog keeps old «not done»
lines under entries that were done later (Э11 was «not done» at line 1513 and done in v0.36.0).
RULE: Social-object placement (T6) starts only after the preset constants audit (T4) and the norms spec with a fixture
test (T5); plot areas are the table minimum «не менее».

RULE: A reviewer's PASS on frontend code is not enough: a function added to a module under `(function(root){…})` is
not global — call it through its exported object, and run the E2E on the combined tree before the commit (T3:
`keepUid is not defined` passed the unit tests and the diff review).
RULE: Agents that share the worktree must not run the E2E on a tree with another agent's unfinished edits; the lead
runs the final gate on the combined tree.
RULE: Norm constants are checked only against decree texts in `docs/standards/moscow-ngp` (audit of 02.10.2026);
the owner sends missing texts as files.

RULE: Starting `apps/grado2/server.py` without a port replaces the owner's server on 8650 — agents always pass an
explicit port ≥ 8660 and `GRADO2_PROJECTS=<temp>`; screenshots for audits are taken from a `git archive` snapshot.
RULE: Anything stored in the undo stack as a full copy must be dropped when its object is replaced from outside
(file, parcels, another person's change) — T16 first version let Ctrl+Z bring an old boundary back over a new one.

RULE: A frontend module must not call the API when the script loads: in hub mode there is no session yet (401) and
the page breaks. Fetch on first use.
RULE: The lead's gate prints the failing step: grep the E2E output for `STEP FAILED` and ` log: ` lines, and a FAILED
gate blocks the commit even when the diff review said PASS (cycle 4: review PASS, both E2E runs failed).

RULE: The lead runs the unit tests WITHOUT `PYTHONPATH` too (as the program starts): a module that imports a core
package not on the server's own `sys.path` list passes with PYTHONPATH and fails in the real program (v0.93.1,
`grado_geom`). A new core package also goes into `packaging/grado2.spec`.
RULE: No inline `<script>` in `index.html`: the page's CSP is `script-src 'self'`; put the code into a file.

RULE: E2E waits for anything that sends the 100 000-object test layer to the server are at least 30 s; a 5 s wait
gave a false failure on a busy machine (v0.95.0).
RULE: Agents never use `git stash` / `git checkout` of files in the shared worktree for «before» screenshots — they
serve a `git archive HEAD` copy on another port.

RULE: A hidden window can keep keyboard focus in its input: a global shortcut handler that skips inputs must still
handle the shortcut that toggles that window (F1 from the help search field, v0.96.0).
RULE: DBF text fields from portals are capped at 254 bytes (≈127 Cyrillic characters): any portal shapefile with long
text needs the attribute refill (CSV/GeoJSON) — check every new document layer for cut values (v0.96.1).

- 04.10.2026, цикл 20 (прерван лимитом сессии ~12:00 MSK) — в team2 (team/t60, после v0.99.6) НЕ закоммичены:
  T69 готова (негативный кэш плиток в print_io.py/sat_io.py, test_print 44 OK, apps 417 OK; ревью и E2E не
  проводились), T70 (server.py/коннекторы) и T71 (albums.js) — исполнители ещё работали. Следующей сессии: прочитать
  `git -C .claude/worktrees/team2 status`, провести ревью T69–T71, общий прогон, коммит v0.99.7; затем слияние
  team/t60 → team/grado2 и выкладка по слову владельца.
- 04.10.2026, цикл 19 (07:00–11:30 MSK, ветка team/t60) — T62 (исполнитель упал на ошибке API, перезапущен с
  сохранёнными правками; ревью FAIL: двойной повтор к порталу → исправлено), T59 (ревью FAIL: права зрителя, нет
  предела → исправлено), осмотр креативного директора v0.99.5 → T67/T68 (ревью FAIL по контрасту подписей →
  исправлено руководителем). Итог v0.99.6: connectors 167 OK, compute 51 OK, apps 416 OK, E2E 363 ok / 0 failed.
  Исполнитель T59 один раз запустил `pkill -f` по ошибке (ничего не задето) — напоминание в брифах.
RULE: Every subagent brief repeats the ban on `pkill -f` and `git stash`/`checkout`; a brief without it is the
lead's fault (cycle 19: one stray `pkill -f`).
RULE: Portal retries live in exactly one place (the connector, with pauses); the page never repeats a failed portal
request itself (T62: 3 × 2 attempts without a pause).
- 04.10.2026, цикл 18 (03:30–07:00 MSK, ветка team/t60) — T6 шаги 3–4 (черновик другой сессии перенесён в team2 и
  доведён; ревью FAIL: таймер по часам → недетерминизм и ложное «не помещается» → бюджет шагов, граница свободной
  земли как препятствие; повторное ревью FAIL: прерванный результат не кэшировался → шторм пересчётов → исправлено
  руководителем), T56 (blocks.js, хук в urbanBlocks; на примере эффекта нет — соседние кварталы; бюджет relax
  переведён на шаги руководителем; вопрос владельцу А/Б/В), T65/T66 (ревью PASS). Итог v0.99.5: apps 413 OK,
  blocks/roles/collab ok, E2E 320 ok / 0 failed. Другая сессия: T6 в `team` без движения с 18:19 03.10 — её
  черновик использован, её рабочая копия не тронута.
RULE: Any search or relaxation that can be cut short is bounded by step counts, never by wall-clock time, and a
cut-short result is cached under the same key (deterministic) — a time bound gives different sketches on different
machines and an uncached partial result re-runs on every render (T6, T56).
- 04.10.2026, цикл 17 (00:40–03:30 MSK, ветка team/t60) — T64 (v0.99.3; ревью PASS, правка руководителя: контуры с
  обводкой не выбрасывать), T61 (ревью FAIL: подмена ключей ломала загрузку листов альбома, K1=1,0 при молчании OSM →
  исправлено), T55 (возврат руководителя до ревью: старые листы сбрасывались бы к шаблону при открытии → только по
  «Обновить листы» с вопросом; опрос заменён хуками; ревью PASS). Итог v0.99.4 (c…): apps 412 OK, E2E 276 ok / 0
  failed (новый харнес: группы t52, t55, t61). Другая сессия: T6 в `team` без движения с 18:19 03.10.
RULE: Any automatic rebuild of the owner's content (sheets, layers, graph) on project open is forbidden: adopt the
current state as the base and rebuild only on an explicit action with a two-click confirmation (T55).
RULE: A layer-key alias (`gisogd.X` ↔ `ogd.X`) is applied only where the user picks from the catalog; code that
loads layers for albums/sheets keeps exact keys (iron rule 5) — T61 first version broke album loads.
- 03.10.2026, цикл 16 (22:30–00:40 MSK, ветка team/t60) — T57 (v0.99.1: стоянки площадью; площадь на место в
  945-ПП нет — допущения 25/30/25 с пометкой), T52+T53+T63 (v0.99.2: док — два окна в зоне, 32 %, вкладки, «Нормативы»
  справа, «Показатели» от 1400 px; ревью PASS; гейт первый раз 249 ok / 4 failed — все четыре в проверках, исправлены
  исполнителем; итог 253 ok / 0 failed, apps 402 OK), T58 (проверка: PPTX из готовой вёрстки 9 слайдов, совместная
  работа с альбомом 17 МБ — PASS; найдены T64 плитки не обрезаны и слайд 2 обычного альбома 159 МБ XML, T65 сборка
  добавляет к импортированным). Другая сессия: правки T6 в `team` без движения с 18:19. Дальше: слияние team/t60 →
  team/grado2 (после T6 или по слову владельца), T55, T61, T62, T64, T65.
- 03.10.2026, цикл 15 (20:40–22:30 MSK) — T60 (v0.99.0): роли слоёв; две правки app.js (robust() отбрасывает кольца
  < 4 точек, EXIST_KEY по роли) сделаны в отдельной рабочей копии `.claude/worktrees/team2` на ветке `team/t60`, чтобы
  не трогать несохранённые правки T6 другой сессии в `team` (без движения с 18:19). Ревью PASS; проверка на копии
  Безобразово с границей КРТ 3141: ЗОУИТ 8 зон из 9 слоёв, вода 3, здания 1541, эскиз 13 корпусов без пересечений с
  водой и домами, консоль чистая; гейт: apps 400 OK, roles 22 ok, E2E 236 ok / 0 failed. Слияние team/t60 →
  team/grado2 — после коммита T6 (ожидается конфликт только в app.js вокруг robust()/EXIST_KEY, легко).
- 03.10.2026, цикл 14 (18:20–20:40 MSK, вторая сессия параллельно с T6) — совещание (продакт, архитектор, креативный
  директор, два круга) → очередь T50–T59 (DECISIONS). T54 (v0.98.5, 1b73e85): альбом — отдельный раздел хаба, meta-правка
  7,9 КБ вместо 19,5 МБ; ревью PASS; гейт на слепке HEAD + 4 файла: apps 395 OK, collab 84, E2E collab OK. T51 часть 1
  (b7502f8): харнес не останавливается на первом сбое, SUMMARY, группы/E2E_ONLY, свободный порт, ожидание готовности;
  полный прогон 236 ok. T50: замер пути на копии проекта сайта — 5,7 мин машинного времени (альбом 4 мин); находка:
  ограничения и здания ищут `gisogd.*`/`nspd.*`/`osm.*`, а проект хранит `ogd.<код>`/`egko.*` — ограничения пустые,
  эскиз на реке; в проекте сайта `territory: null`. → T60 первой, T61–T63. Файлы другой сессии (app.js, index.html,
  scenarios.mjs) не трогались; коммиты path-limited.
RULE: The owner's real projects store catalog layers as `ogd.<code>` and `egko.*`; every feature that looks up a
layer by a fixed key (`gisogd.*`, `nspd.*`, `osm.*`) is silently empty on them — look up layers by role, and test on
the copy of the site project (`/tmp/grado-team/transfer/bezobrazovo.server.grado2`), not only on the example.
- 03.10.2026, цикл 13 (19:50–20:45 MSK) — T6 шаг 2 (фронтенд: «Условия проекта» в «Нормативах»; ревью PASS с тремя
  правками: ключ «Вариантов» учитывает свободные места, текст источника зоны выводится из состояния, а не из серверной
  строки, `tepParams` не дописывает ключи при чтении). Снимок владельческого прогона 0.98.3 на `git archive` (1d0843b):
  владельческий OK; совместный упал на первом шаге и прошёл отдельно (гонка списка проектов при двух сценариях подряд).
  Итог: v0.98.4 (61e5c92), apps 391 OK, E2E оба сценария OK, console clean.
RULE: `test_e2e.py` prints only the last 4000 characters of a scenario's output: a step near the start of
`scenarios.mjs` never shows an «ok» line in the log — a green run is the proof, not the grep.
- 03.10.2026, цикл 12 (18:55–19:50 MSK) — T38 (решение «карта Б, Carto»: плитки CARTO пришли заглушками «API KEY
  REQUIRED» — проверено curl и снимком; заменено на Esri Canvas World_Dark_Gray_Base, проверено z10–17; ревью руководителя),
  T6 шаг 1 (архитектор разбил задачу на 4 шага — plan-T6.md; бэкенд: пресет + /api/tep + place_info; ревью PASS с правкой
  руководителя: свободные места — только целые). Итог: v0.98.3 (1d0843b), compute 51 OK, apps 391 OK (без PYTHONPATH),
  E2E оба сценария OK, console clean. Внутренние решения по вопросам архитектора — в plan-T6.md.
RULE: An external tile or data service is checked with one real request (size and a look at the tile) before it is
wired in: CARTO basemaps returned HTTP 200 with an «API KEY REQUIRED» placeholder (03.10.2026).
RULE: Reviewers never run `git stash` in the shared worktree, even «for a probe» — it reverts other agents' work under a
running E2E (03.10.2026, restored by pop; that gate stayed green, so it was not repeated).
- 03.10.2026 (18:50 MSK), выкладка по слову владельца — v0.98.2: main чистый, team ← main (20bf925, только docs/team),
  unit 388 OK, main ← team/grado2, «Готово: на сервере версия 0.98.2», main отправлен. Ответы владельца: 1В 2А 3А 4А 5А,
  карта Б (CARTO) → T6 открыт, T38 добавлен.
- 03.10.2026, цикл 11 (17:20–18:40 MSK) — T5 (нормоконтроль: спецификация соцобъектов, пример 20 га, тест 4 OK; пять
  вопросов владельцу и три архитектору — в BOARD «Ждёт владельца»), T30 (креативный директор: осмотр тёмной темы на 1280
  и 2560, спецификация; фронтенд: мелочи T28-4/5/6 + обязательные правки тёмной темы; ревью FAIL дважды по масштабу
  графа — обрезка заголовка слоя и вставка узла зависели от --k и меняли файл проекта → исправлено, проверено равенством
  serialize() при k=1 и 7/6; карта в тёмной теме — вопрос владельцу А/Б/В), T37 (справка под v0.98.0). Итог: v0.98.2
  (2e68d6b), unit 388 OK (без PYTHONPATH), compute OK, E2E оба сценария OK, console clean.
RULE: Anything litegraph draws from a size-dependent constant (`--k`) must be stored at scale 1: titles truncated with
`fitText`, node sizes, pasted/cloned nodes (`onConfigure`) — check `JSON.stringify(graph.serialize())` equal at k=1 and 7/6.
- 03.10.2026 (17:15 MSK), выкладка по слову владельца («выкладывай и продолжай по задачам») — v0.98.1: main чистый,
  team/grado2 ← main (8fcdcb8, только docs/team), unit 388 OK, collab 79 (программа та же, что в зелёном прогоне E2E
  цикла 10), main ← team/grado2, скрипт выкладки: «Готово: на сервере версия 0.98.1», main отправлен.
- 03.10.2026, цикл 10 (16:00–17:10 MSK) — T35 (сведение альбома по листам, ревью PASS с правкой: списки без id —
  целиком; collab 79 проверок) и T36 (хвосты меню «Выгрузка»; ревью FAIL по тесту — гонка с настоящей выгрузкой Excel
  → заглушка fetch). Общий прогон падал четыре раза подряд по трём разным причинам: (1) шаг T34 сравнивал строку
  состояния с зашитыми датами, а `editedAt` ставится настоящим временем — после 13:07 MSK 03.10 шаг стал красным
  навсегда (тест); (2) `\/` внутри шаблонной строки теста — «Invalid regular expression flags» (тест); (3) настоящая
  ошибка: Enter на пункте открытого меню «Выгрузка» уходил в обработчик карты «повторить команду» (cad.js), пункт
  не выбирался; затем фокус не возвращался при мгновенной выгрузке (скрытый пункт ещё в activeElement). Итог:
  v0.98.1 (78d7f31), unit 388 OK (без PYTHONPATH), collab 79, E2E оба сценария OK, console clean. Указание владельца
  по T34 принято: перенос уже сделан ночью. Дальше: T30 (тёмная тема, остатки), T6 после T5.
RULE: E2E steps never compare with hard-coded dates while the program stamps the real time (`editedAt`, `builtAt`):
clear or stub the stamps first — the T34 step turned red by itself after 13:07 on 03.10.2026.
RULE: Inside a template literal passed to `p.ev`, write regexes as `/api[/]print[/]pdf/` or `\\/`: a single `\/` is
unescaped to `/` and the page throws «Invalid regular expression flags».
RULE: Keyboard activation of any menu item is tested with a real key event (`p.key("Enter")`), not `.click()`:
the map's global keydown handler (cad.js) can swallow Enter/Space for new menus and buttons.
- 03.10.2026, цикл 9 (02:56 MSK, записано в 16:00 следующим циклом) — T32 + T33 (v0.98.0, 5710e85): перевёрстка окна «Листы и
  альбом» и меню «Выгрузка». Прогон руководителя: unit 388 OK, collab 66; владельческий сценарий E2E дважды красный на
  разных шагах (AE массив; T33 строка «Альбом» в «Проектах» — ложная, кэш списка по mtime), после правки теста и ключа
  кэша два прогона подряд OK (163 с, 154 с). Выложено по стоящему слову владельца: main ← team/grado2 (92bd896), «Готово:
  на сервере версия 0.98.0». Открытое из записи журнала версии: фокус не возвращается на кнопку после пункта меню; `peak` —
  последнее число, не максимум; PDF/PPTX в меню не серые во время сборки → T36.
- 03.10.2026 (02:18 MSK), выкладка v0.97.0 и перенос альбома по слову владельца («выкладывай и переноси как
  закончишь»). Выкладка: main ← team/grado2 (eb3c2d9), «Готово: на сервере версия 0.97.0». Перенос на сервере
  (Mac → msk → grado, как root): условие — автосохранение старше 10 мин и 0 соединений с :8650 (вкладка закрыта);
  бэкапы `/var/lib/grado/projects/.bak/Безобразово.grado2.bak-20261002-2318` и `autosave.grado2.bak-20261002-2318`;
  `transfer_album.py` (копия логики importAlbum «заменить») применён к проекту и к автосохранению: 1 → 9 листов
  (8 frozen), 36 слоёв без изменений, 16 → 34 МБ; атомарная подмена, chown grado, 600. Откат: `cp` бэкапа на место.
RULE: Project files on the site (`/var/lib/grado/projects`, local mode, not hub) are edited only by the lead with the
owner's word: plan first, backup to `.bak/`, atomic replace, the owner's tab closed (browser autosave would overwrite),
verification, rollback path. Subagents never touch them.

- 03.10.2026, цикл 8 — T31 (v0.96.3, ревью PASS с правками руководителя: blur только окна, выделение в таблице не
  теряется от кнопки), T34 (v0.96.3 статус; v0.97.0 импорт — ревью FAIL: зритель, Esc, размер → исправлено; на файлах
  владельца 9 листов, PDF 9 стр., стр. 2 совпадает с его PDF попиксельно). Разведка сервера: сайт в локальном режиме,
  «Безобразово» 1 лист с 29.09 — альбом туда никогда не попадал, собирался на Mac в проекте «КРТ 3141 проверка».
  Спека T32/T33 готова, перевёрстка в работе. Прогоны: 385 unit OK, collab 66, E2E оба сценария OK.
- 03.10.2026, выкладка по слову владельца — v0.96.2: прогон в ветке (apps 384, connectors 162, compute 46, render
  73, collab 66, E2E оба сценария OK), main ← team/grado2 (3141fd7), скрипт выкладки: «Готово: на сервере версия
  0.96.2», main отправлен. Новые замечания владельца по сайту (на 0.93.0): выделение текста при перетаскивании, окно
  «Листы и альбом», три похожие кнопки, где итоговая вёрстка Безобразово → T31–T34.
- 03.10.2026, цикл 7 — пара. Сервер: v0.95.1 ToUnicode в PDF (ревью руководителя, 73 render OK). Интерфейс (v0.96.0):
  тёмный граф, справка, путь новичка, колесо; ревью FAIL (цвета темы попадали в проект) → исправлено исполнителем с
  доказательством равенства сохранённого графа в обеих темах; прогон упал дважды на F1 из поля поиска (окно скрыто,
  фокус в поле) — исправлено руководителем; проверка приветствия сведена к видимому. Владелец 03.10: названия ППТ
  обрезаны → T29: причина — DBF 254 байта; сервер v0.96.1 (ревью FAIL: безграничный повтор CSV и старый кэш →
  исправлено: cooldown 1 ч, `lines2`), интерфейс в работе (убрать «…», перенос, продолжение списка на следующем
  слайде). Итог прогонов: 381 unit OK, connectors 162 OK, collab 66 ok, E2E оба сценария зелёные.
- 03.10.2026, цикл 6 — пара «сервер + интерфейс». Сервер (v0.94.1, c30baa2): участки ДОО, школ, поликлиники как
  показатели ТЭП (сверка нормоконтролёра по тексту — PASS по всем 10 константам), выгрузка GeoJSON устойчивее.
  Интерфейс (v0.95.0, 8598739): меню выгрузок у DXF, район по доле площади, столбцы у всех вариантов, масштаб схемы
  расчёта, поиск по слоям. Ревью PASS; прогон руководителя один раз упал на ожидании 5 с выгрузки слоя в 100 000
  объектов — ожидание увеличено, три мелких замечания ревью исправлены руководителем. Итог: 381 unit OK (без
  PYTHONPATH), compute 46 OK, collab 66 ok, 2 прогона E2E зелёные. Решения команды: школа — один объект, ДОО свыше 350
  мест делится, сокращение участка до 10 % не учитывается; «Слои» и «Свойства» на 1481–2000 px ушли в «Окна».
- 02.10.2026, цикл 5 — пара «сервер + интерфейс». Сервер (v0.93.1, c036320): `/api/export/geojson`,
  `/api/export/xlsx`, `/api/place` с полигоном, разбивка спорта; ревью PASS, но прогон руководителя без PYTHONPATH
  упал (`No module named grado_geom`) — исправлено (sys.path, spec установщика). Интерфейс (v0.94.0, 964838b): масштаб
  по `--k`, панели clamp, «Размер интерфейса», 840 px, `syncVarTep`, подсказка слоёв; ревью PASS, но оба прогона E2E
  упали на CSP (встроенный скрипт) — вынесен в `uisize.js`. После исправлений: 374 unit OK, compute 41 OK, collab 66 ok,
  2 прогона E2E зелёные; снимки 2560 и 840 просмотрены. Дальше: T24 + T25 парой, затем T26, T7.
RULE: Probes of grado.tailink.tech from the Mac are unreliable (the Mac goes out through a VPN; half of the requests
time out before connecting). The landing is confirmed by the deploy script's own health check («Готово: на сервере
версия X»), not by curl from the Mac.

- 02.10.2026, выкладка по слову владельца — v0.93.0: main чистый, полный прогон в ветке (connectors 150, compute 40,
  apps 360, collab 66, E2E 2 сценария — OK), `git merge --ff-only team/grado2` → main 88e5cd2, скрипт выкладки:
  «Готово: на сервере версия 0.93.0», main отправлен на GitHub. Указание владельца: продолжать, пока весь интерфейс
  не исправлен, бэкендер и фронтендер в связке.
- 02.10.2026, цикл 4 — T13 шаг 2, T18, T19, T15 приняты (v0.93.0, 528c736). Ревью архитектора PASS, но общий прогон
  упал дважды на «A: список проектов пуст»: `norms.js` запрашивал `/api/tep/norms` при загрузке страницы, до входа в
  совместном режиме — 401. Исправлено руководителем (запрос при первом расчёте или открытии окна), добавлен минимум
  160 × 120 для плавающего окна. Проверка после исправления: 360 unit OK, collab 66 ok, compute 40 OK, 2 прогона E2E
  подряд зелёные; снимки окна «Нормативы» (1280, 840) и плавающего окна на 1280×720 просмотрены. Открыто: T22
  (варианты после смены норматива), T23 (пометка в выгрузках), T20, T21. На порту 8672 с 30.09 висит чужой тестовый
  сервер (pid 99191) — не трогали.
- 02.10.2026, цикл 3 — указания владельца: правка границы и привязка к ней (T16), интерфейс на разных экранах (T17),
  нормативы вручную (T13). T16 принята со второго захода (v0.92.0, b2edc4e): первый FAIL архитектора — записи отмены
  правки вершин переживали замену границы; исправлено, плюс запрет зрителю в самой правке, отказ на
  самопересечение, замер привязки 0,13 мс на 5000 вершин. T13 шаг 1 (v0.91.4, 5487b43): `constants_meta`,
  `GET /api/tep/norms`, `constants` в `POST /api/tep`; FAIL архитектора (10**400 → 500) исправлен руководителем.
  T17: аудит на 5 размерах окна (e7b31af), правки T18–T21. Проверка на общем дереве: 360 unit OK, collab 66 ok,
  compute 40 OK, 2 прогона E2E подряд зелёные; снимки границы с ручками и маркера привязки просмотрены. Не проверено:
  второй живой участник совместной работы, Retina, тёмная тема. Дальше: T13 шаг 2 (окно «Нормативы»), T18, T19.
- 02.10.2026, цикл 2 — T2, T3, T4 приняты; указание владельца о ручной правке нормативов → T13 первой в очереди.
  T2: сбой сценария — клик по «Доступ» попадал в «Историю», пока шапка сдвигалась ~30 мс; сценарий ждёт устойчивую
  кнопку (hub.js не менялся; сдвиг — T15). T3: `mergeDownload` переносит `_uid` на совпавший объект (`Collab.keepUid`);
  первая версия падала в браузере (`keepUid is not defined`), исправлено руководителем. T4: 34 константы подтверждены
  текстами, включая спорт по 1557-ПП из PDF владельца; не проверены только проектные допущения (k_flats, k_np,
  плотность ИЖС) и правила владельца. Проверка на общем дереве: 355 unit OK, collab 66 checks ok, connectors 150 OK,
  3 прогона E2E подряд зелёные (плюс 5 прогонов сценария у исполнителя). Журнал PROGRESS.md теперь в git (слово
  владельца). Дальше: T13 (нормативы вручную), T15, T5.
- 02.10.2026, цикл 1 — задачи T1 и T2 (частично). T1: совещание продакта, архитектора, нормоконтролёра и креативного
  директора в два круга; план сверен с v0.91.1 (новый раздел «Where we are (02.10.2026)» в ветке команды, 532d0e5),
  очередь T2–T12 в BOARD, решение в DECISIONS. T2а: ошибка 500 ленты событий в unit-тестах — поток пережил подмену
  хаба тестом; обработчик держит свой хаб (v0.91.2, 2180962). Проверка: 3 прогона unit-тестов по 355 — OK, без
  `session_user`; ревью архитектора PASS (прод не меняется). Браузерные сценарии: 4 прогона из 5 зелёные, один упал на
  `#hubShareLogin` — это остаток T2. Дальше: T2 (стабильность сценария), T3 (`_uid` ЕГРН), T4 (сверка констант).
- 02.10.2026 — команда создана: роли в `.claude/agents/grado-*.md`, порядок цикла в `docs/team/CYCLE.md`,
  рабочая копия `.claude/worktrees/team` на ветке `team/grado2` (от main 2c9c6ea, v0.91.1). Первая задача — T1.
