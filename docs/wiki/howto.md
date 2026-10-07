# Как добавить… (рецепты; пишется вручную)

Шесть частых правок по шагам. Выведены из настоящих коммитов (образцы названы) и проверены чтением кода 07.10.2026. Номеров строк здесь нет — они устаревают за день: имя
ищите командой `grep -n "<имя>" <файл>`; размер и функции каждого файла — [modules.md](modules.md). Общие соглашения — [conventions.md](conventions.md).
Каждая правка заканчивается одним и тем же: версия в `apps/grado2/web/version.json`, запись сверху `docs/grado2-changelog.md`, `tools/gate.sh` (с `E2E=1`, если менялись страница, печать или альбом),
PR в `team/t60`.

## 1. Источник данных (слой)

Ключ слоя — `вид.имя` (`egko.place_labels`, `sit.stations`). **Вид** определяет коннектор и предел области:

| вид | коннектор (`core/connectors/grado_connectors/`) | задание в `server.py` | предел, км² (`LIMIT_KM2`) |
|---|---|---|---|
| `nspd` | `nspd.py` (`NspdDirect`) | `run_nspd` | 250 |
| `osm` | `osm.py` (`OsmOverpass`) | `run_osm` | 150 |
| `gisogd` | `gisogd_api.py` (`GisogdApi`) | `run_gisogd` | 150 |
| `egko` | `GisogdApi`, карта base2 | `run_egko` | 150 |
| `yandex` | `yandex_vmap.py`, тайлы z18 | `run_yandex` | 40 |
| `yandex_sit` | то же, тайлы z16 (`SIT_ZOOM`), для ситуационных листов | `run_yandex` | 150 |
| `gisogd_admin` | нет: эталон `docs/standards/admin/moscow-adm.geojson` | `run_admin` | без предела |
| `terrain` | `terrain.py` | `run_terrain` | 150 |

Шаги нового ключа существующего вида (образцы: коммиты `bed3a99`, `egko.place_labels`; `78128d1` и `16f21cd`, `sit.*` с фильтрами):

1. **Правило владельца — раньше кода**, если слой про альбом, легенду или подписи: [album-rules.md](album-rules.md) и `docs/standards/albums/label-rules.md` (навык `owner-remark`).
2. **`apps/grado2/server.py`, `SOURCES["вид.имя"] = (вид, параметр, название)`** — строкой с первой колонки (иначе [sources.md](sources.md) её не увидит). Название — подпись слоя на странице.
   Параметр: gisogd и egko — словарь «код слоя портала → подпись зоны или `None`»; yandex и yandex_sit — список слоёв тайла (`["transport_p"]`); osm — имя набора; nspd — список ID; terrain и gisogd_admin — `None`.
3. **Поля объекта — `PRESENT`** (там же): для gisogd и egko — явная запись, переводящая поля портала в читаемые (`{"Подпись": …}`); у yandex-видов записи не нужны; остальным поля переименует `clean_props`.
4. **Фильтр объектов — `SIT_FILTER`**, если тайл Яндекса отдаёт лишнее (`sit.stations` — только метро, закрытые не берутся).
5. **Роль для расчётов — `SOURCE_ROLES`** (только gisogd; исключения по кодам — `CODE_ROLES_SKIP`); та же таблица на странице — `web/roles.js` (`SOURCE_ROLE`), тест `test_roles_js.py` требует совпадения.
6. **Страница:** `web/layers.js` — порядок в дереве (`PREFERRED`) и стиль по умолчанию (`defaultStyle`; иначе слой получит случайный цвет палитры); `web/sheetlayout.js` — роль слоя на листе (`ROLES`; нет в таблице — «Прочее»);
   `web/ogdpick.js` — окно «Исходные данные» (`GROUPS`, `PRESETS`); `web/app.js` — подпись группы в окне «Данные» (`GROUP`).
7. **Листы альбома:** `web/albums.js` (`cSheet`, массивы `PPTKRT_C`/`PPTKRT_D`: `keys` и `styles`), ситуационный план — `web/sheets.js` (`SIT`, `buildSituation0`).
8. **Тесты:** `apps/grado2/tests/test_server.py` (наборы ключей `yandex.` и `sit.`; образец фильтра — тест, подменяющий `YandexVmap`), `sheetlayout_test.js`, при изменении печати — группа E2E.
9. **Само обновится:** [sources.md](sources.md), [sheets.md](sheets.md), [tests.md](tests.md).
10. Проверка, что ключ нигде не забыт: `grep -n "<ключ>" apps/grado2/server.py apps/grado2/web/*.js`.

