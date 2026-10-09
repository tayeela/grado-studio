/* ГРАДО 2 · совместная работа в новом интерфейсе: движок синхронизации (контракт — docs/specs/collab-contract.md).
   Перенос части web/collab.js «в браузере»: разбиение, склейка и слияние по трём версиям (split, join, merge3) — общие,
   из web/collab.js; здесь обмен с сервером (/api/hub/project/<id>: push, sections, events, presence) и применение чужих
   правок к открытому проекту нового интерфейса (store.project, данные слоя — новый fc, карта перечитывает по ссылкам).
   Разделы те же, что у рабочей страницы, поэтому оба интерфейса работают с одним проектом на сервере.
   Чужая правка не попадает в отмену: после неё Ctrl+Z отменяет только ваши следующие правки (edit.js external).
   Окна, вход и шапка — hub.js и окна Hub*.vue. */
import { reactive, toRaw } from "vue";
import * as collabMod from "../../web/collab.js";
import { currentId, project, viewNow } from "./store.js";
import { external, graphHooks, lyr, normGroups } from "./edit.js";
import { collect, jsonOf, loadShared, markClean, notice, projectJSON } from "./project.js";
import { SOURCES } from "./data.js";
import { fullStyle } from "./symbology.js";

const { split, join, merge3, ensureUids, stable } = collabMod.default || collabMod;
globalThis.jsonOf ||= jsonOf;          // общий кэш текста крупных fc: web/collab.js берёт его, если он есть

export const C = reactive({ on: false, pid: null, rev: 0, role: null, user: null, status: "saved",
  client: Array.from(crypto.getRandomValues(new Uint8Array(8)), b => b.toString(16).padStart(2, "0")).join("") });
let applying = false;
const L = {};
export const listen = (type, cb) => { (L[type] ||= []).push(cb); return () => { L[type] = (L[type] || []).filter(f => f !== cb); }; };
const emit = (type, data) => (L[type] || []).slice().forEach(f => { try { f(data); } catch (e) { console.warn("collab: слушатель", type, e); } });
function setStatus(state) { if (C.status === state) return; C.status = state; emit("status", { state }); }
const editable = () => C.role !== "viewer";
const same = (a, b) => a === b || stable(a) === stable(b);
const js = o => (o && typeof o === "object") ? jsonOf(o) : JSON.stringify(o);
const quick = (a, b) => a === b || js(a) === js(b);
const isObj = v => v && typeof v === "object" && !Array.isArray(v);
const safeObj = v => isObj(v) ? v : {};
const okn = (v, d) => Number.isFinite(+v) && v !== null && v !== "" ? +v : d;

async function http(method, path, body) {
  const o = { method, credentials: "same-origin", headers: {} };
  if (method !== "GET") { o.headers["Content-Type"] = "application/json"; o.body = typeof body === "string" ? body : JSON.stringify(body ?? {}); }
  const r = await fetch(path, o); let json = null; try { json = await r.json(); } catch { /* ответ без тела */ }
  return { ok: r.ok, status: r.status, json };
}
const P = tail => `/api/hub/project/${C.pid}${tail || ""}`;

/* ---- проект нового интерфейса → форма collectProject() рабочей страницы (те же поля слоя и данных: разделы совпадают) ---- */
const DATA_F = ["title", "source", "fetched_at", "notes", "history", "shp", "bbox"];
/* схема — как её пишет рабочая страница: litegraph не хранит пустой widgets_values у узлов без полей (пересчёт здесь его
   добавляет), иначе две страницы перебрасывались бы одной и той же схемой */
