# ГРАДО 2 — совместная работа (контракт реализации)

Status: implementation contract, 2026-09-30. Every agent codes against THIS file. If something here is impossible,
do the closest thing and write the deviation in your report; do not silently change names.

## Goal and modes
- **Local mode (default, the owner's Mac):** nothing changes. Single user, projects in `~/Documents/ГРАДО 2`,
  autosave, optional `GRADO2_TOKEN`. No hub code runs, no hub UI is shown.
- **Hub mode (cloud, grado.tailink.tech):** env `GRADO2_HUB=1` (or CLI flag `--hub`). Accounts, invite-only
  registration, projects stored on the server and shared with roles, live sync between several people editing
  the same project, presence (who is online, their cursors and selection), comments pinned to the map or to an
  object, version history with restore, activity feed. In hub mode `GRADO2_TOKEN` is ignored (accounts replace it).
- Model follows the owner's earlier decision for the old studio (`apps/studio/webhub.py`, «живая синхронизация»):
  server stores the whole project with a revision number and serialises writes; clients merge. Improvements here:
  section-level revisions, server-sent events instead of polling, feature-level 3-way merge by stable ids.
- stdlib only (no new dependencies), Russian UI texts, plain words, no emoji. Server JSON error texts in Russian are
  fine in bodies; HTTP header values ASCII only.

## Storage (hub mode) — `apps/grado2/hub.py`
Root: env `GRADO2_HUB_DIR`, default `<PROJECTS>/.hub`. Directories created with mode 0o700. All writes atomic
(tmp + os.replace) under one `threading.RLock` per Hub instance.
```
users.json        {login: {pw, salt, admin: bool, name, created, disabled: bool}}
invites.json      {code: {created, by, used_by, used_at, expires}}
sessions.json     {sha256(token): {login, created, last_seen, ua}}     # the raw token is never stored
projects/<pid>/meta.json      {id, name, owner, members: {login: "owner"|"editor"|"viewer"}, rev, sec_rev: {section: rev},
                               created, updated, updated_by}
projects/<pid>/project.grado2 the whole project JSON in the normal .grado2 format (so export/import keep working)
projects/<pid>/history/<rev>-<YYYYMMDD-HHMMSS>-<login>.grado2.gz   snapshot, at most one per 10 min per project + one
                               before every restore; keep the newest 60
projects/<pid>/comments.json  [{id, author, created, text, anchor: {lonlat:[lon,lat]} | {layer, uid}, resolved, replies:[{id, author, created, text}]}]
projects/<pid>/activity.json  last 300 entries [{t, login, action, detail}]
```
- pid: `secrets.token_hex(8)`; login regex `^[a-z0-9_.-]{3,32}$` (lowercased); display `name` ≤ 60 chars.
- Passwords: `hashlib.scrypt(pw, salt=16 random bytes, n=2**14, r=8, p=1, dklen=32)`, compare with
  `hmac.compare_digest`; min length 8. Session token `secrets.token_urlsafe(32)`, TTL 30 days sliding.
- Login throttling: 5 failures per login per 15 min, 25 per client IP per 15 min → locked (429).
- Admin bootstrap CLI: `python3 apps/grado2/hub.py adduser <login> [--admin] [--name "…"]` reads the password from
  stdin (no echo when a tty); `python3 apps/grado2/hub.py invite` prints a new invite code; `hub.py passwd <login>`,
  `hub.py list`. Uses the same GRADO2_HUB_DIR / GRADO2_PROJECTS resolution as the server.

### Roles
| action | viewer | editor | owner | admin (global) |
|---|---|---|---|---|
| open project, see presence, read comments, history list | yes | yes | yes | yes |
| push changes, add comments, resolve comments | comments only | yes | yes | yes |
| restore a history version | no | yes | yes | yes |
| rename project, share (add/remove members, change roles) | no | no | yes | yes |
| delete project | no | no | yes | yes |
| create invites, disable users, list all users | no | no | no | yes |
The last owner cannot be removed or downgraded. Team owners count as owners of the team's projects (see Teams).

## Teams (workspaces, added 2026-10-01)
Owner: «разные команды пользователей с доступами к разным проектам, как в Miro, Google Документах, Canva».
Owner's decisions 01.10.2026: new people still get an account only by an admin invite (team owners add existing
accounts by login); a new team project is edited by the whole team by default; link sharing — later, not now.

Storage
```
teams.json   {tid: {name, created, by, members: {login: "owner"|"member"}}}     # tid = secrets.token_hex(8), PID_RE
projects/<pid>/meta.json  + team: tid|null, team_access: "edit"|"view"|"none"     # absent = personal project, "edit"
```
- `teams.json` is loaded in `Hub.__init__` and re-read in `_sync` like `users.json`. Old `meta.json` without `team`
  is a personal project: read with `meta.get("team")`, `meta.get("team_access") or "edit"`. No migration file.
