<!-- генерируется tools/wiki.py — не править руками -->

# Модули ГРАДО 2

Файл — строк — назначение (первый комментарий файла) — функции и классы верхнего уровня.

## Сервер и печать (apps/grado2/*.py)

### `apps/grado2/album_io.py` — 757 стр.

Альбомы по образцам владельца (26.09.2026): «План реализации ППТ КРТ» — по его шаблону PowerPoint («ППТ_КРТ Шаблон (И).pptx», А3 альбомный, красная шапка) и «Градостроительная концепция» — по образцу «ГК Царицыно» (А3 альбомный, белый лист, заголовок справа).

Функции: `photo_bytes`, `_header`, `_glue`, `_wrap`, `_text`, `_tw`, `_hyph_parts`, `_wrap_para`, `_wrap_mm`, `_title_lines`, `_col_widths`, `_not_ready`, `_tab`, `PptKrtFrame`, `_text_boxes`, `_callout_route`, `_remember_ops`, `CalloutFrame`, `MapNoteFrame`, `ortho_legend_h`, `_rgb`, `_dash_fit`, `concept_swatch`, `ConceptColumnFrame`, `OrthoLegendFrame`, `ConceptPhotoFrame`, `OkrugTitleFrame`, `build_pptkrt`

### `apps/grado2/dxf_io.py` — 311 стр.

DXF export/import for ГРАДО 2 on ezdxf (MIT), with the Moscow red-line linetypes REDLN97.

Функции: `acad_name`, `_pattern_string`, `_add_linetype`, `_rings`, `export_dxf`, `fit_view`, `oda_converter`, `oda_convert`, `_rgb`, `_code_of`, `linecode_of`, `written_system`, `import_dxf`

### `apps/grado2/export_io.py` — 274 стр.

Экспорт ГРАДО 2 в обменные форматы: GeoJSON для QGIS (МСК) и таблица ТЭП с перечнем листов в XLSX.

Функции: `_num`, `_text`, `_walk_coords`, `_to_msk`, `_parts`, `_file_name`, `export_geojson`, `_col`, `_Sheet`, `_cell`, `export_xlsx`

### `apps/grado2/file_io.py` — 325 стр.

Import of vector files for ГРАДО 2: GeoJSON, KML/KMZ, Shapefile (a set of files or a zip), DXF.

Функции: `_walk`, `_pts`, `_explode`, `system_of`, `to_wgs84`, `_clean`, `read_geojson`, `_kml_coords`, `_kml_geoms`, `read_kml`, `_prj_hint`, `read_shp_set`, `check_size`, `_check_unpacked`, `import_files`

### `apps/grado2/hub.py` — 1853 стр.

Хаб совместной работы ГРАДО 2 (режим GRADO2_HUB=1): аккаунты, проекты с ролями, ревизии разделов, живые события (presence, комментарии), история версий.

Функции: `_now`, `HubError`, `Conflict`, `_norm_album`, `_layer_key_ok`, `_norm_meta`, `album_summary`, `split_project`, `join_sections`, `_check_sections`, `_clean_name`, `_clean_login`, `_check_password`, `_clean_client`, `_check_pid`, `_is_num`, `_clean_text`, `_clean_anchor`, `_hash_password`, `_color`, `Subscription`, `Hub`, `default_root`, `_read_password`, `main`

### `apps/grado2/ogd_all.py` — 879 стр.

«Всё из ГИС ОГД в DWG»: все слои портала ИСОГД по области — одним чертежом, слой портала = слой чертежа.

Функции: `_load_failed`, `_save_failed`, `catalog_tree`, `layer_list`, `_linetypes`, `_lgr_code`, `_polys`, `_inside`, `orient_lines`, `_cut_bytes`, `_xdata`, `sheet_box`, `sheet_bbox_wgs`, `portal_color`, `_decls`, `_hex`, `_num`, `etalon_code`, `lgr_entry`, `dxf_hatch`, `etalon_style`, `layer_style`, `portal_style`, `label_siblings`, `label_angles`, `set_label_angles`, `_zone_hatch`, `_label`, `build_drawing`, `portal_styles`, `_save_json`, `scan`, `Job`

### `apps/grado2/ogd_warm.py` — 85 стр.

Прогрев кэша ГИС ОГД на сервере: все слои каталога лежат на диске свежими, выгрузка по листу берёт их оттуда.

Функции: `busy`, `main`

### `apps/grado2/print_io.py` — 2473 стр.

Листы и альбом ГРАДО 2: PDF, SVG и PPTX через рендер и вёрстку ядра (core/render, core/layout).

Функции: `page_size`, `PaperFrame`, `slide_k`, `layout`, `_mix`, `_nice`, `MapTransform`, `_simplify`, `ops_cache_get`, `ops_cache_put`, `egko_ops`, `_egko_ops`, `_guillemets`, `_text_w`, `_straight_runs`, `flood_ops`, `_seg_box`, `_in_ring`, `_chains`, `_axis_windows`, `_obox_hit`, `_seg_cross`, `_pole`, `_ring_centroid`, `clip_ring`, `_parts`, `linetype_ops`, `TileGuard`, `tile_ops`, `SketchMapFrame`, `ColumnFrame`, `TepSheetFrame`, `_wrap`, `_view_mark`, `_swatch`, `SlideFrame`, `photo_map_rect`, `panel_rects`, `PanelFrame`, `PhotoGridFrame`, `build_document`, `apply_edits`, `own_texts`, `_num`, `_edited`, `_pages`, `render_pdf`, `not_ready`, `_op_box`, `_meet_box`, `_quad_info`, `_inside`, `_tile_patch`, `pptx_clip_tiles`, `pptx_thin`, `pptx_weight`, `_dash_runs`, `pptx_rasterize`, `pptx_notes`, `render_pptx`, `render_preview_svg`

### `apps/grado2/rail_icons.py` — 123 стр.

Значки станций рельсового каркаса для листов альбома (правило 16 label-rules.md, владелец 05.10.2026).

