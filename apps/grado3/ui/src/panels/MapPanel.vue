<!-- ГРАДО · окно «Карта» (план 09.11.2026, шаги И1 и И2): подложка (OSM, спутник Esri, Sentinel-2, без подложки),
     слои проекта с оформлением через ядро Rust (symbology.ts: единый знак, категории, диапазоны, правила, штриховка,
     подписи, слои знака parts и типы линий ЛГР REDLN97), граница территории поверх слоёв и метка найденного в поиске.
     Курсор и масштаб — в строку состояния, координаты в МСК считает ядро Rust (core.ts). -->
<template>
  <div class="g3-map-wrap">
    <div ref="el" class="g3-map" />
    <div class="g3-base" role="group" aria-label="Подложка карты">
      <button v-for="(label, id) in BASEMAPS" :key="id" type="button" class="b-btn"
              :aria-pressed="project.basemap === id ? 'true' : 'false'" :title="label"
              @click="cmd.run('подложка ' + id)">
        {{ id === "osm" ? "Схема" : id === "esri" ? "Спутник" : id === "s2" ? "Sentinel" : "Нет" }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import OlMap from "ol/Map";
import View from "ol/View";
import Feature from "ol/Feature";
import Point from "ol/geom/Point";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import OSM from "ol/source/OSM";
import XYZ from "ol/source/XYZ";
import VectorSource from "ol/source/Vector";
import GeoJSON from "ol/format/GeoJSON";
import { Circle, Fill, Stroke, Style } from "ol/style";
import { fromLonLat, toLonLat, transformExtent } from "ol/proj";
import { isEmpty, extend, createEmpty } from "ol/extent";
import { mskToWgs, wgsToMsk } from "../core";
import { layerStyleFunction, loadSymbologyLibs } from "../symbology";
import { BASEMAPS, useProject, type GeoFeature } from "../stores/project";
import { useUi } from "../stores/ui";
import { useCommands } from "../stores/commands";

const el = ref<HTMLElement | null>(null);
const project = useProject(), ui = useUi(), cmd = useCommands();
let map: OlMap | null = null;
const baseLayers: Record<string, TileLayer<OSM | XYZ>> = {};
const vectors = new Map<string, VectorLayer<VectorSource>>();
const fmt = new GeoJSON({ featureProjection: "EPSG:3857" });

const markSrc = new VectorSource();
const markLayer = new VectorLayer({
  source: markSrc,
  zIndex: 1200,
  style: f => (f.getGeometry()?.getType() === "Point"
    ? [
        new Style({ image: new Circle({ radius: 9, stroke: new Stroke({ color: "#1a5fb4", width: 2 }), fill: new Fill({ color: "rgba(26,95,180,0.14)" }) }) }),
        new Style({ image: new Circle({ radius: 2.5, fill: new Fill({ color: "#1a5fb4" }) }) }),
      ]
    : new Style({ stroke: new Stroke({ color: "#1a5fb4", width: 2.5 }), fill: new Fill({ color: "rgba(26,95,180,0.10)" }) })),
});

function viewLat(): number {
  const c = map?.getView().getCenter();
  return c ? toLonLat(c)[1] : 55.7558;
}

function syncBasemap() {
  for (const [id, lyr] of Object.entries(baseLayers)) lyr.setVisible(project.basemap === id);
}

function refresh(full = false) {
  if (!map) return;
  if (full) {
    for (const v of vectors.values()) map.removeLayer(v);
    vectors.clear();
  }
  const keys = new Set(project.layers.map(l => l.key));
  for (const [k, v] of vectors) if (!keys.has(k)) { map.removeLayer(v); vectors.delete(k); }
  const n = project.layers.length;
  project.layers.forEach((l, i) => {
    const fc = project.data(l.key);
    let v = vectors.get(l.key);
    if (!v) {
      const src = new VectorSource({ features: fc ? fmt.readFeatures(fc) : [] });
      v = new VectorLayer({ source: src });
      vectors.set(l.key, v);
      map!.addLayer(v);
    }
    v.setStyle(layerStyleFunction(l, fc, viewLat));
    v.setVisible(project.shown(l) || l.role === "territory");
    v.setZIndex(l.role === "territory" ? 1000 : n - i);
  });
}

function fit(key?: string): boolean {
  if (!map) return false;
  const ext = createEmpty();
  const keys = key ? [key] : project.territory ? [project.territory.key] : [...vectors.keys()];
  for (const k of keys) {
    const s = vectors.get(k)?.getSource();
    const e = s && s.getFeatures().length ? s.getExtent() : null;
    if (e) extend(ext, e);
  }
  if (isEmpty(ext)) return false;
  map.getView().fit(ext, { padding: [40, 40, 40, 40], maxZoom: 19, duration: 250 });
  return true;
}

function markAddress(lon: number, lat: number, bbox?: [number, number, number, number]) {
  if (!map) return;
  markSrc.clear();
  const c = fromLonLat([lon, lat]);
  markSrc.addFeature(new Feature(new Point(c)));
  if (bbox && (bbox[0] !== bbox[2] || bbox[1] !== bbox[3])) {
    map.getView().fit(transformExtent(bbox, "EPSG:4326", "EPSG:3857"), { padding: [60, 60, 60, 60], maxZoom: 18, duration: 250 });
  } else {
    map.getView().animate({ center: c, zoom: 17, duration: 250 });
  }
}

function markFeatures(features: GeoFeature[]) {
  if (!map) return;
  markSrc.clear();
  const olFeats = fmt.readFeatures({ type: "FeatureCollection", features });
  if (!olFeats.length) return;
  markSrc.addFeatures(olFeats);
  const ext = markSrc.getExtent();
  if (ext && !isEmpty(ext)) map.getView().fit(ext, { padding: [60, 60, 60, 60], maxZoom: 18, duration: 250 });
}

function clearMark() {
  markSrc.clear();
}

function scaleNow() {
  const v = map!.getView(), c = v.getCenter(), r = v.getResolution();
  if (!c || !r) return;
  const lat = (toLonLat(c)[1] * Math.PI) / 180;
  ui.scale = (r * Math.cos(lat) * 96) / 0.0254;
}

onMounted(() => {
  baseLayers.osm = new TileLayer({ source: new OSM(), zIndex: 0 });
  baseLayers.esri = new TileLayer({
    source: new XYZ({ url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", maxZoom: 19 }),
    visible: false,
    zIndex: 0,
  });
  baseLayers.s2 = new TileLayer({
    source: new XYZ({ url: "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/g/{z}/{y}/{x}.jpg", maxZoom: 15 }),
    visible: false,
    zIndex: 0,
  });
  syncBasemap();

  const v = project.doc?.view;
  map = new OlMap({
    target: el.value!,
    layers: [baseLayers.osm, baseLayers.esri, baseLayers.s2, markLayer],
    view: new View({ center: fromLonLat((v?.center as [number, number]) || [37.6176, 55.7558]), zoom: (v?.zoom as number) || 13 }),
  });
  refresh(true);
  loadSymbologyLibs().then(() => refresh(false));
  map.on("pointermove", e => { ui.cursor = wgsToMsk(toLonLat(e.coordinate) as [number, number]); });
  map.getView().on("change:resolution", scaleNow);
  map.once("rendercomplete", () => { scaleNow(); (window as unknown as { gradoMapMs: number }).gradoMapMs = performance.now(); });
  ui.map.api = {
    refresh,
    fit,
    syncBasemap,
    markAddress,
    markFeatures,
    clearMark,
    centerMsk: p => map?.getView().animate({ center: fromLonLat(mskToWgs(p)), duration: 250 }),
  };
  stopOpen = project.$onAction(({ name, after }) => { if (name === "load") after(() => { syncBasemap(); refresh(true); }); });
});
let stopOpen: (() => void) | null = null;
onBeforeUnmount(() => { stopOpen?.(); ui.map.api = null; ui.cursor = null; markSrc.clear(); map?.setTarget(undefined); map = null; vectors.clear(); });
</script>

<style scoped>
.g3-map-wrap { position: relative; width: 100%; height: 100%; }
.g3-map { width: 100%; height: 100%; }
.g3-base { position: absolute; right: 10px; top: 10px; z-index: 4; display: flex; background: var(--wa-color-surface-raised); border: 1px solid var(--wa-color-neutral-border-normal); border-radius: 6px; overflow: hidden; box-shadow: var(--wa-shadow-s); }
.b-btn { border: 0; background: none; color: inherit; font: inherit; font-size: 11px; padding: 4px 8px; cursor: pointer; }
.b-btn:hover { background: var(--wa-color-surface-lowered); }
.b-btn[aria-pressed="true"] { background: var(--wa-color-brand-fill-quiet); color: var(--wa-color-brand-on-quiet); font-weight: 600; }
</style>
