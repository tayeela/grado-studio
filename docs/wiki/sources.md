<!-- генерируется tools/wiki.py — не править руками -->

# Источники данных (server.py, SOURCES)

45 ключей. Ключ слоя — `источник.имя`; вид — коннектор (gisogd, egko, nspd, osm, yandex…).

| ключ | вид | название | строка |
|---|---|---|---|
| `egko.addresses` | egko | Адреса (ЕГКО) | server.py:141 |
| `egko.buildings` | egko | Здания (ЕГКО) | server.py:128 |
| `egko.fences` | egko | Заборы (ЕГКО) | server.py:140 |
| `egko.green` | egko | Газоны и растительность (ЕГКО) | server.py:132 |
| `egko.paths` | egko | Пешеходные дороги (ЕГКО) | server.py:131 |
| `egko.place_labels` | egko | Пояснительные подписи (ЕГКО) | server.py:139 |
| `egko.roads` | egko | Дороги (ЕГКО) | server.py:130 |
| `egko.water` | egko | Водная поверхность (ЕГКО) | server.py:134 |
| `egko.water_labels` | egko | Подписи рек и водоёмов (ЕГКО) | server.py:136 |
| `gisogd.admin` | gisogd_admin | Административные округа и районы | server.py:123 |
| `gisogd.agr` | gisogd | Свидетельства об утверждении АГР (ОГД) | server.py:122 |
| `gisogd.airfield` | gisogd | Приаэродромные территории (ОГД) | server.py:104 |
| `gisogd.demolition` | gisogd | Уведомления о сносе (ОГД) | server.py:110 |
| `gisogd.gpzu` | gisogd | Градостроительные планы земельных участков (ОГД) | server.py:118 |
| `gisogd.krt` | gisogd | Комплексное развитие территорий (ОГД) | server.py:119 |
| `gisogd.okn` | gisogd | Объекты культурного наследия и их зоны (ОГД) | server.py:89 |
| `gisogd.pmt` | gisogd | Проекты межевания территории (ОГД) | server.py:121 |
| `gisogd.ppt` | gisogd | Проекты планировки (ОГД) | server.py:113 |
| `gisogd.pzz_sub` | gisogd | ПЗЗ: подзоны — плотность, высота, застроенность (ОГД) | server.py:87 |
| `gisogd.pzz_zones` | gisogd | ПЗЗ: территориальные зоны и ВРИ (ОГД) | server.py:88 |
| `gisogd.red_lines` | gisogd | Красные линии и ЛГР (ОГД) | server.py:81 |
| `gisogd.zouit` | gisogd | ЗОУИТ и зоны ограничений (ОГД) | server.py:93 |
| `relief.contours` | terrain | Рельеф: горизонтали (SRTM) | server.py:111 |
| `sit.buildings` | yandex_sit | Ситплан: здания (Яндекс) | server.py:162 |
| `sit.green` | yandex_sit | Ситплан: озеленение (Яндекс) | server.py:158 |
| `sit.places` | yandex_sit | Ситплан: названия территорий (Яндекс) | server.py:179 |
| `sit.rail` | yandex_sit | Ситплан: железная дорога, главные пути (Яндекс) | server.py:163 |
| `sit.road_labels` | yandex_sit | Ситплан: подписи улиц (Яндекс) | server.py:178 |
| `sit.roads` | yandex_sit | Ситплан: оси дорог (Яндекс) | server.py:161 |
| `sit.roads_hd` | yandex_sit | Ситплан: проезжая часть (Яндекс) | server.py:160 |
| `sit.stations` | yandex_sit | Ситплан: станции метро, МЦК и МЦД (Яндекс) | server.py:172 |
| `sit.water` | yandex_sit | Ситплан: вода (Яндекс) | server.py:159 |
| `yandex.buildings` | yandex | Здания (Яндекс) | server.py:146 |
| `yandex.green` | yandex | Озеленение (Яндекс) | server.py:150 |
| `yandex.hd_roads` | yandex | Проезжая часть (Яндекс) | server.py:145 |
| `yandex.landuse` | yandex | Функциональные зоны (Яндекс) | server.py:149 |
| `yandex.parking` | yandex | Парковки (Яндекс) | server.py:152 |
| `yandex.rail` | yandex | Железная дорога, главные пути (Яндекс) | server.py:165 |
| `yandex.rail_stations` | yandex | Станции железной дороги (Яндекс) | server.py:177 |
| `yandex.road_edges` | yandex | Кромки проезжей части (Яндекс) | server.py:148 |
| `yandex.road_labels` | yandex | Подписи улиц (Яндекс) | server.py:176 |
| `yandex.roads` | yandex | Оси дорог и дорожек (Яндекс) | server.py:147 |
| `yandex.stations` | yandex | Станции метро, МЦК и МЦД (Яндекс) | server.py:169 |
| `yandex.transport` | yandex | Транспорт (Яндекс) | server.py:153 |
| `yandex.water` | yandex | Вода (Яндекс) | server.py:151 |

Предел области выгрузки, км² (LIMIT_KM2): `{"gisogd_admin": 1e9, "nspd": 250.0, "osm": 150.0, "gisogd": 150.0, "egko": 150.0, "terrain": 150.0, "yandex": 40.0, "yandex_sit": 150.0}`

Слои с фильтром объектов (SIT_FILTER): `egko.fences`, `egko.place_labels`, `egko.water_labels`, `relief.contours`, `sit.rail`, `sit.stations`, `yandex.rail`, `yandex.stations`

Общие настройки задаются циклами `for _k in (…)` в server.py.