Функции: `flatten`, `icon_id`, `icon_width`, `icon_ops`

### `apps/grado2/sat_io.py` — 258 стр.

Спутник Яндекса для AutoCAD: снимок рамки листа, пересчитанный в МСК (как в QGIS владельца).

Функции: `SatError`, `_ctx`, `YandexSat`, `frame_msk`, `bbox_msk`, `export_sat`, `_package`

### `apps/grado2/server.py` — 2616 стр.

ГРАДО 2: локальный сервер.

Функции: `bbox_km2`, `territory_bbox`, `split_bbox`, `merge_layers`, `clean_props`, `_v`, `_doc`, `_reg`, `pzz_sub_props`, `pzz_zone_props`, `okn_props`, `demolition_props`, `social_props`, `egko_address`, `egko_building_props`, `egko_road_props`, `egko_path_props`, `egko_green_props`, `egko_water_props`, `egko_address_props`, `_renamed`, `linetype_props`, `_layer`, `search_cad`, `search_addr`, `krt_number`, `krt_layer`, `krt_card`, `search_krt`, `search_any`, `body_limit`, `source_ogd_code`, `plain_portal_error`, `not_ready_why`, `not_ready_headers`, `_log_portal`, `ogd_catalog`, `layer_roles`, `egko_features`, `esri_tile`, `yandex_sat_tile`, `_point_in`, `ogd_label_angles`, `_OsmCacheMiss`, `_osm_no_live`, `osm_fetch`, `fetch`, `fgistp_catalog`, `fgistp_docs`, `fgistp_search`, `fgistp_fetch`, `_bbox_of`, `tep`, `tep_norms`, `_norm_name`, `_in_ring`, `_rail_nodes`, `rail_route`, `_fresh`, `_admin_districts`, `place_polygons`, `district_shares`, `place_info`, `project_path`, `atomic_write`, `keep_version`, `QuotaExceeded`, `projects_size`, `save_project`, `album_info`, `list_projects`, `hub_enabled`, `open_hub`, `same_token`, `Handler`, `_bad`, `code_stamp`, `_probe`, `_running`, `_is_grado` и ещё 3

## Страница (apps/grado2/web/*.js)

### `apps/grado2/web/albumgeo.js` — 29 стр.

ГРАДО 2 · мелкая геометрия листов альбома без карты (T10/T11, 06.10.2026): кэш по объекту и углы рамки листа в МСК. Чистые функции; tests/test_albumgeo_js.py.


### `apps/grado2/web/albummeta.js` — 55 стр.

ГРАДО 2 · шапка альбома: «№ КРТ», «Округ, район», «Адрес» заполняются сами из слоёв (T73, 05.10.2026). Чистые функции без обращения к карте: слои и проверка «внутри территории» передаёт sheets.js. Запуск проверок — tests/test_albummeta_js.py. Правило: введённое владельцем не затирается; сам заполненный текст помечен в meta.auto[поле] и обновляется при пересборке.


### `apps/grado2/web/albums.js` — 1173 стр.

ГРАДО 2 · альбомы по образцам владельца (26.09.2026): «План реализации ППТ КРТ» — по его шаблону PowerPoint (А3 альбомный, красная шапка; оформление листа — album_io.py) и «Градостроительная концепция» — по образцу «ГК Царицыно». Листы собираются той же сборкой, что раздел 1 (buildSection в sheets.js), со своим префиксом id. Состав листов — по «ГК Царицыно» (решение владельца 27.09.2026), оформление — шаблон ППТ КРТ.

Функции: `homeAdm`, `okrAbbr`, `okrugMainCalc`, `okrugMain`, `keepParts`, `simplifyAdm`, `admPanelSpec`, `albumExtra`, `MM`, `C_ROADS`, `C_STREETS`, `cSheet`, `W_`, `VRI_CLS`, `inNewMoscow`, `landUseOf`, `osmUseOf`, `SZZ_ORD`, `zoneGen`, `cornerReserve`, `zouitCode`, `bigRing`, `conceptDocs`, `docTitle`, `docLine`, `sharedRoads`, `dataFts`, `waterLabels`, `railStations`, `conceptStations`, `titleRu`, `namedPlaces`, `roadSource`, `conceptSheet`, `conceptRail`, `conceptDistricts`, `conceptWhy`, `buildAlbum`

### `apps/grado2/web/analysis.js` — 157 стр.

ГРАДО 2 · узлы анализа графа (этап Э3): радиусы обслуживания, пешая доступность по улицам, показатели по кварталам, баланс территории. Каждый узел объясняет результат словами: у объектов его выхода есть поле «Пояснение», оно подписывается на карте, пока узел выбран. «В слой» в окне графа делает выход обычным слоем проекта (Bake).

Функции: `CAO`, `socialPoints`, `ha2`, `NRadius`, `walkGraph`, `dijkstra`, `NWalk`, `NBlocks`, `NBalance`, `bakeNode`

### `apps/grado2/web/app.js` — 2376 стр.

ГРАДО 2: одно рабочее поле — карта со слоями, строка инструментов и плавающие окна (данные, граф, эскиз, варианты, показатели, объём, сравнение, таблица). Порядок работы свободный. Данные — реальные выгрузки сервера (/api/fetch), ТЭП — движок ядра (/api/tep). Геометрия в WGS84 (Turf.js); для посадки и объёма — локальная метрическая рамка вокруг территории.

