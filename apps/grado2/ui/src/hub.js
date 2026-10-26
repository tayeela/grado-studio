/* ГРАДО 2 · совместная работа в новом интерфейсе: вход, проекты на сервере, доступ, команды, комментарии, история,
   пользователи (администратор), присутствие. Перенос web/hub.js без разметки: состояние `hub` и действия; окна —
   panels/HubLogin.vue, HubBar.vue, HubWindows.vue, CommentsPanel.vue; метки на карте — hubmap.js. Движок правок — collab.js.
   Работает только на общем сервере (/api/health hub: true); на своём компьютере ничего не показывает. */
import { reactive } from "vue";
import * as Collab from "./collab.js";
import { currentId, winApi } from "./store.js";
import { hooks, notice, shared } from "./project.js";
import { sel } from "./features.js";

export const ROLE = { owner: "владелец", editor: "правка", viewer: "просмотр", admin: "администратор" };
export const TROLE = { owner: "владелец команды", member: "участник", admin: "администратор" };
export const TACC = { edit: "вся команда правит", view: "вся команда смотрит", none: "только приглашённые" };
export const LINKR = { "": "выключен", viewer: "по ссылке смотрят", editor: "по ссылке правят" };
export const ACT = { create: "создал проект", push: "изменил проект", edit: "изменил проект", restore: "вернул версию", comment: "оставил комментарий", reply: "ответил на комментарий",
  resolve: "отметил комментарий решённым", reopen: "вернул комментарий в работу", member: "изменил доступ", rename: "переименовал проект", import: "загрузил файл" };
export const SYNC = {
  saved: ["сохранено", "Все правки сохранены на сервере"], sending: ["отправляю…", "Правки отправляются на сервер"],
  offline: ["нет связи", "Нет связи — правки сохранятся, когда связь вернётся"], conflict: ["объединяю…", "Ваши правки и правки коллег объединяются"],
  readonly: ["только просмотр", "У вас права только на просмотр: правки не отправляются"],
  full: ["хранилище заполнено", "На сервере нет места: правки остаются на экране, но не сохранены"],
};

