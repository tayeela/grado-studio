<!-- генерируется tools/wiki.py — не править руками -->

# Источники данных (server.py, SOURCES)

41 ключей. Ключ слоя — `источник.имя`; вид — коннектор (gisogd, egko, nspd, osm, yandex…).

| ключ | вид | название | строка |
|---|---|---|---|
| `egko.addresses` | egko | Адреса (ЕГКО) | server.py:142 |
| `egko.bridges` | egko | Мосты (ЕГКО) | server.py:131 |
| `egko.buildings` | egko | Здания (ЕГКО) | server.py:127 |
| `egko.fences` | egko | Заборы (ЕГКО) | server.py:141 |
| `egko.green` | egko | Газоны и растительность (ЕГКО) | server.py:133 |
| `egko.paths` | egko | Пешеходные дороги (ЕГКО) | server.py:132 |
| `egko.place_labels` | egko | Пояснительные подписи (ЕГКО) | server.py:140 |
| `egko.roads` | egko | Дороги (ЕГКО) | server.py:129 |
| `egko.water` | egko | Водная поверхность (ЕГКО) | server.py:135 |
| `egko.water_labels` | egko | Подписи рек и водоёмов (ЕГКО) | server.py:137 |
| `gisogd.admin` | gisogd_admin | Административные округа и районы | server.py:122 |
| `gisogd.agr` | gisogd | Свидетельства об утверждении АГР (ОГД) | server.py:121 |
| `gisogd.airfield` | gisogd | Приаэродромные территории (ОГД) | server.py:103 |
| `gisogd.demolition` | gisogd | Уведомления о сносе (ОГД) | server.py:109 |
| `gisogd.gpzu` | gisogd | Градостроительные планы земельных участков (ОГД) | server.py:117 |
| `gisogd.krt` | gisogd | Комплексное развитие территорий (ОГД) | server.py:118 |
| `gisogd.okn` | gisogd | Объекты культурного наследия и их зоны (ОГД) | server.py:88 |
| `gisogd.pmt` | gisogd | Проекты межевания территории (ОГД) | server.py:120 |
| `gisogd.ppt` | gisogd | Проекты планировки (ОГД) | server.py:112 |
| `gisogd.pzz_sub` | gisogd | ПЗЗ: подзоны — плотность, высота, застроенность (ОГД) | server.py:86 |
| `gisogd.pzz_zones` | gisogd | ПЗЗ: территориальные зоны и ВРИ (ОГД) | server.py:87 |
| `gisogd.red_lines` | gisogd | Красные линии и ЛГР (ОГД) | server.py:80 |
| `gisogd.zouit` | gisogd | ЗОУИТ и зоны ограничений (ОГД) | server.py:92 |
| `relief.contours` | terrain | Рельеф: горизонтали (SRTM) | server.py:110 |
| `sit.buildings` | yandex_sit | Ситплан: здания (Яндекс) | server.py:163 |
| `sit.green` | yandex_sit | Ситплан: озеленение (Яндекс) | server.py:159 |
| `sit.rail` | yandex_sit | Ситплан: железная дорога, главные пути (Яндекс) | server.py:164 |
| `sit.roads` | yandex_sit | Ситплан: оси дорог (Яндекс) | server.py:162 |
| `sit.roads_hd` | yandex_sit | Ситплан: проезжая часть (Яндекс) | server.py:161 |
| `sit.water` | yandex_sit | Ситплан: вода (Яндекс) | server.py:160 |
| `yandex.buildings` | yandex | Здания (Яндекс) | server.py:147 |
| `yandex.green` | yandex | Озеленение (Яндекс) | server.py:151 |
| `yandex.hd_roads` | yandex | Проезжая часть (Яндекс) | server.py:146 |
| `yandex.landuse` | yandex | Функциональные зоны (Яндекс) | server.py:150 |
| `yandex.parking` | yandex | Парковки (Яндекс) | server.py:153 |
| `yandex.rail` | yandex | Железная дорога, главные пути (Яндекс) | server.py:166 |
| `yandex.road_edges` | yandex | Кромки проезжей части (Яндекс) | server.py:149 |
| `yandex.roads` | yandex | Оси дорог и дорожек (Яндекс) | server.py:148 |
| `yandex.stations` | yandex | Станции метро, МЦК и МЦД (Яндекс) | server.py:170 |
| `yandex.transport` | yandex | Транспорт (Яндекс) | server.py:154 |
| `yandex.water` | yandex | Вода (Яндекс) | server.py:152 |

Предел области выгрузки, км² (LIMIT_KM2): `{"gisogd_admin": 1e9, "nspd": 250.0, "osm": 150.0, "gisogd": 150.0, "egko": 150.0, "terrain": 150.0, "yandex": 40.0, "yandex_sit": 150.0}`

Слои с фильтром объектов (SIT_FILTER): `egko.fences`, `egko.place_labels`, `egko.water_labels`, `relief.contours`, `sit.rail`, `yandex.rail`, `yandex.stations`

Общие настройки задаются циклами `for _k in (…)` в server.py.
