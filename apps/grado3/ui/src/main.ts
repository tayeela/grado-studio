/* ГРАДО · вход нового интерфейса (план 09.11.2026, шаг И1): ядро Rust (WebAssembly), Pinia, Web Awesome, dockview,
   OpenLayers; тема «Синька» — общая с нынешним интерфейсом (apps/grado2/ui/src/theme.css). Страница — /g3/. */
import "@awesome.me/webawesome/dist/styles/themes/default.css";
import "dockview-vue/dist/styles/dockview.css";
import "ol/ol.css";
import "./fonts.css";
import "../../../grado2/ui/src/theme.css";
import "./app.css";

import "@awesome.me/webawesome/dist/components/button/button.js";
import "@awesome.me/webawesome/dist/components/input/input.js";
import "@awesome.me/webawesome/dist/components/switch/switch.js";
import "@awesome.me/webawesome/dist/components/badge/badge.js";

import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import MapPanel from "./panels/MapPanel.vue";
import LayersPanel from "./panels/LayersPanel.vue";
import ProjectPanel from "./panels/ProjectPanel.vue";
import CheckPanel from "./panels/CheckPanel.vue";
import StubPanel from "./panels/StubPanel.vue";
import { loadCore } from "./core";
import wasmUrl from "./wasm/grado_core_wasm_bg.wasm?url";

const dark = (() => { try { return localStorage.getItem("grado-next-theme") === "dark"; } catch { return false; } })();
document.documentElement.classList.add(dark ? "wa-dark" : "wa-light");

const t0 = performance.now();
loadCore({ module_or_path: wasmUrl }).then(() => {
  (window as unknown as { gradoCoreMs: number }).gradoCoreMs = performance.now() - t0;   // замер для tools/ui_baseline.mjs
  const app = createApp(App);
  app.use(createPinia());
  /* окна dockview находят содержимое по имени компонента (workspaces.ts component) */
  app.component("map", MapPanel).component("layers", LayersPanel).component("project", ProjectPanel)
    .component("check", CheckPanel).component("stub", StubPanel);
  app.mount("#app");
}).catch(e => {
  document.body.textContent = "Ядро программы не загрузилось: " + (e?.message || e) + ". Обновите страницу; если не помогло — нужен браузер посвежее.";
});
