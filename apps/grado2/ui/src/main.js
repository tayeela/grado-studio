/* ГРАДО 2 · вход нового интерфейса: подключает Web Awesome, dockview, OpenLayers и монтирует App.vue.
   Собирается Vite (vite.config.js); страница — /next/index.html на сервере ГРАДО 2. */
import "@awesome.me/webawesome/dist/styles/themes/default.css";
import "@awesome.me/webawesome/dist/styles/utilities.css";
import "dockview-vue/dist/styles/dockview.css";
import "ol/ol.css";
import "./fonts.css";
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
import "@awesome.me/webawesome/dist/components/dialog/dialog.js";
import "@awesome.me/webawesome/dist/components/checkbox/checkbox.js";
import "@awesome.me/webawesome/dist/components/radio/radio.js";
import "@awesome.me/webawesome/dist/components/radio-group/radio-group.js";
import "@awesome.me/webawesome/dist/components/textarea/textarea.js";
import "@awesome.me/webawesome/dist/components/progress-bar/progress-bar.js";
import "@awesome.me/webawesome/dist/components/spinner/spinner.js";
import "@awesome.me/webawesome/dist/components/details/details.js";

import { createApp } from "vue";
import App from "./App.vue";
import MapPanel from "./panels/MapPanel.vue";
import LayersPanel from "./panels/LayersPanel.vue";
import PropsPanel from "./panels/PropsPanel.vue";
import TepPanel from "./panels/TepPanel.vue";
import SheetPanel from "./panels/SheetPanel.vue";
import AlbumLayout from "./panels/AlbumLayout.vue";
import ObjectPanel from "./panels/ObjectPanel.vue";
import TablePanel from "./panels/TablePanel.vue";
import ViewsPanel from "./panels/ViewsPanel.vue";
import HelpPanel from "./panels/HelpPanel.vue";
import DataPanel from "./panels/DataPanel.vue";
import ConsPanel from "./panels/ConsPanel.vue";
import GraphPanel from "./panels/GraphPanel.vue";
import SketchPanel from "./panels/SketchPanel.vue";
import NormsPanel from "./panels/NormsPanel.vue";
import VarsPanel from "./panels/VarsPanel.vue";
import ComparePanel from "./panels/ComparePanel.vue";
import VolumePanel from "./panels/VolumePanel.vue";
import CommentsPanel from "./panels/CommentsPanel.vue";
import AlbumPanel from "./panels/AlbumPanel.vue";
import { applyTheme, theme } from "./store.js";

applyTheme(theme.value);
/* окна dockview находят содержимое по имени компонента (component: "map" в App.vue) — регистрируем глобально */
const app = createApp(App);
app.component("map", MapPanel).component("layers", LayersPanel).component("props", PropsPanel).component("tep", TepPanel)
  .component("object", ObjectPanel).component("table", TablePanel).component("views", ViewsPanel).component("help", HelpPanel).component("data", DataPanel).component("cons", ConsPanel).component("graph", GraphPanel)
  .component("sketch", SketchPanel).component("norms", NormsPanel)
  .component("vars", VarsPanel).component("cmp", ComparePanel).component("vol", VolumePanel).component("comments", CommentsPanel).component("sheet", SheetPanel).component("album", AlbumPanel).component("albumlay", AlbumLayout);
app.mount("#app");
