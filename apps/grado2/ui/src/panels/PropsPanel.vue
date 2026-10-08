<!-- ГРАДО 2 · окно «Свойства» нового интерфейса: оформление текущего слоя проекта на формах Web Awesome.
     Правка меняет стиль слоя в store.project — карта перерисовывается сама, project.js записывает её в проект (автосохранение, Ctrl+S). -->
<template>
  <div class="pane props" v-if="current">
    <h3>Оформление слоя</h3>
    <div class="title">{{ current.title || current.key }}</div>
    <div class="sub">{{ GEOM[current.geom] || current.geom }} · {{ count }} объектов</div>
    <wa-select label="Способ оформления" size="s" :value="s.mode" disabled>
      <wa-option value="single">Единое</wa-option>
      <wa-option value="cat">По категориям</wa-option>
      <wa-option value="grad">По диапазонам</wa-option>
      <wa-option value="rules">По правилам</wa-option>
      <wa-option value="lgr">Знаки ЛГР</wa-option>
    </wa-select>
    <wa-color-picker :label="current.geom === 'line' ? 'Цвет линии' : 'Цвет заливки'" size="s" :value="s.fill" @change="e => set('fill', e.target.value)"></wa-color-picker>
    <wa-color-picker v-if="current.geom !== 'line'" label="Цвет контура" size="s" :value="s.stroke" @change="e => set('stroke', e.target.value)"></wa-color-picker>
    <wa-number-input :label="current.geom === 'point' ? 'Размер, пикс.' : 'Толщина, пикс.'" size="s" :value="s.width" step="0.1" min="0" max="10"
                     @change="e => set('width', Number(e.target.value))"></wa-number-input>
    <wa-slider v-if="current.geom === 'poly'" label="Непрозрачность заливки, %" size="s" min="0" max="100" :value="Math.round(s.opacity * 100)" with-tooltip
               @change="e => set('opacity', Number(e.target.value) / 100)"></wa-slider>
    <wa-switch size="s" :checked="current.visible" @change="e => (current.visible = e.target.checked)">Показывать на карте</wa-switch>
    <p class="hint">Правка сразу попадает в автосохранение, «Проект → Сохранить» (Ctrl+S) записывает её в файл. Другие способы оформления появятся при переносе этого окна.</p>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { current, project, styleOf } from "../store.js";

const GEOM = { point: "Точки", line: "Линии", poly: "Полигоны" };
const s = computed(() => styleOf(current.value));
const count = computed(() => project.data[current.value?.key]?.fc?.features?.length || 0);
function set(k, v) { current.value.style = { ...(current.value.style || {}), [k]: v }; }
</script>

<style>
.props .title { font-weight: 600; }
.props .sub { color: var(--g-muted); font-size: var(--wa-font-size-xs); margin-bottom: var(--wa-space-m); }
</style>
