# apps — программы репозитория

Здесь четыре папки с программами. Рабочая программа одна: `grado2` (ГРАДО 2). Папки `studio`, `wizard` и `calc-web` закрыты решением владельца 23.09.2026: они не развиваются и не чинятся, их не править.

| файл или папка | что это | кто использует |
|---|---|---|
| `grado2/` | ГРАДО 2: рабочая программа, локальный сервер и браузерный интерфейс | `ГРАДО 2.command`, `ГРАДО 2.bat`, `packaging/grado2_entry.py`, `tools/gate.sh`, `.github/workflows/grado2-release.yml` |
| `studio/` | старая ГРАДО Студия, закрыта: `server.py`, `studio_core.py`, `webhub.py`, `web/`, `tests/`. Не править | `core/render/tests/test_render.py` (импорт `studio_core`), `packaging/build_pages.py`, `packaging/py2app_setup.py`, `packaging/windows.spec`, `packaging/windows_version.py`, `Dockerfile` (копирует папку и запускает `apps/studio/server.py --cloud`) |
| `wizard/` | мастер территории, закрыт: пакет `grado_wizard/`, `tests/`. Не править | `packaging/py2app_setup.py`, `packaging/windows.spec`, `Dockerfile` (копирует папку) |
| `calc-web/` | веб-калькулятор ТЭП, закрыт: `index.html`, `engine.js`. Не править | `packaging/py2app_setup.py`, `packaging/windows.spec` (копируют папку в сборку) |

## Почему закрытые папки остались

Код оставлен, потому что на него ссылаются тесты ядра и сборка:

- `core/render/tests/test_render.py` импортирует `studio_core` (строки 699–700).
- `packaging/` ссылается на все три папки; `Dockerfile` — на `apps/studio` и `apps/wizard`.
- `CLAUDE.md` пишет: старая студия, мастер и веб-калькулятор закрыты, код оставлен для тестов ядра, не править.

## Запуск и проверка

- macOS: двойной щелчок по `ГРАДО 2.command` в корне репозитория.
- Windows: двойной щелчок по `ГРАДО 2.bat`.
- Вручную: `python3 apps/grado2/server.py`. Порт 8650 по умолчанию; переменная `GRADO2_PORT` задаёт другой порт.
- Проверка программы: `tools/gate.sh`; `E2E=1 tools/gate.sh` добавляет браузерные сценарии.

Подробности о запуске, проверке и переменных окружения: [grado2/README.md](grado2/README.md).

## Связанное

- [../README.md](../README.md) — корневой README репозитория.
- [../CLAUDE.md](../CLAUDE.md) — память проекта: что за программа, закрытые папки, железные правила.
- [../docs/INDEX.md](../docs/INDEX.md) — оглавление документов.
- [../docs/wiki/INDEX.md](../docs/wiki/INDEX.md) и [../docs/wiki/modules.md](../docs/wiki/modules.md) — вики: файлы и модули, генерируется из кода.
- [../docs/archive/studio/session-log-archive.md](../docs/archive/studio/session-log-archive.md) — запись о закрытии 23.09.2026 решением владельца.
