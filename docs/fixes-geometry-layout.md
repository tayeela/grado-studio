# Фиксы модели: CAD-примитивы, стили и последовательная компоновка альбомов

Документ фиксирует направление переделки `apps/studio` и ядерных модулей.
Цель: уйти от логики "тип объекта = зона/здание/красная линия" к CAD/GIS
модели, где базой являются геометрические примитивы, стили, слои и роли
данных. Семантика градостроительства должна быть конфигурацией слоя или
объекта, а не ветвлением в коде инструмента.

## 1. Текущая проблема

Сейчас приложение смешивает четыре разные сущности в одно поле `kind`:

- геометрию: точка, линия, полигон;
- слой: граница, здание, красная линия, зона;
- стиль: цвет, штрих, заливка, порядок отрисовки;
- предметный смысл: участвует ли объект в ТЭП, на каком листе показывать,
  какие атрибуты редактировать.

Из-за этого появляются жесткие места:

- `apps/studio/web/app.js`: `STYLES`, `Z_ORDER`, `KIND_NAMES`,
  `DEFAULT_PROPS`, `TOOL_CODES`, панели свойств и отрисовка завязаны на
  `kind`;
- `apps/studio/studio_core.py`: `KIND_TO_CODE`, `KIND_ATTRS`,
  `_geom_for`, `compute_tep`, `grado_to_features` конвертируют холст через
  фиксированные градостроительные типы;
- `core/render/grado_render/style.py`: стили привязаны к коду
  классификатора, но не являются отдельной библиотекой стилей;
- `apps/wizard/grado_wizard/sheets.py`: листы альбома напрямую знают
  конкретные слои `terr.boundary`, `cad.parcel`, `tp.func_zone`,
  `oks.building` и т.д.

Это удобно для демо, но мешает настоящему CAD-поведению: пользователь
должен чертить полилинии, полигоны, точки, размеры, штриховки и тексты, а
потом назначать им слой, стиль и смысл.

## 2. Целевая модель данных

### 2.1. Геометрия

Внутренний объект холста должен иметь геометрический тип, независимый от
градостроительной семантики:

```json
{
  "id": "uuid",
  "geometry_type": "point | polyline | polygon | multipolygon | arc | text | dimension",
  "geometry": {
    "coordinates": []
  },
  "layer_id": "project.apo.buildings",
  "style_id": "building.fill.orange",
  "attrs": {},
  "source": {
    "type": "manual | nspd | gisogd | fgistp | imported_file",
    "snapshot_id": null,
    "doc_ref": null
  }
}
```

Правило: инструменты создают только геометрию. Слой и стиль назначают
смысл и внешний вид.

### 2.2. Слой

Слой становится главным объектом управления:

```json
{
  "id": "project.apo.red_lines",
  "title": "Красные линии",
  "group": "Проектные решения",
  "geometry_types": ["polyline"],
  "default_style_id": "red.line.projected",
  "semantic_class": "pp.red_line",
  "stage": "project",
  "roles": ["album.apo", "cad.export"],
  "tep_roles": [],
  "visible": true,
  "locked": false,
  "source_kind": "manual"
}
```

Слой может быть исходным, расчетным, проектным, оформительским или
аннотационным. Код классификатора остается, но становится атрибутом слоя,
а не типом инструмента.

### 2.3. Стили

Стиль должен быть отдельной сущностью, пригодной для canvas, PDF, SVG и
DXF:

```json
{
  "id": "red.line.projected",
  "title": "Красная линия проектируемая",
  "stroke": {
    "color": "#d91a1a",
    "width_mm": 0.6,
    "dash_mm": null,
    "cap": "round",
    "join": "round"
  },
  "fill": null,
  "hatch": null,
  "marker": null,
  "label": {
    "field": "status",
    "enabled": false
  },
  "z_index": 600
}
```

Нужны библиотеки:

