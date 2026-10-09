<!-- ГРАДО 2 · окно «Объект» нового интерфейса: выбранные на карте или в таблице объекты, как вкладка «Объект» рабочей
     страницы (web/layers.js renderObject): один объект — слой, площадь или длина в МСК, атрибуты с правкой, новое поле;
     несколько — сводка площади и длины, общая правка атрибутов у объектов одного слоя («разные» — не меняется, пока не
     заполнить), «Только он» при нескольких слоях; решение по зданиям и этажность ± своих корпусов. Правка — features.js. -->
<template>
  <div class="pane obj">
    <p v-if="!items.length" class="hint">Щёлкните объект на карте или строку таблицы. Несколько объектов — Shift+щелчок
      или рамка с Shift. Все объекты текущего слоя — Ctrl+A. Del — удалить выбранные, Esc — снять выбор.</p>

    <template v-else-if="items.length === 1">
      <div class="ph"><b>{{ lyr(items[0].key)?.title }}</b>
        <wa-button size="s" appearance="plain" title="Приблизить к объекту" @click="mapApi.fitFeature(items[0].f)"><Focus :size="15" /></wa-button></div>
      <div class="sub">{{ sizeText(items) }}{{ items[0].f.properties._edited ? " · изменён вручную" : "" }}</div>
      <DecisionBar :items="items" />
      <div class="grid">
        <template v-for="k in fields" :key="k">
          <label :title="k">{{ k }}</label>
          <wa-input size="s" :value="String(items[0].f.properties[k] ?? '')" @change="e => setAttr(items, k, e.target.value)"></wa-input>
        </template>
      </div>
    </template>

    <template v-else>
      <div class="ph"><b>Выбрано объектов: {{ items.length.toLocaleString("ru-RU") }}</b></div>
      <div class="sub">{{ sizeText(items) }}</div>
      <DecisionBar :items="items" />
      <template v-if="byLayer.length > 1">
        <table class="cl">
          <tr v-for="[k, n] in byLayer" :key="k"><td>{{ lyr(k)?.title }}</td><td class="n">{{ n }}</td>
            <td><wa-button size="s" appearance="outlined" title="Оставить в выборе только объекты этого слоя" @click="only(k)">Только он</wa-button></td></tr>
        </table>
        <p class="hint">Атрибуты правятся у объектов одного слоя: оставьте в выборе один слой.</p>
      </template>
      <template v-else>
        <p class="hint">Слой «{{ lyr(byLayer[0][0])?.title }}». Значение, введённое в поле, получат все {{ items.length }} объектов;
          «разные» — у объектов разные значения, поле не меняется, пока его не заполнить.</p>
        <div class="grid">
          <template v-for="k in fields" :key="k">
            <label :title="k">{{ k }}</label>
            <wa-input size="s" :value="common(k).same ? common(k).v : ''" :placeholder="common(k).same ? '' : `разные (${common(k).n})`"
                      @change="e => setAttr(items, k, e.target.value)"></wa-input>
          </template>
        </div>
      </template>
    </template>

    <div v-if="items.length && byLayer.length === 1" class="row">
      <wa-input size="s" :placeholder="items.length > 1 ? 'Новое поле для всех' : 'Новое поле'" :value="newField" @input="e => (newField = e.target.value)"
                @keydown.enter="addNew"></wa-input>
      <wa-button size="s" appearance="outlined" @click="addNew">Добавить</wa-button>
    </div>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, ref } from "vue";
import { Focus } from "@lucide/vue";
import { lyr, mapApi } from "../edit.js";
import { addField, editFeatures, fieldsOfFeatures, selected, sel, setAttr, setSel, sizeOf } from "../features.js";
import { dataRev } from "../edit.js";

const DECISION = "Решение", DECISIONS = { "сохраняем": "#b9b4ab", "реконструкция": "#eda100", "сносим": "#b3261e" };
const DECSHORT = { "сохраняем": "сохраняем", "реконструкция": "реконстр.", "сносим": "сносим" };