const lsGet = k => { try { return localStorage.getItem(k); } catch { return null; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch { /* частный режим */ } };
export const hub = reactive({
  me: null, login: { open: false, msg: "", guest: false, tg: false }, pid: null, name: "", role: null, members: [], projects: [], teams: null, names: {}, others: [],
  comments: [], cFilter: "open", cSel: null, draft: null, cMode: false, hist: null, adm: null, newCode: null, link: null,
  win: "", q: lsGet("grado2.hub.q") || "", ord: lsGet("grado2.hub.order") === "name" ? "name" : "recent", album: lsGet("grado2.hub.album") === "1",
});
export const C = Collab.C;
export const setPref = (k, v) => { hub[k] = v; lsSet({ q: "grado2.hub.q", ord: "grado2.hub.order", album: "grado2.hub.album" }[k], k === "album" ? (v ? "1" : "0") : v); };

/* ---- подписи ---- */
const two = n => String(n).padStart(2, "0");
export const toMs = v => typeof v === "number" ? (v < 1e11 ? v * 1000 : v) : Date.parse(v) || 0;
export function when(v) {
  const t = toMs(v); if (!t) return "—";
  const d = new Date(t), now = new Date(), s = (now - d) / 1000, hm = `${two(d.getHours())}:${two(d.getMinutes())}`;
  if (s < 60) return "только что"; if (s < 3600) return `${Math.floor(s / 60)} мин назад`;
  const day = x => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime(), dd = Math.round((day(now) - day(d)) / 864e5);
  return dd === 0 ? "сегодня, " + hm : dd === 1 ? "вчера, " + hm : `${two(d.getDate())}.${two(d.getMonth() + 1)}.${d.getFullYear()}, ${hm}`;
}
export const size = b => b > 1e6 ? (b / 1e6).toFixed(1).replace(".", ",") + " МБ" : Math.max(1, Math.round(b / 1e3)) + " КБ";
export const plural = (n, [a, b, c]) => { const m = Math.abs(n) % 100, k = m % 10; return m > 10 && m < 20 ? c : k === 1 ? a : k > 1 && k < 5 ? b : c; };
export const uname = l => hub.names[l] || l || "—";
export const initials = (name, login) => { const w = String(name || login || "?").trim().split(/\s+/); return (w.length > 1 ? w[0][0] + w[1][0] : w[0].slice(0, 2)).toUpperCase(); };
export const safeColor = c => /^#[0-9a-f]{6}$/i.test(c || "") ? c : "#7a7a7a";
export const ink = c => { const n = parseInt(c.slice(1), 16), l = (.299 * (n >> 16) + .587 * (n >> 8 & 255) + .114 * (n & 255)) / 255; return l > .62 ? "#111" : "#fff"; };
const list = (r, key) => Array.isArray(r) ? r : Array.isArray(r?.[key]) ? r[key] : r?.[key] && typeof r[key] === "object" ? Object.entries(r[key]).map(([k, v]) => ({ login: k, code: k, ...v })) : [];
export const myRole = () => C.role || hub.role || (hub.me?.admin ? "admin" : null);
export const canEdit = r => r === "owner" || r === "editor" || r === "admin";
export const isOwner = r => r === "owner" || r === "admin";
export const viewer = () => !!hub.pid && myRole() === "viewer";
const toast = t => { notice.value = t; };

/* запрос к серверу: есть тело — POST, нет — GET; 401 — снова экран входа */
export async function api(path, body) {
  let r;
  try { r = await fetch("/api/hub/" + path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); }
  catch { throw new Error("нет связи с сервером"); }
  let j = null; try { j = await r.json(); } catch { /* без тела */ }
  if (r.status === 401 && !/^(login|register|me|password)$/.test(path)) { sessionLost(); throw Object.assign(new Error("нужно войти заново"), { status: 401 }); }
  if (!r.ok) throw Object.assign(new Error(j?.error || "ошибка сервера " + r.status), { status: r.status, guest: !!j?.guest, tg: !!j?.tg });
  return j;
}
export const fail = pre => e => { if (e.status !== 401) toast((pre ? pre + ": " : "") + e.message); };

/* ================= вход ================= */
let loginRes = null;
function askLogin(msg) { return new Promise(res => { const old = loginRes; loginRes = u => { old?.(u); res(u); }; hub.login.open = true; hub.login.msg = msg || ""; }); }
export async function submitLogin(f) {
  const login = f.login.trim().toLowerCase(), pw = f.pw, reg = f.mode === "reg", msg = t => { hub.login.msg = t; };
  if (!login || !pw) return msg("Введите логин и пароль.");
  if (reg) {
    if (!f.invite.trim()) return msg("Введите код приглашения: его выдаёт администратор.");
    if (!/^[a-z0-9_.-]{3,32}$/.test(login)) return msg("Логин: от 3 до 32 знаков — латинские буквы, цифры, точка, дефис, подчёркивание.");
    if (pw.length < 8) return msg("Пароль должен быть не короче 8 знаков.");
    if (pw !== f.pw2) return msg("Пароли не совпадают.");
  }
  msg("");
  try {
    const r = await api(reg ? "register" : "login", reg ? { invite: f.invite.trim(), login, name: f.name.trim() || login, password: pw } : { login, password: pw });
    loggedIn(r.user); return true;
  } catch (err) { msg(err.message); return false; }
}
/* вход через Telegram: сервер уводит на oauth.telegram.org и возвращает сюда с сессией или с #tg=код ошибки */
export function tgLogin(invite) { location.href = "/api/hub/tg/start" + (invite ? "?invite=" + encodeURIComponent(invite) : ""); }
export function tgBind() { location.href = "/api/hub/tg/start?bind=1"; }
const TG_MSG = {
  unknown: "Этот Telegram сайту не знаком. Попросите у администратора код приглашения и войдите через Telegram на вкладке «Регистрация по приглашению».",
  invite: "Код приглашения не найден, просрочен или уже использован.", taken: "Этот Telegram уже привязан к другой учётной записи.",
  disabled: "Учётная запись отключена администратором.", denied: "Вход через Telegram отменён.", expired: "Вход через Telegram занял больше 10 минут. Попробуйте ещё раз.",
  state: "Вход через Telegram прервался. Попробуйте ещё раз.", token: "Telegram не подтвердил вход. Попробуйте ещё раз.",
  net: "Сервер не смог связаться с Telegram. Попробуйте через минуту.", busy: "Слишком много попыток. Повторите позже.",
  off: "Вход через Telegram на этом сервере не настроен.", fail: "Вход через Telegram не удался."
};
function grabTg() {
  const parts = location.hash.replace(/^#/, "").split("&").filter(Boolean), keep = [];
  let code = null; parts.forEach(x => { const m = /^tg=(\w+)$/.exec(x); if (m) code = m[1]; else keep.push(x); });
  if (code) try { history.replaceState(null, "", location.pathname + location.search + (keep.length ? "#" + keep.join("&") : "")); } catch { /* не важно */ }
  return code;
}
export async function guestLogin() {
  try { loggedIn((await api("guest", {})).user); } catch (err) { hub.login.msg = err.message; }
}
function loggedIn(u) {
  if (hub.me && u.login !== hub.me.login) { location.reload(); return; }      // другой человек за тем же компьютером: чужих данных на экране не оставляем
  hub.login.open = false;
  const res = loginRes; loginRes = null; res?.(u);
}
function sessionLost() {
  if (hub.login.open) return;
  askLogin("Вход закончился. Войдите снова — несохранённые правки остаются на экране и уйдут на сервер.").then(u => { enter(u, true); Collab.resume(); loadProjects(); });
}
let inited = null;
function enter(user, again) {
  hub.me = user; hub.names[user.login] = user.name || user.login;
  if (inited !== user.login) { inited = user.login; Collab.init(user); }
  if (again) return;
  if (getJoin()) { doJoin().then(ok => { if (!ok) startPage(); }); return; }
  startPage();
}
function startPage() { const m = /[#&]p=([\w-]+)/.exec(location.hash); if (m) openProject(m[1]); else openWin("projects"); }

/* ---- вход по ссылке #join=… ---- */
let joinTok = null;
const JKEY = "grado2.join";
function grabJoin() {
  const parts = location.hash.replace(/^#/, "").split("&").filter(Boolean), keep = [];
  let tok = null; parts.forEach(x => { const m = /^join=([\w-]+)$/.exec(x); if (m) tok = m[1]; else keep.push(x); });
  if (!tok) return false;
  joinTok = tok; try { sessionStorage.setItem(JKEY, tok); } catch { /* частный режим */ }
  try { history.replaceState(null, "", location.pathname + location.search + (keep.length ? "#" + keep.join("&") : "")); } catch { /* не важно */ }
  return true;
}
function getJoin() { if (joinTok) return joinTok; try { return sessionStorage.getItem(JKEY) || null; } catch { return null; } }
function clearJoin() { joinTok = null; try { sessionStorage.removeItem(JKEY); } catch { /* частный режим */ } }
async function doJoin() {
  const tok = getJoin(); if (!tok) return false;
  let r; try { r = await api("join", { token: tok }); } catch (e) { if (e.status === 400 || e.status === 404) clearJoin(); fail()(e); return false; }
  clearJoin();
  try { await openProject(r.id, r.name); } catch (e) { fail()(e); return false; }
  toast(`Вы открыли проект по ссылке: ${ROLE[r.role] || r.role}`); return true;
}

/* ================= проекты ================= */
export async function openProject(pid, name) {
  try { await Collab.open(pid); } catch (e) { return fail("Проект не открылся")(e); }
  hub.pid = pid; hub.role = C.role || hub.role; if (name) hub.name = name; hub.comments = []; hub.cSel = null; hub.draft = null; hub.hist = null; hub.link = null;
  try { history.replaceState(null, "", "#p=" + pid); } catch { /* не важно */ }
  if (hub.win === "projects") hub.win = "";
  await refreshMeta(); loadComments();
  if (hub.win === "share") loadLink(); if (hub.win === "history") loadHistory();
}
function closedProject(text) {
  Object.assign(hub, { pid: null, name: "", members: [], comments: [], others: [], draft: null, cSel: null, cMode: false });
  try { history.replaceState(null, "", location.pathname + location.search); } catch { /* не важно */ }
  if (text) toast(text);
  openWin("projects");
}
export async function loadProjects() {
  const teams = !hub.teams || ["projects", "teams", "share"].includes(hub.win);
  try { const [r] = await Promise.all([api("projects"), teams ? loadTeams() : null]); hub.projects = r.projects || []; } catch (e) { fail("Список проектов")(e); return; }
  hub.projects.forEach(p => (p.members || []).forEach(m => { hub.names[m.login] = m.name || m.login; }));
}
export async function loadTeams(loud) {
  try { hub.teams = (await api("teams")).teams || []; hub.teams.forEach(t => t.members.forEach(m => { hub.names[m.login] = m.name || m.login; })); }
  catch (e) { hub.teams ||= []; if (loud) fail("Команды")(e); }
}
export const myTeam = tid => !!tid && (hub.teams || []).some(t => t.id === tid);
export async function refreshMeta() {
  await loadProjects(); const p = hub.projects.find(x => x.id === hub.pid);
  if (p) { hub.name = p.name; hub.members = p.members || []; hub.role = p.role; }
}
const norm = t => String(t || "").toLowerCase().replace(/ё/g, "е").trim();
const teamName = p => p.team_name || (hub.teams || []).find(t => t.id === p.team)?.name || "";
/* группы списка: «Избранное», «Личные», по одной на мою команду, «Доступные мне»; пустые не показываются */
export function projGroups() {
  const f = norm(hub.q), hit = p => (!hub.album || +p.album_n > 0) && (!f || norm(p.name).includes(f) || norm(teamName(p)).includes(f));
  const rows = hub.projects.filter(hit).sort(hub.ord === "name" ? (a, b) => String(a.name).localeCompare(String(b.name), "ru") : (a, b) => toMs(b.updated) - toMs(a.updated)), g = [];
  const add = (title, r, fav) => { if (r.length) g.push({ title, rows: r, fav }); };
  add("Избранное", rows.filter(p => p.star), true);
  add("Личные", rows.filter(p => !p.team));
  (hub.teams || []).forEach(t => add(`Команда «${t.name}»`, rows.filter(p => p.team === t.id)));
  add("Доступные мне", rows.filter(p => p.team && !myTeam(p.team)));
  return g;
}
export async function createProject(body, okText) {
  try {
    const r = await api("projects", body);
    await loadProjects(); toast(okText || `Создан проект «${body.name}»`);
    if (C.pid !== r.id) await openProject(r.id, body.name); else { hub.pid = r.id; hub.name = body.name; await refreshMeta(); hub.win = ""; }
    return true;
  } catch (e) { fail("Проект не создан")(e); return false; }
}
export async function shareLocal(name, team) {
  try {
    const r = await Collab.createFromLocal(name), pid = r?.id || C.pid;
    if (team && pid) { try { await api(`project/${encodeURIComponent(pid)}/team`, { team, team_access: "edit" }); } catch (e) { fail("Проект создан, но не перенесён в команду")(e); } }
    await loadProjects();
    if (pid && C.pid !== pid) await openProject(pid, name); else { hub.pid = C.pid; hub.name = name; try { history.replaceState(null, "", "#p=" + hub.pid); } catch { /* не важно */ } await refreshMeta(); loadComments(); hub.win = ""; }
    toast(`Текущая работа стала общим проектом «${name}»`); return true;
  } catch (e) { fail("Не удалось сделать работу общей")(e); return false; }
}
export async function copyProject(id, name, team) {
  const body = { name }; if (team) body.team = team;
  try { const r = await api(`project/${encodeURIComponent(id)}/copy`, body); await loadProjects(); toast(`Создана копия «${name}»`); await openProject(r.id, name); return true; }
  catch (e) { fail("Копия не создана")(e); return false; }
}
export async function starProject(p) {
  const on = !p.star;
  try { const r = await api(`project/${encodeURIComponent(p.id)}/star`, { on }); p.star = typeof r?.star === "boolean" ? r.star : on; } catch (e) { fail("Избранное не изменено")(e); }
}
export async function renameProject(id, name) {
  try { await api("project/" + encodeURIComponent(id), { name }); if (id === hub.pid) hub.name = name; toast("Проект переименован"); await refreshMeta(); } catch (e) { fail("Не переименован")(e); }
}
export async function deleteProject(p) {
  try { await api(`project/${encodeURIComponent(p.id)}/delete`, {}); toast(`Проект «${p.name}» удалён`); if (p.id === hub.pid) { Collab.close(); closedProject(); } loadProjects(); } catch (e) { fail("Проект не удалён")(e); }
}
export function downloadShared(p) { const a = document.createElement("a"); a.href = `/api/hub/project/${encodeURIComponent(p.id)}/download`; a.download = p.name + ".grado2"; document.body.append(a); a.click(); a.remove(); }

/* ================= доступ ================= */
export async function loadLink() {
  const pid = hub.pid; if (!pid || !isOwner(myRole())) return;
  try { const r = await api(`project/${encodeURIComponent(pid)}/link`); if (pid === hub.pid) hub.link = { pid, link: r?.link || null, users: r?.users || [] }; }
  catch (e) { if (pid === hub.pid) hub.link = { pid, link: null, users: [], err: true }; fail("Доступ по ссылке")(e); }
}
export async function setLink(body, ok) {
  const pid = hub.pid;
  try { const r = await api(`project/${encodeURIComponent(pid)}/link`, body); hub.link = { pid, link: r?.link || null, users: r?.users || [] }; if (ok) toast(ok); refreshMeta(); }
  catch (e) { fail("Ссылка не изменена")(e); loadLink(); }
}
export const linkUrl = t => `${location.origin}${location.pathname}#join=${t}`;
export async function setMember(login, role) { try { await api(`project/${encodeURIComponent(hub.pid)}/members`, { login, role }); } catch (e) { fail("Доступ не изменён")(e); } await refreshMeta(); }
export async function setTeam(team, acc, ok) { try { await api(`project/${encodeURIComponent(hub.pid)}/team`, { team, team_access: acc }); toast(ok); } catch (e) { fail("Доступ не изменён")(e); } await refreshMeta(); }

/* ================= команды ================= */
export async function teamAct(path, data, ok, pre) { try { await api(path, data); await refreshMeta(); await loadTeams(); if (ok) toast(ok); } catch (e) { fail(pre)(e); await refreshMeta(); } }
export const tp = (tid, s) => `team/${encodeURIComponent(tid)}${s || ""}`;

/* ================= комментарии ================= */
export const sortedComments = () => [...hub.comments].sort((a, b) => toMs(a.created) - toMs(b.created));
export const openComments = () => hub.comments.filter(c => !c.resolved).length;
export async function loadComments() {
  if (!hub.pid) return;
  try { hub.comments = list(await api(`project/${encodeURIComponent(hub.pid)}/comments`), "comments"); } catch (e) { fail("Комментарии")(e); return; }
  hub.comments.forEach(c => { if (c.author && !hub.names[c.author]) hub.names[c.author] = c.author; });
}
const cpath = s => `project/${encodeURIComponent(hub.pid)}/comments${s || ""}`;
export async function sendComment(text) {
  if (!hub.draft) return false;
  try { await api(cpath(), { text, anchor: hub.draft.anchor }); hub.draft = null; hub.cMode = false; await loadComments(); return true; }
  catch (e) { fail("Комментарий не отправлен")(e); return false; }
}
export async function commentAct(act, c, text) {
  try {
    if (act === "reply") await api(cpath(`/${encodeURIComponent(c.id)}/reply`), { text });
    else if (act === "resolve") await api(cpath(`/${encodeURIComponent(c.id)}`), { resolved: !c.resolved });
    else if (act === "delete") { await api(cpath(`/${encodeURIComponent(c.id)}/delete`), {}); if (hub.cSel === c.id) hub.cSel = null; }
    await loadComments(); return true;
  } catch (e) { fail("Комментарий")(e); return false; }
}
/* комментарий к выбранному объекту: слой и номер `_uid` (метка встаёт на объект и ходит вместе с ним) */
export function commentSelected() {
  const s = sel[0]; if (!s) return toast("Сначала выберите объект на карте");
  hub.cMode = false; hub.draft = { anchor: { layer: s.key, uid: s.uid } }; winApi.open("comments");
}
export function setCMode(on) {
  on = !!on && !!hub.pid; if (on === hub.cMode) return; hub.cMode = on;
  toast(on ? "Комментарий: щёлкните по карте там, где нужна метка. Esc — отмена" : "");
}

/* ================= история ================= */
export async function loadHistory() {
  if (!hub.pid) return; const p = encodeURIComponent(hub.pid);
  try { const [v, a] = await Promise.all([api(`project/${p}/history`), api(`project/${p}/activity`)]); hub.hist = { ver: list(v, "history"), act: list(a, "activity") }; }
  catch (e) { fail("История")(e); }
}
export async function restore(rev) {
  try { await api(`project/${encodeURIComponent(hub.pid)}/history/${encodeURIComponent(rev)}/restore`, {}); toast(`Версия № ${rev} возвращена. Перед этим текущая работа сохранена в истории`); await loadHistory(); }
  catch (e) { fail("Версия не возвращена")(e); }
}

/* ================= пользователи и приглашения (администратор) ================= */
export async function loadAdmin() {
  try { const [u, i] = await Promise.all([api("users"), api("invites")]); hub.adm = { users: list(u, "users"), inv: list(i, "invites") }; hub.adm.users.forEach(x => { hub.names[x.login] = x.name || x.login; }); }
  catch (e) { fail("Пользователи")(e); }
}
export async function newInvite() { try { hub.newCode = (await api("invites", {})).code; await loadAdmin(); } catch (e) { fail("Не получилось")(e); } }
export async function toggleUser(u) { try { await api("users/" + encodeURIComponent(u.login), { disabled: !u.disabled }); await loadAdmin(); } catch (e) { fail("Не получилось")(e); } }

/* ================= учётная запись ================= */
export async function changePassword(old, nw) { await api("password", { old, new: nw }); toast("Пароль изменён"); }
export async function logout() {
  try { await Collab.flush(); } catch { /* связи нет — правки останутся в браузере до выхода */ }
  clearJoin();
  try { await api("logout", {}); } catch { /* уже вышли */ }
  try { history.replaceState(null, "", location.pathname + location.search); } catch { /* не важно */ }
  location.reload();
}

/* ================= окна ================= */
export function openWin(w) {
  hub.win = w;
  if (w === "projects") loadProjects();
  else if (w === "share") { refreshMeta(); loadLink(); }
  else if (w === "teams") loadTeams(true);
  else if (w === "history") { hub.hist = null; loadHistory(); }
  else if (w === "admin") { hub.newCode = null; hub.adm = null; loadAdmin(); }
}

/* ================= присутствие: что отправляем ================= */
export const pres = { cursor: null, dirty: false, sig: "", t: 0 };
function presenceTick() {
  if (!hub.pid || !hub.me) return;
  const s = sel.map(x => x.uid).filter(Boolean).slice(0, 200), layer = currentId.value || null, sig = layer + "|" + s.join(","), now = Date.now();
  if (pres.dirty || sig !== pres.sig || now - pres.t > 10000) { pres.dirty = false; pres.sig = sig; pres.t = now; Collab.presence({ cursor: pres.cursor, layer, sel: s }); }
}

/* ================= наблюдатель: клавиши правки не действуют ================= */
let hintAt = 0;
function keyGuard(e) {
  if (!viewer()) return;
  const t = e.composedPath?.()[0] || e.target; if (t instanceof HTMLElement && (t.matches("input, textarea, select, [contenteditable]"))) return;
  const mod = e.ctrlKey || e.metaKey;
  if (!(e.key === "Delete" || e.key === "Backspace" || e.key === "Enter" || e.key === " " || (mod && /^[zyxv]$/i.test(e.key)) || (!mod && !e.altKey && e.key.length === 1 && /\p{L}/u.test(e.key)))) return;
  e.preventDefault(); e.stopImmediatePropagation();
  if (Date.now() - hintAt > 5000) { hintAt = Date.now(); toast("Только просмотр: попросите владельца дать права на правку"); }
}

/* ================= запуск: project.js на общем сервере зовёт hooks.shared ================= */
let booted = false;
async function boot() {
  if (booted) return; booted = true;
  grabJoin();
  addEventListener("keydown", keyGuard, true);
  addEventListener("keydown", e => { if (e.key === "Escape" && hub.cMode) setCMode(false); });
  addEventListener("hashchange", () => { if (grabJoin() && hub.me) { doJoin(); return; } const m = /[#&]p=([\w-]+)/.exec(location.hash); if (m && hub.me && m[1] !== hub.pid) openProject(m[1]); });
  Collab.listen("presence", d => { hub.others = (d?.users || []).filter(u => u.client !== C.client); hub.others.forEach(u => { if (u.name) hub.names[u.login] = u.name; }); });
  Collab.listen("comments", () => loadComments());
  Collab.listen("members", () => { refreshMeta(); if (hub.win === "share") loadLink(); });
  Collab.listen("session", d => { if (d?.expired) sessionLost(); });
  Collab.listen("role", () => toast(`Ваша роль в проекте: ${ROLE[myRole()] || "—"}`));
  Collab.listen("rev", () => { if (hub.win === "history") { clearTimeout(histT); histT = setTimeout(loadHistory, 1500); } });
  Collab.listen("deleted", d => { Collab.close(); closedProject(d?.reason === "access" ? "У вас больше нет доступа к этому проекту. Выберите другой проект" : "Проект удалён владельцем. Выберите другой проект"); loadProjects(); });
  Collab.listen("limit", () => toast("Открыто слишком много вкладок с этим проектом: закройте лишние. Чужие правки пока приходят с задержкой"));
  let faultAt = 0; Collab.listen("fault", d => { if (Date.now() - faultAt < 10000) return; faultAt = Date.now(); toast("Правки не сохранены: " + (d?.message || "хранилище на сервере заполнено")); });
  setInterval(presenceTick, 500);
  setInterval(() => { if (!document.hidden && (hub.pid || ["projects", "teams"].includes(hub.win))) refreshMeta(); }, 15000);
  const tg = grabTg();
  let u = null; try { const r = await api("me"); u = r.user; hub.login.tg = !!r.tg; } catch (e) { hub.login.guest = !!e.guest; hub.login.tg = !!e.tg; }
  if (u && tg === "bound") toast("Telegram привязан: теперь можно входить через Telegram");
  else if (u && tg) toast(TG_MSG[tg] || TG_MSG.fail);
  if (!u) u = await askLogin(tg ? TG_MSG[tg] || TG_MSG.fail : "");
  enter(u);
}
let histT = 0;
hooks.touched = Collab.touched;
hooks.shared = boot;
export const flush = async () => { if (!hub.pid) { toast("Откройте совместный проект: окно «Совместные проекты»"); return; } if (viewer()) { toast("Только просмотр: попросите владельца дать права на правку"); return; }
  toast(await Collab.flush() ? "Сохранено на сервере" : "Нет связи с сервером: правки сохранятся, когда связь вернётся"); };
export { shared };
