<!-- ГРАДО 2 · окно «Слои» нового интерфейса: слои по группам, глаз видимости, выбор текущего слоя.
     Читает и меняет store.layers / store.currentId; перетаскивание порядка (SortableJS) — следующий шаг переноса. -->
<template>
  <div class="pane layers">
    <wa-input size="s" placeholder="Найти слой" with-clear v-model="q"></wa-input>
    <template v-for="(items, g) in groups" :key="g">
      <h3>{{ g }}</h3>
      <div v-for="l in items" :key="l.id" class="row" :class="{ cur: l.id === currentId }" @click="currentId = l.id">
        <button class="eye" :title="l.visible ? 'Скрыть слой' : 'Показать слой'" @click.stop="l.visible = !l.visible">
          <Eye v-if="l.visible" :size="15" /><EyeOff v-else :size="15" />
        </button>
        <span class="sw" :class="l.kind" :style="{ '--c': l.color }"></span>
        <span class="name" :class="{ off: !l.visible }">{{ l.title }}</span>
      </div>
    </template>
    <p class="hint">Образец: слои условные. При переносе здесь будет дерево слоёв проекта.</p>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { Eye, EyeOff } from "@lucide/vue";
import { currentId, layers } from "../store.js";

const q = ref("");
const groups = computed(() => {
  const out = {};
  for (const l of layers) {
    if (q.value && !l.title.toLowerCase().includes(q.value.toLowerCase())) continue;
    (out[l.group] ||= []).push(l);
  }
  return out;
});
</script>

<style>
.layers .row { display: flex; align-items: center; gap: 6px; padding: 3px 4px; border-radius: var(--wa-border-radius-s); cursor: default; }
.layers .row:hover { background: var(--wa-color-neutral-fill-quiet); }
.layers .row.cur { background: var(--wa-color-brand-fill-quiet); color: var(--wa-color-brand-on-quiet); }
.layers .eye { all: unset; display: inline-flex; color: var(--g-muted); cursor: pointer; padding: 1px; border-radius: 3px; }
.layers .eye:focus-visible { outline: 2px solid var(--wa-color-focus); }
.layers .sw { width: 16px; height: 10px; flex: none; box-sizing: border-box; }
.layers .sw.line { border-bottom: 2.5px solid var(--c); height: 6px; }
.layers .sw.fill { background: color-mix(in srgb, var(--c) 35%, transparent); border: 1px solid var(--c); }
.layers .name.off { color: var(--g-muted); }
</style>
