<!-- ГРАДО 2 · окно «Карта» нового интерфейса: OpenLayers, подложка по теме, слои открытого проекта из store.project.
     Порядок слоёв — как в окне «Слои» (верхний рисуется поверх), видимость — слой и его группа.
     Оформление пока «единое» (заливка, контур, толщина, прозрачность); категории, диапазоны и знаки ЛГР — следующие шаги переноса.
     Размер карты следит за окном dockview (ResizeObserver); масштаб пишет в store.scale для строки состояния. -->
<template><div ref="el" class="map"></div></template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import Map from "ol/Map.js";
import View from "ol/View.js";
import TileLayer from "ol/layer/Tile.js";
import VectorLayer from "ol/layer/Vector.js";
import VectorSource from "ol/source/Vector.js";
import OSM from "ol/source/OSM.js";
import XYZ from "ol/source/XYZ.js";
import GeoJSON from "ol/format/GeoJSON.js";
import { createEmpty, extend, isEmpty } from "ol/extent.js";
import { fromLonLat, getPointResolution } from "ol/proj.js";
import { Circle, Fill, Stroke, Style } from "ol/style.js";
import { project, scale, shown, styleOf, theme } from "../store.js";

const el = ref(null);
let map, ro;
const vec = {};                       // key слоя → VectorLayer
const fmt = new GeoJSON({ featureProjection: "EPSG:3857" });   // в файле проекта данные в долготе и широте

const rgba = (hex, a) => {
  let h = hex.slice(1); if (h.length <= 4) h = [...h].map(c => c + c).join("");
  const n = parseInt(h.slice(0, 6), 16);
  return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`;
};

/* Как рисует рабочая страница (web/layers.js styleFor, режим «единое»): линия — цветом заливки,
   полигон — полупрозрачной заливкой и контуром, точка — кружком; толщина в пикселях экрана. */
function style(l) {
  const s = styleOf(l);
  const point = new Circle({ radius: 2 + s.width * 2, fill: new Fill({ color: s.fill }), stroke: new Stroke({ color: s.stroke, width: 1 }) });
  if (l.geom === "line") return new Style({ stroke: new Stroke({ color: s.fill, width: s.width, lineCap: "round", lineJoin: "round" }), image: point });
  if (l.geom === "point") return new Style({ image: point });
  return new Style({
    fill: new Fill({ color: rgba(s.fill, s.opacity) }),
    stroke: s.width > 0 ? new Stroke({ color: s.stroke, width: s.width }) : undefined,
    image: point,
  });
}

function basemap(t) {
  return t === "dark"
    ? new TileLayer({ source: new XYZ({ url: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", maxZoom: 16, crossOrigin: "anonymous", attributions: "Подложка © Esri, HERE, Garmin, © OpenStreetMap contributors" }) })
    : new TileLayer({ source: new OSM(), className: "basemap", opacity: 0.55 });
}

/* Слои проекта заново: при открытии другого проекта. */
function rebuild() {
  for (const k in vec) { map.removeLayer(vec[k]); delete vec[k]; }
  const n = project.layers.length, ext = createEmpty();
  project.layers.forEach((l, i) => {
    const fc = project.data[l.key]?.fc;
    let feats = [];
    try { feats = fc ? fmt.readFeatures(fc) : []; } catch { feats = []; }   // битый слой не должен ронять остальные
    const src = new VectorSource({ features: feats });
    if (feats.length) extend(ext, src.getExtent());
    vec[l.key] = new VectorLayer({ source: src, style: style(l), visible: shown(l), zIndex: n - i, properties: { key: l.key } });
    map.addLayer(vec[l.key]);
  });
  const v = project.view, view = map.getView();
  if (v?.center?.length === 2 && Number.isFinite(+v.zoom)) { view.setCenter(fromLonLat(v.center)); view.setZoom(+v.zoom); }
  else if (!isEmpty(ext)) view.fit(ext, { padding: [30, 30, 30, 30], maxZoom: 18 });
}

/* Видимость, порядок и оформление — без перечитывания данных. */
function refresh() {
  const n = project.layers.length;
  project.layers.forEach((l, i) => { const v = vec[l.key]; if (!v) return; v.setVisible(shown(l)); v.setZIndex(n - i); v.setStyle(style(l)); });
}

onMounted(() => {
  map = new Map({ target: el.value, layers: [basemap(theme.value)], view: new View({ center: fromLonLat([37.62, 55.75]), zoom: 11 }) });
  const upd = () => {
    const v = map.getView(), res = getPointResolution(v.getProjection(), v.getResolution(), v.getCenter());
    scale.value = Math.round(res / 0.00028 / 10) * 10;   // 0,28 мм на пиксель экрана
  };
  map.on("moveend", upd); upd();
  ro = new ResizeObserver(() => map.updateSize()); ro.observe(el.value);
  rebuild();
  watch(theme, t => map.getLayers().setAt(0, basemap(t)));
  watch(() => project.data, rebuild);
  watch([() => project.layers, () => project.groups], refresh, { deep: true });
});

onBeforeUnmount(() => { ro?.disconnect(); map?.setTarget(undefined); });
</script>

<style>
.map { width: 100%; height: 100%; background: var(--g-canvas); }
</style>