**Новый вид** (не ключ): коннектор — класс от `Connector` (`contract.py`), результат через `make_result`, сеть через `netutil.open_url`/`read_capped`, HTTPS с `certifi`, не больше трёх повторов; в `server.py` — функция `run_<вид>`,
строка в списке заданий внутри `fetch()` и запись в `LIMIT_KM2` (без неё запрос отвечает 400); `GROUP`/`GROUPS` на странице; тест `core/connectors/tests/test_<имя>.py`. Новых зависимостей нельзя.

Подводные камни: `fetch()` молча пропускает ключи, которых нет в `SOURCES`, и виды без задания — ошибки не будет; маршрут по **id слоя**, не по «первому слою вида» (железное правило 5).

## 2. Маршрут сервера `/api/…`

`apps/grado2/server.py`, класс `Handler`: `do_GET` и `_post` — цепочки `if self.path == "/api/…"`, а не таблица. Каждый запрос уже прошёл проверку Host/Origin, ключ доступа (`GRADO2_TOKEN`) и сессию совместного режима —
открыть маршрут без входа можно только через `LOGIN_OPEN` и список в хабе (решение команды).

1. **GET** — ветка в `do_GET` (образцы `/api/health`, `/api/search/address`); **POST** — ветка в `_post` после чтения тела (образцы `/api/place`, `/api/rail_route`, `/api/tep`).
2. **Тело** читает `_read_obj` (только JSON-объект); обязательное поле — `req["поле"]` (нет поля — 400 «bad request»); диапазоны и числа проверять явно. Предел тела — `body_limit` (по умолчанию 32 МБ,
   пути `/api/import/`, `/api/print/`, `/api/export/` — 250 МБ: префикс выбирать осознанно).
3. **Ответ** — `self._json(код, объект)`; ошибка — `{"error": "текст"}`. Портал недоступен — `ConnectorError` → 502 (текст через `plain_portal_error`); плохие данные — 400 через `_bad`.
   Заголовки HTTP — только ASCII (правило 4); тексты в теле — короткие, понятные владельцу.
4. **Страница вызывает через `api()`** в `web/app.js` (читает JSON до проверки статуса — поэтому ответы маршрута только JSON, иначе ошибка разбора вместо понятного текста).
5. **Тест:** `apps/grado2/tests/test_server.py`, класс `HttpHardening` (сервер на порту 0 в потоке; образец POST — `test_tep_constants_and_norms_over_http`); без HTTP — вызвать функцию напрямую.
6. [api.md](api.md) обновится сам из строк `"/api/…"` в `server.py` (только строчные латинские, цифры, `_`, `/`); важный маршрут добавьте и в заголовок-docstring `server.py`.

## 3. Лист в альбом ППТ КРТ

Шаблон листов — `apps/grado2/web/albums.js`: `PPTKRT_C` (листы «по ГК Царицыно»), `PPTKRT_D` (листы «в границах сит. плана»), порядок выдачи — `PPTKRT_ORDER`; актуальный состав — [sheets.md](sheets.md).
Id листа в проекте — `pptkrt_<индекс>`, поэтому **новый лист добавляют только в конец массива** (иначе в старых проектах сдвинутся снимки и правки), а место в альбоме задаёт `PPTKRT_ORDER`.
Образцы: `82fa57a` (карта района), `1f39be8` (Генплан и ПЗЗ), `b688205` (документация), `e342a0e` (ГПЗУ копией через `PPTKRT_D.push`).

