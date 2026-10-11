/* ГРАДО 2 · эскиз нового интерфейса (как web/app.js publishedControls, renderParams, bakeSketch, reserveState, takePzzTarget):
   параметры блоков схемы, вынесенные в окно «Эскиз», «Построить эскиз» / «Остановить», «Сохранить слоем» (корпуса,
   участки и улицы — слоями группы «Эскиз: …»), резерв участков ДОО, школы и поликлиники в свободной земле пятна
   и цель плотности по ПЗЗ. Правки идут в схему проекта (graph.js) — та же схема, что в рабочей странице. */
import * as turf from "@turf/turf";
import { project, currentId } from "./store.js";
import { touchData, newGroup } from "./edit.js";
import { notice } from "./project.js";
import { ensureLayer } from "./data.js";
import { fullStyle } from "./symbology.js";
import { fmt, safe } from "./geom.js";
import { FLOOR_MODES, LOWRISE, ROWS, TYPES, TYPOLOGIES } from "./graphfile.js";
import { RESULT, edited, graph, nodeById } from "./graph.js";
import { pzzTarget, reserveRadii, reserveSocial, tepParams } from "./tep.js";

export const wi = (n, name) => (TYPES[n.type]?.widgets || []).findIndex(w => w[1] === name);
export const wv = (n, name) => n.widgets_values?.[wi(n, name)];

export const TYP_HINT = { "Секции": "секции по 40–60 м рядами вдоль длинной стороны участка", "Квартал": "периметр каждого участка с проездом во двор, этажность 0,7 заданной",
  "Башни": "точечные дома сеткой, этажность ×1,6", "Точка + секция": "в рядах секций через одну — башня (×1,6)", "Смешанная": "секции по краям участка, башни внутри",
  "Урбан-блоки": "сетка кварталов с улицами 20 м, сплошной фронт, углы северной стороны выше, южная сторона ниже — солнце во дворе",
  "Блокированные": "ряды до 6 блоков по 7 м, у каждого блока участок; проезды 12 м; до 3 этажей", "ИЖС": "дом на своём участке, проезды 12 м между парами рядов; до 3 этажей" };

/* поля блоков схемы, вынесенные в окно: {id, name, label, type: seg|toggle|range, opts, min, max, step, hint};
   параметры, которые выбранная типология не использует, не показываются */