function canonGraph(g) {
  if (!g || !Array.isArray(g.nodes) || !g.nodes.some(n => Array.isArray(n?.widgets_values) && !n.widgets_values.length)) return g ?? null;
  return { ...g, nodes: g.nodes.map(n => Array.isArray(n?.widgets_values) && !n.widgets_values.length ? (({ widgets_values, ...r }) => r)(n) : n) };
}
function collectProject() {
  const p = collect();
  p.groups = project.groups.map(g => ({ id: g.id, title: g.title, visible: g.visible !== false, open: g.open !== false }));
  p.layers = project.layers.map(l => ({ key: l.key, title: l.title, geom: l.geom, visible: l.visible !== false, layerOpacity: okn(l.layerOpacity, 1), open: !!l.open,
    group: l.group ?? null, style: toRaw(l.style), ...(l.role ? { role: l.role } : {}) }));
  p.data = Object.fromEntries(Object.entries(project.data).map(([k, d]) => {
    const o = {}; DATA_F.forEach(f => { if (d[f] !== undefined) o[f] = d[f]; });
    o.fc = d.fc; const og = d.original === d.fc ? "=fc" : d.original; if (og !== undefined) o.original = og;
    return [k, o];
  }));
  p.imports = project.raw.imports || {}; p.checked = project.raw.checked || []; p.album = project.raw.album || { meta: {}, sheets: [] }; p.graph = canonGraph(project.raw.graph);
  return p;
}

/* ---- база: последнее согласованное с сервером, по разделам — текстом JSON ---- */
let base = {}, secRev = {}, LC = new Map(), bm = null, ba = null;
const isLayerName = n => n.startsWith("layer:");
function secText(name, val) {
  if (val == null) return "null";
  const d = val.data;
  if (!isLayerName(name) || !d || typeof d !== "object") return JSON.stringify(val);
  const o = { ...d }, big = [];
  for (const f of ["fc", "original"]) if (o[f] && typeof o[f] === "object") { big.push(o[f]); o[f] = `@@CB_${big.length - 1}@@`; }
  const head = JSON.stringify({ spec: val.spec, data: o }), c = LC.get(name);
  if (c && c.head === head && c.big.length === big.length && c.big.every((x, i) => x === big[i])) return c.text;
  const text = head.replace(/"@@CB_(\d+)@@"/g, (_, i) => js(big[+i]));
  LC.set(name, { head, big, text });
  return text;
}
function baseMeta() { if (!bm || bm.t !== base.meta) bm = { t: base.meta, v: base.meta ? JSON.parse(base.meta) : null, s: null }; return bm; }
function baseAlbum() { if (!ba || ba.t !== base.album) ba = { t: base.album, s: base.album ? stable(JSON.parse(base.album)) : null }; return ba; }
function sameSection(name, val, text) {
  if (val == null) return text == null;
  if (text == null) return false;
  if (name === "meta") { const b = baseMeta(); return (b.s ??= stable(b.v)) === stable(val); }
  if (name === "album") return baseAlbum().s === stable(val);
  return secText(name, val) === text;
}
const baseName = () => baseMeta().v?.name ?? null;
function normSection(name, val) {
  if (val && isLayerName(name) && val.data?.fc) val.data.fc = ensureUids(val.data.fc, name.slice(6));
  if (val && name === "meta" && val.territory?._gid) val.territory = (({ _gid, ...t }) => t)(val.territory);
  if (val && name === "album") return { ...val, meta: { object: "", code: "", stage: "ПП", org: "", slide: "P", ...(isObj(val.meta) ? val.meta : {}) } };
  if (val && name === "meta") {
    if (Array.isArray(val.checked)) val.checked = [...val.checked].sort();
    if (Array.isArray(val.groups)) val.groups = val.groups.map(g => ({ id: g.id, title: g.title, visible: g.visible !== false, open: g.open !== false }));
  }
  return val;
}
function localState() { const s = split(collectProject()); s.meta.name = baseName(); return s; }

