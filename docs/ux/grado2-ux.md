# ГРАДО 2 — UX principles, audit scenarios, queue

The Stop hook `.claude/hooks/grado2_ux_gate.py` sends Claude here after every change to
`apps/grado2`. Walk the scenarios as the owner would: an urban planner who knows QGIS and
AutoCAD and is not a programmer. Judge by the principles. Fix what is small; put the rest in
the queue at the bottom with a date.

## Principles (the owner's own words, 22–23.09.2026)

1. **No imposed stages.** Work does not have to go collect → analysis → sketch. Everything lives
   in one workspace; tools open as floating windows the owner arranges freely.
2. **A tool strip like AutoCAD is always visible.** Point, line, polygon, rectangle, vertices,
   move, delete, undo, measure, territory boundary. Hotkeys work in any keyboard layout.
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

A. **Draw from scratch.** Fresh page → «+ Слой», name it, polygons → draw two polygons →
   edit an attribute in «Объект» → move one polygon → delete one → Ctrl+Z brings it back.
B. **Draw without creating a layer.** Pick «Линия» on the tool strip → a layer «Линии» appears
   and is current → draw a line → the status bar names the layer.
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
F. **Measure.** Length and area tools show the value while drawing and keep it on the map; Esc
   clears.
G. **Export.** «Экспорт DXF» downloads a zip with the drawing, red_lns.shx and REDLN97.LIN.
H. **Windows state.** Move and resize windows, reload → they come back where they were.
I. **Save and restore.** Draw, restyle, change a graph slider → reload → everything is back
   (autosave). Ctrl+S on an unnamed project asks for a name → «Проекты» lists it → «Новый проект»
   empties the map → «Открыть» brings back layers, order, styles, data and graph values. The header
   shows «•» while there are unsaved changes. Test on `grado2-test` (port 8651, temp project folder),
   never in the owner's «Документы/ГРАДО 2».

Every scenario: no console errors, every button has a tooltip, nothing overlaps at 1280×800.

## Queue

- 2026-09-23: real insolation and fire-gap checks (now only a gap/height coefficient).
- 2026-09-23: setbacks from red lines by the ОГД layer (5 m, СП 42.13330) as a graph node.

- 2026-09-23: printing and sheets with REDLN97.
- 2026-09-23: DWG via the ODA converter (owner has not decided).
- 2026-09-23: layer groups in the tree; multi-select and batch attribute edit.
