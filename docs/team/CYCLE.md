# ГРАДО 2 team — the lead's cycle

## GitHub is the source of truth (owner 06.10.2026: «завяжи процесс на гитхабе, а не на локальных папках»)

- **Board = GitHub Issues** of `tayeela/grado-studio`. Labels: `задача`, `замечание владельца`, `ждёт владельца`,
  `в работе`, `готово к выкладке`, `альбом`, `процесс`. `gh issue list` replaces `BOARD.md` (archive before 06.10).
- **Owner's words** → an issue with label `замечание владельца`, the words quoted verbatim with the date (skill
  `owner-remark`); `OWNER.md` is the archive before 06.10. Questions to the owner → issue `ждёт владельца` with А/Б/В.
- **Work** → branch `task/<issue>-<slug>` from `team/t60`, PR into `team/t60` with `Closes #<issue>`; CI
  (`.github/workflows/grado2-release.yml`) runs the tests on every PR. Progress notes → comments on the issue
  (`gh issue comment`), not `/tmp` files; `/tmp/grado-team/` is scratch only.
- **Review** → a fresh reviewer agent comments on the PR (`gh pr review --comment`), only correctness and the owner's
  requirements. Album changes: `tools/album_check.py` report pasted into the PR, crops uploaded to the issue's
  release or the PR comment.
- **Landing («выкладывай»)** → the open PR `team/t60 → main` («Выкладка ГРАДО 2 vX») is merged on GitHub
  (`gh pr merge --merge`), then in the main checkout `git pull --ff-only` — the post-merge hook deploys the site.
- **Deliverables** (album PDF/PPTX) → a GitHub release `album-<project>-<date>` (pre-release), plus the owner's
  delivery folder and the chat. **Baselines** for album_check → release `album-baseline` (`gol.zip`, `bez.zip`).
- **Wiki** → private repo `tayeela/grado-wiki`, published on every commit that changes `docs/wiki`.
- Local folders (worktrees, `/tmp`, `~/.grado2`) are working copies and caches; nothing lives only there.

Since 06.10.2026 (Anthropic best practices, audit 06.10): one task per session — after a task is accepted and committed,
start a new session or `/clear` (state lives in BOARD, PROGRESS and the notes, not in the chat); run ГРАДО sessions
from `~/grado-studio` so the `grado-*` roles load with their tool lists and turn limits; a big new feature starts
with an interview of the owner (AskUserQuestion, options А/Б/В in plain Russian) and a spec in `docs/team/spec-*.md`,
and is built in a fresh session; the reviewer is a fresh agent and reports only gaps in correctness and the
owner's requirements; every visible change is proven with `tools/album_check.py` (skill `album-verify`).
Start every cycle with `docs/team/prompts/lead-cycle-start.md`; build every agent brief from the
templates in `docs/team/prompts/` and point agents to `docs/wiki/` pages instead of pasting file contents; the test
gate is `tools/gate.sh` (`E2E=1` for the browser scenarios). Team work lives on `team/t60` (worktree
`.claude/worktrees/team2`); the older `team/grado2` worktree is not used.

This file is the procedure of one working cycle of the ГРАДО 2 team. The lead is the session that runs it
(started by the owner: the «ГРАДО 2: команда» task in the Claude app, or the words «команда, за работу» in any
session in `~/grado-studio`). Roles are the agents in `.claude/agents/grado-*.md`. The owner-facing description
is `README.md` in this folder.

## Places

- Main checkout `~/grado-studio` (branch `main`): the owner's program runs from here. The team changes only
  `docs/team/*` here, committed path-limited: `GRADO_NO_DEPLOY=1 git commit -m "team: …" -- docs/team`.
  Never stage or commit other files of the main checkout: the owner may have work in progress there.
- Team worktree `~/grado-studio/.claude/worktrees/team2` (branch `team/t60`; a task may get its own worktree from the lead, e.g. `.claude/worktrees/t86`, branch `team/t86`): all program changes. Commits on
  this branch never deploy (the deploy hook acts only on `main`).
- Scratch for screenshots and temp projects: `/tmp/grado-team/<date>/` (create it).
- Never: port 8650, `~/Documents/ГРАДО 2`, ssh, `tools/deploy-server.sh`, the owner's QGIS folder.

## Budget

At most 3 tasks per cycle and about 15 agent calls in total; at most 3 agents at the same time, and two agents
never edit the same files at once. All role agents are Sonnet: when a role is called through `general-purpose`
(the `grado-*` agent types do not load in a session started from `~` — prefer starting the session in `~/grado-studio`, then call the roles by their own type), always pass `model: "sonnet"`. Stop early and write the report if the usage
limit is near. Read big files by line ranges (the changelog is 1800+ lines: read the top 80).

## 0. Start

1. `cd ~/grado-studio`. If `.claude/worktrees/team2` is missing: `git worktree add .claude/worktrees/team2 team/t60`
   (or `-b team/t60 … main` if the branch is missing too).
