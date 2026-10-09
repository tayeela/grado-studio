<!-- ГРАДО 2 · окно «Сравнение» нового интерфейса (как окно «Сравнение» рабочей страницы): две карты рядом с общим видом
     главной карты — слева существующее положение, справа сохраняемые здания и эскиз (или сохранённый вариант). Слои
     проекта на обеих — как на главной карте (maplayers.js). -->
<template>
  <div class="pane cmpp">
    <div class="cbar">
      <p v-if="!ready" class="hint">Здесь рядом показываются существующее положение и эскиз. Сначала загрузите данные и постройте эскиз.</p>
      <span class="sp"></span>
      <select v-if="saved.length" :value="SV.cmp" aria-label="Что показывать справа" title="Справа: текущий эскиз или сохранённый вариант" @change="e => (SV.cmp = e.target.value)">
        <option value="">Текущий эскиз</option>
        <option v-for="r in saved" :key="r.id" :value="r.id">{{ r.name }}</option>
      </select>
    </div>
    <div class="split">
      <div><div ref="a" class="m"></div><span class="mtag">Существующее</span></div>
      <div><div ref="b" class="m"></div><span class="mtag">{{ rightTag }}</span></div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import Map from "ol/Map.js";
import View from "ol/View.js";
import VectorLayer from "ol/layer/Vector.js";
import VectorSource from "ol/source/Vector.js";
import { fromLonLat } from "ol/proj.js";
import { Fill, Stroke, Style } from "ol/style.js";
import * as turf from "@turf/turf";
import { basemapId, project, theme } from "../store.js";
import { dataRev, mapApi } from "../edit.js";
import { RESULT, preview, tick } from "../graph.js";
import { shade } from "../graphmap.js";
import { basemap, gjFormat, layerSync } from "../maplayers.js";
import { SV, savedList } from "../variants.js";

const props = defineProps(["params"]);
const a = ref(null), b = ref(null);
const saved = computed(() => { void tick.value; return savedList(); });
const ready = computed(() => { void tick.value; return !!(RESULT.sketch?.length && Object.keys(project.data).length); });
const rightTag = computed(() => { const r = SV.cmp && saved.value.find(x => x.id === SV.cmp); return r ? "Вариант: " + r.name : "Эскиз"; });

const terrSrc = new VectorSource(), keptSrc = new VectorSource(), skSrc = new VectorSource();
const terrStyle = new Style({ stroke: new Stroke({ color: "#b3261e", width: 2, lineDash: [12, 4, 2, 4] }) });
const skStyle = f => new Style({ fill: new Fill({ color: shade(f.get("floors")) }), stroke: new Stroke({ color: "#1a4f94", width: 1 }) });
const keptStyle = new Style({ fill: new Fill({ color: "#bdb8b0" }), stroke: new Stroke({ color: "#4d4d4d", width: 1 }) });
const read = gj => { try { return gjFormat.readFeature(gj); } catch { return null; } };
function fill() {
  terrSrc.clear(true); if (project.territory) { const f = read(project.territory); if (f) terrSrc.addFeature(f); }
  keptSrc.clear(true); keptSrc.addFeatures((RESULT.tep?.kept || []).map(read).filter(Boolean));
  const r = SV.cmp && saved.value.find(x => x.id === SV.cmp);
  const list = r ? r.sk.map(q => ({ f: turf.feature(q.g, {}), floors: q.floors })) : RESULT.sketch || [];
  skSrc.clear(true); skSrc.addFeatures(list.map(q => { const f = read(q.f); f?.set("floors", q.floors); return f; }).filter(Boolean));
}

let maps = [], syncs = [], off = null, ro = null;
onMounted(() => {
  const view = mapApi.view || new View({ center: fromLonLat([37.62, 55.75]), zoom: 14 });   // общий вид с главной картой: сдвиг одной двигает все
  const mk = (el, extra) => new Map({ target: el, layers: [basemap(basemapId.value, theme.value), ...extra, new VectorLayer({ source: terrSrc, zIndex: 9999, style: terrStyle })], view, controls: [] });
  maps = [mk(a.value, []), mk(b.value, [new VectorLayer({ source: keptSrc, zIndex: 5001, style: keptStyle }), new VectorLayer({ source: skSrc, zIndex: 5010, style: skStyle })])];
  syncs = maps.map(layerSync); syncs.forEach(s => s.sync()); fill();
  ro = new ResizeObserver(() => maps.forEach(m => m.updateSize())); ro.observe(a.value.parentElement.parentElement);
  const api = props.params?.api;
  preview.cmp = api ? api.isVisible : true;
  off = api?.onDidVisibilityChange?.(e => { preview.cmp = e.isVisible; if (e.isVisible) requestAnimationFrame(() => maps.forEach(m => m.updateSize())); });
});
watch([() => project.layers, () => project.groups, dataRev], () => syncs.forEach(s => s.sync()), { deep: true });
watch(() => project.raw, () => syncs.forEach(s => { s.clear(); s.sync(); }));
watch([tick, () => SV.cmp, () => project.territory], fill);
watch([basemapId, theme], ([id, t]) => maps.forEach(m => m.getLayers().setAt(0, basemap(id, t))));
onBeforeUnmount(() => { off?.dispose?.(); ro?.disconnect(); preview.cmp = false; maps.forEach(m => m.setTarget(undefined)); });
</script>

<style>
.cmpp { display: flex; flex-direction: column; padding: 0; }
.cmpp .cbar { display: flex; align-items: center; gap: 6px; padding: 4px 8px; }
.cmpp .cbar .hint { margin: 0; }
.cmpp .cbar .sp { flex: 1; }
.cmpp .cbar select { font: inherit; font-size: var(--wa-font-size-s); padding: 1px 4px; border: 1px solid var(--g-line); border-radius: 4px; background: var(--wa-color-surface-default); color: inherit; }
.cmpp .split { flex: 1; display: grid; grid-template-columns: 1fr 1fr; gap: 2px; min-height: 0; background: var(--g-line); }
.cmpp .split > div { position: relative; min-width: 0; min-height: 0; }
.cmpp .m { position: absolute; inset: 0; background: var(--g-canvas); }
.cmpp .mtag { position: absolute; left: 8px; top: 8px; background: var(--wa-color-surface-default); border: 1px solid var(--g-line); border-radius: 4px; padding: 1px 6px; font-size: var(--wa-font-size-xs); pointer-events: none; }
</style>