- `styles/default.json` - базовые CAD/GIS стили;
- `styles/moscow_agk.json` - стили АГК;
- `styles/gis_sources.json` - стили исходных слоев НСПД/ГИСОГД/ФГИС ТП;
- `styles/print.json` - печатные переопределения при необходимости.

## 3. Фиксы по frontend

### 3.1. Разделить инструменты и слои

Заменить инструменты:

- было: `Граница`, `Зона`, `Ограничение`, `Здание`, `Красная линия`,
  `Соцобъект`;
- должно стать: `Выбор`, `Точка`, `Полилиния`, `Полигон`,
  `Прямоугольник`, `Дуга`, `Текст`, `Размер`, `Штриховка`,
  `Офсет/Сопряжение`.

Пользователь выбирает активный слой отдельно. Например:

- активный инструмент: `Полилиния`;
- активный слой: `Красные линии`;
- результат: объект `geometry_type=polyline` на слое `project.apo.red_lines`
  со стилем слоя.

### 3.2. Убрать `kind` как основу UI

В `apps/studio/web/app.js` заменить:

- `STYLES[kind]` на `styleById[feature.style_id || layer.default_style_id]`;
- `Z_ORDER` на сортировку по `style.z_index` и порядку слоя;
- `KIND_NAMES` на `layers[layer_id].title`;
- `DEFAULT_PROPS[kind]` на `layer.attr_schema.defaults`;
- `state.hidden[kind]` на `layer.visible`;
- `SHARED_KINDS` на флаг слоя `topology: "coverage"`;
- `TOOL_CODES` на геометрические команды.

### 3.3. Панель свойств

Панель свойств должна состоять из блоков:

1. Геометрия: тип, площадь, длина, координаты, количество вершин.
2. Слой: выбор слоя, видимость, блокировка.
3. Стиль: стиль объекта или "как у слоя".
4. Атрибуты: поля из схемы слоя.
5. Операции: удалить, дублировать, офсет, сопряжение, разрезать, объединить.

Градостроительные поля появляются только потому, что активный слой имеет
атрибутную схему. Например, поле `floors` показывается не у всех
полигонов, а только у слоя с `semantic_class=oks.building`.

### 3.4. Совместимость старых проектов

На период миграции оставить адаптер:

```js
legacyKindToLayer = {
  boundary: "project.territory.boundary",
  zone: "project.tp.func_zone",
  restrict: "source.constraints.restrict",
  building: "project.apo.buildings",
  public: "project.apo.public_zones",
  redline: "project.apo.red_lines",
  social: "project.social.objects",
  parcel: "source.nspd.parcels",
  dim: "annotation.dimensions"
}
```

Старый `kind` можно читать, но новые сохранения должны писать
`geometry_type`, `layer_id`, `style_id`, `attrs`.

## 4. Фиксы по backend/core

### 4.1. `studio_core.py`

Заменить жесткую связку:

- `KIND_TO_CODE`;
- `KIND_ATTRS`;
- `_geom_for(feature)`;
- `CODE_TO_KIND`.

На конфигурационную схему:

```python
LAYER_TEMPLATES = load_json("layer_templates/agk_default.json")

def layer_code(feature):
    return layers[feature["layer_id"]]["semantic_class"]

def attrs_for_feature(feature):
    schema = layers[feature["layer_id"]].get("attr_schema", {})
    return apply_defaults_and_validate(feature.get("attrs", {}), schema)

def geom_for_feature(feature):
    return convert_geometry(feature["geometry_type"], feature["geometry"])
```

### 4.2. Расчеты ТЭП

Расчеты не должны искать `f["kind"] == "boundary"` или
`f["kind"] == "building"`.

Должно быть:

- площадь территории: сумма площадей слоев с `tep_role=terr_area`;
- ограничения: сумма площадей слоев с `tep_role=restrict_area`;
- факт по посадке: запрос по слоям с `semantic_class=oks.building` или
  `tep_role=building_footprint`;
- зоны: проверка coverage для слоев с `topology=coverage`.

Пример правила:

