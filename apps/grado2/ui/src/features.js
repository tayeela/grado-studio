/* ГРАДО 2 · объекты слоёв в новом интерфейсе: выбор (щелчок, Shift, рамка, таблица), площадь и длина в МСК,
   правка атрибутов, новое поле, удаление объектов. Объект узнаётся по `_uid` (как web/layers.js и совместная работа).
   Правка данных кладёт в слой новый объект fc с новыми объектами только у изменённых записей: отмена (edit.js)
   держит прежний fc ссылкой, карта (MapPanel) обновляет только изменённые объекты. Площадь — в МСК, как в чертеже
   и в выгрузке (web/msk.js, тот же расчёт, что у рабочей страницы). */
import { reactive } from "vue";
import * as mskModule from "../../web/msk.js";
import { project } from "./store.js";
import { touchData } from "./edit.js";

export const sel = reactive([]);       // [{key, uid}] — выбранные объекты, в порядке выбора

const newUid = () => Array.from(crypto.getRandomValues(new Uint8Array(6)), b => b.toString(16).padStart(2, "0")).join("");
export const hiddenField = k => k.startsWith("_") || k === "gradosym" || k === "geometry";

/* Номер `_uid` у каждого объекта слоя (повтор — новый номер), индекс uid → номер объекта; один раз на объект fc. */
const IDX = new WeakMap();
export function indexOf(fc) {
  if (!fc) return new Map();
  let m = IDX.get(fc); if (m) return m;
  m = new Map();
  (fc.features || []).forEach((f, i) => {
    const p = f.properties ||= {};
    if (!p._uid || m.has(p._uid)) p._uid = newUid();
    m.set(p._uid, i);
  });
  IDX.set(fc, m); return m;
}
export function featureOf(key, uid) {
  const fc = project.data[key]?.fc, i = indexOf(fc).get(uid);
  return i === undefined ? null : fc.features[i];
}
export const selected = () => sel.map(s => ({ ...s, f: featureOf(s.key, s.uid) })).filter(s => s.f);

export function setSel(list) {
  const seen = new Set();
  sel.splice(0, sel.length, ...list.filter(s => s.uid && !seen.has(s.key + "|" + s.uid) && seen.add(s.key + "|" + s.uid)));
}
export function toggleSel(s) {
  const i = sel.findIndex(x => x.key === s.key && x.uid === s.uid);
  if (i >= 0) sel.splice(i, 1); else sel.push(s);
}
export function selectAll(key) {
  const fc = project.data[key]?.fc; indexOf(fc);
  setSel((fc?.features || []).map(f => ({ key, uid: f.properties._uid })));
}

/* ---------- размеры в МСК ---------- */
/* web/msk.js — общий файл с рабочей страницей: в сборке Vite он модуль CommonJS (module.exports), в странице — глобальный MSK */
const MSK = globalThis.MSK || mskModule.default || mskModule;
const toM = c => MSK.fromWgs(c);
const ringArea = r => { const m = r.map(toM); let a = 0; for (let i = 0; i + 1 < m.length; i++) a += m[i][0] * m[i + 1][1] - m[i + 1][0] * m[i][1]; return Math.abs(a / 2); };
const lineLen = r => { const m = r.map(toM); let d = 0; for (let i = 0; i + 1 < m.length; i++) d += Math.hypot(m[i + 1][0] - m[i][0], m[i + 1][1] - m[i][1]); return d; };
/* ["area", м²] | ["len", м] | ["pt", 0] */
export function sizeOf(f) {
  const g = f?.geometry, t = g?.type || "", c = g?.coordinates;
  if (t === "Polygon") return ["area", c.reduce((a, r, i) => a + (i ? -ringArea(r) : ringArea(r)), 0)];
  if (t === "MultiPolygon") return ["area", c.reduce((a, p) => a + p.reduce((b, r, i) => b + (i ? -ringArea(r) : ringArea(r)), 0), 0)];
  if (t === "LineString") return ["len", lineLen(c)];
  if (t === "MultiLineString") return ["len", c.reduce((a, r) => a + lineLen(r), 0)];
  return ["pt", 0];
}
export const fieldsOfFeatures = fs => [...new Set(fs.flatMap(f => Object.keys(f.properties || {})))].filter(k => !hiddenField(k))
  .sort((a, b) => /[а-яё]/i.test(b) - /[а-яё]/i.test(a));

/* Число — числом, «012» и пустое — текстом (web/layers.js numOrText). */
export const numOrText = v => typeof v === "string" && v.trim() !== "" && !isNaN(+v) && !/^0\d/.test(v) ? +v : v;

/* ---------- правка данных ---------- */
/* Исходная выгрузка при первой правке: «=fc» в файле — данные ещё не правились, исходная = нынешние.
   У своего слоя (нарисованного) исходной выгрузки нет и не появляется. */
const keepOriginal = d => typeof d.original === "object" && d.original ? { original: d.original } : d.original === "=fc" ? { original: d.fc } : {};

/* Новый fc слоя: fn(properties) у объектов с uid из списка; исходная выгрузка сохраняется при первой правке. */
export function editFeatures(key, uids, fn) {
  const d = project.data[key]; if (!d?.fc) return;
  const want = new Set(uids), fc = d.fc;
  const features = fc.features.map(f => {
    if (!want.has(f.properties?._uid)) return f;
    const p = { ...f.properties }; fn(p); p._edited = true;
    return { ...f, properties: p };
  });
  project.data[key] = { ...d, fc: { ...fc, features }, ...keepOriginal(d) };
  touchData();
}

export function setAttr(items, field, value) {
  const by = new Map(); items.forEach(s => (by.get(s.key) || by.set(s.key, []).get(s.key)).push(s.uid));
  by.forEach((uids, key) => editFeatures(key, uids, p => { p[field] = numOrText(value); }));
}

export function addField(items, name) { setAttr(items.filter(s => !(name in (featureOf(s.key, s.uid)?.properties || {}))), name, ""); }

export function deleteFeatures(items) {
  const by = new Map(); items.forEach(s => (by.get(s.key) || by.set(s.key, new Set()).get(s.key)).add(s.uid));
  by.forEach((uids, key) => {
    const d = project.data[key]; if (!d?.fc) return;
    project.data[key] = { ...d, fc: { ...d.fc, features: d.fc.features.filter(f => !uids.has(f.properties?._uid)) }, ...keepOriginal(d) };
  });
  setSel(sel.filter(s => !by.get(s.key)?.has(s.uid)));
  touchData();
}
