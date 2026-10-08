/* ГРАДО 2 · схема расчёта нового интерфейса: расчёт узлов и правка схемы. Схема хранится в project.raw.graph в виде
   litegraph (graphfile.js) и правится на месте — файл открывается и в рабочей странице. Узлы считаются по порядку связей
   (как runStep рабочей страницы), каждый со своим кэшем: пересчёт идёт, только когда изменились его входы, поля или данные.
   Узлы — те же, что в web/app.js, web/constraints.js и web/analysis.js: территория, слой с условием, ограничения, число,
   буфер, вычитание, объединение, пересечение, посадка застройки (sketchgen.js), ТЭП (tep.js) и четыре узла анализа.
   Итог для окон и карты — RESULT (пятно, эскиз, ТЭП); tick растёт после каждого пересчёта. Окно — panels/GraphPanel.vue. */
import { reactive, ref, shallowReactive, watch } from "vue";
import * as turf from "@turf/turf";
import "../../web/roles.js";
import { project, shown, currentId } from "./store.js";
import { dataRev, graphRev, graphHooks, lyr, touchData } from "./edit.js";
import { markDirty, notice } from "./project.js";
import { SOURCES, ensureLayer } from "./data.js";
import { CK, CONS } from "./constraints.js";
import { fullStyle, symbolOf } from "./symbology.js";
import { asArea, buf, diff, fmt, floorsOf, inter, m2, plural, safe, setFrame, splitParts, toLL, toXY, unionAll } from "./geom.js";
import { FLOOR_MODES, LOWRISE, TITLE, TYPES, TYPOLOGIES, nodeHeight } from "./graphfile.js";
import { generate } from "./sketchgen.js";
import { CAO, TAO, bakedSketch, existKey, keptBuildings, placeLookup, tepParams, tepRequest } from "./tep.js";

export const tick = ref(0);                  // пересчёт прошёл: окна перечитывают RESULT и пояснения узлов
export const selNode = ref(null);            // выбранный узел (id) — его выход виден на карте, пока открыто окно схемы
export const RESULT = shallowReactive({ site: null, sketch: [], tep: null, placeNode: null, tepNode: null });
export const preview = reactive({ graph: false, sketch: false });   // окна схемы и эскиза на виду: результат схемы — на карте

const RT = new Map();                        // id узла → несохраняемое состояние: выходы, кэш, пояснение
export const rt = n => { let r = RT.get(n.id); if (!r) RT.set(n.id, r = { out: [], info: "" }); return r; };
export const graph = () => project.raw?.graph || null;
export const nodeById = id => graph()?.nodes.find(n => n.id === +id) || null;
export const infoOf = id => { void tick.value; return RT.get(+id)?.info || ""; };

/* ---------- версии: граница и данные ---------- */
let terrRev = 0;
const OID = new WeakMap(); let oidN = 0;
const oid = o => { if (!o || typeof o !== "object") return "-"; let v = OID.get(o); if (!v) OID.set(o, v = ++oidN); return v; };
const gid = f => f ? oid(f) : "-";
const R = () => { const r = window.Roles; r.use({ DATA: project.data, LYR: project.layers }); return r; };
const roleSig = role => R().keys(role).map(k => k + ":" + oid(project.data[k]?.fc)).join(",");
const ha = f => f ? fmt(m2(f) / 1e4, 2) + " га" : "пусто";
const visibleIn = (l, f) => { if (l.style.mode !== "cat" && l.style.mode !== "rules") return true; return !symbolOf(l.style, k => f.properties?.[k], []).hide; };
const terr = () => project.territory;

/* ---------- узлы ---------- */
function testOp(v, op, t) {
  if (op === "—") return true; if (v == null) return false;
  if (op === "содержит") return String(v).toLowerCase().includes(String(t).toLowerCase());
  if (op === "один из") return String(t).split(",").map(s => s.trim().toLowerCase()).includes(String(v).toLowerCase());
  const n = !isNaN(+v) && !isNaN(+t) && t !== "", a = n ? +v : String(v), b = n ? +t : String(t);
  return { "=": a == b, "≠": a != b, ">": a > b, "<": a < b, "≥": a >= b, "≤": a <= b }[op];
}
export const titleToKey = t => Object.keys(project.data).find(k => project.data[k].title === t) || Object.keys(SOURCES).find(k => SOURCES[k].title === t);
export const layerTitles = () => Object.keys(project.data).map(k => project.data[k].title);
export const fieldsOfTitle = t => { const d = project.data[titleToKey(t)]; return d?.fc ? [...new Set(d.fc.features.slice(0, 500).flatMap(f => Object.keys(f.properties || {})))].filter(k => !k.startsWith("_")) : []; };
function geomSig(list) {
  let A = list.length, B = 0;
  for (const f of list) {
    if (!f.geometry) continue;
    let a = 7, b = 11;
    const walk = c => { if (typeof c[0] === "number") { a = (a * 31 + Math.round(c[0] * 1e7)) % 2147483647; b = (b * 37 + Math.round(c[1] * 1e7)) % 2147483629; } else for (const x of c) walk(x); };
    walk(f.geometry.coordinates); A = (A + a) % 9007199254740881; B = (B + b) % 9007199254740881;
  }
  return A + ":" + B;
}
const cached = (r, key, fn) => { if (r.ck !== key) { r.ck = key; r.cv = fn(); } return r.cv; };

