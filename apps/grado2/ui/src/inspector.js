/* ГРАДО 2 · состояние единого инспектора: вкладка и раскрытые разделы только в настройках браузера.
   Карта, таблица и дерево открывают один inspector через прежние команды props/object; проект не меняется. */
import { reactive, watch } from "vue";
import { winApi } from "./store.js";

const KEY = "grado-next-inspector";
const defaults = { appearance: true, labels: true, visibility: false, data: false };
let saved = {};
try { saved = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch { /* частный режим или старая запись */ }
export const inspector = reactive({
  tab: saved.tab === "object" ? "object" : "layer",
  sections: Object.fromEntries(Object.entries(defaults).map(([k, v]) => [k, typeof saved.sections?.[k] === "boolean" ? saved.sections[k] : v])),
});
watch(inspector, () => { try { localStorage.setItem(KEY, JSON.stringify(inspector)); } catch { /* частный режим */ } });

export function showInspector(tab) {
  inspector.tab = tab === "object" ? "object" : "layer";
  winApi.open(tab === "object" ? "object" : "props");
}
