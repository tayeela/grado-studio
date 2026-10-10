<!-- ГРАДО 2 · образец слоя (окно «Слои», шапка «Свойств», легенда «Видов»): рисуется тем же стилем OpenLayers, что и карта
     (symbology.js symbolStyle через ol/render toContext) — заливка с её прозрачностью, штриховка, контур той же толщины, цвета
     и штриха, прозрачность слоя. Категории, диапазоны и правила — до трёх первых классов рядом. Как значок слоя в QGIS. -->
<template>
  <canvas ref="cv" class="lsw" :style="{ opacity: alpha }" :title="title" aria-hidden="true"></canvas>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { toContext } from "ol/render.js";
import LineString from "ol/geom/LineString.js";
import Point from "ol/geom/Point.js";
import Polygon from "ol/geom/Polygon.js";
import { Fill, Stroke, Style, Text } from "ol/style.js";
import { project } from "../store.js";
import { dataRev } from "../edit.js";
import { fullStyle, okn, swatchSymbols, symbolStyle } from "../symbology.js";

const props = defineProps({ l: Object, style: Object, opacity: { type: Number, default: undefined } });
const W = 16, H = 12;
const cv = ref(null);
const st = computed(() => fullStyle(props.style || props.l.style));
const alpha = computed(() => props.opacity ?? okn(props.l.layerOpacity, 1));
const title = computed(() => alpha.value < 1 ? `Прозрачность слоя ${Math.round(alpha.value * 100)} %` : undefined);
// классы категорий зависят от данных слоя (не реактивны: правка — через dataRev)
const syms = computed(() => (st.value.mode === "cat" && dataRev.value, swatchSymbols(st.value, project.data[props.l.key]?.fc)));

function draw() {
  const c = cv.value; if (!c) return;
  const pr = window.devicePixelRatio || 1;
  c.width = W * pr; c.height = H * pr; c.style.width = W + "px"; c.style.height = H + "px";
  const ctx = c.getContext("2d"); ctx.clearRect(0, 0, c.width, c.height);
  const vc = toContext(ctx, { size: [W, H], pixelRatio: pr });
  const s = st.value, g = props.l.geom, list = syms.value.length ? syms.value : [{ fill: s.fill, hatch: false }], n = list.length;
  const put = (style, geom) => { for (const x of [].concat(style)) { vc.setStyle(x); vc.drawGeometry(geom); } };
  if (s.mode === "lgr") return put(new Style({ stroke: new Stroke({ color: "#d7191c", width: 1.5 }) }), new LineString([[1, H / 2], [W - 1, H / 2]]));
  if (g === "point" && s.marker === false)                               // слой подписей без значка: буква цветом подписи
    return put(new Style({ text: new Text({ text: "А", font: "600 11px Onest, system-ui, sans-serif", fill: new Fill({ color: s.labelColor || "#1d1d1f" }) }) }), new Point([W / 2, H / 2 + 0.5]));
  if (g === "point") {                                                    // кружок карты, но не больше образца
    const r = n > 1 ? 2.5 : Math.min(5, 2 + s.width * 2), k = { ...s, width: (r - 2) / 2 };
    return list.forEach((m, i) => put(symbolStyle(k, m, "point"), new Point([n > 1 ? 3 + i * 5 : W / 2, H / 2])));
  }
  if (g === "line") {                                                     // отрезок; у классов — подряд своими цветами
    const k = { ...s, width: Math.min(s.width, 4) };
    return list.forEach((m, i) => put(symbolStyle(k, m, "line"), new LineString([[1 + i * (W - 2) / n, H / 2], [1 + (i + 1) * (W - 2) / n, H / 2]])));
  }
  const w = Math.min(s.width, 3), o = w > 0 ? Math.max(w / 2, 0.5) : 0, k = { ...s, width: w };   // полигон: прямоугольник, контур внутри образца
  list.forEach((m, i) => {
    const x0 = o + i * (W - 2 * o) / n, x1 = o + (i + 1) * (W - 2 * o) / n;
    put(symbolStyle(k, m, "poly"), new Polygon([[[x0, o], [x1, o], [x1, H - o], [x0, H - o], [x0, o]]]));
  });
}

onMounted(draw);
watch(() => [JSON.stringify(st.value), JSON.stringify(syms.value), props.l.geom], draw, { flush: "post" });
</script>

<style>
.lsw { flex: none; display: block; }
</style>
