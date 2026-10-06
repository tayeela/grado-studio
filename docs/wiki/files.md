<!-- пишется руками (карта файлов и мест); tools/wiki.py не трогает -->

# Где что лежит

Короткая карта для человека и ИИ: какой вопрос — какой файл. Пути от корня репозитория `grado-studio`, если не сказано
иное. Подробности по каждой части — страницы вики (INDEX.md).

## Сначала прочитать

| что | где |
|---|---|
| правила работы в репозитории (коротко) | `CLAUDE.md` |
| оглавление вики | `docs/wiki/INDEX.md` |
| **свод правил альбома ППТ КРТ** (до любой работы с листами) | `docs/wiki/album-rules.md` |
| как устроена программа | `docs/wiki/architecture.md` |
| как проверить, собрать альбом, выложить | `docs/wiki/recipes.md` |

## Вопрос → файл

| вопрос | где |
|---|---|
| что сказал владелец, решения по датам | `docs/team/OWNER.md`; полные правила оформления — `docs/standards/albums/label-rules.md` |
| правила вёрстки слайдов (формат, сетка, типографика) | `docs/standards/albums/slide-layout-rules.md` |
| образцы владельца (шапка, ВРИ, Генплан, значки станций) | `docs/standards/albums/` (`pptkrt-header.jpg`, `ВРИ земельных участков_RGB.dxf`, `УСЛОВКИ от Генплана.dxf`, `icons/`) |
| типы линий ЛГР, Эталон, стили | `docs/standards/redln97/`, `core/render/grado_render/styles/*.json` (генерируются `tools/gen_*.py`) |
| нормативы Москвы (ТЭП, РНГП) | `docs/standards/moscow-ngp/`, `docs/regulations-moscow.md` |
| какие слои откуда (ГИС ОГД, ЕГКО, НСПД, OSM, Яндекс) | `docs/wiki/sources.md`; коннекторы — `core/connectors/grado_connectors/` |
| листы альбома: состав, ключи, основа | `docs/wiki/sheets.md`; код — `apps/grado2/web/albums.js` (`PPTKRT_C`, `conceptSheet`), `sheets.js` |
| состав листа по ролям, окно «Слои и листы» | `apps/grado2/web/sheetlayout.js`, `sheetlayers.js`; спецификация — `docs/team/spec-T86-sheet-layers.md` |
| печать карты листа, подписи, знаки ЛГР | `apps/grado2/print_io.py` (`SketchMapFrame`) |
| оформление шаблона ППТ КРТ, легенда, титул, выноски | `apps/grado2/album_io.py` |
| PDF / PPTX / SVG | `core/render/grado_render/backend_pdf.py`, `backend_pptx.py`, `backend_svg.py` |
| маршруты сервера | `docs/wiki/api.md`; код — `apps/grado2/server.py` |
| файлы кода и их функции | `docs/wiki/modules.md` |
| тесты и браузерные сценарии | `docs/wiki/tests.md`; `apps/grado2/tests/`, сценарии — `apps/grado2/tests/e2e/scenarios.mjs` |
| проверка перед коммитом | `tools/gate.sh` (`E2E=1` — с браузером) |
| что менялось | `docs/grado2-changelog.md` (новые сверху), `docs/wiki/changelog-recent.md` |
| очередь команды, что ждёт владельца, готово к выкладке | `docs/team/BOARD.md`, `docs/wiki/team.md` |
| порядок работы команды, роли, шаблоны заданий | `docs/team/CYCLE.md`, `.claude/agents/grado-*.md`, `docs/team/prompts/` |
| уроки команды (обязательные) | строки `RULE:` в `docs/team/PROGRESS.md` |
| решения совета команды | `docs/team/DECISIONS.md` |
| выкладка на сайт grado.tailink.tech | `tools/deploy-server.sh`, хуки `tools/git-hooks/`; рецепт — `docs/wiki/recipes.md` |
| снимки панорам Яндекса для фотофиксации | `tools/panorama_shot.mjs` |
| эта вики | генератор `tools/wiki.py` (страницы из кода при каждом коммите); вручную — `architecture.md`, `recipes.md`, `album-rules.md`, `files.md` |

## Вне репозитория (на Mac владельца)

| что | где | можно ли трогать |
|---|---|---|
| рабочие проекты владельца | `~/Documents/ГРАДО 2/` | **нет**, только читать по просьбе |
| программа владельца (сервер) | порт 8650 | **нет**, тесты — только на 8651+ |
| выдача альбома владельцу | `~/Documents/ГРАДО 2 — ППТ КРТ <№> <район> (<дата>)/`, прежние версии — `прежняя версия/` | да, с копией прежнего |
| тестовые серверы | `~/.claude/launch.json`: `grado2-test` (8651), `grado2-team2` (8661), `grado2-t86` (8671) | да |
| копии проектов для проверок | `/tmp/grado-team/<дата>/proj-*` | да |
| кэш порталов и тайлов | `~/.grado2/cache/` (`tiles/yandex-sat`, `print_ops`, порталы) | удалять — только спросив владельца |
| сертификаты НСПД | `~/.grado2/ca/` | нет |
| рабочие копии команды | `.claude/worktrees/team2` (ветка `team/t60`), `.claude/worktrees/t86` (`team/t86`) | да |

## Ветки

- `main` — то, что на сайте; меняется только по слову владельца «выкладывай».
- `team/t60` — работа команды; `team/t86` — текущая задача; сливаются в `team/t60`, оттуда в `main`.
