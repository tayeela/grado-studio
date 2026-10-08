<!-- ГРАДО 2 · окно «Таблица атрибутов» нового интерфейса на Tabulator (карта ядер): объекты текущего слоя, сортировка
     щелчком по заголовку, поиск по всем полям, «только выбранные», правка ячейки двойным щелчком, щелчок по строке —
     выбор и приближение (Shift — добавить к выбору), как web/layers.js renderTable. Тысячи строк — виртуальной прокруткой. -->
<template>
  <div class="pane tbl">
    <div class="bar">
      <span class="t">{{ title }}</span>
      <wa-input size="s" placeholder="Поиск по полям" with-clear :value="q" @input="e => (q = e.target.value)"></wa-input>
      <wa-checkbox size="s" :checked="selOnly" @change="e => (selOnly = e.target.checked)">только выбранные</wa-checkbox>
    </div>
    <div ref="el" class="grid"></div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { TabulatorFull as Tabulator } from "tabulator-tables";
import "tabulator-tables/dist/css/tabulator_simple.min.css";
import { current, project } from "../store.js";
import { dataRev, mapApi } from "../edit.js";
import { featureOf, fieldsOfFeatures, indexOf, sel, setAttr, setSel, toggleSel } from "../features.js";

const el = ref(null), q = ref(""), selOnly = ref(false);
let table = null, ready = false, shownKey = "", shownFc = null, shownCols = "";

const fc = computed(() => (dataRev.value, project.data[current.value?.key]?.fc));
const nSel = computed(() => sel.filter(s => s.key === current.value?.key).length);
const title = computed(() => {
  const l = current.value; if (!l) return "Выберите слой в окне «Слои»";
  const n = fc.value?.features?.length || 0;
  return `${l.title} · ${n.toLocaleString("ru-RU")} об.${nSel.value ? ` · выбрано ${nSel.value}` : ""}`;
});

function rows() {
  const f = fc.value; indexOf(f);
  return (f?.features || []).map((x, i) => ({ ...x.properties, _uid: x.properties._uid, _n: i + 1 + (x.properties._edited ? "*" : "") }));
}
function columns(fields) {
  return [{ title: "№", field: "_n", width: 54, headerSort: false, frozen: true, cssClass: "rn" },
    ...fields.map(k => ({ title: k, field: k, editor: "input", sorter: "alphanum", headerTooltip: k }))];
}

/* Данные слоя заново, когда сменился слой или его fc; выбранные строки — подсветкой без перестройки. */
function refresh() {
  if (!ready) return;
  const key = current.value?.key || "", f = fc.value, fields = fieldsOfFeatures(f?.features || []), cols = fields.join("\u0001");
  if (cols !== shownCols || key !== shownKey) { table.setColumns(columns(fields)); shownCols = cols; }
  if (key !== shownKey || f !== shownFc) { table.replaceData(rows()); shownKey = key; shownFc = f; }
  applyFilter(); mark();
}
function mark() {
  if (!ready) return;
  const want = new Set(sel.filter(s => s.key === current.value?.key).map(s => s.uid));
  table.getRows().forEach(r => r.getElement().classList.toggle("sel", want.has(r.getData()._uid)));
}
function applyFilter() {
  const s = q.value.trim().toLowerCase(), want = new Set(sel.filter(x => x.key === current.value?.key).map(x => x.uid));
  if (!s && !selOnly.value) return table.clearFilter();
  table.setFilter(d => (!selOnly.value || want.has(d._uid)) && (!s || Object.entries(d).some(([k, v]) => k[0] !== "_" && String(v ?? "").toLowerCase().includes(s))));
}

onMounted(() => {
  table = new Tabulator(el.value, {
    height: "100%", layout: "fitDataStretch", editTriggerEvent: "dblclick", nestedFieldSeparator: false, selectableRows: false, columnDefaults: { maxWidth: 360 },
    placeholder: "Нет объектов", data: [], columns: columns([]),
    rowFormatter: r => r.getElement().classList.toggle("sel", sel.some(s => s.key === current.value?.key && s.uid === r.getData()._uid)),
  });
  table.on("tableBuilt", () => { ready = true; refresh(); });
  table.on("rowClick", (e, r) => {
    const key = current.value?.key, uid = r.getData()._uid; if (!key) return;
    if (e.shiftKey || e.metaKey || e.ctrlKey) return toggleSel({ key, uid });
    setSel([{ key, uid }]); mapApi.fitFeature(featureOf(key, uid));
  });
  table.on("cellEdited", c => {
    const key = current.value?.key, k = c.getField(), v = c.getValue();
    if (!key || String(v ?? "") === String(c.getOldValue() ?? "")) return;
    setAttr([{ key, uid: c.getRow().getData()._uid }], k, String(v ?? ""));
  });
});
onBeforeUnmount(() => { ready = false; table?.destroy(); });
watch([() => current.value?.key, fc], refresh);
watch(sel, () => { mark(); if (selOnly.value) applyFilter(); });
watch([q, selOnly], () => ready && applyFilter());
</script>

<style>
.tbl { display: flex; flex-direction: column; padding: 0; }
.tbl .bar { display: flex; gap: var(--wa-space-s); align-items: center; padding: 4px var(--wa-space-s); border-bottom: 1px solid var(--g-line); }
.tbl .bar .t { flex: 1; font-size: var(--wa-font-size-s); color: var(--g-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tbl .bar wa-input, .tbl .bar wa-checkbox { margin: 0 !important; }
.tbl .bar wa-input { width: 180px; }
.tbl .grid { flex: 1; min-height: 0; font-size: var(--wa-font-size-s); }
.tbl .tabulator { background: var(--wa-color-surface-default); border: 0; color: inherit; }
.tbl .tabulator .tabulator-header, .tbl .tabulator .tabulator-header .tabulator-col { background: var(--g-bar); color: var(--g-muted); border-color: var(--g-line); }
.tbl .tabulator .tabulator-tableholder .tabulator-table { background: var(--wa-color-surface-default); color: inherit; }
.tbl .tabulator-row { background: var(--wa-color-surface-default); border-color: var(--g-line); cursor: default; }
.tbl .tabulator-row.tabulator-row-even { background: color-mix(in srgb, var(--g-bar) 50%, var(--wa-color-surface-default)); }
.tbl .tabulator-row:hover { background: var(--wa-color-neutral-fill-quiet) !important; }
.tbl .tabulator-row.sel { background: var(--wa-color-brand-fill-quiet) !important; }
.tbl .tabulator-row .tabulator-cell { border-color: var(--g-line); }
.tbl .tabulator-cell.rn { color: var(--g-muted); font-variant-numeric: tabular-nums; }
.tbl .tabulator .tabulator-placeholder span { color: var(--g-muted); font-size: var(--wa-font-size-s); }
</style>
