/* ГРАДО 2 · показатели (ТЭП) нового интерфейса — перенос web/app.js и web/norms.js без изменения расчёта: территориальные
   параметры узла ТЭП (район, зона образования, K1, K2, ТиНАО по центру территории через /api/place и /api/rail_route),
   геометрическая часть ТЭП здесь (СПП новой и сохраняемой застройки, ограничения, снос), нормативная — движок ядра на
   сервере (/api/tep), ручные нормативы — разница с пресетом /api/tep/norms в tp.constants. Резерв участков ДОО, школы и
   поликлиники ищется в свободной земле пятна (T6). Всё лежит в свойствах узла ТЭП схемы и уходит в файл проекта. */
import * as turf from "@turf/turf";
import "../../web/roles.js";
import { project } from "./store.js";
import { buf, diff, fmt, floorsOf, inter, m2, polyLL, polys, rect, ringsXY, rot, safe, splitParts, toLL, toXY, unionAll, centroid } from "./geom.js";
import { partFrame } from "./sketchgen.js";

export const CAO = ok => /Центральн/i.test(ok || ""), TAO = ok => /Троицк/i.test(ok || "");
const R = () => { const r = window.Roles; r.use({ DATA: project.data, LYR: project.layers }); return r; };
export const existKey = () => R().existingBuildingsKey?.() ?? (project.data["nspd.buildings"] ? "nspd.buildings" : project.data["osm.buildings"] ? "osm.buildings" : null);
export const insideTerr = f => { const T = project.territory; return T && safe(() => turf.booleanPointInPolygon(turf.pointOnFeature(f), T)); };

async function api(path, body, signal) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal } : signal ? { signal } : {});
  const j = await r.json(); if (!r.ok) throw new Error(j.error || r.status); return j;
}

/* Территориальные параметры ТЭП (как маркер «Калькулятора 2.0»): определяются по центру территории, правятся руками
   в окне «Показатели» (тогда auto = false и повторно не перезаписываются). tp.constants — ручные нормативы. */
export function tepParams(n) {
  n.properties ||= {};
  return n.properties.tp ||= { auto: true, district: "", zone: 1, k1: 1, k2: 0.9, tinao: 0, mode: 1, nonres: 6, unbuilt: 25, walk: null, rev: -1, notes: [] };
}

/* Район по границе: запрос уходит, когда граница не менялась 0,4 с; не дольше 30 с (портал OSM молчит — зону задают руками).
   rt — несохраняемое состояние узла, terrRev — номер версии границы, done — перерисовать и пересчитать. */
const PLACE_LIMIT_MS = 30000;
export function placeLookup(n, rt, terrRev, done) {
  const tp = tepParams(n), T = project.territory; if (!T || tp.rev === terrRev || rt.placeBusy) return;
  if (rt.placeSeen !== terrRev) { rt.placeSeen = terrRev; rt.placeAt = Date.now(); }
  if (tp.rev !== -1 && Date.now() - rt.placeAt < 400) { clearTimeout(rt.placeT); rt.placeT = setTimeout(() => placeLookup(n, rt, terrRev, done), 420 - (Date.now() - rt.placeAt)); return; }
  rt.placeBusy = true; const rev = terrRev, [lon, lat] = turf.centroid(T).geometry.coordinates;
  const ac = new AbortController(), cut = setTimeout(() => ac.abort(), PLACE_LIMIT_MS);
  api("/api/place", { lon, lat, polygon: T.geometry }, ac.signal).then(r => {
    tp.districts = r.chosen_by === "area" ? r.districts || [] : []; tp.rev = rev; tp.district = r.district; tp.okrug = r.okrug; tp.walk = r.rail_walk_m; tp.walkRoute = false; tp.station = ""; tp.notes = r.notes || []; tp.insideTtk = r.inside_ttk;
    tp.zoneDist = r.zone; tp.zoneNote = r.zone_note || "";
    if (tp.auto) Object.assign(tp, { ...(r.k1 != null ? { k1: r.k1 } : {}), k2: r.k2, tinao: r.tinao, ...(tp.zoneSet ? {} : { zone: r.zone }) });
    done();
    tp.routing = r.rail_walk_m != null;          // K1 по улицам: маршрут по пешеходной сети OSM (первый раз — до пары минут)
    if (tp.routing) api("/api/rail_route", { lon, lat }).then(q => {
      if (tp.rev !== rev) return;
      tp.routing = false;
      if (q?.route_m == null) return done();
      tp.walk = q.route_m; tp.walkRoute = true; tp.station = q.station || "";
      if (tp.auto) tp.k1 = q.route_m < 1200 ? 0.75 : q.route_m <= 2200 ? 0.9 : 1.0;
      done();
    }).catch(() => { if (tp.rev === rev) { tp.routing = false; done(); } });
  }).catch(e => {
    tp.rev = rev; tp.districts = [];
    tp.notes = ["район не определён: " + (e?.name === "AbortError" ? "портал OSM не ответил" : e?.message || "портал не ответил") + " — задайте зону вручную"];
  }).finally(() => { clearTimeout(cut); rt.placeBusy = false; done(); });
}