- Limits: `TEAM_MEMBERS_MAX = 200`, `TEAMS_PER_USER = 50` (teams a person belongs to), team name `_clean_name` ≤ 60.
- Any logged-in user may create a team and becomes its owner. Team roles: `owner` (renames the team, adds/removes
  people and changes their team role, deletes an empty team, is owner of every project of the team) and `member`.
  A team keeps at least one owner. A member may leave a team (set own role to null) unless they are its last owner.
  Global admin may do everything with every team and sees all teams (role "admin").
- A team with projects cannot be deleted (400 «в команде есть проекты: перенесите или удалите их»).

Effective project role — the single decision point `Hub._role(u, login, meta)` (instance method now):
disabled → None; global admin → "admin"; else the strongest (viewer < editor < owner) of
(a) the personal share `meta["members"].get(login)`,
(b) if `meta["team"]` is a team where `login` is a member: team owner → "owner"; team member → by `team_access`:
    "edit" → "editor", "view" → "viewer", "none" → nothing.
`_require` and the roles table above are unchanged. Personal shares work for people outside the team (guests).

Projects in teams
- `create_project(user, name, project=None, team=None, team_access="edit")`: with a team, the creator must be a member
  of it (any team role) or admin; `meta["members"] = {creator: "owner"}` as before; `meta["owner"]` = creator (the
  `PROJECTS_PER_USER` quota is still counted on the creator).
- Move between spaces / change team access: `set_project_team(user, pid, team, team_access)` — project owner role
  required (`_require(..., "owner")`); moving INTO a team requires the actor to be a member of that team (or admin).
  Moving OUT to personal (`team=None`): if no personal owner remains in `meta["members"]`, the actor becomes one.
- «Last owner» in `set_member`: owners = personal owners ∪ owners of the project's team; must stay non-empty.
- `list_projects` items gain `team` (tid|null), `team_name`, `team_access`; existing fields and role values unchanged
  (`members` stays the personal share list).

Access-change propagation: adding/removing a team member, changing a team role, changing `team_access`, moving a
project, deleting a team → for every affected project publish `{type:"members"}` and close the event streams of
people who no longer have a role there (same check as `_recheck_subs`, via `role_of`, never while holding `_live`).

HTTP (all inherit the session gate, `_foreign`, JSON Content-Type, 1 MB body limit)
- `GET /api/hub/teams` → `{teams:[{id, name, role, members:[{login,name,role}], projects:n}]}`
- `POST /api/hub/teams {name}` → `{id}` · `POST /api/hub/team/<tid> {name}` rename (team owner/admin)
- `POST /api/hub/team/<tid>/members {login, role:"owner"|"member"|null}` (team owner/admin; anyone for own null = leave)
- `POST /api/hub/team/<tid>/delete` (team owner/admin, empty team only)
- `POST /api/hub/projects {name, project?, team?, team_access?}` (team optional)
- `POST /api/hub/project/<pid>/team {team: tid|null, team_access}` (project owner)

Client (hub.js)
- «Совместные проекты» groups the list: «Личные», one group per team «Команда «…»», «Доступные мне» (shared with me
  from spaces I am not in). Creating a project asks where: «Личные» or one of my teams.
- Window «Команды» (`wTeams`, also in the account menu): my teams; create; per team rename, people with role
  (владелец команды / участник), add by login, remove, leave, delete (empty team).
- Window «Доступ»: for a team project a first row «Вся команда «…»: редактирует / смотрит / нет доступа», then «Где
  лежит проект: Личные / команда …» (owner only), then the personal list as before. One role label table in hub.js.

## Sections (the unit of sync)
The shared project is split into sections; personal state never leaves the client.
- `meta` → `{name, territory, checked, groups, views, album, graph, imports, current_order}` where `current_order`
  is the list of layer keys in draw order.
- `layer:<key>` → `{spec, data}` where `spec` = the layer entry of `collectProject().layers` (key, title, geom,
  visible, layerOpacity, open, group, style) and `data` = the entry of `collectProject().data[key]`.
- A deleted section is sent as `null`.
- **Personal, never synced:** `view` (center, zoom, basemap), `current` layer, selection, undo/redo, `dirty`,
  window layout.
- `project.grado2` on the server = `join(sections)` in the normal file format (format, version, app, name, saved_at,
  layers, data, …) so the file stays openable in local mode.

