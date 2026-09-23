# ГРАДО 2 — goal and plan

## Goal

**ГРАДО 2 is a workstation for an urban planner (macOS and Windows) for pre-design analysis of a
territory in Moscow and a massing sketch on top of it.**

It is ready when an urban planner, without a programmer, gets from a territory boundary to a
package of materials in one working day:

1. a map of the existing situation from real sources, with the date of each download;
2. a map of constraints: ЗОУИТ, red lines and setbacks, the ПЗЗ height limit, the insolation shadow
   of existing buildings, the parts to keep and to demolish;
3. two or three sketch variants that pass the norms check, each with ТЭП by the Moscow КРТ method;
4. the output: a PDF album on sheets with a frame, legend and scale, plus DXF/DWG in МГГТ with the
   REDLN97 linetypes.

Every number and every constraint can be traced to a data source and to a clause of a norm.

**Out of scope:** a legally valid insolation certificate (in Russia that needs certified software;
ГРАДО gives a design-stage estimate and says so), full ППТ documentation, BIM.

**Acceptance:** two reference territories — Хорошёво (46 ha, dense old Moscow) and a ТиНАО site
(greenfield). For each, the scenarios in `docs/ux/grado2-ux.md` pass, the package is produced in
under a day, the console is clean, and the Windows installer runs on a clean machine.

## Where we are (23.09.2026, v0.14.0)