/* ---------- нормативы (web/norms.js): каталог пресета и ручные правки tp.constants ---------- */
export const NORMS = { cat: null, by: {}, error: "" };
let normsLoading = null;
export function loadNorms() {
  return normsLoading ||= fetch("/api/tep/norms").then(r => r.json()).then(j => {
    if (!Array.isArray(j.norms)) throw new Error(j.error || "нет данных");
    NORMS.cat = j; NORMS.by = Object.fromEntries(j.norms.map(n => [n.id, n])); NORMS.error = ""; return j;
  }).catch(e => { normsLoading = null; NORMS.error = e.message; throw e; });
}
/* Правки из проекта: убранная из пресета норма или значение вне пределов отбрасываются (их названия — в ответе); совпавшие — молча */
export function cleanNorms(tp) {
  const o = tp?.constants; if (!o || !NORMS.cat) return [];
  const bad = [];
  for (const [id, v] of Object.entries(o)) {
    const n = NORMS.by[id];
    if (!n) { bad.push(id); delete o[id]; }
    else if (typeof v !== "number" || !(v >= n.min && v <= n.max)) { bad.push(n.title); delete o[id]; }
    else if (v === n.value) delete o[id];
  }
  if (!Object.keys(o).length) delete tp.constants;
  return bad;
}
export function normConstants(tp) { cleanNorms(tp); return tp?.constants && Object.keys(tp.constants).length ? { ...tp.constants } : null; }

/* ---------- ТЭП: геометрические части — здесь, нормативная часть — движок ядра на сервере ---------- */
export function keptBuildings(kept) { const src = kept?.properties?._src || []; return src.filter(f => /Polygon/.test(f.geometry?.type) && insideTerr(f)); }
export const bakedSketch = d => d.fc.features.filter(f => /Polygon/.test(f.geometry?.type)).map(f => ({ f, m2: m2(f), floors: +f.properties["Этажность"] > 0 ? +f.properties["Этажность"] : 1,
  maxF: /ИЖС|Блокированные/.test(f.properties["Типология"] || "") ? 3 : undefined }));