export function publishedControls() {
  const g = graph(), p = RESULT.placeNode, t = RESULT.tepNode; if (!g) return [];
  const numL = p && g.links.find(l => l && l[3] === p.id && l[4] === 1), num = numL && g.nodes.find(n => n.id === numL[1] && n.type === "Параметры/Число");
  const out = [], typ = p && wv(p, "типология"), C = (n, name, o = {}) => out.push({ id: n.id, name, label: o.label || name[0].toUpperCase() + name.slice(1), type: "range", ...o });
  if (p) C(p, "типология", { type: "seg", opts: TYPOLOGIES, hint: TYP_HINT[typ] || "" });
  if (p) C(p, "этажность по", { label: "Этажность по", type: "seg", opts: FLOOR_MODES, hint: "цели плотности — этажность подбирается под «Целевую плотность» блока ТЭП, не выше предельной высоты; «Этажность» ниже — наибольшая" });
  const low = LOWRISE.has(typ), fr = low ? { min: 1, max: 3 } : { min: 3, max: 30 };
  if (num) C(num, "значение", { label: "Этажность", ...fr, step: 1, hint: low ? "до 3 этажей" : "блок «Число» в схеме" }); else if (p) C(p, "этажность", { ...fr, step: 1 });
  if (p && typ === "ИЖС") C(p, "участок, соток", { label: "Участок, соток", min: 4, max: 20, step: 1, hint: "дом до 12 × 12 м: 5 м от проезда, не ближе 3 м к соседним участкам; проезды 12 м между парами рядов" });
  // короче двух корпусов и двора 20 м квартал не бывает — ползунок ниже не опускается
  if (p && typ === "Урбан-блоки") C(p, "квартал, м", { label: "Квартал по длинной стороне, м", min: Math.ceil((2 * Math.round(wv(p, "ширина корпуса, м")) + 20) / .8 / 5) * 5, max: 200, step: 5, hint: "квартал — длина × 0,8; между кварталами улицы 20 м; ставится только квартал, целиком помещающийся в пятно" });
  if (p && typ !== "ИЖС") C(p, "ширина корпуса, м", { label: typ === "Блокированные" ? "Глубина дома, м" : "Ширина корпуса, м", min: 12, max: 24, step: 1, hint: typ === "Блокированные" ? "берётся от 10 до 14 м; блок 7 м по фасаду, до 6 блоков в ряду, палисадник 5 м и сад 12 м" : "" });
  if (p && !low && typ !== "Урбан-блоки") C(p, "разрыв / высота", { min: .5, max: 2, step: .05, hint: "разрыв между длинными сторонами = коэф. × высота, но не меньше 15 м (2–3 эт.) и 20 м (4 эт. и выше), СП 42.13330 п. 7.1" });
  if (p && typ === "Урбан-блоки") C(p, "понижать этажность ради инсоляции", { label: "Понижать этажность ради инсоляции соседей", type: "toggle", hint: "Программа проверяет, получают ли окна солнце, и понижает этажность секций, которые затеняют соседей. Это улучшает инсоляцию, но уменьшает площадь застройки и делает расчёт дольше. Выключено — этажность не меняется; предупреждения «Проверки норм» по инсоляции остаются." });
  if (p && (typ === "Секции" || typ === "Точка + секция")) C(p, "ряды", { label: "Ряды", type: "seg", opts: ROWS, hint: "прямые — полосами вдоль длинной стороны участка; по границе — кольцами от границы внутрь, ряд ломается вслед за ней (поворот не действует)" });
  if (p && !(wv(p, "ряды") === "по границе" && (typ === "Секции" || typ === "Точка + секция"))) C(p, "поворот, °", { label: "Поворот относительно длинной стороны участка, °", min: -90, max: 90, step: 1, hint: "0 — ряды (кварталы) вдоль длинной стороны каждого участка, 90 — поперёк" });
  g.nodes.filter(n => n.type === "Геометрия/Буфер").forEach(n => C(n, "расстояние, м", { label: (n.title || "Буфер") + ", м", min: 0, max: 40, step: 1 }));
  if (t) { C(t, "доля жилья, %", { min: 0, max: 100, step: 5 }); C(t, "цель, тыс. м²/га", { label: "Целевая плотность, тыс. м²/га", min: 5, max: 45, step: 1 }); }
  return out;
}
export function setControl(c, v) {
  const n = nodeById(c.id), i = n && wi(n, c.name); if (!n || i < 0 || n.widgets_values[i] === v) return;
  n.widgets_values[i] = v;
  // переход между малоэтажной и многоэтажной типологией — этажность по умолчанию для неё (2 и 12), а не 12 этажей ИЖС
  if (c.name === "типология") { const fc = publishedControls().find(x => x.name === "значение" || x.name === "этажность"), fn = fc && nodeById(fc.id), fi = fn && wi(fn, fc.name);
    if (fn && LOWRISE.has(v) && fn.widgets_values[fi] > 3) fn.widgets_values[fi] = 2; else if (fn && !LOWRISE.has(v) && fn.widgets_values[fi] <= 3) fn.widgets_values[fi] = 12; }
  edited();
}

/* «Построить эскиз» / «Остановить»: новый эскиз — показатели снова по схеме, а не по сохранённому слою */
export function setRun(on) {
  const pn = RESULT.placeNode; if (!pn) return;
  if (on && !project.territory) { notice.value = "Эскиз строится внутри границы территории, а её нет. Задайте границу в окне «Данные»"; return; }
  if (on && !RESULT.site) { notice.value = "Пятно застройки пусто: вся территория занята запретами или сохраняемыми зданиями. Проверьте окно «Ограничения»"; return; }
  (pn.properties ||= {}).run = !!on;
  const tn = RESULT.tepNode; if (on && tn?.properties?.baked) { tn.properties.baked = null; delete tn.properties.reserveBaked; }
  edited();
}

