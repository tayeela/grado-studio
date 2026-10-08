# core — общая библиотека ГРАДО 2

Здесь семь пакетов Python, на которых стоит программа `apps/grado2`: расчёт ТЭП, проектная база, журнал правок,
данные из порталов, геометрия, рендер листов и альбом. Каждый пакет лежит в папке `core/<имя>/`: код в `grado_<имя>/`,
тесты в `tests/`. Код опирается на стандартную библиотеку и пакеты из `apps/grado2/requirements.txt`: `certifi`, Pillow, shapely 2
(наложение, покрытие и привязки в `core/geom`), httpx и tenacity (запросы к порталам, `grado_connectors/netutil.py`).

Что где лежит во всём проекте: [docs/wiki/files.md](../docs/wiki/files.md).

| Пакет | Кто использует в `apps/grado2` | Тесты |
|---|---|---|
| `core/compute` | `server.py` | `core/compute/tests` |
| `core/model` | нет | `core/model/tests` |
| `core/reactive` | нет | `core/reactive/tests` |
| `core/connectors` | 13 файлов, в том числе тесты: `server.py`, `ogd_all.py`, `print_io.py` и др. | `core/connectors/tests` (запускает gate) |
| `core/geom` | `server.py` | `core/geom/tests` |
| `core/render` | 7 файлов, в том числе тесты: `server.py`, `album_io.py`, `print_io.py` и др. | `core/render/tests` |
| `core/layout` | `album_io.py`, `print_io.py` | `core/layout/tests` |

`core/model` и `core/reactive` в `apps/grado2` не импортируются. Их берут `core/connectors` (CLI и тест),
`core/layout` (демо и тесты), `core/render` (тест), закрытые `apps/studio` и `apps/wizard`. Файл
`packaging/py2app_setup.py` перечисляет оба пакета для сборки.

## Пакеты

### `core/compute` — расчёт ТЭП
Считает технико-экономические показатели (ТЭП) по данным: метрики описаны в JSON-пресетах, а не в коде.
Главные файлы: `engine.py` (класс `Engine`: граф зависимостей и пересчёт), `expressions.py` (безопасный вычислитель
формул), `presets/` (ТЭП по методике «Калькулятора 2.0» и для жилой застройки в Москве), `regulations/` (районы
Москвы и нормативный профиль). CLI: `__main__.py`.

### `core/model` — проектная база
Файл проекта `.grado` — это GeoPackage, который открывают QGIS и GDAL, с таблицами `grado_*`.
Главные файлы: `project.py` (класс `Project`: слои, у каждого объекта провенанс), `gpkg.py` (чтение и запись
GeoPackage на `sqlite3`), `classifier.py` (виды объектов; базовый набор в `presets/classifier_base.json`),
`geometry.py`, `dxf_export.py` (экспорт в DXF R12), `tep_bridge.py` (площади слоёв по ролям для ТЭП). CLI: `__main__.py`.

### `core/reactive` — журнал правок
Единый путь изменения модели: команда → дельта → журнал → подписчики. Журнал лежит в том же `.grado`
(таблицы `grado_journal`, `grado_branches`), поэтому даёт undo/redo и ветки вариантов.
Главные файлы: `session.py` (класс `Session`, через него идут все правки), `journal.py` (`Journal`), `deltas.py`
(формат дельты), `tep_link.py` (пересчёт ТЭП после правки). Демо: `__main__.py`.

### `core/connectors` — данные из порталов и файлов
Работает по одному контракту: discover → fetch → снимок → diff → импорт в проект через журнал.
Источники: НСПД (`nspd.py`), ФГИС ТП (`fgistp.py`), ГИС ОГД Москвы — ZIP (`gisogd.py`) и REST API
(`gisogd_api.py`), OSM через Overpass (`osm.py`), Яндекс vmap (`yandex_vmap.py`), рельеф (`terrain.py`),
адрес через Nominatim (`geocode.py`). Общее: `contract.py`, `store.py` (неизменяемые датированные снимки),
`diff.py`, `importer.py`, `crs.py` (системы координат Москвы), `netutil.py` (потолок размера ответа, редиректы
только на https), `clip.py` (обрезка по рамке), `shp_reader.py` (Shapefile без GDAL). `certs/` — корни Минцифры
для НСПД. CLI: `__main__.py`.

