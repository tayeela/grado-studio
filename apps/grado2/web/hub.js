/* ГРАДО 2 · совместная работа: интерфейс (вход, проекты, доступ, комментарии, история, присутствие на карте).
   Работает только в совместном режиме (window.HUB_MODE ставит project.js после /api/health); в обычном ничего не показывает.
   Движок — web/collab.js (window.Collab); здесь только окна, шапка и наложения на карту. */
(() => {
"use strict";

/* ================= общее ================= */
const ROLE = { owner: "владелец", editor: "правка", viewer: "просмотр", admin: "администратор" };
const C = () => window.Collab;
const st = {
  me: null, pid: null, name: "", role: null, members: [], projects: [], names: {}, others: [], comments: [], cFilter: "open", cSel: null, draft: null,
  cMode: false, replyFor: null, replyText: "", renameId: null, hTab: "ver", armed: null,
};
const myRole = () => C()?.role || st.role || (st.me?.admin ? "admin" : null);
const canEdit = r => r === "owner" || r === "editor" || r === "admin";
const isOwner = r => r === "owner" || r === "admin";
const q = s => document.querySelector(s);
const plural = (n, [a, b, c]) => { const m = Math.abs(n) % 100, k = m % 10; return m > 10 && m < 20 ? c : k === 1 ? a : k > 1 && k < 5 ? b : c; };
const two = n => String(n).padStart(2, "0");
const toMs = v => typeof v === "number" ? (v < 1e11 ? v * 1000 : v) : Date.parse(v) || 0;
function when(v) {
  const t = toMs(v); if (!t) return "—";
  const d = new Date(t), now = new Date(), s = (now - d) / 1000, hm = `${two(d.getHours())}:${two(d.getMinutes())}`;
  if (s < 60) return "только что"; if (s < 3600) return `${Math.floor(s / 60)} мин назад`;
  const day = x => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime(), dd = Math.round((day(now) - day(d)) / 864e5);
  return dd === 0 ? "сегодня, " + hm : dd === 1 ? "вчера, " + hm : `${two(d.getDate())}.${two(d.getMonth() + 1)}.${d.getFullYear()}, ${hm}`;
}
const size = b => b > 1e6 ? (b / 1e6).toFixed(1).replace(".", ",") + " МБ" : Math.max(1, Math.round(b / 1e3)) + " КБ";
const uname = l => st.names[l] || l || "—";
const initials = (name, login) => { const w = String(name || login || "?").trim().split(/\s+/); return (w.length > 1 ? w[0][0] + w[1][0] : w[0].slice(0, 2)).toUpperCase(); };
const safeColor = c => /^#[0-9a-f]{6}$/i.test(c || "") ? c : "#7a7a7a";
const ink = c => { const n = parseInt(c.slice(1), 16), l = (.299 * (n >> 16) + .587 * (n >> 8 & 255) + .114 * (n & 255)) / 255; return l > .62 ? "#111" : "#fff"; };
const rgba = (c, a) => { const n = parseInt(c.slice(1), 16); return `rgba(${n >> 16},${n >> 8 & 255},${n & 255},${a})`; };
const list = (r, key) => Array.isArray(r) ? r : Array.isArray(r?.[key]) ? r[key] : r?.[key] && typeof r[key] === "object" ? Object.entries(r[key]).map(([k, v]) => ({ login: k, code: k, ...v })) : [];
const lyTitle = key => (typeof lyr === "function" ? lyr(key)?.title : null) || key;
const setText = (id, t) => { const e = $(id); if (e) e.textContent = t; };

/* запрос к серверу: есть тело — POST, нет — GET; 401 в любом месте — возврат на экран входа */
async function hub(path, body) {
  let r;
  try { r = await fetch("/api/hub/" + path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); }
  catch { throw new Error("нет связи с сервером"); }
  let j = null; try { j = await r.json(); } catch { }
  if (r.status === 401 && !/^(login|register|me|password)$/.test(path)) { sessionLost(); throw Object.assign(new Error("нужно войти заново"), { status: 401 }); }
  if (!r.ok) throw Object.assign(new Error(j?.error || "ошибка сервера " + r.status), { status: r.status });
  return j;
}
const fail = pre => e => { if (e.status !== 401) toast((pre ? pre + ": " : "") + e.message); };

/* перерисовка списков: пока человек печатает в поле окна, список не пересобирается под пальцами */
const R = {}, stale = new Set();
const typing = el => el.contains(document.activeElement) && /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
function draw(name, force) { const [el, fn] = R[name]; if (!force && typing(el)) { stale.add(name); return; } stale.delete(name); fn(); icons(); }
document.addEventListener("focusout", () => setTimeout(() => stale.forEach(n => draw(n)), 0));
/* двухшаговое подтверждение, как confirmLoss в project.js: первое нажатие взводит кнопку на 4 с, второе выполняет */
const armedIs = k => st.armed?.k === k && Date.now() - st.armed.t < 4000;
function twoStep(k, name) { if (armedIs(k)) { st.armed = null; return true; } st.armed = { k, t: Date.now() }; draw(name, true); setTimeout(() => { if (st.armed?.k === k) { st.armed = null; draw(name, true); } }, 4000); return false; }

/* ================= вход и регистрация ================= */
let loginRes = null, lmode = "in";
function setLmode(m) {
  lmode = m;
  document.querySelectorAll("[data-lmode]").forEach(b => b.setAttribute("aria-selected", b.dataset.lmode === m));
  document.querySelectorAll("[data-lm]").forEach(l => l.hidden = l.dataset.lm !== m);
  $("hubGo").textContent = m === "in" ? "Войти" : "Зарегистрироваться";
  $("hubPw").autocomplete = m === "in" ? "current-password" : "new-password"; setText("hubMsg", "");
}
function lock(on) { document.querySelectorAll(".app,.win").forEach(e => { e.inert = on; }); }
function showLogin(msg) {
  $("hubLogin").hidden = false; lock(true); setLmode("in"); setText("hubMsg", msg || "");
  setTimeout(() => ($("hubLg").value ? $("hubPw") : $("hubLg")).focus(), 0);
}
function askLogin(msg) { return new Promise(res => { const old = loginRes; loginRes = u => { old?.(u); res(u); }; showLogin(msg); }); }
async function submitLogin(e) {
  e.preventDefault();
  const login = $("hubLg").value.trim().toLowerCase(), pw = $("hubPw").value, msg = t => setText("hubMsg", t), reg = lmode === "reg";
  if (!login || !pw) return msg("Введите логин и пароль.");
  if (reg) {
    if (!$("hubInv").value.trim()) return msg("Введите код приглашения: его выдаёт администратор.");
    if (!/^[a-z0-9_.-]{3,32}$/.test(login)) return msg("Логин: от 3 до 32 знаков — латинские буквы, цифры, точка, дефис, подчёркивание.");
    if (pw.length < 8) return msg("Пароль должен быть не короче 8 знаков.");
    if (pw !== $("hubPw2").value) return msg("Пароли не совпадают.");
  }
  $("hubGo").disabled = true; msg("");
  try {
    const r = await hub(reg ? "register" : "login", reg ? { invite: $("hubInv").value.trim(), login, name: $("hubNm").value.trim() || login, password: pw } : { login, password: pw });
    $("hubPw").value = $("hubPw2").value = "";
    if (st.me && r.user.login !== st.me.login) return location.reload();        // другой человек за тем же компьютером: чужих данных на экране не оставляем
    $("hubLogin").hidden = true; lock(false);
    const res = loginRes; loginRes = null; res?.(r.user);
  } catch (err) { msg(err.message); }
  finally { $("hubGo").disabled = false; }
}
function sessionLost() {
  if (!$("hubLogin").hidden) return;
  askLogin("Вход закончился. Войдите снова — несохранённые правки остаются на экране и уйдут на сервер.").then(u => { enter(u, true); C()?.resume?.(); loadProjects(); });
}

/* ================= вход выполнен: шапка, движок, проект ================= */
let inited = null, bootP = null;
function enter(user, again) {
  st.me = user; st.names[user.login] = user.name || user.login;
  setText("hubAccName", user.name || user.login); $("hubAcc").title = `Вы вошли как ${user.name || user.login} (${user.login})`;
  $("hubAdminItem").hidden = !user.admin; $("hubBar").hidden = false; $("hubCTool").hidden = false;
  if (inited !== user.login) { inited = user.login; C()?.init?.(user); }
  if (again) return;
  const m = /[#&]p=([\w-]+)/.exec(location.hash);
  if (m) openProject(m[1]); else winOpen("wHubProjects", true);
}
function boot() {
  return bootP ||= (async () => {
    wire();
    let u = null; try { u = (await hub("me")).user; } catch { }
    if (!u) u = await askLogin();
    return u;
  })();
}

async function openProject(pid, name) {
  if (!C()) return toast("Модуль совместной работы не загрузился: обновите страницу.");
  try { await C().open(pid); } catch (e) { return fail("Проект не открылся")(e); }
  st.pid = pid; st.role = C().role || st.role; if (name) st.name = name; st.comments = []; st.cSel = null; st.draft = null;
  try { history.replaceState(null, "", "#p=" + pid); } catch { }
  if (!$("wHubProjects").hidden) winOpen("wHubProjects", false);
  await refreshMeta(); applyRole(); loadComments();
  ["wShare", "wHistory"].forEach(id => { if (!$(id).hidden) WIN_OPEN[id]?.(); });
}
function closedProject(text) {
  st.pid = null; st.name = ""; st.members = []; st.comments = []; st.others = []; st.draft = null; st.cSel = null; setCMode(false);
  try { history.replaceState(null, "", location.pathname + location.search); } catch { }
  renderBar(); renderAv(); paintPins(); paintPresence(); applyRole(); if (text) toast(text);
  winOpen("wHubProjects", true);
}
async function loadProjects() {
  try { st.projects = (await hub("projects")).projects || []; } catch (e) { fail("Список проектов")(e); return; }
  st.projects.forEach(p => (p.members || []).forEach(m => { st.names[m.login] = m.name || m.login; }));
  draw("projects");
}
async function refreshMeta() {
  await loadProjects(); const p = st.projects.find(x => x.id === st.pid);
  if (p) { st.name = p.name; st.members = p.members || []; st.role = p.role; }
  renderBar(); applyRole();
}

/* ================= шапка ================= */
const SYNC = {
  saved: ["сохранено", "Все правки сохранены на сервере"], sending: ["отправляю…", "Правки отправляются на сервер"],
  offline: ["нет связи", "Нет связи — правки сохранятся, когда связь вернётся"], conflict: ["объединяю…", "Ваши правки и правки коллег объединяются"],
  readonly: ["только просмотр", "У вас права только на просмотр: правки не отправляются"],
  full: ["хранилище заполнено", "На сервере нет места: правки остаются на экране, но не сохранены"],
};
function setSync(state) { const [t, tip] = SYNC[state] || SYNC.saved, b = $("hubSync"); b.dataset.state = state; b.title = tip; setText("hubSyncTxt", t); }
function renderBar() {
  setText("hubProjName", st.pid ? st.name || "Проект" : "Выберите проект");
  setText("hubRole", st.pid ? ROLE[myRole()] || "" : "");
  $("hubProjBtn").title = st.pid ? `Проект «${st.name}». Ваша роль: ${ROLE[myRole()] || "—"}. Совместные проекты: открыть, создать, загрузить` : "Совместные проекты: открыть, создать, загрузить";
  ["hubShareBtn", "hubComBtn", "hubHistBtn"].forEach(id => { $(id).disabled = !st.pid; });
  $("hubCTool").disabled = !st.pid;
}
function renderAv() {
  const seen = new Set(), us = st.others.filter(u => u.login !== st.me?.login && !seen.has(u.login) && seen.add(u.login)), MAX = innerWidth < 1600 ? 3 : 5;
  $("hubAv").innerHTML = us.slice(0, MAX).map(u => { const c = safeColor(u.color); return `<span class="av" style="background:${c};color:${ink(c)}" title="${esc(u.name || u.login)} сейчас в проекте">${esc(initials(u.name, u.login))}</span>`; }).join("")
    + (us.length > MAX ? `<span class="more" title="${esc(us.slice(MAX).map(u => u.name || u.login).join(", "))}">+${us.length - MAX}</span>` : "");
  $("hubAv").title = us.length ? "Сейчас в проекте: " + us.map(u => u.name || u.login).join(", ") : "Кроме вас, в проекте сейчас никого нет";
}
function applyRole() {
  const viewer = !!st.pid && myRole() === "viewer";
  document.body.classList.toggle("hub-viewer", viewer); $("hubViewHint").hidden = !viewer; renderBar();
  if (viewer) { setSync("readonly"); if (typeof setTool === "function" && UIS.tool !== "select") setTool("select"); }
  else if ($("hubSync").dataset.state === "readonly") setSync("saved");
  draw("share"); draw("comments");
}
function menu(on) {
  $("hubAccMenu").hidden = !on; $("hubAcc").setAttribute("aria-expanded", on);
  if (on) [...$("hubAccMenu").querySelectorAll("button")].find(b => b.offsetParent)?.focus();
}

/* ================= окно «Совместные проекты» ================= */
R.projects = [$("hubProjList"), () => {
  const rows = [...st.projects].sort((a, b) => toMs(b.updated) - toMs(a.updated)), el = $("hubProjList"), k = (a, id) => a + ":" + id;
  if (!rows.length) { el.innerHTML = `<div class="empty">Совместных проектов пока нет. Введите название и нажмите «Создать пустой» или «Сделать общим текущую работу».</div>`; return; }
  el.innerHTML = `<table class="at hubt"><thead><tr><th>Проект</th><th>Ваша роль</th><th>Менял последним</th><th>Сейчас в проекте</th><th></th></tr></thead><tbody>${rows.map(p => {
    const cur = p.id === st.pid, own = isOwner(p.role), on = +p.online || 0, ren = st.renameId === p.id;
    const name = ren ? `<input type="text" class="hubren" data-id="${esc(p.id)}" value="${esc(p.name)}" maxlength="60" aria-label="Новое название проекта">` : `${esc(p.name)}${cur ? `<span class="pill">открыт</span>` : ""}`;
    const del = armedIs(k("del", p.id));
    return `<tr class="${cur ? "cur" : ""}"><td class="nm" title="${esc(p.name)}">${name}</td><td>${esc(ROLE[p.role] || p.role)}</td>
      <td>${p.updated_by ? esc(uname(p.updated_by)) : "—"}<span class="sub">${p.updated ? esc(when(p.updated)) : ""}</span></td>
      <td class="num">${on ? `${on} ${plural(on, ["человек", "человека", "человек"])}` : `<span class="hubdim">никого</span>`}</td>
      <td class="acts"><button class="btn" data-act="open" data-id="${esc(p.id)}" ${cur ? "disabled" : ""}>${cur ? "Открыт" : "Открыть"}</button>
        ${own ? `<button class="tb" data-act="ren" data-id="${esc(p.id)}" title="Переименовать проект" aria-label="Переименовать"><i data-lucide="pencil"></i></button>` : ""}
        <button class="tb" data-act="dl" data-id="${esc(p.id)}" title="Скачать проект файлом .grado2" aria-label="Скачать"><i data-lucide="download"></i></button>
        ${own ? `<button class="tb ${del ? "danger" : ""}" data-act="del" data-id="${esc(p.id)}" title="${del ? "Нажмите ещё раз — проект и его история будут удалены у всех" : "Удалить проект у всех участников"}" aria-label="Удалить"><i data-lucide="trash-2"></i>${del ? "Точно?" : ""}</button>` : ""}</td></tr>`;
  }).join("")}</tbody></table>`;
  el.querySelector(".hubren")?.focus();
}];
async function createProject(body, okText) {
  const name = body.name; if (!name) { $("hubNewName").focus(); return toast("Введите название проекта."); }
  try {
    const r = await hub("projects", body); $("hubNewName").value = "";
    await loadProjects(); toast(okText || `Создан проект «${name}».`);
    if (C()?.pid !== r.id) await openProject(r.id, name); else { st.pid = r.id; st.name = name; await refreshMeta(); winOpen("wHubProjects", false); }
  } catch (e) { fail("Проект не создан")(e); }
}
function wireProjects() {
  $("hubNew").onclick = () => createProject({ name: $("hubNewName").value.trim() });
  $("hubNewName").addEventListener("keydown", e => { if (e.key === "Enter") $("hubNew").click(); });
  $("hubShareLocal").onclick = async () => {
    const name = $("hubNewName").value.trim(); if (!name) { $("hubNewName").focus(); return toast("Введите название: под ним текущая работа станет общим проектом."); }
    if (!C()?.createFromLocal) return toast("Модуль совместной работы не загрузился: обновите страницу.");
    try {
      const r = await C().createFromLocal(name), pid = (r && r.id) || (typeof r === "string" ? r : null) || C().pid;
      $("hubNewName").value = ""; await loadProjects();
      if (pid && C().pid !== pid) await openProject(pid, name); else { st.pid = C().pid; st.name = name; history.replaceState(null, "", "#p=" + st.pid); await refreshMeta(); loadComments(); winOpen("wHubProjects", false); }
      toast(`Текущая работа стала общим проектом «${name}».`);
    } catch (e) { fail("Не удалось сделать работу общей")(e); }
  };
  $("hubFile").onchange = async e => {
    const f = e.target.files[0]; e.target.value = ""; if (!f) return;
    try {
      const p = JSON.parse(await f.text()); if (p.format && p.format !== "grado2") throw new Error("это не проект ГРАДО 2");
      const name = $("hubNewName").value.trim() || p.name || f.name.replace(/\.(grado2|json)$/i, "");
      await createProject({ name: name.slice(0, 60), project: p }, `Файл «${f.name}» загружен как общий проект.`);
    } catch (err) { toast("Файл не загружен: " + err.message); }
  };
  $("hubProjList").addEventListener("click", async e => {
    const b = e.target.closest("[data-act]"); if (!b) return; const id = b.dataset.id, p = st.projects.find(x => x.id === id); if (!p) return;
    if (b.dataset.act === "open") openProject(id, p.name);
    else if (b.dataset.act === "dl") { const a = document.createElement("a"); a.href = `/api/hub/project/${encodeURIComponent(id)}/download`; a.download = p.name + ".grado2"; document.body.append(a); a.click(); a.remove(); }
    else if (b.dataset.act === "ren") { st.renameId = id; draw("projects", true); }
    else if (b.dataset.act === "del" && twoStep("del:" + id, "projects")) {
      try { await hub(`project/${encodeURIComponent(id)}/delete`, {}); toast(`Проект «${p.name}» удалён.`); if (id === st.pid) { C()?.close?.(); closedProject(); } loadProjects(); } catch (err) { fail("Проект не удалён")(err); }
    }
  });
  $("hubProjList").addEventListener("keydown", async e => {
    const i = e.target.closest?.(".hubren"); if (!i) return;
    if (e.key === "Escape") { st.renameId = null; draw("projects", true); }
    if (e.key === "Enter") {
      const name = i.value.trim(), id = i.dataset.id; st.renameId = null;
      if (name) try { await hub("project/" + encodeURIComponent(id), { name }); if (id === st.pid) st.name = name; toast("Проект переименован."); await refreshMeta(); } catch (err) { fail("Не переименован")(err); }
      draw("projects", true);
    }
  });
  $("hubProjList").addEventListener("focusout", e => { if (e.target.closest?.(".hubren") && st.renameId) { st.renameId = null; setTimeout(() => draw("projects", true), 0); } });
}

/* ================= окно «Доступ» ================= */
R.share = [$("hubShareBody"), () => {
  const el = $("hubShareBody"), own = isOwner(myRole());
  if (!st.pid) { el.innerHTML = `<div class="empty">Сначала откройте проект: окно «Совместные проекты».</div>`; return; }
  el.innerHTML = `<div class="hubnote">Проект «${esc(st.name)}». ${own ? "Вы владелец: можно добавлять и убирать участников и менять их роли." : "Менять доступ может только владелец проекта."}</div>
  <table class="at hubt"><thead><tr><th>Участник</th><th>Логин</th><th>Роль</th><th></th></tr></thead><tbody>${st.members.map(m => {
    const rm = armedIs("rm:" + m.login);
    return `<tr><td class="nm">${esc(m.name || m.login)}${m.login === st.me?.login ? `<span class="pill">вы</span>` : ""}</td><td>${esc(m.login)}</td>
    <td>${own ? `<select data-act="role" data-login="${esc(m.login)}" aria-label="Роль участника">${["owner", "editor", "viewer"].map(r => `<option value="${r}" ${m.role === r ? "selected" : ""}>${ROLE[r]}</option>`).join("")}</select>` : esc(ROLE[m.role] || m.role)}</td>
    <td class="acts">${own ? `<button class="tb ${rm ? "danger" : ""}" data-act="rm" data-login="${esc(m.login)}" title="${rm ? "Нажмите ещё раз, чтобы убрать участника" : "Убрать из проекта"}" aria-label="Убрать"><i data-lucide="x"></i>${rm ? "Точно?" : ""}</button>` : ""}</td></tr>`;
  }).join("")}</tbody></table>
  ${own ? `<div class="projbar"><input type="text" id="hubShareLogin" placeholder="Логин человека" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="Логин человека"><select id="hubShareRole" aria-label="Роль"><option value="editor">правка</option><option value="viewer">просмотр</option></select><button class="btn primary" data-act="add"><i data-lucide="user-plus"></i>Добавить</button></div>
  <div class="hubnote">Человек должен быть зарегистрирован в ГРАДО 2. Нет учётной записи — попросите администратора выдать приглашение.</div>` : ""}
  <div class="hubnote"><b>Владелец</b> — управляет доступом, может удалить проект. <b>Правка</b> — рисует и меняет проект. <b>Просмотр</b> — смотрит проект и оставляет комментарии.</div>`;
}];
function wireShare() {
  const setRole = async (login, role) => { try { await hub(`project/${encodeURIComponent(st.pid)}/members`, { login, role }); await refreshMeta(); } catch (e) { fail("Доступ не изменён")(e); await refreshMeta(); } };
  $("hubShareBody").addEventListener("change", e => { const s = e.target.closest('select[data-act="role"]'); if (s) setRole(s.dataset.login, s.value); });
  $("hubShareBody").addEventListener("click", async e => {
    const b = e.target.closest("button[data-act]"); if (!b) return;
    if (b.dataset.act === "rm" && twoStep("rm:" + b.dataset.login, "share")) { await setRole(b.dataset.login, null); toast("Участник убран из проекта."); }
    if (b.dataset.act === "add") {
      const login = $("hubShareLogin").value.trim().toLowerCase(); if (!login) return $("hubShareLogin").focus();
      await setRole(login, $("hubShareRole").value); draw("share", true);
    }
  });
  $("hubShareBody").addEventListener("keydown", e => { if (e.key === "Enter" && e.target.id === "hubShareLogin") $("hubShareBody").querySelector('[data-act="add"]').click(); });
}

/* ================= комментарии ================= */
const IDX = new WeakMap();
function uidIndex(src) {
  let e = IDX.get(src); const rev = src.getRevision();
  if (!e || e.rev !== rev) { const m = new Map(); src.getFeatures().forEach(f => { const u = f.get("_uid"); if (u) m.set(u, f); }); e = { rev, m }; IDX.set(src, e); }
  return e.m;
}
function findByUid(uid, layer) {
  if (layer && layerSrc[layer]) { const f = uidIndex(layerSrc[layer]).get(uid); if (f) return f; }
  for (const k in layerSrc) { if (k === layer) continue; const f = uidIndex(layerSrc[k]).get(uid); if (f) return f; }
  return null;
}
function geomPoint(g) {
  if (!g) return null; const t = g.getType();
  if (t === "Point") return g.getCoordinates().slice(0, 2);
  if (t === "Polygon") return g.getInteriorPoint().getCoordinates().slice(0, 2);
  return ol.extent.getCenter(g.getExtent());
}
function anchorPoint(a) {
  if (a?.lonlat) return ol.proj.fromLonLat(a.lonlat);
  if (a?.uid) { const src = layerSrc[a.layer]; return src ? geomPoint(uidIndex(src).get(a.uid)?.getGeometry()) : null; }
  return null;
}
const anchorText = a => a?.lonlat ? "точка на карте" : a?.uid ? (anchorPoint(a) ? `объект слоя «${lyTitle(a.layer)}»` : "объект удалён") : "";
const sortedComments = () => [...st.comments].sort((a, b) => toMs(a.created) - toMs(b.created));

async function loadComments() {
  if (!st.pid) return;
  try { st.comments = list(await hub(`project/${encodeURIComponent(st.pid)}/comments`), "comments"); } catch (e) { fail("Комментарии")(e); return; }
  st.comments.forEach(c => { if (c.author && !st.names[c.author]) st.names[c.author] = c.author; });
  const n = st.comments.filter(c => !c.resolved).length; $("hubComCnt").hidden = !n; setText("hubComCnt", n);
  draw("comments"); paintPins();
}
R.comments = [$("hubCList"), () => {
  const el = $("hubCList"), me = st.me, r = myRole();
  $("hubCObj").disabled = !st.pid || typeof SEL === "undefined" || !SEL.length; $("hubCTool2").disabled = !st.pid;
  document.querySelectorAll("#hubCFilter [data-f]").forEach(b => b.setAttribute("aria-pressed", b.dataset.f === st.cFilter));
  if (!st.pid) { el.innerHTML = `<div class="empty">Сначала откройте проект.</div>`; return; }
  const all = sortedComments(), shown = all.map((c, i) => ({ c, n: i + 1 })).filter(x => st.cFilter === "all" || (st.cFilter === "open") === !x.c.resolved);
  if (!shown.length) { el.innerHTML = `<div class="empty">${all.length ? "В этом списке комментариев нет." : "Комментариев пока нет. Нажмите «Комментарий на карте» и щёлкните по карте, или выберите объект и нажмите «К выбранному объекту»."}</div>`; return; }
  el.innerHTML = shown.map(({ c, n }) => {
    const can = c.author === me?.login || isOwner(r), del = armedIs("cdel:" + c.id);
    return `<div class="hubc ${c.resolved ? "done" : ""} ${c.id === st.cSel ? "sel" : ""}" data-cid="${esc(c.id)}">
      <div class="hubch"><span class="hubpin">${n}</span><b>${esc(uname(c.author))}</b><span class="t">${esc(when(c.created))}</span></div>
      <div class="hubcb">${esc(c.text)}</div><div class="hubca">${esc(anchorText(c.anchor))}${c.resolved ? " · решён" : ""}</div>
      ${(c.replies || []).map(x => `<div class="hubr"><div class="hr"><b>${esc(uname(x.author))}</b><span>${esc(when(x.created))}</span></div><div>${esc(x.text)}</div></div>`).join("")}
      ${st.replyFor === c.id ? `<div class="hubcr"><textarea rows="2" maxlength="4000" data-reply="${esc(c.id)}" placeholder="Ваш ответ" aria-label="Ваш ответ">${esc(st.replyText)}</textarea><div class="hubrow"><button class="btn" data-act="replycancel">Отмена</button><button class="btn primary" data-act="replysend" data-cid="${esc(c.id)}">Ответить</button></div></div>` : ""}
      <div class="hubcf"><button class="btn" data-act="reply" data-cid="${esc(c.id)}">Ответить</button><button class="btn" data-act="resolve" data-cid="${esc(c.id)}">${c.resolved ? "Вернуть в работу" : "Решено"}</button>${can ? `<button class="btn ${del ? "danger" : ""}" data-act="cdel" data-cid="${esc(c.id)}" title="Комментарий удаляется вместе с ответами">${del ? "Точно удалить?" : "Удалить"}</button>` : ""}</div></div>`;
  }).join("");
  const t = el.querySelector("textarea[data-reply]"); if (t) { t.focus(); t.setSelectionRange(t.value.length, t.value.length); }
}];
const cpath = s => `project/${encodeURIComponent(st.pid)}/comments${s || ""}`;
function flyTo(pt) {
  if (!pt) return toast("Объект этого комментария удалён — метки на карте нет.");
  sharedView.animate({ center: pt, zoom: Math.max(sharedView.getZoom() || 0, 17), duration: 350 });
}
function selectComment(cid, open) {
  st.cSel = cid; const c = st.comments.find(x => x.id === cid);
  if (open && $("wComments").hidden) winOpen("wComments", true);
  draw("comments", true); paintPins();
  if (c) { flyTo(anchorPoint(c.anchor)); setTimeout(() => $("hubCList").querySelector(`[data-cid="${CSS.escape(cid)}"]`)?.scrollIntoView({ block: "nearest" }), 0); }
}
function startDraft(anchor, pt) {
  if (!st.pid) return;
  st.draft = { anchor, pt: pt || anchorPoint(anchor) };
  winOpen("wComments", true); $("hubCompose").hidden = false;
  setText("hubCWhere", anchor.lonlat ? "Комментарий к точке на карте" : `Комментарий к объекту слоя «${lyTitle(anchor.layer)}»`);
  $("hubCText").focus(); paintPins();
}
function endDraft() { setCMode(false); st.draft = null; $("hubCompose").hidden = true; $("hubCText").value = ""; paintPins(); }
function setCMode(on) {
  on = !!on && !!st.pid; if (on === st.cMode) return; st.cMode = on;
  if (on) { try { window.CAD?.cancel?.(true); } catch { } if (typeof setTool === "function" && UIS.tool !== "select") setTool("select"); window.setHint?.("Комментарий: щёлкните по карте там, где нужна метка. Esc — отмена."); }
  else window.setHint?.("");
  ["hubCTool", "hubCTool2"].forEach(id => $(id).setAttribute("aria-pressed", on)); document.body.classList.toggle("hub-cmode", on);
}
function wireComments() {
  $("hubCTool").onclick = $("hubCTool2").onclick = () => setCMode(!st.cMode);
  $("hubCObj").onclick = () => {
    const s = typeof SEL !== "undefined" ? SEL[0] : null, uid = s?.f?.get("_uid");
    if (!s) return toast("Сначала выберите объект на карте.");
    if (!uid) return toast("У этого объекта пока нет постоянного номера: подождите секунду и попробуйте ещё раз.");
    setCMode(false); startDraft({ layer: s.key, uid });
  };
  $("hubCCancel").onclick = endDraft;
  $("hubCSend").onclick = async () => {
    const text = $("hubCText").value.trim(); if (!text) return $("hubCText").focus();
    if (!st.draft) return;
    $("hubCSend").disabled = true;
    try { await hub(cpath(), { text, anchor: st.draft.anchor }); endDraft(); setCMode(false); await loadComments(); }
    catch (e) { fail("Комментарий не отправлен")(e); } finally { $("hubCSend").disabled = false; }
  };
  $("hubCText").addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("hubCSend").click(); if (e.key === "Escape") endDraft(); });
  $("hubCFilter").addEventListener("click", e => { const b = e.target.closest("[data-f]"); if (b) { st.cFilter = b.dataset.f; draw("comments", true); } });
  const el = $("hubCList");
  el.addEventListener("input", e => { if (e.target.dataset.reply) st.replyText = e.target.value; });
  el.addEventListener("click", async e => {
    const b = e.target.closest("[data-act]"), card = e.target.closest("[data-cid]");
    if (!b) { if (card && !e.target.closest("textarea")) selectComment(card.dataset.cid); return; }
    const cid = b.dataset.cid;
    try {
      if (b.dataset.act === "reply") { st.replyFor = cid; st.replyText = ""; draw("comments", true); }
      else if (b.dataset.act === "replycancel") { st.replyFor = null; draw("comments", true); }
      else if (b.dataset.act === "replysend") {
        const text = (el.querySelector("textarea[data-reply]")?.value || "").trim(); if (!text) return;
        await hub(cpath(`/${encodeURIComponent(cid)}/reply`), { text }); st.replyFor = null; st.replyText = ""; await loadComments();
      } else if (b.dataset.act === "resolve") { const c = st.comments.find(x => x.id === cid); await hub(cpath(`/${encodeURIComponent(cid)}`), { resolved: !c?.resolved }); await loadComments(); }
      else if (b.dataset.act === "cdel" && twoStep("cdel:" + cid, "comments")) { await hub(cpath(`/${encodeURIComponent(cid)}/delete`), {}); if (st.cSel === cid) st.cSel = null; await loadComments(); }
    } catch (err) { fail("Комментарий")(err); }
  });
}

/* ================= история ================= */
const ACT = { create: "создал проект", push: "изменил проект", edit: "изменил проект", restore: "вернул версию", comment: "оставил комментарий", reply: "ответил на комментарий", resolve: "отметил комментарий решённым", reopen: "вернул комментарий в работу", member: "изменил доступ", rename: "переименовал проект", import: "загрузил файл" };
R.history = [$("hubHBody"), () => {
  document.querySelectorAll("[data-htab]").forEach(b => b.setAttribute("aria-selected", b.dataset.htab === st.hTab));
  const el = $("hubHBody"), h = st.hist; if (!st.pid) { el.innerHTML = `<div class="empty">Сначала откройте проект.</div>`; return; }
  if (!h) { el.innerHTML = `<div class="empty">Загружаю…</div>`; return; }
  if (st.hTab === "ver") {
    const ed = canEdit(myRole()), rows = [...h.ver].sort((a, b) => b.rev - a.rev);
    el.innerHTML = `<div class="hubnote">Версия сохраняется не чаще раза в 10 минут и перед каждым возвратом. Возврат не стирает историю: текущая работа тоже остаётся в списке.${ed ? "" : " Вернуть версию могут владелец и редакторы."}</div>`
      + (rows.length ? `<table class="at hubt"><thead><tr><th>№</th><th>Когда</th><th>Кто</th><th>Размер</th><th></th></tr></thead><tbody>${rows.map(v => { const a = armedIs("rs:" + v.rev);
        return `<tr><td class="num">${esc(v.rev)}</td><td>${esc(when(v.t))}</td><td>${esc(uname(v.login))}</td><td class="num">${v.size ? esc(size(v.size)) : "—"}</td><td class="acts">${ed ? `<button class="btn ${a ? "danger" : ""}" data-act="restore" data-rev="${esc(v.rev)}">${a ? "Точно вернуть?" : "Вернуть эту версию"}</button>` : ""}</td></tr>`; }).join("")}</tbody></table>` : `<div class="empty">Сохранённых версий пока нет: первая появится через несколько минут работы.</div>`);
  } else {
    const rows = [...h.act].sort((a, b) => toMs(b.t) - toMs(a.t));
    el.innerHTML = rows.length ? `<table class="at hubt"><thead><tr><th>Когда</th><th>Кто</th><th>Что сделал</th></tr></thead><tbody>${rows.map(a => `<tr><td>${esc(when(a.t))}</td><td>${esc(uname(a.login))}</td><td class="nm" title="${esc(a.detail)}">${esc(ACT[a.action] || a.action)}${a.detail ? `<span class="sub">${esc(a.detail)}</span>` : ""}</td></tr>`).join("")}</tbody></table>` : `<div class="empty">Записей пока нет.</div>`;
  }
}];
async function loadHistory() {
  if (!st.pid) return draw("history", true); const p = encodeURIComponent(st.pid);
  try {
    const [v, a] = await Promise.all([hub(`project/${p}/history`), hub(`project/${p}/activity`)]);
    st.hist = { ver: list(v, "history"), act: list(a, "activity") };
  } catch (e) { fail("История")(e); return; }
  draw("history");
}
function wireHistory() {
  $("wHistory").querySelector(".dtabs").addEventListener("click", e => { const b = e.target.closest("[data-htab]"); if (b) { st.hTab = b.dataset.htab; draw("history", true); } });
  $("hubHBody").addEventListener("click", async e => {
    const b = e.target.closest('[data-act="restore"]'); if (!b || !twoStep("rs:" + b.dataset.rev, "history")) return;
    try { await hub(`project/${encodeURIComponent(st.pid)}/history/${encodeURIComponent(b.dataset.rev)}/restore`, {}); toast(`Версия № ${b.dataset.rev} возвращена. Перед этим текущая работа сохранена в истории.`); await loadHistory(); }
    catch (err) { fail("Версия не возвращена")(err); }
  });
}

/* ================= пользователи и приглашения (администратор) ================= */
R.admin = [$("hubAdminBody"), () => {
  const el = $("hubAdminBody"), a = st.adm; if (!a) { el.innerHTML = `<div class="empty">Загружаю…</div>`; return; }
  el.innerHTML = `<div class="projbar"><button class="btn primary" data-act="invite"><i data-lucide="user-plus"></i>Создать приглашение</button></div>
    ${st.newCode ? `<div class="hubcode"><code id="hubCode">${esc(st.newCode)}</code><button class="btn" data-act="copy"><i data-lucide="copy"></i>Скопировать</button></div><div class="hubnote">Передайте код человеку: он вводит его на странице входа, вкладка «Регистрация по приглашению». Код одноразовый.</div>` : ""}
    <div class="hubsec">Приглашения</div>
    ${a.inv.length ? `<table class="at hubt"><thead><tr><th>Код</th><th>Создано</th><th>Кем</th><th>Использовано</th></tr></thead><tbody>${[...a.inv].sort((x, y) => toMs(y.created) - toMs(x.created)).map(i => `<tr><td><code>${esc(i.code)}</code></td><td>${esc(when(i.created))}</td><td>${esc(uname(i.by))}</td><td>${i.used_by ? `${esc(uname(i.used_by))}<span class="sub">${esc(when(i.used_at))}</span>` : `<span class="hubdim">ещё нет</span>`}</td></tr>`).join("")}</tbody></table>` : `<div class="hubnote">Приглашений пока нет.</div>`}
    <div class="hubsec">Пользователи</div>
    <table class="at hubt"><thead><tr><th>Имя</th><th>Логин</th><th>Статус</th><th></th></tr></thead><tbody>${a.users.map(u => `<tr><td class="nm">${esc(u.name || u.login)}${u.admin ? `<span class="pill">админ</span>` : ""}</td><td>${esc(u.login)}</td><td>${u.disabled ? `<span style="color:var(--bad)">отключён</span>` : "работает"}</td>
      <td class="acts">${u.login === st.me?.login ? "" : `<button class="btn" data-act="toggle" data-login="${esc(u.login)}" data-dis="${u.disabled ? 1 : 0}">${u.disabled ? "Включить" : "Отключить"}</button>`}</td></tr>`).join("")}</tbody></table>`;
}];
async function loadAdmin() {
  try { const [u, i] = await Promise.all([hub("users"), hub("invites")]); st.adm = { users: list(u, "users"), inv: list(i, "invites") }; st.adm.users.forEach(x => { st.names[x.login] = x.name || x.login; }); }
  catch (e) { fail("Пользователи")(e); return; }
  draw("admin");
}
function wireAdmin() {
  $("hubAdminBody").addEventListener("click", async e => {
    const b = e.target.closest("[data-act]"); if (!b) return;
    try {
      if (b.dataset.act === "invite") { st.newCode = (await hub("invites", {})).code; await loadAdmin(); draw("admin", true); }
      else if (b.dataset.act === "toggle") { await hub("users/" + encodeURIComponent(b.dataset.login), { disabled: b.dataset.dis !== "1" }); await loadAdmin(); }
      else if (b.dataset.act === "copy") {
        const t = st.newCode; let ok = false;
        try { await navigator.clipboard.writeText(t); ok = true; } catch { const r = document.createRange(); r.selectNodeContents($("hubCode")); const s = getSelection(); s.removeAllRanges(); s.addRange(r); try { ok = document.execCommand("copy"); } catch { } }
        toast(ok ? "Код скопирован." : "Код выделен: скопируйте его (Ctrl+C).");
      }
    } catch (err) { fail("Не получилось")(err); }
  });
}

/* ================= учётная запись ================= */
function wireAccount() {
  $("hubAcc").onclick = e => { e.stopPropagation(); menu($("hubAccMenu").hidden); };
  addEventListener("pointerdown", e => { if (!$("hubAccMenu").hidden && !e.target.closest(".hubacc")) menu(false); });
  $("hubAccMenu").addEventListener("keydown", e => {
    const items = [...$("hubAccMenu").querySelectorAll("button")].filter(b => b.offsetParent), i = items.indexOf(document.activeElement);
    if (e.key === "Escape") { menu(false); $("hubAcc").focus(); }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); items[(i + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus(); }
  });
  $("hubAccMenu").addEventListener("click", async e => {
    const w = e.target.closest("[data-hubwin]"); if (w) { menu(false); winOpen(w.dataset.hubwin, true); return; }
    const b = e.target.closest("[data-hubact]"); if (!b) return; menu(false);
    if (b.dataset.hubact === "pw") { ["hubPwOld", "hubPwNew", "hubPwNew2"].forEach(i => { $(i).value = ""; }); setText("hubPwMsg", ""); $("hubPwDlg").showModal(); $("hubPwOld").focus(); }
    if (b.dataset.hubact === "admin") winOpen("wHubAdmin", true);
    if (b.dataset.hubact === "out") {
      try { await C()?.flush?.(); } catch { }
      try { await hub("logout", {}); } catch { }
      try { history.replaceState(null, "", location.pathname + location.search); } catch { }
      location.reload();                                       // с экрана уходят данные проекта: следующий человек начинает с чистой страницы
    }
  });
  $("hubPwCancel").onclick = () => $("hubPwDlg").close();
  $("hubPwForm").addEventListener("submit", async e => {
    e.preventDefault(); const msg = t => setText("hubPwMsg", t), nw = $("hubPwNew").value;
    if (nw.length < 8) return msg("Новый пароль должен быть не короче 8 знаков.");
    if (nw !== $("hubPwNew2").value) return msg("Новые пароли не совпадают.");
    try { await hub("password", { old: $("hubPwOld").value, new: nw }); $("hubPwDlg").close(); toast("Пароль изменён."); } catch (err) { msg(err.message); }
  });
}

/* ================= наложения на карту: метки комментариев и присутствие ================= */
const comSrc = new ol.source.Vector(), presSrc = new ol.source.Vector();
const feat = (g, p) => { const f = new ol.Feature(g); f.setProperties(p); return f; };
const { Style, Fill, Stroke, Circle: OCircle, Text: OText, RegularShape } = ol.style;
const PSTY = new Map();
function pinStyle(f) {
  const draft = f.get("draft"), res = f.get("resolved"), sel = f.get("sel"), k = [draft, res, sel, f.get("n")].join();
  let s = PSTY.get(k); if (s) return s;
  const col = draft ? "#2f6fc4" : res ? "#8a8d91" : "#d9822b", z = sel || draft ? 3 : 2;
  s = [new Style({ image: new OCircle({ radius: 3, fill: new Fill({ color: col }), stroke: new Stroke({ color: "#fff", width: 1 }) }), zIndex: z }),
    new Style({ image: new OCircle({ radius: sel ? 13 : 11, displacement: [0, 14], fill: new Fill({ color: draft ? "rgba(47,111,196,.18)" : col }), stroke: new Stroke({ color: sel ? "#1d1d1f" : draft ? col : "#fff", width: 2, lineDash: draft ? [4, 3] : undefined }) }),
      text: draft ? undefined : new OText({ text: String(f.get("n")), offsetY: -14, font: "600 11px system-ui,sans-serif", fill: new Fill({ color: "#fff" }) }), zIndex: z })];
  PSTY.set(k, s); return s;
}
function presStyle(f) {
  const c = f.get("color");
  if (f.get("kind") === "cursor") return [new Style({ image: new RegularShape({ points: 3, radius: 8, displacement: [0, -8], fill: new Fill({ color: c }), stroke: new Stroke({ color: "#fff", width: 1.5 }) }),
    text: new OText({ text: f.get("name"), offsetX: 10, offsetY: 22, textAlign: "left", font: "600 11px system-ui,sans-serif", fill: new Fill({ color: ink(c) }), backgroundFill: new Fill({ color: c }), padding: [1, 4, 1, 4] }) })];
  const t = f.getGeometry().getType();
  if (/Point/.test(t)) return new Style({ image: new OCircle({ radius: 10, stroke: new Stroke({ color: c, width: 3 }), fill: new Fill({ color: rgba(c, .15) }) }) });
  if (/Line/.test(t)) return new Style({ stroke: new Stroke({ color: c, width: 5 }) });
  return new Style({ stroke: new Stroke({ color: c, width: 3, lineDash: [8, 4] }), fill: new Fill({ color: rgba(c, .14) }) });
}
const pres = { cursor: null, dirty: false, sig: "", t: 0 };
let snapSel = null;
function overlays(map) {
  if (map.get("hubOv")) return; map.set("hubOv", true);
  const p = new ol.layer.Vector({ source: presSrc, zIndex: 910, style: presStyle, updateWhileInteracting: true, updateWhileAnimating: true }),
    c = new ol.layer.Vector({ source: comSrc, zIndex: 920, style: pinStyle, updateWhileInteracting: true, updateWhileAnimating: true }); c.set("hubPins", true);
  map.addLayer(p); map.addLayer(c);
  map.on("pointermove", e => { const ll = ol.proj.toLonLat(e.coordinate); pres.cursor = [+ll[0].toFixed(6), +ll[1].toFixed(6)]; pres.dirty = true; });
  const vp = map.getViewport();
  vp.addEventListener("mouseleave", () => { pres.cursor = null; pres.dirty = true; });
  vp.addEventListener("pointerdown", () => { if (st.cMode && typeof SEL !== "undefined") snapSel = SEL.slice(); }, true);
  map.on("click", e => {
    let cid = null; map.forEachFeatureAtPixel(e.pixel, f => { if (f.get("cid")) { cid = f.get("cid"); return true; } }, { layerFilter: l => !!l.get("hubPins"), hitTolerance: 6 });
    if (cid) return selectComment(cid, true);
    if (!st.cMode || !st.pid) return;
    if (snapSel && typeof setSel === "function") setSel(snapSel);                // щелчок под комментарий не должен менять выбор объектов
    startDraft({ lonlat: ol.proj.toLonLat(e.coordinate) }, e.coordinate);
  });
}
function paintPins() {
  const fs = [];
  sortedComments().forEach((c, i) => { const pt = anchorPoint(c.anchor); if (pt) fs.push(feat(new ol.geom.Point(pt), { cid: c.id, n: i + 1, resolved: !!c.resolved, sel: c.id === st.cSel })); });
  if (st.draft?.pt) fs.push(feat(new ol.geom.Point(st.draft.pt), { draft: true }));
  comSrc.clear(true); comSrc.addFeatures(fs);
}
function paintPresence() {
  const fs = [];
  for (const u of st.others) {
    const col = safeColor(u.color);
    if (Array.isArray(u.cursor) && isFinite(u.cursor[0]) && isFinite(u.cursor[1])) fs.push(feat(new ol.geom.Point(ol.proj.fromLonLat(u.cursor)), { kind: "cursor", color: col, name: u.name || u.login }));
    (u.sel || []).slice(0, 200).forEach(uid => { const g = findByUid(uid, u.layer)?.getGeometry(); if (g) fs.push(feat(g.clone(), { kind: "sel", color: col })); });
  }
  presSrc.clear(true); presSrc.addFeatures(fs); paintDots();
}
/* в дереве слоёв у слоя, который сейчас правит кто-то ещё, стоит цветная точка */
let dotsBusy = false;
function paintDots() {
  const t = $("layerTree"); if (!t) return; dotsBusy = true;
  t.querySelectorAll(".hubdot").forEach(e => e.remove());
  const by = {}; st.others.forEach(u => { if (u.layer) (by[u.layer] ||= []).push(u); });
  t.querySelectorAll(".tn[data-lk]").forEach(row => {
    const us = by[row.dataset.lk]; if (!us) return;
    const d = document.createElement("span"); d.className = "hubdot"; d.title = "Сейчас работают со слоем: " + us.map(u => u.name || u.login).join(", ");
    d.style.cssText = "display:flex;gap:2px;flex:0 0 auto"; d.innerHTML = us.slice(0, 3).map(u => `<i style="width:8px;height:8px;border-radius:50%;background:${safeColor(u.color)};display:block"></i>`).join("");
    row.insertBefore(d, row.querySelector(".meta") || null);
  });
  dotsBusy = false;
}
let tick = 0, histT = 0;
function overlaysRefresh() { clearTimeout(tick); tick = setTimeout(() => { paintPins(); paintPresence(); draw("comments"); }, 500); }

/* ================= присутствие: что отправляем ================= */
function presenceTick() {
  if (!st.pid || !st.me) return;
  const sel = typeof SEL !== "undefined" ? SEL.map(s => s.f?.get?.("_uid")).filter(Boolean).slice(0, 200) : [], layer = typeof CUR !== "undefined" ? CUR : null;
  const sig = layer + "|" + sel.join(","), now = Date.now();
  if (pres.dirty || sig !== pres.sig || now - pres.t > 10000) { pres.dirty = false; pres.sig = sig; pres.t = now; C()?.presence?.({ cursor: pres.cursor, layer, sel }); }
  if (st.cMode && (window.CAD?.active?.() || (typeof UIS !== "undefined" && UIS.tool !== "select"))) setCMode(false);   // человек взялся за другой инструмент
  $("hubCObj").disabled = !st.pid || typeof SEL === "undefined" || !SEL.length;
}

/* ================= окна: открытие и подсказка для наблюдателя ================= */
function hubHooks() {
WIN_OPEN.wHubProjects = () => loadProjects();
WIN_OPEN.wShare = () => refreshMeta();
WIN_OPEN.wComments = () => { draw("comments", true); loadComments(); };
WIN_OPEN.wHistory = () => { st.hist = null; draw("history", true); loadHistory(); };
WIN_OPEN.wHubAdmin = () => { st.newCode = null; loadAdmin(); };
let hintAt = 0;
window.KEYGUARD = e => {                                  // true — клавишу не пускаем дальше (см. app.js)
  if (!document.body.classList.contains("hub-viewer")) return false;
  const t = e.target; if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) return false;
  const mod = e.ctrlKey || e.metaKey;
  if (!(e.key === "Delete" || e.key === "Backspace" || e.key === "Enter" || e.key === " " || (mod && /^[zyxv]$/i.test(e.key)) || (!mod && !e.altKey && e.key.length === 1 && /\p{L}/u.test(e.key)))) return false;
  if (Date.now() - hintAt > 5000) { hintAt = Date.now(); toast("Только просмотр: попросите владельца дать права на правку."); }
  return true;
};
}