/* ограничения: включённые слои-запреты группы «Ограничения» и потолок высоты по сетке «Предельная высота» */
const EXCLUDE = [CK.zouit, CK.water, CK.red, CK.fire, CK.pzz, CK.gp];
function consExclude() {
  const on = EXCLUDE.map(lyr).filter(l => l && shown(l));
  return unionAll(on.flatMap(l => (project.data[l.key]?.fc.features || []).filter(f => visibleIn(l, f) && /Polygon/.test(f.geometry?.type))));
}
function consCeiling() {
  const l = lyr(CK.ceil); if (!l || !shown(l)) return null;
  const cells = (project.data[CK.ceil]?.fc.features || []).filter(c => visibleIn(l, c)).map(c => ({ c, b: turf.bbox(c), v: c.properties["Предельная высота, м"] ?? c.properties["Потолок, м"] })).filter(x => x.v != null);
  const idx = new Map();             // сетка по 0,001° (~100 м): клетки, которые задевает корпус, без перебора всей сетки
  cells.forEach(x => { for (let i = Math.floor(x.b[0] * 1e3); i <= Math.floor(x.b[2] * 1e3); i++) for (let j = Math.floor(x.b[1] * 1e3); j <= Math.floor(x.b[3] * 1e3); j++) { const k = i + ":" + j; (idx.get(k) || idx.set(k, []).get(k)).push(x); } });
  return f => {
    const b = turf.bbox(f), seen = new Set(); let top = Infinity;
    for (let i = Math.floor(b[0] * 1e3); i <= Math.floor(b[2] * 1e3); i++) for (let j = Math.floor(b[1] * 1e3); j <= Math.floor(b[3] * 1e3); j++)
      for (const x of idx.get(i + ":" + j) || []) {
        if (seen.has(x)) continue; seen.add(x);
        if (x.b[0] > b[2] || x.b[2] < b[0] || x.b[1] > b[3] || x.b[3] < b[1] || x.v >= top) continue;
        if (safe(() => turf.booleanIntersects(f, x.c))) top = x.v;
      }
    return top === Infinity ? null : top;
  };
}

/* радиусы обслуживания: 2151-ПП, 2152-ПП и СП 42.13330.2016 (web/analysis.js) */
const SERVICES = {
  "детские сады · Москва (2151-ПП)": { kinds: ["детский сад"], r: ok => CAO(ok) ? 500 : 300, norm: "2151-ПП, табл. 1.4.1 п. 4 (многоквартирная застройка)" },
  "школы · Москва (2151-ПП)": { kinds: ["школа"], r: ok => CAO(ok) ? null : 1000, norm: "2151-ПП, табл. 1.4.2 п. 4 (многоквартирная застройка)" },
  "аптеки и магазины · Москва (2152-ПП)": { kinds: ["аптека"], r: ok => TAO(ok) ? 800 : 500, norm: "2152-ПП, табл. 1.3.1 п. 1.1" },
  "детские сады · 300 м": { kinds: ["детский сад"], r: 300, norm: "СП 42.13330.2016, табл. 10.1" },
  "школы · 500 м": { kinds: ["школа"], r: 500, norm: "СП 42.13330.2016, табл. 10.2" },
  "поликлиники · 1000 м": { kinds: ["поликлиника"], r: 1000, norm: "СП 42.13330.2016, табл. 10.1" },
  "аптеки · 500 м": { kinds: ["аптека"], r: 500, norm: "СП 42.13330.2016, табл. 10.1" } };
