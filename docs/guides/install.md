# Запуск ГРАДО 2

ГРАДО 2 — это небольшой сервер на вашем компьютере и страница в обычном браузере (адрес `http://localhost:8650`).
Данные никуда не уходят: сервер слушает только этот компьютер; интернет нужен для карт-подложек и выгрузки данных с порталов.

## Mac и Windows — двойной клик

| система | файл в корне репозитория | где живёт окружение |
|---|---|---|
| macOS | `ГРАДО 2.command` | `~/.grado2/venv` |
| Windows | `ГРАДО 2.bat` | `%LOCALAPPDATA%\GRADO2\venv` |

Первый запуск сам создаёт окружение и ставит зависимости из `apps/grado2/requirements.txt` (ezdxf, certifi, pillow): нужны интернет
и Python 3.10 или новее с python.org. Следующие запуски открывают браузер за несколько секунд.

## Установщики

Сборка установщиков — в GitHub Actions, задача `build` файла `.github/workflows/grado2-release.yml`: запускается по тегу `grado2-v*`
и вручную (Actions → «ГРАДО 2 release» → Run workflow). Результат — установщик Windows (`.exe`, Inno Setup) и образ macOS (`.dmg`).
Как собрать самому — [../../packaging/README.md](../../packaging/README.md).

## Из исходников

```sh
python3 apps/grado2/server.py            # порт 8650
python3 apps/grado2/server.py 8651       # другой порт
python3 apps/grado2/server.py --hub      # совместный режим (аккаунты и проекты на сервере)
```

Переменные окружения и устройство программы — [../../apps/grado2/README.md](../../apps/grado2/README.md).
Проекты по умолчанию лежат в `Документы/ГРАДО 2` (переменная `GRADO2_PROJECTS` меняет папку). Тесты запускайте только на копиях проектов
и на другом порту: порт 8650 и эта папка — рабочие данные владельца.

## Сайт

Рабочая копия для совместной работы — <https://grado.tailink.tech> (сервер `msk`; доступ выдаёт владелец).
Сайт обновляет сам сервер: раз в 5 минут он забирает ветку `main` с GitHub ([../../tools/server_pull/README.md](../../tools/server_pull/README.md),
рецепт — [../wiki/recipes.md](../wiki/recipes.md)).

## Данные порталов

- ГИС ОГД, ЕГКО, OSM (Overpass), Яндекс — работают без настройки.
- НСПД требует корневые сертификаты Минцифры в `~/.grado2/ca/` — какие и откуда, написано в
  [../../core/connectors/grado_connectors/certs/README.txt](../../core/connectors/grado_connectors/certs/README.txt). Проверку сертификатов отключать нельзя.
- Из облачных сессий НСПД недоступен напрямую; для них есть релей на российском сервере — [../../tools/nspd_relay/README.md](../../tools/nspd_relay/README.md).

## Если что-то не запускается

Первым делом `tools/gate.sh` (тесты) и консоль браузера. Известные подводные камни и срочные исправления —
[../wiki/recipes.md](../wiki/recipes.md).
