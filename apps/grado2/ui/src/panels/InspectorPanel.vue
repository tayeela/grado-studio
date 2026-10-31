<!-- ГРАДО 2 · единый инспектор слоя и объекта: закреплённые вкладки, одно прокручиваемое тело.
     Использует прежние редакторы без второй модели данных; выбор карты/таблицы не забирает фокус. -->
<template>
  <section class="inspector" aria-label="Свойства слоя и объекта">
    <div class="inspector-tabs" role="tablist" aria-label="Свойства">
      <button v-for="[id, title] in tabs" :id="'inspector-tab-' + id" :key="id" type="button" role="tab"
              :aria-selected="inspector.tab === id" :tabindex="inspector.tab === id ? 0 : -1" :aria-controls="'inspector-' + id"
              @click="switchTab(id)" @keydown="tabKey($event, id)">{{ title }}</button>
    </div>
    <div v-show="inspector.tab === 'layer'" id="inspector-layer" class="inspector-body" role="tabpanel" aria-labelledby="inspector-tab-layer">
      <PropsPanel />
    </div>
    <div v-show="inspector.tab === 'object'" id="inspector-object" class="inspector-body" role="tabpanel" aria-labelledby="inspector-tab-object">
      <ObjectPanel />
    </div>
  </section>
</template>
<script setup>
import { inspector } from "../inspector.js";
import PropsPanel from "./PropsPanel.vue";
import ObjectPanel from "./ObjectPanel.vue";
const tabs = [["layer", "Слой"], ["object", "Объект"]];
function switchTab(id) { inspector.tab = id; }
function tabKey(e, id) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
  e.preventDefault(); e.stopPropagation();
  const next = e.key === "Home" ? "layer" : e.key === "End" ? "object" : id === "layer" ? "object" : "layer";
  switchTab(next); document.getElementById("inspector-tab-" + next)?.focus();
}
</script>
<style>
.inspector { height: 100%; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }
.inspector-tabs { display: flex; gap: 4px; flex: none; padding: 4px 8px 0; border-bottom: 1px solid var(--g-line); }
.inspector-tabs button { flex: 1; min-width: 0; min-height: 30px; border: 0; border-bottom: 2px solid transparent; background: none; color: var(--g-muted); font: inherit; cursor: pointer; }
.inspector-tabs button[aria-selected="true"] { color: var(--wa-color-brand-on-quiet); border-bottom-color: var(--wa-color-brand-fill-loud); font-weight: 600; }
.inspector-tabs button:focus-visible { outline: 2px solid var(--wa-color-focus); outline-offset: -2px; }
.inspector-body { flex: 1; min-height: 0; min-width: 0; overflow: hidden; }
.inspector-body > .pane { height: 100%; box-sizing: border-box; overflow-y: auto; overflow-x: hidden; }
.inspector .ph { position: sticky; top: calc(-1 * var(--wa-space-s)); z-index: 2; background: var(--wa-color-surface-default); padding: 8px 0; }
</style>