### `core/geom` — геометрия
Дуги, пути с пикетажем, офсеты и сопряжения, привязки, покрытие зон без дыр и нахлёстов, площадь ограничений
внутри границы для ТЭП. Главные файлы: `path.py` (класс `Path`: геометрия красных линий), `curves.py` (дуги,
хранятся параметрами), `snap.py` (привязки), `coverage.py` (зоны с общими границами), `overlay.py` (площадь
объединения полигонов), `affine.py` (поворот, масштаб, зеркало).

### `core/render` — рендер листов и карты
Одна стилевая машина: `scene.py` превращает проект в список операций рисования (`build_ops`). Два вывода
выполняют этот список: `backend_svg.py` (экран) и `backend_pdf.py` (PDF, кириллица через TrueType из `ttf.py`).
`backend_pptx.py` пишет PowerPoint; из `__init__.py` он не экспортируется, его берёт `apps/grado2/print_io.py`.
`style.py` читает стили из JSON-библиотек в `styles/`, `acad_lin.py` читает типы линий AutoCAD (.SHX, .LIN).

### `core/layout` — альбом
Документ → листы → фреймы: рамка листа, карта, легенда, таблица, текст, штамп. Главные файлы: `model.py`
(`Document`, `Page`, `Frame`), `frames.py` (виды фреймов; карта рисуется той же сценой, что и экран),
`compose.py` (сборка PDF и SVG из одних операций). Демо-альбом: `__main__.py`.

## Тесты

Один пакет, из корня репозитория. Команда та же, что в `tools/gate.sh`; вместо `geom` подставьте нужный пакет:

```bash
PP="core/render:core/geom:core/layout:core/compute:core/model:core/reactive:core/connectors:apps/grado2"
env PYTHONPATH="$PP" ~/.grado2/venv/bin/python -m unittest discover -s core/geom/tests -p "test_*.py"
```

- Из тестов core `tools/gate.sh` запускает только `core/connectors/tests`. Тесты остальных пакетов после правки
  запускайте этой командой вручную.
- Тесты `apps/grado2/tests` (их gate запускает) тоже импортируют пакеты core.
- В `core/render/tests/test_render.py` один тест (`test_frontend_styles_passthrough`) подключает закрытую
  `apps/studio/studio_core.py`.

## Правила

- Готовые библиотеки лучше самописного кода; условия для новой зависимости — в `core/CLAUDE.md`. Уже есть `certifi`, Pillow, shapely, httpx, tenacity.
- ЛГР-стили `core/render/grado_render/styles/*.json` генерируются, кроме `default.json`. Правьте генератор и
  запускайте его: `moscow_lgr.json` ← `tools/gen_moscow_lgr.py`, `moscow_genplan.json` ← `tools/gen_moscow_genplan.py`,
  `osm_highway.json` ← `tools/gen_osm_highway.py`, `redln97.json` ← `tools/gen_redln97.py`. Генератора для
  `default.json` в `tools/` нет.
- Порталы (ГИС ОГД, ЕГКО, НСПД, Яндекс, Overpass): паузы, без параллельных загрузок; запросы и повторы — только
  `grado_connectors/netutil.py` (httpx + tenacity, не больше трёх попыток). Коннекторы порталов лежат в `core/connectors`, но паузы есть и в `apps/grado2`
  (`server.py`, `sat_io.py`, `ogd_all.py`, `ogd_warm.py`), поэтому при новом обращении к порталу проверяйте оба места.
- Координаты: всё, что программа показывает, принимает и выгружает, — МСК (как в QGIS). Преобразование между МСК
  и системой ГИС ОГД — в `core/connectors/grado_connectors/crs.py`. Схему не обсуждать и не калибровать
  (CLAUDE.md, правило 3).
- HTTPS: проверку сертификатов не отключать. Для НСПД нужны корни Минцифры:
  `core/connectors/grado_connectors/certs/README.txt` (CLAUDE.md, правило 4).
