# Сборка установщиков (packaging)

Здесь лежат файлы, из которых собирают ГРАДО 2: установщик для Windows (`.exe`) и программа для macOS (`.app`, образ `.dmg`).
Сборку обычно делает GitHub Actions. Вручную её можно повторить по командам из раздела «Как собрать вручную».
Файлы закрытой студии «ГРАДО Студия» лежат здесь же. Их не развивают.

## Текущие файлы (ГРАДО 2)

| Файл | Что это |
|---|---|
| `grado2.spec` | Спецификация PyInstaller: одна папка для Windows (`.exe`, без окна консоли) и macOS (`.app`). Кладёт в сборку `apps/grado2/web`, стили ЛГР (`core/render/grado_render/styles`), пресеты и регламенты (`core/compute/grado_compute`) и `docs/standards/redln97`. |
| `grado2_entry.py` | Точка входа программы. Запускает `server.main([])` из `apps/grado2/server.py`. Ошибка при старте пишется в `startup-error.log` в папке данных: на Windows это `%LOCALAPPDATA%\GRADO2`, иначе `~/.grado2`. |
| `grado2-installer.iss` | Скрипт Inno Setup 6 для Windows. Берёт папку `dist/ГРАДО 2` и выдаёт `dist/installer/GRADO2-Setup-<версия>.exe`. |
| `AppIcon.svg` | Исходник значка. |
| `AppIcon.icns` | Значок для macOS. `grado2.spec` берёт его на Mac. |
| `AppIcon.ico` | Значок для Windows. Его берут `grado2.spec` и `grado2-installer.iss`. В репозитории нет скрипта, который его создаёт. |
| `build_icon.sh` | Делает `AppIcon.icns` из `AppIcon.svg`. Нужны ImageMagick (`magick`) и `iconutil`, то есть Mac. Запускать после правки SVG. |

## Сборка в GitHub Actions

Файл: [grado2-release.yml](../.github/workflows/grado2-release.yml), job `build`.

- Запуск: вручную (`workflow_dispatch`) или тегом `grado2-v*`. На pull request job `build` не запускается.
- Перед ним идёт job `test`: юнит-тесты и браузерные сценарии на Ubuntu. Он запускается и на pull request, если менялись `apps/grado2/**`, `core/**`, `packaging/grado2*` или сам workflow.
- `build` идёт на `windows-latest` и `macos-latest`. Шаги: Python 3.12, установка `apps/grado2/requirements.txt` и `pyinstaller>=6.14,<7`, сборка по `packaging/grado2.spec`, проверка запуска (программа отвечает на `/api/health`).
- Затем: установщик на Windows (Inno Setup, ставится через Chocolatey) или образ на macOS (`hdiutil`).
- Шагов подписи кода и нотаризации macOS в workflow нет.

| Результат | Файл | Где появляется |
|---|---|---|
| Установщик Windows | `dist/installer/*.exe` | артефакт запуска `grado2-windows-latest` |
| Образ macOS | `dist/GRADO2.dmg` | артефакт запуска `grado2-macos-latest` |

Только при запуске по тегу `grado2-v*` те же файлы публикуются ещё и в GitHub Release (шаг `Release`).

## Как собрать вручную

Команды запускайте из корня репозитория. Сборка создаёт папки `build/` и `dist/`, обе есть в `.gitignore`.

```
python -m pip install -r apps/grado2/requirements.txt "pyinstaller>=6.14,<7"
pyinstaller --noconfirm --clean packaging/grado2.spec
```

Результат: `dist/ГРАДО 2/ГРАДО 2.exe` на Windows или `dist/ГРАДО 2.app` на macOS.

Установщик Windows, нужен Inno Setup 6. Версия — поле `version` в `apps/grado2/web/version.json`:

```
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "/DMyAppVersion=<версия>" packaging\grado2-installer.iss
```

Без `/DMyAppVersion` в `.iss` останется значение по умолчанию, которое не совпадает с `apps/grado2/web/version.json`.

Образ macOS, после сборки на Mac:

```
hdiutil create -volname "ГРАДО 2" -srcfolder "dist/ГРАДО 2.app" -ov -format UDZO "dist/GRADO2.dmg"
```

Значок, только на Mac и только после правки `AppIcon.svg`:

```
packaging/build_icon.sh
```

## Старые файлы закрытой студии (не развивать)

Студия (`apps/studio`), мастер (`apps/wizard`) и веб-калькулятор (`apps/calc-web`) закрыты 23.09.2026: их не развивают и не чинят. Workflow для их сборки удалён (см. `docs/archive/studio/session-log-archive.md`). Ни один workflow сейчас эти файлы не вызывает.

| Файл | Что собирал |
|---|---|
| `build_macos.py` | «ГРАДО Студия.app» через py2app: подпись, проверка universal2, DMG. Нотаризация, если задан `MACOS_NOTARY_PROFILE`. Только на Mac. |
| `py2app_setup.py` | Настройки py2app для «ГРАДО Студия.app», вызывается из `build_macos.py`. Точка входа: `apps/studio/server.py`. |
| `windows.spec` | PyInstaller-сборка «ГРАДО Студия» для Windows, папка `dist/ГРАДО Студия`. |
| `windows-installer.iss` | Установщик Inno Setup для «ГРАДО Студия». Связывает файлы `.grado` с программой. |
| `windows_entry.py` | Точка входа Windows-сборки студии. Данные в папке `GRADO Studio` внутри `%LOCALAPPDATA%` или по пути из `GRADO_STUDIO_DATA_DIR`. |
| `windows_version.py` | Пишет `build/windows_version_info.txt` (сведения о версии для `.exe`) из `apps/studio/web/version.json`. |
| `build_pages.py` | Статическая браузерная редакция студии для GitHub Pages: копирует нужные файлы из `apps/studio/web` в папку, которую задают аргументом, и создаёт страницу и файл стилей. |
| `build_support.py` | Общая функция `data_files_for_tree`: список файлов для py2app и PyInstaller, без кэшей, тестов и локальных настроек. |

Ссылаются на `apps/studio`, `apps/wizard` или `apps/calc-web` (проверено `git grep`): `build_macos.py`, `py2app_setup.py`, `windows.spec`, `windows_version.py`, `build_pages.py`. Тесты `apps/studio/tests/test_packaging.py` импортируют `build_pages.py`, `build_support.py`, `windows_version.py` и `windows_entry.py`.

Вне `packaging/`, из того же набора: `Dockerfile` и `requirements-cloud.txt` в корне. Это облачный режим закрытой студии. Dockerfile копирует `core`, `apps/studio` и `apps/wizard` и запускает `python apps/studio/server.py --cloud`.
