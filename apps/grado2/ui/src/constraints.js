/* ГРАДО 2 · ограничения в новом интерфейсе — перенос расчёта окна «Ограничения» рабочей страницы (web/constraints.js
   computeConstraints): из загруженных данных строятся обычные слои группы «Ограничения» — ЗОУИТ и охранные зоны,
   водные объекты, отступ от красных линий, сохраняемые здания с противопожарными разрывами, подзоны ПЗЗ без нового
   строительства, природные зоны Генплана, инсоляционный фронт окон соседей и предельная высота по солнцу и ПЗЗ.
   Слои берутся по роли (web/roles.js), инсоляция — тот же модуль web/insol.js (ГОСТ Р 57795-2017, предпроектная
   оценка, не сертифицированный расчёт). Настройки — те же, что у рабочей страницы (localStorage «grado2.cons»).
   Узел «Ограничения» схемы расчёта и проверка норм эскиза переедут вместе со схемой и эскизом. */
import { reactive } from "vue";
import * as turf from "@turf/turf";
import * as insolModule from "../../web/insol.js";
import "../../web/roles.js";
import { project } from "./store.js";
import { lyr, newGroup, normGroups, touchData } from "./edit.js";
import { busy, markDirty, notice } from "./project.js";
import { ensureLayer } from "./data.js";
import { fullStyle } from "./symbology.js";
import { bboxOf, buf, floorsOf, inter, m2, plural, polys, ringsXY, safe, setFrame, toLL, toXY, unionAll } from "./geom.js";

const INSOL = globalThis.INSOL || insolModule.default || insolModule;
globalThis.INSOL ||= INSOL;     // web/blocks.js (урбан-блоки) читает инсоляцию из глобального INSOL

export const CONS = reactive({ waterLine: 5, norm: 2, z: 2, step: 4, reveal: 0, cell: 8, floorH: 3, redline: 5, cap: 150,
  use: { zouit: true, red: true, fire: true, pzz: true, gp: true, insol: true }, log: null, running: "" });
try {
  const saved = JSON.parse(localStorage.getItem("grado2.cons") || "{}");
  Object.keys(CONS).forEach(k => { if (!["use", "log", "running"].includes(k) && saved[k] != null && Number.isFinite(Number(saved[k]))) CONS[k] = Number(saved[k]); });
  Object.keys(CONS.use).forEach(k => { if (typeof saved.use?.[k] === "boolean") CONS.use[k] = saved.use[k]; });
} catch { /* настроек нет — умолчания */ }
if (!(CONS.step >= 2 && CONS.step <= 20)) CONS.step = 4;
if (!(CONS.cell >= 4 && CONS.cell <= 20)) CONS.cell = 8;
export function keepCons() {
  try { const { log, running, ...rest } = CONS; void log; void running; localStorage.setItem("grado2.cons", JSON.stringify(rest)); } catch { /* частный режим браузера */ }
}

export const CONS_GROUP = "Ограничения";
export const CK = { zouit: "cons:zouit", red: "cons:redlines", fire: "cons:fire", water: "cons:water", pzz: "cons:pzz0", gp: "cons:gpnature", front: "cons:front", ceil: "cons:ceiling" };

/* противопожарный разрыв до существующего здания по материалу стен ЕГРН — СП 4.13130.2013, табл. 1 */
function fireGap(f) {
  const m = String(f.properties["Материал стен"] || "").toLowerCase();
  if (/дерев|брус|бревен|каркасно|щитов/.test(m)) return 10;
  if (/смешан|проч|иные|металл/.test(m)) return 8;
  return 6;
}
const isChildren = f => { const p = f.properties, s = [p["Назначение"], p["Тип здания"], p["Наименование"], p["Вид"]].join(" ").toLowerCase();
  return /школ|гимнази|лице[йя]|детск(ий|ого) сад|дошкол|ясли|school|kindergarten/.test(s); };
const isResidential = f => { const p = f.properties, s = String(p["Назначение"] || p["Тип здания"] || "").toLowerCase();
  return !/нежил/.test(s) && /жил|многокварт|residential|apartments|house|detached|terrace|bungalow|cabin|semi|dormitory/.test(s) || isChildren(f); };
const decisionOf = f => String(f.properties["Решение"] || "сохраняем");

