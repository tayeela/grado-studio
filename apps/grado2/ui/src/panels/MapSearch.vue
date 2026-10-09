<!-- ГРАДО 2 · поиск над картой нового интерфейса — перенос поиска рабочей страницы (web/app.js «поиск над картой»): адрес
     (OpenStreetMap), кадастровый номер (НСПД) или № КРТ (ГИС ОГД), сервер — /api/search. Адрес — метка и кадр;
     участки — «Показать на карте» (в слой «Земельные участки (ЕГРН)» без повторов) и «Сделать границей территории»;
     КРТ — контур, граница и номер в шапку альбома. Чужую границу молча не заменяем: первый щелчок — вопрос на месте,
     второй за 5 с — замена. Запрос уходит по Enter или кнопке; правка запроса сбрасывает список; Ctrl+F — в поле поиска. -->
<template>
  <div ref="box" class="msearch" role="search">
    <div class="msf">
      <input ref="inp" v-model="q" type="text" placeholder="Адрес, кадастровый номер или № КРТ" autocomplete="off" spellcheck="false"
        aria-label="Поиск по адресу, кадастровому номеру или номеру КРТ" aria-controls="sres" :aria-busy="pend || null"
        @keydown="onKey" @input="onInput">
      <button :disabled="pend" title="Найти (Enter)" aria-label="Найти" @click="run"><Search :size="15" /></button>
    </div>
    <div v-if="msg || R" id="sres" class="sres" role="listbox">
      <div v-if="msg" class="srm" :class="{ bad: msgBad }" role="status">{{ msg }}</div>
      <template v-else>
        <div v-for="(x, i) in R.list" :key="i" class="sri" :class="{ act: i === act }" role="option" :aria-selected="i === act" @click="pick(i)">
          <template v-if="R.type === 'krt'"><b>{{ R.cards[i] || "" }}</b></template>
          <template v-else-if="R.type === 'address'"><b>{{ x.name || x.display }}</b><span v-if="x.name && x.display">{{ x.display }}</span></template>
          <template v-else><b>{{ x.properties?.["Кадастровый номер"] || x.properties?._key || "" }}</b><span>{{ haOf(x) }}{{ x.properties?.["ВРИ"] ? " · " + x.properties["ВРИ"] : "" }}</span></template>
        </div>
        <div v-if="R.missing?.length" class="srm bad">Не найдено: {{ R.missing.join(", ") }}</div>
        <div v-for="n in notes" :key="n" class="srm">{{ n }}</div>
        <div v-if="R.type !== 'address' && R.list.length" class="sra">
          <wa-button size="s" @click="show">Показать на карте</wa-button>
          <wa-button size="s" @click="terr">{{ ask ? (R.type === "krt" ? "Заменить вашу границу контуром КРТ?" : "Заменить вашу границу участками?") : "Сделать границей территории" }}</wa-button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { Search } from "@lucide/vue";
import Feature from "ol/Feature.js";
import Point from "ol/geom/Point.js";
import VectorLayer from "ol/layer/Vector.js";
import VectorSource from "ol/source/Vector.js";
import { createEmpty, extend } from "ol/extent.js";
import { fromLonLat, transformExtent } from "ol/proj.js";
import { Circle as CircleStyle, Fill, Stroke, Style } from "ol/style.js";
import { project } from "../store.js";
import { addParcels, setTerritory, terrArea, unionAll } from "../data.js";
import { sizeOf } from "../features.js";
import { gjFormat } from "../maplayers.js";
import { markDirty, notice } from "../project.js";

const props = defineProps({ map: { type: Object, required: true } });
const fmt = (v, d = 0) => Number(v).toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d });
const plural = (n, [one, few, many]) => { const a = n % 10, b = n % 100; return `${n} ${a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many}`; };
const haOf = f => { const a = (sizeOf(f)[1] || 0) / 1e4; return fmt(a, a < 1 ? 4 : 2) + " га"; };
const srchErr = e => { const m = String(e?.message || e);
  return /busy/i.test(m) ? "Поиск занят другим запросом — повторите через минуту"
    : /KRT/i.test(m) ? "Слой КРТ портала ГИС ОГД не получен — повторите позже"
    : /NSPD/i.test(m) ? "Портал НСПД не ответил — повторите позже"
    : /Nominatim/i.test(m) ? "Сервис адресов OpenStreetMap не ответил — повторите позже"
    : /no valid cadastral/i.test(m) ? "Не похоже на кадастровый номер. Пример: 50:27:0000000:126"
    : /Failed to fetch|NetworkError|Load failed/i.test(m) ? "Нет связи с программой ГРАДО — повторите" : "Поиск не удался — повторите позже"; };

