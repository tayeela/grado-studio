<!-- пишется руками (карта файлов и мест); tools/wiki.py не трогает -->

# Где что лежит

Короткая карта для человека и ИИ: какой вопрос — какой файл. Пути от корня репозитория `grado-studio`, если не сказано
иное. Карта самих папок — `INDEX.md` в корне, карта документов — `docs/INDEX.md`, подробности по каждой части — страницы вики (INDEX.md рядом).

## Сначала прочитать

| что | где |
|---|---|
| что это и как запустить | `README.md` |
| правила работы в репозитории (коротко) | `CLAUDE.md` (для любых агентов — `AGENTS.md`) |
| карта папок и файлов верхнего уровня | `INDEX.md` |
| карта документов по полкам | `docs/INDEX.md` |
| оглавление вики | `docs/wiki/INDEX.md` |
| **свод правил альбома ППТ КРТ** (до любой работы с листами) | `docs/wiki/album-rules.md` |
| как устроена программа | `docs/wiki/architecture.md` |
| как писать код и документы | `docs/wiki/conventions.md`, `docs/CLAUDE.md` |
| как добавить источник данных, маршрут, лист альбома, правило подписей, модуль страницы, тест | `docs/wiki/howto.md` |
| как проверить, собрать альбом, выложить | `docs/wiki/recipes.md` |

## Вопрос → файл

| вопрос | где |
|---|---|
| задачи, слова владельца, что ждёт ответа | **GitHub Issues** `tayeela/grado-studio` (`gh issue list`), PR — `gh pr list`; архив до 06.10 — `docs/archive/team/OWNER.md`, `BOARD.md` |
| что сказал владелец, решения по датам | задачи с меткой «замечание владельца»; полные правила оформления — `docs/standards/albums/label-rules.md` |
| правила вёрстки слайдов (формат, сетка, типографика) | `docs/standards/albums/slide-layout-rules.md` |
| образцы владельца (шапка, ВРИ, Генплан, значки станций) | `docs/standards/albums/` (`pptkrt-header.jpg`, `ВРИ земельных участков_RGB.dxf`, `УСЛОВКИ от Генплана.dxf`, `icons/`); образцы к задаче #37 — `docs/team/samples/2026-10-07/` |
| типы линий ЛГР, Эталон, стили | `docs/standards/redln97/`, `core/render/grado_render/styles/*.json` (генерируются `tools/gen_*.py`) |
| нормативы Москвы (ТЭП, РНГП) | `docs/standards/moscow-ngp/`, `docs/standards/regulations-moscow.md` |
| какие слои откуда (ГИС ОГД, ЕГКО, НСПД, OSM, Яндекс) | `docs/wiki/sources.md`; коннекторы — `core/connectors/grado_connectors/` |
| НСПД из облака (релей) | `tools/nspd_relay/README.md`, `core/connectors/grado_connectors/nspd.py` |
| листы альбома: состав, порядок, ключи, основа | `docs/wiki/sheets.md`; код — `apps/grado2/web/albums.js` (`PPTKRT_C`, `PPTKRT_D`, `PPTKRT_ORDER`, `conceptSheet`), `sheets.js` |
| состав листа по ролям, окно «Слои и листы» | `apps/grado2/web/sheetlayout.js`, `sheetlayers.js`; спецификация — `docs/specs/T86-sheet-layers.md` |
| листы «в границах сит. плана» (район, документация, ПЗЗ, Генплан) | `docs/specs/37-sitplan-sheets.md`; код — `albums.js` (`PPTKRT_D`) |
| печать карты листа, подписи, знаки ЛГР | `apps/grado2/print_io.py` (`SketchMapFrame`) |
| оформление шаблона ППТ КРТ, легенда, титул, выноски | `apps/grado2/album_io.py` |
| PDF / PPTX / SVG | `core/render/grado_render/backend_pdf.py`, `backend_pptx.py`, `backend_svg.py` |
| маршруты сервера | `docs/wiki/api.md`; код — `apps/grado2/server.py` |
| совместная работа (хаб, роли, ссылки) | `apps/grado2/hub.py`, `web/collab.js`, `web/hub.js`; контракт — `docs/specs/collab-contract.md`; руководство — `docs/guides/collab.md` |
| файлы кода и их функции | `docs/wiki/modules.md` |
| тесты и браузерные сценарии | `docs/wiki/tests.md`; `apps/grado2/tests/`, сценарии — `apps/grado2/tests/e2e/scenarios.mjs` |
| проверка перед коммитом | `tools/gate.sh` (`E2E=1` — с браузером) |
| автоматика GitHub (тесты, вики, проверка документов) | `.github/workflows/README.md` |
| что менялось | `docs/grado2-changelog.md` (новые сверху), `docs/wiki/changelog-recent.md` |
| очередь команды, что ждёт владельца, готово к выкладке | GitHub Issues (метки «ждёт владельца», «готово к выкладке») и PR выкладки `team/t60 → main` |
| выданные альбомы (PDF, PPTX) | релизы GitHub `album-*` (`gh release list`) и папки выдачи на Mac |
| порядок работы команды, роли, шаблоны заданий | `docs/team/CYCLE.md`, `.claude/agents/grado-*.md`, `docs/team/prompts/` |
| уроки команды (обязательные) | строки `RULE:` в `docs/team/PROGRESS.md` |
| решения совета команды | `docs/team/DECISIONS.md` |
| выкладка на сайт grado.tailink.tech | `tools/deploy-server.sh`, хуки `tools/git-hooks/`; рецепт — `docs/wiki/recipes.md` |
| снимки панорам Яндекса для фотофиксации | `tools/panorama_shot.mjs` |
| проверка альбома «до / после» (картинки и текст страниц) | `tools/album_check.py`; эталоны — релиз GitHub `album-baseline` (копия в `~/.grado2/album-baseline/`), отчёт — `/tmp/grado-album-check/<имя>/` |
| проверка оформления готового альбома (наложения, края, переносы, «ё», неразрывные пробелы в PPTX) | `tools/album_lint.py` (его же запускает `album_check.py`); чек-лист — `docs/standards/albums/layout-qa.md` |
| контрольные строки альбома (адрес титула, выноска территории, число листов) | `tools/album_expect/*.json` (формат — `tools/album_expect/README.md`) |
| аудит оформления альбома по плиткам | шаблон `docs/team/prompts/album-design-audit.md`; итоги первого прогона — задача #53 |
| готовые сценарии (навыки) | `.claude/skills/album-verify` (проверка), `owner-remark` (замечание владельца), `land` (выкладка) |
| закрытая студия, прежние аудиты и планы | `docs/archive/` (читать только как историю) |
| вики на GitHub (приватно) | `tayeela/grado-wiki`: README, llms.txt, AGENTS.md; обновляет `.github/workflows/wiki.yml` и `tools/wiki_publish.sh` |
| эта вики | генератор `tools/wiki.py` (страницы из кода); вручную — `architecture.md`, `recipes.md`, `album-rules.md`, `files.md`, `conventions.md`, `howto.md` |

