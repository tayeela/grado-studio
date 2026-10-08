# Карта репозитория

Что лежит в каждой папке и файле верхнего уровня. Новичку и ИИ-агенту — сначала [README.md](README.md) (что это) и [CLAUDE.md](CLAUDE.md) (правила), затем отсюда
по ссылке в нужную папку: у папок верхнего уровня и у каждой полки `docs/` есть `README.md` (у `docs/` — `INDEX.md`) с таблицей содержимого. Полнота этой карты проверяется (`tools/docs_check.py`, правило `root`):
новый файл или папка в корне должны быть названы здесь.

## Папки

| папка | что в ней | живое? |
|---|---|---|
| [apps/grado2/](apps/grado2/README.md) | **рабочая программа ГРАДО 2**: сервер, страница в браузере, печать, экспорт, тесты | да |
| `apps/studio/`, `apps/wizard/`, `apps/calc-web/` | закрытые 23.09.2026 старая студия, мастер, калькулятор ТЭП ([apps/README.md](apps/README.md)); не править | нет |
| [core/](core/README.md) | ядро: `compute` (ТЭП), `model` (проект .grado), `reactive` (правки), `geom`, `connectors` (порталы), `render` (PDF/SVG/PPTX/DXF), `layout` (вёрстка) | да |
| [docs/](docs/INDEX.md) | документы: `wiki/`, `standards/`, `specs/`, `product/`, `ux/`, `guides/`, `team/`, `archive/` | да |
| [tools/](tools/README.md) | скрипты разработки: `gate.sh`, `wiki.py`, `docs_check.py`, `server_pull/` (выкладка сервером), `album_check.py`, генераторы стилей, хуки git | да |
| [packaging/](packaging/README.md) | сборка установщиков Windows и macOS (ГРАДО 2) и прежней студии | частично |
| [.claude/](.claude/README.md) | роли, навыки и хуки ИИ-агентов, настройки Claude Code | да |
| [.github/](.github/workflows/README.md) | проверки и автоматика GitHub (`workflows/`), шаблоны задач и PR | да |

## Файлы верхнего уровня

| файл | что это |
|---|---|
| [README.md](README.md) | титульная страница для человека: что это, как запустить, куда смотреть |
| [CLAUDE.md](CLAUDE.md) | память проекта для Claude Code: правила, процесс, железные правила (грузится в каждый ход, короткий) |
| [AGENTS.md](AGENTS.md) | вход для любых ИИ-агентов, указывает на CLAUDE.md и эту карту |
| `INDEX.md` | эта карта |
| `ГРАДО 2.command`, `ГРАДО 2.bat` | запуск двойным щелчком на macOS и Windows |
| `requirements.txt` | зависимости ГРАДО 2 (ссылка на `apps/grado2/requirements.txt`) |
| `requirements-cloud.txt`, `Dockerfile`, `.dockerignore` | облачный образ **закрытой студии**; к ГРАДО 2 не относятся |
| `.gitignore`, `.gitattributes` | настройки git (переводы строк для лаунчеров, исключённые файлы) |

## Куда идти по вопросу

| вопрос | файл |
|---|---|
| где в коде то-то | [docs/wiki/files.md](docs/wiki/files.md), функции — [docs/wiki/modules.md](docs/wiki/modules.md) |
| правила оформления альбома | [docs/wiki/album-rules.md](docs/wiki/album-rules.md) |
| как устроена программа | [docs/wiki/architecture.md](docs/wiki/architecture.md) |
| как писать код и документы | [docs/wiki/conventions.md](docs/wiki/conventions.md), [docs/CLAUDE.md](docs/CLAUDE.md) |
| как добавить источник, маршрут, лист, подпись, модуль, тест | [docs/wiki/howto.md](docs/wiki/howto.md) |
| как проверить, собрать альбом, выложить | [docs/wiki/recipes.md](docs/wiki/recipes.md) |
| процесс команды и GitHub | [docs/team/CYCLE.md](docs/team/CYCLE.md) |
| что менялось | [docs/grado2-changelog.md](docs/grado2-changelog.md) |
