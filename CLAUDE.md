# ГРАДО — память проекта

Loaded into every turn and every subagent: keep it short, details live in the wiki.

- **Start with `docs/wiki/files.md`** (question → file, places on the owner's Mac, branches) and `docs/wiki/INDEX.md`.
  The wiki is generated from the code on every commit (`tools/wiki.py`) and published to the private GitHub repo
  `tayeela/grado-wiki` (`tools/wiki_publish.sh`, post-commit). Read wiki pages, not big files whole.
- **Album work (any sheet, legend, label, line, data, export): first `docs/wiki/album-rules.md`** — the owner's rules
  from all remarks. A new owner remark goes there and to `docs/standards/albums/label-rules.md` before code.
- Tests: `tools/gate.sh` (`E2E=1` adds browser scenarios) — green on the exact tree before every commit.
- History: `docs/grado2-changelog.md` (newest on top), `git log`; old studio and the former CLAUDE.md —
  `docs/session-log-archive.md`.

## What it is
Urban-planning workspace: existing situation → АГК → ППТ, album ППТ КРТ to PDF/PPTX. The working program is
**ГРАДО 2 (`apps/grado2`)**; old studio, wizard and calc-web are closed (code kept for core tests). The owner is an urban
planner, not a programmer (QGIS, AutoCAD, macOS): Russian, plain words, no emoji, results described as what is on screen.

## Run and test
- Owner's server: port 8650, projects in `~/Documents/ГРАДО 2` — **never test there**. Test servers and project copies —
  `docs/wiki/files.md` («Вне репозитория»), recipes — `docs/wiki/recipes.md`.
- Backend changes need a server restart; frontend — a page reload.
- `.claude/launch.json` points `grado2-test` to the main checkout; in a worktree it is edited locally and marked
  `skip-worktree` — do not commit it.

## Workflow
- Commit each step as `grado2 vX.Y.Z: …` (version in `apps/grado2/web/version.json`), one entry on top of
  `docs/grado2-changelog.md`. Stop hook: after grado2 changes, a short UX note to the owner in 2–3 lines.
- Team (since 02.10.2026): roles `.claude/agents/grado-*.md`, procedure `docs/team/CYCLE.md`, owner notes
  `docs/team/OWNER.md`, briefs `docs/team/prompts/`. «Команда, за работу» = one cycle; team work on `team/t60`
  (worktree `.claude/worktrees/team2`), reaches `main` only on the owner's «выкладывай» (Landing in CYCLE.md).
- `main` updates grado.tailink.tech by itself (hooks `post-commit`/`post-merge` → `tools/deploy-server.sh`); read its
  output and tell the owner; «отложено» or a failure = old version still runs, rerun later. `GRADO_NO_DEPLOY=1` skips.
- No new dependencies in core and apps/grado2. Do not touch the owner's QGIS DB or plugin. Ask before deleting
  `~/.grado2/cache`. Portals (ГИС ОГД, ЕГКО, НСПД, Yandex, Overpass): pauses, no parallel downloads, ≤ 3 retries.
- Token budget: no Workflow fan-outs; outside the team cycle at most one subagent at a time (Sonnet, read-only).
- Scripts started from git hooks must unset `GIT_DIR`/`GIT_INDEX_FILE` before running git elsewhere (RULE, 06.10.2026).

## Iron rules
1. The owner's open project is irreplaceable data — never experiment on it.
2. ЛГР styles (`core/render/grado_render/styles/*.json`) are generated: edit `tools/gen_*.py` and regenerate.
3. Coordinates: «МСК (как в QGIS)» and «система ГИС ОГД» on one datum; МСК = ОГД − `OGD_SHIFT`. Everything shown,
   typed or exported is МСК. Do not discuss or «calibrate» this scheme.
4. Server error messages are ASCII only. Outgoing HTTPS from python.org Python needs `SSLContext(cafile=certifi.where())`;
   НСПД needs the Минцифры root CA in `~/.grado2/ca/` (or `GRADO_NSPD_CA`); never disable verification.
5. Route by layer id, never by the first layer of a kind.
6. Verify visual claims with a screenshot, not DOM numbers; verify signs against the owner's reference picture; album
   changes — a real rebuild on a project copy and a page-by-page PDF comparison.