/* Рельеф: отметка земли по горизонталям (слой relief.contours), средневзвешенная по ближайшим вершинам. */
let RELIEF_G = null;
function groundAt(x, y) {
  const d = project.data["relief.contours"], key = d?.fc;
  if (!RELIEF_G || RELIEF_G.key !== key || RELIEF_G.terr !== project.territory) {
    const pts = [];
    (d?.fc?.features || []).forEach(f => { const e = +(f.properties["Высота, м"] ?? f.properties.elev); if (!isFinite(e)) return;
      const g = f.geometry; (g.type === "LineString" ? [g.coordinates] : g.type === "MultiLineString" ? g.coordinates : []).forEach(l => l.forEach(c => { const q = toXY(c); pts.push([q[0], q[1], e]); })); });
    const base = pts.length ? Math.min(...pts.map(p => p[2])) : 0, idx = new Map(), C = 50;
    pts.forEach(p => { const k = Math.floor(p[0] / C) + "," + Math.floor(p[1] / C); (idx.get(k) || idx.set(k, []).get(k)).push(p); });
    RELIEF_G = { key, terr: project.territory, pts, base, idx, C };
  }
  const G = RELIEF_G; if (!G.pts.length) return 0;
  let near = [];
  for (let r = 1; r <= 6 && near.length < 6; r++) { near = [];
    for (let i = -r; i <= r; i++) for (let j = -r; j <= r; j++) near.push(...(G.idx.get((Math.floor(x / G.C) + i) + "," + (Math.floor(y / G.C) + j)) || [])); }
  if (!near.length) return 0;
  near = near.map(p => [p[2], Math.hypot(p[0] - x, p[1] - y)]).sort((a, b) => a[1] - b[1]).slice(0, 6);
  if (near[0][1] < 0.5) return near[0][0] - G.base;
  const w = near.map(n => 1 / n[1] ** 2); return near.reduce((s, n, i) => s + n[0] * w[i], 0) / w.reduce((a, b) => a + b, 0) - G.base;
}
const ringMid = r => { let x = 0, y = 0; r.forEach(p => { x += p[0]; y += p[1]; }); return [x / r.length, y / r.length]; };

/* Слой ограничения: данные заменяются целиком (исходной выгрузки нет), новый слой получает оформление и встаёт
   в группу «Ограничения»; прежний слой сохраняет ваше оформление и видимость. */
function consLayer(key, title, fc, geom, style) {
  const had = !!lyr(key);
  project.data[key] = { title, source: "ограничение, рассчитано " + new Date().toLocaleString("ru-RU"), fetched_at: new Date().toISOString().slice(0, 10), fc };
  const l = ensureLayer(key, title);
  if (!had) { l.geom = geom; l.style = fullStyle(style); l.visible = true; }
  l.title = title;
  let g = project.groups.find(x => x.title === CONS_GROUP);
  if (!g) { newGroup([key], CONS_GROUP); g = project.groups.find(x => x.title === CONS_GROUP); }
  l.group = g.id; normGroups();
  return l;
}

const R = () => { const r = window.Roles; r.use({ DATA: project.data, LYR: project.layers }); return r; };
const clip = (f, terr) => { const r = inter(f, terr); return r && m2(r) > 1 ? r : null; };
const cleanTitle = t => String(t || "").replace(/\s*\((ОГД|ЕГРН|ЕГКО|OSM)\)\s*$/, "");
const roleFeats = (role, re = /Polygon/) => R().info(role).flatMap(L => project.data[L.key].fc.features.filter(f => re.test(f.geometry?.type)).map(f => ({ f, L })));
const nameOf = (f, L, fields) => { for (const k of fields) { const v = f.properties?.[k]; if (v != null && String(v).trim() !== "") return String(v).trim(); } return L.codeTitle || cleanTitle(L.title); };
function usedLine(label, roles, n, unit = ["объект", "объекта", "объектов"]) {
  const ls = [].concat(roles).flatMap(r => R().info(r));
  if (!ls.length) return `${label}: слоёв этой роли нет`;
  const names = ls.slice(0, 3).map(l => l.title).join(", ") + (ls.length > 3 ? ` и ещё ${ls.length - 3}` : "");
  return `${label}: ${plural(n, unit)} · ${plural(ls.length, ["слой", "слоя", "слоёв"])} — ${names}`;
}
const ZONE_FIELDS = ["Вид зоны", "vid_zouit", "Наименование", "Название", "type_zone"];

