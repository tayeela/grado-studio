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
import { dataRev, mapApi } from "../edit.js";
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

/* Слои карты по слоям проекта: новый слой или заменённые данные — новый источник, изменённое оформление — новый слой
   на том же источнике, видимость и порядок — на месте; слои, которых в проекте нет, убираются. */
function sync() {
  const n = project.layers.length, keys = new Set(project.layers.map(l => l.key));
  for (const k in vec) if (!keys.has(k)) { map.removeLayer(vec[k]); delete vec[k]; }
  project.layers.forEach((l, i) => {
    const fc = project.data[l.key]?.fc;
    let v = vec[l.key];
    if (!v || v.get("fc") !== fc) {
      let feats = [];
      try { feats = fc ? fmt.readFeatures(fc) : []; } catch { feats = []; }   // битый слой не должен ронять остальные
      if (v) map.removeLayer(v);
      v = vec[l.key] = olLayer(l, i, n, new VectorSource({ features: feats }));
      v.set("fc", fc); v.set("sig", sig(l)); map.addLayer(v);
    } else if (v.get("sig") !== sig(l)) {
      const nv = olLayer(l, i, n, v.getSource()); nv.set("fc", fc); nv.set("sig", sig(l));
      map.getLayers().setAt(map.getLayers().getArray().indexOf(v), nv); vec[l.key] = v = nv;
    }
    v.setVisible(shown(l)); v.setZIndex(n - i);
  });
}

/* Другой проект: слои заново и его вид карты (или все объекты в кадре). */
function opened() {
  for (const k in vec) { map.removeLayer(vec[k]); delete vec[k]; }
  sync();
  const v = project.view, view = map.getView();
  if (v?.center?.length === 2 && Number.isFinite(+v.zoom)) { view.setCenter(fromLonLat(v.center)); view.setZoom(+v.zoom); }
  else zoomTo(Object.keys(vec));
}

function zoomTo(keys) {
  const ext = createEmpty();
  keys.forEach(k => { const s = vec[k]?.getSource(); if (s?.getFeatures().length) extend(ext, s.getExtent()); });
  if (!isEmpty(ext)) map.getView().fit(ext, { padding: [40, 40, 40, 40], maxZoom: 18, duration: 200 });
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
  opened();
  mapApi.zoomTo = zoomTo;
  loadLibs().then(() => map.render());   // знаки ЛГР появляются, когда пришли библиотеки
  watch(theme, t => map.getLayers().setAt(0, basemap(t)));
  watch(() => project.raw, opened);
  watch([() => project.layers, () => project.groups, dataRev], sync, { deep: true });
});

onBeforeUnmount(() => { ro?.disconnect(); map?.setTarget(undefined); });
</script>

<style>
.map { width: 100%; height: 100%; background: var(--g-canvas); }
</style>
