# ГРАДО 2 — UX principles, audit scenarios, queue

The Stop hook `.claude/hooks/grado2_ux_gate.py` sends Claude here after every change to
`apps/grado2`. Walk the scenarios as the owner would: an urban planner who knows QGIS and
AutoCAD and is not a programmer. Judge by the principles. Fix what is small; put the rest in
the queue at the bottom with a date.

## Principles (the owner's own words, 22–23.09.2026)

1. **No imposed stages.** Work does not have to go collect → analysis → sketch. Everything lives
   in one workspace; tools open as floating windows the owner arranges freely.
2. **Drawing works like AutoCAD** (owner, 23.09.2026: «ориентируйся на автокад, скопируй инструменты»). The ribbon
   has the AutoCAD Draw and Modify panels (line, polyline, circle, arc, rectangle, polygon, point; move, copy, rotate,
   mirror, scale, offset, trim, extend, fillet, break, join, explode, erase, grips) with AutoCAD-style icons; commands are
   typed by their AutoCAD aliases (L, PL, C, TR…) and Enter or Space in any keyboard layout; Enter/Space repeats the last
   command, right click is Enter. Status bar modes: object snap (F3), object tracking with dashed alignment lines (F11),
   polar tracking (F10), ortho (F8), dynamic input (F12).
3. **Every tool says what to do next.** The status bar shows the active tool, the layer it
   draws into, and the next action ("щёлкайте вершины, двойной щелчок завершает").
4. **A new layer is immediately usable.** After «+ Слой» the drawing tool of its geometry is on.
   Picking a drawing tool without a suitable layer creates one and says so.
5. **Layers behave like QGIS.** Tree with drag-and-drop draw order, visibility, legend, styles
   (single / categories / ranges / rules / ЛГР), labels, attribute table, editable downloads with
   «Вернуть исходную выгрузку».
6. **No command line. No AI-slop design.** Plain system font, neutral panels, Lucide icons,
   no gradients or decorative cards. Both themes.
7. **Real data only.** Sources are real downloads (НСПД, OSM, ГИС ОГД); nothing is invented.
8. **Nothing is generated uninvited** (TestFit/Forma logic). A territory boundary only draws the
   boundary. Buildings appear after «Построить эскиз» with a chosen typology; they hug each
   part's long side, only whole buildings, gaps by СП 42.13330 п. 7.1 (15/20 m).
9. **Preview is not the project** (Grasshopper Preview/Bake). Graph results show only while the
   graph/sketch windows are open; «Принять в проект» turns the sketch into a normal layer that can
   be edited, styled, saved and exported.
10. **Windows version is mandatory** — nothing Mac-only in the UI (hotkeys show Ctrl on Windows).

## Scenarios

A. **Draw from scratch.** Fresh page → «+ Слой», name it, polygons → draw a polygon (polyline, double click),
   Space repeats the command → a second polygon →
   edit an attribute in «Объект» → move one polygon → delete one → Ctrl+Z brings it back.
B. **Draw without creating a layer.** Type PL and Enter (or the polyline button) → click points → Enter → a layer
   «Линии» appears and is current; the status bar shows the command prompt with its options in brackets.
C. **Existing situation.** Open «Данные» → «Пример» territory → load sources → layers appear in
   the tree in a sensible order → drag a layer up → it draws on top.
D. **Analysis.** Open «Граф» → select a node → its output shows on the main map → change a
   buffer → «Эскиз застройки» on the map updates → «Показатели» shows ТЭП.
D2. **No uninvited sketch.** New project → «Пример» → load → the map shows data and the boundary
   only. «Эскиз» → «Построить эскиз» → sections along the blocks, not over existing houses →
   «Принять в проект» → a layer «Эскиз: …» appears; close the sketch window → the preview hides,
   the accepted layer stays; restyle it (single / ranges) → the map follows.
E. **Variants and 3D.** Open «Варианты» → generate 6 → pick one → graph and map follow →
   open «Объём».
F2. **Precise drawing.** PL in a polygon layer → click → 40<0, 25<90, @-40;0, Enter each → Enter: a 40 × 25 m polygon.
   REC → click → @30;20. PO → 5000;15000. Hover an endpoint half a second → green «+» → move away along the vertical:
   a dashed tracking line holds the cursor; with a second acquired point the cursor stops at the crossing. L lines by
   coordinates, then TR (red dashed preview of what goes), EX, O 5, F with Р 3, RO 90 — all exact to a millimetre.
F. **Measure.** Length and area tools show the value while drawing and keep it on the map; Esc
   clears.