```json
{
  "id": "fact_spp",
  "query": {
    "geometry_type": "polygon",
    "semantic_class": "oks.building"
  },
  "formula": "sum(area_m2(feature) * feature.attrs.floors) / 1000"
}
```

### 4.3. Render

`StyleSet` должен читать стили из данных проекта:

1. стиль объекта;
2. стиль слоя;
3. стиль semantic_class;
4. fallback.

Нельзя считать, что `code == style_id`. Код классификатора и стиль - разные
вещи.

### 4.4. DXF

DXF-экспорт должен строить слои из `Layer.title/dxf_name`, а не из
константы `LAYERS`.

Минимальные поля слоя:

```json
{
  "dxf_name": "KRASNYE_LINII",
  "dxf_color": 1,
  "dxf_linetype": "CONTINUOUS"
}
```

## 5. Последовательная логика компоновки альбома

Компоновка должна работать не как список вручную написанных листов, а как
pipeline: источники -> нормализация -> слои -> наборы слоев -> листы ->
альбом.

### 5.1. Источники

Исходные данные сохраняются неизменяемыми снимками:

- НСПД: участки, ЗОУИТ, кадастровые сведения;
- ГИСОГД: градпланы, зоны, ИРД, инженерные ограничения;
- ФГИС ТП: документы территориального планирования;
- ручной импорт: SHP/GPKG/DXF/PDF/GeoTIFF.

Каждый импорт создает:

- `SourceSnapshot`;
- `ImportBatch`;
- набор слоев `source.*`;
- провенанс у каждого объекта.

### 5.2. Нормализация слоев

Пример групп:

```json
[
  {
    "id": "source.nspd.parcels",
    "title": "Земельные участки ЕГРН",
    "source_kind": "nspd",
    "semantic_class": "cad.parcel",
    "geometry_types": ["polygon", "multipolygon"],
    "stage": "existing",
    "roles": ["existing.base", "album.location", "album.ortho"]
  },
  {
    "id": "source.gisogd.restrictions",
    "title": "Ограничения ГИСОГД",
    "source_kind": "gisogd",
    "semantic_class": "terr.restrict",
    "geometry_types": ["polygon", "multipolygon"],
    "stage": "existing",
    "roles": ["existing.base", "album.base_plan"],
    "tep_roles": ["restrict_area"]
  },
  {
    "id": "project.apo.buildings",
    "title": "Проектируемая застройка",
    "source_kind": "manual",
    "semantic_class": "oks.building",
    "geometry_types": ["polygon"],
    "stage": "project",
    "roles": ["album.apo", "album.tep"],
    "tep_roles": ["building_footprint"]
  }
]
```

### 5.3. Наборы слоев

Лист должен ссылаться не на конкретные коды, а на `LayerSet`.

```json
{
  "id": "layerset.existing_position",
  "title": "Существующее положение",
  "include_roles": ["existing.base"],
  "exclude_stages": ["project"],
  "order": [
    "source.basemap",
    "source.fgistp.functional_zones",
    "source.gisogd.restrictions",
    "source.nspd.parcels",
    "project.territory.boundary"
  ]
}
```

Примеры обязательных наборов:

- `layerset.location` - расположение территории;
- `layerset.ortho` - ортофото + границы + участки;
- `layerset.existing_position` - существующее положение;
- `layerset.planning_docs` - обеспеченность ГПЗУ/ППТ/ИРД;
- `layerset.apo` - архитектурно-планировочная организация;
- `layerset.social` - социальная инфраструктура;
- `layerset.parking` - парковки;
- `layerset.greening` - озеленение;
- `layerset.red_lines` - красные линии/УДС.

### 5.4. Шаблоны листов

Лист должен быть декларативным:

```json
{
  "id": "sheet.existing_position",
  "title": "Опорный план. Существующее положение",
  "page": {"format": "A3", "orientation": "landscape"},
  "frames": [
    {
      "type": "map",
      "rect": [12, 10, 280, 277],
      "layerset": "layerset.existing_position",
      "scale": "fit"
    },
    {
      "type": "legend",
      "rect": [302, 40, 106, 150],
      "source": "map.visible_layers"
    },
    {
      "type": "source_table",
      "rect": [302, 200, 106, 70],
      "source": "project.source_snapshots"
    }
  ]
}
```