const q = ref(""), R = ref(null), act = ref(-1), pend = ref(false), msg = ref(""), msgBad = ref(false), ask = ref(false);
const inp = ref(null), box = ref(null);
const notes = computed(() => (R.value?.notes || []).filter(n => !/^Ничего не найдено/.test(n)));
let tok = 0, ctl = null, tAsk = null;

/* метка найденного: точка адреса или контур участка, синим поверх слоёв */
const mk = new VectorSource();
const mkLayer = new VectorLayer({ source: mk, zIndex: 120, style: f => f.getGeometry().getType() === "Point"
  ? [new Style({ image: new CircleStyle({ radius: 9, stroke: new Stroke({ color: "#1a5fb4", width: 2 }), fill: new Fill({ color: "rgba(26,95,180,.12)" }) }) }),
     new Style({ image: new CircleStyle({ radius: 2.5, fill: new Fill({ color: "#1a5fb4" }) }) })]
  : new Style({ stroke: new Stroke({ color: "#1a5fb4", width: 2.5 }), fill: new Fill({ color: "rgba(26,95,180,.10)" }) }) });
const view = () => props.map.getView();
const dur = () => matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 250;
const fitExt = ext => view().fit(ext, { padding: [60, 60, 60, 60], maxZoom: 18, duration: dur() });
const toOl = f => gjFormat.readFeature(f);
const extOf = list => { const ex = createEmpty(); list.forEach(f => extend(ex, toOl(f).getGeometry().getExtent())); return ex; };

const say = (t, bad = false) => { msg.value = t; msgBad.value = bad; R.value = null; act.value = -1; };
const untAsk = () => { clearTimeout(tAsk); tAsk = null; ask.value = false; };
function close() {
  tok++; ctl?.abort(); ctl = null; untAsk();
  msg.value = ""; R.value = null; act.value = -1; mk.clear(); pend.value = false;
}
function pick(i) {
  const x = R.value?.list[i]; if (!x) return; mk.clear();
  if (R.value.type === "address") {
    const [w, s, e, n] = x.bbox || [x.lon, x.lat, x.lon, x.lat], c = fromLonLat([x.lon, x.lat]);
    mk.addFeature(new Feature(new Point(c)));
    if (w === e || s === n) view().animate({ center: c, zoom: 17, duration: dur() }); else fitExt(transformExtent([w, s, e, n], "EPSG:4326", "EPSG:3857"));
  } else { const f = toOl(x); mk.addFeature(f); fitExt(f.getGeometry().getExtent()); }
}
async function run() {
  const text = q.value.trim(); if (!text) return;
  ctl?.abort(); ctl = new AbortController(); const sig = ctl.signal, my = ++tok;
  mk.clear(); untAsk(); pend.value = true; say("Ищу…");
  try {
    const res = await fetch("/api/search?q=" + encodeURIComponent(text), { signal: sig }), r = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(r.error || String(res.status));
    if (my !== tok || sig.aborted) return;
    msg.value = "";
    if (r.type === "krt") {
      const v = { type: "krt", list: r.features || [], cards: r.cards || [], missing: r.missing || [], notes: r.notes || [] };
      if (!v.list.length) return say(`Номер ${v.missing[0] || ""} не найден в слое «Комплексное развитие территорий»`, true);
      R.value = v;
    } else if (r.type === "cadastral") {
      const v = { type: "cadastral", list: r.features || [], missing: r.missing || [], notes: r.notes || [] };
      if (!v.list.length && !v.missing.length) return say(v.notes[0] || "Ничего не нашлось", true);
      R.value = v;
    } else {
      const list = r.results || []; if (!list.length) return say("Ничего не нашлось в Москве и области");
      R.value = { type: "address", list, notes: r.notes || [] };
    }
    act.value = -1;
  } catch (e) { if (my === tok && e.name !== "AbortError") say(srchErr(e), true); }
  finally { if (my === tok) { ctl = null; pend.value = false; } }
}
/* граница по найденным участкам — объединение участков, как «По участкам» окна «Данные» */
function parcelsToTerritory(feats) {
  const polys = feats.filter(f => /Polygon/.test(f.geometry?.type)); if (!polys.length) { notice.value = "У найденных участков нет контура — граница не изменена"; return false; }
  const u = unionAll(polys); if (!u) { notice.value = "Участки не объединились — граница не изменена"; return false; }
  addParcels(polys); setTerritory(u); notice.value = `Граница по участкам: ${plural(polys.length, ["участок", "участка", "участков"])}, ${fmt(terrArea() / 1e4, 2)} га`; return true;
}
function terr() {
  const r = R.value; if (!r) return; mk.clear();
  if (project.territory && !ask.value) { ask.value = true; tAsk = setTimeout(untAsk, 5000); return; }
  untAsk();
  if (r.type === "krt") {
    const g = r.list[0]; if (!/Polygon/.test(g?.geometry?.type)) { notice.value = "У найденной КРТ нет контура — граница не изменена"; return; }
    setTerritory(g);
    // номер КРТ — в шапку альбома, если владелец его не вписал сам (meta.auto — заполнено программой)
    const num = g.properties?.num_krt, m = project.raw?.album?.meta;
    if (num != null && m && (!m.short || m.auto?.short)) { m.short = `№ ${Math.round(+num) || num}`; m.auto = { ...(m.auto || {}), short: true }; markDirty(); }
    notice.value = `Граница — контур ${(r.cards[0] || "КРТ").split(" · ")[0]}: ${fmt(terrArea() / 1e4, 2)} га`; close(); return;
  }
  if (parcelsToTerritory(r.list)) close();
}
function show() {
  const r = R.value; if (!r) return; mk.clear(); untAsk();
  if (r.type === "krt") { mk.addFeatures(r.list.map(toOl)); fitExt(extOf(r.list)); return; }
  addParcels(r.list); fitExt(extOf(r.list));
  notice.value = `На карте: ${plural(r.list.length, ["участок", "участка", "участков"])} в слое «${project.data["nspd.parcels"]?.title || "Земельные участки (ЕГРН)"}»`;
}
function setAct(i) {
  const n = R.value?.list.length; if (!n) return;
  act.value = (i + n) % n;
  nextTick(() => box.value?.querySelectorAll(".sri")[act.value]?.scrollIntoView({ block: "nearest" }));
}
function onKey(e) {
  if (e.isComposing) return;
  if (e.key === "Enter") { e.preventDefault(); if (act.value >= 0 && R.value) pick(act.value); else run(); }
  else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    if (R.value?.list.length) { e.preventDefault(); setAct(act.value < 0 ? (e.key === "ArrowDown" ? 0 : -1) : act.value + (e.key === "ArrowDown" ? 1 : -1)); }
  } else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); q.value = ""; close(); inp.value.blur(); }
}
const onInput = () => { if (R.value || msg.value || pend.value) close(); };    // правка запроса сбрасывает устаревший список
const onDown = e => { if ((R.value || msg.value) && !box.value?.contains(e.target)) close(); };
/* Ctrl+F — в поле поиска, если оно на виду и фокус не в другом поле ввода (фильтр таблицы и другие — свои) */
const onFind = e => {
  if (!(e.ctrlKey || e.metaKey) || e.shiftKey || e.altKey || e.code !== "KeyF" || !inp.value?.offsetParent) return;
  if (e.composedPath().some(n => n !== inp.value && n instanceof HTMLElement && n.matches("input, textarea, select, [contenteditable], wa-input, wa-textarea"))) return;
  e.preventDefault(); e.stopImmediatePropagation(); inp.value.focus(); inp.value.select();
};
onMounted(() => { props.map.addLayer(mkLayer); addEventListener("pointerdown", onDown, true); addEventListener("keydown", onFind, true); });
onBeforeUnmount(() => { close(); props.map.removeLayer(mkLayer); removeEventListener("pointerdown", onDown, true); removeEventListener("keydown", onFind, true); });
</script>