const socialPoints = kinds => R().features("social").filter(f => f.geometry?.type === "Point" && kinds.includes(f.properties["Вид"]));
const NO_WALK = new Set(["motorway", "motorway_link", "trunk_link", "construction", "proposed"]);
function walkGraph() {
  const roads = R().features("roads"), key = p => p[0].toFixed(1) + "," + p[1].toFixed(1);
  const nodes = new Map(), adj = [], xy = [];
  const id = p => { const k = key(p); let i = nodes.get(k); if (i === undefined) { i = xy.length; nodes.set(k, i); xy.push(p); adj.push([]); } return i; };
  roads.forEach(f => { if (NO_WALK.has(f.properties["Тип дороги"])) return; const g = f.geometry; (g.type === "LineString" ? [g.coordinates] : g.type === "MultiLineString" ? g.coordinates : []).forEach(line => {
    const ps = line.map(toXY); for (let i = 1; i < ps.length; i++) { const a = id(ps[i - 1]), b = id(ps[i]), d = Math.hypot(ps[i][0] - ps[i - 1][0], ps[i][1] - ps[i - 1][1]); adj[a].push([b, d]); adj[b].push([a, d]); } }); });
  return { xy, adj };
}
function dijkstra(G, starts, D) {
  const dist = new Float64Array(G.xy.length).fill(Infinity), heap = [];
  const push = (d, i) => { heap.push([d, i]); let k = heap.length - 1; while (k > 0) { const p = (k - 1) >> 1; if (heap[p][0] <= heap[k][0]) break; [heap[p], heap[k]] = [heap[k], heap[p]]; k = p; } };
  const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let k = 0; for (;;) { const l = 2 * k + 1, r = l + 1; let m = k; if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === k) break; [heap[m], heap[k]] = [heap[k], heap[m]]; k = m; } } return top; };
  starts.forEach(([i, d]) => { if (d < dist[i]) { dist[i] = d; push(d, i); } });
  while (heap.length) { const [d, i] = pop(); if (d > dist[i] || d > D) continue; for (const [j, w] of G.adj[i]) { const nd = d + w; if (nd < dist[j] && nd <= D) { dist[j] = nd; push(nd, j); } } }
  return dist;
}

/* параметры посадки из полей узла (web/app.js placeParams) */
export function placeParams(n, x) {
  const w = n.widgets_values, mode = FLOOR_MODES.includes(w[5]) ? w[5] : FLOOR_MODES[0];
  return { typ: TYPOLOGIES.includes(w[0]) ? w[0] : "Секции", width: Math.round(w[1]), floors: x?.in(1) ?? Math.round(w[2]), gap: +w[3], angle: Math.round(w[4]),
    cap: n.inputs?.[2] ? x?.in(2) || null : null, goal: mode === FLOOR_MODES[1] ? densityGoal() : null,
    plot: Math.round(w[6] ?? 10), block: Math.round(w[7] ?? 110), relax: !!w[8] };
}
function densityGoal() {
  const t = graph()?.nodes.find(n => n.type === "Показатели/ТЭП КРТ"), T = terr(); if (!t || !T) return null;
  const kept = keptBuildings(inputOf(t, 1)), sppKept = kept.reduce((s, f) => s + m2(f) * floorsOf(f), 0), target = t.widgets_values[1];
  return { target, need: Math.max(0, target * 1000 * m2(T) / 1e4 - sppKept) };
}