Текущие функции `base_plan_sheet`, `apo_sheet`, `ortho_sheet` надо оставить
как генераторы из шаблонов или постепенно заменить на JSON-шаблоны.

## 6. Последовательность альбома

Целевой порядок для альбома уровня АГК:

1. Титульный лист.
2. Расположение территории.
3. Ортофотоплан.
4. Фотофиксация.
5. Схема границ разработки / правообладателя.
6. Существующее положение из НСПД/ГИСОГД/ФГИС ТП.
7. Обеспеченность ГПЗУ.
8. Обеспеченность ППТ/ИРД.
9. Схема архитектурно-планировочной организации.
10. Сводные ТЭП.
11. Социальная инфраструктура.
12. Парковки.
13. Озеленение.

Каждый следующий лист должен опираться на предыдущие слои:

- сначала исходные данные;
- затем ограничения и документы;
- затем проектные решения;
- затем расчетные/проверочные схемы;
- затем сводные таблицы.

## 7. Миграция по шагам

### Шаг 1. Ввести `layers`, `styles`, `features` v2 на фронте — готово (v0.11.0)

- ~~Добавить в `state` словари `layers` и `styles`~~ — `LAYERS_V2`/`STYLES_V2`
  в app.js; стили — чистые данные (подпись через `label_field`, не функция).
- ~~Новые объекты писать в формате v2~~ — `addFeature` пишет `layer_id` +
  `geometry_type`; `kind` остаётся legacy-мостом к API ядра до шага 4.
- ~~Старые объекты мигрировать при загрузке~~ — `upgradeFeature()` на всех
  точках входа: restore из localStorage (включая старый `hidden` по kind),
  открытие .grado, мост расширения, импорт НСПД, демо, офсеты.
- ~~Панель слоев строить по `state.layers`~~ — видимость теперь
  `layer.visible`, сохраняется как `layersVisible` по layer_id.
- Бонус: `SHARED_KINDS` заменён флагом слоя `topology: "coverage"`,
  `DEFAULT_PROPS` — методом слоя `defaults()`, `Z_ORDER` — порядком
  массива слоёв, `KIND_NAMES` — `layer.title`.

Критерий выполнен: демо выглядит так же (проверено в браузере), в JSON
объектов есть `layer_id`/`geometry_type`, UI не читает словари по `kind`.

### Шаг 2. Геометрические инструменты — готово (v0.12.0)

- ~~Заменить предметные кнопки на `point/polyline/polygon/rectangle`~~ —
  тулбар: Выбор / Точка / Полилиния / Полигон / Прямоугольник (протянуть =
  прямоугольник, клик = контур) / Размер / Измерение.
- ~~Добавить выбор активного слоя~~ — клик по имени слоя в панели «Слои»
  (чекбокс отвечает только за видимость), подсветка активного, индикатор
  в футере; несовместимая пара инструмент↔слой чинится автоматически в обе
  стороны (полигон при точечном слое → первый полигональный слой; выбор
  точечного слоя → инструмент «Точка»).
- ~~Старые быстрые кнопки как пресеты~~ — клавиши G Z O B P L S = слой +
  его естественный инструмент (`naturalToolFor`: у зданий — прямоугольник,
  у размеров — dim).

Критерий выполнен (проверено e2e в браузере): один инструмент «Полигон»
создал границу, зону и здание — различался только активный слой;
спецповедения красных линий (радиус/пикетаж/офсет) сохранились.

### Шаг 3. Конфигурационные стили — готово (v0.13.0)

- ~~Вынести стили в JSON~~ — `core/render/grado_render/styles/default.json`:
  один источник (цвет hex, ширина отдельно `width_mm` для листа и
  `width_px` для холста, `dash_*`, `hatch`, `label_field`, `codes`
  классификатора, `dxf` имя+цвет ACI).
