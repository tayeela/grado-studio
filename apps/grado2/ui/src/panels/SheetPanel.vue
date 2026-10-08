<!-- ГРАДО 2 · окно «Макет листа» нового интерфейса: листы проекта и редактор раскладки на Konva (src/sheet/SheetEditor.vue)
     во вкладке dockview рядом с картой. Сверху — список листов (как «Менеджер макетов» QGIS): выбрать, новый, копия,
     удалить, все листы одним PDF; листы пишутся в файл проекта (ключ layouts, project.js saveLayouts) через секунду после правки — слои
     и альбом рабочей страницы при этом не меняются. Карта блока — настоящая карта проекта в масштабе блока, «PDF»
     печатает лист тем же рендером, что альбом (sheetmaps.js). Штамп берёт поля альбома (store.js album.meta). Новый
     лист ставит карту туда, где открыт проект, легенду собирает из его слоёв. -->
<template>
  <div class="spn">
    <div class="spn-bar" role="toolbar" aria-label="Листы макета">
      <span class="spn-cap">Лист</span>
      <select class="spn-sel" :value="cur" aria-label="Лист макета" @change="cur = +$event.target.value">
        <option v-for="(s, i) in sheets" :key="s.id" :value="i">{{ i + 1 }}. {{ s.title || 'без названия' }}</option>
      </select>
      <button class="spn-b" title="Новый лист А3 с картой и легендой" @click="add()"><FilePlus2 :size="15" :stroke-width="1.7" />Новый</button>
      <button class="spn-b" title="Копия этого листа" @click="add(sheets[cur])"><Copy :size="15" :stroke-width="1.7" />Копия</button>
      <button class="spn-b" :disabled="sheets.length < 2" title="Удалить этот лист" @click="drop"><Trash2 :size="15" :stroke-width="1.7" />Удалить</button>
      <button class="spn-b" title="Все листы по порядку одним PDF, номера листов — в штампе" @click="all"><FileDown :size="15" :stroke-width="1.7" />Все листы в PDF</button>
      <span class="spn-sp"></span>
      <span class="spn-st" :class="state.kind">{{ state.text }}</span>
    </div>
    <SheetEditor :key="sheets[cur].id" v-model="sheets[cur]" :maps="maps" :meta="project.album?.meta || {}"
      :page="{ page_no: cur + 1, page_total: sheets.length }" class="spn-ed" />
  </div>
</template>

<script setup>
import { ref, reactive, watch } from "vue";
import { FilePlus2, Copy, Trash2, FileDown } from "@lucide/vue";
import SheetEditor from "../sheet/SheetEditor.vue";
import { newSheet, newId, LEGEND_SAMPLE } from "../sheet/model.js";
import { project } from "../store.js";
import { saveLayouts } from "../project.js";
import { mapImage, here, legendItems, printPdf, printAll } from "./sheetmaps.js";

const maps = { image: mapImage, here, legend: legendItems, pdf: printPdf };
const SAMPLE = JSON.stringify(LEGEND_SAMPLE);
const clone = x => JSON.parse(JSON.stringify(x));
const sheets = ref([]), cur = ref(0);
const state = reactive({ kind: "", text: "" });
let loaded = "", base = "", timer = 0, saving = Promise.resolve();

/* Новый лист: карта там, где открыт проект, легенда из его слоёв. */
function fresh(title) {
  const s = { id: newId("sheet"), ...newSheet({ format: "A3", title, center: here()?.center || null }) }, items = legendItems();
  s.blocks.forEach(b => { if (b.kind === "legend" && items.length && JSON.stringify(b.items) === SAMPLE) b.items = items; });
  return s;
}
function add(from) {
  const s = from ? { ...clone(from), id: newId("sheet"), title: `${from.title || "Лист"} (копия)` } : fresh(`Лист ${sheets.value.length + 1}`);
  sheets.value.splice(cur.value + 1, 0, s); cur.value += 1;
}
function drop() {
  if (sheets.value.length < 2 || !confirm(`Удалить лист «${sheets.value[cur.value].title || "без названия"}»?`)) return;
  sheets.value.splice(cur.value, 1); cur.value = Math.min(cur.value, sheets.value.length - 1);
}

async function all() {
  state.kind = ""; state.text = "PDF собирается…";
  try { await printAll(clone(sheets.value), project.album?.meta || {}, project.name || "листы"); state.text = "PDF готов"; }
  catch (e) { state.kind = "warn"; state.text = e.message; }
}

/* Открыт другой проект: его листы; листов нет — один новый (в файл он попадёт после первой правки). */
function open() {
  loaded = project.name + "|" + project.source;
  const list = (project.layouts || []).map(s => ({ ...clone(s), id: s.id || newId("sheet") }));
  sheets.value = list.length ? list : [fresh("Новый лист")];
  cur.value = 0;
  state.kind = ""; state.text = list.length ? `Листов в проекте: ${list.length}` : project.name ? "Лист ещё не сохранён" : "";
  base = JSON.stringify(sheets.value);                // то, что уже в файле (или нетронутый новый лист): не записывать
}
watch(() => project.name + "|" + project.source, k => { if (k !== loaded) open(); }, { immediate: true });

/* Любая правка листа — через секунду в файл проекта; без открытого проекта сохранять некуда. */
watch(sheets, () => {
  const j = JSON.stringify(sheets.value);
  if (j === base) return;
  if (!project.name) { state.kind = "warn"; state.text = "Проект не открыт: лист не сохраняется"; return; }
  clearTimeout(timer); state.kind = ""; state.text = "Изменено…";
  timer = setTimeout(() => {
    const data = clone(sheets.value);
    saving = saving.then(() => saveLayouts(data)).then(() => { base = JSON.stringify(data); project.layouts = data; state.kind = "ok"; state.text = "Сохранено в проект"; },
      e => { state.kind = "warn"; state.text = "Не сохранилось: " + e.message; });
  }, 1000);
}, { deep: true });
</script>

<style scoped>
.spn { display: flex; flex-direction: column; height: 100%; }
.spn-ed { flex: 1; min-height: 0; }
.spn-bar { flex: none; display: flex; align-items: center; gap: 6px; height: 34px; padding: 0 8px; font: 13px/1.3 var(--wa-font-family-body, system-ui), sans-serif;
  color: var(--wa-color-text-normal, #1f2328); background: var(--wa-color-surface-default, #fff); border-bottom: 1px solid var(--wa-color-surface-border, #e3e6ea); }
.spn-cap { color: var(--wa-color-text-quiet, #66707c); }
.spn-sel { font: inherit; color: inherit; background: var(--wa-color-surface-default, #fff); border: 1px solid var(--wa-color-neutral-border-normal, #cfd4da); border-radius: 5px; height: 26px; padding: 0 6px; max-width: 280px; }
.spn-b { display: inline-flex; align-items: center; gap: 4px; font: inherit; color: inherit; background: none; border: 1px solid transparent; border-radius: 5px; height: 26px; padding: 0 8px; cursor: pointer; }
.spn-b:hover:not(:disabled) { background: var(--wa-color-neutral-fill-quiet, #f0f2f5); }
.spn-b:disabled { opacity: .4; cursor: default; }
.spn-sp { flex: 1; }
.spn-st { color: var(--wa-color-text-quiet, #66707c); font-size: 12px; white-space: nowrap; }
.spn-st.ok { color: var(--wa-color-success-on-quiet, #1a7f37); }
.spn-st.warn { color: var(--wa-color-danger-on-quiet, #b4441b); }
</style>
