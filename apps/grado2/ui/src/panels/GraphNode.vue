<!-- ГРАДО 2 · блок схемы расчёта в окне «Схема расчёта» (Rete.js рисует, этот компонент — его вид): заголовок цветом
     вида блока, выходы справа, входы слева, поля блока (список, ползунок, текст, флажок) и строка пояснения снизу.
     Значения полей читаются и пишутся прямо в схему проекта (graph.js), как поля узлов litegraph рабочей страницы. -->
<template>
  <div v-if="n" class="gnode" :class="['k-' + kind, { selected: data.selected }]" :style="{ width: width + 'px' }" data-testid="node">
    <div class="gtitle" :title="title + ' — двойной щелчок: переименовать'" @dblclick.stop="editing = true">
      <input v-if="editing" class="gren" :value="n.title || def.title" @pointerdown.stop @keydown.enter="e => e.target.blur()" @keydown.esc="editing = false"
             @blur="e => { if (editing) renameNode(n.id, e.target.value.trim()); editing = false; }" v-focus>
      <span v-else class="gt">{{ title }}</span>
      <button class="gx" title="Удалить блок (Del)" @pointerdown.stop @click.stop="removeNode(n.id)">×</button>
    </div>
    <div v-for="(o, i) in n.outputs || []" :key="'o' + i" class="gio gout">
      <span>{{ o.name }}</span>
      <Ref class="gsock-out" :emit="emit" :data="{ type: 'socket', side: 'output', key: String(i), nodeId: data.id, payload: data.outputs[String(i)]?.socket }" />
    </div>
    <div v-for="(o, i) in n.inputs || []" :key="'i' + i" class="gio gin">
      <Ref class="gsock-in" :emit="emit" :data="{ type: 'socket', side: 'input', key: String(i), nodeId: data.id, payload: data.inputs[String(i)]?.socket }" />
      <span>{{ o.name }}</span>
    </div>
    <div v-for="(w, i) in widgets" :key="'w' + i" class="gw" @pointerdown.stop @wheel.stop @dblclick.stop>
      <template v-if="w[0] === 'combo'">
        <label :title="w[1]">{{ w[1] }}</label>
        <select :value="val(i)" :title="String(val(i))" @change="e => setWidget(n.id, i, e.target.value)">
          <option v-if="!values(w, i).includes(val(i))" :value="val(i)">{{ val(i) === '' ? '—' : val(i) }}</option>
          <option v-for="v in values(w, i)" :key="v" :value="v">{{ v === '' ? '—' : v }}</option>
        </select>
      </template>
      <template v-else-if="w[0] === 'slider'">
        <label :title="w[1]">{{ w[1] }}</label>
        <input type="range" :min="w[3].min" :max="w[3].max" :step="w[3].precision ? 10 ** -w[3].precision : 1" :value="val(i)" :title="w[1]"
               @input="e => setWidget(n.id, i, +e.target.value)"><b>{{ show(w, i) }}</b>
      </template>
      <template v-else-if="w[0] === 'text'">
        <label :title="w[1]">{{ w[1] }}</label>
        <input type="text" :value="val(i)" :title="w[1]" @change="e => setWidget(n.id, i, e.target.value)">
      </template>
      <label v-else-if="w[0] === 'toggle'" class="gtg"><input type="checkbox" :checked="!!val(i)" @change="e => setWidget(n.id, i, e.target.checked)"> {{ w[1] }}</label>
    </div>
    <div class="ginfo" :title="info">{{ info }}</div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { Ref } from "rete-vue-plugin";
import { fieldsOfTitle, infoOf, layerTitles, nodeById, nodeTitle, removeNode, renameNode, setWidget, tick } from "../graph.js";
import { TYPES } from "../graphfile.js";