2. Bring the team branch up to date with `main` (in the worktree): `git merge --ff-only main` when possible, otherwise
   `git merge main` (not rebase: the branch is pushed, a rebase would need a forced push). On conflicts in `version.json` or `docs/grado2-changelog.md` keep main's entries and put the
   team's on top with the next version number. Never rewrite `main`.

## 1. Read

1. `docs/team/OWNER.md` — the owner's words. Every entry not yet marked `(принято <date>)` is applied first:
   a direction, a priority, a veto of a decision, a new task. Mark it `(принято <date>)` and say in the report how it
   was applied. The owner's word overrides any council decision.
2. `docs/team/DECISIONS.md` (last 10 entries), `RULE:` lines of `docs/team/PROGRESS.md`, `docs/team/BOARD.md`.

## 2. Council (only for strategic questions)

Strategic = changes the goal or the order of stages; a new big area of the program; a new window, mode or
concept the owner will see; a change of the project format or data model; a new dependency or a new data source;
dropping a feature; a disagreement between roles that blocks a task. Also when BOARD has no ready task.

Procedure:
1. Write the question in one paragraph with the facts (files, versions, what the owner said).
2. Round 1: ask 2–3 relevant roles in parallel (multi-agent costs ~15× a chat — Anthropic; scale to the question) (always `grado-product` for priorities, `grado-architect` for
   anything technical, `grado-norms` for anything about norms or data meaning, `grado-creative` for anything visible)
   for a position: proposal, reasons, risks, cost in sessions.
3. Round 2 only if the positions really disagree: send each the other positions (SendMessage to the same agents) and
   ask for a final position: agree, or one objection with a reason.
4. Decide: consensus, or the majority with the domain owner's vote counting double (norms for norms, creative for
   the look, architect for code structure). Write the entry in `DECISIONS.md`.
5. If the decision changes what the owner sees in a big way, or is irreversible, or costs money: do not act on it
   — put it in BOARD under «Ждёт владельца» with options А/Б/В and the team's recommendation first.

## 3. Work — one task at a time

For each task taken from BOARD «Очередь» (top first; mark it `[~]`):
1. Prepare (only when needed): `grado-norms` writes the domain part with a worked example and expected numbers;
   `grado-creative` writes the UI spec for a visible change; `grado-architect` splits a large task into steps.
2. Implement: the responsible role (`grado-backend`, `grado-frontend` or `grado-gis`) in the team worktree. Give it
   the task line, the prepared spec, the files, the check, and the `RULE:` lines. Route its `ASK <role>:` questions to
   that role and pass the answer back with SendMessage.
3. Check: `grado-qa` (tests, browser scenarios, screenshots of visible changes) and `grado-architect` (diff review)
   — in parallel. Then `grado-creative` signs off screenshots of visible changes, `grado-norms` signs off numbers
   and norms. A FAIL goes back to the implementer with the five-line return (UNIT, VERDICT, REASON, EVIDENCE, SCOPE).
4. Two FAILs in a row on the same task: stop it, mark `[!]`, write what was tried. Do not try a third time.
5. Accepted: bump `apps/grado2/web/version.json`, add an entry on top of `docs/grado2-changelog.md` (and UX items in
   `docs/ux/grado2-ux.md`), commit in the worktree as `grado2 vX.Y.Z: …` with the attribution line, push the branch:
   `git push origin team/t60`. Move the task to «Готово к выкладке» in BOARD with one line in plain Russian.
   A lesson that the next tasks must follow goes into PROGRESS.md as `RULE: …`.

## 4. Finish

1. Append the cycle to `PROGRESS.md`: date, tasks, what was done, how it was checked, results, what is next.
2. Commit `docs/team` on main path-limited (see Places) and `git push origin main` only if main has nothing but
   that commit ahead of origin; otherwise leave the push to the owner's next session and say so.
3. Report to the owner in Russian, plain words, no jargon, no role or hook names unless asked, 5–8 lines:
   - what the team did (as what appears on screen);
   - how it was checked;
   - what is ready to land and what they will see after «выкладывай»;
   - decisions the team made (one line each) — the owner can cancel any in `OWNER.md`;
   - what waits for the owner (А/Б/В questions), or «От вас ничего не нужно».

## Landing («выкладывай» from the owner)

Only on the owner's explicit word in chat or in `OWNER.md`.
1. In the main checkout: `git status --porcelain -- apps/grado2 core docs` must be empty; if not, stop and tell the
   owner that there is unsaved work in the program folder.
2. Bring `team/t60` up to date with `main` (step 0.2) and run the full test gate in the worktree (unit +
   `GRADO2_E2E=1`).
3. In the main checkout: `git merge --ff-only team/t60`. The post-merge hook updates grado.tailink.tech; read its
   output. «Сервер занят выгрузкой… отложено» or a failure means the server still runs the old version: say so and
   rerun `tools/deploy-server.sh` later.
4. `git push origin main`. Clear «Готово к выкладке» in BOARD, note the landing in PROGRESS.md, report to the owner:
   version, what changed on screen, server result, «перезапустите программу, чтобы увидеть».
