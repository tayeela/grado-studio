<!-- ГРАДО 2 · окно «Слои» нового интерфейса: слои проекта по группам в порядке файла (сверху вниз — как на карте),
     глаз слоя и группы, свёртка группы, выбор текущего слоя. Читает и меняет store.project / store.currentId; в файл пишет project.js. -->
<template>
  <div class="pane layers">
    <wa-input size="s" placeholder="Найти слой" with-clear v-model="q"></wa-input>
    <p v-if="!project.layers.length" class="hint">{{ loadError || "В проекте пока нет слоёв" }}</p>
    <template v-for="b in blocks" :key="b.id">
      <div v-if="b.group" class="grp" :class="{ off: !b.group.visible }">
        <button class="tw" :title="b.group.open ? 'Свернуть группу' : 'Развернуть группу'" @click="b.group.open = !b.group.open">
          <ChevronDown v-if="b.group.open || q" :size="14" /><ChevronRight v-else :size="14" />
        </button>
        <button class="eye" :title="b.group.visible ? 'Скрыть группу' : 'Показать группу'" @click="b.group.visible = !b.group.visible">
          <Eye v-if="b.group.visible" :size="15" /><EyeOff v-else :size="15" />
        </button>
        <span class="gname">{{ b.group.title }}</span>
        <span class="cnt">{{ b.layers.length }}</span>
      </div>
      <template v-if="!b.group || b.group.open || q">
        <div v-for="l in b.layers" :key="l.key" class="row" :class="{ cur: l.key === currentId, nested: !!b.group }"
             :data-key="l.key" @click="currentId = l.key">
          <button class="eye" :title="l.visible ? 'Скрыть слой' : 'Показать слой'" @click.stop="l.visible = !l.visible">
            <Eye v-if="l.visible" :size="15" /><EyeOff v-else :size="15" />
          </button>
          <span class="sw" :class="swatchOf(l).kind" :style="{ '--c': swatchOf(l).c, '--e': swatchOf(l).e }"></span>
          <span class="name" :class="{ off: !shown(l) }">{{ l.title || l.key }}</span>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { ChevronDown, ChevronRight, Eye, EyeOff } from "@lucide/vue";
import { currentId, project, shown, swatchOf } from "../store.js";
import { loadError } from "../project.js";

const q = ref("");

/* Блоки списка в порядке слоёв файла: группа встаёт там, где её первый слой; слой без группы — отдельной строкой. */
const blocks = computed(() => {
  const s = q.value.trim().toLowerCase(), out = [], byGroup = {};
  for (const l of project.layers) {
    if (s && !(l.title || l.key).toLowerCase().includes(s)) continue;
    const g = l.group && project.groups.find(x => x.id === l.group);
    if (!g) { out.push({ id: "l:" + l.key, group: null, layers: [l] }); continue; }
    if (!byGroup[g.id]) out.push(byGroup[g.id] = { id: "g:" + g.id, group: g, layers: [] });
    byGroup[g.id].layers.push(l);
  }
  return out;
});
</script>

<style>
.layers .row, .layers .grp { display: flex; align-items: center; gap: 6px; padding: 3px 4px; border-radius: var(--wa-border-radius-s); cursor: default; }
.layers .row.nested { padding-left: 24px; }
.layers .row:hover { background: var(--wa-color-neutral-fill-quiet); }
.layers .row.cur { background: var(--wa-color-brand-fill-quiet); color: var(--wa-color-brand-on-quiet); }
.layers .grp { margin-top: var(--wa-space-xs); font-weight: 600; }
.layers .grp .cnt { margin-left: auto; color: var(--g-muted); font-weight: 400; font-size: var(--wa-font-size-xs); }
.layers .grp.off .gname { color: var(--g-muted); }
.layers .eye, .layers .tw { all: unset; display: inline-flex; color: var(--g-muted); cursor: pointer; padding: 1px; border-radius: 3px; }
.layers .eye:focus-visible, .layers .tw:focus-visible { outline: 2px solid var(--wa-color-focus); }
.layers .sw { width: 16px; height: 10px; flex: none; box-sizing: border-box; }
.layers .sw.line { border-bottom: 2.5px solid var(--c); height: 6px; }
.layers .sw.poly { background: color-mix(in srgb, var(--c) 45%, transparent); border: 1px solid var(--e); }
.layers .sw.poly.hatch { background: repeating-linear-gradient(135deg, var(--c) 0 1px, transparent 1px 4px); }
.layers .sw.point { width: 10px; margin: 0 3px; border-radius: 50%; background: var(--c); border: 1px solid var(--e); }
.layers .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.layers .name.off { color: var(--g-muted); }
</style>
