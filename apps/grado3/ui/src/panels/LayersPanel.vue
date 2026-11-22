<!-- ГРАДО · окно «Слои» (план 09.11.2026, шаги И1 и И2): слои проекта сверху вниз по группам, образец знака слоя,
     число объектов и площадь границы территории в га (МСК, ядро Rust). Глаз — показать/скрыть слой или всю группу,
     «граница» — роль границы у слоя полигонов, стрелки — порядок слоёв, создание группы. Всё через команды: отменяется Ctrl+Z. -->
<template>
  <div class="g3-panel g3-layers">
    <div v-if="project.doc" class="l-bar">
      <input v-model="newGrp" class="l-inp" type="text" placeholder="Новая группа слоёв…"
             aria-label="Название новой группы слоёв" @keydown.enter.prevent="addGroup" />
      <wa-button size="small" appearance="outlined" :disabled="!newGrp.trim()" @click="addGroup">+ Группа</wa-button>
    </div>

    <p v-if="!project.layers.length" class="g3-muted">Проект не открыт или в нём нет слоёв.</p>

    <template v-for="g in tree" :key="g.id || '_free'">
      <div v-if="g.id" class="grp-row">
        <wa-switch size="small" :checked="g.visible !== false" :title="g.visible !== false ? 'Скрыть группу' : 'Показать группу'"
                   @change="cmd.run((g.visible !== false ? 'группа-скрыть ' : 'группа-показать ') + g.id)" />
        <button type="button" class="grp-title" @click="toggleOpen(g.id)">
          <span>{{ isOpen(g.id) ? "▾" : "▸" }} {{ g.title || g.id }}</span>
          <span class="g3-muted">{{ g.layers.length }}</span>
        </button>
      </div>

      <template v-if="!g.id || isOpen(g.id)">
        <div v-for="l in g.layers" :key="l.key" class="row" :class="{ terr: l.role === 'territory', off: !project.shown(l), cur: ui.selectedLayer === l.key }">
          <wa-switch size="small" :checked="l.visible !== false" :title="l.visible !== false ? 'Скрыть слой' : 'Показать слой'"
                     @change="cmd.run((l.visible !== false ? 'скрыть ' : 'показать ') + l.key)" />
          <span class="sw" :class="{ dash: swatchOf(l).dash, line: l.geom === 'line' }"
                :style="{ background: swatchOf(l).fill, borderColor: swatchOf(l).stroke }" />
          <button type="button" class="t" :title="`${l.title || l.key} (${l.key}) — выбрать для свойств и таблицы; двойной щелчок — показать на карте`"
                  @click="selectLayer(l.key)" @dblclick="cmd.run('показать-всё ' + l.key)">
            <span class="tn">{{ l.title || l.key }}</span>
            <span class="tm g3-muted">
              {{ project.layerCount(l.key) }}
              <template v-if="l.role === 'territory' && project.territoryAreaM2 > 0"> · {{ fmtHa(project.territoryAreaM2) }}</template>
            </span>
          </button>
          <wa-badge v-if="l.role === 'territory'" variant="brand" appearance="filled" class="b-terr"
                    title="Снять роль границы территории" @click="cmd.run('граница нет')">граница</wa-badge>
          <wa-button v-else-if="l.geom === 'poly' || !l.geom" size="small" appearance="plain"
                     title="Сделать этот слой границей территории" @click="cmd.run('граница ' + l.key)">граница</wa-button>
          <button type="button" class="act" title="Показать слой на карте" @click="cmd.run('показать-всё ' + l.key)">◎</button>
          <button type="button" class="act" title="Поднять слой выше" @click="cmd.run('выше ' + l.key)">↑</button>
          <button type="button" class="act" title="Опустить слой ниже" @click="cmd.run('ниже ' + l.key)">↓</button>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { swatchOf } from "../symbology";
import { useProject } from "../stores/project";
import { useUi } from "../stores/ui";
import { useCommands } from "../stores/commands";
import type { Layer } from "../types/project";

const project = useProject(), ui = useUi(), cmd = useCommands();
const newGrp = ref("");
const closed = reactive<Record<string, boolean>>({});

function selectLayer(key: string) {
  ui.selectedLayer = key;
  ui.selectedFeatureIdx = null;
}

const isOpen = (id: string): boolean => !closed[id];
const toggleOpen = (id: string) => { closed[id] = !closed[id]; };

const fmtHa = (m2: number): string => {
  const ha = m2 / 1e4;
  return ha.toLocaleString("ru-RU", { minimumFractionDigits: ha < 1 ? 4 : 2, maximumFractionDigits: ha < 1 ? 4 : 2 }) + " га";
};

function addGroup() {
  const t = newGrp.value.trim();
  if (!t) return;
  newGrp.value = "";
  cmd.run(`группа ${t}`);
}

const tree = computed(() => {
  const gs = project.groups.map(g => ({ id: g.id, title: g.title || g.id, visible: g.visible !== false, layers: [] as Layer[] }));
  const free = { id: "", title: "", visible: true, layers: [] as Layer[] };
  for (const l of project.layers) (gs.find(g => g.id === l.group) || free).layers.push(l);
  return [free, ...gs].filter(g => g.layers.length || g.id);
});
</script>

<style scoped>
.g3-layers { display: flex; flex-direction: column; gap: 4px; }
.l-bar { display: flex; gap: 6px; margin-bottom: 6px; }
.l-inp { flex: 1; min-width: 0; padding: 4px 8px; border: 1px solid var(--wa-color-neutral-border-normal); border-radius: 6px; background: var(--wa-color-surface-default); color: inherit; font: inherit; font-size: 12px; }
.grp-row { display: flex; align-items: center; gap: 6px; margin-top: 8px; padding: 3px 4px; border-radius: 6px; background: var(--wa-color-surface-lowered); }
.grp-title { flex: 1; display: flex; justify-content: space-between; align-items: center; border: 0; background: none; color: inherit; font: inherit; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; cursor: pointer; padding: 2px 4px; }
.row { display: flex; align-items: center; gap: 6px; padding: 2px 4px; min-height: 28px; border-radius: 6px; }
.row.cur { background: var(--wa-color-brand-fill-quiet); }
.row.off .tn { opacity: 0.55; }
.sw { width: 14px; height: 14px; border-radius: 3px; border: 1.5px solid; flex-shrink: 0; box-sizing: border-box; }
.sw.dash { border-style: dashed; }
.sw.line { height: 0; border-width: 2px 0 0 0; border-radius: 0; }
.row .t { flex: 1; min-width: 0; display: flex; align-items: baseline; gap: 6px; border: 0; background: none; color: inherit; font: inherit; text-align: left; padding: 0; cursor: pointer; }
.row .tn { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row .tm { font-size: 11px; flex-shrink: 0; }
.row.terr .tn { font-weight: 600; }
.b-terr { cursor: pointer; }
.act { border: 0; background: none; color: var(--wa-color-text-quiet); cursor: pointer; padding: 2px 4px; font-size: 12px; border-radius: 4px; }
.act:hover { background: var(--wa-color-surface-lowered); color: var(--wa-color-text-normal); }
</style>
