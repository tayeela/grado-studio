<!-- ГРАДО 2 · окно «Объём» нового интерфейса (как окно «Объём» рабочей страницы, web/app.js draw3d): аксонометрия корпусов
     эскиза и сохранённых слоёв эскиза (синие) и сохраняемых зданий (серые) с тенями на земле на выбранную дату и время
     (солнечное), дороги OSM на земле, поворот на 90°. Высота — этажность × высота этажа окна «Ограничения». -->
<template>
  <div class="pane volp">
    <div class="vbar">
      <wa-button aria-label="Повернуть на 90°" size="s" appearance="outlined" title="Повернуть на 90°" @click="rot = (rot + 1) % 4"><RotateCw :size="14" /></wa-button>
      <select v-model.number="day" title="Дата теней" aria-label="Дата теней"><option :value="112">22 апреля</option><option :value="172">22 июня</option><option :value="234">22 августа</option><option :value="356">22 декабря</option></select>
      <input v-model.number="time" type="range" min="6" max="18" step=".25" title="Время, солнечное" aria-label="Время">
      <small>{{ sunInfo }}</small>
    </div>
    <div ref="wrap" class="cwrap">
      <canvas ref="cv"></canvas>
      <div v-if="!project.territory" class="empty"><b>Объёма пока нет</b>Здесь видны корпуса эскиза и сохраняемые здания с тенями. Сначала задайте границу территории (окно «Данные»), затем постройте эскиз в окне «Эскиз».</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RotateCw } from "@lucide/vue";
import * as turf from "@turf/turf";
import { project, shown } from "../store.js";
import { dataRev } from "../edit.js";
import { CONS, INSOL } from "../constraints.js";
import { RESULT, preview, tick } from "../graph.js";
import { centroid, floorsOf, ringsXY, rot as rotP, toXY } from "../geom.js";

const props = defineProps(["params"]);
const MAJOR = new Set(["motorway", "trunk", "primary", "secondary", "tertiary"]);
const cv = ref(null), wrap = ref(null), rot = ref(0), day = ref(112), time = ref(12);
const hhmm = t => `${String(Math.floor(t)).padStart(2, "0")}:${String(Math.round(t % 1 * 60)).padStart(2, "0")}`;
const sunAlt = ref(null);
const sunInfo = computed(() => hhmm(time.value) + (sunAlt.value == null ? "" : ` · солнце ${sunAlt.value > 0 ? Math.round(sunAlt.value * 180 / Math.PI) + "°" : "за горизонтом"}`));

