/* ГРАДО 2 · совместная работа: движок синхронизации (контракт — docs/grado2-collab-spec.md).
   Сервер хранит проект целиком, разбитым на разделы, и нумерует правки; клиенты сводят правки сами:
   · разделы: «meta» (граница, группы, виды, альбом, граф, источники, порядок слоёв) и «layer:<ключ>» = {spec, data};
   · после каждой правки (markDirty → Collab.touched) с паузой 400 мс (не дольше 3 с) меняются только изменившиеся разделы;
   · сервер отвечает 409, если раздел успел поменять кто-то ещё: правки сводятся по трём версиям (база, моя, чужая):
     объекты слоя — по `_uid`, свойства — по полям, остальное — по ключам; затем отправка повторяется;
   · чужие правки (SSE) применяются к открытому проекту без clearProject: объекты слоя правятся на месте
     (выбор, отмена и вид карты остаются), слои, группы, виды, альбом и граф обновляются точечно.
   Локальный режим (Collab.on === false): все входы — пустые функции, ничего не меняется.
   Чистая часть (split/join/merge3) работает и под node — тесты tests/collab_test.js. */
(function (root) {
"use strict";
const PV = typeof PROJ_VERSION !== "undefined" ? PROJ_VERSION : 2;
const EMPTY_FC = Object.freeze({ type: "FeatureCollection", features: Object.freeze([]) });

/* ================= чистая часть: разбиение, склейка, слияние ================= */

// канонический текст значения: ключи по алфавиту, undefined пропускается — порядок ключей не считается правкой
function stable(v) {
  if (v === undefined) return "u";
  if (v === null || typeof v !== "object") return JSON.stringify(v);
  if (Array.isArray(v)) return "[" + v.map(stable).join(",") + "]";
  return "{" + Object.keys(v).sort().filter(k => v[k] !== undefined).map(k => JSON.stringify(k) + ":" + stable(v[k])).join(",") + "}";
}
const same = (a, b) => a === b || stable(a) === stable(b);
const isObj = v => v && typeof v === "object" && !Array.isArray(v);
// быстрый текст для крупных объектов (у слоя в 100 000 объектов — из кэша jsonOf проекта, если он есть)
const js = o => (typeof jsonOf === "function" && o && typeof o === "object") ? jsonOf(o) : JSON.stringify(o);
const quick = (a, b) => a === b || js(a) === js(b);

// объект слоя для сравнения: координаты до 1e-9° (0,1 мм) — круговой пересчёт 4326 ↔ 3857 даёт шум в последних знаках
const R9 = x => Math.round(x * 1e9) / 1e9;
const cg = c => typeof c === "number" ? R9(c) : c.map(cg);
function canonGeom(g) {
  if (!g) return "null";
  if (g.type === "GeometryCollection") return "GC[" + (g.geometries || []).map(canonGeom).join(",") + "]";
  return g.type + JSON.stringify(cg(g.coordinates || []));
}
const CF = new WeakMap();
function canonF(f) {
  let t = CF.get(f);
  if (t === undefined) { const { gradosym, ...p } = f.properties || {}; t = canonGeom(f.geometry) + "|" + stable(p); CF.set(f, t); }
  return t;
}
const sameF = (a, b) => a === b || canonF(a) === canonF(b);

// 12 знаков hex из текста (два 32-разрядных хэша): детерминированный номер для объекта, у которого его ещё нет
function h12(s) {
  let a = 0x811c9dc5, b = 0x9747b28c;
  for (let i = 0; i < s.length; i++) { const c = s.charCodeAt(i); a = Math.imul(a ^ c, 16777619); b = Math.imul(b ^ c, 0x5bd1e995); b ^= b >>> 15; }
  return ((a >>> 0).toString(16).padStart(8, "0") + (b >>> 0).toString(16).padStart(8, "0")).slice(0, 12);
}
/* Всем объектам слоя — `_uid`. Номер объекта, у которого его нет (файл из старой версии, проект, загруженный на сервер),
   считается из ключа слоя, места в списке и геометрии: у всех участников он получается одинаковым, и два человека,
   открывшие такой проект одновременно, не плодят двойников. Вход не меняется: нужен номер — возвращается копия. */
/* Перевыгрузка слоя: объект источника, который уже есть на карте (тот же `_key`), сохраняет прежний `_uid` —
   иначе номер считается заново из места в списке и геометрии, и совместная работа теряет все объекты. Вход не меняется. */
function keepUid(fresh, cur) {
  const u = cur?.properties?._uid; if (!u || fresh?.properties?._uid === u) return fresh;
  return { ...fresh, properties: { ...(fresh.properties || {}), _uid: u } };
}
function ensureUids(fc, salt) {
  const fs = fc?.features; if (!Array.isArray(fs)) return fc;
  const seen = new Set(); let out = null;
  fs.forEach((f, i) => {
    let u = f.properties?._uid;
    if (!u || seen.has(u)) {
      u = h12(salt + "|" + i + "|" + (u || "") + "|" + JSON.stringify(f.geometry));
      if (!out) out = fs.slice();
      out[i] = { ...f, properties: { ...(f.properties || {}), _uid: u } };
    }
    seen.add(u);
  });
  return out ? { ...fc, features: out } : fc;
}
const uidMap = fc => { const m = new Map(); for (const f of fc?.features || []) m.set(f.properties._uid, f); return m; };

/* split: проект (форма collectProject()) → разделы. Ссылки на части проекта, не копии. */
function split(p) {
  const layers = p.layers || [], s = {};
  const terr = p.territory ? (({ _gid, ...t }) => t)(p.territory) : null;      // _gid — метка в памяти (app.js gid()), у каждого участника своя
  s.meta = { name: p.name ?? null, territory: terr, checked: [...(p.checked || [])].sort(), groups: p.groups || [], views: p.views || [],
    album: p.album || { meta: {}, sheets: [] }, graph: p.graph ?? null, imports: p.imports || {}, current_order: layers.map(l => l.key) };
  for (const l of layers) s["layer:" + l.key] = { spec: l, data: p.data?.[l.key] ?? null };
  return s;
}
/* join: разделы (+ личное: view, current, file, app) → проект в обычном формате .grado2. Слой, которого нет в
   current_order, встаёт в конец; ключ из порядка без раздела пропускается. */
function join(sec, personal) {
  personal = personal || {}; const m = sec.meta || {};
  const keys = Object.keys(sec).filter(n => n.startsWith("layer:") && sec[n] && sec[n].spec).map(n => n.slice(6));
  const order = [...new Set((m.current_order || []).filter(k => keys.includes(k)).concat(keys))];
  const data = {}; order.forEach(k => { const d = sec["layer:" + k].data; if (d) data[k] = d; });
  const p = { format: "grado2", version: PV, app: personal.app || "ГРАДО 2", name: m.name ?? null, file: personal.file ?? null, saved_at: new Date().toISOString() };
  if (personal.view) p.view = personal.view;
  Object.assign(p, { territory: m.territory ?? null, imports: m.imports || {}, checked: m.checked || [] });
  if (personal.current !== undefined) p.current = personal.current;
  Object.assign(p, { groups: m.groups || [], views: m.views || [], album: m.album || { meta: {}, sheets: [] }, layers: order.map(k => sec["layer:" + k].spec), data });
  if (m.graph) p.graph = m.graph;
  return p;
}

// свойства по полям: одно поле правил только одна сторона — берётся её; обе, по-разному — чужое (оно ушло на сервер раньше)
function mergeObj(b, m, t, info, depth) {
  b = b || {}; m = m || {}; t = t || {};
  const out = {};
  for (const k of new Set([...Object.keys(b), ...Object.keys(m), ...Object.keys(t)])) {
    const bv = b[k], mv = m[k], tv = t[k], mc = !same(mv, bv), tc = !same(tv, bv);
    let v;
    if (!mc) v = tv; else if (!tc) v = mv; else if (same(mv, tv)) v = mv;
    else if (depth > 0 && isObj(bv) && isObj(mv) && isObj(tv)) v = mergeObj(bv, mv, tv, info, depth - 1);
    else { v = tv; info?.conflicts.push(k); }
    if (v !== undefined) out[k] = v;
  }
  return out;
}
function mergeFeature(b, m, t) {
  const gm = canonGeom(b.geometry) !== canonGeom(m.geometry), gt = canonGeom(b.geometry) !== canonGeom(t.geometry);
  const geometry = !gm ? t.geometry : !gt ? m.geometry : (canonGeom(m.geometry) === canonGeom(t.geometry) ? m.geometry : t.geometry);
  const { gradosym: _a, ...bp } = b.properties || {}, { gradosym: _b, ...mp } = m.properties || {}, { gradosym: _c, ...tp } = t.properties || {};
  return { ...t, type: "Feature", geometry, properties: mergeObj(bp, mp, tp, null, 0) };
}
// одно решение по одному объекту; b, m, t — версии (undefined — объекта нет)
function decide(b, m, t) {
  if (m && t) {
    if (!b) return sameF(m, t) ? m : mergeFeature({ properties: {}, geometry: null }, m, t);
    const mc = !sameF(b, m), tc = !sameF(b, t);
    return !mc ? t : !tc ? m : sameF(m, t) ? m : mergeFeature(b, m, t);
  }
  if (m) return !b || !sameF(b, m) ? m : null;       // у них удалён: если я правил — остаётся (правка побеждает удаление)
  if (t) return !b || !sameF(b, t) ? t : null;       // у меня удалён: если они правили — остаётся
  return null;
}
function mergeFC(bfc, mfc, tfc, salt) {
  if (mfc && bfc && quick(mfc, bfc)) return tfc;      // быстрые случаи: одна сторона слой не трогала
  if (tfc && bfc && quick(tfc, bfc)) return mfc;
  if (mfc && tfc && quick(mfc, tfc)) return mfc;
  const B = uidMap(ensureUids(bfc || EMPTY_FC, salt)), Mf = ensureUids(mfc || EMPTY_FC, salt), Tf = ensureUids(tfc || EMPTY_FC, salt);
  const M = uidMap(Mf), T = uidMap(Tf), out = [];
  for (const [u, m] of M) { const r = decide(B.get(u), m, T.get(u)); if (r) out.push(r); }
  for (const [u, t] of T) if (!M.has(u)) { const r = decide(B.get(u), undefined, t); if (r) out.push(r); }
  return { ...(mfc || tfc || bfc || {}), type: "FeatureCollection", features: out };
}
function mergeLayer(b, m, t, salt) {
  b = b || { spec: {}, data: {} };
  const spec = mergeObj(b.spec, m.spec, t.spec, null, 1);         // поля слоя — по одному; у стиля — по его полям
  const bd = b.data || {}, md = m.data || {}, td = t.data || {};
  const { fc: bf, ...br } = bd, { fc: mf, ...mr } = md, { fc: tf, ...tr } = td;
  const rest = mergeObj(br, mr, tr, null, 0);
  if (!b.data && !m.data && !t.data) return { spec, data: null };
  return { spec, data: { ...rest, fc: mergeFC(bf, mf, tf, salt) } };
}
// порядок слоёв: чужой порядок + слои, добавленные мной, на своём месте (после соседа слева); убранные мной и не тронутые ими — убираются
function mergeOrder(b, m, t) {
  b = b || []; m = m || []; t = t || [];
  const bs = new Set(b), ms = new Set(m);
  const out = t.filter(k => !(bs.has(k) && !ms.has(k))), has = new Set(out);
  m.forEach((k, i) => { if (has.has(k)) return; const at = i ? out.indexOf(m[i - 1]) + 1 : 0; out.splice(at, 0, k); has.add(k); });
  return out;
}
function mergeMeta(b, m, t, info) {
  b = b || {};
  const out = {};
  for (const k of new Set([...Object.keys(b), ...Object.keys(m), ...Object.keys(t)])) {
    const bv = b[k], mv = m[k], tv = t[k], mc = !same(mv, bv), tc = !same(tv, bv);
    let v;
    if (!mc) v = tv; else if (!tc) v = mv; else if (same(mv, tv)) v = mv;
    else if (k === "current_order") v = mergeOrder(bv, mv, tv);
    else if (k === "imports" && isObj(mv) && isObj(tv)) { const sub = { conflicts: [] }; v = mergeObj(bv, mv, tv, sub, 0); if (sub.conflicts.length && info) info.conflicts.push(k); }
    else { v = tv; info?.conflicts.push(k); }                      // обе стороны правили ключ по-разному: оставлена их версия
    if (v !== undefined) out[k] = v;
  }
  return out;
}
function eqLayer(a, b) {
  const { fc: af, ...ar } = a.data || {}, { fc: bf, ...br } = b.data || {};
  return same(a.spec, b.spec) && same(ar, br) && (af === bf || (af && bf ? quick(af, bf) : false));
}
/* merge3: слияние раздела. base — общая прежняя версия, mine — моя, theirs — чужая (null — раздела нет).
   info (необязательно) собирает info.conflicts — ключи раздела, где правки совпали и взята чужая версия. */
function merge3(base, mine, theirs, sectionName, info) {
  base = base ?? null; mine = mine ?? null; theirs = theirs ?? null;
  const layer = /^layer:/.test(sectionName || "");
  // слой сравнивается по частям: крупные данные — через кэш текста, а не целиком
  const eq = (a, b) => a === b || (a && b ? (layer ? eqLayer(a, b) : same(a, b)) : false);
  if (eq(mine, base)) return theirs;                  // я не менял — беру чужое
  if (eq(theirs, base)) return mine;                  // они не меняли — остаётся моё
  if (eq(mine, theirs)) return mine;
  if (mine === null) return theirs;                   // я удалил, они правили — правка побеждает удаление
  if (theirs === null) return mine;                   // они удалили, я правил — слой возвращается
  return layer ? mergeLayer(base, mine, theirs, sectionName) : mergeMeta(base, mine, theirs, info);
}

/* ================= часть в браузере: обмен с сервером и применение к открытому проекту ================= */
function install() {
const C = { on: false, pid: null, rev: 0, role: null, user: null, client: Array.from(crypto.getRandomValues(new Uint8Array(8)), b => b.toString(16).padStart(2, "0")).join(""),
  applying: false, status: "saved", split, join, merge3, keepUid };
root.Collab = C;
const L = {};
C.listen = (type, cb) => { (L[type] ||= []).push(cb); return () => { L[type] = (L[type] || []).filter(f => f !== cb); }; };
const emit = (type, data) => (L[type] || []).slice().forEach(f => { try { f(data); } catch (e) { console.warn("collab: слушатель", type, e); } });
function setStatus(state) { if (C.status === state) return; C.status = state; emit("status", { state }); }
const editable = () => C.role !== "viewer";

/* ---- обмен ---- */
async function http(method, path, body) {
  const o = { method, credentials: "same-origin", headers: {} };
  if (method !== "GET") { o.headers["Content-Type"] = "application/json"; o.body = typeof body === "string" ? body : JSON.stringify(body ?? {}); }
  const r = await fetch(path, o); let json = null; try { json = await r.json(); } catch { }
  return { ok: r.ok, status: r.status, json };
}
const P = tail => `/api/hub/project/${C.pid}${tail || ""}`;

/* ---- состояние: база (последнее согласованное, по разделам — текстом JSON) ---- */
let base = {}, secRev = {}, LC = new Map(), bm = null;
const isLayerName = n => n.startsWith("layer:");
/* Текст раздела. Слой: крупные fc/original берутся из кэша jsonOf по самому объекту, а готовый текст слоя — из своего кэша,
   пока объекты данных те же: слои без правок не сериализуются и не копируются заново. */
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
function sameSection(name, val, text) {
  if (val == null) return text == null;
  if (text == null) return false;
  if (name === "meta") { const b = baseMeta(); return (b.s ??= stable(b.v)) === stable(val); }   // ключи графа и шум порядка — не правка
  return secText(name, val) === text;
}
function baseName() { return baseMeta().v?.name ?? null; }
// номера `_uid` во всех объектах слоя раздела (в самом разделе: он только что пришёл по сети)
function normSection(name, val) {
  if (val && isLayerName(name) && val.data?.fc) val.data.fc = ensureUids(val.data.fc, name.slice(6));
  if (val && name === "meta" && val.territory?._gid) val.territory = (({ _gid, ...t }) => t)(val.territory);
  if (val && name === "meta") {                       // то, что приложение и так приводит к норме при загрузке: иначе разница с сервером выглядела бы моей правкой
    if (Array.isArray(val.checked)) val.checked = [...val.checked].sort();                 // как у split: порядок Set — не правка
    if (val.album) val.album = { ...val.album, meta: { object: "", code: "", stage: "ПП", org: "", slide: "P", ...(isObj(val.album.meta) ? val.album.meta : {}) } };
    if (Array.isArray(val.groups)) val.groups = val.groups.map(g => ({ id: g.id, title: g.title, visible: g.visible !== false, open: g.open !== false }));
  }
  return val;
}
// мои разделы: как они сейчас на карте. Название проекта хаб ставит сам — своей правкой оно не считается
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
C.touched = function () {
  if (!C.on || !C.pid || C.applying || (typeof PROJ !== "undefined" && PROJ.loading)) return;
  if (!editable()) { setStatus("readonly"); return; }
  schedulePush(400);
};
C.flush = function () {
  if (!C.on || !C.pid || !editable()) return Promise.resolve(true);
  clearTimeout(timer); timer = null; firstT = 0;
  return queuePush();
};

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
    // ревизия растёт на 1 за отправку: если скачок больше, пока мы отправляли, кто-то отправил своё — сначала подтянуть его
    if (rev === C.rev + 1) C.rev = rev; else await catchUp([]);
    return "ok";
  }
  if (r.status === 409) {
    setStatus("conflict");
    const cf = r.json?.conflicts || {}, have = {}, sr = {};
    for (const n of Object.keys(cf)) { have[n] = cf[n].value ?? null; sr[n] = cf[n].rev; }
    integrate(have, sr, lastBy);
    await catchUp([]);                                // остальные разделы, которые ушли вперёд, — до повторной отправки
    return "conflict";
  }
  if (r.status === 403) { if (await refreshRole() === false) { lost("access"); return "stop"; } if (editable()) { setStatus("sending"); return "fail"; } return "stop"; }
  if (r.status === 404) { lost("deleted"); return "stop"; }
  if (r.status === 401) { authExpired(); return "stop"; }
  if (r.status === 507) { setStatus("full"); emit("fault", { message: r.json?.error || "хранилище на сервере заполнено" }); return "stop"; }   // правки остаются на экране; повтор — со следующей правкой
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
  schedulePush(400); return false;                    // правки идут непрерывно: отдельный заход
}
function markSaved() {
  retryMs = 0; setStatus("saved");
  if (typeof PROJ !== "undefined" && PROJ.dirty) { PROJ.dirty = false; PROJ.autoTick = PROJ.tick; PROJ.savedTick = PROJ.tick; syncProjTitle(); }
}
// пять сведений подряд не сошлись: проект заново с сервера (свои несохранённые правки теряются — об этом сказано)
async function recover(msg) {
  const r = await http("GET", P());
  if (!r.ok) { netFail(new Error("reload " + r.status)); return; }
  loadProject(r.json, true);
  toast(msg || "Правки не удалось свести с чужими: проект загружен заново с сервера. Ваши последние изменения могли потеряться.");
  markSaved();
}

/* ---- получение чужого ---- */
/* Подтянуть всё, что на сервере ушло вперёд от базы. Инвариант: C.rev — ревизия, на которой вся база совпадает с сервером
   (кроме моих неотправленных правок); по нему сервер ловит конфликты, поэтому растёт он только после подтягивания. */
async function catchUp(names) {
  for (let i = 0; i < 6; i++) {
    const want = [...new Set(["meta", ...names])], plain = want.every(n => !n.includes(","));
    if (!plain) return fullSync();
    let r = await http("GET", P("/sections?names=" + want.map(encodeURIComponent).join(",")));
    if (r.status === 401) return authExpired();
    if (r.status === 404 || r.status === 403) return lost(r.status === 403 ? "access" : "deleted");
    if (!r.ok || !r.json?.sec_rev) return fullSync();
    let { rev, sec_rev: sr, sections } = r.json;
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
    names = [];                                       // проверить ещё раз: пока тянули, сервер мог уйти дальше
  }
  return fullSync();
}
// полное сведение: весь проект с сервера против базы (после обрыва связи и когда точечное подтягивание не вышло)
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
// проект удалён (404) или доступ снят (403): закрыть и сказать, почему
function lost(reason) { emit("deleted", { reason: reason || "deleted" }); close(); }
// сессия кончилась (другой вход сменил пароль, срок, выход в другой вкладке): экран входа; правки остаются на экране, после входа — C.resume()
let dead = false;
function authExpired() { dead = true; setStatus("offline"); emit("session", { expired: true }); }

/* Сведение пришедших разделов с моими неотправленными правками и применение к карте. have: имя → значение (null — удалён),
   revs: имя → ревизия раздела на сервере. */
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
  try { applyResults(res, local, nb); }
  catch (e) { console.error("collab: применение чужих правок", e); enqueue(() => recover("Чужие правки применились не полностью: проект загружен заново с сервера.")); }
  for (const n of names) { if (nb[n] == null) delete base[n]; else base[n] = nb[n]; if (revs && n in revs) { if (revs[n] === undefined) delete secRev[n]; else secRev[n] = revs[n]; } }
  if (info.conflicts.length) {
    const lab = { territory: "границе", checked: "наборе источников", groups: "группах слоёв", views: "видах", album: "альбоме", graph: "схеме расчёта", imports: "источниках", current_order: "порядке слоёв" };
    const what = [...new Set(info.conflicts)].map(k => lab[k] || k).join(", ");
    toast(`Ваши правки в ${what} совпали с правками ${by || "другого участника"}: оставлена их версия.`);
  }
  emit("rev", { by: by || null, sections: names });
  if (!names.every(n => sameSection(n, local[n] ?? null, base[n]))) schedulePush(100);   // моё, не вошедшее в чужое, надо отправить
}

