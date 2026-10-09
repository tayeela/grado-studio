<!-- ГРАДО 2 · режимы черчения в строке состояния нового интерфейса (как web/cad.js buildModes): ПРИВЯЗКА (F3) и набор
     привязок, ОТСЛЕЖ (F11), ПОЛЯР (F10) и шаг угла, ОРТО (F8), ДИН (F12), ТОПО. Состояние — cad.st (cad.js), запоминает браузер. -->
<template>
  <span v-if="cad.ready" class="modes">
    <span class="mg">
      <button :aria-pressed="!!st.osnap" title="Объектная привязка (F3): конечная точка, середина, центр, пересечение… ▾ — какие привязки включены" @click="cadApi.toggle('osnap')">ПРИВЯЗКА</button>
      <wa-dropdown placement="top-start" @wa-select="onSnap">
        <button slot="trigger" class="dd" title="Какие привязки включены" aria-label="Набор привязок">▾</button>
        <h4 class="menu-h">Объектные привязки</h4>
        <wa-dropdown-item v-for="(t, k) in cadApi.MODES" :key="k" type="checkbox" :value="k" :checked="!!st.modes[k]">{{ t }}</wa-dropdown-item>
        <wa-divider></wa-divider>
        <wa-dropdown-item value="*all">Включить все</wa-dropdown-item>
        <wa-dropdown-item value="*none">Снять все</wa-dropdown-item>
      </wa-dropdown>
    </span>
    <button :aria-pressed="!!st.otrack" title="Объектное отслеживание (F11): задержите курсор на точке привязки, пока не появится «+», и ведите — пунктирные линии выравнивания и продолжения" @click="cadApi.toggle('otrack')">ОТСЛЕЖ</button>
    <span class="mg">
      <button :aria-pressed="!!st.polar" title="Полярное отслеживание (F10): пунктирный луч от последней точки под углами, кратными шагу. ▾ — шаг угла" @click="cadApi.toggle('polar')">ПОЛЯР {{ st.polarInc }}°</button>
      <wa-dropdown placement="top-start" @wa-select="onPolar">
        <button slot="trigger" class="dd" title="Шаг угла" aria-label="Шаг угла">▾</button>
        <h4 class="menu-h">Шаг угла</h4>
        <wa-dropdown-item v-for="v in [90, 45, 30, 15, 10, 5]" :key="v" type="checkbox" :value="String(v)" :checked="st.polarInc === v">{{ v }}°</wa-dropdown-item>
        <wa-divider></wa-divider>
        <wa-dropdown-item value="rel" type="checkbox" :checked="!!st.polarRel">Угол от последнего отрезка</wa-dropdown-item>
      </wa-dropdown>
    </span>
    <button :aria-pressed="!!st.ortho" title="Орто (F8): только по осям X и Y МСК" @click="cadApi.toggle('ortho')">ОРТО</button>
    <button :aria-pressed="!!st.dyn" title="Динамический ввод (F12): размеры и поле ввода у курсора" @click="cadApi.toggle('dyn')">ДИН</button>
    <button :aria-pressed="!!st.topo" title="Топологическое редактирование: вершина, общая для нескольких объектов (граница соседних участков, зон), двигается во всех сразу" @click="cadApi.toggle('topo')">ТОПО</button>
  </span>
</template>

<script setup>
import { computed } from "vue";
import { cad, cadApi } from "../cad.js";

const st = computed(() => cad.st);
function onSnap(e) {
  const v = e.detail.item.value;
  if (v === "*all" || v === "*none") Object.keys(cadApi.MODES).forEach(k => cadApi.setMode(k, v === "*all"));
  else cadApi.setMode(v, !cad.st.modes[v]);
}
function onPolar(e) {
  const v = e.detail.item.value;
  if (v === "rel") cadApi.setOpt("polarRel", !cad.st.polarRel);
  else { cadApi.setOpt("polarInc", +v); if (!cad.st.polar) cadApi.toggle("polar"); }
}
</script>

<style>
.status .modes { display: inline-flex; gap: 2px; align-items: center; }
.status .modes .mg { display: inline-flex; }
.status .modes button {
  height: 18px; padding: 0 6px; border: 1px solid var(--g-line); border-radius: 3px; background: none; color: var(--g-muted);
  font: 600 var(--wa-font-size-2xs)/1 system-ui, sans-serif; letter-spacing: .03em; cursor: pointer; white-space: nowrap;
}
.status .modes .mg > button { border-top-right-radius: 0; border-bottom-right-radius: 0; }
.status .modes .mg .dd { border-left: 0; border-top-left-radius: 0; border-bottom-left-radius: 0; padding: 0 4px; }
.status .modes button[aria-pressed=true] {
  background: color-mix(in srgb, var(--wa-color-brand-fill-loud) 14%, transparent);
  border-color: color-mix(in srgb, var(--wa-color-brand-fill-loud) 45%, transparent); color: var(--wa-color-text-normal);
}
.status .modes button:not([aria-pressed=true]):hover { background: var(--wa-color-neutral-fill-quiet); color: var(--wa-color-text-normal); }
</style>
