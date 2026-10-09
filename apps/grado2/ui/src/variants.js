/* ГРАДО 2 · варианты эскиза нового интерфейса (как web/app.js «варианты» и «сохранённые варианты» T59).
   Подбор: перебор типологий × ширины корпуса × поворота (вдоль и поперёк длинной стороны участков), этажность — под цель
   плотности блока ТЭП, не выше предельной высоты; оценка — отклонение плотности от цели и доля фасадов новых домов с
   нормой инсоляции. Выбранный вариант переносит параметры в схему. Сохранённые варианты — именные снимки эскиза
   с показателями в блоке «ТЭП КРТ» (properties.saved), тот же формат, что у рабочей страницы. */
import { reactive, shallowRef, watch } from "vue";
import * as turf from "@turf/turf";
import { project, currentId } from "./store.js";
import { dataRev, lyr, touchData } from "./edit.js";
import { notice, busy } from "./project.js";
import { CHECK, ownInsolation } from "./constraints.js";
import { floorsOf, m2 } from "./geom.js";
import { FLOOR_MODES, LOWRISE, TYPOLOGIES } from "./graphfile.js";
import { RESULT, densityGoal, edited, inputOf, placeParams, tick } from "./graph.js";
import { bakedSketch, keptBuildings, tepParams, tepRequest } from "./tep.js";
import { bakeSketch, wi, wv } from "./sketch.js";
import { generate } from "./sketchgen.js";

export const VARS = shallowRef([]);             // посчитанные варианты, лучшие сверху
export const VS = reactive({ sel: -1, running: false, stop: false, done: 0, total: 0, msg: "" });
export const vName = v => `${v.typ}${v.typ === "ИЖС" ? "" : v.typ === "Урбан-блоки" ? ` · квартал ${v.block} м` : ` · ${v.width} м`} · ${v.angle ? "поперёк" : "вдоль"}`;
const terrM2 = () => project.territory ? m2(project.territory) : 0;

/* показатели всех вариантов: не больше 4 запросов одновременно; stale() — ответ устарел, остальные запросы не посылаются */
async function tepForVars(vs, kept, lim, share, target, tp, stale = () => false) {
  const out = new Array(vs.length); let next = 0;
  await Promise.all(Array.from({ length: Math.min(4, vs.length) }, async () => { while (next < vs.length && !stale()) { const i = next++; out[i] = await tepRequest(vs[i].sk, kept, lim, share, target, tp); } }));
  return out;
}
const OID = new WeakMap(); let oidN = 0;
const gid = o => { if (!o || typeof o !== "object") return "-"; let v = OID.get(o); if (!v) OID.set(o, v = ++oidN); return v; };
function tepKeyNow() {
  const t = RESULT.tepNode; if (!t) return null; const q = tepParams(t);
  return [JSON.stringify(q.constants || {}), JSON.stringify(q.free || {}), q.nonres, q.zone, q.k1, q.k2, q.tinao, q.mode, q.unbuilt, t.widgets_values[0], t.widgets_values[1],
    gid(inputOf(t, 1)), gid(inputOf(t, 2)), gid(project.territory), dataRev.value].join("|");
}
/* нормативы или параметры территории изменились — показатели вариантов пересчитываются тем же запросом, что «Показатели» */
let tepKey = null, tepTimer = 0, tepSeq = 0;
watch(tick, () => {
  if (!VARS.value.length || VS.running || !RESULT.tepNode || tepKey === null || tepKey === tepKeyNow()) return;
  clearTimeout(tepTimer); tepTimer = setTimeout(async () => {
    const t = RESULT.tepNode, key = tepKeyNow(); if (!t || !VARS.value.length || VS.running || key === tepKey) return;
    const seq = ++tepSeq, raw = project.raw, vs = VARS.value.slice(), w = t.widgets_values, tp = JSON.parse(JSON.stringify(tepParams(t)));
    busy.value = true;
    try {
      const res = await tepForVars(vs, inputOf(t, 1), inputOf(t, 2), w[0] / 100, w[1], tp, () => seq !== tepSeq || raw !== project.raw);
      if (seq !== tepSeq || raw !== project.raw) return;
      vs.forEach((v, i) => { v.tep = res[i]; }); tepKey = key; VARS.value = vs.slice();
    } catch (e) { console.warn("варианты: пересчёт показателей не удался", e); }
    finally { busy.value = false; }
  }, 400);
});
watch(() => project.raw, () => { VARS.value = []; VS.sel = -1; VS.stop = true; tepKey = null; SV.cmp = ""; });