/* ---- применение к открытому проекту (без clearProject) ---- */
const typing = () => { const a = document.activeElement; return !!(a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName) && a.closest("#rightPane, #attrBody")); };
function diffApply(key, mineFc, newFc) {
  const src = layerSrc[key], live = new Map(src.getFeatures().map(f => [f.get("_uid"), f]));
  const mine = uidMap(mineFc ? ensureUids(mineFc, key) : EMPTY_FC), now = uidMap(newFc), add = [], rm = [], chg = [];
  for (const [u, nf] of now) { const lf = live.get(u); if (!lf) add.push(nf); else { const mf = mine.get(u); if (!mf || !sameF(mf, nf)) chg.push([lf, nf]); } }
  for (const [u, lf] of live) if (!now.has(u)) rm.push(lf);
  for (const [lf, nf] of chg) {
    const g = GJ.readFeature(nf), p = g.getProperties(), gn = g.getGeometryName();
    lf.getKeys().forEach(k => { if (k !== lf.getGeometryName() && k !== SYMK && !(k in p)) lf.unset(k, true); });
    const { [gn]: geom, ...props } = p; lf.setProperties(props, true); lf.setGeometry(geom); lf.changed();
  }
  if (rm.length) src.removeFeatures(rm);
  if (add.length) src.addFeatures(GJ.readFeatures({ type: "FeatureCollection", features: add }));
  return add.length + rm.length + chg.length;
}
function createLayerFrom(key, val) {
  const { spec, data } = val, fc = data.fc || { type: "FeatureCollection", features: [] };
  DATA[key] = { ...data, fc, count: 0, fields: [] };
  if (data.original === "=fc") delete DATA[key].original;
  layerSrc[key] ||= new ol.source.Vector(); setLayerData(key, DATA[key].fc, true);
  if (!data.original) delete DATA[key].original;
  if (!fc.features.length) DATA[key].fields = ["Наименование", "Примечание"];
  const l = ensureLayer(key, spec.title, spec.geom);
  Object.assign(l, { visible: spec.visible, layerOpacity: okn(spec.layerOpacity, 1), open: !!spec.open, style: ST(spec.style || {}) });
  return l;
}
function applyLayer(key, val, mine, restyled) {
  if (val == null) { if (lyr(key)) { dropLayer(key); return true; } return false; }
  const { spec, data } = val; if (!data) return false;
  if (!lyr(key) || !DATA[key]) { restyled.push(createLayerFrom(key, val)); return true; }
  const d = DATA[key], l = lyr(key);
  for (const f of ["title", "source", "fetched_at", "notes", "history", "shp"]) if (!same(d[f], data[f])) d[f] = data[f];
  const newFc = data.fc || { type: "FeatureCollection", features: [] }, mineFc = mine?.data?.fc;
  if (!(mineFc && quick(mineFc, newFc))) {
    if (diffApply(key, mineFc, newFc) || !mineFc) syncFromSource(key);
    d.fc = newFc;                                     // кэш данных — ровно то, что пришло: текст совпадёт с базой, эхо правок не возникает
    if (SEL.some(x => x.key === key)) setSel(SEL);
  }
  if (data.original === "=fc") d.original = newFc; else if (data.original === undefined) delete d.original; else if (data.original !== mine?.data?.original) d.original = data.original;
  if (spec.title != null) l.title = spec.title;
  if (spec.geom) l.geom = spec.geom;
  Object.assign(l, { visible: spec.visible, layerOpacity: okn(spec.layerOpacity, 1), open: !!spec.open });
  if (!same(spec.style || {}, l.style)) { l.style = ST(spec.style || {}); restyled.push(l); }
  return false;
}
function applyTerritory(t) {
  if (t) { const c = sharedView.getCenter(), z = sharedView.getZoom(); setTerritory(t); sharedView.setCenter(c); sharedView.setZoom(z); return; }   // чужая граница не сдвигает мой вид
  TERR = null; TERRSEL = false; TERR_M2 = 0; TERR_REV++; terrSrc.clear(); $("bLoad").disabled = true; dataRev++;
  $("terrInfo").textContent = "Граница не задана: нарисуйте её на карте (двойной щелчок завершает) или возьмите пример.";
}
function applyGraph(g) {
  const ds = typeof lgc !== "undefined" && lgc.ds ? { scale: lgc.ds.scale, offset: [...lgc.ds.offset] } : null;   // холст графа остаётся там, где я его оставил
  graph.configure(JSON.parse(JSON.stringify(g)));
  graph._nodes.forEach(n => n.widgets?.forEach(w => { if (w.value === undefined) w.value = (w.options?.min ?? 0) > 0 ? w.options.min : 0; }));
  if (ds) { lgc.ds.scale = ds.scale; lgc.ds.offset = ds.offset; }
  lastSig = ""; dataRev++; recompute(true); renderParams(); if (typeof lgc !== "undefined") lgc.setDirty(true, true);
}
function applyMeta(meta, mine, flags) {
  const ch = k => !same(meta[k], mine?.[k]);
  if (meta.name && meta.name !== PROJ.name) { PROJ.name = meta.name; syncProjTitle(); }
  if (ch("territory")) applyTerritory(meta.territory);
  if (ch("checked")) { CHECKED.clear(); (meta.checked || []).forEach(k => CHECKED.add(k)); flags.sources = true; }
  if (ch("imports")) {
    Object.keys(SOURCES).filter(k => (k.startsWith("import:") || SOURCES[k].kind === "fgistp") && !(k in (meta.imports || {}))).forEach(k => delete SOURCES[k]);
    Object.entries(safeObj(meta.imports)).forEach(([k, s]) => { if (s && typeof s === "object") SOURCES[k] = { ...safeObj(s), title: String(s.title ?? k), kind: String(s.kind ?? "import") }; });
    flags.sources = true;
  }
  if (ch("groups")) GROUPS.splice(0, GROUPS.length, ...(meta.groups || []).map(g => ({ id: g.id, title: g.title, visible: g.visible !== false, open: g.open !== false })));
  if (ch("views")) { VIEWS.splice(0, VIEWS.length, ...(meta.views || []).map(v => ({ ...v, id: safeId(v.id) }))); if (VIEW_CUR && !VIEWS.some(v => v.id === VIEW_CUR)) VIEW_CUR = null; flags.views = true; }
  if (ch("album")) {
    const a = meta.album || {};
    Object.assign(ALBUM.meta, { object: "", code: "", stage: "ПП", org: "", slide: "P", builtAt: undefined, pdfAt: undefined, pptxAt: undefined }, safeObj(a.meta)); window.hideSheetFrame?.();
    ALBUM.sheets.splice(0, ALBUM.sheets.length, ...(a.sheets || []).map(s => { const x = { ...s }; if (x.scale != null) x.scale = okn(x.scale, 0); if (x.view != null) x.view = safeId(x.view); if (x.photos != null && !Array.isArray(x.photos)) delete x.photos; return x; }));
    ALBUM.frames = a.frames; window.migrateFrames?.(); flags.album = true;
  }
  if (ch("graph") && meta.graph) applyGraph(meta.graph);
}
function applyResults(res, local) {
  C.applying = true;
  try {
    const restyled = [], layerNames = Object.keys(res).filter(isLayerName);
    let structure = false;
    for (const n of layerNames) structure = applyLayer(n.slice(6), res[n], local[n], restyled) || structure;
    const flags = {};
    if (res.meta) applyMeta(res.meta, local.meta, flags);
    // группа слоя — после групп, порядок — после слоёв (пока слои приходят по одному, нормализация сочла бы группы пустыми)
    for (const n of layerNames) if (res[n]) { const l = lyr(n.slice(6)); if (l) l.group = res[n].spec.group || null; }
    const order = (res.meta ? res.meta.current_order : null);
    if (order && (structure || !same(order, local.meta?.current_order))) { const ix = k => { const i = order.indexOf(k); return i < 0 ? 1e9 : i; }; LYR.sort((a, b) => ix(a.key) - ix(b.key)); }
    normGroups(); restyled.forEach(l => { if (lyr(l.key)) restyle(l); }); applyOrder(); dataRev++;
    if (flags.album) { window.renderSheets?.(); window.redrawFrames?.(); window.setBySheet?.(!!ALBUM.meta.treeBySheet); }
    if (flags.views) window.renderViews?.();
    if (flags.sources) window.renderSources?.();
    renderTree(); if (!typing()) { renderRight(); renderTable(); }
    if (SEL.length) setSel(SEL);                      // ручки выбранных объектов — по новой геометрии
    window.syncStatus?.();
  } finally { C.applying = false; }
}

