/* ГРАДО 2 · вход нового интерфейса: подключает Web Awesome, dockview, OpenLayers и монтирует App.vue.
   Собирается Vite (vite.config.js); страница — /next/index.html на сервере ГРАДО 2. */
import "@awesome.me/webawesome/dist/styles/themes/default.css";
import "@awesome.me/webawesome/dist/styles/utilities.css";
import "dockview-vue/dist/styles/dockview.css";
import "ol/ol.css";
import "./theme.css";

import "@awesome.me/webawesome/dist/components/button/button.js";
import "@awesome.me/webawesome/dist/components/button-group/button-group.js";
import "@awesome.me/webawesome/dist/components/dropdown/dropdown.js";
import "@awesome.me/webawesome/dist/components/dropdown-item/dropdown-item.js";
import "@awesome.me/webawesome/dist/components/divider/divider.js";
import "@awesome.me/webawesome/dist/components/tooltip/tooltip.js";
import "@awesome.me/webawesome/dist/components/select/select.js";
import "@awesome.me/webawesome/dist/components/option/option.js";
import "@awesome.me/webawesome/dist/components/color-picker/color-picker.js";
import "@awesome.me/webawesome/dist/components/number-input/number-input.js";
import "@awesome.me/webawesome/dist/components/slider/slider.js";
import "@awesome.me/webawesome/dist/components/switch/switch.js";
import "@awesome.me/webawesome/dist/components/input/input.js";
import "@awesome.me/webawesome/dist/components/badge/badge.js";

import { createApp } from "vue";
import App from "./App.vue";
import MapPanel from "./panels/MapPanel.vue";
import LayersPanel from "./panels/LayersPanel.vue";
import PropsPanel from "./panels/PropsPanel.vue";
import TepPanel from "./panels/TepPanel.vue";
import { applyTheme, theme } from "./store.js";

applyTheme(theme.value);
/* окна dockview находят содержимое по имени компонента (component: "map" в App.vue) — регистрируем глобально */
const app = createApp(App);
app.component("map", MapPanel).component("layers", LayersPanel).component("props", PropsPanel).component("tep", TepPanel);
app.mount("#app");