const progress = (done, total, msg) => { VS.done = done; VS.total = total; VS.msg = msg; };
export function stopVariants() { if (VS.running) { VS.stop = true; VS.msg = "Останавливаю: дорабатывает текущий вариант…"; } }
export async function runVariants() {
  const p = RESULT.placeNode, t = RESULT.tepNode, T = project.territory;
  if (!p || !RESULT.site || !T) { notice.value = "В схеме расчёта нет пятна застройки или блока посадки: задайте территорию и загрузите данные"; return; }
  if (!t) { notice.value = "В схеме расчёта нет блока «ТЭП КРТ»: варианты сравниваются по его целевой плотности"; return; }
  const base = placeParams(p), w = t.widgets_values, share = w[0] / 100, target = w[1], kept = inputOf(t, 1), lim = inputOf(t, 2), goal = densityGoal();
  const TM = terrM2(), ha = TM / 1e4, sppKept = keptBuildings(kept).reduce((s, f) => s + m2(f) * floorsOf(f), 0);
  // малоэтажные типологии (ИЖС, блокированные) — только при цели до 10 тыс. м²/га: плотнее они не бывают
  const widthsOf = typ => typ === "ИЖС" ? [base.width] : typ === "Блокированные" ? [12, 14] : typ === "Квартал" ? [14, 18] : typ === "Урбан-блоки" ? [16] : [14, 17];
  const cands = []; for (const typ of TYPOLOGIES) { if (LOWRISE.has(typ) && target > 10) continue;
    for (const width of widthsOf(typ)) for (const angle of [0, 90]) for (const block of typ === "Урбан-блоки" ? [80, 110] : [base.block]) cands.push({ typ, width, angle, block }); }
  const NINS = 8, total = cands.length + NINS + 1, raw = project.raw, pause = () => new Promise(r => setTimeout(r, 0));
  Object.assign(VS, { running: true, stop: false, sel: -1 }); busy.value = true; const out = []; VARS.value = [];
  try {
    for (const [i, c] of cands.entries()) {
      if (VS.stop) break;
      progress(i, total, `Посадка: вариант ${i + 1} из ${cands.length} — ${c.typ}, ${c.width} м, ${c.angle ? "поперёк" : "вдоль"}…`); await pause();
      const sk = generate(RESULT.site, { ...base, ...c, goal }); if (!sk.length) continue;
      const spp = sk.reduce((s, b) => s + b.m2 * b.floors, 0), fp = sk.reduce((s, b) => s + b.m2, 0);
      out.push({ ...c, sk, n: sk.length, spp, density: (spp + sppKept) / 1000 / ha, cover: fp / TM, avg: spp / fp, capped: sk.filter(b => b.capped).length });
    }
    out.forEach(v => { v.err = Math.abs(v.density - target) / target; }); out.sort((a, b) => a.err - b.err);
    for (const [i, v] of out.slice(0, NINS).entries()) {
      if (VS.stop) break;
      progress(cands.length + i, total, `Инсоляция новых домов: вариант ${i + 1} из ${Math.min(NINS, out.length)}…`); await pause(); v.own = ownInsolation(v.sk);
    }
    out.forEach(v => { v.score = v.err + (v.own == null ? .3 : (100 - v.own) / 100 * .5); });   // недобор инсоляции весит как половина отклонения плотности
    out.sort((a, b) => a.score - b.score);
    progress(total - 1, total, "Показатели лучших вариантов…");
    tepKey = tepKeyNow(); const res = await tepForVars(out, kept, lim, share, target, tepParams(t), () => raw !== project.raw); out.forEach((v, i) => { v.tep = res[i]; });
    if (raw !== project.raw) { notice.value = "Подбор вариантов для прежнего проекта отброшен"; return; }
    VARS.value = out;
    VS.msg = !out.length ? (VS.stop ? "Подбор остановлен до первого варианта." : "Ни один вариант не поместился в пятно застройки: проверьте ограничения и цель плотности.")
      : VS.stop ? `Подбор остановлен: вариантов ${out.length} из ${cands.length}${out.some(v => v.own == null) ? ", у части инсоляция не посчитана (—)" : ""}.` : `Вариантов: ${out.length}.`;
    if (out.length) notice.value = VS.msg + " Щелчок по карточке или строке таблицы переносит параметры в схему и на карту";
  } catch (e) { console.error(e); VS.msg = "Подбор не удался: " + e.message; notice.value = "Варианты не посчитались: " + e.message; }
  finally { VS.running = false; busy.value = false; }
}
/* вариант → поля блока посадки (этажность — по цели плотности), посадка включается */
export function pickVariant(i) {
  const v = VARS.value[i], p = RESULT.placeNode; if (!v || !p) return; VS.sel = i;
  const set = (name, val) => { const k = wi(p, name); if (k >= 0) p.widgets_values[k] = val; };
  set("типология", v.typ); set("ширина корпуса, м", v.width); set("поворот, °", v.angle); if (v.block) set("квартал, м", v.block); set("этажность по", FLOOR_MODES[1]);
  (p.properties ||= {}).run = true; edited();
  notice.value = `Вариант «${vName(v)}» перенесён в схему: на карте эскиз этого варианта`;
}
export const bakeVariant = () => VS.sel < 0 ? (notice.value = "Выберите вариант в списке — щелчок по карточке") : bakeSketch();