const EXEC = {
  "Данные/Территория": x => { x.out(0, terr()); x.info(terr() ? ha(terr()) : "граница не задана"); },
  "Данные/Слой": x => {
    const [lv, fv, ov, vv] = x.n.widgets_values, r = x.r;
    let key = titleToKey(lv), d = project.data[key];
    const alt = !d && lv === "Здания (ЕГРН)" && project.data["osm.buildings"] ? "osm.buildings" : null;   // ЕГРН не выгрузился — здания OSM
    if (alt) { key = alt; d = project.data[alt]; }
    if (!d?.fc) { x.out(0, null); x.info(lv ? "слой не загружен" : "выберите слой"); r.label = ""; return; }
    const ck = [oid(d.fc), key, fv, ov, vv, terrRev].join("|");
    if (r.cacheKey !== ck) {
      r.cacheKey = ck;
      const list = d.fc.features.filter(f => fv === "—" || testOp(f.properties?.[fv], ov, vv));
      const gs = geomSig(list);       // правка атрибута не меняет геометрию: объединение и буферы после него остаются
      if (r.outG && gs === r.gsig && terrRev === r.terr) r.outG = { ...r.outG, properties: { _src: list } };
      else { let u = unionAll(list.map(asArea)); if (u) u = { ...u, properties: { _src: list } }; r.outG = u; r.gsig = gs; r.terr = terrRev; }
      r.n = [list.length, d.fc.features.length];
    }
    x.out(0, r.outG);
    r.label = "Слой: " + d.title + (fv !== "—" && ov !== "—" ? ` [${fv} ${ov} ${vv}]` : "");
    x.info(alt ? `${r.n[0]} зд. OSM: ЕГРН не выгружен` : `${r.n[0]} из ${r.n[1]} объектов`);
  },
  "Данные/Ограничения": x => {
    const r = x.r, vis = [...EXCLUDE, CK.ceil].map(k => { const l = lyr(k); return l ? (shown(l) ? 1 : 0) + ":" + oid(project.data[k]?.fc) + ":" + JSON.stringify([l.style.mode, l.style.cat?.off, l.style.rules]) : "-"; }).join(",");
    if (r.ck !== vis) { r.ck = vis; r.ex = consExclude(); r.cap = consCeiling(); if (r.ex) r.ex = { ...r.ex, properties: {} }; }
    x.out(0, r.ex); x.out(1, r.cap);
    const n = EXCLUDE.filter(k => lyr(k) && shown(lyr(k))).length;
    x.info(lyr(CK.zouit) || lyr(CK.ceil) ? `запретов: ${n} слоя · ${ha(r.ex)}${r.cap ? " · предельная высота" : ""}` : "окно «Ограничения» → Рассчитать");
  },
  "Параметры/Число": x => x.out(0, Math.round(x.n.widgets_values[0])),
  "Геометрия/Буфер": x => { const a = x.in(0), d = x.in(1) ?? Math.round(x.n.widgets_values[0]); const res = cached(x.r, gid(a) + ":" + d, () => buf(a, d)); x.out(0, res); x.info(ha(res)); },
  "Геометрия/Вычесть": x => { const a = x.in(0), b = x.in(1); const res = cached(x.r, gid(a) + ":" + gid(b), () => diff(a, b)); x.out(0, res); x.info(ha(res)); },
  "Геометрия/Объединить": x => { const a = x.in(0), b = x.in(1);
    const res = cached(x.r, gid(a) + ":" + gid(b), () => { let u = unionAll([a, b]); if (u) u = { ...u, properties: { _src: [...(a?.properties?._src || []), ...(b?.properties?._src || [])] } }; return u; }); x.out(0, res); x.info(ha(res)); },
  "Геометрия/Пересечь": x => { const a = x.in(0), b = x.in(1); const res = cached(x.r, gid(a) + ":" + gid(b), () => inter(a, b)); x.out(0, res); x.info(ha(res)); },
  "Эскиз/Посадка застройки": x => {
    const n = x.n; n.properties ||= {};
    if (!n.properties.run) { x.out(0, []); x.info("не построена: «Построить эскиз» в окне «Эскиз»"); return; }
    if (!terr()) { x.out(0, []); x.info("нет границы территории — эскиз не строится"); return; }
    const site = x.in(0), p = placeParams(n, x), capId = p.cap ? oid(p.cap) : "";
    const res = cached(x.r, gid(site) + JSON.stringify({ ...p, cap: undefined }) + capId + ":" + CONS.floorH, () => generate(site, p)); x.out(0, res);
    const capped = res.filter(b => b.capped).length, avg = res.length ? res.reduce((s, b) => s + b.floors * b.m2, 0) / res.reduce((s, b) => s + b.m2, 0) : 0;
    const np = res.plots?.filter(g => /^участок/.test(g.kind)).length, ny = res.plots?.filter(g => g.kind === "двор" || g.kind === "свет соседям").length;
    const guest = (res.streets || []).filter(g => g.kind === "гостевая стоянка").reduce((s, g) => s + g["Мест"], 0);
    x.info(`${plural(res.length, LOWRISE.has(p.typ) ? ["дом", "дома", "домов"] : ["корпус", "корпуса", "корпусов"])}${np ? ` · ${plural(np, ["участок", "участка", "участков"])}` : ny ? ` · ${plural(ny, ["двор", "двора", "дворов"])}` : ""} · ${fmt(res.reduce((s, b) => s + b.m2 * b.floors, 0) / 1000, 1)} тыс. м² СПП · ср. ${fmt(avg, 1)} эт.${guest ? ` · гостевых мест ${guest} (945-ПП)` : ""}${capped ? ` · ${capped} ниже предельной высоты` : ""}${res.goal ? ` · ${res.goal}` : ""}${res.note ? ` · ${res.note}` : ""}`);
  },
  "Показатели/ТЭП КРТ": x => {
    const n = x.n, r = x.r; n.properties ||= {};
    const bk = n.properties.baked, bd = bk && project.data[bk];       // принятый эскиз считается вместо превью схемы, пока его слой в проекте
    if (bk && !bd) n.properties.baked = null;
    const sk = bd ? bakedSketch(bd) : x.in(0) || [], kept = x.in(1), lim = x.in(2), share = n.widgets_values[0] / 100, target = n.widgets_values[1];
    const tp = tepParams(n); placeLookup(n, r, terrRev, () => { schedule(); tick.value++; });
    if (!terr()) { x.out(0, null); x.info("нет границы территории"); return; }
    const key = [bd ? `${bk}:${oid(bd.fc)}:${sk.length}` : gid(sk), gid(kept), gid(lim), share, target, dataRev.value, terrRev, JSON.stringify(tp)].join("|");
    if (r.key !== key) { r.key = key; const seq = r.seq = (r.seq || 0) + 1;
      tepRequest(sk, kept, lim, share, target, tp).then(t => { if (seq !== r.seq) return; r.tep = t; r.out[0] = t; r.info = `${bd ? "по сохранённому эскизу · " : ""}плотность ${fmt(t.density, 1)} · население ${fmt(t.m.population)}`; RESULT.tep = t; tick.value++; })
        .catch(e => { if (seq === r.seq) { r.info = "ТЭП: " + e.message; tick.value++; } }); }
    x.out(0, r.tep || null);
  },
  "Анализ/Радиусы обслуживания": x => {
    const w = x.n.widgets_values, r = x.r, sv = SERVICES[w[0]] || Object.values(SERVICES)[0], tn = graph().nodes.find(n => n.type === "Показатели/ТЭП КРТ"), ok = tn ? tepParams(tn).okrug : "";
    const r0 = typeof sv.r === "function" ? sv.r(ok) : sv.r, rad = r0 == null ? null : r0 * (w[1] ? .7 : 1), T = terr();
    const key = [roleSig("social"), w[0], rad, terrRev].join("|");
    if (rad == null) { r.ck = key; r.fc = []; x.out(0, null); x.out(1, null); x.info(`в ЦАО школа нормируется «в границах ЦАО» (${sv.norm}) — радиусом не проверяется`); return; }
    if (r.ck !== key) {
      r.ck = key; const pts = socialPoints(sv.kinds);
      const circles = pts.map(p => turf.circle(p, rad, { units: "meters", steps: 48, properties: { "Пояснение": `${p.properties["Название"] || p.properties["Вид"]}: ${Math.round(rad)} м` } }));
      const cover = unionAll(circles), out = T ? diff(T, cover) : null;
      r.res = [cover, out];
      r.fc = circles.concat(out ? [turf.feature(out.geometry, { "Пояснение": `вне радиуса ${Math.round(rad)} м: ${ha(out)} — здесь ${sv.kinds[0]} не доступен пешком по норме (${sv.norm})` })] : []);
      r.msg = !R().keys("social").length ? "загрузите «Школы, детсады, поликлиники (OSM)» в окне «Данные»" : `${plural(pts.length, ["объект", "объекта", "объектов"])} · вне радиуса ${out ? ha(out) : "0 га"} · ${sv.norm}`;
    }
    x.out(0, r.res[0]); x.out(1, r.res[1]); x.info(r.msg);
  },
  "Анализ/Пешая доступность": x => {
    const w = x.n.widgets_values, r = x.r, sv = SERVICES[w[0]] || Object.values(SERVICES)[0], min = Math.round(w[1]), D = min * 75, T = terr();
    const key = [roleSig("roads"), roleSig("social"), w[0], min, terrRev].join("|");
    if (r.ck !== key) {
      r.ck = key; r.res = null; r.fc = [];
      if (!R().keys("roads").length || !R().keys("social").length) r.msg = "нужны «Улично-дорожная сеть (OSM)» и «Школы, детсады, поликлиники (OSM)»";
      else {
        const G = walkGraph(), pts = socialPoints(sv.kinds);
        const starts = pts.map(p => { const q = toXY(p.geometry.coordinates); let best = -1, bd = 200; G.xy.forEach((v, i) => { const d = Math.hypot(v[0] - q[0], v[1] - q[1]); if (d < bd) { bd = d; best = i; } }); return best < 0 ? null : [best, bd]; }).filter(Boolean);
        const dist = dijkstra(G, starts, D), segs = [];
        G.adj.forEach((edges, a) => edges.forEach(([b, wt]) => { if (a > b) return; const da = dist[a], db = dist[b], A = G.xy[a], B = G.xy[b];
          if (da + wt <= D || db + wt <= D || (da <= D && db <= D)) segs.push([A, B]);
          else { if (da < D) { const t = (D - da) / wt; segs.push([A, [A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t]]); } if (db < D) { const t = (D - db) / wt; segs.push([B, [B[0] + (A[0] - B[0]) * t, B[1] + (A[1] - B[1]) * t]]); } } }));
        if (segs.length) {
          const zone = buf(turf.multiLineString(segs.map(s => s.map(toLL))), 30);
          r.res = zone;
          const out = T && zone ? diff(T, zone) : null;
          r.fc = [turf.feature(zone.geometry, { "Пояснение": `${min} мин пешком до: ${sv.kinds[0]} (${pts.length}) — по улицам OSM, 4,5 км/ч` })]
            .concat(out ? [turf.feature(out.geometry, { "Пояснение": `дальше ${min} мин пешком: ${ha(out)}` })] : []);
        }
        r.msg = `${plural(pts.length, ["объект", "объекта", "объектов"])} · ${G.xy.length} узлов улиц · ${r.res ? "зона " + ha(r.res) : "недостижимо"}`;
      }
    }
    x.out(0, r.res); x.info(r.msg);
  },
  "Анализ/Показатели кварталов": x => {
    const r = x.r, T = terr(); let bl = x.in(0);
    if (!bl && T && R().keys("roads").length) { r.auto ||= {}; const k = roleSig("roads") + "|" + terrRev; if (r.auto.k !== k) { const streets = R().features("roads").filter(f => /Line/.test(f.geometry?.type) && !/footway|path|steps|cycleway|service|track|pedestrian/.test(f.properties["Тип дороги"] || "")); r.auto = { k, g: diff(T, unionAll(streets.map(f => buf(f, 10)))) }; } bl = r.auto.g; }
    const bi = x.in(1), key = gid(bl) + ":" + gid(bi) + ":" + dataRev.value;
    if (r.ck !== key) {
      r.ck = key;
      const ek = existKey(), blds = bi?.properties?._src || (ek ? project.data[ek].fc.features : []), polyB = blds.filter(f => /Polygon/.test(f.geometry?.type));
      const cents = polyB.map(f => ({ f, c: safe(() => turf.pointOnFeature(f)) })).filter(q => q.c);
      r.fc = (bl ? splitParts(bl) : []).filter(p => m2(p) > 500).map((p, i) => {
        const inB = cents.filter(q => safe(() => turf.booleanPointInPolygon(q.c, p))).map(q => q.f), a = m2(p);
        const fp = inB.reduce((s, f) => s + m2(f), 0), spp = inB.reduce((s, f) => s + m2(f) * floorsOf(f), 0), dens = spp / 1000 / (a / 1e4);
        return turf.feature(p.geometry, { "Квартал": i + 1, "Площадь, га": +(a / 1e4).toFixed(2), "Зданий": inB.length, "СПП, тыс. м²": +(spp / 1000).toFixed(1), "Плотность, тыс. м²/га": +dens.toFixed(1),
          "Застроенность, %": +(fp / a * 100).toFixed(1), "Средняя этажность": fp ? +(spp / fp).toFixed(1) : 0,
          "Пояснение": `кв. ${i + 1}: ${fmt(dens, 1)} тыс. м²/га, ${fp ? fmt(spp / fp, 1) : 0} эт., застроено ${fmt(fp / a * 100, 0)} %` });
      });
      r.msg = bl ? `${r.fc.length} кварталов · зданий ${polyB.length}${x.in(0) ? "" : " · кварталы — между улицами OSM"}` : "подайте на вход кварталы или загрузите улицы OSM";
    }
    x.out(0, bl); x.info(r.msg);
  },
  "Анализ/Баланс территории": x => {
    const r = x.r, T = terr(), z = x.in(0), src = z?.properties?._src || [], w = x.n.widgets_values, key = gid(z) + ":" + w[0] + ":" + terrRev;
    if (r.ck !== key && T) {
      r.ck = key; r.fc = [];
      const fields = [...new Set(src.slice(0, 200).flatMap(f => Object.keys(f.properties || {})))].filter(k => !k.startsWith("_"));
      const want = w[0];
      const field = (want && fields.includes(want) ? want : null) || fields.find(k => new Set(src.map(f => f.properties[k])).size > 1 && src.every(f => typeof (f.properties[k] ?? "") === "string")) || fields[0];
      if (field && w[0] !== field) w[0] = field;
      const by = new Map(); src.filter(f => /Polygon/.test(f.geometry?.type)).forEach(f => { const q = inter(f, T); if (!q) return; const v = String(f.properties[field] ?? "—"); (by.get(v) || by.set(v, []).get(v)).push(q); });
      const total = m2(T), rows = [...by].map(([v, parts]) => { const u = unionAll(parts); return { v, u, a: m2(u) }; }).sort((a, b) => b.a - a.a);
      const covered = rows.reduce((s, q) => s + q.a, 0);
      r.fc = rows.map(q => turf.feature(q.u.geometry, { [field || "Значение"]: q.v, "Площадь, га": +(q.a / 1e4).toFixed(2), "Доля, %": +(q.a / total * 100).toFixed(1), "Пояснение": `${q.v}: ${fmt(q.a / 1e4, 2)} га (${fmt(q.a / total * 100, 1)} %)` }));
      r.msg = field ? `${rows.length} значений «${field}» · покрыто ${fmt(covered / total * 100, 0)} % территории` : "подайте на вход слой зон (узел «Слой»)";
    }
    x.out(0, T); x.info(r.msg || "нет территории");
  },
};

