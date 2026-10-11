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
   Coordinates are typed as in AutoCAD too (owner, 01.10.2026). Comma is the Russian decimal separator, so the rule is
   fixed: where a POINT is expected, `A,B` without spaces is a point X,Y when both parts are integers (`0,0`), or when a
   part has a dot (`12345.6,6789.1`); `@A,B` is the same relative to the last point. An absolute `A,B` of two integers
   is a point only while there is no last point (the first point); after it, `25,5` stays the length 25.5 m, use `@`
   for an offset. Everywhere else comma stays decimal: `12345,6`, `25,5`, `25,5<90`, `12345,6;6789,1`. `X;Y` and
   `@dx;dy` are unchanged. Where a length or number is expected, `A,B` is a decimal number.
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
   graph/sketch windows are open; «Сохранить слоем» turns the sketch into a normal layer that can
   be edited, styled, saved and exported.
10. **Windows version is mandatory** — nothing Mac-only in the UI (hotkeys show Ctrl on Windows).
11. **A tool, not a template** (owner, 25.09.2026: «не задавай строгую логику, делай приложение инструментом, а не
    макетом»). Direct manipulation first: an object on the map with grips and a context bar beats a form in a window.
    Nothing requires a territory boundary: a sheet drawn on the map is enough to load data and export. Analogues:
    Figma frame (F, presets, drag to draw, bar over selection), AutoCAD viewport on a layout, QGIS «Export Project to
    DXF» (layer per layer, extent drawn on canvas).

## Scenarios

A. **Draw from scratch.** Fresh page → «+ Слой», name it, polygons → draw a polygon (polyline, double click),
   Space repeats the command → a second polygon →
   edit an attribute in «Объект» → move one polygon → delete one → Ctrl+Z brings it back.
B. **Draw without creating a layer.** Type PL and Enter (or the polyline button) → click points → Enter → a layer
   «Линии» appears and is current; the status bar shows the command prompt with its options in brackets.
C. **Existing situation.** Open «Данные» → «Пример» territory → load sources → layers appear in
   the tree in a sensible order → drag a layer up → it draws on top.
D. **Analysis.** Open «Схема расчёта» → select a node → its output shows on the main map → change a
   buffer → «Эскиз застройки» on the map updates → «Показатели» shows ТЭП.
D2. **No uninvited sketch.** New project → «Пример» → load → the map shows data and the boundary
   only. «Эскиз» → «Построить эскиз» → sections along the blocks, not over existing houses →
   «Сохранить слоем» → a layer «Эскиз: …» appears; close the sketch window → the preview hides,
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
   «Эскиз» → «Построить» → some sections are lower («ниже предельной высоты» in the node). Switch the ceiling layer off → the sketch
   rises back. The window says the insolation is a design-stage estimate by ГОСТ Р 57795-2017, not for expertise.

M. **Generation.** After L: «Эскиз» → «Этажность по: цели плотности» → «Построить» — the node reaches the ТЭП target or says
   how much is missing. «Варианты» → «Подобрать варианты» → cards and a table; click one → the map shows it → «Сохранить слоем».
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
(`GRADO2_E2E=1 python -m unittest apps/grado2/tests/test_e2e.py`). C, D, E, G, H, N run offline in the new interface `/next/`
(`apps/grado2/tests/e2e/next_acceptance.mjs`, same test file): the fixture project with a boundary instead of «Пример» and the portals,
then sketch and ТЭП, a sketch parameter changing ТЭП, variants and «Объём», DXF / GeoJSON / Excel downloads, the window layout
after a reload, the «Радиусы обслуживания» node and «В слой», views switching layer visibility. Real portal downloads stay with the
owner's run on Хорошёво and ТиНАО.

## Queue

