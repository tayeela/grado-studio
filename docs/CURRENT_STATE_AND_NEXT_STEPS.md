# GRADO Studio — Current State and Continuation Guide (2026-07)

> **ОБНОВЛЕНИЕ (после v0.48.0):** главный пункт этого файла — «GISOGD/данные без ZIP и бриджа» —
> реализован кнопкой «Данные»: прямая выгрузка OSM (Overpass, серверная, с зеркалами) и
> **НСПД/Росреестр (intersects-API геопортала, без авторизации)** по видимому экстенту с
> автосозданием слоёв-приёмников `source.osm.*` / `source.nspd.*`. ГИС ОГД Москвы прямо
> недоступен (API за SSO mos.ru — проверено), остаётся ZIP/ссылка. Детали протокола НСПД и
> исправленные косяки — в CLAUDE.md, блок «Сделано (v0.48.0)». Разделы ниже про OSM-504/
> «no-ZIP GISOGD» устарели в этой части.

**Purpose for other AIs/agents:** This document summarizes the current state of the GRADO Studio web app (browser-based CAD for urban planning/АГК/ППТ). It captures recent changes, fixes, open issues, and next steps per the approved plan (roadmap.md + fixes-geometry-layout.md + CLAUDE.md). Use this to continue development without re-reading the entire history.

## Project Overview
- **Main app:** `grado-studio/apps/studio/` — Python server (`server.py`) + web frontend (`web/app.js`, `index.html`, `style.css`).
- **Core:** CAD drawing on canvas (points, polylines, polygons, arcs, circles), layers (with roles), styles (LGR + project overrides), TEP calculations, album/PDF export, .grado (GeoPackage) roundtrip.
- **Key principles (from CLAUDE.md and fixes-geometry-layout.md):**
  - Move from hard `kind` (zone/building/redline) to generic CAD model: `geometry_type` + `layer_id` + `style_id` + attrs.
  - Layers have `topology="coverage"` for shared boundaries.
  - Styles resolved in priority: f.style_id → ruleStyleFor → layerStyle → + f.fmt.
  - Iron rules: tests first, generator-only styles (tools/gen_moscow_lgr.py), layer_id routing (not kind), no live .autosave editing.
  - UI: custom modals (.modal, .fmt-modal, .ask-modal), resizable panels, non-selectable text where appropriate.
- **Data sources:** Direct OSM (Overpass), file/bridge imports for НСПД/ГИС ОГД/ФГИС ТП, basemap tiles (OSM/ESRI).
- **Current version notes:** ~0.42+ (from code), many Etap 2 items done, focus on CAD robustness + UI polish + direct open data loading.