/* Радиус защиты соседей: тень высокого дома у границы при солнце ~10° над горизонтом; 200…600 м. */
function protectR(TERR) {
  const hs = R().features("pzz_sub").filter(f => f.properties["Высота, м"] > 0 && safe(() => turf.booleanIntersects(f, TERR))).map(f => +f.properties["Высота, м"]);
  const H = Math.min(CONS.cap, hs.length ? Math.max(...hs) : 75);
  return Math.max(200, Math.min(600, Math.round(H / Math.tan(10 * Math.PI / 180) / 50) * 50));
}

export async function computeConstraints() {
  const TERR = project.territory;
  if (!TERR) { notice.value = "Сначала задайте границу территории (окно «Данные»)"; return; }
  if (CONS.running) return;
  keepCons();
  await R().ready();
  setFrame(turf.centroid(TERR).geometry.coordinates);
  const Rp = protectR(TERR), zone = buf(TERR, Rp), log = [], tick = () => new Promise(r => setTimeout(r, 0));
  busy.value = true; CONS.running = "Расчёт…";
  try {
    if (CONS.use.zouit) {
      const out = [], add = (f, L, why) => { if (!why) return; const c = clip(f, TERR); if (c) out.push(turf.feature(c.geometry, { "Причина": why, "Источник": L.title, "Наименование": f.properties["Наименование"] || f.properties["Название"] || "" })); };
      roleFeats("zouit").forEach(({ f, L }) => add(f, L, nameOf(f, L, ZONE_FIELDS)));
      roleFeats("szz").forEach(({ f, L }) => add(f, L, f.properties["Вид зоны"] || L.codeTitle || "СЗЗ"));
      roleFeats("okn").forEach(({ f, L }) => { const v = f.properties["Вид зоны"] || L.codeTitle || cleanTitle(L.title); add(f, L, /регулирован/i.test(v) ? null : `ОКН: ${v}`); });
      consLayer(CK.zouit, "Запрет: ЗОУИТ и охранные зоны", turf.featureCollection(out), "poly", { mode: "cat", hatch: true, width: 1.2, cat: { field: "Причина", colors: {}, off: [] } });
      log.push(usedLine("ЗОУИТ и охранные зоны", ["zouit", "szz", "okn"], out.length, ["зона", "зоны", "зон"]) + (R().keys("okn").length ? "" : " (ОКН не загружены)"));
      const wat = []; roleFeats("water", /Polygon|Line/).forEach(({ f, L }) => { const g = /Line/.test(f.geometry.type) ? buf(f, CONS.waterLine) : f, c = g && clip(g, TERR);
        if (c) wat.push(turf.feature(c.geometry, { "Причина": "водный объект: " + (f.properties["Вид"] || nameOf(f, L, [])), "Источник": L.title })); });
      consLayer(CK.water, "Запрет: водные объекты", turf.featureCollection(wat), "poly", { fill: "#2a78d6", stroke: "#1a4f94", opacity: 0.3, width: 1 });
      log.push(usedLine("водные объекты", "water", wat.length));
    }
    if (CONS.use.red) {
      const lines = R().features("red_lines").filter(f => /Line/.test(f.geometry?.type) && safe(() => turf.booleanIntersects(f, zone)));
      const out = lines.map(f => buf(f, CONS.redline)).filter(Boolean).map(f => clip(f, TERR)).filter(Boolean);
      const u = unionAll(out), fc = turf.featureCollection(u ? [turf.feature(u.geometry, { "Причина": `отступ ${CONS.redline} м от красных линий`, "Норма": "СП 42.13330.2016" })] : []);
      consLayer(CK.red, `Запрет: ${CONS.redline} м от красных линий`, fc, "poly", { fill: "#d7191c", stroke: "#d7191c", hatch: true, width: 1 });
      log.push(R().keys("red_lines").length ? usedLine("красные линии", "red_lines", lines.length, ["линия", "линии", "линий"]) : "красные линии не загружены (нет слоя с ролью «Красные линии») — отступ не построен");
    }
    await tick();
    const ek = R().existingBuildingsKey(), exist = ek ? project.data[ek].fc.features.filter(f => /Polygon/.test(f.geometry?.type) && safe(() => turf.booleanIntersects(f, zone))) : [];
    const kept = exist.filter(f => decisionOf(f) !== "сносим");
    if (CONS.use.fire) {
      const out = kept.map(f => { const g = fireGap(f), b = buf(f, g), c = b && clip(b, TERR); return c ? turf.feature(c.geometry, { "Причина": `противопожарный разрыв ${g} м`, "Материал стен": f.properties["Материал стен"] || "нет данных", "Норма": "СП 4.13130.2013, табл. 1" }) : null; }).filter(Boolean);
      consLayer(CK.fire, "Запрет: сохраняемые здания и пожарные разрывы", turf.featureCollection(out), "poly", { fill: "#eb6834", stroke: "#b34a1c", opacity: 0.25, width: 0.8 });
      log.push(ek ? `сохраняемых зданий: ${kept.length} из ${exist.length} в полосе защиты (слой «${project.data[ek].title}»; «сносим» не учитывается)` : "здания не загружены (нет слоя с ролью «Здания»)");
    }
    if (CONS.use.pzz) {
      const sub = roleFeats("pzz_sub"), zero = sub.map(x => x.f).filter(f => /не предусмотрено/.test(f.properties["Регламент"] || "")).map(f => { const c = clip(f, TERR); return c && turf.feature(c.geometry, { "Причина": "ПЗЗ: нулевые параметры", "Номер подзоны": f.properties["Номер подзоны"] ?? f.properties.podzone_num, "Документ": f.properties["Документ"] ?? f.properties.num_pp }); }).filter(Boolean);
      consLayer(CK.pzz, "Запрет: ПЗЗ без нового строительства", turf.featureCollection(zero), "poly", { fill: "#8a5a00", stroke: "#8a5a00", hatch: true, width: 1 });
      log.push(!sub.length ? "ПЗЗ не загружены (нет слоя с ролью «ПЗЗ: подзоны»)" : usedLine("подзоны ПЗЗ без строительства", "pzz_sub", zero.length, ["подзона", "подзоны", "подзон"])
        + (sub.some(x => x.f.properties["Регламент"] != null) ? "" : `; в слое ${sub.length} подзон, но регламент (плотность, высота) не разобран — выгрузка сырая, запрет по нулевым параметрам не построен`));
    }
    if (CONS.use.gp) {
      const natural = v => /природн|озелен|парков|лесопарк|оопт|особо охраняем/i.test(v) && !/жил/i.test(v);
      const fz = roleFeats("func_zones"), FZ = ["naimfunkzony", "Вид зоны", "Название", "zone_title"];
      const out = fz.map(({ f, L }) => ({ f, L, t: nameOf(f, L, FZ) })).filter(x => natural(x.t)).map(({ f, L, t }) => { const c = clip(f, TERR); return c && turf.feature(c.geometry, { "Причина": `Генплан: ${t}`, "Источник": L.title }); }).filter(Boolean);
      consLayer(CK.gp, "Запрет: природные зоны Генплана", turf.featureCollection(out), "poly", { fill: "#2e7d32", stroke: "#2e7d32", hatch: true, width: 1 });
      log.push(fz.length ? usedLine("природные зоны Генплана", "func_zones", out.length, ["зона", "зоны", "зон"]) : "функциональные зоны Генплана не загружены (нет слоя с ролью «Функциональные зоны»)");
    }
    await tick();
    if (CONS.use.insol) {
      const t0 = performance.now(), lat = turf.centroid(TERR).geometry.coordinates[1];
      const open = r => r.length > 1 && r[0][0] === r[r.length - 1][0] && r[0][1] === r[r.length - 1][1] ? r.slice(0, -1) : r;
      const prism = f => polys(f).map(p => { const ring = open(p[0].map(toXY)), g = groundAt(...ringMid(ring));
        return { ring, holes: p.slice(1).map(h => open(h.map(toXY))), g, h: g + floorsOf(f) * CONS.floorH, f }; });
      const obst = kept.flatMap(prism), resid = kept.filter(isResidential).flatMap(prism);
      const ob = INSOL.obstacleIndex(obst), paths = INSOL.DATES.map(d => INSOL.sunPath(lat, d.day, 5));
      const pts = INSOL.frontPoints(resid, CONS.step, CONS.z);
      for (let i = 0; i < pts.length; i += 200) { INSOL.evalFront(pts.slice(i, i + 200), ob, paths, { norm: CONS.norm * 60, reveal: CONS.reveal }); CONS.running = `Инсоляция: фасады ${Math.min(pts.length, i + 200)} из ${pts.length}…`; await tick(); }
      const fmin = m => `${Math.floor(m / 60)} ч ${String(m % 60).padStart(2, "0")} мин`;
      const front = turf.featureCollection(pts.map(p => turf.point(toLL([p.x, p.y]), { "Норма": p.orient ? "не нормируется (фасад на север)" : p.worst.ok ? `выполняется (${p.worst.ok})` : "не выполняется до застройки", "Непрерывно": fmin(p.worst.cont), "Всего": fmin(p.worst.total), "Непрерывно, мин": p.worst.cont, "Здание": resid[p.b].f.properties["Адрес"] || resid[p.b].f.properties["Кадастровый номер"] || "" })));
      consLayer(CK.front, "Инсоляция: окна соседей (фронт)", front, "point", { mode: "cat", width: 1.2, maxDen: 2500, cat: { field: "Норма", colors: { "выполняется (непрерывная)": "#1f7a4d", "выполняется (прерывистая)": "#eda100", "не выполняется до застройки": "#b3261e", "не нормируется (фасад на север)": "#9aa1a8" }, off: [] } });
      const tb = bboxOf(ringsXY(TERR)[0]), cell = CONS.cell, nx = Math.ceil((tb[2] - tb[0]) / cell), ny = Math.ceil((tb[3] - tb[1]) / cell);
      const grid = { x0: tb[0], y0: tb[1], cell, nx, ny, inside: new Uint8Array(nx * ny) };
      const tRings = ringsXY(TERR)[0], inPoly = (x, y) => { let c = false; for (let i = 0, j = tRings.length - 1; i < tRings.length; j = i++) { const a = tRings[i], b = tRings[j]; if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) c = !c; } return c; };
      for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) grid.inside[j * nx + i] = inPoly(tb[0] + (i + 0.5) * cell, tb[1] + (j + 0.5) * cell) ? 1 : 0;
      CONS.running = "Инсоляция: предельная высота по солнцу…"; await tick();
      const gmax = Math.max(0, ...obst.map(p => p.g || 0)) + 50, capAbs = CONS.cap + gmax;
      const { env } = INSOL.envelope(pts, paths, grid, { norm: CONS.norm * 60, cap: capAbs });
      const pzz = roleFeats("pzz_sub").map(x => x.f).filter(f => f.properties["Высота, м"] > 0).map(f => ({ f, h: +f.properties["Высота, м"] }));
      const cells = [];
      for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
        const n = j * nx + i; if (!grid.inside[n]) continue;
        const x = tb[0] + i * cell, y = tb[1] + j * cell, cx = toLL([x + cell / 2, y + cell / 2]);
        const hp = pzz.find(z => safe(() => turf.booleanPointInPolygon(cx, z.f)))?.h ?? null, hs = env[n] >= capAbs - 0.01 ? null : Math.max(0, env[n] - groundAt(x + cell / 2, y + cell / 2));
        const top = Math.min(hs ?? Infinity, hp ?? Infinity);
        if (top === Infinity) continue;
        cells.push(turf.polygon([[toLL([x, y]), toLL([x + cell, y]), toLL([x + cell, y + cell]), toLL([x, y + cell]), toLL([x, y])]], {
          "Предельная высота, м": Math.floor(top * 10) / 10, "Предельная высота, эт.": Math.floor(top / CONS.floorH),
          "По инсоляции, м": hs == null ? null : Math.floor(hs * 10) / 10, "По ПЗЗ, м": hp, "Почему": hs != null && (hp == null || hs <= hp) ? "тень на окна соседей" : hp != null ? "высота по ПЗЗ" : "не ограничено" }));
      }
      consLayer(CK.ceil, "Предельная высота застройки (инсоляция соседей, ПЗЗ)", turf.featureCollection(cells), "poly", { mode: "grad", opacity: 0.4, stroke: "#ffffff", width: 0, grad: { field: "Предельная высота, эт.", n: 5, ramp: "green", method: "equal" } });
      const north = pts.filter(p => p.orient).length, bad = pts.filter(p => !p.orient && !p.worst.ok).length;
      log.push(`инсоляция: ${pts.length} расчётных точек на ${resid.length} жилых домах в ${Rp} м от границы (дома дальше полосы выгрузки 60 м не загружены и не защищены); ${north} на северных фасадах (не нормируются), ${bad} не выполняют норму уже сейчас — для них «не ухудшать»; ${Math.round(performance.now() - t0)} мс`);
    }
    touchData(); markDirty(); import("./graph.js").then(m => m.ensureConsNode());   // блок «Ограничения» в схеме расчёта, как web/constraints.js
    CONS.log = log; notice.value = "Ограничения рассчитаны. Выключенный слой группы «Ограничения» генерация не учитывает";
  } catch (e) { console.error(e); notice.value = "Ограничения не рассчитаны: " + e.message; }
  finally { busy.value = false; CONS.running = ""; }
}