export async function tepRequest(sketch, kept, lim, share, target, tp = {}) {
  const TERR = project.territory, TERR_M2 = m2(TERR), DATA = project.data;
  const keptList = keptBuildings(kept), keptSet = new Set(keptList);
  const sppNew = sketch.reduce((s, b) => s + b.m2 * b.floors, 0), fpNew = sketch.reduce((s, b) => s + b.m2, 0);
  const sppKept = keptList.reduce((s, f) => s + m2(f) * floorsOf(f), 0), fpKept = keptList.reduce((s, f) => s + m2(f), 0);
  const ek = existKey(), demol = ek ? DATA[ek].fc.features.filter(f => /Polygon/.test(f.geometry?.type) && insideTerr(f) && !keptSet.has(f)) : [];
  // площадь сохранения и ограничений: запреты плюс пятна сохраняемых зданий (решение владельца 24.09.2026)
  const restrict = m2(inter(TERR, unionAll([lim, ...keptList].filter(Boolean)))) / 1e4, terr = TERR_M2 / 1e4;
  const sppLow = sketch.filter(b => b.maxF === 3).reduce((s, b) => s + b.m2 * b.floors, 0);        // ИЖС и блокированные: 50 м² квартир на жителя
  await loadNorms().catch(() => null); const consts = normConstants(tp);
  const r = await api("/api/tep", { ...(consts ? { constants: consts } : {}), terr_ha: terr, restrict_ha: restrict, spp_new_m2: sppNew, share, spp_kept_m2: sppKept, spp_low_m2: sppLow,
    nonres_part: tp.nonres ?? 6, education_zone: tp.zone ?? 1, k1: tp.k1 ?? 1, k2: tp.k2 ?? 0.9, tinao: tp.tinao ?? 0, territory_mode: tp.mode ?? 1, unbuilt_share: tp.unbuilt ?? 25,
    free_doo: tp.free?.doo ?? 0, free_school: tp.free?.school ?? 0, free_clinic: tp.free?.clinic ?? 0 });
  const m = Object.fromEntries(r.metrics.map(x => [x.id, x.value]));
  return { m, metrics: r.metrics, social: r.social || [], constantsChanged: r.constants_changed || [], density: r.density_total, target, terr, restrict, sppNew, sppKept, cover: (fpNew + fpKept) / TERR_M2, n: sketch.length, kept: keptList, demolN: demol.length, demolSpp: demol.reduce((s, f) => s + m2(f) * floorsOf(f), 0), existKey: ek };
}

/* Цель плотности по ПЗЗ: средняя предельная плотность подзон внутри границы, взвешенная по площади. */
export function pzzTarget() {
  const fs = project.data["gisogd.pzz_sub"]?.fc.features, TERR = project.territory; if (!fs?.length || !TERR) return null;
  let a = 0, s = 0; const vals = new Set();
  for (const f of fs) { const v = f.properties["Плотность, тыс. м²/га"]; if (typeof v !== "number") continue; const x = inter(TERR, f); const mm = x ? m2(x) : 0; if (mm < 1) continue; a += mm; s += mm * v; vals.add(v); }
  return a ? { value: s / a, share: a / m2(TERR), vals: [...vals].sort((x, y) => x - y) } : { value: null, share: 0, vals: [] };
}

/* ---------- T6: резерв участков ДОО, школы и поликлиники ----------
   Площади участков и их число даёт сервер (/api/tep → social); здесь только место на карте в свободной земле пятна. */