/* ---------- сохранённые варианты (T59): node.properties.saved = [{id, name, at, typ, n, avg, spp, cover, density, pop, doo, own, sig, sk:[{g, floors, kind?, grp?}]}] ---------- */
export const SV = reactive({ ask: "", val: "", ren: null, arm: null, cmp: "" });
export const SV_MAX = 20;                      // не больше 20 вариантов: схема уходит в файл целиком
export const savedList = () => { void tick.value; return RESULT.tepNode?.properties?.saved || []; };
const svRound = g => JSON.parse(JSON.stringify(g, (k, v) => typeof v === "number" ? Math.round(v * 1e6) / 1e6 : v));
/* текущий эскиз: принятый слой (с правками этажности и переносами) или результат схемы */
export function svCurrent() {
  void tick.value;
  const t = RESULT.tepNode, bk = t?.properties?.baked, bd = bk && project.data[bk];
  if (bd) return { sk: bakedSketch(bd), typ: bd.fc.features[0]?.properties?.["Типология"] || wv(RESULT.placeNode || { type: "" }, "типология") || "" };
  return { sk: RESULT.sketch || [], typ: RESULT.placeNode ? wv(RESULT.placeNode, "типология") : "" };
}
export const svSig = sk => sk.map(b => { const c = turf.centroid(turf.feature(svRound(b.f.geometry), {})).geometry.coordinates;      // по округлённой геометрии: открытый вариант совпадает со своей подписью
  return b.floors + ":" + c[0].toFixed(6) + "," + c[1].toFixed(6); }).join(";");
