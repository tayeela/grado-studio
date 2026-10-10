# ГРАДО — память проекта

Loaded into every turn and every subagent: keep it short, details live in the wiki.

- **Orientation:** `INDEX.md` (map of the repository) → `docs/wiki/files.md` (question → file, places on the owner's Mac, branches) →
  `docs/wiki/INDEX.md`. Every top-level folder and every `docs/` shelf has a `README.md` (`docs/` has `INDEX.md`); nested `CLAUDE.md` files (`docs/`, `apps/grado2/`, `core/`) load when you work there.
  Read wiki pages, not big files whole. The wiki is generated from the code (`tools/wiki.py`: pre-commit hook and CI `wiki.yml` on `team/t60`
  and `main`) and mirrored to the private GitHub repo `tayeela/grado-wiki` (`tools/wiki_publish.sh`).
- **The owner's words and abbreviations (АГК, сущпол, СПРИТ, «лист 5»…): `docs/wiki/glossary.md`** — look a term up, never guess it.
- **Album work (any sheet, legend, label, line, data, export): first `docs/wiki/album-rules.md`** — the owner's rules
  from all remarks. A new owner remark goes there and to `docs/standards/albums/label-rules.md` before code.
- Tests: `tools/gate.sh` (`E2E=1` adds browser scenarios) — green on the exact tree before every commit. It also runs
  `tools/wiki.py --check` and `tools/docs_check.py` (links, paths, shelves, file headers).
  Cloud sessions: `.claude/hooks/session-start.sh` builds `~/.grado2/venv` and sets `$CHROME`, so gate and E2E run as on the Mac.
- History: `docs/grado2-changelog.md` (newest on top), `git log`; old studio and the former CLAUDE.md —
  `docs/archive/studio/session-log-archive.md`.

## GitHub is the source of truth (since 06.10.2026)
Tasks and the owner's words — GitHub Issues (`gh issue list`); work — branches and PRs into `team/t60`; landing —
merging the PR `team/t60 → main` on GitHub deploys (the server pulls `main` itself); album deliveries — releases
`album-*`; album_check baselines — release `album-baseline`; wiki — repo `tayeela/grado-wiki`. Details:
`docs/team/CYCLE.md`. The old board and the owner's notes before 06.10 are archives (`docs/archive/team/`).

## Context hygiene (Anthropic best practices)
- One task per session: after a task is accepted and committed — new session or `/clear`; state is in GitHub issues and PRs,
  `docs/team/PROGRESS.md` and the wiki. Two failed fixes of the same thing — `/clear` and a sharper prompt.
  Run ГРАДО sessions from `~/grado-studio` (project roles, skills and hooks load there).
- Compact instructions: keep the list of changed files, current version, gate/album_check commands and results,
  open owner questions (А/Б/В), the owner's latest words verbatim.

## What it is
Urban-planning workspace: existing situation → АГК → ППТ, album ППТ КРТ to PDF/PPTX. The working program is
**ГРАДО 2 (`apps/grado2`)**; old studio, wizard and calc-web are closed (code kept for core tests, do not edit). The owner is an urban
planner, not a programmer (QGIS, AutoCAD, macOS): Russian, plain words, no emoji, results described as what is on screen.
Asking the owner to do something on the Mac — always give the exact Terminal command, ready to paste (owner 06.10.2026).

## Run and test
- Owner's server: port 8650, projects in `~/Documents/ГРАДО 2` — **never test there**. Test servers and project copies —
  `docs/wiki/files.md` («Вне репозитория»), recipes — `docs/wiki/recipes.md`.
- Backend changes need a server restart; frontend — a page reload.
- `.claude/launch.json` points `grado2-test` to the main checkout; in a worktree it is edited locally and marked
  `skip-worktree` — do not commit it.

## Workflow
- Commit each step as `grado2 vX.Y.Z: …` (version in `apps/grado2/web/version.json`), one entry on top of
  `docs/grado2-changelog.md`. Stop hook: after grado2 changes, a short UX note to the owner in 2–3 lines.
- Team (since 02.10.2026): roles `.claude/agents/grado-*.md`, procedure `docs/team/CYCLE.md`, briefs `docs/team/prompts/`.
  «Команда, за работу» = one cycle; team work on `team/t60`, reaches `main` only on the owner's «выкладывай» (skill `land`).
- `main` on GitHub updates grado.tailink.tech (host `msk`) by itself: the server timer `grado-pull` pulls `main` every 5 minutes,
  checks the version and rolls back on failure (`tools/server_pull/README.md`). Never deploy from the Mac (since 08.10.2026, #73).
  Result: `/api/health` on the site, or the owner's taiLink session reads `journalctl -u grado-pull`.
- Ready libraries over hand-written code, rare exceptions (owner 08.10.2026, #69); which engine replaces which part — `docs/product/engine-map.md`
  (UI: Vue 3 + dockview + Web Awesome with a Vite build; sheet editor: own on Konva; check it before writing a mechanism): a new dependency needs wheels for
  macOS arm64 and x86_64 and Windows, a permissive license, a line in requirements and the same gate. Do not touch the owner's QGIS DB or plugin. Ask before deleting
  `~/.grado2/cache`. Portals (ГИС ОГД, ЕГКО, НСПД, Yandex, Overpass): pauses, never one portal from two places at once (parallel layers inside one job are fine), ≤ 3 retries (owner 10.10.2026, #51).
- Token budget: no Workflow fan-outs; outside the team cycle at most one Sonnet subagent at a time, read-only. Owner 07.10.2026: many
  parallel Haiku 5.5 agents are allowed for mechanical work (audits, headers, moving files); each on its own files, the lead reviews the result.
- Scripts started from git hooks must unset `GIT_DIR`/`GIT_INDEX_FILE` before running git elsewhere (RULE, 06.10.2026).
- Docs and code conventions (shelves, file headers, link checks): `docs/CLAUDE.md`, `docs/wiki/conventions.md`.

## Iron rules
1. The owner's open project is irreplaceable data — never experiment on it.
2. ЛГР styles (`core/render/grado_render/styles/*.json`) are generated: edit `tools/gen_*.py` and regenerate.
3. Coordinates: «МСК (как в QGIS)» and «система ГИС ОГД» on one datum; МСК = ОГД − `OGD_SHIFT`. Everything shown,
   typed or exported is МСК. Do not discuss or «calibrate» this scheme.
4. Server HTTP headers are ASCII only; error text in the JSON body is Russian (owner 10.10.2026, #51). Outgoing HTTPS from python.org Python needs `SSLContext(cafile=certifi.where())`;
   НСПД needs the Минцифры root CA in `~/.grado2/ca/` (or `GRADO_NSPD_CA`); never disable verification.
5. Route by layer id, never by the first layer of a kind.
6. Verify visual claims with a screenshot, not DOM numbers; verify signs against the owner's reference picture; album
   changes — a real rebuild on a project copy and a page-by-page PDF comparison.