/* ---- очередь: отправки и сведение чужого идут по одной ---- */
let chain = Promise.resolve();
function enqueue(fn) { const p = chain.then(() => fn()); chain = p.catch(e => console.warn("collab", e)); return p; }
let pushQueued = false, catchQueued = false, lastBy = null; const hint = new Set();
const queuePush = () => { if (pushQueued) return chain.then(() => true); pushQueued = true; return enqueue(async () => { pushQueued = false; return pushLoop(); }); };
function queueCatchUp(names, by) {
  (names || []).forEach(n => hint.add(n)); if (by) lastBy = by;
  if (catchQueued) return; catchQueued = true;
  enqueue(async () => { catchQueued = false; const h = [...hint]; hint.clear(); try { await catchUp(h); } catch (e) { netFail(e); } });
}
let timer = null, firstT = 0, retryMs = 0, retryT = null;
function schedulePush(ms) {
  if (!C.pid || !editable()) return;
  const now = Date.now(); if (!firstT) firstT = now;
  clearTimeout(timer); timer = setTimeout(() => { timer = null; firstT = 0; queuePush(); }, Math.max(0, Math.min(ms, firstT + 3000 - now)));
}
function netFail(e) {
  if (e) console.warn("collab: нет связи", e);
  setStatus("offline"); clearTimeout(retryT);
  retryMs = Math.min(30000, (retryMs || 1000) * 2); retryT = setTimeout(() => { retryT = null; if (C.pid) { queuePush(); if (!es) connect(); } }, retryMs);
}
/* правка проекта (project.js markDirty): отправка через 400 мс после последней, не реже раза в 3 с */
export function touched() {
  if (!C.on || !C.pid || applying) return;
  if (!editable()) { setStatus("readonly"); return; }
  schedulePush(400);
}
export function flush() {
  if (!C.on || !C.pid || !editable()) return Promise.resolve(true);
  clearTimeout(timer); timer = null; firstT = 0;
  return queuePush();
}

/* ---- отправка ---- */
async function pushOnce() {
  if (!C.pid) return "stop";
  if (!editable()) { setStatus("readonly"); return "stop"; }
  const secs = localState(), parts = [], sent = {};
  for (const n of Object.keys(secs)) if (!sameSection(n, secs[n], base[n])) { const t = secText(n, secs[n]); sent[n] = t; parts.push(JSON.stringify(n) + ":" + t); }
  for (const n of Object.keys(base)) if (!(n in secs)) { sent[n] = null; parts.push(JSON.stringify(n) + ":null"); }
  if (!parts.length) return "empty";
  setStatus("sending");
  let r;
  try { r = await http("POST", P("/push"), `{"base_rev":${C.rev},"client":${JSON.stringify(C.client)},"sections":{${parts.join(",")}}}`); }
  catch (e) { netFail(e); return "fail"; }
  if (r.status === 200) {
    const rev = r.json.rev; retryMs = 0;
    for (const n of Object.keys(sent)) { if (sent[n] == null) delete base[n]; else base[n] = sent[n]; secRev[n] = rev; }
    if (rev === C.rev + 1) C.rev = rev; else await catchUp([]);
    return "ok";
  }
  if (r.status === 409) {
    setStatus("conflict");
    const cf = r.json?.conflicts || {}, have = {}, sr = {};
    for (const n of Object.keys(cf)) { have[n] = cf[n].value ?? null; sr[n] = cf[n].rev; }
    integrate(have, sr, lastBy);
    await catchUp([]);
    return "conflict";
  }
  if (r.status === 403) { if (await refreshRole() === false) { lost("access"); return "stop"; } if (editable()) { setStatus("sending"); return "fail"; } return "stop"; }
  if (r.status === 404) { lost("deleted"); return "stop"; }
  if (r.status === 401) { authExpired(); return "stop"; }
  if (r.status === 507) { setStatus("full"); emit("fault", { message: r.json?.error || "хранилище на сервере заполнено" }); return "stop"; }
  netFail(new Error("push: HTTP " + r.status)); return "fail";
}
async function pushLoop() {
  let conflicts = 0;
  for (let i = 0; i < 40; i++) {
    const r = await pushOnce();
    if (r === "empty") { markSaved(); return true; }
    if (r === "ok") continue;
    if (r === "conflict") { if (++conflicts > 5) { await recover(); return false; } continue; }
    return false;
  }
  schedulePush(400); return false;
}
function markSaved() { retryMs = 0; setStatus("saved"); markClean(); }
async function recover(msg) {
  const r = await http("GET", P());
  if (!r.ok) { netFail(new Error("reload " + r.status)); return; }
  await loadProject(r.json, true);
  notice.value = msg || "Правки не удалось свести с чужими: проект загружен заново с сервера. Ваши последние изменения могли потеряться";
  markSaved();
}