## Вне репозитория

| что | где | можно ли трогать |
|---|---|---|
| рабочие проекты владельца | `~/Documents/ГРАДО 2/` (Mac) | **нет**, только читать по просьбе |
| программа владельца (сервер) | порт 8650 на Mac | **нет**, тесты — только на 8651+ |
| сайт grado.tailink.tech | сервер `msk` (`ssh msk`): программа `/opt/grado/app`, проекты `/var/lib/grado/projects`, службы `grado` и `grado-guest` | только выкладкой `tools/deploy-server.sh` с Mac |
| выдача альбома владельцу | `~/Documents/ГРАДО 2 — ППТ КРТ <№> <район> (<дата>)/`, прежние версии — `прежняя версия/` | да, с копией прежнего |
| тестовые серверы | `~/.claude/launch.json`: `grado2-test` (8651), `grado2-team2` (8661), `grado2-t86` (8671) | да |
| копии проектов для проверок | `/tmp/grado-team/<дата>/proj-*` (на Mac); в облаке — релиз `album-work-*` | да |
| кэш порталов и тайлов | `~/.grado2/cache/` (`tiles/yandex-sat`, `print_ops`, порталы) | удалять — только спросив владельца |
| сертификаты НСПД | `~/.grado2/ca/` | нет |
| рабочие копии команды | `.claude/worktrees/team2` (ветка `team/t60`) | да |

## Ветки

- `main` — то, что на сайте; меняется только по слову владельца «выкладывай».
- `team/t60` — ветка команды: сюда сливаются PR из веток `task/<номер задачи>-<имя>`; оттуда PR в `main`.
- Влитые ветки удаляются; незавершённая работа живёт в открытом PR.