1. Правило и ТЗ: слова владельца — задача GitHub; строка в [album-rules.md](album-rules.md) (раздел 5) и пункт в `label-rules.md`; большой лист — `docs/specs/<номер>-<имя>.md`.
2. **Описать лист** — объект в массиве: `title` (18 пт, до двух строк, иначе лист «не готов»), `concept` (ветка в `conceptSheet`), `basemap` (`"sat"` — снимок), `keys` и `styles` (оформление каждого ключа), `only`, `labelFn`/`labelMM`/`labelStyle`,
   `fit` (`terr`, `cover`, `district`, `okrug`, `moscow` — рамка), `ctx`, `rect`, `bleed`, `look`, `sit` («в границах сит. плана»: рамка своя, «Масштаб схем» не действует), `twin` (две схемы на листе), `extra`, `kind` (`photos`, `title`).
   Значения по умолчанию — `C_BASE`; каждый лист проходит `cSheet` (добавляет дороги ЕГКО, подписи, начальный `layout`).
3. **Вид листа** — ветка `if (k === "<вид>")` в `conceptSheet`: общее (источник дорог, топонимы, подписи воды, станции) идёт до веток; легенду собирают `out.cLegend` и `LegendRules.pruneGroups`.
4. **Рамка и масштаб:** `fitBox` в `sheets.js` (`cover` → `coverFrameBox`); лист должен слушаться «Масштаб схем 5–9» — добавьте вид в `SCHEME_CONCEPTS` и не ставьте `sit`.
5. **Печать:** `print_io.build_document` при `style: "pptkrt"` вызывает `album_io.build_pptkrt`, который выбирает рамку по полям листа (`look`, `twin` → `TwinCaptionFrame`, `kind: photos`, `bleed`). Новый класс рамки добавьте в `PPTX_GROUPS` в `print_io.py`, иначе PPTX положит его в группу «Оформление».
6. **Порядок:** индекс в `PPTKRT_ORDER` на нужное место и комментарий в той же строке; иначе лист будет «в шаблоне, но не в выдаче».
7. **Тесты:** новая группа E2E (`p.group("t93", …)`, образец `t90` в `scenarios.mjs`); обновить ожидания, зашитые на шаблон (длина `PPTKRT_D`, хвост порядка); `legendrules_test.js` при новых видах документов.
8. **Проверка картинкой** — навык `album-verify`: сборка на копии проекта, `tools/album_check.py --name gol` и `--name bez`; новый лист в середине порядка сдвигает номера страниц — отличия «страниц стало M» ожидаемы. Эталон (`--update`) — только после принятия владельцем.
   Затем `tools/album_lint.py album.pdf` и аудит оформления ([../team/prompts/album-design-audit.md](../team/prompts/album-design-audit.md)).
9. Существующий проект получает новый лист только после «Заменить» в окне «Листы и альбом» (`buildSection0`); «Обновить листы» (`tplRefresh`) меняет лишь листы, которые уже есть.

## 4. Правило подписей и условных обозначений

Порядок: слова владельца → задача GitHub → правило в [album-rules.md](album-rules.md) и `label-rules.md` → код → пересборка на копии проекта и сравнение страниц (навыки `owner-remark`, `album-verify`).

| что меняется | где |
|---|---|
| текст подписи (кавычки, станции, сокращения) | функции `LABEL_FN` в `web/sheets.js` (`vri`, `gp`, `adm`, `pzz`) и `web/albums.js` (`street`, `yaStreet`, `name2`); строковые правила — чистые функции `web/labelfmt.js` |
| какой слой какой функцией | поле листа `labelFn`; имени нет в `LABEL_FN` — вызов падает |
| кегль, шрифт, обводка, цвет | поля `labelMM`, `labelStyle` (`lf` шрифт, `lh` обводка, `lhc` цвет обводки); по умолчанию 2 мм — `print_io.py`, `SketchMapFrame` |
| обязательные подписи и сдвиг | `must`, `mustAt`, `nudge` (albums.js и `SketchMapFrame`) |
| состав подписей | `yandexToponyms`, `waterLabels`, `namedPlaces`, `railStations` в `albums.js` |
| легенда | `out.cLegend` в `conceptSheet`, правила — `web/legendrules.js` (`docKinds`, `docTitle`, `pruneGroups`, `notesLast`); вид знака — `concept_swatch` в `album_io.py` (`line`, `lt`, `rail`, `icon`, `flood`, `num`, `text`, `note`) |
| расстановка | `SketchMapFrame` в `print_io.py`: сначала реки, номера документов, ГИС ОГД; потом улицы; потом территории; подпись обрезается до 60 знаков и 3 строк |

