/* ГРАДО 2 · правка проекта в новом интерфейсе: слои и группы (создать, удалить, переместить, сгруппировать,
   вернуть исходную выгрузку, копировать стиль) и одна общая отмена (Ctrl+Z / Ctrl+Shift+Z) на все правки слоёв,
   групп, оформления и данных. Отмена хранит снимки: описания слоёв копией, данные слоёв — ссылкой на объект
   (правка данных всегда кладёт новый объект, как web/layers.js), поэтому снимок дешёвый и на больших слоях.
   Правила как у рабочей страницы (web/layers.js normGroups, moveLayer, createLayer, removeLayers). */
import { reactive, ref, toRaw, watch } from "vue";
import { currentId, project } from "./store.js";
import { fullStyle } from "./symbology.js";

export const dataRev = ref(0);         // данные слоя заменены (новый слой, удаление, возврат, правка объектов): карта перечитывает
export const history = reactive({ undo: 0, redo: 0, label: "" });
export const mapApi = { zoomTo: () => {} };   // MapPanel подставляет: приблизить к слоям по ключам

export const grp = id => project.groups.find(g => g.id === id);
export const lyr = key => project.layers.find(l => l.key === key);
export function touchData() { dataRev.value++; }

/* Слои одной группы идут подряд на месте первого из них; пустые группы исчезают. */
export function normGroups() {
  const L = project.layers, seen = new Set(), out = [];
  L.forEach(l => {
    if (l.group && !grp(l.group)) l.group = null;
    if (!l.group) return out.push(l);
    if (seen.has(l.group)) return;
    seen.add(l.group); out.push(...L.filter(x => x.group === l.group));
  });
  project.layers.splice(0, L.length, ...out);
  for (let i = project.groups.length - 1; i >= 0; i--) if (!seen.has(project.groups[i].id)) project.groups.splice(i, 1);
}

/* ---------- слои ---------- */
export function newLayer(name, geom) {
  const key = "user:" + Date.now().toString(36);
  project.data[key] = { title: name, source: "создан в проекте", fetched_at: new Date().toISOString().slice(0, 10), fc: { type: "FeatureCollection", features: [] } };
  project.layers.unshift({ key, title: name, geom, visible: true, layerOpacity: 1, open: false, group: null, style: fullStyle() });   // свои слои — наверх
  currentId.value = key; touchData();
  return key;
}

export function removeLayers(keys) {
  const set = new Set(keys);
  project.layers.splice(0, project.layers.length, ...project.layers.filter(l => !set.has(l.key)));
  keys.forEach(k => delete project.data[k]);
  if (set.has(currentId.value)) currentId.value = project.layers[0]?.key || "";
  normGroups(); touchData();
}

export function renameLayer(key, title) {
  const l = lyr(key); if (!l || !title.trim()) return;
  l.title = title.trim(); if (project.data[key]) project.data[key].title = l.title;
}

/* «Выше/Ниже» — внутри своей группы или среди слоёв без группы. */
export function moveLayer(key, d) {
  const L = project.layers, l = lyr(key), peers = L.filter(x => x.group === l.group), i = peers.indexOf(l), j = i + d;
  if (j < 0 || j >= peers.length) return;
  const a = L.indexOf(l), b = L.indexOf(peers[j]);
  [L[a], L[b]] = [L[b], L[a]]; normGroups();
}

export function setGroup(key, gid) {
  const L = project.layers, l = lyr(key); if (!l) return;
  l.group = gid || null;
  if (gid) { L.splice(L.indexOf(l), 1); const at = L.findIndex(x => x.group === gid); L.splice(at < 0 ? 0 : at, 0, l); }
  normGroups();
}

/* Полный порядок после перетаскивания: [{key, group}] сверху вниз. */
export function reorder(list) {
  const byKey = Object.fromEntries(project.layers.map(l => [l.key, l]));
  const out = list.map(({ key, group }) => { const l = byKey[key]; if (l) l.group = group || null; return l; }).filter(Boolean);
  project.layers.forEach(l => { if (!out.includes(l)) out.push(l); });
  project.layers.splice(0, project.layers.length, ...out); normGroups();
}