/* ---------- расчёт ---------- */
let LINKS = new Map();
function inputOf(n, i) {
  const id = n.inputs?.[i]?.link; if (id == null) return undefined;
  const l = LINKS.get(id); if (!l) return undefined;
  return RT.get(l[1])?.out[l[2]];
}
function order(g) {
  const ids = new Set(g.nodes.map(n => n.id)), deg = new Map(g.nodes.map(n => [n.id, 0])), next = new Map();
  for (const l of g.links) { if (!l || !ids.has(l[1]) || !ids.has(l[3])) continue; deg.set(l[3], deg.get(l[3]) + 1); (next.get(l[1]) || next.set(l[1], []).get(l[1])).push(l[3]); }
  const q = g.nodes.filter(n => !deg.get(n.id)).sort((a, b) => (a.order ?? 0) - (b.order ?? 0)), out = [];
  while (q.length) { const n = q.shift(); out.push(n); for (const t of next.get(n.id) || []) { deg.set(t, deg.get(t) - 1); if (!deg.get(t)) q.push(g.nodes.find(m => m.id === t)); } }
  return out.concat(g.nodes.filter(n => !out.includes(n)));     // петля в схеме — её узлы в конце, как придётся
}
export function recompute() {
  const g = graph(); if (!g) return;
  LINKS = new Map(g.links.filter(Boolean).map(l => [l[0], l]));
  for (const n of order(g)) {
    const r = rt(n), ex = EXEC[n.type];
    if (!ex || n.mode === 2 || n.mode === 4) { r.out = []; r.info = ex ? "выключен" : "узел этой версии не знает"; continue; }
    const x = { n, r, in: i => inputOf(n, i), out: (i, v) => { r.out[i] = v; }, info: t => { r.info = t; } };
    n.widgets_values ||= [];
    try { ex(x); } catch (e) { console.warn("[схема]", n.type, e); r.out = []; r.info = "ошибка: " + e.message; }
  }
  const place = g.nodes.find(n => n.type === "Эскиз/Посадка застройки"), tepN = g.nodes.find(n => n.type === "Показатели/ТЭП КРТ");
  RESULT.placeNode = place || null; RESULT.tepNode = tepN || null;
  RESULT.site = place ? inputOf(place, 0) || null : null;
  RESULT.sketch = place ? RT.get(place.id)?.out[0] || [] : [];
  RESULT.tep = tepN ? RT.get(tepN.id)?.tep || null : null;
  tick.value++;
}
let timer = 0;
export function schedule() { clearTimeout(timer); timer = setTimeout(recompute, 60); }
/* «Пересчитать всё»: кэши узлов сбрасываются (данные могли смениться в рабочей странице) */
export function recomputeAll() { RT.forEach(r => { r.ck = r.cacheKey = r.key = null; }); recompute(); }