/* ---------- резерв участков (T6): кэш по пятну, эскизу, ответу сервера и радиусам ---------- */
const OID = new WeakMap(); let oidN = 0;
const gid = o => { if (!o || typeof o !== "object") return "-"; let v = OID.get(o); if (!v) OID.set(o, v = ++oidN); return v; };
const EMPTY = () => ({ plots: [], notes: [], warns: [] });
let resKey = "", resVal = EMPTY();
export function reserveState() {
  const t = RESULT.tep, social = t?.social || [], tn = RESULT.tepNode;
  if (!RESULT.site || !RESULT.sketch?.length || !social.length || !tn) { resKey = ""; return resVal = EMPTY(); }
  if (!tn.properties?.baked && Math.abs((t.sppNew || 0) - RESULT.sketch.reduce((q, b) => q + b.m2 * b.floors, 0)) >= 1) return EMPTY();   // ответ сервера от прежнего эскиза: не считаем
  const radii = reserveRadii(tepParams(tn)), key = gid(RESULT.site) + ":" + gid(RESULT.sketch) + JSON.stringify(social) + JSON.stringify(radii);
  if (key !== resKey) { resKey = key; resVal = safe(() => reserveSocial(RESULT.site, RESULT.sketch, social, radii)) || EMPTY(); }
  return resVal;
}
const reserveSaved = () => { const k = RESULT.tepNode?.properties?.reserveBaked; return !!(k && project.data[k]); };
export const reserveShown = () => reserveSaved() ? [] : reserveState().plots;     // участки уже в сохранённом слое — превью не рисуем второй раз