export const RES_KINDS = { doo: "участок ДОО", school: "участок школы", clinic: "участок поликлиники" }, RES_NAMES = { doo: "ДОО", school: "школа", clinic: "поликлиника" };
const RES_GRID = 2500, RES_CHECKS = 800, RES_TESTS = 60;     // бюджет поиска одного участка: узлов сетки, дешёвых и точных проверок
const RES_GAP = 3;              // м от стен корпусов до границы резервного участка
export const reserveRadii = tp => { const cao = CAO(tp?.okrug); return { doo: cao ? 500 : 300, school: cao ? null : 1000, clinic: null }; };   // 2151-ПП табл. 1.4.1–1.4.2 п. 4
const hitsBox = (x0, y0, x1, y1, ring, solid = true) => {
  for (const [x, y] of ring) if (x > x0 && x < x1 && y > y0 && y < y1) return true;
  for (let i = 0; i < ring.length; i++) {
    const [ax, ay] = ring[i], [bx, by] = ring[(i + 1) % ring.length]; if ((ax <= x0 && bx <= x0) || (ax >= x1 && bx >= x1) || (ay <= y0 && by <= y0) || (ay >= y1 && by >= y1)) continue;
    const dx = bx - ax, dy = by - ay; let t0 = 0, t1 = 1, out = false;
    for (const [pp, qq] of [[-dx, ax - x0], [dx, x1 - ax], [-dy, ay - y0], [dy, y1 - ay]]) {
      if (pp === 0) { if (qq <= 0) { out = true; break; } continue; }
      const r = qq / pp; if (pp < 0) { if (r > t1) { out = true; break; } if (r > t0) t0 = r; } else { if (r < t0) { out = true; break; } if (r < t1) t1 = r; } }
    if (!out && t0 < t1) return true;
  }
  if (!solid) return false;
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2; let inside = false;
  for (let i = 0, k = ring.length - 1; i < ring.length; k = i++) if ((ring[i][1] > cy) !== (ring[k][1] > cy) && cx < (ring[k][0] - ring[i][0]) * (cy - ring[i][1]) / (ring[k][1] - ring[i][1]) + ring[i][0]) inside = !inside;
  return inside;
};
export function reserveSocial(site, sketch, social, radii) {
  const out = { plots: [], notes: [], warns: [] };
  if (!site || !social?.length) return out;
  const blds = sketch.map(b => b.f), bu = blds.length ? unionAll(blds) : null, ground = [...(sketch.streets || []), ...(sketch.plots || [])].map(s => s.f);
  let free = site;
  for (const g of [bu && buf(bu, RES_GAP), ...ground]) { if (g && free) free = diff(free, g); }
  const obst = [...blds.map(f => buf(f, RES_GAP) || f), ...ground], houses = blds.map(f => centroid(ringsXY(f)[0]));
  const reach = {};
  const order = { school: 0, doo: 1, clinic: 2 }, list = social.map((s, i) => ({ ...s, i })).sort((a, b) => order[a.kind] - order[b.kind] || a.i - b.i);
  const total = {}; list.forEach(s => { total[s.kind] = (total[s.kind] || 0) + s.places; });
  const seen = {};
  for (const s of list) {
    const n = seen[s.kind] = (seen[s.kind] || 0) + 1, many = list.filter(x => x.kind === s.kind).length > 1, nm = RES_NAMES[s.kind], name = `${nm === "ДОО" ? "ДОО" : nm[0].toUpperCase() + nm.slice(1)}${many ? " №" + n : ""}`;
    const A = s.m2, rad = radii?.[s.kind], st = { cands: 0, checks: 0, tests: 0 }; let best = null, cut = false;
    if (rad && bu) reach[s.kind] ||= buf(bu, rad);
    const rch = rad && bu ? reach[s.kind] : null;
    for (const part of free ? splitParts(free) : []) {
      if (m2(part) < A * .997) continue;
      const { a, b } = partFrame(ringsXY(part)[0], 0), W = rp => rp.map(q => rot(q, a, [0, 0])), L = rp => rp.map(q => rot(q, -a, [0, 0]));
      const box = o => polys(o).map(c => { const r = c[0].map(toXY).map(q => rot(q, -a, [0, 0])), xs = r.map(q => q[0]), ys = r.map(q => q[1]); return { r, x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) }; });
      const ob = obst.flatMap(box), hs = L(houses), edge = polys(part).flatMap(c => c.map(r => r.map(toXY).map(q => rot(q, -a, [0, 0]))));
      const pin = pt => turf.booleanPointInPolygon(pt, part), inPart = rp => rp.every(q => pin(toLL(q)));
      const dh = (x, y) => hs.length ? Math.min(...hs.map(q => Math.hypot(q[0] - x, q[1] - y))) : 0;
      const W0 = Math.sqrt(A * 1.5), shapes = [[W0, A / W0], [A / W0, W0]].filter(([w, h]) => w <= b[2] - b[0] + .1 && h <= b[3] - b[1] + .1);
      const minStep = m2(part) > 1e5 ? 10 : 5;
      for (const fine of [1, 3]) {
        const cands = [];
        for (const [w, h] of shapes) {
          let su = Math.max(minStep, w / 8) / fine, sv = Math.max(minStep, h / 6) / fine; const us = [], vs = [];
          const nGrid = ((b[2] - b[0] - w) / su + 2) * ((b[3] - b[1] - h) / sv + 2); if (nGrid > RES_GRID) { const q = Math.sqrt(nGrid / RES_GRID); su *= q; sv *= q; }
          for (let u = b[0]; u + w <= b[2] + .01; u += su) us.push(u); us.push(b[2] - w);
          for (let v = b[1]; v + h <= b[3] + .01; v += sv) vs.push(v); vs.push(b[3] - h);
          for (const v of vs) for (const u of us) {
            if (edge.some(r => hitsBox(u, v, u + w, v + h, r, false))) continue;
            if (ob.some(o => o.x1 > u - .5 && o.x0 < u + w + .5 && o.y1 > v - .5 && o.y0 < v + h + .5 && hitsBox(u - .5, v - .5, u + w + .5, v + h + .5, o.r))) continue;
            cands.push({ u, v, w, h, d: dh(u + w / 2, v + h / 2) });
          }
        }
        cands.sort((p, q) => p.d - q.d);
        st.cands += cands.length;
        for (const c of cands) {
          if (best && c.d >= best.d) break;
          if (st.checks >= RES_CHECKS || st.tests >= RES_TESTS) { cut = true; break; }
          st.checks++;
          let ring = W(rect(c.u, c.v, c.u + c.w, c.v + c.h));
          if (!inPart(ring) || !pin(toLL(W([[c.u + c.w / 2, c.v + c.h / 2]])[0]))) continue;
          if (rch && !ring.some(q => turf.booleanPointInPolygon(toLL(q), rch))) continue;
          st.tests++;
          let f = polyLL(ring); const k = Math.sqrt(A / m2(f));
          if (Math.abs(k - 1) > 1e-6) { const mx = c.u + c.w / 2, my = c.v + c.h / 2; ring = W(rect(mx - c.w * k / 2, my - c.h * k / 2, mx + c.w * k / 2, my + c.h * k / 2)); f = polyLL(ring); }
          if (m2(inter(part, f)) >= m2(f) * .997 && (!rch || m2(inter(rch, f)) > 0)) { best = { f, d: c.d }; break; }
        }
        if (best || cut) break;
      }
    }
    const ha = fmt(A / 1e4, 3); (out.stats ||= []).push({ name, ...st, cut: cut && !best });
    if (!best && cut) { out.partial = true; out.notes.push(`${name} (${ha} га): поиск места прерван: слишком сложное пятно`); out.warns.push(`${name}: поиск места прерван`); }
    else if (best) { out.plots.push({ f: best.f, kind: RES_KINDS[s.kind], m2: m2(best.f), "Участок": name, "Места": s.places, "Дефицит": total[s.kind] }); free = diff(free, best.f); obst.push(best.f); }
    else {
      out.notes.push(rad ? `${name} (${ha} га) не помещается в свободной земле пятна (в радиусе ${fmt(rad)} м от домов) — освободите землю`
        : `${name} (${ha} га) не помещается в свободной земле пятна — освободите землю (сократите СПП или снимите ограничения)`);
      out.warns.push(`${name}: ${ha} га не помещается`);
    }
  }
  return out;
}
export function reserveSummary(t) {
  const s = t.social || []; if (!s.length) return "Резерв участков не нужен";
  const cnt = k => s.filter(x => x.kind === k).length, parts = [cnt("doo") && `ДОО ${cnt("doo")}`, cnt("school") && `школа ${cnt("school")}`, cnt("clinic") && `поликлиника ${cnt("clinic")}`].filter(Boolean);
  const ha = s.reduce((a, x) => a + x.m2, 0) / 1e4;
  return `Резерв: ${parts.join(", ")} · ${fmt(ha, 3)} га (${fmt(t.terr ? ha / t.terr * 100 : 0, 0)} %)`;
}
