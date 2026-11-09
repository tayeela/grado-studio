<!-- ГРАДО 2 · «Слои знака» в окне «Свойства» (план 08.11.2026, шаг 2, как слои символа QGIS): стопка частей поверх
     основного знака — линия по контуру, полоса внутрь вдоль границы (ЗОУИТ), штриховка, значки вдоль линии со стороной.
     Правит массив o.parts: у слоя — его стиль, у класса — st.cat.sym[значение] или правило (тогда части класса заменяют части слоя).
     Смысл полей — symbology.js PARTS/cleanParts; карта рисует partStyles, печать — symparts.py. -->
<template>
  <div class="sparts">
    <div v-for="(p, i) in list" :key="i" class="sp">
      <div class="row">
        <wa-select size="s" class="grow" :aria-label="'Вид слоя знака ' + (i + 1)" :value="p.k" @change="e => setKind(i, e.target.value)">
          <wa-option v-for="(t, k) in kinds" :key="k" :value="k">{{ t }}</wa-option>
        </wa-select>
        <wa-color-picker size="s" aria-label="Цвет слоя знака" :value="p.c" @change="e => (p.c = e.target.value)"></wa-color-picker>
        <wa-button size="s" appearance="plain" title="Выше" aria-label="Слой знака выше" :disabled="i === list.length - 1" @click="move(i, 1)"><ChevronUp :size="14" /></wa-button>
        <wa-button size="s" appearance="plain" title="Ниже" aria-label="Слой знака ниже" :disabled="i === 0" @click="move(i, -1)"><ChevronDown :size="14" /></wa-button>
        <wa-button size="s" appearance="plain" title="Убрать слой знака" aria-label="Убрать слой знака" @click="drop(i)"><X :size="14" /></wa-button>
      </div>
      <div class="row">
        <template v-if="p.k === 'band'">
          <span class="u">ширина</span>
          <wa-number-input size="s" class="num" aria-label="Ширина полосы, пикс." :value="p.b" min="1" max="60" @change="e => (p.b = num(e, 6))"></wa-number-input>
        </template>
        <template v-if="p.k === 'hatch'">
          <wa-select size="s" class="grow" aria-label="Узор штриховки" :value="p.hp" @change="e => (p.hp = e.target.value)">
            <wa-option v-for="(t, k) in HATCHES" :key="k" :value="k">{{ t }}</wa-option>
          </wa-select>
          <span class="u">шаг</span>
          <wa-number-input size="s" class="num" aria-label="Шаг штриховки, пикс." :value="p.hs" min="4" max="40" @change="e => (p.hs = num(e, 8))"></wa-number-input>
        </template>
        <template v-if="p.k === 'marks'">
          <wa-select size="s" class="grow" aria-label="Значок" :value="p.shape" @change="e => (p.shape = e.target.value)">
            <wa-option v-for="(t, k) in MARKS" :key="k" :value="k">{{ t }}</wa-option>
          </wa-select>
          <wa-select size="s" class="grow" aria-label="Сторона значков" :value="String(p.side)" @change="e => (p.side = +e.target.value)">
            <wa-option value="1">{{ geom === 'poly' ? 'внутрь' : 'справа' }}</wa-option>
            <wa-option value="-1">{{ geom === 'poly' ? 'наружу' : 'слева' }}</wa-option>
          </wa-select>
        </template>
      </div>
      <div class="row">
        <template v-if="p.k === 'marks'">
          <span class="u">шаг</span>
          <wa-number-input size="s" class="num" aria-label="Шаг значков, пикс." :value="p.step" min="4" max="200" @change="e => (p.step = num(e, 16))"></wa-number-input>
          <span class="u">размер</span>
          <wa-number-input size="s" class="num" aria-label="Размер значка, пикс." :value="p.size" min="1" max="40" @change="e => (p.size = num(e, 5))"></wa-number-input>
        </template>
        <template v-if="p.k !== 'band'">
          <span class="u">толщина</span>
          <wa-number-input size="s" class="num" aria-label="Толщина, пикс." :value="p.w" step="0.1" min="0.1" max="10" @change="e => (p.w = num(e, 1))"></wa-number-input>
        </template>
        <template v-if="p.k === 'line'">
          <wa-select size="s" class="grow" aria-label="Тип линии слоя знака" :value="(p.dash || []).join(',') || 'solid'" @change="e => setDash(p, e.target.value)">
            <wa-option v-for="(t, k) in DASHES" :key="k" :value="k">{{ t }}</wa-option>
          </wa-select>
        </template>
        <template v-if="p.k === 'band'">
          <span class="sl" title="Непрозрачность полосы">
            <wa-slider size="s" min="0" max="100" aria-label="Непрозрачность полосы" :value="Math.round((p.a ?? 1) * 100)" @input="e => (p.a = num(e, 35) / 100)"></wa-slider>
            <span class="u v">{{ Math.round((p.a ?? 1) * 100) }} %</span>
          </span>
        </template>
      </div>
    </div>
    <wa-select size="s" class="add" aria-label="Добавить слой знака" value="" placeholder="+ слой знака" @change="e => { add(e.target.value); e.target.value = ''; }">
      <wa-option v-for="(t, k) in kinds" :key="k" :value="k">{{ t }}</wa-option>
    </wa-select>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { ChevronDown, ChevronUp, X } from "@lucide/vue";
import { DASHES, HATCHES, MARKS, PARTS, PART_DEF, okn } from "../symbology.js";

const props = defineProps({ o: Object, geom: String });
const num = (ev, d) => okn(ev.target.value, d);
/* у линейного слоя полоса и штриховка не рисуются — их нет в списке */
const kinds = computed(() => props.geom === "poly" ? PARTS : { line: "Линия", marks: PARTS.marks });
const list = computed(() => props.o.parts || []);
function add(k) {
  if (!k || !PART_DEF[k]) return;
  const p = { k, ...structuredClone(PART_DEF[k]) };
  props.o.parts = [...list.value, p];
}
function setKind(i, k) { const parts = [...list.value]; parts[i] = { k, ...structuredClone(PART_DEF[k]), c: parts[i].c }; props.o.parts = parts; }
function drop(i) { const parts = list.value.filter((_, j) => j !== i); if (parts.length) props.o.parts = parts; else delete props.o.parts; }
function move(i, d) { const parts = [...list.value], j = i + d; [parts[i], parts[j]] = [parts[j], parts[i]]; props.o.parts = parts; }
function setDash(p, v) { if (v === "solid") delete p.dash; else p.dash = v.split(",").map(Number); }
</script>

<style>
.sparts .sp { border: 1px solid var(--g-line); border-radius: var(--wa-border-radius-s); padding: 6px; margin-bottom: 6px; }
.sparts .row { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-bottom: 4px; }
.sparts .row:empty { display: none; }
.sparts .grow { flex: 1 1 90px; min-width: 0; }
.sparts .num { width: 72px; }
.sparts .u { color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.sparts .sl { display: inline-flex; align-items: center; gap: 6px; flex: 1; }
.sparts .sl wa-slider { flex: 1; }
.sparts wa-select.add { width: 100%; }
</style>
