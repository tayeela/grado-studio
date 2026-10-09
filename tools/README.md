# tools — проверки, генераторы, выкладка

Здесь скрипты для проверок и выкладки ГРАДО 2, генераторы стилей, сборка вики и git-хуки. Команды запускают из корня
репозитория. Перед каждым коммитом запускайте `tools/gate.sh`.

## Проверки

| Файл | Что делает | Когда запускать | Команда |
|---|---|---|---|
| `gate.sh` | Проверка перед коммитом: вики (`wiki.py --check`), навигация документов (`docs_check.py`), тесты `apps/grado2` (с PYTHONPATH и без), тесты коннекторов. Итог «GATE: OK» или «GATE: FAIL»; при сбое печатает путь к логу шага. | Перед каждым коммитом. С `E2E=1` добавляются браузерные сценарии (около 6 минут): при правках страницы, печати или альбома. | `tools/gate.sh`; `E2E=1 tools/gate.sh`; `E2E_ONLY=t71,t82 tools/gate.sh` (только эти группы) |
| `ui_check.sh` | Проверка, что собранный новый интерфейс `apps/grado2/web/next` совпадает с исходниками `apps/grado2/ui` (пересборка Vite и сравнение с git). | После правки `apps/grado2/ui`. Запускают `gate.sh` (шаг ui, если в apps/grado2/ui установлены пакеты: npm ci) и CI. | `tools/ui_check.sh` |
| `ui_layout_check.mjs` | Проверка раскладки нового интерфейса по `docs/ux/ui-grid.md`: открывает каждое окно на тестовом проекте (1280 и 1920, светлая и тёмная тема), тянет окна мышью и ищет полосы прокрутки, поля за краем окна, прыжки, мелкие цели и шрифт. Отчёт `report.md`, снимки по `--shots`. | После правки окон `apps/grado2/ui`. Запускает `gate.sh` при `E2E=1` (шаг ui-layout). | `CHROME=… node tools/ui_layout_check.mjs --out /tmp/grado-ui-check --shots` |
| `docs_check.py` | Проверка навигации: ссылки в Markdown, пути в обратных кавычках, README в ключевых папках, документы `docs/` названы в оглавлении, у файлов кода есть заголовок. | После переноса или добавления документов и файлов. Запускают его `gate.sh` (шаг docs) и CI (`.github/workflows/docs.yml`). | `python3 tools/docs_check.py` (код 1 — есть нарушения); `python3 tools/docs_check.py --rules` — правила и исключения |
| `album_check.py` | Визуальная проверка альбома «до / после»: печатает PDF на тестовом сервере, сравнивает страницы с эталоном, пишет отчёт с вырезками и в конце отчёта — результат `album_lint.py`. Код выхода: 0 — отличий нет, 1 — есть отличия, 2 — ошибка печати, 3 — линт нашёл ошибки оформления. | После любой правки альбома: печать, подписи, легенда, слои, данные. Порядок работы — в скилле `album-verify` (`.claude/skills/album-verify/SKILL.md`). | `~/.grado2/venv/bin/python tools/album_check.py --spec <папка проектов>/_specX.grado2 --name gol`; `--update` делает текущий результат эталоном |
| `album_lint.py` | Автоматические проверки оформления готового альбома: PDF — слова налезают друг на друга, выходят за край листа или рамку карты, слишком мелкий кегль, подписи-дубли рядом, предлог или число на конце строки, «ё» и тире, невшитые шрифты, растры с низким разрешением; PPTX — неразрывные пробелы; контрольные строки владельца (`album_expect/`). Читает PDF утилитами poppler. | После сборки альбома, до слова «готово» (`album_check.py` запускает его сам; то же — в аудите оформления, `docs/team/prompts/album-design-audit.md`). | `python3 tools/album_lint.py album.pdf --pptx album.pptx --spec spec.json --expect tools/album_expect/all.json`; `--json` — для свода аудита |
| `album_expect/` | Контрольные строки альбома: обязательный и запрещённый текст страниц (адрес титула, выноска территории, число листов), каждая с причиной; формат — [album_expect/README.md](album_expect/README.md). | Когда владелец называет конкретный текст или аудит находит пропущенную строку. | правит человек; читает `album_lint.py --expect` и `album_check.py` |

Эталоны лежат в кэше `~/.grado2` (папка `album-baseline`) и в релизе `album-baseline`. Путь к отчёту и остальные
параметры — в заголовке `album_check.py`. Порт 8650 — программа владельца, его не использовать.

## Выкладка, вики и хуки

