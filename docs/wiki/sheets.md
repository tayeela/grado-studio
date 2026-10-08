<!-- генерируется tools/wiki.py — не править руками -->

# Листы альбомов

Состав и порядок листов альбома ППТ КРТ берутся из самого `apps/grado2/web/albums.js` (его выполняет
`tools/wiki_albums.mjs` в Node), поэтому таблица совпадает с тем, что собирает программа. Порядок выдачи — `PPTKRT_ORDER`;
«шаблон #» — номер листа в массиве (по нему хранятся снимки и правки проектов). Дальнейший выбор источников (дороги,
станции, районы, зоны) делает `conceptSheet` в albums.js по данным рамки листа. Правила — album-rules.md и rules.md.

## Альбом «План реализации ППТ КРТ» — 11 листов в порядке выдачи (PPTKRT_ORDER)

| № | лист | концепт / вид | основа | рамка | ключи слоёв | шаблон # |
|---|---|---|---|---|---|---|
| 1 | Титульный лист | title | белая | — |  | 0 |
| 2 | Месторасположение рассматриваемой территории | — | белая | — |  | 1 |
| 3 | Фрагмент карты административно-планировочной структуры города Москвы | district | sat | sit, bleed, fit:district | `osm.roads`, `sit.road_labels`, `sit.places`, `gisogd.admin`, `egko.water`, `egko.water_labels`, `sit.stations` | 9 |
| 4 | Ортофотоплан | ortho | sat | bleed, fit:terr | `yandex.hd_roads`, `egko.roads`, `yandex.rail`, `osm.landuse`, `osm.roads`, `yandex.road_labels`, `gisogd.admin`, `egko.water`, `egko.water_labels`, `egko.place_labels`, `egko.addresses`, `yandex.stations`, `yandex.rail_stations` | 2 |
| 5 | Материалы фотофиксации | photos | белая | fit:terr | `egko.water`, `yandex.hd_roads`, `egko.roads`, `egko.buildings`, `yandex.rail`, `osm.landuse`, `osm.roads`, `yandex.road_labels`, `egko.water_labels`, `egko.place_labels`, `egko.addresses`, `yandex.stations`, `yandex.rail_stations` | 3 |
| 6 | Схема существующего использования территорий с границами зон с особыми условиями использования территорий | use | белая | fit:terr | `egko.water`, `yandex.hd_roads`, `egko.roads`, `egko.buildings`, `yandex.rail`, `nspd.parcels`, `gisogd.zouit`, `gisogd.szz`, `gisogd.vodookhr`, `gisogd.red_lines`, `gisogd.airfield`, `osm.landuse`, `osm.roads`, `yandex.road_labels`, `egko.water_labels`, `egko.place_labels`, `egko.addresses`, `yandex.stations`, `yandex.rail_stations` | 4 |
| 7 | Схема существующих землепользователей разрабатываемой территории | parcels | sat | fit:terr | `nspd.parcels`, `osm.landuse`, `osm.roads`, `egko.water`, `egko.water_labels`, `egko.place_labels`, `egko.addresses`, `yandex.stations`, `yandex.rail_stations` | 8 |
| 8 | Схема с отображением границ территорий с имеющимися территориальными и отраслевыми схемами, документацией по планировке территории | docs | белая | sit, fit:cover | `egko.green`, `egko.water`, `yandex.hd_roads`, `egko.roads`, `egko.buildings`, `yandex.rail`, `nspd.parcels`, `gisogd.red_lines`, `gisogd.ppt`, `gisogd.pmt`, `osm.landuse`, `osm.roads`, `yandex.road_labels`, `egko.water_labels`, `egko.place_labels`, `egko.addresses`, `yandex.stations`, `yandex.rail_stations` | 10 |
| 9 | Схема с отображением границ территорий с выданными градостроительными планами земельных участков | docs | белая | sit, fit:cover | `egko.green`, `egko.water`, `yandex.hd_roads`, `egko.roads`, `egko.buildings`, `yandex.rail`, `nspd.parcels`, `gisogd.red_lines`, `gisogd.gpzu`, `osm.landuse`, `osm.roads`, `yandex.road_labels`, `egko.water_labels`, `egko.place_labels`, `egko.addresses`, `yandex.stations`, `yandex.rail_stations` | 13 |
| 10 | Размещение территории в материалах градостроительного зонирования (ПЗЗ города Москвы) | pzz | белая | sit, twin, fit:cover | `egko.water`, `yandex.hd_roads`, `egko.roads`, `egko.buildings`, `yandex.rail`, `gisogd.krt`, `gisogd.pzz_zones`, `gisogd.pzz_sub`, `osm.landuse`, `osm.roads`, `yandex.road_labels`, `egko.water_labels`, `egko.place_labels`, `egko.addresses`, `yandex.stations`, `yandex.rail_stations` | 12 |
| 11 | Генеральный план города Москвы. Фрагмент схемы «Карта функциональных зон» | gp | белая | fit:terr | `gisogd.func_zones`, `gisogd.func_zones_tinao`, `egko.water`, `yandex.hd_roads`, `egko.roads`, `egko.buildings`, `yandex.rail`, `osm.landuse`, `osm.roads`, `yandex.road_labels`, `egko.water_labels`, `egko.place_labels`, `egko.addresses`, `yandex.stations`, `yandex.rail_stations` | 5 |

## В шаблоне, но не в выдаче

| № | лист | концепт / вид | основа | рамка | ключи слоёв | шаблон # |
|---|---|---|---|---|---|---|
| — | Схема обеспеченности территории разработанной документацией ППТ и ПМТ | ppt | белая | fit:terr | `egko.water`, `yandex.hd_roads`, `egko.roads`, `egko.buildings`, `yandex.rail`, `gisogd.ppt`, `gisogd.pmt`, `osm.landuse`, `osm.roads`, `yandex.road_labels`, `egko.water_labels`, `egko.place_labels`, `egko.addresses`, `yandex.stations`, `yandex.rail_stations` | 6 |
| — | Схема обеспеченности территории разработанной документацией ГПЗУ и АГР | gpzu | белая | fit:terr | `egko.water`, `yandex.hd_roads`, `egko.roads`, `egko.buildings`, `yandex.rail`, `gisogd.gpzu`, `gisogd.agr`, `osm.landuse`, `osm.roads`, `yandex.road_labels`, `egko.water_labels`, `egko.place_labels`, `egko.addresses`, `yandex.stations`, `yandex.rail_stations` | 7 |
| — | Размещение территории в материалах территориального планирования (Генеральный план города Москвы) | gp | белая | sit, fit:cover | `gisogd.func_zones`, `gisogd.func_zones_tinao`, `egko.water`, `yandex.hd_roads`, `egko.roads`, `egko.buildings`, `yandex.rail`, `osm.landuse`, `osm.roads`, `yandex.road_labels`, `egko.water_labels`, `egko.place_labels`, `egko.addresses`, `yandex.stations`, `yandex.rail_stations` | 11 |

Ветки conceptSheet по виду листа: `district`, `docs`, `gp`, `gpzu`, `ortho`, `parcels`, `photos`, `ppt`, `pzz`, `pzzsub`, `use`.

## Раздел «Существующее положение» (sheets.js SEC1)

| № | лист | концепт / вид | основа | ключи слоёв |
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