/* ---- проект: загрузка, открытие, закрытие ---- */
const VKEY = pid => "grado2.hub.view." + pid;
function savePersonal() {
  if (!C.pid) return;
  try { localStorage.setItem(VKEY(C.pid), JSON.stringify({ view: { center: ol.proj.toLonLat(sharedView.getCenter()), zoom: sharedView.getZoom() }, current: CUR })); } catch { }
}
function personal(keep) {
  if (keep) return { view: { center: ol.proj.toLonLat(sharedView.getCenter()), zoom: sharedView.getZoom(), basemap: BASE }, current: CUR };
  try { const s = JSON.parse(localStorage.getItem(VKEY(C.pid)) || "null"); if (s?.view?.center) return { view: { ...s.view, basemap: BASE }, current: s.current }; } catch { }
  return {};
}
// проект с сервера → на карту целиком (открытие и аварийная перезагрузка)
function loadProject(j, keepView) {
  const secs = j.sections || {};
  for (const n of Object.keys(secs)) secs[n] = normSection(n, secs[n]);
  C.rev = j.rev; secRev = { ...(j.sec_rev || {}) }; base = {}; LC = new Map(); bm = null;
  for (const n of Object.keys(secs)) if (secs[n] != null) base[n] = secText(n, secs[n]);
  C.applying = true;
  try { applyProject(join(secs, personal(keepView))); } finally { C.applying = false; }
  PROJ.name = j.name ?? PROJ.name; PROJ.file = null; PROJ.dirty = false; PROJ.autoTick = PROJ.savedTick = PROJ.tick; syncProjTitle();
  updateRole(j.role, true);
}
function updateRole(role, silent) {
  if (!role || role === C.role) return;
  const was = C.role; C.role = role;
  if (!silent) emit("role", { role });
  if (role === "viewer") setStatus("readonly"); else if (was === "viewer") { setStatus("saved"); schedulePush(100); }
}
async function refreshRole() {
  // true — проект в списке, false — доступа к нему больше нет, null — не удалось спросить (связи нет, сессия кончилась)
  try { const r = await http("GET", "/api/hub/projects"); if (r.status === 401) { authExpired(); return null; } if (!r.ok) return null; const p = r.json?.projects?.find(x => x.id === C.pid); if (p) updateRole(p.role); return !!p; } catch { return null; }
}