G. **Export.** «Экспорт DXF» downloads a zip with the drawing, red_lns.shx and REDLN97.LIN.
H. **Windows state.** Move and resize windows, reload → they come back where they were.
I. **Save and restore.** Draw, restyle, change a graph slider → reload → everything is back
   (autosave). Ctrl+S on an unnamed project asks for a name → «Проекты» lists it → «Новый проект»
   empties the map → «Открыть» brings back layers, order, styles, data and graph values. The header
   shows «•» while there are unsaved changes. Test on `grado2-test` (port 8651, temp project folder),
   never in the owner's «Документы/ГРАДО 2».

J. **Many objects.** A layer of 100 000 objects: pan and zoom without stalls; click selects; Shift+frame selects;
   Ctrl/⌘+A selects all; batch-edit one field; Ctrl/⌘+Z undoes it at once. Groups: make a group, drag a layer in,
   hide the group, save, reopen — the group and its order are back.

K. **Existing situation, full.** «Пример» → tick «ПЗЗ: подзоны», «ОКН», «Рельеф» → «Загрузить» → subzones coloured by
   density, a subzone's «Объект» shows «Регламент» in words. Buildings: menu «Реестр зданий» → select three → «сносим» →
   «Показатели» shows them under «Под снос». Drag a GeoJSON or KML onto the map → a layer appears. Switch the basemap to
   satellite. «Загрузить» again → the toast says what changed and your marks stay.

L. **Constraints.** With buildings (and ideally red lines, ПЗЗ, ОКН) loaded: «Ограничения» → «Рассчитать» → a group
   «Ограничения» appears; the front shows green / red / grey dots on neighbours' facades; the ceiling colours the site.
   «Эскиз» → «Построить» → some sections are lower («ниже по потолку» in the node). Switch the ceiling layer off → the sketch
   rises back. The window says the insolation is a design-stage estimate by ГОСТ Р 57795-2017, not for expertise.

M. **Generation.** After L: «Эскиз» → «Этажность по: цели плотности» → «Построить» — the node reaches the ТЭП target or says
   how much is missing. «Варианты» → «Подобрать варианты» → cards and a table; click one → the map shows it → «Принять в проект».
   Select three buildings → «Этажность +» a few times → the «Проверка норм» layer updates by itself. «Объём» → move the time
   slider → shadows move.

N. **Analysis and views.** Load «Улично-дорожная сеть» and «Школы, детсады, поликлиники (OSM)». Graph → «Анализ» →
   «Радиусы обслуживания» → select it: circles and «вне радиуса … га» are written on the map → «В слой». «Показатели
   кварталов» without inputs → blocks between streets with density. «Виды» → save «Существующее», hide layers, save
   «Анализ», switch between them; the legend follows.

O. **Album.** After M: «Виды» → save «Существующее» and «Эскиз» → «Листы» → fill the title block → «Добавить лист» twice
   (one per view, one A1 at 1:1000 with ТЭП) → the eye shows the sheet with frame, stamp, north arrow, scale bar and legend →
   «PDF альбома» downloads a file in about a second.

Every scenario: no console errors, every button has a tooltip, nothing overlaps at 1280×800 **and at 840 px wide** (the owner's
browser pane: the ribbon wraps into two rows, the layer and properties panels open over the map from «Окна ▾», windows stay
below the ribbon, the command line with clickable options sits at the bottom of the map).
Scenarios A, B, F, I, J, K (register), L, M, O are automated offline in `apps/grado2/tests/e2e/scenarios.mjs`
(`GRADO2_E2E=1 python -m unittest apps/grado2/tests/test_e2e.py`); C, D, E, G, H, N need real portals or the eye.

## Queue