- ~~Синхронизировать canvas/PDF/DXF~~ — `style.py` строит `Style`
  (rgb 0..1, мм) и индекс код→стиль из JSON; `frontend_styles()`
  отдаёт холсту (px, rgba); `dxf_layers_from_styles()` кормит DXF-экспорт
  (project_to_dxf получил параметр `layers=`, модель осталась независимой).
- Resolver object→layer→semantic — частично: `StyleSet.resolve(code)`
  по коду классификатора (пайплайн альбома работает от кодов слоёв);
  полная цепочка с per-object style_id — вместе с MODEL-01 (у объектов
  .grado ещё нет поля style_id).

Критерий выполнен: тест `test_editing_json_changes_dxf` (правка имени
слоя в JSON меняет DXF), холст читает стили из `/api/styles` (styleOf →
STYLES_V2), альбомный PDF собирается через StyleSet из того же JSON.
Проверено e2e: демо визуально без изменений, DXF со слоями из JSON,
альбом 5 листов.

### Шаг 4. Расчетные роли вместо `kind` — готово (v0.13.1)

- ~~compute_tep на layer roles~~ — `make_engine` собирает площади входов
  через `_role_areas` по `tep_role` слоёв (terr_area/restrict_area из
  классификатора), не по `kind == "boundary"/"restrict"`.
- ~~zones_report на topology=coverage~~ — покрытие проверяется для слоёв
  с флагом `topology: "coverage"` (добавлен в классификатор для
  tp.func_zone и в парсер ClassifierClass).
- ~~факт СПП по semantic query~~ — сумма по слоям с
  `tep_role="building_footprint"` (добавлена роль на oks.building), не по
  `kind == "building"`.
- Мост: `_class_of` резолвит объект холста в класс классификатора через
  KIND_TO_CODE (kind — транспорт до шага 6 source pipeline).

Критерий выполнен: тест `test_new_building_layer_counts_without_code_change`
добавляет слой-здание только записью в классификатор + карту kind→код,
и ТЭП его учитывает без правки compute_tep. Проверено e2e по HTTP:
terr/restrict/факт-СПП/покрытие считаются по ролям.

### Шаг 5. LayerSet и шаблоны листов — частично готово (v0.14.0)

- ~~Ввести JSON наборов слоёв~~ — `apps/wizard/grado_wizard/album_templates.json`:
  набор задаётся явным списком codes или фильтром по стадии слоя
  (`exclude_stages`/`include_stages`); стадия (`base`/`existing`/`project`)
  добавлена в классификатор и в парсер ClassifierClass.
- ~~Заменить `layers=[...]` в sheets.py на layerset~~ — location/ortho/
  base_plan/apo зовут `layerset_codes(project, name)`.
- ~~Таблица источников на листе существующего положения~~ — `_source_table`
  (слой → объектов → стадия) на опорном плане; полная фиксация снимков —
  шаг 6.
- Полный перевод листов в декларативный JSON (frames в JSON) — не сделан:
  листы остаются Python-генераторами, что ТЗ допускает («оставить как
  генераторы из шаблонов»); наборы слоёв уже декларативны.

Критерий выполнен: лист «Существующее положение» собирается из исходных
слоёв (exclude_stages=["project"]) без застройки/красных линий/соцобъектов
— проверено e2e (тест + рендер листа: только зоны, ограничения, граница
и таблица источников).

### Шаг 6. Source pipeline — готово (v0.15.0)

- ~~Связать коннекторы со снимками~~ — импорт НСПД/ФГИС ТП фиксирует
  неизменяемый датированный снимок через `SnapshotStore` (sha256,
  идемпотентно), стор `apps/studio/.sources` (gitignored).
- ~~Провенанс у объектов~~ — каждый импортированный объект несёт
  `prov` (source/date/doc/snapshot); `build_project` пишет его в модель
  (колонки source/source_date/source_doc), `grado_to_features` читает
  обратно; вручную нарисованное остаётся `source=manual`.