/* ---- получение чужого ---- */
async function catchUp(names) {
  for (let i = 0; i < 6; i++) {
    const want = [...new Set(["meta", ...names])];
    if (!want.every(n => !n.includes(","))) return fullSync();
    const r = await http("GET", P("/sections?names=" + want.map(encodeURIComponent).join(",")));
    if (r.status === 401) return authExpired();
    if (r.status === 404 || r.status === 403) return lost(r.status === 403 ? "access" : "deleted");
    if (!r.ok || !r.json?.sec_rev) return fullSync();
    const { rev, sec_rev: sr, sections } = r.json;
    const need = Object.keys(sr).filter(n => sr[n] !== secRev[n]).concat(Object.keys(secRev).filter(n => !(n in sr)));
    if (!need.length) { C.rev = Math.max(C.rev, rev); return; }
    const have = {}, revs = {};
    for (const n of need) if (n in sections) { have[n] = sections[n] ?? null; revs[n] = sr[n]; }
    const miss = need.filter(n => n in sr && !(n in sections));
    if (miss.length) {
      if (miss.some(n => n.includes(","))) return fullSync();
      const r2 = await http("GET", P("/sections?names=" + miss.map(encodeURIComponent).join(",")));
      if (!r2.ok) return fullSync();
      for (const n of miss) { have[n] = r2.json.sections?.[n] ?? null; revs[n] = r2.json.sec_rev?.[n] ?? sr[n]; }
    }
    for (const n of need) if (!(n in sr)) { have[n] = null; revs[n] = undefined; }
    integrate(have, revs, lastBy);
    names = [];
  }
  return fullSync();
}
async function fullSync() {
  const r = await http("GET", P());
  if (r.status === 401) return authExpired();
  if (r.status === 404 || r.status === 403) return lost(r.status === 403 ? "access" : "deleted");
  if (!r.ok) throw new Error("HTTP " + r.status);
  const j = r.json, sr = j.sec_rev || null, have = {}, revs = {};
  updateRole(j.role);
  const names = new Set([...Object.keys(j.sections || {}), ...Object.keys(base)]);
  for (const n of names) {
    const v = normSection(n, j.sections?.[n] ?? null);
    const changed = sr ? sr[n] !== secRev[n] : secText(n, v) !== (base[n] ?? "null");
    if (changed || (v == null) !== (base[n] == null)) { have[n] = v; revs[n] = sr ? sr[n] : undefined; }
  }
  integrate(have, revs, lastBy);
  C.rev = j.rev;
}
function lost(reason) { emit("deleted", { reason: reason || "deleted" }); close(); }
let dead = false;
function authExpired() { dead = true; setStatus("offline"); emit("session", { expired: true }); }

function integrate(have, revs, by) {
  const names = Object.keys(have);
  if (!names.length) return;
  for (const n of names) have[n] = normSection(n, have[n]);
  const local = localState(), res = {}, info = { conflicts: [] }, nb = {};
  for (const n of names) {
    const tv = have[n], mv = local[n] ?? null;
    res[n] = sameSection(n, mv, base[n]) ? tv : merge3(base[n] == null ? null : JSON.parse(base[n]), mv, tv, n, info);
    nb[n] = tv == null ? null : secText(n, tv);
  }
  try { applyResults(res, local); }
  catch (e) { console.error("collab: применение чужих правок", e); enqueue(() => recover("Чужие правки применились не полностью: проект загружен заново с сервера")); }
  for (const n of names) { if (nb[n] == null) delete base[n]; else base[n] = nb[n]; if (revs && n in revs) { if (revs[n] === undefined) delete secRev[n]; else secRev[n] = revs[n]; } }
  if (info.conflicts.length) {
    const lab = { territory: "границе", checked: "наборе источников", groups: "группах слоёв", views: "видах", album: "альбоме", graph: "схеме расчёта", imports: "источниках", current_order: "порядке слоёв" };
    const what = [...new Set(info.conflicts)].map(k => lab[k] || (k.startsWith("album:") ? "альбоме (" + k.slice(6) + ")" : k)).join(", ");
    notice.value = `Ваши правки в ${what} совпали с правками ${by || "другого участника"}: оставлена их версия`;
  }
  emit("rev", { by: by || null, sections: names });
  if (!names.every(n => sameSection(n, local[n] ?? null, base[n]))) schedulePush(100);
}