- 2026-09-24 (v0.39.0, audit leftovers): ~~3D shadow hull, 200 m protection radius, TR preview on closed contours, partial
  Yandex areas, pending walking route~~ — done v0.40.0. ~~ТЭП «площадь сохранения и ограничений» holds only ЗОУИТ~~ —
  done v0.41.0 (owner's decision: footprints of kept buildings are added). Neighbours beyond the 60 m download
  strip are not loaded, so they are not protected even inside the new radius (the log says so).
- ~~2026-09-24 (v0.34.0, Яндекс): a Yandex layer loaded in v0.33 keeps «Контур 0» after re-download~~ — done v0.35.0: an untouched
  v0.33 style gets the outline back on re-download.
- ~~2026-09-24 (v0.33.0, Яндекс): tile seams in the outline of Yandex area layers~~ — done in v0.34.0 (pieces dissolved along tile edges).
- ~~2026-09-23 (v0.32.0, МСК): old ОГД/ЕГКО layers silently ~7,7 m off; old DXF system unknown~~ — done v0.35.0: opening a project
  of ≤ 0.31 with such layers says so (toast + «Данные» note with «Выгрузить заново»); DXF of ГРАДО 2 carries GRADO_CRS=MSK,
  an older ГРАДО 2 DXF (ezdxf + red_lns.shx, no mark) is read as ОГД by itself. Still: objects you edited keep old geometry.
- ~~2026-09-23 (v0.31.0, ЕГКО): frame outline of clipped polygons; «0 МБ» while the portal prepares; long re-download toast~~ —
  done v0.35.0 (edges on the clip frame are not stroked; «портал готовит файл…»; unchanged layers are counted, not listed).
  Still: a GPU-drawn layer (> 20 000 objects) and the PDF sheets stroke the frame edge.
- 2026-09-23 (v0.29–0.30, docking; done v0.30: layouts, splitter under the map): ~~docking by keyboard~~ (done v0.41.0: Tab to a
  window header, Alt+← → ↓ docks, Alt+↑ floats); a layout
  ~~does not remember window sizes inside zones~~ (done v0.40.0: «Моя раскладка» keeps heights, widths and the bottom zone). ~~Audit v0.30.0: a toast covers the «Окна» menu~~ — done v0.35.0.
- ~~2026-09-23 (UX audit v0.27–0.28): dropped-section yards, cut node line, array box at the top-left~~ — done v0.35.0: touching
  spots of dropped sections merge into one, own kind «свет соседям» (yellow) with «Причина» in the accepted layer; node line
  shortened; the typed-value box opens mid-map when the mouse has not been over the map.
- 2026-09-23 (done v0.27.0): a selection over 3 000 grips says so in the status bar; ARRAY shows ghost copies while its numbers are typed.
- 2026-09-23 (v0.24.0–0.25.0, AutoCAD drawing; done in v0.25.0: PLINE arc segments, CHAMFER, STRETCH, ARRAY rectangular
  and polar, LENGTHEN, polar tracking from the last segment, lengths at grips). ~~Not yet — rectangle corner options,
  ellipse, hatch, dimensions (DIM), text, associative arrays, a command history panel~~ — done v0.37.0 (REC fillet/chamfer,
  EL, H, DIM, T, AR remembers its numbers + AE, F2 history). Text goes to DXF as TEXT (v0.39.0) and a dimension's value as TEXT over its line (v0.40.0), not as a DIMENSION entity; hatch patterns are the layer's hatch, not ANSI patterns.
  Trim and extend work on lines and contours, not on points; a trimmed
  polygon becomes a line (a GIS polygon cannot be open).
- ~~2026-09-23 (v0.23.0, precise drawing): lengths in «Вершины», polar angles, perpendicular/parallel snaps, typed rotation~~ —
  done (lengths at vertices v0.25, polar steps and perpendicular v0.24, typed rotation = RO, parallel snap v0.37.0).
  Test note only: the first mouse moves right after a click sometimes do not show the snap marker in headless runs.
- 2026-09-23 (v0.22.0, acceptance on ТиНАО): ~~the ТЭП density target defaults to 25 everywhere~~ — done v0.38.0 (area-weighted
  ПЗЗ subzone density: taken automatically on the ПЗЗ download while the target is untouched, «взять цель» in «Показатели»).
  Still: urban blocks leave north-side sections under 50 % insolated facades.
- 2026-09-23 (v0.21.0): ТЭП follows «Калькулятор 2.0». ~~K1 straight × 1.3; two districts~~ — done v0.38.0 (K1 by a walking
  route over OSM streets and paths from the territory centre, `/api/rail_route`; a boundary spanning districts is named in a
  note — zone and K2 still follow the centre). Open: ВРИ cost and social compensation are not computed (owner: data P, Kp, УПКС);
  ~~the «Территория расчёта» block has no «сброс» for territory mode and percentages~~ (done v0.35.0).

- 2026-09-23 (v0.20.0, partly done): on the real Хорошёво site (13.2 ha buildable in 6 irregular parts) plots are now clipped
  by the boundary when ≥ 70 % (ИЖС) / 60 % (blocked) remain and the house fits — use of the site 30 → 45 %; urban blocks are
  clipped to the site with a courtyard ≥ 20 % and ≥ 600 m², streets only between placed blocks, no ribbons around existing
  houses. ~~No outbuildings; blocked rows packed from one end; ТЭП for ИЖС without 50 m² per person~~ — done
  (v0.41.0: a 4 × 6 m outbuilding/garage at the back of each ИЖС plot; blocked rows centred in the strip with memoised
  plot clipping; 50 m²/person since v0.21). Still open: strips stay straight (not bent to the boundary — needs a
  boundary-following layout, not a grid); guest parking for ИЖС needs a norm from the owner (945-ПП gives none for ИЖС).

- ~~2026-09-23 (audit v0.18.0): autosave, «Правила» counting, norms re-check~~ — done v0.36.0: unchanged layer data is not
  serialised again (100 000 objects: 111 → 5 ms), rule counts cached per data version and rules, the norms check runs in
  chunks, keeps the neighbours' baseline and a new edit interrupts the old run.

- ~~2026-09-23: DWG via the ODA converter~~ — done v0.41.0: DWG opens and «DXF» also writes grado2.dwg when the free ODA File
  Converter is installed (not bundled; path override GRADO2_ODA); without it the message says where to get it. Not tested
  here with a real converter (not installed on this Mac).
- 2026-09-23 (done v0.15.0): ФГИС ТП has a search by name over the whole catalog (all words, «ё» = «е»). The Moscow
  genplan is not in the ФГИС ТП catalog at all (checked over all 27 993 documents); for a territory in Moscow the window says
  so and points to the ГИС ОГД group.
- 2026-09-23 (done v0.15.0): the first ГИС ОГД download shows percent and MB in the status line (size from the portal's
  ETag / Content-Length), then «разбор».
- 2026-09-23 (done v0.14.0): OSM answers are cached on disk; a repeat or an area inside a cached one is instant, and when
  Overpass is down the last answer (up to 90 days) is used with a note. The first download of a new area still waits for
  the fastest mirror (measured 21 s at maps.mail.ru; overpass-api.de refused, two mirrors 504 after 50–77 s).
- 2026-09-23 (done v0.15.0): the style panel of a GPU-drawn layer says that labels appear from scale 1:N and hatches
  are a translucent fill at overview.
- 2026-09-23: insolation — ~~schools and kindergartens are not told apart; relief is flat~~ (done v0.41.0: schools and
  kindergartens are protected like housing; ground heights from «Рельеф: горизонтали» raise buildings and windows). Still: one
  reveal angle for all windows. (Done v0.17.0: the front points merged into the facade line at 1:3000 — the layer is now
  shown only at 1:2500 and larger, by the new per-layer scale visibility.)
- 2026-09-23: the ceiling makes the sketch lower but not smarter — sections do not move to where the ceiling is high (Э5).
  Tried in v0.16 and not adopted: shifting the whole row grid across rows by 1/5…4/5 of a step and keeping the best
  capacity under the ceiling gave +0 % (sections), +0 % (mixed), +8 % (towers) on the test site, at 5× the time (1.7–2.5 s
  per edit instead of 0.35–0.5 s). What helps is per building: in «цели плотности» mode the best grid reached the goal
  with 91 instead of 100 sections — dropping buildings under a low ceiling when the goal is met without them. Needs the
  owner's word: it leaves free spots (yards) where neighbours need sun. (Done v0.28.0 with the owner's approval.)
