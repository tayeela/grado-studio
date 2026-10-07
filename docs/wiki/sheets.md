<!-- генерируется tools/wiki.py — не править руками -->

# Листы альбомов

Состав листов задают массивы ниже; дальнейший выбор (источник дорог, станции, районы, зоны) делает
`conceptSheet` в albums.js по данным рамки листа. Подробно о правилах — rules.md.

## План реализации ППТ КРТ, листы 3–9 (albums.js PPTKRT_C; 1 — титул, 2 — месторасположение)

| № | лист | concept / kind | основа | ключи слоёв |
|---|---|---|---|---|
| 3 | Ортофотоплан | ortho | sat | `yandex.hd_roads`, `yandex.rail`, `osm.landuse`, `osm.roads`, `yandex.road_labels`, `gisogd.admin`, `egko.water`, `egko.water_labels` |
| 4 | Материалы фотофиксации | photos / photos | белая |  |
| 5 | Схема существующего использования территорий с границами зон с особыми условиями использования территорий | use | белая | `nspd.parcels`, `gisogd.zouit`, `gisogd.szz`, `gisogd.vodookhr`, `gisogd.red_lines`, `gisogd.airfield` |
| 6 | Генеральный план города Москвы. Фрагмент схемы «Карта функциональных зон» | gp | белая | `gisogd.func_zones`, `gisogd.func_zones_tinao` |
| 7 | Схема обеспеченности территории разработанной документацией ППТ и ПМТ | ppt | белая | `gisogd.ppt`, `gisogd.pmt` |
| 8 | Схема обеспеченности территории разработанной документацией ГПЗУ и АГР | gpzu | белая | `gisogd.gpzu`, `gisogd.agr` |
| 9 | Схема существующих землепользователей разрабатываемой территории | parcels | sat | `nspd.parcels`, `osm.landuse`, `osm.roads`, `egko.water`, `egko.water_labels` |

## План реализации ППТ КРТ, листы «в границах сит. плана», с 10-го (albums.js PPTKRT_D; в конец альбома, #37)

| № | лист | concept / kind | основа | ключи слоёв |
|---|---|---|---|---|
| 10 | Фрагмент карты административно-планировочной структуры города Москвы | district | sat | `osm.roads`, `sit.road_labels`, `sit.places`, `gisogd.admin`, `egko.water`, `egko.water_labels` |

## Раздел «Существующее положение» (sheets.js SEC1)

| № | лист | concept / kind | основа | ключи слоёв |
|---|---|---|---|---|
| 1 | Подготовка проекта планировки территории | title | белая |  |
| 2 | Месторасположение рассматриваемой территории | — | белая | `gisogd.admin` |
| 3 | Ортофотоплан | — | sat | `gisogd.admin` |
| 4 | Ортофотоплан | — | sat | `osm.roads` |
| 5 | Существующее состояние и использование территории с имеющимися ограничениями | — | белая | `nspd.zouit`, `gisogd.zouit`, `gisogd.szz`, `gisogd.vodookhr`, `egko.green`, `egko.water`, `calc.uds_osm`, `nspd.parcels`, `egko.buildings`, `gisogd.okn`, `gisogd.red_lines` |
| 6 | Существующее использование территории с характеристикой по землепользованию | — | sat | `nspd.parcels` |
| 7 | Материалы фотофиксации | photos | белая | `calc.uds_osm`, `egko.buildings`, `osm.roads` |
| 8 | Фрагменты схем Генерального плана города Москвы | — | белая | `gisogd.func_zones`, `gisogd.func_zones_tinao` |
| 9 | Фрагменты схем правил землепользования и застройки города Москвы | — | белая | `gisogd.pzz_zones` |
| 10 | Схема об утверждённой и разрабатываемой документации | — | белая | `calc.uds_osm`, `egko.buildings`, `gisogd.gpzu`, `gisogd.krt`, `gisogd.ppt` |
| 11 | Объекты социальной инфраструктуры и радиусы обслуживания | — | белая | `egko.buildings`, `osm.social` |

Ветки conceptSheet по виду листа: `district`, `docs`, `gp`, `gpzu`, `ortho`, `parcels`, `photos`, `ppt`, `pzz`, `pzzsub`, `use`.