- 2026-10-08 (#53 fixes, v0.99.46; checked in headless Chrome on a copy of «КРТ 3229 Гольяново», console clean). An address taken
  from the registry marks the title row «не готов: адрес из реестра — сверьте с письмом ДГП»; the reason was only in the icon tip, so
  «Штамп…» now shows a grey note under «Адрес» that goes away once the owner edits the field (fixed). Not yet: the note does not say
  where the letter's address comes from — the owner types it by hand; a «Письмо ДГП» field could keep it with the project.
- 2026-10-07 (#45, #47, album ППТ КРТ by the owner's remarks; checked on the real build of «КРТ 3229 Гольяново» in headless Chrome, console:
  only the old `voronoi` warning of sheet «сущпол»). Not yet: the scheme outline (`ALBUM.meta.area`) has no button — it is set in the
  project data; needs «Контур схем» in «Листы и альбом» (draw or load GeoJSON). Panorama links are stored with photos (`photo.link`) but
  not shown and cannot be added from the photo button — needs «Добавить снимок по ссылке Яндекс Панорам» and the link in the photo tip.
  Sheet order of the album is fixed by `PPTKRT_ORDER`; reordering by hand in the sheet list is kept until the next «Собрать».

- 2026-10-07 (v0.99.34–0.99.38, external audit #25): done and checked on screenshots — «ещё не рассчитано» in «Показатели»,
  short sheet labels, Enter on buttons + skip links + focusable map, whole graph on second «Вся схема» + «Широкая карта»,
  source sets. Not yet: the right panel «Стиль / Объект» keeps its width while empty («Выберите слой в дереве») — could
  collapse to a strip until a layer is chosen; the bottom-docked graph is only ~250 px high on 1365 × 923 — a taller
  default for that dock; a full screen-reader pass (VoiceOver) of the map objects through «Таблица атрибутов».
- 2026-10-06 (v0.99.32–0.99.33, audit): «Нормативы» show «район не определён — выберите зону» after a failed lookup —
  checked on screen. Guest entry checked: opens at once as «Гость», «Выйти» → login with «Войти гостем, без пароля»,
  console clean. Not yet: all guests are one account «Гость» — in comments, presence and history colleagues cannot be
  told apart; a name prompt for guests (kept in the browser) would fix it.
- 2026-10-06 (v0.99.21, «Макет листа», ported from DesignCraft): done — labels snap to edges and centres of other labels
  and of the sheet with a magenta guide (Alt off), Ctrl+Z / Ctrl+Shift+Z and header buttons. Audit: works on a test sheet,
  console clean. Not yet (DesignCraft `crates/tools/src/snap.rs` has them): snap to the map frame, legend and table boxes
  (only labels carry `data-key` in the sheet SVG, frames do not); equal-spacing snap (pass_spacing) for rows of own labels;
  a rotated label (street names) snaps by its upright bounding box; several labels selected at once with align/distribute.
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
  EL, H, DIM, T, AR remembers its numbers + AE, F2 history). Text goes to DXF as TEXT (v0.39.0), dimensions as real DIMENSION entities and back (v0.45.0); hatch patterns: seven patterns and a step per layer since v0.47.0 (not the full ANSI set).
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
  boundary-following layout, not a grid); ~~guest parking for ИЖС~~ (done v0.42.0 by 945-ПП, owner: «все по 945»).

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
- 2026-09-25 (done v0.49.0): the «Листы» table no longer squeezes the title column to zero in a narrow window (it scrolls
  sideways); section sheets say «слои раздела». Street labels along lines, the territory callout and wrapped legend lines — done v0.50.0.
- 2026-09-25 (done v0.53.0): the canvas was cluttered after building section 1 (all slide layers on, buildings from three
  sources, roads hidden under zones). Now a reference plan with one buildings layer and УДС polygons; «Упорядочить слои».
  Open: the ОКН legend shows a category «0» (portal value without a zone name); УДС polygons are not dissolved, so a white
  road with an edge would show seams — on slides they are drawn without an edge.

- 2026-09-26 (v0.60.0): one window for source data. Choosing what to load and what goes to the ГИС ОГД DXF happens
  in a single tree («Исходные данные»), opened from «Данные», from a sheet and from «DXF ГИС ОГД»; the «Данные»
  window only shows what the project already has.

