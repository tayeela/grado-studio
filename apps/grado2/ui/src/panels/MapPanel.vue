<!-- ГРАДО 2 · окно «Карта» нового интерфейса: OpenLayers, подложка по теме, слои-образцы из store.js.
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
import Feature from "ol/Feature.js";
import Polygon from "ol/geom/Polygon.js";
import LineString from "ol/geom/LineString.js";
import { fromLonLat, getPointResolution } from "ol/proj.js";
import { Fill, Stroke, Style } from "ol/style.js";
import { layers, scale, theme } from "../store.js";

const el = ref(null);
let map, ro;

/* Образец: условная территория у Гольянова (не данные проекта). */
const ring = pts => [pts.map(([x, y]) => fromLonLat([x, y]))];
const SAMPLE = {
  boundary: new Polygon(ring([[37.794, 55.822], [37.812, 55.821], [37.815, 55.829], [37.803, 55.833], [37.792, 55.829], [37.794, 55.822]])),
  lgr: new LineString(ring([[37.790, 55.8245], [37.817, 55.8235]])[0]),
  zouit: new Polygon(ring([[37.800, 55.8255], [37.808, 55.825], [37.809, 55.8285], [37.801, 55.829], [37.800, 55.8255]])),
};

function style(l) {
  const w = l.kind === "line" ? 2.5 : 1.2;
  return new Style({
    stroke: new Stroke({ color: l.color, width: w, lineDash: l.id === "boundary" ? [10, 4, 2, 4] : undefined }),
    fill: l.kind === "fill" ? new Fill({ color: l.color + "40" }) : undefined,
  });
}

const vec = {};
function basemap(t) {
  return t === "dark"
    ? new TileLayer({ source: new XYZ({ url: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", maxZoom: 16, crossOrigin: "anonymous", attributions: "Подложка © Esri, HERE, Garmin, © OpenStreetMap contributors" }) })
    : new TileLayer({ source: new OSM(), className: "basemap", opacity: 0.55 });
}

onMounted(() => {
  const base = basemap(theme.value);
  map = new Map({ target: el.value, layers: [base], view: new View({ center: fromLonLat([37.803, 55.827]), zoom: 15 }) });
  for (const l of layers) {
    if (!SAMPLE[l.id]) continue;
    vec[l.id] = new VectorLayer({ source: new VectorSource({ features: [new Feature(SAMPLE[l.id])] }), style: style(l), visible: l.visible });
    map.addLayer(vec[l.id]);
  }
  const upd = () => {
    const v = map.getView(), res = getPointResolution(v.getProjection(), v.getResolution(), v.getCenter());
    scale.value = Math.round(res / 0.00028 / 10) * 10;   // 0,28 мм на пиксель экрана
  };
  map.on("moveend", upd); upd();
  ro = new ResizeObserver(() => map.updateSize()); ro.observe(el.value);
  watch(theme, t => map.getLayers().setAt(0, basemap(t)));
  watch(layers, ls => { for (const l of ls) if (vec[l.id]) { vec[l.id].setVisible(l.visible); vec[l.id].setStyle(style(l)); } }, { deep: true });
});

onBeforeUnmount(() => { ro?.disconnect(); map?.setTarget(undefined); });
</script>

<style>
.map { width: 100%; height: 100%; background: var(--g-canvas); }
</style>
