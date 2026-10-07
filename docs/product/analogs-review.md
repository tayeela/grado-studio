# Обзор open-source аналогов ГРАДО Студии

> Дата верификации: **2026-07-16**. Лицензия, звёзды (★) и дата последнего коммита проверены напрямую через GitHub API на эту дату. Deep-research харнесс сфазой автоверификации не доработал (упал синтез, подтвердил голосованием лишь 6 утверждений, ни одного не опроверг), поэтому все репозитории перепроверены вручную по API.
>
> **Итог:** из 18 GitHub-репозиториев 16 подтверждены, 1 опровергнут (OpenCAD), 1 URL исправлен (Sidewalkreator висел под неправильным владельцем).
>
> Статусы: ✅ подтверждён · ⚠️ подтверждён с оговоркой · ❌ опровергнут / не OSS

## Направление 1 — функциональные аналоги (цельные среды)

| Проект | Статус | Лицензия | ★ | Посл. коммит | Вывод |
|---|---|---|---|---|---|
| [qgis/QGIS](https://github.com/qgis/QGIS) | ✅ | GPL-2.0 | 14 092 | 2026-07-15 | Эталон возможностей (точная оцифровка + Print Layout), но десктоп C++/Qt и через GDAL — то, чего проект избегает |
| [digitalcityscience/TOSCA](https://github.com/digitalcityscience/TOSCA) | ⚠️ | MIT | 36 | 2023-11-08 | Веб-ГИС для партиципаторного планирования; близко по цели, но нет CAD-черчения и вёрстки. Заброшен ~2.5 года |
| [GeoNode/geonode](https://github.com/GeoNode/geonode) | ✅ | Other (GPL-family) | 1 694 | 2026-07-16 | Django+GeoServer CMS — архитектурный контраст без-серверному сценарию ГРАДО |
| [UDST/urbansim](https://github.com/UDST/urbansim) | ⚠️ | BSD-3-Clause | 538 | 2023-12-06 | Статистическая модель городов, не среда черчения. Заброшен |
| [EL-BID/open-urban-planning-toolbox](https://github.com/EL-BID/open-urban-planning-toolbox) | ⚠️ | нет файла лицензии | 6 | 2026-05-07 | Не единая среда, а хаб-каталог из 3 инструментов спутник-анализа. Далеко от ГРАДО |
| ArcGIS Urban (Esri) | ❌ не OSS | проприетарный | — | — | Ближайший по классу референс, но закрытый SaaS, не для GitHub-обзора |

## Направление 2 — CAD-черчение на JS / canvas / web-GIS

| Проект | Статус | Лицензия | ★ | Посл. коммит | Вывод |
|---|---|---|---|---|---|
| [mlightcad/cad-viewer](https://github.com/mlightcad/cad-viewer) | ✅ | MIT | 831 | 2026-07-16 | «Fully web-based DXF/DWG viewer+editor, runs entirely in browser» — тезис «без бэкенда» подтверждён его же описанием. Стек TypeScript, не чистый JS |
| [microsoft/maker.js](https://github.com/microsoft/maker.js) | ✅ | Apache-2.0 | 2 013 | 2026-06-27 | Программное 2D-черчение (масштаб/поворот/зеркало/пересечения), работает в браузере — годный building block |
| [dubstar-04/Design-Core](https://github.com/dubstar-04/Design-Core) | ✅ | GPL-3.0 | 15 | 2026-05-23 | «Javascript 2D CAD Library», DXF + canvas/Cairo. Прямо в тему, но GPL-3.0 — вирусная лицензия, осторожно |
| [vagran/dxf-viewer](https://github.com/vagran/dxf-viewer) | ✅ | MPL-2.0 | 559 | 2026-06-08 | Браузерный DXF-рендер через WebGL, только просмотр, без редактирования |
| [geosolutions-it/MapStore2](https://github.com/geosolutions-it/MapStore2) | ✅ | Other (GPL-family) | 651 | 2026-07-16 | Веб-ГИС фреймворк React+OpenLayers; тяжелее чистого JS+canvas |
| [tldraw/tldraw](https://github.com/tldraw/tldraw) | ✅ | Other (своя tldraw-лицензия) | 48 789 | 2026-07-16 | Мощный infinite-canvas SDK, но лицензия несвободная — коммерческое использование ограничено |
| OpenCAD (opencad.dev) | ❌ опровергнут | — | — | — | Сайт живой (HTTP 200), но заявленного репозитория `Cengizhanuzuner/OpenCAD` не существует (у пользователя 0 репозиториев). Как OSS-аналог с GitHub — не подтверждается |
| [kauevestena/osm_sidewalkreator](https://github.com/kauevestena/osm_sidewalkreator) | ✅ URL исправлен | GPL-3.0 | 46 | 2025-09-21 | Харнесс дал неверного владельца (`AhcamCortes`). QGIS-плагин генерации тротуаров — узкая ниша, слабо релевантен |

## Направление 3 — парсеры SHP/DXF без GDAL, печать

| Проект | Статус | Лицензия | ★ | Посл. коммит | Вывод |
|---|---|---|---|---|---|
| [GeospatialPython/pyshp](https://github.com/GeospatialPython/pyshp) | ✅ | MIT | 1 153 | 2026-06-29 | Точное попадание: SHP чтение/запись на чистом Python без GDAL — аналог `shp_reader.py` |
| [mozman/ezdxf](https://github.com/mozman/ezdxf) | ✅ | MIT | 1 359 | 2026-07-05 | DXF R12–R2018 на Python без GDAL — готовый DXF-экспорт под сценарий ГРАДО |
| [calvinmetcalf/shapefile-js](https://github.com/calvinmetcalf/shapefile-js) | ✅ | MIT | 813 | 2025-10-01 | SHP→GeoJSON прямо в браузере, без внешних гео-библиотек |
| [mapfish/mapfish-print](https://github.com/mapfish/mapfish-print) | ✅ | BSD-2-Clause | 197 | 2026-07-15 | Печать шаблонных карт в PDF — референс для вёрстки альбомов, но Java-сервис |
| [mlightcad/awesome-cad](https://github.com/mlightcad/awesome-cad) | ✅ | MIT | 53 | 2026-06-21 | Curated-список OSS CAD — вторичный источник для дальнейшего поиска |

## Практический вывод для ГРАДО Студии

Наиболее близкое по стеку и лицензии, на что реально можно опереться кодом:

- **Парсеры без GDAL** — pyshp, ezdxf, shapefile-js (все MIT, живые, точное попадание в архитектуру).
- **CAD-ядро на canvas** — maker.js (Apache-2.0) как building block; cad-viewer как ориентир «всё в браузере» (но TS). Design-Core ближе всех по замыслу, но GPL-3.0 — при заимствовании кода потянет за собой лицензию.
- **Осторожно с лицензиями:** tldraw (несвободная), Design-Core и Sidewalkreator (GPL-3.0), MapStore2/GeoNode (GPL-family).
- **Прямых цельных аналогов «ГИС+CAD+вёрстка в браузере» нет** — TOSCA близка по духу, но без CAD и заброшена; ArcGIS Urban закрыт. Ниша фактически свободна.
