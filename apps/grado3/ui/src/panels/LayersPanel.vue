<!-- ГРАДО · окно «Слои» каркаса (шаг И1): слои проекта сверху вниз по группам, глаз — команды «показать» и «скрыть»,
     «граница» — роль границы у слоя полигонов (отдельного инструмента нет). Всё через команды: отменяется Ctrl+Z.
     Дерево с перетаскиванием и «Свойства» переезжают на шаге И3 (apps/grado2/ui/src/panels/LayersPanel.vue). -->
<template>
  <div class="g3-panel">
    <p v-if="!project.layers.length" class="g3-muted">Проект не открыт или в нём нет слоёв.</p>
    <template v-for="g in groups" :key="g.id">
      <div v-if="g.title" class="grp">{{ g.title }}</div>
      <div v-for="l in g.layers" :key="l.key" class="row" :class="{ terr: l.role === 'territory' }">
        <wa-switch size="small" :checked="l.visible !== false" :title="l.visible !== false ? 'Скрыть' : 'Показать'"
                   @change="cmd.run((l.visible !== false ? 'скрыть ' : 'показать ') + l.key)" />
        <span class="t" :title="l.key">{{ l.title || l.key }}</span>
        <wa-badge v-if="l.role === 'territory'" variant="brand" appearance="filled">граница</wa-badge>
        <wa-button v-else-if="l.geom === 'poly'" size="small" appearance="plain" title="Сделать этот слой границей территории"
                   @click="cmd.run('граница ' + l.key)">граница</wa-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useProject } from "../stores/project";
import { useCommands } from "../stores/commands";
import type { Layer } from "../types/project";

const project = useProject(), cmd = useCommands();
const groups = computed(() => {
  const gs = project.doc?.groups || [];
  const out: { id: string; title: string; layers: Layer[] }[] = gs.map(g => ({ id: g.id, title: g.title || g.id, layers: [] }));
  const free = { id: "", title: "", layers: [] as Layer[] };
  for (const l of project.layers) (out.find(g => g.id === l.group) || free).layers.push(l);
  return [free, ...out].filter(g => g.layers.length);
});
</script>

<style scoped>
.grp { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: var(--wa-color-text-quiet); margin: 10px 0 4px; }
.row { display: flex; align-items: center; gap: 8px; padding: 2px 0; min-height: 28px; }
.row .t { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row.terr .t { font-weight: 600; }
</style>