Функции: `fmt`, `esc`, `icons`, `api`, `setFrame`, `toLL`, `polyLL`, `rect`, `bboxOf`, `centroid`, `polys`, `ringsXY`, `splitParts`, `planarArea`, `m2`, `safe`, `quiet`, `snap6`, `robust`, `unionAll`, `diff`, `inter`, `buf`, `asArea`, `rot`, `toOl`, `calmWheel`, `interactions`, `basemap`, `setBasemap`, `ruScaleLine`, `newMap`, `hatch`, `S`, `loadStyleLibs`, `ltCode`, `redLineStyle`, `dataBBox`, `terrLayer`, `setTerritory`, `coverSheets`, `coverBox`, `updateCover`, `pickBoundary`, `importBoundary`, `parcelsWord`, `haOf`, `srchErr`, `searchApi`, `cadOf`, `parcelKey`, `addParcels`, `parcelsToTerritory`, `boundaryByNumbers`, `histText`, `renderSources`, `fgHTML`, `fgRender`, `fgFind`, `fgSearch`, `fgPick`, `fgLoad`, `sameLayerKey`, `dlStatus`, `loadKeys`, `mergeDownload`, `EXIST_KEY`, `floorsOf`, `insideTerr`, `existingSummary`, `kv`, `b64`, `importFiles`, `exportLayers`, `saveBlob`, `exportTo`, `expItems`, `expSync`, `expMenu`, `ogdSheet` и ещё 135

### `apps/grado2/web/blocks.js` — 63 стр.

ГРАДО 2 · урбан-блоки: дозированное понижение этажности секций, чьи фасады не получают нормы инсоляции (задача T56). Критерий тот же, что в «Проверке норм» (constraints.js, checkNorms): у секции без северных фасадов норму СанПиН 1.2.3685-21 (см. insol.js) должна получать не меньше половины точек фасада (шаг 6 м, шаг солнца 10 мин, окно на z над землёй). Метод: пока есть секции ниже 50 %, для каждой подбирается соседняя секция (чаще всего южное крыло своего квартала или торец соседнего), понижение которой на этаж даёт больше всего света на потерянный м² этажей; если ничто не помогает, секция сн…


### `apps/grado2/web/cad.js` — 1593 стр.

