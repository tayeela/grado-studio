<!-- ГРАДО 2 · знак одного класса в окне «Свойства» (PropsPanel.vue): категория или правило получает полный знак, а не только
     цвет заливки (Марат 08.11.2026): прозрачность заливки, штриховка (узор, шаг, свой цвет — тогда заливка под ней остаётся),
     цвет, толщина и тип контура, подпись (поле, кегль, цвет), свои слои знака (SymbolParts.vue). Пустое поле — «как у слоя». Поля пишутся в объект o:
     у категории — st.cat.sym[значение], у правила — само правило (symbology.js SYM_KEYS, cleanSym, classStyle). -->
<template>
  <div class="csym">
    <div class="f" v-if="geom === 'poly'">
      <span>Заливка</span>
      <div class="fc">
        <span class="sl" title="Непрозрачность заливки класса">
          <wa-slider size="s" min="0" max="100" aria-label="Непрозрачность заливки класса" :value="Math.round(e.opacity * 100)" @input="ev => (o.opacity = num(ev, 70) / 100)"></wa-slider>
          <span class="u v">{{ Math.round(e.opacity * 100) }} %</span>
        </span>
      </div>
    </div>
    <template v-if="geom === 'poly'">
      <label class="f">
        <span>Штриховка</span>
        <wa-select size="s" :value="hatchKey" @change="ev => setHatch(ev.target.value)">
          <wa-option v-if="!rule" value="layer">как у слоя</wa-option>
          <wa-option value="none">нет</wa-option>
          <wa-option v-for="(t, k) in HATCHES" :key="k" :value="k">{{ t }}</wa-option>
        </wa-select>
      </label>
      <div class="f" v-if="hatched">
        <span>Узор</span>
        <div class="fc">
          <wa-color-picker size="s" aria-label="Цвет штриховки" :value="o.hatchColor || fill" @change="ev => (o.hatchColor = ev.target.value)"></wa-color-picker>
          <wa-number-input size="s" class="num" aria-label="Шаг штриховки, пикс." :value="e.hatchStep || 8" min="4" max="40" @change="ev => (o.hatchStep = num(ev, 8))"></wa-number-input>
          <span class="u">пикс.</span>
        </div>
      </div>
    </template>
    <div class="f" v-if="geom !== 'line'">
      <span>Контур</span>
      <div class="fc">
        <wa-color-picker size="s" aria-label="Цвет контура класса" :value="edge" @change="ev => (o.stroke = ev.target.value)"></wa-color-picker>
        <template v-if="geom === 'poly'">
          <wa-number-input size="s" class="num" aria-label="Толщина контура класса, пикс." :value="e.width" step="0.1" min="0" max="10" @change="ev => (o.width = num(ev, 1))"></wa-number-input>
          <span class="u">пикс.</span>
        </template>
      </div>
    </div>
    <label class="f" v-if="geom !== 'poly'">
      <span>{{ geom === 'point' ? 'Размер' : 'Толщина' }}</span>
      <div class="fc">
        <wa-number-input size="s" class="num" :value="e.width" step="0.1" min="0.3" max="10" @change="ev => (o.width = num(ev, 1))"></wa-number-input>
        <span class="u">пикс.</span>
      </div>
    </label>
    <label class="f" v-if="geom !== 'point'">
      <span>Линия</span>
      <wa-select size="s" :value="dashKey" @change="ev => setDash(ev.target.value)">
        <wa-option value="layer">как у слоя</wa-option>
        <wa-option v-for="(t, k) in DASHES" :key="k" :value="k">{{ t }}</wa-option>
      </wa-select>
    </label>
    <label class="f">
      <span>Подпись</span>
      <wa-select size="s" :value="labelKey" @change="ev => setLabel(ev.target.value)">
        <wa-option value="layer">как у слоя{{ st.label ? ": " + st.label : ": нет" }}</wa-option>
        <wa-option value="-">без подписи</wa-option>
        <wa-option v-for="k in fields" :key="k" :value="'f:' + k">{{ k }}</wa-option>
      </wa-select>
    </label>
    <div class="f" v-if="e.label">
      <span>Шрифт</span>
      <div class="fc">
        <wa-color-picker size="s" aria-label="Цвет подписи класса" :value="e.labelColor || '#1d1d1f'" @change="ev => (o.labelColor = ev.target.value)"></wa-color-picker>
        <wa-number-input size="s" class="num" aria-label="Кегль подписи класса, пт" :value="e.labelSize" min="7" max="24" @change="ev => (o.labelSize = num(ev, 11))"></wa-number-input>
        <span class="u">пт</span>
      </div>
    </div>
    <template v-if="geom !== 'point'">
      <div class="f"><span>Слои знака</span><span class="u">{{ o.parts ? "свои у класса" : "как у слоя" }}</span></div>
      <SymbolParts :o="o" :geom="geom" />
    </template>
    <wa-button v-if="own" size="s" appearance="plain" class="reset" title="Убрать свой знак класса: всё, кроме заливки, — как у слоя" @click="reset">Как у слоя</wa-button>
  </div>
</template>

<script setup>
import { computed } from "vue";
import SymbolParts from "./SymbolParts.vue";
import { DASHES, HATCHES, SYM_KEYS, classStyle, edgeColor, hasOwnSym, okn } from "../symbology.js";

const props = defineProps({ st: Object, o: Object, fill: String, geom: String, fields: Array, rule: Boolean });
const num = (ev, d) => okn(ev.target.value, d);
const e = computed(() => classStyle(props.st, props.o));
/* штриховка: у правила — своя (нет или узор), у категории — своя или как у слоя */
const hatched = computed(() => props.rule ? !!props.o.hatch : (props.o.hatch ?? !!props.st.hatch));
const hatchKey = computed(() => {
  if (!props.rule && props.o.hatch == null) return "layer";
  return hatched.value ? (props.o.hatchPat || props.st.hatchPat || "45") : "none";
});
const edge = computed(() => edgeColor(e.value, { fill: props.fill, hatch: hatched.value }));
const dashKey = computed(() => { const d = props.o.dash; if (!d) return "layer"; const k = d.join(","); return !k ? "solid" : Object.hasOwn(DASHES, k) ? k : "layer"; });
const labelKey = computed(() => props.o.label == null ? "layer" : props.o.label === "" ? "-" : "f:" + props.o.label);
const own = computed(() => hasOwnSym(props.o) && Object.keys(props.o).some(k => SYM_KEYS.includes(k) && !(props.rule && k === "hatch")));

function setHatch(v) {
  const o = props.o;
  if (v === "layer") { delete o.hatch; delete o.hatchPat; delete o.hatchStep; delete o.hatchColor; }
  else if (v === "none") o.hatch = false;
  else { o.hatch = true; o.hatchPat = v; }
}
function setDash(v) { const o = props.o; if (v === "layer") delete o.dash; else o.dash = v === "solid" ? [] : v.split(",").map(Number); }
function setLabel(v) { const o = props.o; if (v === "layer") { delete o.label; delete o.labelSize; delete o.labelColor; } else o.label = v === "-" ? "" : v.slice(2); }
function reset() { SYM_KEYS.forEach(k => { if (!(props.rule && k === "hatch")) delete props.o[k]; }); }
</script>

<style>
.csym { border-left: 2px solid var(--g-line); padding: 6px 0 2px 8px; margin: 2px 0 6px; }
.csym wa-button.reset { margin-top: 2px; }
</style>
