<!-- ГРАДО 2 · окно «Карта» нового интерфейса: OpenLayers, подложка по теме, слои открытого проекта из store.project.
     Порядок слоёв — как в окне «Слои» (верхний рисуется поверх), видимость — слой и его группа.
     Оформление — все способы рабочей страницы (symbology.js): единое, категории, диапазоны, правила, знаки ЛГР, подписи, масштаб.
     Размер карты следит за окном dockview (ResizeObserver); масштаб пишет в store.scale, вид — в store.viewNow (для записи проекта). -->
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
import { fromLonLat, toLonLat } from "ol/proj.js";
import { project, scale, shown, theme, viewNow } from "../store.js";
import { denToRes, fullStyle, loadLibs, okn, scaleDen, styleFunction } from "../symbology.js";

const el = ref(null);
let map, ro;
const vec = {};                       // key слоя → VectorLayer
const fmt = new GeoJSON({ featureProjection: "EPSG:3857" });   // в файле проекта данные в долготе и широте

const lat = () => toLonLat(map.getView().getCenter())[1];

/* Слой OpenLayers по описанию слоя из файла: оформление, видимость по масштабу (как в QGIS), прозрачность слоя.
   Подписи разводятся (declutter), если у слоя есть подпись. Источник с объектами переиспользуется. */
function olLayer(l, i, n, src) {
  const st = fullStyle(l.style), la = lat();
  return new VectorLayer({
    source: src, style: styleFunction(l, project.data[l.key]?.fc, lat), declutter: !!st.label,
    visible: shown(l), zIndex: n - i, opacity: okn(l.layerOpacity, 1),
    maxResolution: st.maxDen ? denToRes(st.maxDen, la) : Infinity, minResolution: st.minDen ? denToRes(st.minDen, la) : 0,
    properties: { key: l.key },
  });
}
const sig = l => JSON.stringify([l.style, l.layerOpacity, l.geom]);

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
    vec[l.key] = olLayer(l, i, n, src); vec[l.key].set("sig", sig(l));
    map.addLayer(vec[l.key]);
  });
  const v = project.view, view = map.getView();
  if (v?.center?.length === 2 && Number.isFinite(+v.zoom)) { view.setCenter(fromLonLat(v.center)); view.setZoom(+v.zoom); }
  else if (!isEmpty(ext)) view.fit(ext, { padding: [30, 30, 30, 30], maxZoom: 18 });
}

/* Видимость и порядок — на месте; изменённое оформление — новый слой на том же источнике (без перечитывания данных). */
function refresh() {
  const n = project.layers.length;
  project.layers.forEach((l, i) => {
    let v = vec[l.key]; if (!v) return;
    if (v.get("sig") !== sig(l)) {
      const nv = olLayer(l, i, n, v.getSource()); nv.set("sig", sig(l));
      map.getLayers().setAt(map.getLayers().getArray().indexOf(v), nv); vec[l.key] = v = nv;
    }
    v.setVisible(shown(l)); v.setZIndex(n - i);
  });
}

onMounted(() => {
  map = new Map({ target: el.value, layers: [basemap(theme.value)], view: new View({ center: fromLonLat([37.62, 55.75]), zoom: 11 }) });
  const upd = () => {
    const v = map.getView();
    scale.value = scaleDen(v.getResolution(), lat());     // как в рабочей странице: 0,2646 мм на пиксель, поправка на широту
    viewNow.center = toLonLat(v.getCenter()); viewNow.zoom = v.getZoom();   // вид уходит в файл при записи, сдвиг карты — не правка
  };
  map.on("moveend", upd); upd();
  ro = new ResizeObserver(() => map.updateSize()); ro.observe(el.value);
  rebuild();
  loadLibs().then(() => map.render());   // знаки ЛГР появляются, когда пришли библиотеки
  watch(theme, t => map.getLayers().setAt(0, basemap(t)));
  watch(() => project.data, rebuild);
  watch([() => project.layers, () => project.groups], refresh, { deep: true });
});

onBeforeUnmount(() => { ro?.disconnect(); map?.setTarget(undefined); });
</script>

<style>
.map { width: 100%; height: 100%; background: var(--g-canvas); }
</style>
