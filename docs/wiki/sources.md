<!-- генерируется tools/wiki.py — не править руками -->

# Источники данных (server.py, SOURCES)

45 ключей. Ключ слоя — `источник.имя`; вид — коннектор (gisogd, egko, nspd, osm, yandex…).

| ключ | вид | название | строка |
|---|---|---|---|
| `egko.addresses` | egko | Адреса (ЕГКО) | server.py:144 |
| `egko.buildings` | egko | Здания (ЕГКО) | server.py:131 |
| `egko.fences` | egko | Заборы (ЕГКО) | server.py:143 |
| `egko.green` | egko | Газоны и растительность (ЕГКО) | server.py:135 |
| `egko.paths` | egko | Пешеходные дороги (ЕГКО) | server.py:134 |
| `egko.place_labels` | egko | Пояснительные подписи (ЕГКО) | server.py:142 |
| `egko.roads` | egko | Дороги (ЕГКО) | server.py:133 |
| `egko.water` | egko | Водная поверхность (ЕГКО) | server.py:137 |
| `egko.water_labels` | egko | Подписи рек и водоёмов (ЕГКО) | server.py:139 |
| `gisogd.admin` | gisogd_admin | Административные округа и районы | server.py:126 |
| `gisogd.agr` | gisogd | Свидетельства об утверждении АГР (ОГД) | server.py:125 |
| `gisogd.airfield` | gisogd | Приаэродромные территории (ОГД) | server.py:107 |
| `gisogd.demolition` | gisogd | Уведомления о сносе (ОГД) | server.py:113 |
| `gisogd.gpzu` | gisogd | Градостроительные планы земельных участков (ОГД) | server.py:121 |
| `gisogd.krt` | gisogd | Комплексное развитие территорий (ОГД) | server.py:122 |
| `gisogd.okn` | gisogd | Объекты культурного наследия и их зоны (ОГД) | server.py:92 |
| `gisogd.pmt` | gisogd | Проекты межевания территории (ОГД) | server.py:124 |
| `gisogd.ppt` | gisogd | Проекты планировки (ОГД) | server.py:116 |
| `gisogd.pzz_sub` | gisogd | ПЗЗ: подзоны — плотность, высота, застроенность (ОГД) | server.py:90 |
| `gisogd.pzz_zones` | gisogd | ПЗЗ: территориальные зоны и ВРИ (ОГД) | server.py:91 |
| `gisogd.red_lines` | gisogd | Красные линии и ЛГР (ОГД) | server.py:84 |
| `gisogd.zouit` | gisogd | ЗОУИТ и зоны ограничений (ОГД) | server.py:96 |
| `relief.contours` | terrain | Рельеф: горизонтали (SRTM) | server.py:114 |
| `sit.buildings` | yandex_sit | Ситплан: здания (Яндекс) | server.py:165 |
| `sit.green` | yandex_sit | Ситплан: озеленение (Яндекс) | server.py:161 |
| `sit.places` | yandex_sit | Ситплан: названия территорий (Яндекс) | server.py:182 |
| `sit.rail` | yandex_sit | Ситплан: железная дорога, главные пути (Яндекс) | server.py:166 |
| `sit.road_labels` | yandex_sit | Ситплан: подписи улиц (Яндекс) | server.py:181 |
| `sit.roads` | yandex_sit | Ситплан: оси дорог (Яндекс) | server.py:164 |
| `sit.roads_hd` | yandex_sit | Ситплан: проезжая часть (Яндекс) | server.py:163 |
| `sit.stations` | yandex_sit | Ситплан: станции метро, МЦК и МЦД (Яндекс) | server.py:175 |
| `sit.water` | yandex_sit | Ситплан: вода (Яндекс) | server.py:162 |
| `yandex.buildings` | yandex | Здания (Яндекс) | server.py:149 |
| `yandex.green` | yandex | Озеленение (Яндекс) | server.py:153 |
| `yandex.hd_roads` | yandex | Проезжая часть (Яндекс) | server.py:148 |
| `yandex.landuse` | yandex | Функциональные зоны (Яндекс) | server.py:152 |
| `yandex.parking` | yandex | Парковки (Яндекс) | server.py:155 |
| `yandex.rail` | yandex | Железная дорога, главные пути (Яндекс) | server.py:168 |
| `yandex.rail_stations` | yandex | Станции железной дороги (Яндекс) | server.py:180 |
| `yandex.road_edges` | yandex | Кромки проезжей части (Яндекс) | server.py:151 |
| `yandex.road_labels` | yandex | Подписи улиц (Яндекс) | server.py:179 |
| `yandex.roads` | yandex | Оси дорог и дорожек (Яндекс) | server.py:150 |
| `yandex.stations` | yandex | Станции метро, МЦК и МЦД (Яндекс) | server.py:172 |
| `yandex.transport` | yandex | Транспорт (Яндекс) | server.py:156 |
| `yandex.water` | yandex | Вода (Яндекс) | server.py:154 |

Предел области выгрузки, км² (LIMIT_KM2): `{"gisogd_admin": 1e9, "nspd": 250.0, "osm": 150.0, "gisogd": 150.0, "egko": 150.0, "terrain": 150.0, "yandex": 40.0, "yandex_sit": 150.0}`

Слои с фильтром объектов (SIT_FILTER): `sit.places`, `sit.rail`, `sit.stations`, `yandex.rail`, `yandex.rail_stations`, `yandex.stations`

Общие настройки задаются циклами `for _k in (…)` в server.py.
