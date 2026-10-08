/* ГРАДО 2 · общее состояние нового интерфейса: слои, выбранный слой, тема, масштаб карты.
   Одно место вместо общих переменных старой страницы; читают App.vue и панели в src/panels. */
import { ref, reactive, computed } from "vue";

/* Образец: набор слоёв типового проекта. В настоящем переходе слои придут из проекта (project.js). */
export const layers = reactive([
  { id: "boundary", title: "Граница территории", group: "Территория", color: "#c0392b", kind: "line", visible: true },
  { id: "lgr", title: "Красные линии (ЛГР)", group: "Ограничения", color: "#e03131", kind: "line", visible: true },
  { id: "zouit", title: "ЗОУИТ", group: "Ограничения", color: "#7048e8", kind: "fill", visible: true },
  { id: "egrn", title: "Участки ЕГРН", group: "Существующее положение", color: "#868e96", kind: "line", visible: true },
  { id: "bld", title: "Здания существующие", group: "Существующее положение", color: "#adb5bd", kind: "fill", visible: true },
  { id: "sketch", title: "Эскиз застройки", group: "Эскиз", color: "#f08c00", kind: "fill", visible: false },
]);

export const currentId = ref("boundary");
export const current = computed(() => layers.find(l => l.id === currentId.value));
export const scale = ref(0);

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