Done: one workspace with an AutoCAD-like tool strip; floating windows that snap to the side
panels; resizable panels; QGIS-like layers (order, styles single/categories/ranges/rules/ЛГР,
labels, attribute table, editing with the original kept); real sources НСПД, OSM, ГИС ОГД
(red lines with REDLN97); DXF import/export in МГГТ; node graph (layer filter, buffer, subtract,
union, intersect, placement, ТЭП КРТ); sketch on demand along each block, preview vs accepted
layer; variants; 3D; projects with autosave; self-audit hooks.
Э1 done in v0.7.0: layer groups, multi-select (click, Shift, frame), batch attribute edit, undo/redo for objects and
styles, keys window, first-run panel, GPU drawing for layers over 20 000 objects (100 000 checked).
Э2 done in v0.8.0: ПЗЗ subzones (density, height, coverage) and zones (ВРИ), ОКН and their zones, demolition notices,
relief contours, ФГИС ТП documents by territory, import of GeoJSON/KML/Shapefile/DXF by button or drop, satellite
basemaps, re-download with a diff merged with manual edits, buildings register «сохраняем / сносим». DWG still waits for
the owner's decision on the ODA converter.
Э4 done in v0.9.0: window «Ограничения» → layers (ЗОУИТ and ОКН zones, red-line setback, fire gaps to kept buildings,
ПЗЗ zero subzones, insolation front of neighbours' windows, solar ceiling with the ПЗЗ height); graph node «Ограничения»
reads the switched-on layers; placement never exceeds the ceiling. Insolation validated against the МАрхИ 55° ruler and
analytic cases. Not done: site sun-hours map and own insolation of new buildings (moved to Э5).
Э5 done in v0.10.0: five typologies, floors water-filled to the density goal under the ceiling, a 20-candidate variant
search with a comparison table, «Проверить нормы» (own and neighbours' insolation, bans, fire gaps) re-run live on edits of
an accepted sketch, floors ± for selected buildings, 3D ground shadows for a date and time. Not done: NSGA-II (a weighted
ranking is used instead), a sun-hours map of the site.
Э3 done in v0.11.0: analysis nodes (service radii by СП 42.13330, walking isochrones over OSM streets, block indicators,
territory balance) that label their result on the map, «В слой» for any node, views of the map with legends.
Э6 done in v0.12.0: window «Листы» — A3/A1 sheets from views with a ГОСТ frame and title block, north arrow, scale bar,
legend and ТЭП table; SVG preview and a PDF album through the core renderer in МГГТ with REDLN97. DWG waits for the ODA
converter decision.
Э7 done in v0.13.0 except the installer runs: project format 2 with migrations, browser scenarios (offline, headless Chrome)
in the unittest gate and CI, PyInstaller spec + Inno Setup + GitHub workflow for Windows and macOS, launchers, built-in help.
Open: run the workflow on GitHub and install on a clean Windows machine; accept the Xcode licence to build the .app locally.
v0.14.0 (after the plan): OSM answer cache and a separate OSM request, «Стоп» and progress for the variant search, long names cut in graph nodes.

## Where we are (23.09.2026, v0.21.0) and the next plan

All seven stages Э1–Э7 are done in code. Since v0.14: ФГИС ТП search by name, ОГД download percent (v0.15), sheet frame on
the map and ТЭП-only sheets (v0.16), per-layer scale visibility (v0.17), weak-point audit with security and data-safety fixes
(v0.18), typologies ИЖС, blocked houses and urban blocks with plots and streets (v0.19–0.20), ТЭП by «Калькулятор 2.0» with
Moscow norms, district parameters and the owner's rounding rules (v0.21).

**The goal is not yet accepted.** The acceptance above needs two things that were never done: the full package on the
ТиНАО reference site, and the Windows installer on a clean machine. The release workflow cannot even start: 69 commits of
ГРАДО 2 (everything since 17.07.2026) are not pushed to GitHub — this is also the only off-site copy of the work.

Next stages, in order. Estimates are in working sessions.

### Э8. Acceptance of the goal (2 sessions) — first; partly done 23.09.2026 (v0.22.0)
Results so far:
- GitHub run 35852669412 (workflow_dispatch on `main`): unit and browser tests, Windows build with a smoke test and the
  Inno Setup installer, macOS build with a smoke test and the DMG — all green; artifacts `grado2-windows-latest` (26 MB) and
  `grado2-macos-latest` (29 MB). Not yet: install on a clean Windows machine (owner).
- ТиНАО, Краснопахорский, 44.2 ha (a village with ИЖС and a nature zone next to it): 16 sources loaded without errors,
  constraints, a sketch to the density goal, norms check, 24 variants, accepted sketch, a two-sheet album PDF (0.58 MB) and
  DXF (0.54 MB) — 24 s of program time with warm caches, console clean. ТЭП took zone 2, K2 0.9, ТиНАО and K1 1.0 by itself.
- Found and fixed: generation did not respect the Genplan functional zones — a sketch could stand in a nature zone. New ban
  layer «Запрет: природные зоны Генплана» (natural, green, park and ООПТ zones; «природно-жилая» allows housing); checked on
  a site crossing the ТиНАО nature zone: 16.8 ha banned, none of 21 buildings on it.
- Found, not fixed (→ Э9/Э10): the density target is 25 everywhere — in ТиНАО the ПЗЗ subzone density should set it (the
  sketch reports «не хватает 779 тыс. м²» against an unrealistic goal); urban blocks leave 5 buildings with under 50 % of
  facades insolated (north sides of blocks).
- Still to do: first download on a cold cache timed, Хорошёво repeated with the new ТЭП, the owner's own run.

- Done 23.09.2026: `main` pushed, run `grado2-release.yml`, install on a clean Windows machine (owner or a
  Windows VM), build the .app after `sudo xcodebuild -license` (owner's password).
- ТиНАО greenfield site (e.g. Коммунарка or Былово): boundary → data → constraints → sketch → variants → album PDF + DXF,
  timed. Everything that stops the owner goes into Э9–Э11; the package-in-a-day claim is written down with the real time.
- Repeat on Хорошёво with the new ТЭП and the new typologies; compare ТЭП with the genplan.tech calculator for the same inputs.

### Э9. ТЭП and social infrastructure to the end (3 sessions)
- The ТЭП demand becomes objects: ДОО, school and clinic as placeable building types with plot areas by capacity
  (2151-ПП tables 1.4.1–1.4.2 steps, clinic plot 0.35 ha); «Посадка» reserves them first when the deficit is not covered.
- Service radii and walking access by the Moscow decrees instead of federal СП 42.13330 (ДОО 300 m, 500 m in ЦАО; school
  1000 m; retail 500/800 m; culture 1500 m / 20 min; clinic 20/30 min) — the analysis nodes switch by the territory.
- Missing norms: additional education 6/8/4 per 1000, ОТОП 0.7 m² per person, playground reductions (−15 %, −20 %), minimums 100/50 m².
- Parking as space: permanent places turn into a required area of car parks (ground, underground, multi-storey) and the
  sketch shows where they go; visitor parking for non-residential floors.
- K1 by walking distance over the OSM street graph (the walking isochrone node already has Dijkstra) instead of × 1.3;
  a territory over two districts takes the district with the larger share and says so.

### Э10. Generation quality (3 sessions)
- Rows bent to the site boundary instead of straight strips; blocked rows packed from both ends; outbuildings and garages
  for ИЖС; guest parking in urban blocks.
- Done v0.28.0: per-building drop under a low solar ceiling when the density goal is met without it; the freed spots
  become yards where neighbours need sun (test site: goal 15 — 19 sections dropped, neighbours keep the norm).
- Insolation: schools and kindergartens as their own norm class (hours to be taken from СанПиН 1.2.3685-21 text, not from memory), relief height
  from SRTM under the buildings, the site sun-hours map.
- A variant can be edited and saved as a named variant; the comparison table keeps accepted and hand-edited variants.

### Э11. Speed and reliability for big projects (1–2 sessions)
- Autosave caches each layer's JSON by `rev` (now ~0.3 s freeze at 100 000 objects).
- «Правила» style counts once per data change, not per redraw; attribute table virtualised.
- «Проверить нормы» re-checks only buildings near the edit, in chunks, with a progress line.
- PDF: text as real text (ToUnicode and font subset) so an album can be searched and copied; empty rings; `fill_opacity`
  instead of mixing with white.

### Э12. Exchange (1–2 sessions)
- Export of the accepted sketch and constraints to GeoJSON/SHP for QGIS and to the ГИС ОГД attribute layout.
- Sheet list and ТЭП table as XLSX for the explanatory note.

### Owner decisions (23.09.2026)
1. Work is pushed to GitHub; the repository stays private.
2. Rounding: two decimals only for SPP values and SPP density, three for everything else — as implemented in v0.21.
3. Buildings under a low solar ceiling are dropped when the density goal is met without them (Э10).
4. No DWG: the ODA converter is not used; exchange stays DXF. Э12 loses its DWG item.
5. The old studio (`apps/studio`), the wizard (`apps/wizard`) and the ТЭП web calculator (`apps/calc-web`) are closed: no
   development and no fixes; their launchers and the studio release workflow are removed. The code stays in the repository
   because `core/*` tests and history use it. `moscow_krt.json` stays with its known errors, only for them.
6. The 5 places for children with disabilities are inside the ДОО and school norm — nothing to add.
7. ВРИ change cost and social compensation are not done for now.

## Stages (Э1–Э7, done)

Each stage ends with a working, checked version and a commit. Estimates are in working sessions.

### Э1. Shell finish (2 sessions) — done, v0.7.0
- Layer groups in the tree; multi-select of objects (frame, Shift); batch attribute edit.
- Undo for style changes. Done: copy/paste style between layers (v0.6.3).
- Keyboard map window; first-run hint instead of an empty screen.
- Performance: 100 000 objects in a layer without lag (OL WebGL layer for big point/line sets).
- Done: OpenLayers, Turf, litegraph and Lucide served locally, the app works offline (v0.6.2).

### Э2. Existing situation — complete data (3 sessions) — done, v0.8.0 (DWG open)
- ПЗЗ Москвы: territorial zones and their limits (height, density, КОЗ) from ГИС ОГД.
- ОКН and their zones; ФГИС ТП (fix the DNS issue or go through the portal the studio already uses).
- Import SHP, GeoJSON, KML; DWG through the ODA File Converter (the owner decides).
- Satellite basemap; relief (contours) from the core connector.
- Re-download with a diff against the previous download (the core connectors already keep snapshots).
- Existing-buildings register: floors, year, purpose, «сохраняем / сносим» marked on the map.

### Э3. Analysis (3 sessions) — done, v0.11.0
- Nodes: distance and service radii (schools, ДОО, clinics by 2151-ПП/945-ПП), walking isochrones
  over the OSM street graph, density and floors by block, territory balance.
- Thematic maps as «views» of one map (layer set + styles + title + legend), reused on sheets.
- Every node explains its result in words on the map («почему здесь нельзя»).

### Э4. Constraints for generation (3–4 sessions) — done, v0.9.0
- Buildable area = territory − ЗОУИТ − 5 m from red lines (СП 42.13330) − kept buildings with
  their gaps; the ПЗЗ height limit per zone.
- Insolation: shadow of existing buildings on the site and of new buildings on existing windows,
  СанПиН 1.2.3685-21 (2 h continuous, 22.04–22.08) — 2.5D extruded prisms, sun vectors, facade
  points. Solar envelope of the site (the max height that does not shade neighbours).
- Fire gaps by СП 4.13130 table 1 (by fire-resistance degree), shown as buffers.
- All constraints are layers the owner can see and switch off; generation reads the same layers.
- Details and sources: section «Generation under constraints» below (from the research).

### Э5. Generation (3–4 sessions) — done, v0.10.0
- Typologies: sections, perimeter block, towers, point-and-bar, mixed; floors chosen to hit the
  target density within the height limit.
- Several variants scored by ТЭП and constraints; a comparison table; accept one into the project.
- Manual edit of accepted buildings (floors per building, move) with a live norms check that
  highlights violations (gap, insolation of neighbours, ЗОУИТ).
- 3D with shadows for a chosen date and time.

### Э6. Output (3 sessions) — done, v0.12.0 (DWG open)
- Sheets: A3/A1 frame by ГОСТ, title block, north arrow, scale bar, legend from the view, ТЭП table.
- PDF through the core renderer (core/render + core/layout already print albums), with REDLN97.
- Album of several sheets; DXF/DWG of the whole project.

### Э7. Product (2–3 sessions) — done in code, v0.13.0 (installers not yet run on a clean machine)
- Windows and macOS installers (the studio already has PyInstaller/py2app + Inno Setup specs).
- Project format with a version number and migrations.
- Scenario tests in a headless browser in CI; the UX hook scenarios become automated.
- Short built-in help in the owner's terms.

## Order

Э1 → Э2 (ПЗЗ and existing-buildings register first) → Э4 (constraints) → Э5 → Э3 → Э6 → Э7.
Constraints come before more generation: a sketch that ignores ЗОУИТ and insolation is the
"random rows of houses" the owner rejected. Analysis nodes grow along the way as constraints need them.

## Generation under constraints

Research notes and sources: `docs/research/2026-09-23-generative-constraints.md`. The consensus of
the literature and of production tools: hard geometry first, search only inside the feasible region.
ML generators are not usable for norm compliance (no Moscow training data, not verifiable).

Pipeline for ГРАДО 2, in this order:

1. **Buildable area** (Э4, low effort): territory − ⋃ ЗОУИТ − 5 m from red lines − kept buildings
   with СП 42.13330 gaps; the ПЗЗ height limit per zone. Turf difference/buffer. ЗОУИТ is plain data
   exclusion — no published algorithm is needed.
2. **Insolation of existing buildings** (Э4): sun positions for Moscow (55.75° N) every 10 min for
   22.04 and 22.08 (the СанПиН window); 2.5D shadow polygons of each prism per sun position; an
   "insolation front" of test points every few metres along the facades of existing residential
   buildings (their flat layouts are unknown — PIK Digital's approach); a point passes with ≥ 2 h
   continuous or ≥ 2.5 h intermittent with one interval ≥ 1 h. Validate on the МАрхИ worked cases.
3. **Solar envelope** (Э4): per grid cell the max height that does not break any front point —
   an instant «потолок» heatmap, order-independent (fixes PIK's greedy order dependence).
4. **Growth inside the envelope** (Э5): typology footprints (sections, blocks, towers) placed along
   the frontage as now; floors raised per building up to min(envelope, ПЗЗ, target density).
5. **Variants** (Э5): NSGA-II or a simple weighted search over typology, width, rotation and floors,
   scoring density vs. target, insolation margin, frontage, fire gaps (penalty). A comparison table;
   accept one into the project.
6. **Own insolation of new buildings** (Э5): the same front on the new facades — a check with
   highlighted failures, not a generator.

Every calculation says in the UI that it is a design-stage estimate by ГОСТ Р 57795-2017 methods,
not the certified calculation for expertise.
