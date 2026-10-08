/* ГРАДО 2 · общее состояние нового интерфейса: проект (группы и слои), текущий слой, тема, масштаб карты.
   Одно место вместо общих переменных старой страницы; заполняет project.js, читают App.vue и панели в src/panels. */
import { ref, reactive, computed, markRaw } from "vue";

/* Проект в том виде, как его хранит файл .grado2: группы и слои сверху вниз, данные слоёв отдельно.
   data не реактивна (markRaw): тысячи объектов GeoJSON рисует карта, Vue за ними не следит. */
export const project = reactive({ name: "", source: "", groups: [], layers: [], data: markRaw({}), view: null, album: null });
export const currentId = ref("");
export const current = computed(() => project.layers.find(l => l.key === currentId.value));
export const scale = ref(0);

const HEX = /^#[0-9a-f]{3,8}$/i;
const num = (v, d) => { const n = Number(v); return v !== null && v !== "" && Number.isFinite(n) ? n : d; };

/* Стиль слоя с теми же значениями по умолчанию, что у рабочей страницы (web/layers.js cleanStyle). */
export function styleOf(l) {
  const st = l.style || {};
  return {
    mode: st.mode || "single",
    fill: HEX.test(st.fill) ? st.fill : "#9aa1a8",
    stroke: HEX.test(st.stroke) ? st.stroke : "#5f6368",
    width: num(st.width, 1),
    opacity: num(st.opacity, 0.7),
  };
}

/* Цвет образца в списке слоёв: у линии цвет — fill (так рисует рабочая страница), у полигона — заливка и контур. */
export function swatchOf(l) {
  const s = styleOf(l);
  return l.geom === "line" ? { kind: "line", c: s.fill } : l.geom === "point" ? { kind: "point", c: s.fill, e: s.stroke } : { kind: "poly", c: s.fill, e: s.stroke };
}

/* Слой виден на карте, когда включён он сам и его группа. */
export function shown(l) {
  const g = l.group && project.groups.find(x => x.id === l.group);
  return l.visible !== false && (!g || g.visible !== false);
}

export function setProject(p, name, source) {
  project.name = name || p.name || "";
  project.source = source;
  project.groups = (p.groups || []).map(g => ({ id: g.id, title: g.title || g.id, visible: g.visible !== false, open: g.open !== false }));
  project.layers = (p.layers || []).filter(l => l && l.key).map(l => ({ ...l, visible: l.visible !== false }));
  project.data = markRaw(p.data || {});
  project.view = p.view || null;
  project.album = p.album ? { meta: { ...(p.album.meta || {}) }, sheets: p.album.sheets || [] } : null;   // штамп в «Макете листа»
  currentId.value = project.layers.some(l => l.key === p.current) ? p.current : (project.layers[0]?.key || "");
}

const saved = (() => { try { return localStorage.getItem("grado-next-theme"); } catch { return null; } })();
export const theme = ref(saved || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));

export function applyTheme(t) {
  const html = document.documentElement;
  html.classList.toggle("wa-dark", t === "dark");
  html.classList.toggle("wa-light", t !== "dark");
  html.dataset.theme = t;
  try { localStorage.setItem("grado-next-theme", t); } catch { /* частный режим браузера */ }
}

export function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
  applyTheme(theme.value);
}
