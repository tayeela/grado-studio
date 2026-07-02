# ГРАДО Студия

Единая среда градпроектирования: ГИС-анализ + точное 2D-черчение + вёрстка альбомов
над одной моделью данных. Для этапов: анализ существующего положения → АГК → ППТ.

Архитектура: [docs/architecture.md](docs/architecture.md)

## Состав репозитория

```
core/compute/    ТЭП-движок (эталонная реализация на Python; метрики — данные, а не код)
core/model/      проектная БД: .grado = GeoPackage + классификатор + провенанс
core/reactive/   журнал дельт: undo/redo, ветки вариантов, живой пересчёт ТЭП
core/connectors/ сервис данных: НСПД, ФГИС ТП, ГИС ОГД Москвы; снимки, диф, подписки
core/geom/       кривые, пикетаж, офсеты, привязки, топологическое покрытие зон
core/render/     стилевая машина + два бэкенда: SVG (экран) и собственный PDF
core/layout/     альбом: листы, карта, легенда, таблицы, основная надпись ГОСТ
apps/calc-web/   веб-калькулятор ТЭП поверх того же JSON-пресета
docs/            архитектура и решения
```

## Модуль compute

Декларативные метрики (JSON-пресет) + граф зависимостей + инкрементальный пересчёт.
Первый пресет — `moscow_krt.json`: ТЭП жилой застройки по московской методике КРТ
(константы восстановлены из genplan.tech/calc; перед применением в документации
сверить с действующей редакцией МНГП).

```sh
cd core/compute
python3 -m unittest discover -s tests        # тесты
python3 -m grado_compute --set terr_area=15  # расчёт в консоли
python3 -m grado_compute --json              # вывод в JSON
```

## Веб-калькулятор

```sh
python3 -m http.server 8642 --directory .
# открыть http://localhost:8642/apps/calc-web/?terrArea=15&restrictArea=0
```

Параметры URL совместимы с genplan.tech (`terrArea`, `restrictArea`) и дополняются
нативными идентификаторами пресета (`density`, `ratio_zh`, ...).

## Модуль model

Файл проекта `.grado` — честный GeoPackage (открывается QGIS/GDAL) с расширенными
таблицами `grado_*`. Слои привязаны к классификатору (JSON-пресет), провенанс
(источник, дата, документ) обязателен на каждом объекте. Мост `tep_bridge`
подставляет площади слоёв с ролями (`terr_area`, `restrict_area`) во входы
ТЭП-движка — ТЭП считается из геометрии, а не из ручного ввода.

```sh
cd core/model
python3 -m unittest discover -s tests          # тесты
python3 -m grado_model demo /tmp/демо.grado    # демо-проект
python3 -m grado_model tep  /tmp/демо.grado    # ТЭП из геометрии
```

## Модуль reactive

Единый путь изменений: команда → дельта → журнал (таблицы `grado_journal`,
`grado_branches` в том же файле проекта) → подписчики. Один журнал закрывает
undo/redo (в т.ч. между сессиями), ветки вариантов концепции и — позже —
синхронизацию. `TepLink` пересчитывает ТЭП при каждой правке геометрии.

```sh
cd core/reactive
python3 -m unittest discover -s tests                 # тесты
PYTHONPATH=. python3 -m grado_reactive demo /tmp/д.grado  # сквозной сценарий
```

## Модуль connectors

Контракт: `discover` → `fetch` → неизменяемый датированный снимок (sha256,
фиксация ИРД) → `diff` → импорт в проект одной записью журнала. Подписки:
`check()` замечает изменения документа на территории. Протоколы сняты с
работающего GRADO-моста: НСПД (перехват fetch с intersects, EPSG:3857,
options→opt_*), ФГИС ТП (json_layers_stp_list.jsp + WFS 2.0.0 с CQL по uin
и mt_classid; транспорт заменяемый — портал отдаёт данные только в сессии),
ГИС ОГД Москвы (ZIP-в-ZIP, SHP в МСК-50 через ogr2ogr из QGIS-LTR).

```sh
cd core/connectors
python3 -m unittest discover -s tests
python3 -m grado_connectors ingest-nspd захват.json --store снимки/
python3 -m grado_connectors import <SID> --project п.grado --layer cad.parcel \
    --map cad_num=opt_cad_num --store снимки/
```

## Модули geom / render / layout

- geom: дуги параметрически (линеаризация по сагитте), сопряжения красных
  линий, пикетаж, офсеты (G1-цепи поэлементно, ломаные miter), привязки с
  CAD-приоритетами, топологическое покрытие зон (общее ребро одно, правка
  двигает обе зоны, validate ловит дырки/нахлёсты).
- render: стиль — данные к коду классификатора; сцена собирает один список
  операций, его исполняют SVG-бэкенд (экран) и собственный PDF-писатель
  (вектор, кириллица через встраиваемый TrueType, Identity-H) — WYSIWYG.
- layout: документ → листы → фреймы (рамка ГОСТ, карта, легенда, таблица,
  упрощённая основная надпись формы 3). Таблица ТЭП живая — из движка.

```sh
cd core/layout
PYTHONPATH=../render:../model:../compute:../geom:../connectors \
    python3 -m grado_layout demo out/альбом.pdf
```

## Дорожная карта модулей

1. compute — ТЭП-движок (готов прототип)
2. model — проектная БД: GeoPackage, классификатор, провенанс, мост в ТЭП (готов прототип)
3. reactive — журнал дельт: undo/redo, ветки, живой ТЭП (готов прототип)
4. connectors — сервис данных: НСПД/ФГИС ТП/ГИС ОГД, снимки, диф, подписки (готов прототип)
5. geom / render / layout — кривые, топология, два бэкенда, альбом (готовы прототипы)