/* ---- применение к открытому проекту: данные слоя — пришедший fc (карта переиспользует неизменённые объекты), описание слоя,
   граница, группы, виды, схема и альбом — на месте ---- */
function applyLayer(key, val) {
  const has = lyr(key);
  if (val == null) {
    if (!has) return false;
    project.layers.splice(project.layers.indexOf(has), 1); delete project.data[key]; return true;
  }
  const { spec, data } = val; if (!data) return false;
  const fc = data.fc || { type: "FeatureCollection", features: [] }, d = {};
  DATA_F.forEach(f => { if (data[f] !== undefined) d[f] = data[f]; });
  d.fc = fc; if (data.original === "=fc") d.original = fc; else if (data.original !== undefined) d.original = data.original;
  const prev = project.data[key];
  project.data[key] = prev && quick(prev.fc, fc) ? { ...d, fc: prev.fc, ...(data.original === "=fc" ? { original: prev.fc } : {}) } : d;
  const st = fullStyle(spec.style || {}), at = { title: spec.title ?? has?.title ?? key, geom: spec.geom || has?.geom || "poly", visible: spec.visible !== false,
    layerOpacity: okn(spec.layerOpacity, 1), open: !!spec.open, ...(spec.role ? { role: spec.role } : {}) };
  if (!has) { project.layers.push({ key, ...at, group: null, style: st }); return true; }
  Object.assign(has, at); if (!spec.role) delete has.role;
  if (!same(toRaw(has.style), st)) has.style = st;
  return false;
}
function applyMeta(meta, mine) {
  const ch = k => !same(meta[k], mine?.[k]);
  if (meta.name && meta.name !== project.name) project.name = meta.name;
  if (ch("territory")) project.territory = meta.territory?.geometry ? meta.territory : null;
  if (ch("checked")) project.raw.checked = [...(meta.checked || [])];
  if (ch("imports")) {
    const imp = safeObj(meta.imports); project.raw.imports = imp;
    Object.keys(SOURCES).filter(k => (k.startsWith("import:") || SOURCES[k].kind === "fgistp") && !(k in imp)).forEach(k => delete SOURCES[k]);
    Object.entries(imp).forEach(([k, s]) => { if (isObj(s)) SOURCES[k] = { ...s, title: String(s.title ?? k), kind: String(s.kind ?? "import") }; });
  }
  if (ch("groups")) project.groups.splice(0, project.groups.length, ...(meta.groups || []).map(g => ({ id: g.id, title: g.title || g.id, visible: g.visible !== false, open: g.open !== false })));
  if (ch("views")) project.views.splice(0, project.views.length, ...(meta.views || []).filter(v => v && v.id).map(v => JSON.parse(JSON.stringify(v))));
  if (ch("graph") && meta.graph) { project.raw.graph = JSON.parse(JSON.stringify(meta.graph)); graphHooks.restored(); }
}
function applyResults(res, local) {
  applying = true;
  try {
    external(() => {
      const layerNames = Object.keys(res).filter(isLayerName);
      let structure = false;
      for (const n of layerNames) structure = applyLayer(n.slice(6), res[n]) || structure;
      if (res.meta) applyMeta(res.meta, local.meta);
      if (res.album && !same(res.album, local.album)) project.raw.album = res.album;
      for (const n of layerNames) if (res[n]) { const l = lyr(n.slice(6)); if (l) l.group = res[n].spec.group || null; }
      const order = res.meta ? res.meta.current_order : null;
      if (order && (structure || !same(order, local.meta?.current_order))) {
        const ix = k => { const i = order.indexOf(k); return i < 0 ? 1e9 : i; };
        project.layers.splice(0, project.layers.length, ...[...project.layers].sort((a, b) => ix(a.key) - ix(b.key)));
      }
      normGroups();
      if (!lyr(currentId.value)) currentId.value = project.layers[0]?.key || "";
    });
  } finally { setTimeout(() => { applying = false; }, 0); }    // наблюдатели за слоями отработали — это не моя правка
}