/* ================= запуск ================= */
let wired = false;
function wire() {
  if (wired) return; wired = true;
  document.body.classList.add("hub-on");
  hubHooks(); ALLMAPS.forEach(overlays);
  const att = window.attachDataLayers; window.attachDataLayers = m => { att?.(m); overlays(m); };
  $("hubLoginForm").addEventListener("submit", submitLogin);
  document.querySelectorAll("[data-lmode]").forEach(b => b.onclick = () => setLmode(b.dataset.lmode));
  wireProjects(); wireShare(); wireComments(); wireHistory(); wireAdmin(); wireAccount();
  addEventListener("keydown", e => { if (e.key === "Escape" && st.cMode && !e.target.closest?.("input,textarea")) setCMode(false); });
  addEventListener("hashchange", () => { const m = /[#&]p=([\w-]+)/.exec(location.hash); if (m && st.me && m[1] !== st.pid) openProject(m[1]); });
  if (typeof MutationObserver === "function") new MutationObserver(() => { if (!dotsBusy) requestAnimationFrame(paintDots); }).observe($("layerTree"), { childList: true });
  const L = C()?.listen?.bind(C());
  if (L) {
    L("status", d => setSync(d?.state));
    L("presence", d => { st.others = (d?.users || []).filter(u => u.client !== C().client); st.others.forEach(u => { if (u.name) st.names[u.login] = u.name; }); renderAv(); paintPresence(); });
    L("comments", () => loadComments());
    L("members", () => refreshMeta());
    L("session", d => { if (d?.expired) sessionLost(); });
    L("role", () => { renderBar(); applyRole(); toast(`Ваша роль в проекте: ${ROLE[myRole()] || "—"}.`); });
    L("rev", () => { overlaysRefresh(); if (!$("wHistory").hidden) { clearTimeout(histT); histT = setTimeout(loadHistory, 1500); } });
    L("deleted", d => { C().close?.(); closedProject(d?.reason === "access" ? "У вас больше нет доступа к этому проекту. Выберите другой проект." : "Проект удалён владельцем. Выберите другой проект."); loadProjects(); });
    L("limit", () => toast("Открыто слишком много вкладок с этим проектом: закройте лишние. Чужие правки пока приходят с задержкой."));
    let faultAt = 0; L("fault", d => { if (Date.now() - faultAt < 10000) return; faultAt = Date.now(); toast("Правки не сохранены: " + (d?.message || "хранилище на сервере заполнено") + "."); });
  } else toast("Модуль совместной работы не загрузился: обновите страницу.");
  setInterval(presenceTick, 500);
  setInterval(() => { if (document.hidden) return; if (st.pid || !$("wHubProjects").hidden) refreshMeta(); draw("comments"); }, 15000);
  renderBar(); renderAv(); icons();
}

const modeP = new Promise(res => {
  let n = 0;
  const chk = () => { if (window.HUB_MODE !== undefined) { res(!!window.HUB_MODE); return true; } return ++n > 3000 && (res(false), true); };   // 5 минут ожидания, дальше считаем, что режим обычный
  if (!chk()) { const iv = setInterval(() => chk() && clearInterval(iv), 100); addEventListener("grado:mode", () => { if (chk()) clearInterval(iv); }); }
});
modeP.then(on => { if (on) boot(); });

window.HubUI = {
  /* project.js ждёт этот вызов перед стартом: в обычном режиме — сразу null, в совместном — после входа, с данными человека */
  requireSession: () => modeP.then(on => on ? boot() : null),
  /* после старта программы (project.js): шапка, движок, первый проект; до этого вход уже выполнен */
  enter: () => boot().then(u => enter(u)),
  open: openProject, projects: () => winOpen("wHubProjects", true), state: st,
};
})();
