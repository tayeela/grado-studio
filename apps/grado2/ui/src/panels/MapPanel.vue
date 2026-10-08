<!-- ГРАДО 2 · окно «Карта» нового интерфейса: OpenLayers, подложка (схема по теме, спутник, Sentinel-2), граница
     территории и слои открытого проекта из store.project.
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
import { defaults as defaultInteractions } from "ol/interaction/defaults.js";
import DragBox from "ol/interaction/DragBox.js";
import { shiftKeyOnly } from "ol/events/condition.js";
import { Circle as CircleStyle, Fill, Stroke, Style } from "ol/style.js";
import { fromLonLat, toLonLat } from "ol/proj.js";
import { basemapId, project, scale, shown, theme, viewNow } from "../store.js";
import { dataRev, mapApi } from "../edit.js";
import { indexOf, sel, selected, setSel, toggleSel } from "../features.js";
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

/* Подложки — как web/app.js BASEMAPS: «Схема OSM» в тёмной теме — тёмная схема Esri. */
function basemap(id, t) {
  if (id === "esri") return new TileLayer({ className: "basemap-sat", opacity: 0.9, source: new XYZ({ url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", maxZoom: 19, attributions: "Снимки © Esri, Maxar, Earthstar Geographics" }) });
  if (id === "s2") return new TileLayer({ className: "basemap-sat", opacity: 0.9, source: new XYZ({ url: "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/g/{z}/{y}/{x}.jpg", maxZoom: 15, attributions: "Sentinel-2 cloudless 2021 © EOX IT Services GmbH (содержит изменённые данные Copernicus Sentinel)" }) });
  return t === "dark"
    ? new TileLayer({ source: new XYZ({ url: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", maxZoom: 16, crossOrigin: "anonymous", attributions: "Подложка © Esri, HERE, Garmin, © OpenStreetMap contributors" }) })
    : new TileLayer({ source: new OSM(), className: "basemap", opacity: 0.55 });
}

/* Граница территории (поле territory файла): штрихпунктир, как у рабочей страницы; правка границы — с окном «Данные». */
const terrSrc = new VectorSource();
const terrStyle = new Style({ stroke: new Stroke({ color: "#b3261e", width: 2, lineDash: [12, 4, 2, 4] }) });
function drawTerr() {
  terrSrc.clear(true);
  const t = project.raw?.territory; if (!t?.geometry) return;
  try { terrSrc.addFeature(fmt.readFeature(t)); } catch { /* граница повреждена — карта без неё */ }
}

/* Слои карты по слоям проекта: новый слой или заменённые данные — новый источник, изменённое оформление — новый слой
   на том же источнике, видимость и порядок — на месте; слои, которых в проекте нет, убираются. */
function sync() {
  const n = project.layers.length, keys = new Set(project.layers.map(l => l.key));
  for (const k in vec) if (!keys.has(k)) { map.removeLayer(vec[k]); delete vec[k]; }
  project.layers.forEach((l, i) => {
    const fc = project.data[l.key]?.fc;
    let v = vec[l.key];
    if (!v) {
      v = vec[l.key] = olLayer(l, i, n, new VectorSource({ features: readAll(fc) }));
      v.set("fc", fc); v.set("sig", sig(l)); map.addLayer(v);
    } else if (v.get("fc") !== fc || v.get("sig") !== sig(l)) {
      if (v.get("fc") !== fc) patch(v.getSource(), v.get("fc"), fc);
      const nv = olLayer(l, i, n, v.getSource()); nv.set("fc", fc); nv.set("sig", sig(l));   // стиль заново: категории и диапазоны зависят от данных
      map.getLayers().setAt(map.getLayers().getArray().indexOf(v), nv); vec[l.key] = v = nv;
    }
    v.setVisible(shown(l)); v.setZIndex(n - i);
  });
  drawSel();
}

/* Объекты GeoJSON слоя → объекты карты; у каждого ссылка gj на свою запись в файле (по ней выбор и правка). */
function readAll(fc) {
  indexOf(fc);                                      // номера _uid у всех объектов
  return (fc?.features || []).map(readOne).filter(Boolean);
}
function readOne(gj) {
  try { const f = fmt.readFeature(gj); f.gj = gj; return f; } catch { return null; }   // битый объект не должен ронять слой
}
/* Правка данных: только изменённые записи (новые объекты в fc) меняются на карте; тысячи прочих не перечитываются. */
function patch(src, oldFc, fc) {
  indexOf(fc);
  const now = new Set(fc?.features || []), was = new Set(oldFc?.features || []);
  const gone = src.getFeatures().filter(f => !now.has(f.gj)), add = (fc?.features || []).filter(gj => !was.has(gj));
  if (gone.length + add.length > 2000) { src.clear(true); src.addFeatures(readAll(fc)); return; }
  gone.forEach(f => src.removeFeature(f));
  src.addFeatures(add.map(readOne).filter(Boolean));
}

/* ---------- выбор: щелчок, Shift+щелчок, рамка с Shift; подсветка поверх слоёв ---------- */
const selSrc = new VectorSource();
const SELSTYLE = {
  poly: new Style({ fill: new Fill({ color: "rgba(47,111,196,.15)" }), stroke: new Stroke({ color: "#2f6fc4", width: 3 }) }),
  line: new Style({ stroke: new Stroke({ color: "#2f6fc4", width: 4 }) }),
  point: new Style({ image: new CircleStyle({ radius: 8, stroke: new Stroke({ color: "#2f6fc4", width: 3 }) }) }),
};
const gkind = f => { const t = f.getGeometry()?.getType() || ""; return /Point/.test(t) ? "point" : /Line/.test(t) ? "line" : "poly"; };
function drawSel() {
  selSrc.clear(true);
  selSrc.addFeatures(selected().slice(0, 5000).map(s => readOne(s.f)).filter(Boolean));
}
function hitAt(pixel) {
  let hit = null;
  map.forEachFeatureAtPixel(pixel, (f, layer) => { const key = layer?.get("key"); if (!key || !f.gj) return; hit = { key, uid: f.gj.properties._uid }; return true; },
    { hitTolerance: 4, layerFilter: la => !!la.get("key") && la.getVisible() });
  return hit;
}
function onClick(e) {
  const hit = hitAt(e.pixel), add = e.originalEvent.shiftKey || e.originalEvent.metaKey || e.originalEvent.ctrlKey;
  if (add) { if (hit) toggleSel(hit); }
  else setSel(hit ? [hit] : []);
}
function onBox(box) {
  const ext = box.getGeometry().getExtent(), out = [];
  project.layers.forEach(l => {
    const v = vec[l.key]; if (!v?.getVisible()) return;
    v.getSource().forEachFeatureIntersectingExtent(ext, f => { if (f.gj) out.push({ key: l.key, uid: f.gj.properties._uid }); });
  });
  setSel([...sel, ...out]);
}

/* Другой проект: слои заново и его вид карты (или все объекты в кадре). Пока окно карты не получило размер
   (dockview ещё раскладывает окна), вид ставится позже — иначе «всё в кадре» на нулевом окне даёт обзор всей Земли. */
let viewPending = true;
function opened() {
  for (const k in vec) { map.removeLayer(vec[k]); delete vec[k]; }
  sync();
  drawTerr();
  viewPending = true; applyView();
}
function applyView() {
  const size = map.getSize();
  if (!viewPending || !size || !size[0] || !size[1]) return;
  viewPending = false;
  const v = project.view, view = map.getView();
  if (v?.center?.length === 2 && Number.isFinite(+v.zoom)) { view.setCenter(fromLonLat(v.center)); view.setZoom(+v.zoom); }
  else if (terrSrc.getFeatures().length) view.fit(terrSrc.getExtent(), { padding: [40, 40, 40, 40], maxZoom: 18 });
  else zoomTo(Object.keys(vec), 0);
}
/* Вид карты из окна «Виды»: центр (долгота, широта) и уровень. */
mapApi.setView = (center, zoom) => { const v = map.getView(); v.setCenter(fromLonLat(center)); v.setZoom(zoom); };

mapApi.fitFeature = gj => { const f = readOne(gj); if (f) map.getView().fit(f.getGeometry().getExtent(), { padding: [80, 80, 80, 80], maxZoom: 19, duration: 150 }); };
function zoomTo(keys, duration = 200) {
  const ext = createEmpty();
  keys.forEach(k => { const s = vec[k]?.getSource(); if (s?.getFeatures().length) extend(ext, s.getExtent()); });
  if (!isEmpty(ext)) map.getView().fit(ext, { padding: [40, 40, 40, 40], maxZoom: 18, duration });
}

onMounted(() => {
  map = new Map({
    target: el.value, layers: [basemap(basemapId.value, theme.value), new VectorLayer({ source: terrSrc, zIndex: 9999, style: terrStyle }), new VectorLayer({ source: selSrc, zIndex: 10000, style: f => SELSTYLE[gkind(f)] })],
    view: new View({ center: fromLonLat([37.62, 55.75]), zoom: 11 }),
    interactions: defaultInteractions({ shiftDragZoom: false }),   // Shift+рамка — выбор, как в рабочей странице
  });
  const box = new DragBox({ condition: shiftKeyOnly });
  box.on("boxend", () => onBox(box)); map.addInteraction(box);
  map.on("singleclick", onClick);
  const upd = () => {
    if (viewPending) return;                        // вид проекта ещё не поставлен: в файл не должен уйти случайный
    const v = map.getView();
    scale.value = scaleDen(v.getResolution(), lat());     // как в рабочей странице: 0,2646 мм на пиксель, поправка на широту
    viewNow.center = toLonLat(v.getCenter()); viewNow.zoom = v.getZoom();   // вид уходит в файл при записи, сдвиг карты — не правка
  };
  map.on("moveend", upd); upd();
  ro = new ResizeObserver(() => { map.updateSize(); if (viewPending) { applyView(); upd(); } }); ro.observe(el.value);
  opened();
  mapApi.zoomTo = zoomTo;
  loadLibs().then(() => map.render());   // знаки ЛГР появляются, когда пришли библиотеки
  watch([basemapId, theme], ([id, t]) => map.getLayers().setAt(0, basemap(id, t)));
  watch(() => project.raw, opened);
  watch([() => project.layers, () => project.groups, dataRev], sync, { deep: true });
  watch(sel, drawSel);
});

onBeforeUnmount(() => { ro?.disconnect(); map?.setTarget(undefined); });
</script>

<style>
.map { width: 100%; height: 100%; background: var(--g-canvas); }
</style>