| Файл | Что делает | Когда запускать | Команда |
|---|---|---|---|
| `server_pull/` | Выкладка сайта самим сервером msk: таймер `grado-pull` раз в 5 минут забирает `main` с GitHub, ставит новую программу, проверяет версию по `/api/health`, при сбое возвращает прежнюю. Файлы: `grado-pull.sh`, службы systemd, `install-on-msk.sh`. | Сам на сервере. С Mac не запускается. | установка и откат — `tools/server_pull/README.md` |
| `wiki.py` | Пересобирает вики `docs/wiki/` из кода: страницы с пометкой «генерируется». Страницы, которые пишут руками (например, `files.md`, `recipes.md`), не трогает. С `--check` — код 1, если вики устарела. | После любой правки кода или документов. Pre-commit-хук пересобирает вики перед коммитом; CI проверяет её (`.github/workflows/docs.yml`) и пересобирает (`.github/workflows/wiki.yml`). | `python3 tools/wiki.py`; `python3 tools/wiki.py --check` |
| `wiki_albums.mjs` | Выдаёт состав альбома ППТ КРТ (листы и порядок выдачи) как JSON: выполняет `apps/grado2/web/albums.js` в Node. Нужен `wiki.py` для страницы `sheets.md`. | Запускает `wiki.py` сам. Вручную — редко. | `node tools/wiki_albums.mjs` (нужен только Node) |
| `wiki_publish.sh` | Выкладывает `docs/wiki` в приватный репозиторий `tayeela/grado-wiki` и добавляет README, llms.txt и AGENTS.md. Без изменений ничего не отправляет. | Сам: хук `post-commit` (ветки `main` и `team/t60`, если менялась `docs/wiki`) и GitHub Actions (`wiki.yml`). Вручную — по необходимости. | `tools/wiki_publish.sh`. Доступ: `WIKI_TOKEN`, либо `gh auth`, либо обычный git |
| `prune-merged-branches.sh` | Показывает (и с `--yes` удаляет на GitHub) ветки, целиком влитые в `main` или `team/t60`: коммиты остаются в истории; ветки открытых PR не трогает. | Изредка, для порядка в ветках; лучше включить в настройках GitHub автоудаление веток после слияния. | `tools/prune-merged-branches.sh` (список); `tools/prune-merged-branches.sh --yes` (удалить) |
| `git-hooks/` | `pre-commit` пересобирает вики и кладёт её в коммит. `post-commit` публикует вики (если менялась `docs/wiki`, ветки `main` и `team/t60`). `post-commit` и `post-merge` на `main` вызывают `deploy-if-main.sh` — он только напоминает, что сайт обновит сервер. Подробно — в `tools/git-hooks/README.md`. | Запускает git, когда хуки подключены. Подключение один раз в каждой рабочей копии. | `git config core.hooksPath tools/git-hooks` |

## Генераторы стилей и прочее

| Файл | Что делает | Когда запускать | Команда |
|---|---|---|---|
| `gen_moscow_lgr.py` | Пишет `core/render/grado_render/styles/moscow_lgr.json`: знаки линий градостроительного регулирования (ЛГР) по приказу Москомархитектуры от 10.03.2025 № 65. Данные зашиты в скрипт. | После правки генератора. JSON руками не править. | `python3 tools/gen_moscow_lgr.py` |
| `gen_moscow_genplan.py` | Пишет `core/render/grado_render/styles/moscow_genplan.json`: функциональные зоны Генплана Москвы. Данные зашиты в скрипт; QML-файлы владельца в репозиторий не входят. | После правки генератора. | `python3 tools/gen_moscow_genplan.py` |
| `gen_osm_highway.py` | Пишет `core/render/grado_render/styles/osm_highway.json`: знаки дорог OSM по рабочим QML владельца. | После правки генератора. | `python3 tools/gen_osm_highway.py` |
| `gen_redln97.py` | Пишет `core/render/grado_render/styles/redln97.json` из `docs/standards/redln97` (REDLN97.LIN и RED_LNS.SHX, стандарт красных линий Москвы). | После правки генератора или файлов стандарта. | `python3 tools/gen_redln97.py` |
| `gen_lgr_sheet.py` | Рисует справочный лист всех знаков ЛГР из `moscow_lgr.json`: PDF и SVG в папке `build` в корне репозитория (её создаёт скрипт). Для глазной сверки; альбом этим не печатается. | Когда нужно сверить знаки ЛГР глазами. | `python3 tools/gen_lgr_sheet.py` |
| `panorama_shot.mjs` | Снимок панорамы Яндекса без надписей (Chrome headless) для листа «Фотофиксация». Кадр: вырезка (550, 0, 2650, 1400), уменьшить до 1500×1000. | При подготовке кадра этого листа. | `node tools/panorama_shot.mjs <ссылка> <out.png>`; `WAIT` — ожидание загрузки в мс (по умолчанию 12000); `CHROME` — путь к Chrome (в облаке на Linux) |
| `nspd_relay/` | Релей к НСПД на российском сервере для облачных сессий. Файлы: `Caddyfile.example`, `install-on-msk.sh`. | Установка и работа описаны в `tools/nspd_relay/README.md`. | нет (см. README папки) |

## Что запускать когда

- Перед каждым коммитом — `tools/gate.sh`. Для правок страницы, печати или альбома — `E2E=1 tools/gate.sh`.
- После правки кода или документов — `python3 tools/wiki.py`. Вики в `docs/wiki/` собирается из кода.
- После переноса или добавления документов — `python3 tools/docs_check.py` (то же делает `gate.sh`).
- После правки альбома — `tools/album_check.py` и скилл `album-verify`.
- После правки генератора `tools/gen_*.py` — запустить его. JSON в `styles/` руками не править.

## Правила

- Правила альбома — в `docs/wiki/album-rules.md` (CLAUDE.md).
- Скрипты, которые запускают git-хуки, сбрасывают `GIT_DIR` и `GIT_INDEX_FILE` до вызова git (см. `wiki_publish.sh`;
  CLAUDE.md).
- Порт 8650 — программа владельца. Не тестировать на нём (CLAUDE.md).
- Сайт выкладывает сам сервер msk после слияния в `main` (`server_pull/README.md`); с Mac не выкладывать. Если новая версия не поднялась,
  на сервере остаётся прежняя.