export function svDefName() { const L = savedList(); let i = L.length + 1; while (L.some(r => r.name === "Мой вариант " + i)) i++; return "Мой вариант " + i; }
export function svAsk(where) {
  if (savedList().length >= SV_MAX) { notice.value = `Сохранено ${SV_MAX} вариантов — это предел: удалите ненужные в окне «Варианты»`; return; }
  if (!svCurrent().sk.length) { notice.value = "Эскиз пуст: сначала «Построить эскиз»"; return; }
  if (!RESULT.tep) { notice.value = "Показатели ещё считаются: повторите через секунду"; return; }
  SV.ask = where; SV.val = svDefName();
}
export function svCommit() {
  const c = svCurrent(), t = RESULT.tep, name = SV.val.trim() || svDefName(); if (!c.sk.length || !t) return;
  if (savedList().length >= SV_MAX) { notice.value = `Сохранено ${SV_MAX} вариантов — это предел: удалите ненужные в окне «Варианты»`; return; }
  if (savedList().some(r => r.name === name)) { notice.value = `Вариант «${name}» уже есть: назовите иначе`; return; }
  if (Math.abs((t.sppNew || 0) - c.sk.reduce((q, b) => q + b.m2 * b.floors, 0)) >= 1) { notice.value = "Показатели ещё считаются по прежнему эскизу: повторите через секунду"; return; }
  const spp = c.sk.reduce((q, b) => q + b.m2 * b.floors, 0), fp = c.sk.reduce((q, b) => q + b.m2, 0), TM = terrM2();
  const rec = { id: "sv" + Date.now().toString(36), name, at: new Date().toISOString().slice(0, 10), typ: c.typ, n: c.sk.length, avg: fp ? spp / fp : 0, spp, cover: TM ? fp / TM : 0,
    density: t.density, pop: t.m?.population ?? null, doo: t.m?.doo_places ?? null, own: CHECK.last?.own ?? null, sig: svSig(c.sk),
    sk: c.sk.map(b => ({ g: svRound(b.f.geometry), floors: b.floors, ...(b.kind ? { kind: b.kind } : {}), ...(b.grp ? { grp: b.grp } : {}) })) };
  ((RESULT.tepNode.properties ||= {}).saved ||= []).push(rec);
  SV.ask = ""; edited(); notice.value = `Вариант «${name}» сохранён вместе с показателями. Он в окне «Варианты», группа «Сохранённые»`;
}
/* «Открыть»: вариант становится текущим эскизом — один слой «Вариант: …» на все открытия, показатели — по нынешним нормативам */
function svOpen(id) {
  const r = savedList().find(x => x.id === id); if (!r) return;
  const sk = r.sk.map(b => { const f = turf.feature(b.g, {}); return { f, m2: m2(f), floors: b.floors, kind: b.kind, grp: b.grp }; });
  const P = RESULT.tepNode.properties, vk = P.svLayer, old = P.baked, ol = old && old !== vk && lyr(old);
  if (ol) project.layers.filter(l => l === ol || (l.group && l.group === ol.group)).forEach(l => { l.visible = false; });      // принятый эскиз остаётся в проекте, но не рисуется поверх
  if (vk && project.data[vk] && lyr(vk)) {
    const fc = turf.featureCollection(sk.map((b, i) => turf.feature(b.f.geometry, { "№": i + 1, "Типология": r.typ, "Корпус": b.kind || "", "Этажность": b.floors, "Площадь застройки, м²": Math.round(b.m2), "СПП, м²": Math.round(b.m2 * b.floors), ...(b.grp ? { "Блок": b.grp } : {}) })));
    const d = project.data[vk]; project.data[vk] = { ...d, title: "Вариант: " + r.name, source: "сохранённый вариант, открыт " + new Date().toLocaleDateString("ru-RU"), fc };
    const l = lyr(vk); l.title = "Вариант: " + r.name; l.visible = true; P.baked = vk; currentId.value = vk; touchData();
    notice.value = `Вариант «${r.name}» открыт: ${sk.length} корпусов`;
  } else { bakeSketch(sk, r.typ, "Вариант: " + r.name); P.svLayer = P.baked; }
  edited();
}
const armed = (id, act) => SV.arm && SV.arm.id === id && SV.arm.act === act && Date.now() - SV.arm.t < 4000;
export const svArmed = (id, act) => armed(id, act);
/* «Открыть» при несохранённом текущем и «Удалить» — со второго щелчка, как в меню слоёв */
export function svClick(id, act) {
  const r = savedList().find(x => x.id === id); if (!r) return;
  const c = svCurrent(), dirty = act === "open" && c.sk.length && !savedList().some(x => x.sig === svSig(c.sk)), need = act === "del" || dirty;
  if (need && !armed(id, act)) { SV.arm = { id, act, t: Date.now() }; setTimeout(() => { if (SV.arm && Date.now() - SV.arm.t >= 3900) SV.arm = null; }, 4000);
    notice.value = act === "del" ? `Удалить вариант «${r.name}»? Нажмите «Удалить» ещё раз` : "Текущий эскиз не сохранён как вариант и будет заменён. Нажмите «Открыть» ещё раз, чтобы продолжить"; return; }
  SV.arm = null;
  if (act === "del") { const L = RESULT.tepNode.properties.saved; L.splice(L.findIndex(x => x.id === id), 1); if (SV.cmp === id) SV.cmp = ""; edited(); notice.value = `Вариант «${r.name}» удалён`; }
  else svOpen(id);
}
export function svRename(id, name) {
  const r = savedList().find(x => x.id === id); name = (name || "").trim(); SV.ren = null;
  if (r && name && name !== r.name) { if (savedList().some(x => x.name === name)) notice.value = `Вариант «${name}» уже есть: имя не изменено`; else { r.name = name; edited(); } }
}
