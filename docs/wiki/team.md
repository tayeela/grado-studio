<!-- генерируется tools/wiki.py — не править руками -->

# Команда: доска на GitHub, правила команды

С 06.10.2026 доска задач — GitHub Issues репозитория tayeela/grado-studio (метки «задача», «замечание владельца», «ждёт владельца», «в работе», «готово к выкладке»), работа — ветки и Pull Request, выкладка — слияние PR в main. Смотреть: `gh issue list`, `gh pr list`; порядок — docs/team/CYCLE.md.
Прежняя доска и указания владельца — архив до 06.10.2026: docs/archive/team/BOARD.md, docs/archive/team/OWNER.md.

## Правила команды (RULE из PROGRESS.md)

- An owner remark that names concrete wording («вл. 8», «выноска такая») gets a line in `tools/album_expect/` in the same commit as the rule in `album-rules.md`; `tools/album_check.py` runs the lint and those lines on every comparison (exit 3 on errors); a sheet without a baseline gets a full tile audit before delivery; a rule that supersedes an older one edits the older line in place (07.10.2026, audit #53: the title address, the ortho callout and a label under the legend passed unseen on the new sheets, and two lines of the rule base gave two colours for the calculated СЗЗ).
- Navigation is checked by `python3 tools/docs_check.py` (in `tools/gate.sh` and CI `docs.yml`): a document is moved with `git mv` and the checker runs at once; a new `.md` under `docs/` is named in the README of its shelf (`docs/CLAUDE.md`); every code file starts with a «what it is» header; a new top-level file or folder is named in `INDEX.md` (07.10.2026, issue #50).
- Every package with tests is in `tools/gate.sh` and in `.github/workflows/grado2-release.yml`: the tests of `core/compute`, `geom`, `layout`, `model`, `reactive`, `render` (232) were run by nobody until 07.10.2026; a new tests folder gets a line in both files the same day.
- A browser step waits for the element or text it checks (`until`), never reads it right after a window becomes visible: the collab step «A: список проектов пуст» read `hubProjList` before `loadProjects()` drew it and failed on the slow GitHub runner; T27 and T61 failed the same way on other runs of one PR (07.10.2026, issue #40).
- Album changes are verified with `tools/album_check.py` against `~/.grado2/album-baseline/{gol,bez}` (pixels and page text, crops in summary.png) — skill `album-verify`; owner remarks follow skill `owner-remark`; landing — skill `land`.
- A script started from a git hook inherits GIT_DIR/GIT_INDEX_FILE: before running git in another repository, unset them and check `git rev-parse --show-toplevel` (06.10.2026 the wiki publisher committed wiki pages over the program on team/t60; caught by `git show --stat`, branch restored to the previous commit, main untouched).
- A change to album download or label placement is accepted only after a real album rebuild with network on a fresh project copy plus a page-by-page PDF comparison with the previous baseline on two territories (T86: mocked download and spec-JSON golden both passed while sheet 4 lost roads and the station label moved onto a road).
- Cycle start = `git merge main` in the team branch → `tools/gate.sh` → read `docs/wiki/INDEX.md` and `docs/wiki/team.md`; agent briefs come from `docs/team/prompts/` and cite wiki pages instead of pasting file ranges.
- A feature that reads portal data is checked on one live (cached) object before it is accepted: unit tests on fake data passed for T82 while the real Yandex points carry the name in «Название», not `name`, and no icon was drawn.
- Any new choice bar in «Листы и альбом» closes the pending one (only one bar at a time) and old E2E steps that export on purpose pass `force` — T74's export gate broke t62/t66 until then.
- An E2E check must not assume where the territory lies: earlier steps move it (T71 expected ≥ 5 okrug districts, the run had the territory in a 4-district okrug). Compare with the data of the current territory instead.
- Owner-requested changes between cycles land on main only through a PR and the owner's «выкладывай» (no direct commits, 08.10.2026); the cycle starts by merging main into the team branch and resolving conflicts in albums.js / print_io.py by hand (cycle 21: Yandex satellite vs TileGuard, okrugMain vs simplifyAdm). Never assume the team branch is ahead of main.
- The owner's program and the site change only after the owner's word «выкладывай»; all program work happens in the team worktree `.claude/worktrees/team2` on branch `team/t60` (cloud: branch `task/<issue>-<slug>`, PR into `team/t60`).
- Before taking a status claim from a role, check the changelog entry it cites: the changelog keeps old «not done» lines under entries that were done later (Э11 was «not done» at line 1513 and done in v0.36.0).
- Social-object placement (T6) starts only after the preset constants audit (T4) and the norms spec with a fixture test (T5); plot areas are the table minimum «не менее».
- A reviewer's PASS on frontend code is not enough: a function added to a module under `(function(root){…})` is not global — call it through its exported object, and run the E2E on the combined tree before the commit (T3: `keepUid is not defined` passed the unit tests and the diff review).
- Agents that share the worktree must not run the E2E on a tree with another agent's unfinished edits; the lead runs the final gate on the combined tree.
- Norm constants are checked only against decree texts in `docs/standards/moscow-ngp` (audit of 02.10.2026); the owner sends missing texts as files.
- Starting `apps/grado2/server.py` without a port replaces the owner's server on 8650 — agents always pass an explicit port ≥ 8660 and `GRADO2_PROJECTS=<temp>`; screenshots for audits are taken from a `git archive` snapshot.
- Anything stored in the undo stack as a full copy must be dropped when its object is replaced from outside (file, parcels, another person's change) — T16 first version let Ctrl+Z bring an old boundary back over a new one.
- A frontend module must not call the API when the script loads: in hub mode there is no session yet (401) and the page breaks. Fetch on first use.
- The lead's gate prints the failing step: grep the E2E output for `STEP FAILED` and ` log: ` lines, and a FAILED gate blocks the commit even when the diff review said PASS (cycle 4: review PASS, both E2E runs failed).
- The lead runs the unit tests WITHOUT `PYTHONPATH` too (as the program starts): a module that imports a core package not on the server's own `sys.path` list passes with PYTHONPATH and fails in the real program (v0.93.1, `grado_geom`). A new core package also goes into `packaging/grado2.spec`.
- No inline `<script>` in `index.html`: the page's CSP is `script-src 'self'`; put the code into a file.
- E2E waits for anything that sends the 100 000-object test layer to the server are at least 30 s; a 5 s wait gave a false failure on a busy machine (v0.95.0).
- Agents never use `git stash` / `git checkout` of files in the shared worktree for «before» screenshots — they serve a `git archive HEAD` copy on another port.
- A hidden window can keep keyboard focus in its input: a global shortcut handler that skips inputs must still handle the shortcut that toggles that window (F1 from the help search field, v0.96.0).
- DBF text fields from portals are capped at 254 bytes (≈127 Cyrillic characters): any portal shapefile with long text needs the attribute refill (CSV/GeoJSON) — check every new document layer for cut values (v0.96.1).
- Every subagent brief repeats the ban on `pkill -f` and `git stash`/`checkout`; a brief without it is the lead's fault (cycle 19: one stray `pkill -f`).
- Portal retries live in exactly one place (the connector, with pauses); the page never repeats a failed portal request itself (T62: 3 × 2 attempts without a pause).
- Any search or relaxation that can be cut short is bounded by step counts, never by wall-clock time, and a cut-short result is cached under the same key (deterministic) — a time bound gives different sketches on different machines and an uncached partial result re-runs on every render (T6, T56).
- Any automatic rebuild of the owner's content (sheets, layers, graph) on project open is forbidden: adopt the current state as the base and rebuild only on an explicit action with a two-click confirmation (T55).
- A layer-key alias (`gisogd.X` ↔ `ogd.X`) is applied only where the user picks from the catalog; code that loads layers for albums/sheets keeps exact keys (iron rule 5) — T61 first version broke album loads.
- The owner's real projects store catalog layers as `ogd.<code>` and `egko.*`; every feature that looks up a layer by a fixed key (`gisogd.*`, `nspd.*`, `osm.*`) is silently empty on them — look up layers by role, and test on the copy of the site project (`/tmp/grado-team/transfer/bezobrazovo.server.grado2`), not only on the example.
- `test_e2e.py` prints only the last 4000 characters of a scenario's output: a step near the start of `scenarios.mjs` never shows an «ok» line in the log — a green run is the proof, not the grep.
- An external tile or data service is checked with one real request (size and a look at the tile) before it is wired in: CARTO basemaps returned HTTP 200 with an «API KEY REQUIRED» placeholder (03.10.2026).
- Reviewers never run `git stash` in the shared worktree, even «for a probe» — it reverts other agents' work under a running E2E (03.10.2026, restored by pop; that gate stayed green, so it was not repeated).
- Anything litegraph draws from a size-dependent constant (`--k`) must be stored at scale 1: titles truncated with `fitText`, node sizes, pasted/cloned nodes (`onConfigure`) — check `JSON.stringify(graph.serialize())` equal at k=1 and 7/6.
- E2E steps never compare with hard-coded dates while the program stamps the real time (`editedAt`, `builtAt`): clear or stub the stamps first — the T34 step turned red by itself after 13:07 on 03.10.2026.
- Inside a template literal passed to `p.ev`, write regexes as `/api[/]print[/]pdf/` or `\\/`: a single `\/` is unescaped to `/` and the page throws «Invalid regular expression flags».
- Keyboard activation of any menu item is tested with a real key event (`p.key("Enter")`), not `.click()`: the map's global keydown handler (cad.js) can swallow Enter/Space for new menus and buttons.
- Project files on the site (`/var/lib/grado/projects`, local mode, not hub) are edited only by the lead with the owner's word: plan first, backup to `.bak/`, atomic replace, the owner's tab closed (browser autosave would overwrite), verification, rollback path. Subagents never touch them.
- Probes of grado.tailink.tech from the Mac are unreliable (the Mac goes out through a VPN; half of the requests time out before connecting). The landing is confirmed by the deploy script's own health check («Готово: на сервере версия X»), not by curl from the Mac.

## Последние циклы

- 10.10.2026, выкладка по слову владельца («выкладывай») — v0.99.77 (PR #96 `team/t60 → main`, слияние bf729a4): окно «Свойства» (PR #95) —
  в узком окне подпись над полем (`@container` на `.pane`), разделы «Оформление / Подписи / Слой», глаз в шапке; значок слоя рисуется стилем карты
  (`LayerSwatch.vue`, `symbolStyle`); в `tools/ui_layout_check.mjs` шаг «узкое окно Свойства» 190 px. Проверено: `E2E=1 tools/gate.sh` зелёный,
  CI PR #95 и #96 зелёные. Сайт из облачной сессии не проверялся (`/api/health` отвечает 401 без входа). PR #93 — черновик, не вошёл.
- 09.10.2026, выкладка по слову владельца («Выкладывай») — v0.99.74 (PR #91 `team/t60 → main`, слияние 76cf063): шаг 1 плана (PR #90) —
  плавающие окна идут за мышью (заплатка dockview-core через patch-package), «Данные» по шагам с ходом выгрузки по слоям, «Объект» таблицей
  «Поле | Значение», окно масштаба «1 : N» со списком; проверка раскладки окон `tools/ui_layout_check.mjs` в gate (E2E) и CI. Проверено:
  `E2E=1 tools/gate.sh` зелёный, CI PR #90 и #91 зелёные. Сайт из облачной сессии не проверялся (`/api/health` отвечает 401 без входа).
