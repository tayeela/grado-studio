<!-- ГРАДО 2 · окно «Эскиз» нового интерфейса (как окно «Эскиз» рабочей страницы, web/app.js renderParams): «Построить эскиз»
     и «Остановить», «Сохранить слоем», «Проверить нормы», типология и параметры блоков схемы, вынесенные в окно.
     Правка здесь меняет схему расчёта, и наоборот (sketch.js, graph.js). Пока окно на виду, эскиз виден на карте. -->
<template>
  <div class="pane sketchp">
    <p v-if="!pn" class="hint">В схеме расчёта нет блока «Посадка застройки».</p>
    <template v-else>
      <div class="row">
        <wa-button v-if="on" size="s" appearance="outlined" title="Остановить пересчёт посадки: правка параметров перестанет перестраивать эскиз" @click="setRun(false)"><Pause :size="14" /> Остановить</wa-button>
        <wa-button v-else size="s" variant="brand" title="Разместить корпуса на пятне застройки по заданной типологии" @click="setRun(true)"><Play :size="14" /> Построить эскиз</wa-button>
        <wa-button size="s" appearance="outlined" :disabled="!n" title="Сделать эскиз обычным слоем проекта: править, стилизовать, выгружать" @click="bakeSketch()"><Stamp :size="14" /> Сохранить слоем</wa-button>
      </div>
      <p v-if="on" class="hint">Эскиз перестраивается при каждой правке ниже. {{ low ? "Домов" : "Корпусов" }}: {{ n }}.<template v-if="dropped"> Цель набрана и без {{ plural(dropped, ["корпуса", "корпусов", "корпусов"]) }} под низкой предельной высотой — на их месте пятна «свет соседям» (жёлтые): там нужен свет соседям.</template><template v-if="goalNote"> {{ goalNote }}.</template> Пока эскиз не сохранён, он виден только при открытых окнах схемы расчёта и эскиза.</p>
      <p v-else-if="project.territory" class="hint">Выберите типологию и параметры, затем «Построить эскиз»: корпуса сами не появляются. Пока окно открыто, на карте виден предварительный просмотр — пятно застройки и сохраняемые здания; «Сохранить слоем» сохраняет построенный эскиз слоем.</p>
      <p v-else class="hint"><b class="warnt">Нет границы территории.</b> Эскиз строится только внутри неё: задайте границу в окне «Данные».</p>
      <div class="row">
        <template v-if="SV.ask === 'sk'">
          <input v-model="SV.val" v-focus type="text" maxlength="60" aria-label="Название варианта" placeholder="Название варианта" @keydown.enter.prevent="svCommit" @keydown.esc.prevent="SV.ask = ''">
          <wa-button size="s" variant="brand" @click="svCommit">Сохранить</wa-button><wa-button size="s" appearance="outlined" @click="SV.ask = ''">Отмена</wa-button>
        </template>
        <wa-button v-else size="s" appearance="outlined" :disabled="!svN" title="Запомнить текущий эскиз с показателями под своим названием: он появится в окне «Варианты», группа «Сохранённые»" @click="svAsk('sk')"><BookmarkPlus :size="14" /> Сохранить как вариант…</wa-button>
      </div>
      <p v-if="savedN" class="hint">Сохранённых вариантов: {{ savedN }} (окно «Варианты»)</p>
      <p v-for="(x, i) in resNotes" :key="'r' + i" class="warn">{{ x }}</p>
      <div class="row">
        <wa-button size="s" appearance="outlined" :disabled="!n || !!CONS.running" :loading="CONS.running === 'Проверка норм…'"
                   title="Инсоляция новых домов и соседей, корпуса на запретах, разрывы между корпусами — слой «Проверка норм» с причиной у каждой точки"
                   @click="check"><ShieldCheck :size="14" /> Проверить нормы</wa-button>
      </div>
      <p v-if="CHECK.last" class="hint">{{ CHECK.last.text }}; новые дома — норму получают {{ CHECK.last.own }} % фасадов; соседи, потерявшие норму: {{ CHECK.last.lost }}</p>
      <div v-for="c in controls" :key="c.id + c.name" class="ctl">
        <template v-if="c.type === 'seg'">
          <div class="t">{{ c.label }}</div>
          <div class="seg">
            <wa-button v-for="o in c.opts" :key="o" size="s" :appearance="val(c) === o ? 'accent' : 'outlined'" :variant="val(c) === o ? 'brand' : 'neutral'"
                       :aria-pressed="String(val(c) === o)" :title="o" @click="setControl(c, o)">{{ o }}</wa-button>
          </div>
        </template>
        <wa-checkbox v-else-if="c.type === 'toggle'" size="s" :checked="!!val(c)" @change="e => setControl(c, e.target.checked)">{{ c.label }}</wa-checkbox>
        <template v-else>
          <div class="t"><span>{{ c.label }}</span><b>{{ fmt(val(c), c.step < 1 ? 2 : 0) }}</b></div>
          <input type="range" :min="c.min" :max="c.max" :step="c.step" :value="Number(val(c))" :aria-label="c.label"
                 :title="`${c.label}: от ${fmt(c.min, c.step < 1 ? 2 : 0)} до ${fmt(c.max, c.step < 1 ? 2 : 0)}; эскиз перестраивается сразу`"
                 @input="e => setControl(c, +e.target.value)">
        </template>
        <small v-if="c.hint">{{ c.hint }}</small>
      </div>
      <p class="hint">Параметры блоков схемы, вынесенные в окно: правка здесь меняет схему, и наоборот.</p>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted } from "vue";
