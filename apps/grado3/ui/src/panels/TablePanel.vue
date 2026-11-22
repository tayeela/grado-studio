<!-- ГРАДО · окно «Таблица атрибутов» (план 09.11.2026, шаг И3): атрибуты активного слоя, поиск по всем полям,
     сортировка по столбцам, постраничный показ больших слоёв без тормозов, щелчок по строке подсвечивает и вписывает
     объект на карте, двойной щелчок по ячейке правит атрибут через шину команд с отменой Ctrl+Z. -->
<template>
  <div class="g3-panel g3-table">
    <div class="tbar">
      <span class="tt">{{ title }}</span>
      <input v-model="q" class="t-inp" type="search" placeholder="Поиск по полям…" aria-label="Поиск по атрибутам слоя" />
      <span v-if="filtered.length > pageSize" class="pager">
        <button type="button" class="pbtn" :disabled="page <= 0" @click="page--">‹</button>
        <span class="g3-muted">{{ page * pageSize + 1 }}–{{ Math.min((page + 1) * pageSize, filtered.length) }} из {{ filtered.length }}</span>
        <button type="button" class="pbtn" :disabled="(page + 1) * pageSize >= filtered.length" @click="page++">›</button>
      </span>
    </div>

    <div v-if="!layer" class="empty g3-muted">Выберите слой в окне «Слои» — таблица покажет его объекты.</div>
    <div v-else-if="!rows.length" class="empty g3-muted">В слое «{{ layer.title || layer.key }}» нет объектов.</div>
    <div v-else class="twrap">
      <table>
        <thead>
          <tr>
            <th class="rn">№</th>
            <th v-for="col in fields" :key="col" :title="col" @click="toggleSort(col)">
              {{ col }}
              <span v-if="sortCol === col" class="sarr">{{ sortAsc ? "▲" : "▼" }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in pageRows" :key="r.idx" :class="{ sel: ui.selectedFeatureIdx === r.idx }" @click="pickRow(r.idx)">
            <td class="rn">{{ r.idx + 1 }}<span v-if="r.edited" class="ed" title="Объект изменён в проекте">*</span></td>
            <td v-for="col in fields" :key="col" :title="String(r.props[col] ?? '')" @dblclick.stop="startEdit(r.idx, col, r.props[col])">
              <input v-if="editing && editing.idx === r.idx && editing.col === col" ref="editInput" v-model="editVal"
                     class="cell-inp" @keydown.enter.prevent="commitEdit" @keydown.esc.prevent="editing = null" @blur="commitEdit" />
              <span v-else>{{ r.props[col] ?? "" }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { fieldsOf } from "../symbology";
import { useProject } from "../stores/project";
import { useUi } from "../stores/ui";
import { useCommands } from "../stores/commands";

const project = useProject(), ui = useUi(), cmd = useCommands();
const q = ref("");
const sortCol = ref("");
const sortAsc = ref(true);
const page = ref(0);
const pageSize = 200;

const editing = ref<{ idx: number; col: string; oldVal: string } | null>(null);
const editVal = ref("");
const editInput = ref<HTMLInputElement[] | null>(null);

const layer = computed(() => {
  if (ui.selectedLayer) {
    const found = project.layer(ui.selectedLayer);
    if (found) return found;
  }
  return project.layers[0] || null;
});

const fc = computed(() => { void project.dataTick; return layer.value ? project.data(layer.value.key) : null; });
const fields = computed(() => fieldsOf(fc.value));

const rows = computed(() =>
  (fc.value?.features || []).map((f, idx) => ({
    idx,
    props: (f.properties || {}) as Record<string, unknown>,
    edited: Boolean(f.properties?._edited),
  })),
);

const filtered = computed(() => {
  const needle = q.value.trim().toLowerCase();
  let arr = needle
    ? rows.value.filter(r => fields.value.some(k => String(r.props[k] ?? "").toLowerCase().includes(needle)))
    : rows.value.slice();
  if (sortCol.value) {
    const col = sortCol.value, dir = sortAsc.value ? 1 : -1;
    arr.sort((a, b) => {
      const av = a.props[col] ?? "", bv = b.props[col] ?? "";
      const an = Number(av), bn = Number(bv);
      if (av !== "" && bv !== "" && Number.isFinite(an) && Number.isFinite(bn)) return (an - bn) * dir;
      return String(av).localeCompare(String(bv), "ru") * dir;
    });
  }
  return arr;
});

const pageRows = computed(() => filtered.value.slice(page.value * pageSize, (page.value + 1) * pageSize));

const title = computed(() => {
  if (!layer.value) return "Таблица атрибутов";
  const total = rows.value.length;
  const shown = filtered.value.length;
  return `${layer.value.title || layer.value.key} · ${shown === total ? total : `${shown} из ${total}`} об.`;
});

function toggleSort(col: string) {
  if (sortCol.value === col) sortAsc.value = !sortAsc.value;
  else { sortCol.value = col; sortAsc.value = true; }
  page.value = 0;
}

function pickRow(idx: number) {
  ui.selectedFeatureIdx = idx;
  const feat = fc.value?.features?.[idx];
  if (feat?.geometry) ui.map.api?.markFeatures([feat]);
}

function startEdit(idx: number, col: string, cur: unknown) {
  const s = cur == null ? "" : String(cur);
  editing.value = { idx, col, oldVal: s };
  editVal.value = s;
  nextTick(() => {
    const inp = Array.isArray(editInput.value) ? editInput.value[0] : editInput.value;
    inp?.focus();
    inp?.select();
  });
}

function commitEdit() {
  const ed = editing.value;
  editing.value = null;
  if (!ed || !layer.value || editVal.value === ed.oldVal) return;
  cmd.exec("атрибут", [layer.value.key, String(ed.idx), ed.col, editVal.value]);
}

watch([() => layer.value?.key, q], () => { page.value = 0; editing.value = null; });
</script>

<style scoped>
.g3-table { display: flex; flex-direction: column; padding: 0; height: 100%; font-size: 12px; }
.tbar { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-bottom: 1px solid var(--wa-color-neutral-border-quiet); }
.tt { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; font-size: 12px; }
.t-inp { width: 180px; padding: 3px 8px; border: 1px solid var(--wa-color-neutral-border-normal); border-radius: 6px; background: var(--wa-color-surface-default); color: inherit; font: inherit; font-size: 12px; }
.pager { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; }
.pbtn { border: 1px solid var(--wa-color-neutral-border-normal); background: var(--wa-color-surface-default); color: inherit; border-radius: 4px; padding: 1px 6px; cursor: pointer; }
.pbtn:disabled { opacity: 0.4; cursor: default; }
.empty { padding: 20px; text-align: center; }
.twrap { flex: 1; min-height: 0; overflow: auto; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { border-bottom: 1px solid var(--wa-color-neutral-border-quiet); border-right: 1px solid var(--wa-color-neutral-border-quiet); padding: 4px 8px; text-align: left; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
th { position: sticky; top: 0; z-index: 1; background: var(--wa-color-surface-lowered); font-weight: 600; font-size: 11px; cursor: pointer; user-select: none; }
th.rn, td.rn { width: 44px; text-align: right; color: var(--wa-color-text-quiet); font-variant-numeric: tabular-nums; cursor: default; }
tbody tr:hover { background: var(--wa-color-surface-lowered); }
tbody tr.sel { background: var(--wa-color-brand-fill-quiet); }
.sarr { font-size: 9px; margin-left: 3px; }
.ed { color: var(--wa-color-brand-on-quiet); margin-left: 2px; font-weight: 700; }
.cell-inp { width: 100%; box-sizing: border-box; padding: 1px 4px; border: 1px solid var(--wa-color-brand-border-normal); border-radius: 3px; background: var(--wa-color-surface-default); color: inherit; font: inherit; }
</style>