/* Исходная выгрузка: в файле «=fc» значит, что данные не правились. */
export const canRevert = key => { const d = project.data[key]; return !!d && !!d.original && typeof d.original === "object" && d.original !== d.fc; };
export function revertLayer(key) {
  const d = project.data[key]; if (!canRevert(key)) return;
  project.data[key] = { ...d, fc: d.original, original: d.original }; touchData();
}

let clip = null;                       // буфер стиля, как «Копировать / Вставить стиль» в QGIS
export const styleClip = ref("");
export function copyStyle(key) { const l = lyr(key); clip = { style: JSON.parse(JSON.stringify(toRaw(l.style))), geom: l.geom }; styleClip.value = l.title; }
export function pasteStyle(key) { const l = lyr(key); if (!clip || !l) return false; l.style = fullStyle(JSON.parse(JSON.stringify(clip.style))); return clip.geom === l.geom; }

/* ---------- группы ---------- */
export function newGroup(keys, title) {
  const id = "g" + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
  project.groups.push({ id, title: title || `Группа ${project.groups.length + 1}`, visible: true, open: true });
  keys.map(lyr).filter(Boolean).forEach(l => { l.group = id; });
  normGroups(); return id;
}
export function ungroup(id) { project.layers.forEach(l => { if (l.group === id) l.group = null; }); normGroups(); }
export function removeGroup(id) { removeLayers(project.layers.filter(l => l.group === id).map(l => l.key)); }
export const groupKeys = id => project.layers.filter(l => l.group === id).map(l => l.key);

/* ---------- отмена ---------- */
const UNDO = [], REDO = [];
let last = null, timer = null, applying = false;
/* схема расчёта лежит в project.raw.graph (вид litegraph, graph.js правит её на месте): в отмену — её текст */
export const graphRev = ref(0);         // правка схемы расчёта (узлы, связи, поля узлов)
export const graphHooks = { restored: () => {} };   // graph.js: схема вернулась отменой
const snap = () => ({
  layers: JSON.stringify(project.layers), groups: JSON.stringify(project.groups), views: JSON.stringify(project.views),
  data: { ...project.data }, current: currentId.value, territory: project.territory, graph: JSON.stringify(project.raw?.graph ?? null),
});
const same = (a, b) => a.layers === b.layers && a.groups === b.groups && a.views === b.views && a.territory === b.territory && a.graph === b.graph
  && Object.keys(a.data).length === Object.keys(b.data).length && Object.keys(a.data).every(k => a.data[k] === b.data[k]);
function sync() { history.undo = UNDO.length; history.redo = REDO.length; }

/* Правки, идущие подряд без паузы (ползунок, набор числа), — одна запись отмены. */
function commit() {
  clearTimeout(timer); timer = null;
  if (applying || !last) return;
  const now = snap(); if (same(now, last)) return;
  UNDO.push(last); if (UNDO.length > 80) UNDO.shift();
  REDO.length = 0; last = now; sync();
}
watch([() => project.layers, () => project.groups, () => project.views, () => project.territory, dataRev, graphRev], () => {
  if (applying) return;
  clearTimeout(timer); timer = setTimeout(commit, 400);
}, { deep: true });

export function resetHistory() { clearTimeout(timer); UNDO.length = 0; REDO.length = 0; last = snap(); sync(); }

function apply(s) {
  applying = true;
  project.layers.splice(0, project.layers.length, ...JSON.parse(s.layers));
  project.groups.splice(0, project.groups.length, ...JSON.parse(s.groups));
  project.views.splice(0, project.views.length, ...JSON.parse(s.views));
  for (const k of Object.keys(project.data)) if (!(k in s.data)) delete project.data[k];
  Object.assign(project.data, s.data);
  project.territory = s.territory;
  if (project.raw && s.graph !== JSON.stringify(project.raw.graph ?? null)) { project.raw.graph = JSON.parse(s.graph); graphHooks.restored(); }
  if (project.layers.some(l => l.key === s.current)) currentId.value = s.current;
  touchData();
  setTimeout(() => { applying = false; last = snap(); }, 0);   // наблюдатели отработали на возврате — это не новая правка
}
export function undo() { if (timer) commit(); if (!UNDO.length) return false; REDO.push(snap()); apply(UNDO.pop()); sync(); return true; }
export function redo() { if (timer) commit(); if (!REDO.length) return false; UNDO.push(snap()); apply(REDO.pop()); sync(); return true; }
