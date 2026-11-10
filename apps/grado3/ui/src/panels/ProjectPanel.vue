<!-- ГРАДО · окно «Проект» каркаса (шаг И1): проекты папки, новые сверху; щелчок — команда «открыть». Каталог с превью,
     корзиной и совместными проектами переезжает на шаге И6 (apps/grado2/ui/src/panels/ProjectCatalog.vue). -->
<template>
  <div class="g3-panel">
    <p class="g3-muted">{{ project.dir || "Папка проектов" }}</p>
    <p v-if="err" class="g3-muted">{{ err }}</p>
    <button v-for="p in project.list" :key="p.name" class="item" :aria-current="p.name === project.name ? 'true' : undefined"
            @click="cmd.run(`открыть &quot;${p.name}&quot;`)">
      <span class="t">{{ p.name }}</span>
      <span class="g3-muted">{{ when(p.modified) }} · {{ size(p.size) }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useProject } from "../stores/project";
import { useCommands } from "../stores/commands";

const project = useProject(), cmd = useCommands();
const err = ref("");
const when = (t: number) => new Date(t * 1000).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const size = (b: number) => b > 2 ** 20 ? (b / 2 ** 20).toFixed(1).replace(".", ",") + " МБ" : Math.max(1, Math.round(b / 1024)) + " КБ";
onMounted(async () => { try { await project.refreshList(); } catch (e) { err.value = (e as Error).message; } });
</script>

<style scoped>
.item { display: grid; width: 100%; text-align: left; gap: 2px; padding: 6px 8px; border: 1px solid transparent; border-radius: 8px; background: none; color: inherit; font: inherit; cursor: pointer; }
.item:hover { background: var(--wa-color-surface-lowered); }
.item[aria-current] { background: var(--wa-color-brand-fill-quiet); border-color: var(--wa-color-brand-border-normal); }
.t { font-weight: 500; }
</style>