Кавычки и префикс станции «ст. ж/д » продублированы в Python (`_guillemets`, `STATION_MARK` в `print_io.py`) и JS (`labelfmt.js`): меняйте обе стороны, иначе на экране и в печати будут разные. Тесты:
`labelfmt_test.js`, `legendrules_test.js`, `test_t78_labels.py`, `test_t89_labels.py`, `test_print.py`, группа E2E `t89`.

## 5. Модуль страницы (JS)

Страница без сборки: `web/index.html` подключает скрипты тегами в нужном порядке; сервер отдаёт весь `web/` сам. CSP запрещает inline-скрипты (`script-src 'self'`).

1. Файл `apps/grado2/web/<имя>.js`; первая строка — заголовок «что это» (проверяет `docs_check.py`). Образец заголовка — `labelfmt.js`.
2. **Чистый модуль — IIFE** с экспортом для Node и браузера (образец хвоста — `labelfmt.js`):
   ```js
   (function (root) {
     // функции…
     const api = { fnA, fnB };
     if (typeof module === "object" && module.exports) module.exports = api;
     root.Имя = api;
   })(typeof window !== "undefined" ? window : globalThis);
   ```
   Не вынесенное в `api` снаружи не вызвать; при загрузке скрипта модуль не обращается к API сервера.
3. Подключить в `index.html` до тех, кто использует модуль при загрузке (зависимость `albums.js` от `AlbumGeo` и `SheetLayout` — они стоят раньше него). Сервер не трогать, после правки — перезагрузка страницы.
4. Тест под Node: `tests/<имя>_test.js` (`require("../web/<имя>.js")`, счётчик проверок, в конце `console.log(n + " checks ok")`) и обёртка `tests/test_<имя>_js.py` — копия `test_labelfmt_js.py` (`skipUnless(shutil.which("node"))`).
   Быстро: `node apps/grado2/tests/<имя>_test.js`, `node --check apps/grado2/web/<имя>.js`.
5. Строку в таблицу «web/» файла `apps/grado2/README.md`; [modules.md](modules.md) обновится сам (`python3 tools/wiki.py`).

## 6. Тест

| вид | где | запуск |
|---|---|---|
| Python, сервер и печать | `apps/grado2/tests/test_*.py` | шаги `unit` и `unit-bare` gate (с `PYTHONPATH` и без) |
| Python, ядро | `core/<пакет>/tests/test_*.py` | шаги `connectors` и `core` gate |
| JS под Node | `apps/grado2/tests/<имя>_test.js` + `test_<имя>_js.py` | шаг `unit` gate |
| браузер (headless Chrome) | `apps/grado2/tests/e2e/scenarios.mjs`, `collab_scenarios.mjs` | `E2E=1 tools/gate.sh`; группы — `E2E_ONLY=t90,t91` |

- **Python:** `sys.path.insert(0, …/apps/grado2)` и `import server as S` / `import print_io` — так тест работает и без `PYTHONPATH`. Лист без браузера:
  `print_io.document_pages_ops(print_io.build_document({"sheets": [sh]}, S.REDLN, S.LGR_DASH), None)[0][2]` (образец `test_t89_labels.py`).
- **Браузерная группа:** `await p.group("tNN", async () => { … })`; номер свободный — `grep -rn 'tNN' apps/grado2/tests`. Группы связаны состоянием страницы: в конце группы верните его, как делает `t90`.
  `check(условие, "что проверяем")`; `p.ev(js)` выполняется в async-функции, без `return` значения нет; `p.click`, `p.drag`, `p.key` (пункты меню — клавишей), `p.wheel`, `p.shot`.
- **Шаг ждёт, а не спит** (урок задачи #40): ждёт текст или элемент, который проверяет (`until(js)`, цикл опроса); `p.sleep` — только для анимации. Сравнивать с жёсткой датой нельзя — очистите штампы времени до шага.
  Слой в сотни тысяч объектов — ожидание не меньше 30 с.
- **Результат прогона:** журналы шагов — `/tmp/grado-gate/<шаг>.log`; у E2E итог — строка `SUMMARY: N ok, M failed`. Перед коммитом полный E2E на общем дереве, без чужих незакоммиченных правок.