/* ---- события сервера (SSE) ---- */
let es = null, esT = null, esMs = 0, wasDown = false, pollT = null;
function connect() {
  if (!C.pid || es) return;
  const pid = C.pid; es = new EventSource(P("/events"));
  es.onopen = () => {
    esMs = 0; clearTimeout(esT); clearInterval(pollT);
    // правки, пришедшие между загрузкой проекта и подпиской (или за время обрыва), — подтянуть
    if (wasDown) { wasDown = false; enqueue(async () => { try { await fullSync(); if (C.status === "offline") setStatus("saved"); schedulePush(100); } catch (e) { netFail(e); } }); }
    else queueCatchUp([]);
    if (C.status === "offline") { setStatus("saved"); schedulePush(100); }
  };
  es.onmessage = e => { if (C.pid !== pid) return; let ev; try { ev = JSON.parse(e.data); } catch { return; } onEvent(ev); };
  es.onerror = () => {
    if (C.pid !== pid) return;
    try { es.close(); } catch { } es = null; wasDown = true;
    probeStream(pid);
  };
}
/* EventSource не сообщает код ответа, поэтому причину обрыва выясняет обычный запрос к тому же адресу:
   401 — сессия кончилась (экран входа, без переподключений до входа), 403/404 — доступ снят или проект удалён,
   429 — у человека слишком много открытых вкладок (не долбить: раз в минуту, а чужие правки подтягивать опросом),
   иначе связь оборвалась — переподключение с нарастающей паузой. */