ГРАДО 2 · черчение как в AutoCAD. Команды вызываются кнопкой на ленте или набором псевдонима (L, PL, C, A, REC, POL, PO, M, CO, RO, SC, MI, O, TR, EX, F, BR, J, X, E, DI, AA, BO) и Enter или пробелом в любой раскладке; Enter или пробел без команды повторяют последнюю. У курсора — поле динамического ввода: длина, длина<угол, @dx;dy, X;Y (МСК), буквы параметров команды ([З]амкнуть, [Р]адиус…). Режимы строки состояния, как у AutoCAD: ПРИВЯЗКА (F3, набор привязок), ОТСЛЕЖ (F11: наведите курсор на точку привязки, пока не появится «+», — дальше пунктирные линии выравнивания и продолжения), ПОЛЯР (F1…

Функции: `toM`, `saveST`, `fLine`, `fPoly`, `fPt`, `vertices`, `syncGrips`, `gripAt`, `chainsOf`, `inSweep`, `gather`, `acquireTick`, `acquire`, `parTick`, `trackLines`, `resolve`, `refresh`, `f2`, `tip`, `toEn`, `normNum`, `openInput`, `closeInput`, `autoc`, `typedNum`, `bad`, `submit`, `matchOpt`, `parsePoint`, `title`, `start`, `cancel`, `finish`, `MODK`, `plural`, `result`, `drawSummary`, `editSummary`, `downloadWarn`, `note`, `hist`, `showHist`, `toggleHist`, `showCmd`, `after`, `enter`, `syncButtons`, `toggle`, `targetFor`, `newFeature`, `copyFeat`, `addNew`, `edit`, `worldChains`, `xformGeom`, `xformCad`, `affineOf`, `ghosts`, `opt`, `optStr`, `selection`, `pickChain`, `replaced`, `piecesEdit`, `boundaries`, `CURKEY`, `annoLayer`, `def`, `closeOpt`, `contourAt`, `regionAt`, `regionIn`, `zoomAll`, `chainCmd`, `distFin`, `areaFin`, `terrFin`, `transformCmd`, `trimInfo`, `arrayGroup` и ещё 20

### `apps/grado2/web/cadcore.js` — 255 стр.

ГРАДО 2 · геометрия черчения в метрах МСК (X на восток, Y на север). Без DOM и OpenLayers — проверяется под node (tests/cadcore_test.js). Цепочка — массив точек [x, y]; у замкнутой первая точка повторена в конце. Здесь всё, что считают команды AutoCAD: пересечения, перпендикуляр, касательные, дуги по трём точкам, правильные многоугольники, подобие (offset), обрезка, удлинение, разрыв, сопряжение, соединение.


### `apps/grado2/web/collab.js` — 753 стр.

ГРАДО 2 · совместная работа: движок синхронизации (контракт — docs/grado2-collab-spec.md). Сервер хранит проект целиком, разбитым на разделы, и нумерует правки; клиенты сводят правки сами: · разделы: «meta» (граница, группы, виды, граф, источники, порядок слоёв), «album» (альбом: meta и листы — отдельно, чтобы правка meta не пересылала альбом) и «layer:<ключ>» = {spec, data}; · после каждой правки (markDirty → Collab.touched) с паузой 400 мс (не дольше 3 с) меняются только изменившиеся разделы; · сервер отвечает 409, если раздел успел поменять кто-то ещё: правки сводятся по трём версиям (база,…

Функции: `stable`, `same`, `isObj`, `js`, `quick`, `R9`, `cg`, `canonGeom`, `canonF`, `sameF`, `h12`, `keepUid`, `ensureUids`, `uidMap`, `split`, `join`, `mergeObj`, `mergeFeature`, `decide`, `mergeFC`, `mergeLayer`, `mergeOrder`, `layoutDerived`, `layoutConsistent`, `three`, `mergeKeyed`, `mergeGroup`, `mergeSheet`, `mergeAlbum`, `mergeMeta`, `eqLayer`, `merge3`, `install`, `emit`, `setStatus`, `editable`, `http`, `P`, `isLayerName`, `secText`, `baseMeta`, `baseAlbum`, `sameSection`, `baseName`, `normSection`, `localState`, `enqueue`, `queuePush`, `queueCatchUp`, `schedulePush`, `netFail`, `pushOnce`, `pushLoop`, `markSaved`, `recover`, `catchUp`, `fullSync`, `lost`, `authExpired`, `integrate`, `typing`, `diffApply`, `createLayerFrom`, `applyLayer`, `applyTerritory`, `applyGraph`, `applyMeta`, `applyAlbum`, `applyResults`, `VKEY`, `savePersonal`, `personal`, `loadProject`, `updateRole`, `refreshRole`, `connect`, `probeStream`, `onEvent`, `close`, `sendPresence`

### `apps/grado2/web/constraints.js` — 361 стр.

ГРАДО 2 · ограничения для генерации (этап Э4 плана). Окно «Ограничения» строит из загруженных данных обычные слои группы «Ограничения»: ЗОУИТ и охранные зоны, отступ от красных линий, противопожарные разрывы до сохраняемых зданий, подзоны ПЗЗ без нового строительства, инсоляционный фронт существующих окон и солнечный потолок участка. Слои видны, стилизуются и выключаются как любые другие; узел графа «Ограничения» читает только ВКЛЮЧЁННЫЕ слои группы — выключил слой в дереве, и посадка его больше не учитывает (что видно на карте, то и учитывает генерация). Инсоляция — предпроектная оценка по ме…

Функции: `fireGap`, `isResidential`, `isChildren`, `groundAt`, `ringMid`, `decisionOf`, `consLayer`, `clip`, `protectR`, `polyFeats`, `cleanTitle`, `roleFeats`, `nameOf`, `usedLine`, `computeConstraints`, `consExclude`, `consCeiling`, `NCons`, `ensureConsNode`, `renderCons`, `openRing`, `prismsOf`, `keptForCheck`, `sketchFromLayer`, `yieldUI`, `evalChunked`, `checkNorms`, `runCheck`, `ownInsolation`

### `apps/grado2/web/frames.js` — 188 стр.

ГРАДО 2 · листы альбома на карте — как фреймы в Figma или видовые экраны в AutoCAD. Каждый лист-карта альбома (ALBUM.sheets) — рамка на карте: её размер = карта листа (frameMM) × масштаб. Инструмент «Лист»: тяните прямоугольник — пропорции формата держатся сами (по умолчанию А3 без штампа), масштаб считается из размера; появляется новый лист альбома. Выбранный лист: тянуть внутри — сдвиг (sheet.center), за угол — размер (sheet.scale), над листом панель: название, формат, ориентация, масштаб, «Загрузить сюда», «ГИС ОГД в DXF», «Просмотр», удалить. Листы раздела (строятся по территории) видны на…


### `apps/grado2/web/gpzones.js` — 34 стр.

Генплан (лист 6 альбома): название и индекс типа функциональной зоны, цвет по таблице MapInfo ТиНАО (правило 13). Старая Москва (gisogd.func_zones, virtual1742) несёт naimfunkzony + fztip; ТиНАО (gisogd.func_zones_tinao) — «Вид зоны» + fz_type. Цвет — по индексу из любого слоя, сплошной; нет индекса — по названию, иначе fallback (палитра Эталона). Тесты — tests/test_gpzones_js.py.


### `apps/grado2/web/hub.js` — 842 стр.

ГРАДО 2 · совместная работа: интерфейс (вход, проекты, доступ, комментарии, история, присутствие на карте). Работает только в совместном режиме (window.HUB_MODE ставит project.js после /api/health); в обычном ничего не показывает. Движок — web/collab.js (window.Collab); здесь только окна, шапка и наложения на карту.

Функции: `C`, `lsGet`, `lsSet`, `myRole`, `canEdit`, `isOwner`, `q`, `plural`, `two`, `toMs`, `when`, `size`, `uname`, `initials`, `safeColor`, `ink`, `rgba`, `list`, `lyTitle`, `setText`, `hub`, `fail`, `typing`, `draw`, `armedIs`, `twoStep`, `setLmode`, `lock`, `showLogin`, `askLogin`, `submitLogin`, `guestLogin`, `sessionLost`, `enter`, `startPage`, `grabJoin`, `getJoin`, `clearJoin`, `doJoin`, `boot`, `openProject`, `closedProject`, `loadProjects`, `loadTeams`, `myTeam`, `teamOpts`, `fillNewTeam`, `refreshMeta`, `setSync`, `renderBar`, `renderAv`, `applyRole`, `menu`, `norm`, `teamName`, `projGroups`, `createProject`, `copyProject`, `el_copyName`, `wireProjects`, `linkUrl`, `linkBlock`, `loadLink`, `setLink`, `wireShare`, `wireTeams`, `uidIndex`, `findByUid`, `geomPoint`, `anchorPoint`, `anchorText`, `sortedComments`, `loadComments`, `cpath`, `flyTo`, `selectComment`, `startDraft`, `endDraft`, `setCMode`, `wireComments` и ещё 16

### `apps/grado2/web/insol.js` — 189 стр.

ГРАДО 2 · инсоляция: положение солнца, инсоляционный фронт существующих окон, солнечный потолок участка. Предпроектная оценка по методам ГОСТ Р 57795-2017 и нормам СанПиН 1.2.3685-21 (табл. 5.58, центральная зона): расчётные даты 22 апреля и 22 августа, время солнечное, первый час после восхода и последний перед заходом не учитываются (на 55–56° с. ш. — как на инсографике МАрхИ: 6:00–18:00); норма — 2 ч непрерывно или 2,5 ч прерывисто при одном периоде не короче 1 ч. Это НЕ сертифицированный расчёт для экспертизы. Упрощения: рельеф плоский, высота этажа задаётся одна, теневые углы окон — одним…


### `apps/grado2/web/labelfmt.js` — 83 стр.

Оформление подписей альбома (albums.js): железнодорожные станции и кавычки. Чистые функции, без карты. Правило 15 (владелец 05.10.2026): станция подписывается «ст. ж/д Калошино», сокращение не отрывается от названия (неразрывные пробелы). Станция — по признакам данных, а не по названию: землепользование OSM «railway» с названием, тег railway = station / halt / yard и т. п., типы Яндекса «транспорт: станция». Депо, заводы и прочее на железной дороге, и названия без признаков станции не переименовываются. Запуск проверок — tests/test_labelfmt_js.py.


### `apps/grado2/web/layers.js` — 1514 стр.

ГРАДО 2 · слои проекта как в QGIS: дерево с порядком прорисовки (перетаскивание), видимость, оформление (единое / категории / диапазоны / правила / знаки ЛГР), подписи, таблица атрибутов. Строка инструментов как в AutoCAD: рисование в текущий слой, вершины, перенос, удаление, замеры; правка выгрузок с возвратом к исходной. Данные слоя живут в DATA[key].fc (WGS84) — их же читает граф анализа.

Функции: `ramp`, `okn`, `cleanStyle`, `ST`, `stDefaults`, `tidyLayers`, `defaultStyle`, `lyr`, `grp`, `shown`, `isBig`, `geomOf`, `hiddenField`, `fieldsOfKey`, `ensureLayer`, `kindOf`, `glSwitchRes`, `denToRes`, `outOfScale`, `olLayersFor`, `attachLayer`, `rebuildLayer`, `mainOl`, `applyOrder`, `normGroups`, `newUid`, `writeFC`, `bindFC`, `setLayerData`, `syncFromSource`, `isNum`, `numOf`, `catValues`, `numFields`, `assignCats`, `breaks`, `testRule`, `symbolOf`, `rgba`, `css`, `upright`, `labelDeg`, `floorsDenOf`, `labelStyle`, `symAll`, `glStyle`, `frameless`, `ruleCount`, `styleFor`, `portalStyles`, `portalStylesOnce`, `labelAngles`, `restyle`, `symHTML`, `legendItems`, `rowHTML`, `sheetKeys`, `sheetView`, `sheetEditable`, `mapSheets`, `sheetTreeHTML`, `showSheet`, `sheetSet`, `sheetMenu`, `setBySheet`, `normQ`, `renderTree0`, `tree`, `rowId`, `rowById`, `focusRow`, `renderTree`, `decorateTree`, `dropRow`, `makeRegister`, `setDecision`, `newGroup`, `groupMenu`, `renameGroup`, `closeMenu` и ещё 81

### `apps/grado2/web/layout.js` — 203 стр.

ГРАДО 2 · редактор макета листа (как «Макет» в QGIS): готовый лист во весь экран, любая надпись листа — заголовок, шапка, подписи карты, легенда — выбирается щелчком и правится: текст, шрифт, кегль, цвет, обводка, поворот, место (тянуть мышью или стрелками). «Текст» добавляет свою надпись. Правки хранятся в листе (edits — по ключу «текст#n», items — свои надписи) и попадают в PDF и PPTX: лист собирает тот же рендер ядра (print_io.apply_edits). Правка — ручная поправка поверх автоматических подписей листа: правила подписей сами по себе не меняются. Вёрстка как в InDesign (из DesignCraft, 06.10.…

Функции: `layoutEl`, `setAdding`, `sheetOf`, `laySnap`, `remember`, `layHist`, `isItem`, `itemOf`, `editOf`, `layHint`, `openLayout`, `closeLayout`, `renderLayout`, `layZoom`, `selEl`, `markSel`, `boxOf`, `drawGuides`, `svgPt`, `layDown`, `moveSel`, `hideSel`, `curOf`, `layPanel`

### `apps/grado2/web/legendrules.js` — 53 стр.

Легенда листов 5–9 — только из нарисованного (правило 7, T85a) и общие препятствия подписей рек (правило 0, T85b). Чистые функции, без карты: albums.js даёт им «что есть в рамке», они отвечают «что писать». Проверки — tests/test_legendrules_js.py. Слово владельца 06.10.2026: «всё должно быть не по предустановленному скрипту, а максимально гибко, но при этом под цели сбора».


### `apps/grado2/web/linetype.js` — 61 стр.

Draws AutoCAD complex linetypes (LIN + SHX) on a canvas. Data: styles/redln97.json, generated from REDLN97.LIN + RED_LNS.SHX by tools/gen_redln97.py. Pattern units are drawing units (metres); k = pixels per metre.


### `apps/grado2/web/login.js` — 16 стр.

Вход по ключу доступа (включается переменной GRADO2_TOKEN на сервере). Ключ уходит только в теле POST, не в адрес.


### `apps/grado2/web/migrate.js` — 39 стр.

ГРАДО 2 · переименование «потолок» → «предельная высота» в проектах (решение владельца 01.10.2026). Идемпотентно и без смены номера формата: идёт при каждой загрузке проекта (project.js → migrate, в том числе из совместной работы: collab.js → join → applyProject). Трогает только служебный слой «cons:ceiling» (поля, стиль) и гнёзда узлов графа «Данные/Ограничения» и «Эскиз/Посадка застройки»; одноимённые поля в слоях пользователя остаются как есть. Проверяется под node (tests/migrate_test.js).


### `apps/grado2/web/msk.js` — 49 стр.

ГРАДО 2 · рабочая местная система Москвы МСК (как пользовательская СК «МСК» в QGIS владельца) в браузере. Перенос core/connectors/grado_connectors/crs.py (msk_to_wgs84 / wgs84_to_msk) один в один: обратный поперечный Меркатор на эллипсоиде Бесселя без сдвига начала (+x_0=0 +y_0=0), 7-параметрический Хельмерт (Position Vector), WGS84. X — на восток, Y — на север, метры: так же, как в DXF и на листах. Система ГИС ОГД — та же формула со сдвигом начала (16,098; 14,512) м, в браузере она не нужна. Сверено с PROJ в tests/test_msk.py (меньше 1 мм).


### `apps/grado2/web/norms.js` — 165 стр.

Нормативы расчёта ТЭП: окно с полями норм, предзаполненными действующими значениями пресета (GET /api/tep/norms). Правки хранятся только как разница {id: число} в параметрах узла ТЭП (tepParams(node).constants): они сохраняются вместе с графом проекта и ходят в совместной работе без смены формата. tepRequest шлёт их как constants.


### `apps/grado2/web/ogdpick.js` — 131 стр.

ГРАДО 2 · окно «Исходные данные»: одно дерево всех источников — ЕГРН, подборки ГИС ОГД, все слои ГИС ОГД ровно в порядке портала, ЕГКО, OpenStreetMap, Яндекс, рельеф. Флажки на папках и слоях, поиск, число объектов каждого слоя ГИС ОГД в области (по кэшу на диске, портал не трогается). Отмеченное — выбор проекта (CHECKED; слои портала — ключами «ogd.<код>»). Две кнопки: «Загрузить в проект» — по листу или по покрытию всех листов, «ГИС ОГД в DXF» — чертёж отмеченных слоёв портала по листу (runOgd в app.js).


### `apps/grado2/web/project.js` — 286 стр.

ГРАДО 2 · проект: сохранение в «Документы/ГРАДО 2» (файл .grado2 = JSON), открытие, новый проект, автосохранение с восстановлением после перезагрузки страницы. В файле: граница, слои (порядок, стиль, видимость), их данные с исходной выгрузкой, граф, вид карты.

Функции: `migrate`, `markDirty`, `syncProjTitle`, `collectProject`, `jsonOf`, `projectJSON`, `clearProject`, `safeObj`, `safeId`, `applyProject`, `hubSave`, `saveProject`, `openProject`, `newProject`, `confirmLoss`, `autosave`, `fmtDate`, `fmtSize`, `albumLine`, `renderProjects`, `openProjects`

### `apps/grado2/web/railstations.js` — 66 стр.

Станции рельсового каркаса на листах альбома (albums.js): метро, МЦК и МЦД — значок и название (правило 16 label-rules.md, владелец 05.10.2026 и 06.10.2026). Чистые функции, без карты; проверки — tests/test_railstations_js.py. Источник — точки Яндекс Карт transport_p (слой yandex.stations), по одной на каждую линию станции: ft_type_name = transport-metro-station, closed ≠ 1 (закрытая станция не рисуется); network = moscow_metro, line = moscow_metro-14 (или p_name «Московское центральное кольцо») — МЦК; network = moscow_metro, прочие line = moscow_metro-N — метро (N — номер линии, в том числе Б…


### `apps/grado2/web/roadclean.js` — 81 стр.

Картографическая чистка полигонов дорог листа альбома (albums.js, roadSource). Владелец 06.10.2026 (T84): «сделай на всех векторных схемах дороги ЕГКО, чтобы остались только полигональные, сделай красиво по лучшим правилам оформления градостроительных схем». Куски проезжей части (особенно ЕГКО) лежат внахлёст и с волосяными щелями — на листе видны швы. Порядок: рамка с запасом 5 % → слияние в одну фигуру (сначала по плиткам: работа ограничена) → закрытие щелей (буфер +0.4 м, затем −0.4 м) → без обрывков < 10 м² и дыр-«островов» < 25 м² → упрощение ~0.3 м. Решение (фильтры, плитки) — чистые фун…


### `apps/grado2/web/roadsrc.js` — 19 стр.

Источник дорог листа альбома (albums.js): решение «полигоны какого источника». Чистая функция, без карты. Решение 06.10.2026 (T84, владелец: «сделай на всех векторных схемах дороги ЕГКО, чтобы остались только полигональные»): — векторные схемы (основа не снимок: листы 4–8): сначала полигоны ЕГКО (egko.roads); полигоны Яндекса — только там, где у ЕГКО в рамке ничего пригодного: площадь ЕГКО меньше 20 % площади Яндекса либо её нет; — снимок (листы 3, 9): сначала полигоны Яндекса (решение 05.10.2026), ЕГКО — запасной источник; — дороги по осям (calc.uds_ya, calc.uds_osm) не рисуются ни на одном л…


### `apps/grado2/web/roles.js` — 63 стр.

ГРАДО 2 · роли слоёв в расчётах. Ограничения, анализ и эскиз ищут данные по РОЛИ слоя, а не по фиксированному ключу: в проектах владельца каталожные слои лежат как `ogd.<код>` и `egko.*`, а не `gisogd.*`/`nspd.*`/`osm.*`. Роль слоя определяется так (по убыванию силы): а) вручную: поле `role` в описании слоя (роль из списка или "none" — слой не участвует в расчётах); нет поля = «авто»; б) по ключу источника (таблица SOURCE_ROLE: `nspd.zouit` → zouit, `egko.buildings` → buildings…); в) по коду каталога для `ogd.<код>` — таблица с сервера (GET /api/layer_roles, строится из SOURCES), грузится лени…


### `apps/grado2/web/sheetlayers.js` — 538 стр.

ГРАДО 2 · окно «Слои и листы» (T86b, 06.10.2026; слово владельца: «единая логика для всех листов, группировка слоёв по листам и перетаскивание, всё красиво и интуитивно понятно», макет — docs/team/mockups/2026-10-06-sheet-layers.png, вариант А). Три колонки: листы альбома → роли выбранного листа (глаз, источник, покрытие рамки, состояние) → слои проекта по ролям с номерами листов. Перетаскивание (T86c, 06.10.2026): слой банка → лист или строка роли (включить), роль → другой лист (перенос, Alt — копия), источники дорог — за ручку ⋮⋮ и Alt+↑/↓; цель подсвечивается и пишет, что произойдёт; Esc от…


### `apps/grado2/web/sheetlayout.js` — 478 стр.

ГРАДО 2 · состав слоёв листа по ролям: sheet.layout (T86a, 06.10.2026, слово владельца: «единая логика для всех листов, группировка слоёв по листам и перетаскивание»). Чистые функции без карты: слои проекта и шаблон передаёт sheets.js / albums.js. layout = { groups: [{ id, title, role, items: [{ key, on, style?, only?, src? }] }] }. Порядок групп и элементов — порядок рисования (как у sheet.keys). style — оформление слоя на этом листе поверх стиля слоя проекта; only — отбор объектов { field, values }; src — очередь источников (только у дорог: кто первый, кто запасной). Переходный релиз: keys, …


### `apps/grado2/web/sheets.js` — 1110 стр.

ГРАДО 2 · листы и альбом (этап Э6). Лист = вид карты (или текущая карта) в рамке А3/А1 с масштабом, легендой вида, таблицей ТЭП, стрелкой севера, масштабной линейкой и основной надписью по ГОСТ Р 21.101. Оформление объектов считает тот же код, что рисует слои на экране (symbolOf), поэтому лист не расходится с картой; в PDF его собирает рендер ядра (print_io.py): МСК, типы линий REDLN97, штриховки. Состав альбома хранится в проекте.

Функции: `isPaper`, `paperMM`, `isSlide`, `frameMM`, `newSheet`, `autoScale`, `viewLayers`, `sheetCenter`, `sheetScale`, `tepRows`, `sheetSpec`, `albumSpec`, `monthYear`, `metaVals`, `autoMeta`, `noAddrWhy`, `syncAddrWhy`, `codes`, `wrapLab`, `gpNum`, `gpIdx`, `gpFund`, `fitBox`, `shortRight`, `parcelsSheet`, `cut`, `genplanTable`, `dateRu`, `docsSheet`, `radiiSheet`, `udsLayer`, `buildUds`, `ensureAdmin`, `situationExtras`, `buildSituation`, `buildSituation0`, `cloneJ`, `sameJ`, `tplBase`, `makeTplSheet`, `makeSitSheet`, `carryHand`, `tplKey`, `tplSet`, `tplMake`, `whyOf`, `readFit`, `lostPhrase`, `notReadyWhy`, `tplAdopt`, `tplRefresh`, `tplSig`, `tplAfter`, `tplAuto`, `tplSchedule`, `tplManual`, `planUnits`, `buildSection`, `buildSection0`, `frameBox`, `previewSheet`, `setBuilding`, `albumFile`, `emptyInFrame`, `exportIssues`, `albumFile0`, `dlDir`, `satFile`, `stampAlbum`, `stampText`, `shWord`, `albumStatText`, `syncAlbumStat`, `isViewer`, `mb`, `isReadySheet`, `albumOfJson`, `readAlbumFile`, `askExport`, `expAnswer` и ещё 38

### `apps/grado2/web/snap.js` — 49 стр.

Привязка и умные направляющие для редактора макета листа (layout.js), как в InDesign. Перенос прохода выравнивания из DesignCraft (crates/tools/src/snap.rs: pass_align, offer_box, offer, push_alignment_guide; MIT, лицензия — vendor/LICENSE-designcraft). Владелец 06.10.2026: «используй код этой программы для нашего редактора листов — вёрстка». Надпись при перетаскивании встаёт краем к краю или серединой к середине другой надписи или листа, если до них не дальше зоны привязки (4 пикселя экрана); по каждой оси — ближайшее совпадение, и рисуется одна направляющая. Чистые функции, рамки в мм листа …


### `apps/grado2/web/uisize.js` — 3 стр.

Размер интерфейса, выбранный в «Окна» → «Размер интерфейса»: ставится до отрисовки, чтобы страница не прыгала. Отдельный файл, а не скрипт в index.html: политика страницы (CSP script-src 'self') встроенные скрипты не выполняет.


### `apps/grado2/web/views.js` — 52 стр.

ГРАДО 2 · виды карты (как «Темы карты» в QGIS): вид запоминает, какие слои видны, их оформление и прозрачность, видимость групп, подложку и, по желанию, масштаб. «Существующее положение», «Ограничения», «Эскиз» — одна карта с разными видами; легенда вида собирается из его видимых слоёв. Виды сохраняются в проекте и станут листами альбома.

Функции: `clone`, `captureView`, `applyView`, `legendHTML`, `renderViews`

## Ядро: коннекторы (core/connectors/grado_connectors)

### `core/connectors/grado_connectors/clip.py` — 147 стр.

Обрезка геометрии GeoJSON по прямоугольнику (w, s, e, n) — только стандартная библиотека.

Функции: `_inside`, `_clip_ring`, `_ring_in_box`, `_clip_polygon`, `_clip_segment`, `_clip_line`, `_bbox_of`, `clip_geometry`

### `core/connectors/grado_connectors/contract.py` — 31 стр.

Контракт коннектора (архитектура, п. «Сервис данных»).

Функции: `ConnectorError`, `Connector`, `make_result`

### `core/connectors/grado_connectors/crs.py` — 239 стр.

Трансформации СК без PROJ (для эталонной реализации).

Функции: `merc_to_wgs84`, `wgs84_to_merc`, `wgs84_to_utm37n`, `utm37n_to_wgs84`, `merc_to_utm37n`, `_meridian_arc`, `msk50_to_wgs84`, `wgs84_to_msk50`, `msk_to_wgs84`, `wgs84_to_msk`, `ogd_to_msk`, `transform_geom`

### `core/connectors/grado_connectors/diff.py` — 29 стр.

Диф снимков: что изменилось в источнике между выгрузками.

Функции: `_sig`, `diff`, `has_changes`

### `core/connectors/grado_connectors/fgistp.py` — 176 стр.

Коннектор ФГИС ТП (Минэк, mnp.economy.gov.ru) — протокол v2 (JSP).

Функции: `check_base_url`, `_ssl_context`, `FgistpConnector`

### `core/connectors/grado_connectors/geocode.py` — 174 стр.

Поиск адреса через OpenStreetMap Nominatim (решение владельца 01.10.2026).

Функции: `Busy`, `clean_query`, `_default_transport`, `Geocoder`, `parse`, `geocode`

### `core/connectors/grado_connectors/gisogd.py` — 215 стр.

Коннектор ГИС ОГД Москвы — приём ZIP-выгрузок.

Функции: `_windows_ogr2ogr_candidates`, `find_ogr2ogr`, `clean_msg`, `_safe_extract`, `_extract_recursive`, `GisogdZip`

### `core/connectors/grado_connectors/gisogd_api.py` — 866 стр.

Коннектор ГИС ОГД Москвы — прямая выгрузка слоёв по открытому REST API.

Функции: `_check_code`, `_inflate`, `_ssl_context`, `_tmp_beside`, `_nowhere`, `_expected_size`, `_http_get`, `_http_stream`, `_layer_lock`, `catalog`, `_full_names`, `_shp_features`, `_zip_of`, `_geom_bbox`, `_overlaps`, `norm_id`, `GisogdApi`

### `core/connectors/grado_connectors/importer.py` — 65 стр.

Импорт снимка в проект: снимок → слой .grado через журнал.

Функции: `_coerce`, `import_snapshot`

### `core/connectors/grado_connectors/netutil.py` — 28 стр.

Общие сетевые помощники коннекторов: потолок размера ответа и редиректы только на https.

Функции: `_HttpsOnlyRedirect`, `open_url`, `read_capped`

### `core/connectors/grado_connectors/nspd.py` — 396 стр.

Коннектор НСПД (Росреестр): захват моста + прямая выгрузка по экстенту.

Функции: `_flatten_options`, `_geom_sig`, `NspdCapture`, `_extra_ca_files`, `_ssl_context`, `_ssl_context_unverified`, `_warn_insecure`, `_short`, `NspdDirect`, `_Retryable`, `_http_get`, `normalize_cadastral`, `_search_features`, `search_cadastral`

### `core/connectors/grado_connectors/osm.py` — 434 стр.

Коннектор OSM (Overpass API) — прямая выгрузка векторов по экстенту.

Функции: `_in_ring`, `_assemble_rings`, `_which_set`, `_point_of`, `_bbox_hits`, `_OverpassCache`, `retry_wait`, `_is_timeout`, `post_with_retry`, `OsmOverpass`

### `core/connectors/grado_connectors/shp_reader.py` — 229 стр.

Чтение ESRI Shapefile (.shp + .dbf) без GDAL — фолбэк, когда нет ogr2ogr.

Функции: `_rec_bytes`, `_dbf_fields`, `_dbf_row`, `_read_dbf`, `_points`, `_ring_area`, `_shape`, `read_shp`, `iter_records`, `_encoding_of`, `iter_zip`, `_Null`

### `core/connectors/grado_connectors/store.py` — 151 стр.

Хранилище снимков — неизменяемые датированные выгрузки.

Функции: `StoreError`, `SnapshotStore`, `Subscriptions`

### `core/connectors/grado_connectors/terrain.py` — 316 стр.

Коннектор рельефа: горизонтали (изолинии высот) по видимому экстенту.

Функции: `_lon2tilex`, `_lat2tiley`, `_gpix2lonlat`, `_pick_zoom`, `_nice_interval`, `_fetch_grid`, `_http_get`, `_cell_segments`, `_stitch`, `_contours`, `TerrainContours`

### `core/connectors/grado_connectors/yandex_vmap.py` — 584 стр.

Яндекс Карты: векторные тайлы vmap3 (обратная разработка, сверено 23.09.2026) — только стандартная библиотека.

Функции: `_varint`, `_parse`, `_varints`, `_zz`, `_value`, `decode`, `lonlat_to_3395`, `lat_from_3395`, `to_lonlat`, `scale_3395`, `tile_range`, `tile_to_3395`, `_ring_area`, `_poly_area_m2`, `_line_len_m`, `_closed`, `_ll`, `_to_grid`, `_grid_to_3395`, `_sarea`, `_seam`, `_clean`, `_inside`, `_dissolve`, `_join`, `features_from_tiles`, `_ssl_context`, `YandexVmap`

## Ядро: печать (core/render/grado_render)

### `core/render/grado_render/acad_lin.py` — 320 стр.

AutoCAD complex linetypes: reading .SHX (compiled shapes) and .LIN (linetypes).

Функции: `_s8`, `read_shx`, `_read_shx`, `_draw`, `_bulge`, `read_lin`, `_complex`, `lgr_index`, `linetype_for`, `_get`, `linetypes_for_codes`, `missing_codes`, `parse_line_codes`

### `core/render/grado_render/backend_pdf.py` — 364 стр.

Печатный бэкенд: собственный PDF-писатель.

Функции: `jpeg_info`, `_jpeg_info`, `_f`, `_to_unicode_cmap`, `PdfBackend`

### `core/render/grado_render/backend_pptx.py` — 603 стр.

PPTX-бэкенд: тот же список операций, что у PDF и SVG, — в редактируемую презентацию PowerPoint.

Функции: `_hex`, `_t`, `clip_polygon`, `_segment`, `clip_polyline`, `_bbox`, `_inside_box`, `_meet`, `_area2`, `_in_ring`, `orient`, `_eot`, `_Slide`, `PptxBackend`, `_scheme`

### `core/render/grado_render/backend_svg.py` — 134 стр.

Экранный бэкенд: SVG (в C++ ядре его место занимает GPU-рендер).

Функции: `_num`, `_css`, `_pts`, `render_svg`, `_esc`

### `core/render/grado_render/scene.py` — 663 стр.

Сцена: проект → список операций отрисовки в координатах листа (мм).

Функции: `MapTransform`, `_geom_bbox`, `centroid`, `project_extent`, `_polygons`, `_lines`, `_points`, `hatch_ops`, `_point_in_rings`, `dots_ops`, `_ring_ccw`, `_marker_glyph`, `marker_ops`, `_inward_sign`, `_offset_chain`, `line_label_ops`, `_label_bbox`, `_filter_overlapping_labels`, `build_ops`

### `core/render/grado_render/style.py` — 263 стр.

Стилевая машина: стиль — данные из единой JSON-библиотеки.

Функции: `set_style_overrides`, `style_overrides`, `load_library`, `merged_library`, `hex_to_rgb`, `_dots_from_json`, `Style`, `_build_default_styles`, `StyleSet`

### `core/render/grado_render/ttf.py` — 173 стр.

Минимальный разбор TrueType для встраивания в PDF.

Функции: `FontError`, `find_font`, `Font`
