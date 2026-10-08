<!-- ГРАДО 2 · окно «Свойства» нового интерфейса: оформление текущего слоя на формах Web Awesome.
     Меняет цвет и вид слоя в store.layers — карта перерисовывается сама (MapPanel следит за store). -->
<template>
  <div class="pane props" v-if="current">
    <h3>Оформление слоя</h3>
    <div class="title">{{ current.title }}</div>
    <wa-select label="Способ оформления" size="s" value="single">
      <wa-option value="single">Единое</wa-option>
      <wa-option value="cat">По категориям</wa-option>
      <wa-option value="range">По диапазонам</wa-option>
      <wa-option value="rules">По правилам</wa-option>
      <wa-option value="lgr">Знаки ЛГР</wa-option>
    </wa-select>
    <wa-color-picker label="Цвет" size="s" :value="current.color" @change="e => (current.color = e.target.value)"></wa-color-picker>
    <wa-select label="Вид" size="s" :value="current.kind" @change="e => (current.kind = e.target.value)">
      <wa-option value="line">Линия</wa-option>
      <wa-option value="fill">Заливка с контуром</wa-option>
    </wa-select>
    <wa-number-input label="Толщина линии, мм" size="s" value="0.35" step="0.05" min="0.05"></wa-number-input>
    <wa-slider label="Прозрачность заливки" size="s" min="0" max="100" value="25" with-tooltip></wa-slider>
    <wa-switch size="s" :checked="current.visible" @change="e => (current.visible = e.target.checked)">Показывать на карте</wa-switch>
    <wa-switch size="s">Подписи объектов</wa-switch>
  </div>
</template>

<script setup>
import { current } from "../store.js";
</script>

<style>
.props .title { font-weight: 600; margin-bottom: var(--wa-space-m); }
</style>