/* аксонометрия: стены, крыши, порядок по глубине; дороги — земля */
function draw() {
  const c = cv.value; if (!c) return;
  const r = wrap.value.getBoundingClientRect(), dpr = devicePixelRatio || 1, TERR = project.territory;
  c.width = Math.max(1, r.width * dpr); c.height = Math.max(1, r.height * dpr); c.style.width = r.width + "px"; c.style.height = r.height + "px";
  const x = c.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, r.width, r.height);
  if (!r.width || !TERR) { sunAlt.value = null; return; }
  const terr = ringsXY(TERR)[0], A = rot.value * Math.PI / 2, C = Math.cos(Math.PI / 6), Sn = Math.sin(Math.PI / 6), R = p => rotP(p, A, [0, 0]);
  // новые — эскиз схемы и принятые слои эскизов (видимые), серые — сохраняемые здания
  const baked = project.layers.filter(l => shown(l) && /^эскиз/.test(project.data[l.key]?.source || "")).flatMap(l => project.data[l.key].fc.features.filter(f => f.properties?.["Этажность"] != null).map(f => ({ f, floors: +f.properties["Этажность"] || 1 })));
  const fh = CONS.floorH;
  const cKey = b => turf.centroid(b.f).geometry.coordinates.map(v => v.toFixed(6)).join(","), bakedAt = new Set(baked.map(cKey));
  const prevSk = (RESULT.sketch || []).filter(b => !bakedAt.has(cKey(b)));          // принятый эскиз не рисуется второй раз из предпросмотра
  const items = [...prevSk.concat(baked).flatMap(b => ringsXY(b.f).map(ring => ({ ring, h: b.floors * fh, c: [222, 232, 246], e: [42, 90, 170] }))),
    ...(RESULT.tep?.kept || []).flatMap(f => ringsXY(f).map(ring => ({ ring, h: floorsOf(f) * fh, c: [214, 210, 202], e: [90, 90, 90] })))];
  const P = (p, z) => { const q = R(p); return [(q[0] - q[1]) * C, -(q[0] + q[1]) * Sn - z]; };
  const all = [...terr.map(p => P(p, 0)), ...items.map(i => P(i.ring[0], i.h))], xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const k = Math.min((r.width - 60) / (Math.max(...xs) - Math.min(...xs) || 1), (r.height - 60) / (Math.max(...ys) - Math.min(...ys) || 1));
  const ox = r.width / 2 - k * (Math.max(...xs) + Math.min(...xs)) / 2, oy = r.height / 2 - k * (Math.max(...ys) + Math.min(...ys)) / 2;
  const T = (p, z = 0) => { const s = P(p, z); return [ox + s[0] * k, oy + s[1] * k]; };
  const poly = (pts, fill, stroke, close = true) => { x.beginPath(); pts.forEach((p, i) => i ? x.lineTo(...p) : x.moveTo(...p)); if (close) x.closePath(); if (fill) { x.fillStyle = fill; x.fill(); } if (stroke) { x.strokeStyle = stroke; x.lineWidth = .7; x.stroke(); } };
  poly(terr.map(p => T(p)), "#f7f6f1", null);
  const roads = project.data["osm.roads"]?.fc.features || [];
  x.lineCap = "round"; roads.forEach(f => { const g = f.geometry; (g?.type === "LineString" ? [g.coordinates] : g?.type === "MultiLineString" ? g.coordinates : []).forEach(line => { x.beginPath(); line.map(toXY).forEach((p, i) => i ? x.lineTo(...T(p)) : x.moveTo(...T(p))); x.strokeStyle = "#d9d4c9"; x.lineWidth = MAJOR.has(f.properties?.["Тип дороги"]) ? 4 : 2; x.stroke(); }); });
  poly(terr.map(p => T(p)), null, "#b3261e");
  // тени на земле для выбранной даты и времени (солнечное время): тень призмы — основание и по четырёхугольнику на каждое ребро;
  // все части одного обхода и одной заливкой по правилу nonzero — наложения не темнеют дважды
  const sun = INSOL.sunAt(turf.centroid(TERR).geometry.coordinates[1], INSOL.declination(day.value), time.value);
  sunAlt.value = sun.alt;
  if (sun.alt > 0) {
    x.fillStyle = "rgba(40,40,60,.22)";
    const sa = q => q.reduce((acc, p, i) => { const n = q[(i + 1) % q.length]; return acc + p[0] * n[1] - n[0] * p[1]; }, 0);
    const add = q => { q = q.map(p => T(p)); if (sa(q) < 0) q.reverse(); q.forEach((p, i) => i ? x.lineTo(...p) : x.moveTo(...p)); x.closePath(); };
    x.beginPath();
    items.forEach(it => { const d = it.h / sun.tan, sh = p => [p[0] - sun.vx * d, p[1] - sun.vy * d]; add(it.ring);
      it.ring.forEach((a, i) => { const b = it.ring[(i + 1) % it.ring.length]; add([a, b, sh(b), sh(a)]); }); });
    x.fill("nonzero");
  }
  items.forEach(i => { i.d = R(centroid(i.ring)).reduce((a, b) => a + b, 0); }); items.sort((a, b) => b.d - a.d);
  for (const it of items) {
    let ring = it.ring; if (ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]) ring = ring.slice(0, -1);
    const sa = ring.reduce((s, p, j) => { const q = ring[(j + 1) % ring.length]; return s + p[0] * q[1] - q[0] * p[1]; }, 0); if (sa < 0) ring = ring.slice().reverse();
    for (let j = 0; j < ring.length; j++) { const a = ring[j], b = ring[(j + 1) % ring.length], ra = R(a), rb = R(b), nx = rb[1] - ra[1], ny = -(rb[0] - ra[0]);
      if (nx + ny < 0) { const lum = nx < ny ? .8 : .66; poly([T(a), T(b), T(b, it.h), T(a, it.h)], `rgb(${it.c.map(v => Math.round(v * lum)).join(",")})`, `rgba(${it.e.join(",")},.6)`); } }
    poly(ring.map(p => T(p, it.h)), `rgb(${it.c.join(",")})`, `rgb(${it.e.join(",")})`);
  }
  x.fillStyle = getComputedStyle(wrap.value).color; x.font = "11px system-ui, sans-serif";
  x.fillText(`Объём: этаж ${fh} м. Серым — сохраняемые здания, тени — на земле, время солнечное.`, 10, r.height - 10);
}
let raf = 0;
const later = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => { if (preview.vol) draw(); }); };

let off = null, ro = null;
onMounted(() => {
  const api = props.params?.api;
  preview.vol = api ? api.isVisible : true;
  off = api?.onDidVisibilityChange?.(e => { preview.vol = e.isVisible; later(); });
  ro = new ResizeObserver(later); ro.observe(wrap.value);
  later();
});
watch([tick, dataRev, rot, day, time, () => CONS.floorH, () => project.territory, () => project.layers.map(l => shown(l))], later);
onBeforeUnmount(() => { off?.dispose?.(); ro?.disconnect(); cancelAnimationFrame(raf); preview.vol = false; });
</script>

<style>
.volp { display: flex; flex-direction: column; padding: 0; }
.volp .vbar { display: flex; align-items: center; gap: 8px; padding: 4px 8px; border-bottom: 1px solid var(--g-line); font-size: var(--wa-font-size-s); }
.volp .vbar select { font: inherit; padding: 1px 4px; border: 1px solid var(--g-line); border-radius: 4px; background: var(--wa-color-surface-default); color: inherit; }
.volp .vbar input[type=range] { width: 130px; accent-color: var(--wa-color-brand-fill-loud); }
.volp .vbar small { color: var(--g-muted); font-size: var(--wa-font-size-xs); font-variant-numeric: tabular-nums; }
.volp .cwrap { flex: 1; position: relative; min-height: 0; color: var(--g-muted); }
.volp canvas { position: absolute; inset: 0; }
.volp .empty { position: absolute; inset: 0; display: flex; flex-direction: column; gap: 6px; align-items: center; justify-content: center; text-align: center; padding: 20px; font-size: var(--wa-font-size-s); }
</style>
