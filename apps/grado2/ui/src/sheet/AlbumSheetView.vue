<!-- ГРАДО 2 · лист альбома ППТ КРТ в окне «Макет листа» (шаг 2 переноса альбома на общие листы): листы альбома стоят в том же
     списке листов, что и листы макета (SheetPanel.vue), и открываются здесь. Картинка — та же печать, что PDF альбома
     (albumapi preview → /api/print/svg, album_io.build_pptkrt): что на экране, то и на бумаге. Карта листа — рамка на карте,
     общая с рамками видов (viewframesmap.js, id «alb:…»): «Рамка на карте» выбирает её и приближает; сдвиг рамки или масштаб
     за угол — и картинка перерисуется. Надписи листа правит окно «Макет надписей» (AlbumLayout.vue), остальные свойства —
     вкладка «Листы». -->
<template>
  <div class="asv">
    <div class="asv-bar" role="toolbar" aria-label="Лист ППТ КРТ">
      <span class="asv-t" :title="title">{{ title }}</span>
      <button class="asv-b" :disabled="!frame" title="Выбрать рамку листа на карте и приблизить к ней: тянуть внутри — сдвиг, за угол — масштаб" @click="showFrame"><Frame :size="15" :stroke-width="1.7" />Рамка на карте</button>
      <button v-if="sheet?.kind !== 'tep'" class="asv-b" title="Двигать, выравнивать и править надписи листа — окно «Макет надписей»" @click="openLay"><Type :size="15" :stroke-width="1.7" />Надписи</button>
      <button class="asv-b" :disabled="busy" title="PDF только этого листа" @click="pdf"><FileDown :size="15" :stroke-width="1.7" />PDF листа</button>
      <button class="asv-b" title="Слои листа, формат, масштаб, штамп — вкладка «Листы»" @click="props"><SlidersHorizontal :size="15" :stroke-width="1.7" />Свойства</button>
      <span class="asv-st" :class="{ warn: err }">{{ err || (busy ? "Лист рисуется…" : "") }}</span>
    </div>
    <div class="asv-page">
      <img v-if="url" :src="url" :alt="title" class="asv-img" :class="{ dim: busy }">
      <p v-else class="asv-hint">{{ busy ? "Лист рисуется той же печатью, что и PDF…" : err ? "" : "Лист ППТ КРТ" }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { FileDown, Frame, SlidersHorizontal, Type } from "@lucide/vue";
import { album, call } from "../albumhost.js";
import { ALB, vframes } from "../viewframesmap.js";
import { project, winApi } from "../store.js";

const p = defineProps({ i: { type: Number, required: true } });
const sheet = computed(() => (album.rev, project.raw?.album?.sheets?.[p.i] || null));   // раздел album не реактивен: правку отмечает album.rev
const frame = computed(() => (album.frames || []).find(f => f.i === p.i) || null);
const title = computed(() => { const n = `Лист ${p.i + 1}`, t = sheet.value?.title; return t && t !== n ? `${n}. ${t}` : n; });
const url = ref(""), busy = ref(false), err = ref("");

/* картинка листа: та же печать, что PDF; правка листа (рамка, масштаб, надписи) — перерисовать, не чаще раза в секунду */
let timer = 0, seq = 0;
async function draw() {
  const k = ++seq; busy.value = true; err.value = "";
  try {
    const u = await call(a => a.preview(p.i));
    if (k !== seq) { if (u) URL.revokeObjectURL(u); return; }
    if (url.value) URL.revokeObjectURL(url.value);
    url.value = u || "";
  } catch (e) { if (k === seq) err.value = "Лист не нарисовался: " + (e.message || e); }
  finally { if (k === seq) busy.value = false; }
}
const later = () => { clearTimeout(timer); timer = setTimeout(draw, 1000); };
watch(() => p.i, draw, { immediate: true });
watch(() => album.rev, later);
onBeforeUnmount(() => { clearTimeout(timer); seq++; if (url.value) URL.revokeObjectURL(url.value); });

// карта выходит вперёд (вкладка «Карта»), затем рамка выбрана и карта приближена к ней — когда окно карты уже на виду
function showFrame() { const f = frame.value; if (!f) return; album.cur = p.i; vframes.sel = ALB + f.id; winApi.open("map"); setTimeout(() => { vframes.fit = ALB + f.id; }, 150); }
function openLay() { album.lay = p.i; album.layTick++; winApi.open("albumlay"); }
function props() { album.cur = p.i; winApi.open("album"); }
async function pdf() {
  busy.value = true;
  try { await call(a => a.file("pdf", p.i)); } catch (e) { err.value = "PDF не собрался: " + (e.message || e); } finally { busy.value = false; }
}
</script>

<style scoped>
.asv { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.asv-bar { flex: none; display: flex; align-items: center; gap: 6px; height: 34px; padding: 0 8px; font: 13px/1.3 var(--wa-font-family-body, system-ui), sans-serif;
  color: var(--wa-color-text-normal, #1f2328); background: var(--wa-color-surface-default, #fff); border-bottom: 1px solid var(--wa-color-surface-border, #e3e6ea); }
.asv-t { min-width: 0; max-width: 40%; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-right: 6px; }
.asv-b { display: inline-flex; align-items: center; gap: 4px; font: inherit; color: inherit; background: none; border: 1px solid transparent; border-radius: 5px; height: 26px; padding: 0 8px; cursor: pointer; white-space: nowrap; }
.asv-b:hover:not(:disabled) { background: var(--wa-color-neutral-fill-quiet, #f0f2f5); }
.asv-b:disabled { opacity: .4; cursor: default; }
.asv-st { flex: 1; min-width: 0; text-align: right; color: var(--wa-color-text-quiet, #66707c); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.asv-st.warn { color: var(--wa-color-danger-on-quiet, #b4441b); }
.asv-page { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; padding: 16px; background: var(--g-canvas, #e9ecef); overflow: auto; }
.asv-img { max-width: 100%; max-height: 100%; background: #fff; box-shadow: 0 1px 4px rgba(0, 0, 0, .18); transition: opacity .2s; }
.asv-img.dim { opacity: .6; }
.asv-hint { color: var(--wa-color-text-quiet, #66707c); font-size: 13px; }
</style>