const items = computed(() => (dataRev.value, sel.length, selected()));
const fields = computed(() => fieldsOfFeatures(items.value.slice(0, 2000).map(s => s.f)));
const byLayer = computed(() => { const m = new Map(); items.value.forEach(s => m.set(s.key, (m.get(s.key) || 0) + 1)); return [...m]; });
const fmt = (v, d) => v.toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d });
function sizeText(list) {
  let area = 0, len = 0;
  if (list.length <= 5000) list.forEach(s => { const [k, v] = sizeOf(s.f); if (k === "area") area += v; if (k === "len") len += v; });
  if (list.length === 1) return area ? fmt(area, 1) + " м²" : len ? fmt(len, 2) + " м" : "точка";
  return [area ? `площадь ${fmt(area / 1e4, 3)} га` : "", len ? `длина ${fmt(len, 0)} м` : ""].filter(Boolean).join(" · ");
}
function common(k) {
  const vals = new Set(items.value.slice(0, 5000).map(s => String(s.f.properties[k] ?? "")));
  return { same: vals.size === 1, v: [...vals][0], n: vals.size + (items.value.length > 5000 ? "+" : "") };
}
const only = k => setSel(sel.filter(s => s.key === k));
const newField = ref("");
function addNew() { const n = newField.value.trim(); if (!n) return; addField(items.value, n); newField.value = ""; }

/* Решение по зданиям реестра (поле «Решение») и этажность своих корпусов (эскиз, нарисованное) — кнопками, как в TestFit. */
const DecisionBar = defineComponent({
  props: { items: Array },
  setup(props) {
    return () => {
      const its = props.items, dec = its.filter(s => DECISION in s.f.properties);
      const own = its.filter(s => "Этажность" in s.f.properties && !/^(nspd|osm|gisogd)\./.test(s.key));
      const out = [];
      if (dec.length) out.push(h("div", { class: "dec" }, Object.keys(DECISIONS).map(v => h("wa-button", {
        size: "s", appearance: "outlined", title: "Решение по выбранным зданиям: " + v, onClick: () => setAttr(dec, DECISION, v),
      }, [h("i", { class: "dot", style: { background: DECISIONS[v] } }), " " + DECSHORT[v]]))));
      if (own.length) {
        const vals = [...new Set(own.map(s => s.f.properties["Этажность"]))];
        const step = d => {           // этажность ± 1; у корпуса эскиза СПП следует за этажностью
          const by = new Map(); own.forEach(s => (by.get(s.key) || by.set(s.key, []).get(s.key)).push(s.uid));
          by.forEach((uids, key) => editFeatures(key, uids, p => {
            const n = Math.max(1, (+p["Этажность"] || 1) + d); p["Этажность"] = n;
            if (p["Площадь застройки, м²"]) p["СПП, м²"] = Math.round(p["Площадь застройки, м²"] * n);
          }));
        };
        out.push(h("div", { class: "fl" }, [h("span", "Этажность"),
          h("wa-button", { size: "s", appearance: "outlined", title: "На этаж ниже", onClick: () => step(-1) }, "−"),
          h("b", vals.length === 1 ? String(vals[0]) : "разная"),
          h("wa-button", { size: "s", appearance: "outlined", title: "На этаж выше", onClick: () => step(1) }, "+")]));
      }
      return out;
    };
  },
});
</script>

<style>
.obj .ph { display: flex; align-items: center; gap: 6px; justify-content: space-between; }
.obj .sub { color: var(--g-muted); font-size: var(--wa-font-size-xs); margin: 2px 0 var(--wa-space-s); }
.obj .grid { display: grid; grid-template-columns: minmax(70px, 40%) minmax(0, 1fr); gap: 3px 6px; align-items: center; margin-bottom: var(--wa-space-s); }
.obj .grid label { font-size: var(--wa-font-size-s); color: var(--g-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.obj .grid wa-input { margin: 0 !important; }
.obj .row { display: flex; gap: 6px; align-items: center; }
.obj .row wa-input { flex: 1; min-width: 0; margin: 0 !important; }
.obj table.cl { width: 100%; border-collapse: collapse; font-size: var(--wa-font-size-s); margin-bottom: var(--wa-space-s); }
.obj table.cl td { padding: 2px 4px; border-bottom: 1px solid var(--g-line); }
.obj .n { color: var(--g-muted); text-align: right; }
.obj .dec, .obj .fl { display: flex; gap: 4px; align-items: center; margin-bottom: var(--wa-space-s); flex-wrap: wrap; }
.obj .fl b { min-width: 48px; text-align: center; }
.obj .dot { display: inline-block; width: 10px; height: 10px; border-radius: 2px; vertical-align: middle; }
</style>