watch(() => project.territory, t => { terrRev++; if (t) setFrame(turf.centroid(t).geometry.coordinates); schedule(); }, { immediate: true });
watch(() => project.raw, () => { RT.clear(); selNode.value = null; schedule(); });
watch([dataRev, graphRev, () => CONS.floorH, () => project.layers.map(l => [l.key, shown(l), l.style.mode, l.style.cat?.off, l.style.rules])], schedule, { deep: true });
graphHooks.restored = () => { RT.clear(); structRev.value++; schedule(); };

/* ---------- правка схемы ---------- */
export function edited(structure) { graphRev.value++; markDirty(); if (structure) structRev.value++; schedule(); }
export const structRev = ref(0);             // узлы или связи изменились: окно схемы перестраивает картинку
export function setWidget(id, i, v) { const n = nodeById(id); if (!n) return; n.widgets_values ||= []; if (n.widgets_values[i] === v) return; n.widgets_values[i] = v; edited(); }
export function setProp(id, k, v) { const n = nodeById(id); if (!n) return; (n.properties ||= {})[k] = v; edited(); }
export function renameNode(id, title) { const n = nodeById(id); if (!n) return; if (title && title !== TYPES[n.type]?.title) n.title = title; else delete n.title; edited(true); }
export function moveNode(id, x, y) { const n = nodeById(id); if (!n) return; n.pos = [Math.round(x), Math.round(y)]; graphRev.value++; markDirty(); }
export function addNode(type, pos) {
  const g = graph(), t = TYPES[type]; if (!g || !t) return null;
  const id = ++g.last_node_id, ins = t.inputs || [], outs = t.outputs || [];
  const n = { id, type, pos: [Math.round(pos[0]), Math.round(pos[1])], size: { 0: t.width, 1: nodeHeight(ins.length, outs.length, t.widgets.length) }, flags: {}, order: g.nodes.length, mode: 0,
    ...(ins.length ? { inputs: ins.map(([name, type]) => ({ name, type, link: null })) } : {}),
    outputs: outs.map(([name, type]) => ({ name, type, links: null })), properties: JSON.parse(JSON.stringify(t.props || {})),
    ...(t.widgets.length ? { widgets_values: t.widgets.map(w => w[2]) } : {}), color: TITLE[t.kind], bgcolor: "#f7f7f5" };
  g.nodes.push(n); edited(true); return n;
}
function unlink(g, lid) {
  const l = g.links.find(q => q && q[0] === lid); if (!l) return;
  g.links = g.links.filter(q => q !== l);
  const o = g.nodes.find(n => n.id === l[1]), t = g.nodes.find(n => n.id === l[3]);
  const outs = o?.outputs?.[l[2]]; if (outs?.links) { outs.links = outs.links.filter(x => x !== lid); if (!outs.links.length) outs.links = null; }
  if (t?.inputs?.[l[4]]?.link === lid) t.inputs[l[4]].link = null;
}
export function disconnect(lid) { const g = graph(); if (!g) return; unlink(g, +lid); edited(true); }
export function canConnect(o, os, t, ts) {
  const a = nodeById(o), b = nodeById(t); if (!a || !b || a === b) return false;
  const ot = a.outputs?.[os]?.type, it = b.inputs?.[ts]?.type; return !!ot && ot === it;
}
export function connect(o, os, t, ts) {
  const g = graph(); if (!g || !canConnect(o, os, t, ts)) return null;
  const a = nodeById(o), b = nodeById(t), was = b.inputs[ts].link;
  if (was != null) unlink(g, was);                               // у входа одна связь: новая заменяет прежнюю
  const id = ++g.last_link_id, l = [id, a.id, os, b.id, ts, a.outputs[os].type];
  g.links.push(l); b.inputs[ts].link = id; (a.outputs[os].links ||= []).push(id);
  edited(true); return id;
}
export function removeNode(id) {
  const g = graph(), n = nodeById(id); if (!g || !n) return;
  g.links.filter(l => l && (l[1] === n.id || l[3] === n.id)).forEach(l => unlink(g, l[0]));
  g.nodes = g.nodes.filter(m => m !== n); RT.delete(n.id);
  if (selNode.value === n.id) selNode.value = null;
  edited(true);
}
export const nodeTitle = n => { void tick.value; return RT.get(n.id)?.label || n.title || TYPES[n.type]?.title || n.type; };
export const outputOf = (id, i) => { void tick.value; return RT.get(+id)?.out[i]; };
export const fcOf = id => { void tick.value; return RT.get(+id)?.fc || null; };

