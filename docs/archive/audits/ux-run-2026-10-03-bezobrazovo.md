# Run 2026-10-03: Безобразово, owner's path (T50), v0.98.4, snapshot of team/grado2 HEAD
Machine: Mac, load average 4.8 at start, 2.5 at end (uptime). Headless Chrome 1440x900, server port 8696. Portals: no parallel loads, no retries added by me.

| # | step | time | result (what the owner sees) | blockers |
|---|---|---|---|---|
| 1 | open project (16.5 MB, 36 layers) | 0.7 s (same session); 0.75 s after page reload (autorestore) | 36 layers in tree, map with sheet "Лист 1 A1 1:5053" | project has territory=null: "Территория 0,00 га" (lead said boundary exists) |
| 2 | Данные, re-download one layer (ГПЗУ ОГД) | 34.5 s (status "Выгрузка идёт" for 30 s with no name/percent; after 30 s "Первая выгрузка слоя целиком... разбор") | toast "Загружено слоёв: 1", layer list now 37 | creates a DUPLICATE layer (gisogd.gpzu 350 next to ogd.gpzu 349) instead of refreshing; picker pre-checks 38 layers; Данные docks as a 280 px strip |
| 2b | draw boundary by hand (needed for 3) | ~4 s | 92,39 га | owner must redraw boundary; zoom jumps to 1:4990 |
| 3 | Ограничения, Рассчитать | 0.34 s | "Ограничения рассчитаны", all 7 layers = 0 objects: ЗОУИТ 0, красные линии/ПЗЗ/Генплан "не загружены", здания 0 | WRONG: project layers are keyed ogd.*/egko.*, constraints read gisogd.*/nspd.*/osm.* keys; 3566 ЕГКО buildings and water zones ignored |
| 4a | Схема расчёта, Пересчитать | 0.25 s | "Пятно застройки 78,51 га · 0 корпусов"; node "Слой: Санитарно-защитные... слой не загружен" | graph window opens 1.1 s, cramped strip |
| 4b | Эскиз, Построить (Секции) | <0.1 s | 206 corpuses of 12 floors, over the river, water zone and existing villages | consequence of step 3 (no constraints), no warning |
| 5 | Варианты, Подобрать (24) | ~3 s | 24 variants, table, best "Секции 17 м вдоль" density 25,0 | none; column "Ниже предельной высоты" empty |
| 6 | Показатели, Нормативы, change 2,1 to 2,5 | open 0.04 s; recompute 0.3 s | Квартир 16 596 to 13 941, population unchanged (correct) | "Показатели" is not on the top bar at 1440 px (only in Окна menu); "Район определяется…" stuck, orange raw text "Overpass не ответил (Errno 54; HTTP 504; timed out)" |
| 7a | Листы, Собрать, Альбом ППТ КРТ | ~4 min (20:25:50 to 20:30) | 10 sheets; downloads Yandex tiles 1470, OSM x2 (HTTP 504), ЕГКО re-download, ОГД | status only in bottom bar, window says "Собираю…" with no progress; selection of 787 buildings left over; title sheet says "АДРЕС" placeholder |
| 7b | PDF | 26 s, 6.3 MB, 10 pages | warning "Не готовы листы 6, 10: не всё поместилось" (grey note on sheet) | console warning turf SweepLine union (albums.js:568); page 5 map empty; sheet 1 has no sketch |
| 7c | DXF | 23.6 s, 12.9 MB zip "grado2-dxf.zip" | toast ok | file name generic, not project name |
| 7d | Excel | 0.13 s, 6 KB | toast ok | not opened |
| 8 | Save | 0.9 s | file 16.5 to 34 MB | none |

Total machine time of the steps: about 5.7 min (344 s), of which album 250 s, project load 1 s, calculations under 5 s. Plus manual boundary.
Console: only one warning (turf SweepLine in albums.js:568); no errors.

## Top 5 blockers (board lines)
T? | developer | constraints read keys of the loaded ОГД/ЕГКО layers (ogd.*, egko.buildings), not only gisogd.*/nspd.*/osm.* | Безобразово: Рассчитать ограничения gives non-zero ЗОУИТ/ПЗЗ/здания, sketch avoids water zone | apps/grado2/web/constraints.js, app.js (EXIST_KEY)
T? | developer | sketch/graph warn "ограничения пустые" when all constraint layers are 0 | sketch over empty constraints shows a message | web/constraints.js, analysis.js
T? | developer | re-download of a layer replaces the existing layer (same key) instead of adding a duplicate; picker pre-selects only the clicked layer; progress with layer name | ГПЗУ re-download keeps 36 layers; status shows name and percent | web/app.js, ogdpick.js, ogd_all.py
T? | developer | "Собрать альбом": progress window (step n of m, tiles) and no OSM 504 hang; do not leave selection of 787 objects | album assembly shows progress; time under 2 min warm | web/albums.js, sheets.js
T? | designer | bottom docked windows (Данные, Ограничения, Эскиз) are 280x230 strips; run buttons below fold; Показатели hidden from top bar at 1440 px; Overpass error shown raw | at 1440x900 run button visible without scroll | web/index.html, app.js, layout.js

## Screenshots (/tmp/grado-team/2026-10-03/t50/shots)
01a-proj-menu, 02-opened, 02c-after, 02e-reload, 03a-data, 03b-picker, 03c-search, 03e-checked, 03f-load-10s, 03f-load-30s, 03g-done, 04a-cons, 04f-boundary-drawn, 05b-cons-done, 06b-graph-run, 07a-sketch, 07b-sketch-built, 08c-vars-done, 09d-oкна-menu, 09e-tep, 10a-norms, 10b-norm-changed, 11a-sheets, 11b-collect-menu, 11d-album-done, 11e-album-state, 12b-pdf-done, 12c-pdf-pages, 13a-export-menu, 13b-dxf, 13c-excel, 14a-save-menu, 14b-saved
Downloads: dl/Безобразово.pdf, dl/grado2-dxf.zip, dl/grado2-tep.xlsx (pdf pages in pdfimg/).