- ~~Сравнение при изменении~~ — переимпорт сравнивается с прошлым снимком
  (`diff` по grado_key), в UI тост «источник изменился: +N −M ~K».
- ~~Журнал источников в UI~~ — панель «Источники» (снимок: источник, дата,
  объектов, sha8), кнопка ⟳ подтягивает журнал сервера (`/api/sources`),
  провенанс виден в свойствах объекта.
- Включать/выключать исходные слои — уже работало (панель «Слои»).

Критерий выполнен: исходные слои включаются/выключаются, снимок
фиксирует выпуск (sha256, provenance в .grado), переимпорт сравнивается
с прошлым (diff+тост). Проверено e2e в браузере + 6 тестов.

**Остаётся вне 6 шагов (MODEL-01/02):** выделенный слой
`source.fgistp.func_zones` (сейчас ФГИС ТП идёт в tp.func_zone стадии
existing с провенансом — семантически исходные данные, но отдельного
source-слоя нет из-за 1:1 связки kind→слой); полное снятие `kind` как
транспорта требует per-object `layer_id`/`style_id` в модели .grado.

## 8. Минимальный набор задач в трекере

1. ~~`MODEL-01`: schema v2 для `Layer`, `Feature`, `Style`~~ — готово
   (v0.16.0): grado_layers v2 (layer_id != semantic_class, stage/style_id/
   source_kind), колонка style_id у объекта, миграция v1→v2 в open(),
   реестр LAYER_TEMPLATES; студия маршрутизирует по layer_id, ФГИС ТП →
   выделенный source.fgistp.func_zones (проверено: два слоя одного класса
   в .grado + round-trip). Остаток: рендер по per-object style_id (нужен
   StyleSet по style_id) и полное снятие kind из KIND_ATTRS/_geom_for.
2. ~~`MODEL-02`: мигратор legacy `kind` -> `layer_id`~~ — частично: объекты
   без layer_id роутятся по kind (_KIND_TO_LAYER), новые пишут layer_id;
   отдельный мигратор старых .grado-журналов не нужен (legacy layer_id=code).
3. ~~`UI-01`: CAD-примитивы~~ — готово (шаг 2, v0.12.0).
4. ~~`UI-02`: активный слой + шаблоны~~ — готово (шаг 2).
5. `UI-03`: переписать панель свойств на геометрия/слой/стиль/атрибуты.
6. ~~`RENDER-01`: стили в JSON + resolver~~ — готово (шаг 3, v0.13.0).
7. ~~`COMPUTE-01`: ТЭП на layer roles~~ — готово (шаг 4, v0.13.1).
8. ~~`LAYOUT-01`: `LayerSet`~~ — готово (шаг 5, v0.14.0).
9. `LAYOUT-02`: перевести листы на JSON-шаблоны (частично: наборы слоёв
   декларативны, сами фреймы — Python-генераторы).
10. ~~`DATA-01`: импорт в source layers~~ — готово (шаг 6 + MODEL-01b).
11. `DATA-02`: журнал источников (готов, шаг 6) + провенанс на листах
    (частично: таблица источников на опорном плане).
12. ~~`EXPORT-01`: DXF-слои из style config~~ — готово (шаг 3).

## 9. Критерии готовности

- Пользователь чертит не "здание", а полигон на активном слое
  "Проектируемая застройка".
- Один и тот же полигон можно перенести на другой слой без пересоздания.
- Стиль слоя редактируется отдельно от геометрии.
- Альбом собирается из последовательных наборов слоев: источники ->
  существующее положение -> проект -> расчеты.
- Импорт из НСПД/ГИСОГД создает исходные слои с провенансом, а не
  перемешивается с проектными объектами.
- ТЭП и легенды обновляются по ролям слоев, а не по hardcoded `kind`.
- Старые `.grado` и localStorage-сцены открываются через мигратор.
