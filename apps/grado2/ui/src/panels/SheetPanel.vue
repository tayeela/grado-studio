<!-- ГРАДО 2 · окно «Макет листа» нового интерфейса: листы проекта и редактор раскладки на Konva (src/sheet/SheetEditor.vue)
     во вкладке dockview рядом с картой. Сверху — список листов (как «Менеджер макетов» QGIS): выбрать, новый, копия,
     удалить, все листы одним PDF; листы — часть проекта (store.js project.layouts, ключ layouts файла): правка листа — правка
     проекта, её держит автосохранение и пишет «Сохранить», как и правки слоёв (project.js). Карта блока — настоящая карта проекта в масштабе блока, «PDF»
     печатает лист тем же рендером, что альбом (sheetmaps.js). Штамп берёт поля альбома (album.meta файла). Новый
     лист ставит карту туда, где открыт проект, легенду собирает из его слоёв. Это свои листы проекта; альбом ППТ КРТ
     собирается отдельно — кнопкой «Листы и альбом» в шапке (строка-пояснение справа). Удаление листа — через диалог Web Awesome.
     Блок карты с видом (#119) следует за рамкой вида: сдвинули или растянули рамку на карте — листы с этим видом
     меняются сами (sheetmaps.js sync); пока окно открыто, рамки видов видны на карте (viewframesmap.js). -->
<template>
  <div class="spn">
    <div class="spn-bar" role="toolbar" aria-label="Листы макета">
      <span class="spn-cap">Лист</span>
      <select class="spn-sel" :value="cur" aria-label="Лист макета" @change="cur = +$event.target.value">
        <option v-for="(s, i) in sheets" :key="s.id" :value="i">{{ i + 1 }}. {{ s.title || 'без названия' }}</option>
      </select>
      <button class="spn-b" title="Новый лист А3 с картой и легендой" @click="add()"><FilePlus2 :size="15" :stroke-width="1.7" />Новый</button>
      <button class="spn-b" title="Копия этого листа" @click="add(sheets[cur])"><Copy :size="15" :stroke-width="1.7" />Копия</button>
      <button class="spn-b" :disabled="sheets.length < 2" title="Удалить этот лист" @click="askDrop = true"><Trash2 :size="15" :stroke-width="1.7" />Удалить</button>
      <button class="spn-b" title="Все листы по порядку одним PDF, номера листов — в штампе" @click="all"><FileDown :size="15" :stroke-width="1.7" />Все листы в PDF</button>
      <span class="spn-hint" :title="HINT">{{ HINT }}</span>
      <span class="spn-st" :class="state.kind">{{ state.text }}</span>
    </div>
    <wa-dialog label="Удалить лист" :open="askDrop" @wa-after-hide="askDrop = false">
      <p class="spn-q">Удалить лист «{{ sheets[cur]?.title || "без названия" }}»? Лист со всеми его элементами пропадёт из проекта, остальные листы останутся.</p>
      <wa-button slot="footer" size="s" appearance="plain" @click="askDrop = false">Отмена</wa-button>
      <wa-button slot="footer" size="s" variant="danger" @click="drop">Удалить</wa-button>
    </wa-dialog>
    <SheetEditor :key="sheets[cur].id" v-model="sheets[cur]" :maps="maps" :meta="meta()"
      :page="{ page_no: cur + 1, page_total: sheets.length }" class="spn-ed" />
  </div>
</template>

<script setup>
import { ref, reactive, toRaw, watch, onMounted, onBeforeUnmount } from "vue";
import { FilePlus2, Copy, Trash2, FileDown } from "@lucide/vue";
import SheetEditor from "../sheet/SheetEditor.vue";
import { newSheet, newId, LEGEND_SAMPLE } from "../sheet/model.js";
import { project } from "../store.js";
import { mapImage, here, legendItems, printPdf, printAll, views, sync, frameTo } from "./sheetmaps.js";
import { vframes } from "../viewframesmap.js";

const maps = { image: mapImage, here, legend: legendItems, pdf: printPdf, views, sync, frameTo, showFrame: id => { vframes.sel = id; vframes.fit = id; } };
const SAMPLE = JSON.stringify(LEGEND_SAMPLE);
const clone = x => JSON.parse(JSON.stringify(x));
const sheets = ref([]), cur = ref(0), askDrop = ref(false);
const HINT = "Здесь — свои листы проекта. Альбом ППТ КРТ собирается в «Листы и альбом» вверху окна.";
const state = reactive({ kind: "", text: "" });
const meta = () => project.raw?.album?.meta || {};
let mine = null, base = "";             // mine — список листов, который панель сама положила в project.layouts

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
  askDrop.value = false;
  if (sheets.value.length < 2) return;
  sheets.value.splice(cur.value, 1); cur.value = Math.min(cur.value, sheets.value.length - 1);
}

async function all() {
  state.kind = ""; state.text = "PDF собирается…";
  try { await printAll(clone(sheets.value), meta(), project.name || "листы"); state.text = "PDF готов"; }
  catch (e) { state.kind = "warn"; state.text = e.message; }
}

/* Открыт другой проект (или его листы заменены): его листы; листов нет — один новый (в проект он попадёт после первой правки). */
function open() {
  const list = (project.layouts || []).map(s => ({ ...clone(s), id: s.id || newId("sheet") }));
  sheets.value = list.length ? list : [fresh("Новый лист")];
  cur.value = 0;
  state.kind = ""; state.text = list.length ? `Листов в проекте: ${list.length}` : "";
  base = JSON.stringify(sheets.value);                // то, что уже в проекте (или нетронутый новый лист): правкой не считать
}
watch(() => project.layouts, l => { if (toRaw(l) !== mine) open(); }, { immediate: true });
// рамку вида сдвинули или растянули на карте — блоки карты с этим видом встают по ней на всех листах
watch(() => project.views.map(v => [v.id, v.frame]), () => sheets.value.forEach(sync), { deep: true });
onMounted(() => { vframes.on++; });
onBeforeUnmount(() => { vframes.on--; });

/* Любая правка листа — правка проекта: автосохранение держит её, «Сохранить» пишет в файл. */
watch(sheets, () => {
  const j = JSON.stringify(sheets.value);
  if (j === base) return;
  base = j; mine = JSON.parse(j); project.layouts = mine;
  state.kind = ""; state.text = project.name ? "Листы изменены: сохраняются вместе с проектом" : "Листы изменены: сохраните проект";
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
.spn-hint { flex: 1; min-width: 0; margin-left: 8px; color: var(--wa-color-text-quiet, #66707c); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.spn-q { margin: 0; line-height: 1.45; }
.spn-st { color: var(--wa-color-text-quiet, #66707c); font-size: 12px; white-space: nowrap; }
.spn-st.ok { color: var(--wa-color-success-on-quiet, #1a7f37); }
.spn-st.warn { color: var(--wa-color-danger-on-quiet, #b4441b); }
</style>
