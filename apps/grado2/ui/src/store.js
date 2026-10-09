/* ГРАДО 2 · общее состояние нового интерфейса: проект (группы и слои), текущий слой, тема, масштаб и вид карты.
   Одно место вместо общих переменных старой страницы; заполняет project.js, читают App.vue и панели в src/panels.
   Весь файл проекта как есть лежит в project.raw: при записи меняются только поля, которые правит новый интерфейс,
   остальное (граф, альбом, граница, источники) уходит в файл без изменений. */
import { ref, reactive, computed, markRaw } from "vue";
import { fullStyle, swatchColor } from "./symbology.js";

/* Проект в том виде, как его хранит файл .grado2: группы и слои сверху вниз, данные слоёв отдельно.
   data не реактивна (markRaw): тысячи объектов GeoJSON рисует карта, Vue за ними не следит. */
export const project = reactive({ name: "", file: null, source: "", groups: [], layers: [], views: [], data: markRaw({}), territory: null, view: null, raw: markRaw({}) });
export const winApi = { open: () => {} };   // App.vue подставляет: открыть окно по id или вывести его вперёд
export const viewCur = ref(null);      // вид карты, показанный последним (окно «Виды»)
export const currentId = ref("");
export const current = computed(() => project.layers.find(l => l.key === currentId.value));
export const scale = ref(0);
export const cursor = ref(null);       // курсор над картой в МСК [восток, север], м (MapPanel); строка состояния
export const viewNow = { center: null, zoom: null };   // вид карты сейчас (MapPanel): долгота и широта, уровень; уходит в файл при записи

/* Образец слоя в списке: у линии и точки — цвет знака, у полигона — заливка и контур (штриховка — косой полосой). */
export function swatchOf(l) {
  const st = l.style, c = swatchColor(st);
  return l.geom === "line" ? { kind: "line", c } : l.geom === "point" ? { kind: "point", c, e: st.stroke } : { kind: st.hatch ? "poly hatch" : "poly", c, e: st.hatch ? c : st.stroke };
}

/* Слой виден на карте, когда включён он сам и его группа. */
export function shown(l) {
  const g = l.group && project.groups.find(x => x.id === l.group);
  return l.visible !== false && (!g || g.visible !== false);
}

export function setProject(p, name, source) {
  project.raw = markRaw(p);
  project.name = name || p.name || "";
  project.file = p.file !== undefined ? p.file : (p.name || null);
  project.source = source;
  project.groups = (p.groups || []).map(g => ({ id: g.id, title: g.title || g.id, visible: g.visible !== false, open: g.open !== false }));
  project.layers = (p.layers || []).filter(l => l && l.key).map(l => ({ ...l, visible: l.visible !== false, style: fullStyle(l.style) }));   // стиль со всеми полями, как web/layers.js ST
  project.data = markRaw(p.data || {});
  project.territory = p.territory?.geometry ? markRaw(p.territory) : null;   // граница территории: GeoJSON Feature, как в файле
  project.views = (p.views || []).filter(v => v && v.id).map(v => JSON.parse(JSON.stringify(v)));
  viewCur.value = null;
  project.view = p.view || null;
  viewNow.center = viewNow.zoom = null;   // пока карта не поставила вид нового проекта, в файл идёт его прежний вид
  if (BASEMAPS[p.view?.basemap]) setBasemap(p.view.basemap);
  currentId.value = project.layers.some(l => l.key === p.current) ? p.current : (project.layers[0]?.key || "");
}

/* Подложка карты, как у рабочей страницы (web/app.js BASEMAPS): выбор помнит браузер (тот же ключ «grado2.base»)
   и файл проекта (view.basemap). Слои подложки создаёт MapPanel. */
export const BASEMAPS = { osm: "Схема OSM", esri: "Спутник (Esri)", s2: "Sentinel-2 (EOX)" };
const savedBase = (() => { try { return localStorage.getItem("grado2.base"); } catch { return null; } })();
export const basemapId = ref(BASEMAPS[savedBase] ? savedBase : "osm");
export function setBasemap(id) {
  if (!BASEMAPS[id]) return;
  basemapId.value = id;
  try { localStorage.setItem("grado2.base", id); } catch { /* частный режим браузера */ }
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