/* ---------- «Сохранить слоем» (Bake в Grasshopper): снимок эскиза — обычные слои, схема на них больше не влияет ---------- */
let seq = 0;
const newKey = () => "user:" + Date.now().toString(36) + (seq++).toString(36);
function addLayer(title, fc, style) {
  const key = newKey(), day = new Date();
  project.data[key] = { title, source: "эскиз из схемы расчёта, сохранён " + day.toLocaleDateString("ru-RU"), fetched_at: day.toISOString().slice(0, 10), fc };
  const l = ensureLayer(key, title); l.style = fullStyle(style); return key;
}
/* skIn — сохранённый вариант (T59): корпуса без участков и улиц схемы, typIn и titleIn — его типология и название слоя */
export function bakeSketch(skIn, typIn, titleIn) {
  const own = Array.isArray(skIn), sk = own ? skIn : RESULT.sketch || []; if (!sk.length) { notice.value = "Эскиз пуст: сначала «Построить эскиз»"; return null; }
  const typ = (own && typIn) || wv(RESULT.placeNode, "типология") || "", t = typ.toLowerCase(), fl = [...new Set(sk.map(b => b.floors))];
  const resP = own ? [] : reserveState().plots, plots = [...(sk.plots || []), ...resP], keys = [];
  // новые слои встают наверх: сначала улицы, затем участки, корпуса — сверху
  if (sk.streets?.length) keys.unshift(addLayer(`Эскиз: улицы и проезды (${t})`, turf.featureCollection(sk.streets.map((g, i) => turf.feature(g.f.geometry, { "№": i + 1, "Вид": g.kind, "Площадь, м²": Math.round(g.m2),
    ...(g["Мест"] ? { "Мест": g["Мест"], "Норма": g.kind === "стоянка" ? "945-ПП прил. 5: 0,8 места на квартиру и 10 % гостевых" : "945-ПП п. 6.2.3.2: 10 % от 1,6 места на дом" } : {}) }))),
    { mode: "cat", fill: "#e4e1da", stroke: "#b7b2a8", width: .8, opacity: .9, cat: { field: "Вид", colors: { "проезд": "#e4e1da", "улица": "#e4e1da", "гостевая стоянка": "#9fb6d9", "стоянка": "#c3ccd8" }, off: [] } }));
  let plotKey = null;
  if (plots.length) keys.unshift(plotKey = addLayer(`Эскиз: участки и дворы (${t})`, turf.featureCollection(plots.map((g, i) => turf.feature(g.f.geometry, { "№": i + 1, "Вид": g.kind, "Площадь, м²": Math.round(g.m2),
    ...(g["Участок"] ? { "Участок": g["Участок"], "Места": g["Места"], "Дефицит": g["Дефицит"] } : {}), ...(g["Площадь, сот."] ? { "Площадь, сот.": g["Площадь, сот."] } : {}),
    ...(g["Блок"] ? { "Блок": g["Блок"] } : {}), ...(g["Причина"] ? { "Причина": g["Причина"] } : {}) }))),
    { mode: "cat", width: .8, stroke: "#7a9a5a", opacity: .6, cat: { field: "Вид", colors: { "участок ИЖС": "#dfeccd", "участок блока": "#dfeccd", "двор": "#f3eac6", "свет соседям": "#fbe39a", "хозпостройка": "#d9cdb8", "участок ДОО": "#f6dccb", "участок школы": "#dcd3ec", "участок поликлиники": "#cfe8e3" }, off: [] } }));
  const title = (own && titleIn) || `Эскиз: ${t}, ${fl.join("/")} эт.`;
  const key = addLayer(title, turf.featureCollection(sk.map((b, i) => turf.feature(b.f.geometry, { "№": i + 1, "Типология": typ, "Корпус": b.kind || "", "Этажность": b.floors, "Площадь застройки, м²": Math.round(b.m2), "СПП, м²": Math.round(b.m2 * b.floors),
    ...(b.grp ? { "Блок": b.grp } : {}), ...(b["Блоков"] ? { "Блоков": b["Блоков"] } : {}), ...(b["1 этаж"] ? { "1 этаж": b["1 этаж"] } : {}) }))),
    { mode: fl.length > 1 ? "grad" : "single", fill: "#6fa6e6", stroke: "#1a4f94", width: .8, opacity: .9, label: "Этажность", grad: { field: "Этажность", n: 4, ramp: "blue", method: "equal" } });   // разная этажность — диапазоны, одна — единый цвет
  keys.unshift(key);
  if (keys.length > 1) newGroup(keys, `Эскиз: ${t}`);
  const tn = RESULT.tepNode;
  if (tn) { tn.properties ||= {}; tn.properties.baked = key; if (resP.length && plotKey) tn.properties.reserveBaked = plotKey; else delete tn.properties.reserveBaked; }   // «Показатели» — по принятому слою
  currentId.value = key; touchData(); edited();
  notice.value = `Эскиз сохранён слоем «${title}»: ${sk.length} корпусов${sk.plots?.length ? `, участков, дворов и хозпостроек ${sk.plots.length}` : ""}${sk.streets?.length ? `, улиц, проездов и стоянок ${sk.streets.length}` : ""}. Слои можно править, стилизовать и выгружать; схема на них больше не влияет`;
  return key;
}

/* цель плотности по ПЗЗ — в ползунок «цель» блока ТЭП (пределы 5–45) */
export function takePzzTarget(silent) {
  const t = RESULT.tepNode, pz = pzzTarget(); if (!t || pz?.value == null) return false;
  const v = Math.max(5, Math.min(45, Math.round(pz.value))); t.widgets_values[wi(t, "цель, тыс. м²/га")] = v; (t.properties ||= {}).pzzTarget = true;
  if (!silent) notice.value = `Цель плотности взята по ПЗЗ: ${fmt(pz.value, 1)} тыс. м²/га${v !== Math.round(pz.value) ? ` (ползунок держит ${v}: пределы 5–45)` : ""}; подзоны с числом покрывают ${Math.round(pz.share * 100)} % границы`;
  edited(); return true;
}
