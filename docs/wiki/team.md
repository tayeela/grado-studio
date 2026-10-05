<!-- генерируется tools/wiki.py — не править руками -->

# Команда: что ждёт, что в очереди, что готово

Источник — docs/team/BOARD.md и PROGRESS.md (там же полные тексты).

## Ждёт владельца

- T85f (правки владельца по ролям листа, `docs/team/spec-T85-layer-roles.md`): А (рекомендация) — переключатели ролей
  в настройках выбранного листа («Дороги: ЕГКО / Яндекс / не показывать»); Б — только автоматический выбор; В —
  переключатели в окне «Данные», общие для всех листов.


- T56 (инсоляция соседних кварталов): А (рекомендация) — переключатель в «Эскизе» «Понижать этажность ради
  инсоляции соседей», по умолчанию выключен; Б — всегда (−15 % площади, +11 с); В — не делать, оставить
  предупреждения проверки норм.

## В работе

(пусто)

## Очередь

- [ ] T85a | grado-frontend | легенда только из нарисованного: лист 5 (застройка, границы участков), 7 (нет ППТ и ПМТ), 8 (ГПЗУ) — правило 7 | проверка: КРТ 3229, Безобразово | файлы: apps/grado2/web/albums.js
- [ ] T85b | grado-frontend | места подписей рек не зависят от порядка расчёта листов (правило 0) | проверка: тест + листы 5–9 | файлы: apps/grado2/web/albums.js (waterLabels)
- [ ] T85c | grado-frontend | общая таблица стилей и only листов ППТ КРТ вместо копий (вид не меняется) | файлы: apps/grado2/web/albums.js
- [ ] T85d | grado-frontend + grado-backend | на листе видны выбранный источник и покрытие ролей; предупреждение об окне Яндекса; «нет в природе» ≠ «не скачалось» | файлы: albums.js, sheets.js
- [ ] T85e | grado-frontend | двухфазная выгрузка: запасные источники только для ролей, где основной не прошёл | файлы: sheets.js (buildSection0), albums.js
- [ ] T77 | grado-frontend | okrugMain кэшируется; районы по углам листа — по рамке МСК, а не по рамке в градусах (анклав на карте Москвы остаётся — владелец 05.10) | файлы: apps/grado2/web/albums.js
- [x] T67 — v0.99.6: цвета участков по темам, подписи вида, легенда. | участки резерва: свои цвета для тёмной темы, бирюзовый
  в светлой — не цвет штриховки; подпись вида на участке («ДОО», «школа», «поликлиника»); легенда трёх видов в
  «Предпросмотре схемы» и в слое «Участки и улицы эскиза» | проверка: 1:5 000 и 1:2 000 в обеих темах участки
  отличимы от штриховки и зданий, легенда из трёх видов | файлы: apps/grado2/web/app.js (GROUND, groundStyle)
- [x] T68 — v0.99.6. | значок «не готов» у листа — цветом предупреждения (`--warn`), не серым; подписи «Роль в
  расчётах» и «Подписи этажности» в правом доке не обрезаются; слова «нет в текстах репозитория» и
  «docs/standards/moscow-ngp» в «Нормативах» → «проектное допущение» и названия постановлений | проверка: снимки 1440
  обеих тем | файлы: index.html, norms.js, moscow_calc2.json (meta-тексты)
- [x] T66 — v0.99.5 кроме подсказки о третьем окне (раз навсегда). | grado-frontend | мелочи после ревью T52–T55: подсказка о третьем окне — раз за сеанс, не навсегда; отсечка
  подписей этажности настраиваемая; «Листы обновлены» только когда лист реально изменился; размер старого листа после
  «Обновить листы» сохраняется | проверка: сценарии | файлы: web/app.js, layers.js, sheets.js
- [x] T64 — v0.99.3 (team/t60): плитки обрезаны рамкой, тяжёлые слайды растрируются. | grado-backend | PPTX: спутниковые плитки слайда «Ортофотоплан» не обрезаны рамкой карты — лезут под легенду и
  заголовок (и в обычном альбоме); слайд 2 обычного альбома — 244 тыс. фигур и 159 МБ XML, LibreOffice не открыл за 9
  минут: упрощать геометрию/растрировать подложку слайда | проверка: слайд 9 обрезан, слайд 2 < 5 МБ XML и открывается |
  файлы: apps/grado2/album_io.py, print_io.py
