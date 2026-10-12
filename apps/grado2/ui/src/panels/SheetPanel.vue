<!-- ГРАДО 2 · окно «Макет листа» нового интерфейса: листы проекта и редактор раскладки на Konva (src/sheet/SheetEditor.vue)
     во вкладке dockview рядом с картой. Сверху — список листов (как «Менеджер макетов» QGIS): выбрать, новый, копия,
     удалить, все листы одним PDF; листы — часть проекта (store.js project.layouts, ключ layouts файла): правка листа — правка
     проекта, её держит автосохранение и пишет «Сохранить», как и правки слоёв (project.js). Карта блока — настоящая карта проекта в масштабе блока, «PDF»
     печатает лист тем же рендером, что альбом (sheetmaps.js). Штамп берёт поля альбома (album.meta файла). Новый
     лист пустой (без заготовки): карту рисуют на листе и выбирают ей вид. Листы альбома ППТ КРТ — в том же списке, группой
     «Альбом ППТ КРТ»: открываются картинкой той же печати, что PDF альбома (sheet/AlbumSheetView.vue). Те же листы списком — в окне «Листы и альбом»
     (AlbumPanel.vue): оттуда «Новый лист» и щелчок по листу открывают его здесь (store.js sheetNav). Удаление листа — через диалог Web Awesome.
     Блок карты с видом (#119) следует за рамкой вида: сдвинули или растянули рамку на карте — листы с этим видом
     меняются сами (sheetmaps.js sync); пока окно открыто, рамки видов видны на карте (viewframesmap.js). -->
<template>
  <div class="spn">
    <div class="spn-bar" role="toolbar" aria-label="Листы макета">
      <span class="spn-cap">Лист</span>
      <select class="spn-sel" :value="acur >= 0 ? 'a' + acur : String(cur)" aria-label="Лист макета" @change="pick($event.target.value)">
        <optgroup v-if="albumList.length" label="Листы проекта">
          <option v-for="(s, i) in sheets" :key="s.id" :value="String(i)">{{ i + 1 }}. {{ s.title || 'без названия' }}</option>
        </optgroup>
        <template v-else><option v-for="(s, i) in sheets" :key="s.id" :value="String(i)">{{ i + 1 }}. {{ s.title || 'без названия' }}</option></template>
        <optgroup v-if="albumList.length" label="Альбом ППТ КРТ">
          <option v-for="a in albumList" :key="a.id" :value="'a' + a.i">{{ a.t }}</option>
        </optgroup>
      </select>
      <button class="spn-b" title="Новый пустой лист А3: карту и остальное ставите сами" @click="add()"><FilePlus2 :size="15" :stroke-width="1.7" />Новый</button>
      <button class="spn-b" :disabled="acur >= 0" title="Копия этого листа" @click="add(sheets[cur])"><Copy :size="15" :stroke-width="1.7" />Копия</button>
      <button class="spn-b" :disabled="acur >= 0 || sheets.length < 2" title="Удалить этот лист" @click="askDrop = true"><Trash2 :size="15" :stroke-width="1.7" />Удалить</button>
      <button class="spn-b" title="Все листы по порядку одним PDF, номера листов — в штампе" @click="all"><FileDown :size="15" :stroke-width="1.7" />Все листы в PDF</button>
      <span class="spn-hint" :title="HINT">{{ HINT }}</span>
      <span class="spn-st" :class="state.kind">{{ state.text }}</span>
    </div>
    <wa-dialog label="Удалить лист" :open="askDrop" @wa-after-hide="askDrop = false">
      <p class="spn-q">Удалить лист «{{ sheets[cur]?.title || "без названия" }}»? Лист со всеми его элементами пропадёт из проекта, остальные листы останутся.</p>
      <wa-button slot="footer" size="s" appearance="plain" @click="askDrop = false">Отмена</wa-button>
      <wa-button slot="footer" size="s" variant="danger" @click="drop">Удалить</wa-button>
    </wa-dialog>
    <AlbumSheetView v-if="acur >= 0" :i="acur" class="spn-ed" />
    <SheetEditor v-else :key="sheets[cur].id" v-model="sheets[cur]" :maps="maps" :meta="meta()"
      :page="{ page_no: cur + 1, page_total: sheets.length }" class="spn-ed" />
  </div>
</template>

<script setup>
import { computed, ref, reactive, toRaw, watch, onMounted, onBeforeUnmount } from "vue";
import { FilePlus2, Copy, Trash2, FileDown } from "@lucide/vue";
import SheetEditor from "../sheet/SheetEditor.vue";
import AlbumSheetView from "../sheet/AlbumSheetView.vue";
import { album } from "../albumhost.js";
import { newSheet, newId } from "../sheet/model.js";
import { project, sheetNav } from "../store.js";
import { mapImage, here, legendItems, printPdf, printAll, views, sync, frameTo, frameScale, ownView } from "./sheetmaps.js";
import { ALB, vframes } from "../viewframesmap.js";

const maps = { image: mapImage, here, legend: legendItems, pdf: printPdf, views, sync, frameTo, frameScale, ownView, showFrame: id => { vframes.sel = id; vframes.fit = id; } };
const clone = x => JSON.parse(JSON.stringify(x));
const sheets = ref([]), cur = ref(0), askDrop = ref(false);
/* листы альбома ППТ КРТ — в том же списке (шаг 2 переноса альбома): открываются картинкой той же печати (AlbumSheetView.vue) */
const acur = ref(-1);
const albumList = computed(() => (album.rev, album.sheets, (project.raw?.album?.sheets || []).map((s, i) => {
  const n = `Лист ${i + 1}`; return { id: s.id, i, t: s.title && s.title !== n ? `${n}. ${s.title}` : n };
})));
function pick(v) { if (v.startsWith("a")) acur.value = +v.slice(1); else { acur.value = -1; cur.value = +v; } }
// лист альбома открыли, а его уже нет (пересобрали, удалили) — к листам проекта
watch(() => albumList.value.length, n => { if (acur.value >= n) acur.value = -1; });
const HINT = "Те же листы — в окне «Листы и альбом». Карта листа — рамка вида на карте (окно «Виды»).";
const state = reactive({ kind: "", text: "" });
const meta = () => project.raw?.album?.meta || {};
let mine = null, base = "";             // mine — список листов, который панель сама положила в project.layouts

/* Новый лист — пустой (#119: без заготовок): рамка и штамп, элементы человек ставит сам — карту рисует на листе
   и выбирает ей вид. */
const fresh = title => ({ id: newId("sheet"), ...newSheet({ format: "A3", title, blank: true }) });
function add(from) {
  acur.value = -1;
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
  cur.value = Math.max(0, sheets.value.findIndex(s => s.id === sheetNav.id));   // открыли из «Листов и альбома» — на том листе
  acur.value = -1; navAlbum();
  state.kind = ""; state.text = list.length ? `Листов в проекте: ${list.length}` : "";
  base = JSON.stringify(sheets.value);                // то, что уже в проекте (или нетронутый новый лист): правкой не считать
}
watch(() => project.layouts, l => { if (toRaw(l) !== mine) open(); }, { immediate: true });
// «Листы и альбом»: щелчок по листу или «Новый лист» — этот лист здесь
watch(() => sheetNav.tick, () => { const i = sheets.value.findIndex(s => s.id === sheetNav.id); if (i >= 0) { cur.value = i; acur.value = -1; } else navAlbum(); });
// лист альбома: sheetNav.id = «alb:<id листа>»
function navAlbum() { const id = String(sheetNav.id); if (!id.startsWith(ALB)) return; const a = albumList.value.find(x => x.id === id.slice(ALB.length)); if (a) acur.value = a.i; }
// рамку вида сдвинули или растянули на карте — блоки карты с этим видом встают по ней на всех листах
// и легенды «за видом» — по слоям вида
watch(() => JSON.stringify(project.views), () => sheets.value.forEach(sync));
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