- 2026-09-23 (done v0.14.0): the variant search has a progress bar and «Стоп» (also Esc); stopped runs keep what is
  computed. Still open: sections do not move towards where the ceiling is high — only floors adapt.
- 2026-09-23 (done v0.15.0): a toast moves to the top of the map when a window stands at the bottom centre.
- 2026-09-23 (done v0.15.0): segmented controls are an even grid; five typologies sit in 3 + 2 equal cells, nothing cut.
- 2026-09-23 (done v0.14.0): graph node titles, list values and the info line are cut with «…» to the node width;
  the list menu still shows full names.
- ~~2026-09-23: Moscow's own social norms are not wired into radii~~ — done v0.38.0: «Радиусы обслуживания» offers 2151-ПП
  (ДОО 300 м / ЦАО 500 м, школы 1000 м / ЦАО «в границах ЦАО») and 2152-ПП (аптеки 500 м / ТАО 800 м) by the territory's okrug;
  поликлиники by 2150-ПП are minutes of a transit route — the СП radius stays for them.
- 2026-09-23 (done v0.16.0): a sheet's frame is shown on the map (button in the sheet row) and dragged with the mouse
  like an AutoCAD viewport; the sheet keeps its own centre («Вернуть» centres it on the territory again). Content «таблица
  ТЭП» makes a sheet with all indicators in up to three columns. The «Листы» window opens as a strip at the bottom.
- 2026-09-23 (done v0.16.0): below 1480 px the six rarer windows move into a labelled «Окна ▾» menu with check marks
  (arrow keys, Enter, Esc work).