## Plan Status (from roadmap.md)
### Completed (~~strikethrough~~ in roadmap)
- Etap 0/1 basics: .grado roundtrip, imports, basemap, panel layers (QGIS-like), undo, styles.
- Etap 2 CAD: arcs (3pt + typed r), circles (center+radius, edit, snaps, buffers), trim/extend (now with circles as boundaries + parametric preserve), join improvements, fillet generalization (radius prop + visual arcTo on *any* polyline, not just redline), shared vertices for coverage layers.
- UI: modals sizing/fit-content (compact + fluid widths), resizable right panel (#panel + #panel-resizer with drag + localStorage), project styles manager, rules with operators (= > < contains starts), non-selectable UI text, onboard removed.
- Etap 6 partial: TEP presets editor + basic rules/checks.
- Direct OSM vector loading (no bridge needed).

### Remaining / Next Priorities (per roadmap + CLAUDE.md "Осталось")
- **Etap 2 CAD remaining:**
  - Полные сопряжения (full fillets) — beyond visual radius; actual geometry bake or tool to apply fillet to lines (currently only arcTo render + manual bake button for some cases).
  - Совместное редактирование общей границы одной операцией (joint shared boundary editing as single op) — improve beyond per-vertex (e.g., drag shared edges/segments as unit for coverage layers).
- **More powerful rules (fmt-патчи):** Current rules support basic ops; extend to multi-conditions, expressions, or per-feature fmt patches.
- **Свои стили в проекте + управление BASE_KINDS:** Project styles manager exists (create/edit/delete); enhance BASE_KINDS (add/edit/delete customs with defaults/topology).
- **Etap 4:** Ветки вариантов (branches/variants of concepts + side-by-side TEP comparison). Reactive journal basics done; UI + state branching needed.
- **Direct open data (no manual ZIP/bridge):**
  - GISOGD (ОГД): Current = user downloads ZIP → file or pasted URL → server fetch + import_gisogd (GisogdZip + ogr2ogr for MSK-50 → local).
    - **Goal achieved partially:** URL support added so user can generate export on portal and paste link (no local save).
    - **Next:** True "no download at all" — reverse portal selection/export API if possible (POST to generate, or find public WFS/GeoJSON endpoints for common layers like func zones, red lines, restrictions). Proxy via studio server. Hardcode common layer presets.
  - OSM: Direct Overpass for bbox (roads/buildings). Fixed 504 (area check + optimized query + Abort + better errors), coords (lonLatToLocal), visibility.
  - Other: Integrate data.mos.ru public datasets or other open sources directly (fetch GeoJSON, convert, add as layers).
- **UI polish (from user requests):**
  - Scale bar text no longer selectable (user-select:none).
  - Onboard "С чего начать" window removed.
  - Resizable panels (right #panel done; consider others).
  - Modals fit content (compact classes, wider lg variants, max-heights).
- **Etap 3/5/6 polish:** Album, packaging (.app, icons), more TEP rules.
- **General:** Fix remaining TODOs (e.g., arc support in duplicate/rotate), tests, error banners, offline.

**Current focus (last user-driven):** Making data import (esp. GISOGD + OSM) seamless/direct/in-UI without external tools/bridges/downloads. UI adaptation (resizable, no unwanted selection, fitting).

## Recent Changes & Fixes (as of latest session)
- **CAD drawing robustness:**
  - Circles work as trim/extend boundaries (circleIntersect + global search in trim*/extend*, exact for arcs via circleCircleIntersections + angle filter).
  - Fillet (radius) generalized to *any* polyline (removed kind==="redline" guard in draw; added to generic line fields in renderProps; applyFillet + filletLine JS impl for baking).
  - Join improved (carry max radius from originals so join corners fillet).
  - Rules enhanced (ruleStyleFor supports ops; UI table has "Оп" column; work/sync/render updated).
- **UI/Interface:**
  - Modals: .fmt-modal → min() widths, .modal-body.compact, better max-heights/scroll for lists/tables (manage-kinds, attr, lib, shortcuts). Fixed fitting.
  - Layers panel: Fixed duplicate + icons (new-layer=plus, project-styles=label/icon); project-styles now opens full manager (list + create/edit/delete, reuses createProjectStyle + uiPrompt).
  - Right panel (#panel): Made resizable (added #panel-resizer + drag JS with flexBasis, live resize(), localStorage persist, min/max). Fixed inversion (startW - dx for right sidebar).
  - Non-selectable UI text (body {user-select:none}), except inputs/editable. Scale label fixed.
  - Removed onboard "С чего начать" entirely (HTML + CSS + JS).
  - Consistent custom modals (no native prompt for project styles/create — now uiPrompt).
- **Data loading (direct, no bridge/ZIP where possible):**
  - **OSM direct (btn-osm):** Overpass for current view bbox → roads/buildings as features. Fixes: 504 (area check + timeout:15 + AbortController + specific msgs), coords (now converts via lonLatToLocal before push), visibility (force visible + renderLayers + fitView). Toast on success. No external GRADO needed.
  - **GISOGD/ОГД (btn-gisogd):** Still ZIP-based (user download or paste link). Server now supports `/api/import-gisogd-url` (fetches URL server-side via urllib, then same import_gisogd logic). UI choice: File or URL (uiConfirm + prompt for link). Force visible layers post-import. Clarified in titles/confirm: user generates on gisogd.mos.ru.
  - Goal: "получить данные из гисогд не скачивая зип" — use pasted export link (portal generates, app fetches). Still relies on portal export for full/auth data.
  - Bridge/inbox still supported for live GRADO extension, but de-emphasized for open sources.
- **Other:**
  - Project styles now have manager (no more blind create).
  - Topology="coverage" auto-set on boundary/restrict/zone layers.
  - Various polish: wider modals, compact forms, better error toasts.

**Bugs fixed in recent steps:**
- Circles as boundaries + result highlight (global search, thicker visuals, draw after setSelection).
- Duplicate + in layers panel + native prompt (distinct icons + uiPrompt).
- Text selection in scale (removed exception).
- Onboard window removed.
- OSM 504 + invisible objects (coords + area checks + force visible).
- GISOGD "strange data" (clarified workflow; added visibility force; URL support to avoid local ZIP).
- Resizer inversion + live feedback (sign fix + flexBasis + resize() on move).
- Modals not fitting (compact + widths + scroll).

## Key Files to Edit
- `apps/studio/web/app.js` — main logic (draw, props, modals, imports, resizer, OSM/GISOGD handlers, style resolution).
- `apps/studio/web/index.html` — structure (buttons, panel, modals, onboard removed).
- `apps/studio/web/style.css` + `tokens.css` — layout (modals, #panel, resizer, user-select, compact).
- `apps/studio/server.py` — endpoints (import-gisogd-url, etc.).
- `apps/studio/studio_core.py` — import_gisogd, _gisogd_route, build_project, grado_to_features.
- `core/connectors/grado_connectors/gisogd.py` — ZIP parsing (GisogdZip, ogr2ogr).
- `docs/roadmap.md`, `docs/fixes-geometry-layout.md`, `CLAUDE.md` — plan references (update on changes).

**How to run/test:**
- `cd apps/studio && python3 server.py` (http://localhost:8643).
- Open in browser; use "Демо", imports, drawing tools (T/E for trim/extend, J join).
- For OSM: zoom in, click "ОСМ" button.
- For GISOGD: generate on portal → copy link → click "ОГД" → "По ссылке".
- Check console for errors; use ? for shortcuts; F for fit; panel "Слои" for visibility.

## Open Issues / Next Steps (prioritize per plan)
1. **GISOGD without any ZIP/download (highest per last query):**
   - Current: URL support reduces manual save.
   - Next: Investigate portal's internal export API (POST with layer selection? Use devtools to capture). If possible, build mini-selector in UI (list common layers like "функционал", "красн"), POST to portal (or proxy via server with user token if needed), get direct bytes/GeoJSON. Fallback to data.mos.ru public datasets for overlapping layers.
   - Alternative: Embed GISOGD map (WMS) + "capture visible" or query features. Add "Публичные слои ГИС ОГД" with presets that fetch known open mirrors.
   - Code: Extend server with /api/gisogd-direct (layer params), UI dialog with checkboxes.

2. **Full CAD (Etap 2):**
   - Full fillets: Enhance applyFillet (use core fillet_polyline logic client-side or server call; support on join/offset for any lines).
   - Shared boundary: Extend beyond vertices (shared edge drag as rigid unit for coverage layers; update companions for segments).
   - Arc support: Fix TODOs (duplicate, rotate for arcs; join without full approx to points).
   - More: Fillet tool in toolbar? Radius editing live preview.

3. **UI/Adaptation (per recent):**
   - Panels: Make more (e.g., toolbar?) resizable; improve drag UX (snap, min live redraw).
   - More powerful fmt/rules: Multi-cond in table, expressions.
   - Project styles/BASE_KINDS: Full manager polish (icons, bulk delete).
   - General: Better error banners, fit on resize, dark mode if missing.

4. **Data/Etap 1+4:**
   - OSM: More categories (landuse, water), progress, clip to territory boundary, error recovery.
   - Variants: Implement branches UI (using reactive/journal).
   - Direct sources: More open data (data.mos.ru API direct fetch → layers).

5. **Other:**
   - Update tests (test_studio_core.py for new imports/fillet).
   - Packaging/offline if next phase.
   - Docs: Keep this file + roadmap updated.

**For continuation AI:**
- Start by reading this file + roadmap.md + CLAUDE.md + fixes-geometry-layout.md.
- Reproduce issues: Run server, test OSM/GISOGD buttons, resize panel, check modals.
- Use search_replace for precise edits (read first with read_file).
- Follow plan order; incremental + tested changes.
- Preserve: layer_id routing, generator styles, custom modals, coverage topology.
- Test: Manual in browser + python -m unittest for core.
- Recent context: Focus on "direct from open sources" (OSM done, GISOGD URL done → next no-ZIP at all) + CAD completeness + UI polish.

Last known issues (user-reported):
- OSM: Said "loaded" but nothing visible (fixed by coords/visible).
- ОГД: Strange data (clarified as user ZIP; now URL support).
- Scale text selectable (fixed).
- Onboard window (removed).
- Resizer inversion (fixed).

Update this MD after changes. Commit with version notes if applicable.

**Next concrete task suggestion:** Implement GISOGD direct (no link/portal step) or full fillets. Ask user for priority if unclear.