import { BookmarkPlus, Pause, Play, ShieldCheck, Stamp } from "@lucide/vue";
import { project } from "../store.js";
import { CHECK, CONS, runCheck } from "../constraints.js";
import { LOWRISE } from "../graphfile.js";
import { RESULT, nodeById, preview, tick } from "../graph.js";
import { bakeSketch, publishedControls, reserveState, setControl, setRun, wv } from "../sketch.js";
import { fmt, plural } from "../geom.js";
import { SV, savedList, svAsk, svCommit, svCurrent } from "../variants.js";

const props = defineProps(["params"]);
const pn = computed(() => { void tick.value; return RESULT.placeNode; });
const on = computed(() => { void tick.value; return !!pn.value?.properties?.run; });
const n = computed(() => { void tick.value; return RESULT.sketch?.length || 0; });
const low = computed(() => { void tick.value; return pn.value ? LOWRISE.has(wv(pn.value, "типология")) : false; });
const dropped = computed(() => { void tick.value; return RESULT.sketch?.dropped || 0; });
const goalNote = computed(() => { void tick.value; const g = RESULT.sketch?.goal; return g && /не достигнута/.test(g) ? g[0].toUpperCase() + g.slice(1) : ""; });
const resNotes = computed(() => { void tick.value; return reserveState().notes; });
const controls = computed(() => { void tick.value; return publishedControls(); });
const val = c => { void tick.value; return wv(nodeById(c.id), c.name); };
const svN = computed(() => svCurrent().sk.length);
const savedN = computed(() => { void tick.value; return savedList().length; });
const vFocus = { mounted: el => { el.focus(); el.select(); } };
const check = () => runCheck(RESULT.sketch.map(b => ({ f: b.f, floors: b.floors, grp: b.grp || null })));

let off = null;
onMounted(() => {
  const api = props.params?.api;
  preview.sketch = api ? api.isVisible : true;
  off = api?.onDidVisibilityChange?.(e => { preview.sketch = e.isVisible; });
});
onBeforeUnmount(() => { off?.dispose?.(); preview.sketch = false; });
</script>

<style>
.sketchp .row { display: flex; gap: 6px; flex-wrap: wrap; margin: 2px 0 4px; }
.sketchp .row wa-button::part(base) { gap: 4px; width: 100%; }
.sketchp .row > wa-button { flex: 1 1 140px; min-width: 0; }   /* кнопки действий — ровными колонками на всю ширину окна */
.sketchp .row input[type=text] { flex: 1; min-width: 120px; font: inherit; font-size: var(--wa-font-size-s); padding: 2px 6px; border: 1px solid var(--g-line); border-radius: 4px; background: var(--wa-color-surface-default); color: inherit; }
.sketchp .warn { color: var(--wa-color-warning-on-quiet); font-size: var(--wa-font-size-xs); margin: 2px 0; }
.sketchp .warnt { color: var(--wa-color-warning-on-quiet); }
.sketchp .ctl { margin: var(--wa-space-s) 0; font-size: var(--wa-font-size-s); }
.sketchp .ctl .t { display: flex; justify-content: space-between; gap: 8px; margin-bottom: 3px; }
.sketchp .ctl .t b { font-variant-numeric: tabular-nums; }
.sketchp .ctl input[type=range] { width: 100%; margin: 0; cursor: pointer; accent-color: var(--wa-color-brand-fill-loud); }
.sketchp .ctl small { display: block; color: var(--g-muted); font-size: var(--wa-font-size-xs); line-height: 1.3; margin-top: 2px; }
.sketchp .seg { display: flex; flex-wrap: wrap; gap: 3px; }
.sketchp .seg wa-button { margin: 0 !important; }
.sketchp wa-checkbox { display: block; }
</style>