<style>
.msearch { position: absolute; left: 8px; top: 8px; z-index: 5; width: min(340px, calc(100% - 120px)); min-width: 190px; font: var(--wa-font-size-s)/1.35 system-ui, sans-serif; }
.msearch .msf { display: flex; background: var(--wa-color-surface-raised); border: 1px solid var(--g-line); border-radius: 6px; box-shadow: var(--wa-shadow-s); }
.msearch .msf:focus-within { border-color: var(--wa-color-brand-border-loud); }
.msearch input { flex: 1; min-width: 0; border: 0; background: none; padding: 6px 9px; font: inherit; color: var(--wa-color-text-normal); outline: none; }
.msearch .msf button { border: 0; background: none; padding: 0 9px; color: var(--g-muted); cursor: pointer; display: inline-flex; align-items: center; }
.msearch .msf button:hover:not(:disabled) { color: var(--wa-color-text-normal); }
.msearch .sres { margin-top: 2px; background: var(--wa-color-surface-raised); border: 1px solid var(--g-line); border-radius: 6px; box-shadow: var(--wa-shadow-m);
  max-height: min(60vh, 380px); overflow: auto; padding: 3px 0; }
.msearch .sri { display: block; padding: 5px 10px; cursor: pointer; }
.msearch .sri:hover, .msearch .sri.act { background: var(--wa-color-neutral-fill-quiet); }
.msearch .sri b { display: block; font-weight: 600; color: var(--wa-color-text-normal); }
.msearch .sri span, .msearch .srm { display: block; color: var(--g-muted); }
.msearch .srm { padding: 5px 10px; }
.msearch .srm.bad { color: var(--wa-color-danger-on-quiet); }
.msearch .sra { display: flex; flex-wrap: wrap; gap: 6px; padding: 6px 10px 4px; border-top: 1px solid var(--g-line); margin-top: 3px; }
</style>