async function probeStream(pid) {
  clearTimeout(esT); let st = 0;
  const ac = new AbortController();
  try { st = (await fetch(P("/events"), { credentials: "same-origin", signal: ac.signal })).status; } catch { st = 0; }
  ac.abort();
  if (C.pid !== pid || es) return;
  if (st === 401) return authExpired();
  if (st === 403 || st === 404) return lost(st === 403 ? "access" : "deleted");
  if (st === 429) {
    emit("limit", {}); clearInterval(pollT); pollT = setInterval(() => { if (C.pid && !es) queueCatchUp([]); }, 10000);
    esT = setTimeout(connect, 60000); return;
  }
  setStatus("offline"); esMs = Math.min(30000, (esMs || 1000) * 2); esT = setTimeout(connect, esMs);
}
function onEvent(ev) {
  if (ev.type === "rev") { if (ev.client !== C.client) queueCatchUp(ev.sections, ev.by); }
  else if (ev.type === "presence") emit("presence", { users: ev.users || [] });
  else if (ev.type === "comments") emit("comments", ev);
  else if (ev.type === "members") { refreshRole().then(ok => { if (ok === false) lost("access"); else emit("members", ev); }); }
  else if (ev.type === "deleted") { lost("deleted"); }
}

/* ---- открытые входы ---- */
C.init = async function (user) { C.on = true; C.user = user || null; };
C.open = async function (pid) {
  if (!C.on) throw new Error("совместный режим не включён");
  if (C.pid) close();
  const r = await http("GET", `/api/hub/project/${pid}`);
  if (!r.ok) throw new Error(r.json?.error || "проект не открылся (код " + r.status + ")");
  C.pid = pid; C.role = null; C.status = "saved";
  loadProject(r.json, false);
  PROJ.loading = false;
  setStatus(C.role === "viewer" ? "readonly" : "saved");          // роль открывшему известна из Collab.role; событие «role» — только при её смене
  connect();
  schedulePush(150);                                  // номера `_uid`, проставленные при загрузке, и прочая разница с сервером — одной отправкой
};
C.close = close;
// после повторного входа: поток событий заново (если оборвался из-за сессии) и отправка того, что накопилось
C.resume = function () { dead = false; if (!C.on || !C.pid) return Promise.resolve(true); clearTimeout(esT); esMs = 0; if (!es) connect(); return C.flush(); };
function close() {
  savePersonal();
  clearTimeout(timer); clearTimeout(retryT); clearTimeout(esT); clearInterval(pollT); timer = retryT = esT = pollT = null; firstT = retryMs = esMs = 0;
  if (es) { try { es.close(); } catch { } es = null; }
  Object.assign(C, { pid: null, rev: 0, role: null }); base = {}; secRev = {}; LC = new Map(); bm = null; wasDown = false; pushQueued = catchQueued = false; hint.clear();
  if (C.status !== "saved") { C.status = "saved"; emit("status", { state: "saved" }); }
}
C.createFromLocal = async function (name) {
  if (!C.on) throw new Error("совместный режим не включён");
  const body = JSON.stringify({ name }).slice(0, -1) + ',"project":' + projectJSON() + "}";
  const r = await http("POST", "/api/hub/projects", body);
  if (!r.ok) throw new Error(r.json?.error || "проект не создан (код " + r.status + ")");
  await C.open(r.json.id); return { id: r.json.id };
};
// положение указателя, выбор и текущий слой — другим участникам, не чаще двух раз в секунду
let pres = {}, presT = 0, presTimer = null;
function sendPresence() {
  presTimer = null; presT = Date.now();
  if (!C.on || !C.pid || dead) return;
  http("POST", P("/presence"), { client: C.client, cursor: pres.cursor ?? null, layer: pres.layer ?? null, sel: pres.sel || [] }).then(r => { if (r.status === 401) authExpired(); }).catch(() => { });
}
C.presence = function (p) {
  Object.assign(pres, p || {});
  if (!C.on || !C.pid || presTimer) return;
  presTimer = setTimeout(sendPresence, Math.max(0, 500 - (Date.now() - presT)));
};
C.selUids = () => SEL.map(s => s.f.get("_uid")).filter(Boolean);
C.featureByUid = (key, uid) => layerSrc[key]?.getFeatures().find(f => f.get("_uid") === uid) || null;

addEventListener("pagehide", () => savePersonal());
addEventListener("beforeunload", e => { if (C.on && C.pid && editable() && (timer || C.status === "sending" || C.status === "offline" || C.status === "conflict")) { e.preventDefault(); e.returnValue = ""; } });
}

if (typeof module === "object" && module.exports) module.exports = { split, join, merge3, ensureUids, keepUid, stable, h12 };
if (typeof window !== "undefined" && typeof document !== "undefined") install();
})(typeof window !== "undefined" ? window : globalThis);
