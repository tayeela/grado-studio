# ГРАДО — память проекта

Keep this file short: it is loaded into every turn and every subagent. History lives in docs:
`docs/grado2-changelog.md` (ГРАДО 2, newest on top), `docs/grado2-plan.md`, `docs/ux/grado2-ux.md`,
`docs/session-log-archive.md` (old studio and the full former CLAUDE.md), `git log`.

## What it is
Urban-planning workspace for existing-situation analysis → АГК → ППТ. The working program is
**ГРАДО 2 (`apps/grado2`)**. Old studio `apps/studio`, wizard and calc-web are closed (code kept for core tests).
User: urban planner, not a programmer, fluent in QGIS and AutoCAD, macOS. Talk in Russian, plain words,
no emoji, describe results as what appears on screen.

## Run and test
- Owner's server: `python3 apps/grado2/server.py` (port 8650, projects in `~/Documents/ГРАДО 2`). **Never test
  there.** Test only on preview `grado2-test` (port 8651, temp projects folder).
- Backend changes need a server restart; frontend needs a page reload.
- Tests before every commit (commit only after they pass on that exact tree):
  ```sh
  PYTHONPATH="core/render:core/geom:core/layout:core/compute:core/model:core/reactive:core/connectors:apps/grado2" \
    python3 -m unittest discover -s <core/connectors/tests | core/compute/tests | apps/grado2/tests> -p "test_*.py"
  GRADO2_E2E=1  # add for the headless browser scenarios in apps/grado2/tests
  ```
- `.claude/launch.json` points `grado2-test` to the main checkout; in a worktree it is edited locally and marked
  `skip-worktree` — do not commit it.

## Workflow rules
- Commit each step as `grado2 vX.Y.Z: …` (version in `apps/grado2/web/version.json`), merge ff into `main`,
  push branch and `main`. One entry per change on top of `docs/grado2-changelog.md`; UX items in `docs/ux/grado2-ux.md`.
- Stop hook: after grado2 changes do a short UX audit, tell the owner 2–3 lines.
- No new dependencies in core and apps/grado2. Do not touch the owner's QGIS DB or plugin
  (`~/Library/Application Support/QGIS`). Ask before deleting caches in `~/.grado2/cache`.
- Portals (ГИС ОГД, ЕГКО, НСПД, Yandex, Overpass): pauses, no parallel downloads, at most 3 retries.
- Token budget: no Workflow fan-outs; at most one subagent at a time (Sonnet, read-only) and only when it saves reading.

## Iron rules (still valid)
1. The owner's open project is irreplaceable data — never experiment on it.
2. ЛГР styles (`core/render/grado_render/styles/*.json`) are generated: edit `tools/gen_*.py` and regenerate.
3. Coordinates: two Moscow systems on one datum — «МСК (как в QGIS)» and «система ГИС ОГД»; МСК = ОГД − `OGD_SHIFT`.
   Everything shown/typed/exported is МСК. Do not discuss or «calibrate» this scheme.
4. Server error messages are ASCII only. Outgoing HTTPS from python.org Python needs `SSLContext(cafile=certifi.where())`.
5. Route by layer id, never by the first layer of a kind.
6. Verify visual claims with a screenshot, not DOM numbers; verify signs against the owner's reference picture.