### Stable object ids
Every feature in every layer gets property `_uid` (12 hex chars from `crypto.getRandomValues`) the first time the
client sees it without one (load, draw, import, paste, portal download). `_uid` is hidden from the attribute table,
field lists and exports the same way other `_`-prefixed service fields are (check how `_edited`/`_key` are hidden and
reuse that). Duplicated/pasted features get new `_uid`s.

## Sync protocol (HTTP, all under `/api/hub/…`, JSON bodies, cookie `grado_session`)
Auth
- `POST /api/hub/login {login, password}` → 200 `{user:{login,name,admin}}` + `Set-Cookie: grado_session=<token>;
  Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000` (+ `; Secure` when `X-Forwarded-Proto: https`).
  Wrong → 401 `{error:"неверный логин или пароль"}`; throttled → 429.
- `POST /api/hub/logout` → clears cookie. `GET /api/hub/me` → `{user}` or 401.
- `POST /api/hub/register {invite, login, name, password}` → like login. `POST /api/hub/password {old, new}`.
- Admin: `GET /api/hub/users`, `POST /api/hub/invites` → `{code}`, `GET /api/hub/invites`,
  `POST /api/hub/users/<login> {disabled?, admin?, name?}`.
Projects
- `GET /api/hub/projects` → `{projects:[{id,name,owner,role,rev,updated,updated_by,members:[{login,name,role}],online:n}]}`
  (only projects where the user is a member; admin sees all with role "admin").
- `POST /api/hub/projects {name, project?}` → create (optional full .grado2 JSON to import, e.g. the local autosave
  or an uploaded file) → `{id, rev}`.
- `GET /api/hub/project/<pid>` → `{id, name, role, rev, sec_rev, sections:{...}}`.
- `POST /api/hub/project/<pid>/push {base_rev, sections:{name: value|null}, client}` (editor+):
  for each section, if `sec_rev[name] > base_rev` → conflict; if any conflict → 409
  `{rev, conflicts:{name: {value, rev}}}` and NOTHING is written; else all sections written, `rev += 1`,
  `sec_rev[name] = rev` for each, file joined and saved, activity + history snapshot rule applied, event broadcast →
  200 `{rev}`.
- `GET /api/hub/project/<pid>/sections?names=a,b` → `{rev, sec_rev, sections:{...}}` (for fetching after an event).
- `POST /api/hub/project/<pid>` `{name}` rename (owner); `DELETE`-like: `POST /api/hub/project/<pid>/delete` (owner).
- `POST /api/hub/project/<pid>/members {login, role|null}` (owner/admin).
- `GET /api/hub/project/<pid>/download` → the .grado2 file (attachment).
Live
- `GET /api/hub/project/<pid>/events` — `text/event-stream`, one per open tab. Events (JSON in `data:`):
  `{type:"rev", rev, sections:[names], by, client}` · `{type:"presence", users:[{login,name,color,client,cursor:[lon,lat]|null,
  layer, sel:[uids], t}]}` · `{type:"comments", rev_c}` · `{type:"members"}` · `{type:"deleted"}` · comment line
  `: ping` every 15 s. Header `X-Accel-Buffering: no`, `Cache-Control: no-cache`. The handler thread blocks on the hub's
  event bus (`threading.Condition`), exits when the client disconnects or the project is deleted/the user loses access.
- `POST /api/hub/project/<pid>/presence {client, cursor, layer, sel}` — at most 2/s per client; TTL 20 s; colour is
  assigned by the server per login (fixed palette of 8, stable by hash).
- Comments: `GET /api/hub/project/<pid>/comments`, `POST …/comments {text, anchor}`, `POST …/comments/<cid> {text?|resolved?}`,
  `POST …/comments/<cid>/reply {text}`, `POST …/comments/<cid>/delete` (author, owner, admin). Text ≤ 4000 chars.
- History: `GET …/history` → `[{rev, t, login, size}]`, `POST …/history/<rev>/restore` (editor+) → writes that
  snapshot as a new revision (all sections), broadcast.
- Activity: `GET …/activity` → last 300 entries.
Limits: push body ≤ 400 MB (same as project), other hub POSTs ≤ 1 MB. Every hub POST requires a valid session, the
existing Host/Origin check (`_foreign`) and — for state-changing calls — header `Content-Type: application/json`.