const props = defineProps(["data", "emit", "seed"]);
const n = computed(() => { void tick.value; return nodeById(props.data.id); });
const def = computed(() => TYPES[n.value?.type] || { kind: "op", width: 200, widgets: [] });
const kind = computed(() => def.value.kind);
const width = computed(() => { const s = n.value?.size; const w = s ? +(s[0] ?? s["0"]) : 0; return Math.max(def.value.width, w || 0); });
const title = computed(() => n.value ? nodeTitle(n.value) : "");
const info = computed(() => infoOf(props.data.id));
const widgets = computed(() => def.value.widgets);
const val = i => { void tick.value; return n.value?.widgets_values?.[i]; };
const show = (w, i) => { const v = +val(i); return Number.isFinite(v) ? v.toLocaleString("ru-RU", { maximumFractionDigits: w[3].precision || 0 }) : ""; };
function values(w, i) {
  if (Array.isArray(w[3])) return w[3];
  if (n.value?.type === "Данные/Слой" && i === 0) return layerTitles();
  if (n.value?.type === "Данные/Слой" && i === 1) return ["—", ...fieldsOfTitle(val(0))];
  return [];
}
const editing = ref(false);                 // название блока правится прямо в заголовке
const vFocus = { mounted: el => { el.focus(); el.select(); } };
</script>

<style>
.gnode { background: var(--wa-color-surface-default); border: 1px solid var(--wa-color-neutral-border-loud); border-radius: 8px; font-size: 12px; color: var(--wa-color-text-normal);
  box-shadow: 0 1px 3px rgba(0, 0, 0, .12); padding-bottom: 4px; user-select: none; cursor: grab; }
.gnode.selected { outline: 2px solid var(--wa-color-brand-fill-loud); outline-offset: 1px; }
.gnode .gtitle { display: flex; align-items: center; gap: 4px; padding: 4px 8px; border-radius: 7px 7px 0 0; font-weight: 600; min-height: 24px; }
.gnode .gt { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gnode .gren { flex: 1; min-width: 0; font: inherit; padding: 0 3px; border: 1px solid var(--g-line); border-radius: 3px; }
.gnode .gx { border: 0; background: none; cursor: pointer; font-size: 15px; line-height: 1; color: inherit; opacity: .5; padding: 0 2px; }
.gnode .gx:hover { opacity: 1; }
.gnode.k-src .gtitle { background: var(--gk-src); } .gnode.k-op .gtitle { background: var(--gk-op); } .gnode.k-gen .gtitle { background: var(--gk-gen); }
.gnode.k-tep .gtitle { background: var(--gk-tep); } .gnode.k-num .gtitle { background: var(--gk-num); }
.gnode .gio { display: flex; align-items: center; gap: 6px; height: 20px; font-size: 11px; color: var(--g-muted); }
.gnode .gout { justify-content: flex-end; margin-right: -9px; }
.gnode .gin { margin-left: -9px; }
.gnode .gw { display: flex; align-items: center; gap: 6px; height: 22px; padding: 0 8px; font-size: 11px; }
.gnode .gw > label { flex: 0 0 38%; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--g-muted); }
.gnode .gw b { flex: none; min-width: 22px; text-align: right; color: var(--wa-color-text-normal); font-weight: 600; }
.gnode .gw select, .gnode .gw input[type=text] { flex: 1; min-width: 0; font: inherit; font-size: 11px; padding: 1px 3px; border: 1px solid var(--g-line); border-radius: 4px; background: var(--wa-color-surface-default); color: inherit; }
.gnode .gw input[type=range] { flex: 1; min-width: 0; margin: 0; cursor: pointer; }
.gnode .gw > .gtg { flex: 1; display: flex; align-items: center; gap: 6px; cursor: pointer; color: var(--g-muted); white-space: normal; line-height: 1.1; }
.gnode .ginfo { padding: 3px 8px 0; font-size: 11px; color: var(--g-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gsock { width: 14px; height: 14px; border-radius: 50%; border: 2px solid var(--wa-color-surface-default); box-sizing: border-box; cursor: crosshair; background: var(--gl-geom); }
.gsock:hover { transform: scale(1.3); }
.gsock.t-num { background: var(--gl-num); } .gsock.t-sketch { background: var(--gl-sketch); } .gsock.t-tep { background: var(--gl-tep); } .gsock.t-cap { background: var(--gl-cap); }
</style>