/* ---- проект: загрузка, открытие, закрытие; вид карты и текущий слой — личные, помнит браузер ---- */
const VKEY = pid => "grado2.hub.view." + pid;
function savePersonal() {
  if (!C.pid || !viewNow.center) return;
  try { localStorage.setItem(VKEY(C.pid), JSON.stringify({ view: { center: viewNow.center, zoom: viewNow.zoom }, current: currentId.value })); } catch { /* частный режим */ }
}
function personal(keep) {
  if (keep && viewNow.center) return { view: { center: viewNow.center, zoom: viewNow.zoom }, current: currentId.value };
  try { const s = JSON.parse(localStorage.getItem(VKEY(C.pid)) || "null"); if (s?.view?.center) return { view: s.view, current: s.current }; } catch { /* нет */ }
  return {};
}
async function loadProject(j, keepView) {
  const secs = j.sections || {};
  for (const n of Object.keys(secs)) secs[n] = normSection(n, secs[n]);
  C.rev = j.rev; secRev = { ...(j.sec_rev || {}) }; base = {}; LC = new Map(); bm = null; ba = null;
  for (const n of Object.keys(secs)) if (secs[n] != null) base[n] = secText(n, secs[n]);
  applying = true;
  try {
    const p = join(secs, personal(keepView));
    Object.keys(SOURCES).filter(k => k.startsWith("import:") || SOURCES[k].kind === "fgistp").forEach(k => delete SOURCES[k]);
    Object.entries(safeObj(p.imports)).forEach(([k, s]) => { if (isObj(s)) SOURCES[k] = { ...s, title: String(s.title ?? k), kind: String(s.kind ?? "import") }; });
    await loadShared(p, j.name ?? p.name);
  } finally { applying = false; }
  updateRole(j.role, true);
}
function updateRole(role, silent) {
  if (!role || role === C.role) return;
  const was = C.role; C.role = role;
  if (!silent) emit("role", { role });
  if (role === "viewer") setStatus("readonly"); else if (was === "viewer") { setStatus("saved"); schedulePush(100); }
}
async function refreshRole() {
  try { const r = await http("GET", "/api/hub/projects"); if (r.status === 401) { authExpired(); return null; } if (!r.ok) return null; const p = r.json?.projects?.find(x => x.id === C.pid); if (p) updateRole(p.role); return !!p; } catch { return null; }
}