## Client (hub mode only)
The page learns the mode from `GET /api/health` → `{…, hub: true}`. In hub mode, before `projectStart`, the client
requires a session: no session → the hub login screen.
- `web/collab.js` (engine, no DOM except what it must touch in the app): `window.Collab = {on, pid, rev, role, …}`.
  - `split(projectObject) → {sections}` and `join(sections, personal) → projectObject` using `collectProject()` shape.
  - Keeps `base` = last agreed sections (deep-frozen JSON strings per section to save memory).
  - After each local edit (hook: `markDirty` calls `window.Collab?.touched()`), debounced 400 ms (max wait 3 s):
    compute changed sections by comparing JSON with `base` (layers: compare via the existing `jsonOf` cache so unchanged
    layers are free), push with `base_rev`. On 409: 3-way merge per conflicting section — for `layer:*` merge features
    by `_uid` (theirs wins on a property both changed; additions from both kept; deletion wins over an unchanged side,
    edit wins over deletion), spec fields last-writer-wins per field; for `meta` merge per top-level key (graph,
    album, views…: theirs wins if both changed, and toast «Ваши правки в … совпали с правками <name>: оставлена их
    версия»). Re-push. At most 5 retries, then full reload of the project with a toast.
  - On SSE `rev` from another client: fetch changed sections, merge with local un-pushed changes (same 3-way), apply
    **without** `clearProject`: per layer `setLayerData(key, fc, true)` keeping the local selection when the selected
    `_uid`s still exist; meta sections through small appliers (territory, groups, views, album, graph.configure while
    keeping the canvas offset). Applying remote data must not mark the project dirty or trigger a push (flag
    `Collab.applying`).
  - Local mode: `Collab.on === false`, every hook is a no-op.
  - Autosave, «Сохранить» (Ctrl+S) and the «Проекты» window in hub mode: Ctrl+S just forces an immediate push and
    toasts «Сохранено на сервере»; the local autosave POST is not used.
- `web/hub.js` + `web/hub.css` (all hub UI; loaded after project.js; does nothing in local mode):
  - Login / register-by-invite screen (full-page overlay, same look as `login.html`).
  - Top-bar block: project name, avatars of people online (initials in their colour), sync status dot
    («сохранено», «отправляю…», «нет связи — правки сохранятся, когда связь вернётся»), account menu (name, change
    password, sign out, for admins «Пользователи и приглашения»).
  - Window «Совместные проекты» (`wHubProjects`): list with role, who edited last and when, who is online; create
    new, create from the current local work, upload .grado2, open, rename, delete (owner), download.
  - Window «Доступ» (`wShare`): members with roles, add by login, change role, remove; owner-only controls.
  - Window «Комментарии» (`wComments`): list, filter open/resolved, add comment by clicking the map (tool «Комментарий»)
    or on the selected object; pins on the map (OpenLayers vector layer added to every map in `ALLMAPS`), replies,
    resolve, jump to pin.
  - Window «История» (`wHistory`): versions with author and time, «Вернуть эту версию» (editor+), activity feed tab.
  - Remote presence on the map: a coloured cursor with the person's name, and a coloured outline of the objects they
    have selected (vector overlay layer per map); layer tree shows a small coloured dot on layers someone is editing.
  - Viewer role: editing tools disabled with the hint «Только просмотр: попросите владельца дать права на правку».
- Presence send: pointer position throttled to 2/s, selection and current layer on change.

## Server integration — `apps/grado2/server.py`
- `HUB = Hub(root) if hub mode else None` created in `main()`/module init from env; `/api/health` gains `hub: bool`.
- In hub mode, the gate: everything except `/api/health`, static files needed by the login overlay (index.html, *.js,
  *.css, vendor/, styles/ are static and public — they hold no data), `POST /api/hub/login`, `POST /api/hub/register`
  requires a valid session → else 401 JSON. Existing data endpoints (`/api/fetch`, `/api/print/*`, `/api/export/*`,
  `/api/import/*`, ogd_all, fgistp …) require any logged-in user. The local projects endpoints `/api/projects`,
  `/api/project` are disabled in hub mode (403 «в совместном режиме проекты хранятся на сервере: окно «Совместные
  проекты»»).
- SSE handler: must not hold the global request timeout: set `self.connection.settimeout(None)` for the stream and
  rely on heartbeats + write errors to exit.
- Deployment: systemd unit on grado.tailink.tech gets `Environment=GRADO2_HUB=1` — done by the owner/ops later,
  not by code agents.

## Tests
- `apps/grado2/tests/test_hub.py` — unit tests of hub.py (accounts, throttling, roles, push/conflict, history,
  comments, events bus, presence TTL).
- `apps/grado2/tests/test_server.py` — class `HubHttp`: server in hub mode on a temp dir: login, cookie flags, 401
  without session, push/409, SSE receives a `rev` event from another client, viewer cannot push, local endpoints 403.
- `apps/grado2/tests/collab_test.js` (node, like `cadcore_test.js`, run from `test_*.py` wrapper if that is how the
  existing js tests run) — split/join round trip, 3-way merge cases.
- `apps/grado2/tests/e2e/collab_scenarios.mjs` — two browser sessions editing one project (see driver.mjs).