- [x] T65 — v0.99.5: сборка при чужих листах спрашивает «заменить / добавить». | grado-frontend | «Собрать → Альбом ППТ КРТ» при уже импортированных листах добавляет 9 к 9 (18) вместо
  вопроса «заменить / добавить» | проверка: сценарий — импорт, затем сборка — вопрос, итог 9 | файлы: web/sheets.js
- [x] T60 — v0.99.0 на ветке team/t60 (слить в team/grado2 после сохранения T6 другой сессией): слои по роли, ограничения и эскиз работают на проекте Безобразово. | grado-backend + grado-frontend | ограничения, здания и эскиз не видят слои настоящего проекта: «Ограничения»
  читают `gisogd.pzz_sub`, `gisogd.func_zones`, `nspd.zouit`, `gisogd.okn`, `gisogd.red_lines`, здания — `nspd.buildings` /
  `osm.buildings`, а проект Безобразово хранит слои каталога `ogd.<код>` (virtual130 ПЗЗ, virtual1977… Генплан, zu_…
  участки, ЗОУИТ…) и `egko.buildings/water/green/roads` — все 7 слоёв ограничений пустые, 3566 зданий не учитываются,
  эскиз ставит 206 домов на реку и деревни. Сделать реестр ролей слоёв (роль ← ключ источника по таблице кодов каталога
  + ручное назначение роли в свойствах слоя), ограничения/здания/эскиз/ТЭП берут слои по роли; вода и существующая
  застройка ЕГКО — запреты для эскиза | проверка: копия проекта Безобразово (/tmp/grado-team/transfer/*.grado2):
  «Рассчитать ограничения» даёт непустые ЗОУИТ/ПЗЗ/Генплан, здания 3566 учтены, эскиз не заходит на воду; тест ролей |
  файлы: apps/grado2/web/constraints.js, новый web/roles.js, server.py (таблица кодов), app.js (EXIST_KEY — после T6)
- [x] T61 — v0.99.4 (team/t60): повторная выгрузка без дубля, имя слоя и проценты в строке состояния, «район» завершается за 30 с, ошибки портала по-русски. | grado-frontend + grado-backend | повторная выгрузка слоя добавляет дубль (36 → 37) и идёт 34 с с надписью
  «Выгрузка идёт» без имени слоя и процентов; район «определяется…» не завершается; сырая ошибка Overpass на экране |
  проверка: повторная выгрузка — тот же слой обновлён, число слоёв прежнее, строка «ГПЗУ (ОГД): 42 %» | файлы: web/app.js,
  server.py
- [x] T62 — v0.99.6: ход сборки по листам, «Остановить», повторы OSM на сервере, причины «не поместились»; OSM-запрос 30 с убран. | сборка «Альбома ППТ КРТ» 4 минуты с одним «Собираю…»: ход по листам
  («лист 3 из 10: ситуационный план»), повтор Overpass при 504 с паузой, листы 6 и 10 «не поместились» — причина в
  строке состояния | проверка: прогон на копии Безобразово — ход виден, 504 повторён, причины названы | файлы:
  web/albums.js, sheets.js, server.py
- [x] T63 — в v0.99.2 («Показатели» в строке от 1400 px). | grado-frontend | «Показатели» на 1440 px нет в верхней строке (только через «Окна»); док в 280 px с кнопкой
  запуска ниже сгиба — учесть в T52 | проверка: 1440×900, кнопка видна | файлы: web/index.html, app.js
- [x] T50 — замер сделан: docs/ux/run-2026-10-03-bezobrazovo.md; машинного времени 5,7 мин (из них сборка альбома 4 мин), главная помеха — ограничения пустые на слоях `ogd.*`/`egko.*` (T60). | grado-qa | замер реального пути на границе Безобразово (копия проекта сайта): граница → данные → ограничения →
  эскиз → варианты → показатели → альбом PDF/DXF; секундомер, список того, что мешает, консоль чистая |
  проверка: файл docs/ux/run-2026-10-03-bezobrazovo.md с временем каждого шага и списком помех | файлы: docs/ux/*
- [x] T51 (часть 1 сохранена: driver.mjs, test_e2e.py; разрез на файлы и группы в scenarios.mjs — после выкладки T6) | grado-architect + worker | прогон сценариев в браузере: не останавливаться на первом сбое, печатать имена
  всех упавших шагов, выбор по тегам (`E2E_ONLY=…`), свободный порт Chrome, ожидание готовности вместо 2,5 с; разрез
  scenarios.mjs на параллельные файлы и дым-набор — после выкладки T6 (файл правит другая сессия) | проверка: один
  намеренно красный шаг виден по имени, остальные идут; выбор по тегу < 30 с | файлы: tests/e2e/driver.mjs, test_e2e.py
- [x] T54 — v0.98.5: альбом — отдельный раздел совместного проекта; правка параметров шлёт 7,9 КБ вместо 19,5 МБ. | grado-backend + grado-frontend | альбом в отдельный раздел совместной работы (`meta` сейчас несёт 18 МБ при
  каждой правке; миграция разделов), замер размера отправки с альбомом 17 МБ | проверка: правка ТЭП отправляет < 100 КБ;
  collab_test, test_hub | файлы: apps/grado2/hub.py, web/collab.js, tests
- [x] T52 — v0.99.2 (team/t60): не больше двух окон в зоне, нижняя зона 32 %, вкладки с подписями, «Нормативы» справа, «Показатели» в строке от 1400 px. | grado-frontend | док не теснит карту: не больше двух окон в зоне (третье — вкладка или
  плавает), нижняя зона ≤ 32 % высоты, вкладки дока с подписями, «Нормативы» в правом доке по умолчанию; обратимо через
  «Окна»; после выкладки T6 | проверка: 1440×900, «Данные» + «Эскиз» + «Листы» открыты — карте ≥ 55 % высоты, граница
  видна целиком; снимки светлая/тёмная | файлы: apps/grado2/web/app.js, index.html, norms.js
- [x] T53 — v0.99.2: мелочи CSS сделаны. | grado-frontend | мелочи CSS: тень/полоса прокрутки у панелей дока, шапка «Вариантов» в одну строку
  («Перебор типологий»), пустые «Листы» («Листов пока нет. Добавьте лист или соберите альбом», «ППТ КРТ» неразрывно,
  строка «Штамп: ПП» как обычный заголовок), подписи эскиза «12 эт.» только при приближении, штриховка пятна светлее |
  проверка: снимки 1440 | файлы: index.html, sheets.js, app.js
- [x] T55 — v0.99.4 (team/t60): листы по шаблону обновляются сами, ручные правки сохраняются, старые листы — только по «Обновить листы». | grado-frontend | листы альбома по шаблону обновляются после смены ТЭП, нормативов или эскиза
  (рамка, масштаб, фото сохраняются; готовая вёрстка из файла не трогается) | проверка: сменить норматив → ТЭП на листе
  обновился; импортированные листы без изменений | файлы: web/albums.js, sheets.js, print_io.py
- [x] T58 — PASS: PPTX 9 слайдов из готовой вёрстки, совместная работа с альбомом 17 МБ (meta-правка 6 КБ); найдено T64–T65 (docs/ux/check-2026-10-03-pptx-collab.md). | grado-qa | PPTX из листов готовой вёрстки открывается, 9 слайдов совпадают с PDF; совместная работа вдвоём с
  альбомом 17 МБ | проверка: тест выгрузки PPTX; двухпользовательский сценарий | файлы: tests
- [x] T56 (частично) — v0.99.5: поквартальное понижение этажности; на примере не помогает (тени соседних кварталов) — решение владельца А/Б/В в отчёте. | grado-gis | северные стороны урбан-блоков: 5 корпусов на площадке Э8 с < 50 % инсолируемых фасадов доходят
  до нормы | проверка: тесты инсоляции зелёные, площадка Э8 | файлы: core/compute/*, web/analysis.js
- [x] T57 — v0.99.1 (team/t60): стоянки площадью, доли подземных/многоуровневых в «Нормативах». | grado-backend | стоянки как требуемая площадь (наземные, подземные, многоуровневые) в «Показателях» по
  945-ПП | проверка: фикстура 945-ПП, число сходится вручную | файлы: moscow_calc2.json, server.py, tests
- [x] T59 — v0.99.6: сохранённые варианты (до 20), группа «Сохранённые», выбор в «Сравнении». | вариант, отредактированный вручную, сохраняется под именем и остаётся в «Сравнении» |
  проверка: правка → имя → перезагрузка → в сравнении с ТЭП | файлы: web/app.js
- [x] T6 — шаги 3–4 в v0.99.5 (team/t60): участки ДОО/школ/поликлиник на эскизе, строка «Резерв» в «Показателях». | grado-backend + grado-frontend | решения владельца 03.10: 1В зона норм — выбор в окне «Нормативы»
  (по умолчанию из района, если он в списке 2151-ПП, иначе зона 2 с пометкой); 2А свободные места — три числа вручную в
  «Нормативах», по умолчанию 0; 3А ОВЗ не прибавлять; 4А встроенные ДОО не резервировать; 5А школа — всегда один участок.
  Шаг 1 — архитектор делит задачу на шаги с проверкой; дальше — по шагам | проверка: числа примера из
  docs/team/spec-T5-social-objects.md (test_social_fixture.py) сходятся через программу; эскиз резервирует участки, ТЭП
  показывает их | файлы: core/compute/*, apps/grado2/server.py, web/analysis.js, web/norms.js, web/app.js
- [x] T31 — v0.96.3: протаскивание не выделяет текст. | grado-frontend | владелец 03.10: при растягивании окон, панелей и протаскивании мышкой беспорядочно
  выделяется текст — при любом перетаскивании (заголовок окна, разделители панелей, ручки размера, ползунки, холст
  графа, перетаскивание слоёв) выделение текста выключено, после отпускания возвращается | проверка: сценарий —
  тащить заголовок и разделитель через текст, `getSelection().toString()` пустой; снимок | файлы: apps/grado2/web/*
- [x] T34 — v0.96.3 строка состояния, v0.97.0 «Листы» → «Из файла…» (готовая вёрстка из файла, проверено на файлах владельца); перенос в «Безобразово» — руководитель на сервере после выкладки. | grado-frontend | владелец 03.10: «не вижу, где в Безобразово сохранена наша итоговая вёрстка» — разобраться,
  как и где проект хранит альбом (листы, макет, собранный PDF/PPTX), почему в окне «Листы» на сайте виден только
  «Лист 1»; в окне показать строку состояния альбома («Альбом: N листов, собран дд.мм.гггг чч:мм», «PDF не собирался»)
  и путь к последнему файлу | проверка: сценарий — собрать альбом ППТ КРТ, сохранить, открыть заново — листы и строка
  на месте | файлы: apps/grado2/web/sheets.js, albums.js, project.js
- [x] T32 — v0.98.0 (выложено 03.10): окно «Листы и альбом» перевёрстано по спецификации docs/ux/spec-2026-10-03-sheets-and-exports.md. | grado-frontend | владелец 03.10: окно «Листы и альбом» неудобное и странно свёрстано
  (снимки владельца 03.10: поля «Шифр», «Организация» уезжают влево при узкой панели, таблица листов с горизонтальной
  прокруткой, кнопки «Добавить лист / слайд / Раздел / Альбом ППТ КРТ / Ситуационный план / PPTX / PDF» россыпью) —
  спецификация, затем перевёрстка | проверка: снимки 1280×720, 1440×900, 2560 в доке снизу и справа, без
  горизонтальной прокрутки | файлы: apps/grado2/web/sheets.js, index.html
- [x] T33 — v0.98.0 (выложено 03.10): две кнопки «Листы и альбом» и «Выгрузка ▾» с меню из шести пунктов. | grado-frontend | владелец 03.10: три кнопки «Листы», «DXF», «DXF ГИС ОГД» похожи по смыслу
  и не понятны — одна кнопка «Листы и альбом» (печать) и одно меню «Выгрузка» с понятными подписями и пояснениями
  (чертёж DXF, слои ГИС ОГД в DXF, GeoJSON для QGIS, Excel ТЭП) | проверка: снимок верхней строки на 1280 и 1920,
  подсказки при наведении | файлы: apps/grado2/web/index.html, app.js
- [x] T29 — v0.96.1 + v0.96.2 (выложено 03.10): полные названия ППТ с портала, без «…» в альбоме. | grado-frontend | указание владельца 03.10: название ППТ в презентации КРТ всегда полное и
  как на ГИСОГД. Причина: shape-выгрузка портала режет `document_1` до 254 знаков (DBF), 216 из 530 ППТ обрезаны;
  плюс `docTitle` в albums.js добавляет «…» от 120 знаков. Сделать: полные названия документов из выгрузки портала с
  атрибутами (CSV/GeoJSON по `gisguid`), «…» убрать, длинное название переносится целиком на слайде и листе |
  проверка: тест коннектора на записи длиннее 254; слайд с названием 498 знаков — текст целиком, без «…» | файлы:
  core/connectors/grado_connectors/gisogd.py, apps/grado2/server.py, web/albums.js, print_io.py
- [x] T6 (старая строка, см. выше) | grado-backend | шаг 2 соцобъектов: «Посадка» резервирует участки ДОО/школы/поликлиники, когда дефицит не
  покрыт; после T2 и T5 | проверка: тестовый участок ТиНАО, дефицит мест до > 0, после = 0, ТЭП сходится вручную |
  файлы: core/compute/*, apps/grado2/web/analysis.js, tests

## Готово к выкладке

- v0.99.12 (T84): на векторных схемах (листы 4–8) дороги — полигоны ЕГКО, без дорог по осям, слитые без швов и
  мелкого мусора; на снимках — полигоны Яндекса.

- v0.99.10–0.99.11 (цикл 24): станции метро и МЦК — красная «М», МЦД — параллелограмм диаметра; название всегда
  красное с белой обводкой и всегда рядом со значком, в легенде «Транспорт» — только то, что на листе; вложенные кавычки „лапками“.

- v0.99.9 (team/t60, цикл 23): станции подписаны «ст. ж/д …»; подписи не ложатся на железную дорогу и границу района;
  выноски не заходят на угловые надписи; «ёлочки» вместо прямых кавычек; лист Генплана — цвета зон по таблице и знаки
  с индексом в легенде; пометка «снимок грубее обычного» на очень больших листах; тесты на правки альбома.

## Правила команды (RULE из PROGRESS.md)

- Cycle start = `git merge main` in the team branch → `tools/gate.sh` → read `docs/wiki/INDEX.md` and `docs/wiki/team.md`; agent briefs come from `docs/team/prompts/` and cite wiki pages instead of pasting file ranges.
- A feature that reads portal data is checked on one live (cached) object before it is accepted: unit tests on fake data passed for T82 while the real Yandex points carry the name in «Название», not `name`, and no icon was drawn.
- Any new choice bar in «Листы и альбом» closes the pending one (only one bar at a time) and old E2E steps that export on purpose pass `force` — T74's export gate broke t62/t66 until then.
- An E2E check must not assume where the territory lies: earlier steps move it (T71 expected ≥ 5 okrug districts, the run had the territory in a 4-district okrug). Compare with the data of the current territory instead.
- Direct owner-requested changes land on main between cycles; the cycle starts by merging main into the team branch and resolving conflicts in albums.js / print_io.py by hand (cycle 21: Yandex satellite vs TileGuard, okrugMain vs simplifyAdm). Never assume the team branch is ahead of main.
- The owner's program and the site change only after the owner's word «выкладывай»; all program work happens in the team worktree `.claude/worktrees/team` on branch `team/grado2`.
- Before taking a status claim from a role, check the changelog entry it cites: the changelog keeps old «not done» lines under entries that were done later (Э11 was «not done» at line 1513 and done in v0.36.0).
- Social-object placement (T6) starts only after the preset constants audit (T4) and the norms spec with a fixture test (T5); plot areas are the table minimum «не менее».
- A reviewer's PASS on frontend code is not enough: a function added to a module under `(function(root){…})` is not global — call it through its exported object, and run the E2E on the combined tree before the commit (T3: `keepUid is not defined` passed the unit tests and the diff review).
- Agents that share the worktree must not run the E2E on a tree with another agent's unfinished edits; the lead runs the final gate on the combined tree.
- Norm constants are checked only against decree texts in `docs/standards/moscow-ngp` (audit of 02.10.2026); the owner sends missing texts as files.
- Starting `apps/grado2/server.py` without a port replaces the owner's server on 8650 — agents always pass an explicit port ≥ 8660 and `GRADO2_PROJECTS=<temp>`; screenshots for audits are taken from a `git archive` snapshot.
- Anything stored in the undo stack as a full copy must be dropped when its object is replaced from outside (file, parcels, another person's change) — T16 first version let Ctrl+Z bring an old boundary back over a new one.
- A frontend module must not call the API when the script loads: in hub mode there is no session yet (401) and the page breaks. Fetch on first use.
- The lead's gate prints the failing step: grep the E2E output for `STEP FAILED` and ` log: ` lines, and a FAILED gate blocks the commit even when the diff review said PASS (cycle 4: review PASS, both E2E runs failed).
- The lead runs the unit tests WITHOUT `PYTHONPATH` too (as the program starts): a module that imports a core package not on the server's own `sys.path` list passes with PYTHONPATH and fails in the real program (v0.93.1, `grado_geom`). A new core package also goes into `packaging/grado2.spec`.
- No inline `<script>` in `index.html`: the page's CSP is `script-src 'self'`; put the code into a file.
- E2E waits for anything that sends the 100 000-object test layer to the server are at least 30 s; a 5 s wait gave a false failure on a busy machine (v0.95.0).
- Agents never use `git stash` / `git checkout` of files in the shared worktree for «before» screenshots — they serve a `git archive HEAD` copy on another port.
- A hidden window can keep keyboard focus in its input: a global shortcut handler that skips inputs must still handle the shortcut that toggles that window (F1 from the help search field, v0.96.0).
- DBF text fields from portals are capped at 254 bytes (≈127 Cyrillic characters): any portal shapefile with long text needs the attribute refill (CSV/GeoJSON) — check every new document layer for cut values (v0.96.1).
- Every subagent brief repeats the ban on `pkill -f` and `git stash`/`checkout`; a brief without it is the lead's fault (cycle 19: one stray `pkill -f`).
- Portal retries live in exactly one place (the connector, with pauses); the page never repeats a failed portal request itself (T62: 3 × 2 attempts without a pause).
- Any search or relaxation that can be cut short is bounded by step counts, never by wall-clock time, and a cut-short result is cached under the same key (deterministic) — a time bound gives different sketches on different machines and an uncached partial result re-runs on every render (T6, T56).
- Any automatic rebuild of the owner's content (sheets, layers, graph) on project open is forbidden: adopt the current state as the base and rebuild only on an explicit action with a two-click confirmation (T55).
- A layer-key alias (`gisogd.X` ↔ `ogd.X`) is applied only where the user picks from the catalog; code that loads layers for albums/sheets keeps exact keys (iron rule 5) — T61 first version broke album loads.
- The owner's real projects store catalog layers as `ogd.<code>` and `egko.*`; every feature that looks up a layer by a fixed key (`gisogd.*`, `nspd.*`, `osm.*`) is silently empty on them — look up layers by role, and test on the copy of the site project (`/tmp/grado-team/transfer/bezobrazovo.server.grado2`), not only on the example.
- `test_e2e.py` prints only the last 4000 characters of a scenario's output: a step near the start of `scenarios.mjs` never shows an «ok» line in the log — a green run is the proof, not the grep.
- An external tile or data service is checked with one real request (size and a look at the tile) before it is wired in: CARTO basemaps returned HTTP 200 with an «API KEY REQUIRED» placeholder (03.10.2026).
- Reviewers never run `git stash` in the shared worktree, even «for a probe» — it reverts other agents' work under a running E2E (03.10.2026, restored by pop; that gate stayed green, so it was not repeated).
- Anything litegraph draws from a size-dependent constant (`--k`) must be stored at scale 1: titles truncated with `fitText`, node sizes, pasted/cloned nodes (`onConfigure`) — check `JSON.stringify(graph.serialize())` equal at k=1 and 7/6.
- E2E steps never compare with hard-coded dates while the program stamps the real time (`editedAt`, `builtAt`): clear or stub the stamps first — the T34 step turned red by itself after 13:07 on 03.10.2026.
- Inside a template literal passed to `p.ev`, write regexes as `/api[/]print[/]pdf/` or `\\/`: a single `\/` is unescaped to `/` and the page throws «Invalid regular expression flags».
- Keyboard activation of any menu item is tested with a real key event (`p.key("Enter")`), not `.click()`: the map's global keydown handler (cad.js) can swallow Enter/Space for new menus and buttons.
- Project files on the site (`/var/lib/grado/projects`, local mode, not hub) are edited only by the lead with the owner's word: plan first, backup to `.bak/`, atomic replace, the owner's tab closed (browser autosave would overwrite), verification, rollback path. Subagents never touch them.
- Probes of grado.tailink.tech from the Mac are unreliable (the Mac goes out through a VPN; half of the requests time out before connecting). The landing is confirmed by the deploy script's own health check («Готово: на сервере версия X»), not by curl from the Mac.

## Последние циклы

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