- 2026-09-26 (v0.62.0): the layer tree can be read by sheets. «По листам» shows a folder per sheet with only its
  layers; a layer of several sheets is listed in each of them. Sheet content is edited right in its folder.
- 2026-09-30 (v0.84.0, hub mode): at 1440 px the hub buttons fold into the account menu below 1400 px; check on the owner's real screen once hub mode is on. Comment pins can sit under sheet frames and make grabbing a frame at that exact spot harder (frames.js:141).
- 2026-10-01 (v0.84.9): album sheets keep the styles they were built with, so a style change in the program reaches an
  existing project only after the album is rebuilt; the owner has to remember to press it. Candidate: refresh the
  template part of «pptkrt_» sheets on project open (keep frame, scale and photos). Sheets that do not fit are now
  named in the export message and marked «не готов» under the map — check that the owner notices it.
- 2026-10-01 (v0.85.0, teams): open points from the review, not fixed. (1) Anyone can add an existing person to a
  team without their consent, and the 404/200 answer reveals whether a login exists (same as project shares today);
  if it becomes a nuisance — accept-to-join or a daily limit. (2) Team and project metadata are changed in memory
  before the file write; a failed write leaves memory ahead of disk until the next re-read. (3) Disabled people still
  count as team owners, so a team whose only owner is disabled is managed by the admin only. (4) Test gaps: demoting a
  team owner to member keeps the stream; personal role plus team access «none». Projects window: list_teams reads
  every project file to count team projects — fine for tens of projects, cache team ids if the hub grows.
- 2026-10-01 (v0.86.0, link access, favourites, copy): open points, not fixed. (1) People who came by a link stay in
  `link_users` until the link is rotated or turned off; disabled accounts stay there and count toward the cap of 500,
  and an account the admin re-enables gets its link access back. (2) While a login is throttled for bad links, a valid
  link also answers 429 until the window passes. (3) The pid → team map goes stale if `meta.json` is edited outside the
  server (a restart fixes it). (4) `test_server.py` guard: temp folders are not cleaned; an explicitly set
  `GRADO2_HUB_DIR` is outside the guard. (5) After a 429 the page retries the stored link on each reload until the tab is
  closed. (6) People without the owner role see only «Включать и выключать ссылку может только владелец проекта», not
  whether a link is on.
- 2026-10-01 (v0.87.0, UI audit, `docs/archive/audits/ux-2026-10-01.md`): left for later — dark graph canvas (litegraph reads
  colours once), cursor coordinates in the status bar, AutoCAD-style staged ribbon collapse, layer search, undo entries
  of a deleted layer's earlier edits are dropped, focus after re-render in «По листам» mode returns to the first row.
- 2026-10-01 (v0.88.1): closed — socket names and fields «Потолок, м», «Потолок, эт.» renamed with a project
  migration. Open: a ceiling layer with two distinct values and 5 quantile classes paints both cells one colour.
- 2026-10-01 (v0.88.0, first-run audit): open — a sheet/PDF path for a
  newcomer still needs the «Листы» window explained; mouse-wheel zoom felt too fast to a novice; the help (F1) is long
  and has no jump links.
- 2026-10-02 (v0.91.3): the `_uid` loss on re-download below is fixed. Open: header buttons shift ~80 px for ~30 ms
  after a project opens (sync label «сохранено» → «отправляю…» → «сохранено»); a click in that moment hits the
  neighbouring button — give the sync label a fixed width.
- 2026-10-01 (v0.88.0, found while checking): a re-download of «Земельные участки (ЕГРН)» keeps the internal `_uid` of
  only 2 of 1122 unchanged parcels (same on v0.87.0 — not new); collaboration merges and selections rely on `_uid`.
  The default ГИС ОГД layers in the source picker were empty for the ТАО site, so a newcomer gets ГИС ОГД data only
  after ticking other layers.