/* ---- события сервера (SSE) ---- */
let es = null, esT = null, esMs = 0, wasDown = false, pollT = null;
function connect() {
  if (!C.pid || es) return;
  const pid = C.pid; es = new EventSource(P("/events"));
  es.onopen = () => {
    esMs = 0; clearTimeout(esT); clearInterval(pollT);
    if (wasDown) { wasDown = false; enqueue(async () => { try { await fullSync(); if (C.status === "offline") setStatus("saved"); schedulePush(100); } catch (e) { netFail(e); } }); }
    else queueCatchUp([]);
    if (C.status === "offline") { setStatus("saved"); schedulePush(100); }
  };
  es.onmessage = e => { if (C.pid !== pid) return; let ev; try { ev = JSON.parse(e.data); } catch { return; } onEvent(ev); };
  es.onerror = () => { if (C.pid !== pid) return; try { es.close(); } catch { /* уже закрыт */ } es = null; wasDown = true; probeStream(pid); };
}
async function probeStream(pid) {
  clearTimeout(esT); let st = 0;
  const ac = new AbortController();
  try { st = (await fetch(P("/events"), { credentials: "same-origin", signal: ac.signal })).status; } catch { st = 0; }
  ac.abort();
  if (C.pid !== pid || es) return;
  if (st === 401) return authExpired();
  if (st === 403 || st === 404) return lost(st === 403 ? "access" : "deleted");
  if (st === 429) { emit("limit", {}); clearInterval(pollT); pollT = setInterval(() => { if (C.pid && !es) queueCatchUp([]); }, 10000); esT = setTimeout(connect, 60000); return; }
  setStatus("offline"); esMs = Math.min(30000, (esMs || 1000) * 2); esT = setTimeout(connect, esMs);
}
function onEvent(ev) {
  if (ev.type === "rev") { if (ev.client !== C.client) queueCatchUp(ev.sections, ev.by); }
  else if (ev.type === "presence") emit("presence", { users: ev.users || [] });
  else if (ev.type === "comments") emit("comments", ev);
  else if (ev.type === "members") refreshRole().then(ok => { if (ok === false) lost("access"); else emit("members", ev); });
  else if (ev.type === "deleted") lost("deleted");
}

/* ---- открытые входы ---- */
export function init(user) { C.on = true; C.user = user || null; }
export async function open(pid) {
  if (!C.on) throw new Error("совместный режим не включён");
  if (C.pid) close();
  const r = await http("GET", `/api/hub/project/${pid}`);
  if (!r.ok) throw new Error(r.json?.error || "проект не открылся (код " + r.status + ")");
  C.pid = pid; C.role = null; C.status = "saved";
  await loadProject(r.json, false);
  setStatus(C.role === "viewer" ? "readonly" : "saved");
  connect();
  schedulePush(150);                                  // номера `_uid`, проставленные при загрузке, — одной отправкой
}
export function resume() { dead = false; if (!C.on || !C.pid) return Promise.resolve(true); clearTimeout(esT); esMs = 0; if (!es) connect(); return flush(); }
export function close() {
  savePersonal();
  clearTimeout(timer); clearTimeout(retryT); clearTimeout(esT); clearInterval(pollT); timer = retryT = esT = pollT = null; firstT = retryMs = esMs = 0;
  if (es) { try { es.close(); } catch { /* уже закрыт */ } es = null; }
  Object.assign(C, { pid: null, rev: 0, role: null }); base = {}; secRev = {}; LC = new Map(); bm = null; ba = null; wasDown = false; pushQueued = catchQueued = false; hint.clear();
  if (C.status !== "saved") { C.status = "saved"; emit("status", { state: "saved" }); }
}
export async function createFromLocal(name) {
  if (!C.on) throw new Error("совместный режим не включён");
  const body = JSON.stringify({ name }).slice(0, -1) + ',"project":' + projectJSON() + "}";
  const r = await http("POST", "/api/hub/projects", body);
  if (!r.ok) throw new Error(r.json?.error || "проект не создан (код " + r.status + ")");
  await open(r.json.id); return { id: r.json.id };
}
/* положение указателя, выбор и текущий слой — другим участникам, не чаще двух раз в секунду */
let pres = {}, presT = 0, presTimer = null;
function sendPresence() {
  presTimer = null; presT = Date.now();
  if (!C.on || !C.pid || dead) return;
  http("POST", P("/presence"), { client: C.client, cursor: pres.cursor ?? null, layer: pres.layer ?? null, sel: pres.sel || [] }).then(r => { if (r.status === 401) authExpired(); }).catch(() => { /* следующий раз */ });
}
export function presence(p) {
  Object.assign(pres, p || {});
  if (!C.on || !C.pid || presTimer) return;
  presTimer = setTimeout(sendPresence, Math.max(0, 500 - (Date.now() - presT)));
}
export const busyPush = () => !!timer || ["sending", "offline", "conflict"].includes(C.status);

addEventListener("pagehide", () => savePersonal());
addEventListener("beforeunload", e => { if (C.on && C.pid && editable() && busyPush()) { e.preventDefault(); e.returnValue = ""; } });