/* «В слой» (Bake): выход выбранного узла — обычный слой проекта; у узлов анализа — с таблицей показателей */
export function bakeNode(id) {
  const n = nodeById(id); if (!n) { notice.value = "Выберите блок в схеме расчёта"; return; }
  const r = RT.get(n.id), out = (n.outputs || []).findIndex(o => o.type === "geom"), g = out >= 0 ? r?.out[out] : null;
  const feats = r?.fc?.length ? r.fc : g ? [turf.feature(g.geometry, { "Узел": nodeTitle(n) })] : [];
  if (!feats.length) { notice.value = "У блока нет геометрии на выходе"; return; }
  const key = "user:" + Date.now().toString(36), title = `Анализ: ${nodeTitle(n)}`, fc = turf.featureCollection(feats.map(f => turf.feature(f.geometry, { ...f.properties })));
  project.data[key] = { title, source: "выход блока схемы, " + new Date().toLocaleDateString("ru-RU"), fetched_at: new Date().toISOString().slice(0, 10), fc };
  const l = ensureLayer(key, title); l.style = fullStyle({ ...l.style, label: "Пояснение", opacity: .35 });
  currentId.value = key; touchData();
  notice.value = `Слой «${title}»: ${plural(feats.length, ["объект", "объекта", "объектов"])} с таблицей показателей. Схема на него больше не влияет`;
}

/* узел «Ограничения» встаёт между пятном застройки и посадкой (web/constraints.js ensureConsNode): после расчёта ограничений */
export function ensureConsNode() {
  const g = graph(); if (!g) return;
  const place = g.nodes.find(n => n.type === "Эскиз/Посадка застройки"); if (!place) return;
  if (g.nodes.some(n => n.type === "Данные/Ограничения")) return;
  const lid = place.inputs?.[0]?.link, src = lid != null ? g.links.find(l => l && l[0] === lid) : null;
  const nc = addNode("Данные/Ограничения", [place.pos[0] - 250, place.pos[1] + 260]);
  const nd = addNode("Геометрия/Вычесть", [place.pos[0] - 20, place.pos[1] + 200]); nd.title = "Пятно с ограничениями";
  if (src) connect(src[1], src[2], nd.id, 0);
  connect(nc.id, 0, nd.id, 1); connect(nd.id, 0, place.id, 0);
  if (!place.inputs[2]) place.inputs.push({ name: "предельная высота", type: "cap", link: null });
  connect(nc.id, 1, place.id, 2);
  notice.value = "В схему добавлен блок «Ограничения»: пятно застройки минус запреты, высота корпусов не выше предельной высоты";
}
