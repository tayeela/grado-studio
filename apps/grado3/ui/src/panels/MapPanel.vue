<!-- ГРАДО · окно «Карта» каркаса (шаг И1): подложка OSM и слои проекта (данные — GeoJSON WGS84 из файла) с простым
     оформлением слоя (заливка, контур, толщина, прозрачность, пунктир); граница территории — поверх, синькой.
     Курсор и масштаб — в строку состояния, координаты в МСК считает ядро Rust (core.ts). Полное оформление (знак из слоёв,
     знаки ЛГР, подписи) переезжает на шагах И2–И3 из apps/grado2/ui/src/symbology.js. -->
<template>
  <div ref="el" class="g3-map" />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import OlMap from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import OSM from "ol/source/OSM";
import VectorSource from "ol/source/Vector";
import GeoJSON from "ol/format/GeoJSON";
import { Fill, Stroke, Style, Circle } from "ol/style";
import { fromLonLat, toLonLat } from "ol/proj";
import { isEmpty, extend, createEmpty } from "ol/extent";
import { mskToWgs, wgsToMsk } from "../core";
import { useProject } from "../stores/project";
import { useUi } from "../stores/ui";
import type { Layer } from "../types/project";

const el = ref<HTMLElement | null>(null);
const project = useProject(), ui = useUi();
let map: OlMap | null = null;
const vectors = new Map<string, VectorLayer<VectorSource>>();
const fmt = new GeoJSON({ featureProjection: "EPSG:3857" });

type St = { fill?: string; stroke?: string; width?: number; opacity?: number; dash?: number[] };
function hexA(c: string | undefined, a: number): string {
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(c || "");
  if (!m) return `rgba(80,90,110,${a})`;
  const h = m[1].length === 3 ? m[1].split("").map(x => x + x).join("") : m[1];
  return `rgba(${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)},${a})`;
}
function styleOf(l: Layer): Style {
  const s = (l.style || {}) as St, terr = l.role === "territory";
  const stroke = new Stroke({ color: terr ? "#2446d8" : hexA(s.stroke || s.fill, 1), width: terr ? 3 : (s.width ?? 1.5), lineDash: terr ? [8, 5] : s.dash });
  const fill = new Fill({ color: hexA(s.fill, terr ? 0 : (s.opacity ?? 0.35)) });
  return new Style({ stroke, fill: l.geom === "line" ? undefined : fill, image: new Circle({ radius: 4, fill, stroke }) });
}

function refresh() {
  if (!map) return;
  const keys = new Set(project.layers.map(l => l.key));
  for (const [k, v] of vectors) if (!keys.has(k)) { map.removeLayer(v); vectors.delete(k); }
  const n = project.layers.length;
  project.layers.forEach((l, i) => {
    let v = vectors.get(l.key);
    if (!v) {
      const fc = project.data(l.key);
      const src = new VectorSource({ features: fc ? fmt.readFeatures(fc) : [] });
      v = new VectorLayer({ source: src });
      vectors.set(l.key, v);
      map!.addLayer(v);
    }
    v.setStyle(styleOf(l));
    v.setVisible(l.visible !== false || l.role === "territory");
    v.setZIndex(l.role === "territory" ? 1000 : n - i);   // слои сверху вниз, как в «Слоях»; граница поверх всех
  });
}
function rebuild() { for (const v of vectors.values()) map?.removeLayer(v); vectors.clear(); refresh(); }

function fit(key?: string): boolean {
  if (!map) return false;
  const ext = createEmpty();
  const keys = key ? [key] : project.territory ? [project.territory.key] : [...vectors.keys()];
  for (const k of keys) { const s = vectors.get(k)?.getSource(); const e = s && s.getFeatures().length ? s.getExtent() : null; if (e) extend(ext, e); }
  if (isEmpty(ext)) return false;
  map.getView().fit(ext, { padding: [40, 40, 40, 40], maxZoom: 19, duration: 250 });
  return true;
}

function scaleNow() {
  const v = map!.getView(), c = v.getCenter(), r = v.getResolution();
  if (!c || !r) return;
  const lat = toLonLat(c)[1] * Math.PI / 180;
  ui.scale = r * Math.cos(lat) * 96 / 0.0254;          // экран 96 точек на дюйм, как масштаб в QGIS
}

onMounted(() => {
  const v = project.doc?.view;
  map = new OlMap({
    target: el.value!,
    layers: [new TileLayer({ source: new OSM() })],
    view: new View({ center: fromLonLat((v?.center as [number, number]) || [37.6176, 55.7558]), zoom: (v?.zoom as number) || 13 }),
  });
  rebuild();
  map.on("pointermove", e => { ui.cursor = wgsToMsk(toLonLat(e.coordinate) as [number, number]); });
  map.getView().on("change:resolution", scaleNow);
  map.once("rendercomplete", () => { scaleNow(); (window as unknown as { gradoMapMs: number }).gradoMapMs = performance.now(); });
  ui.map.api = { refresh, fit, centerMsk: p => map?.getView().animate({ center: fromLonLat(mskToWgs(p)), duration: 250 }) };
  stopOpen = project.$onAction(({ name, after }) => { if (name === "load") after(() => rebuild()); });
});
let stopOpen: (() => void) | null = null;
onBeforeUnmount(() => { stopOpen?.(); ui.map.api = null; ui.cursor = null; map?.setTarget(undefined); map = null; vectors.clear(); });
</script>

<style scoped>
.g3-map { width: 100%; height: 100%; }
</style>
