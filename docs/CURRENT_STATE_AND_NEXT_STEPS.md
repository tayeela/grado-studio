# GRADO Studio — Current State and Continuation Guide

> **Updated 2026-07-14.** This file was stale for ~2 months of in-repo development (last full
> rewrite referenced v0.42–0.53; the project is now at **v0.9.0-beta.40**, commit `2c4b32d`).
> Two independent work tracks landed since: this session's own Claude track (redesign cat-over,
> dialog audit, label settings) and a large ChatGPT/Codex track (packaging, cloud/Pages deploy,
> autosave/collab hardening, regulatory profile). Both are folded into the authoritative,
> Russian-language project memory — **read that first, this file is a compact English pointer**:

**Read in this order:**
1. `CLAUDE.md` (repo root) — auto-loaded every session, has the iron rules + current-state summary.
2. `docs/session-log-archive.md` — full diagnosis/verification narrative for every change up to
   2026-07-14 (git log for the ChatGPT/Codex commits is mostly one-line subjects with no body —
   this archive is the ONLY place with root-cause/testing detail for that track).
3. `docs/roadmap.md` — forward-looking plan by stage (etap), strikethrough = done.
4. `git log --oneline` — commit-level detail going forward.

## Project Overview
- **Main app:** `apps/studio/` — Python server (`server.py`) + web frontend
  (`web/app.js` + `web/app-{transform,snap,data,style-ui,attr,import}.js` + `index.html` +
  `redesign/{shell,studio2}.css` + `tokens.css`). `index.html` is the **current** UI (post
  redesign cat-over); `index-classic.html` is the old UI, kept as a working fallback.
- **Core:** CAD drawing on canvas (points/polylines/polygons/arcs/circles), layers with roles,
  styles (LGR library + project overrides), TEP (technical-economic indicators) computed inside
  the development-territory boundary, album/PDF/DXF export, `.grado` (GeoPackage) roundtrip.
- **Distribution (new since last rewrite of this file):** Windows installer + portable ZIP built
  by CI (`.github/workflows/windows-release.yml`) on tag push, macOS DMG (`packaging/build_macos.py`,
  py2app + optional codesign/notarize), Docker cloud deploy (`Dockerfile`, `server.py --cloud` /
  `GRADO_CLOUD=1`, `docs/CLOUD_DEPLOY.md`), and a no-server browser edition on GitHub Pages
  (`pages-adapter.js` + `pages-core.js` + `crs.js`, IndexedDB-backed, missing server-only features
  by design — see CLAUDE.md "Дистрибуция" section for the honest capability split).
- **Iron rules (see CLAUDE.md for the full, current list — do not rely on the list below, it may
  drift):** tests are a commit gate (`unittest`, 350 tests across 5 modules as of this writing);
  generator-only LGR styles (`tools/gen_moscow_lgr.py`); route by `layer_id` never by `kind`;
  never test live on the user's real project (stub `persist` first); canvas needs `flex-basis:0` +
  absolute wrapper inside flex containers; server errors must be ASCII-only.

## Plan Status
Nearly everything this file used to list as "Open Issues / Next Steps" (GISOGD direct import,
full fillets, shared-boundary editing, variants UI, project styles manager, rules with operators,
resizable panel, arc support in transforms) is **done** — see `docs/roadmap.md` (strikethrough
items) and `CLAUDE.md`'s "Текущее состояние" section for what each one actually does now.

### Known remaining gaps (verified honest, not guessed)
- Fillet parametrics are lost once JS linearizes a polyline into points (duplicates the core
  `path.py` model) — a re-unification, not yet done.
- Snapping spatial index (`app-snap.js`) isn't wired into every operation yet.
- MSK calibration is UTM37N/Snyder only; no per-zone MSK calibration UI.
- Arbitrary-intersection noding exists only in the Python core, not mirrored in JS.
- `srcKey`-based dedup for repeated NSPD/OSM/GISOGD imports doesn't survive a `.grado` round-trip.
- Moscow city layers (`data.mos.ru`) are unreachable from this environment (domain blocked/API
  key required) — not implemented, and not a bug in the import code.
- No git tags/CHANGELOG beyond a single `v0.9.0-beta.8` tag (used only for the Windows CI release
  pattern `v*`). Version history lives in `docs/session-log-archive.md` + `docs/audits/` + git log.

## How to Run / Verify
```sh
cd apps/studio && python3 server.py          # http://localhost:8643, local mode
python3 server.py --hub                       # + collaboration (see CLAUDE.md)
python3 server.py --cloud                     # or GRADO_CLOUD=1, hardened for public exposure
```
Backend changes (`server.py`/`studio_core.py`/`core/render/**`/`styles/*.json`) need a preview
restart — no hot reload. Frontend changes reload normally.

Test gate (must pass before any commit):
```sh
PYTHONPATH="apps/studio:apps/wizard:core/render:core/geom:core/layout:core/compute:core/model:core/reactive:core/connectors" \
  python3 -m unittest discover -s <module/tests> -p "test_*.py"
```
Run for each of: `apps/studio/tests`, `core/render/tests`, `core/connectors/tests`,
`core/model/tests`, `core/compute/tests` (229+38+32+32+19 = 350 tests, all green as of `2c4b32d`).

**Before testing anything interactively:** stub `window.persist = () => {}` in the browser console
first — the user's live project in that browser tab is irreplaceable data; autosave writes
synchronously on every change. Reload afterward to discard the test session's state.

## For a Continuation AI
- Don't re-derive project history from scratch — `docs/session-log-archive.md` has the "why"
  behind almost every non-obvious decision (root causes of bugs, what was verified and how).
- This project is worked on by multiple AI sessions/accounts in parallel on the same working
  directory — re-read a file immediately before editing it if an `old_string` match fails; it may
  have changed since you last read it.
- User is an urban planner, not a programmer, works in Russian, no jargon in responses — explain
  results in terms of what they'll see on screen, not implementation details.
- Update `CLAUDE.md`'s "Правки этой сессии" section (append new entries at the top) after any
  non-trivial change, with root cause + what was verified. Consolidate into the main snapshot
  (and archive the log) only when it grows large again — not on every session.
