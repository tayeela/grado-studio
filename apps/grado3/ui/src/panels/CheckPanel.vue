<!-- ГРАДО · окно «Проверка проекта» (шаг И1): итог проверки файла ядром Rust (rust/crates/model check) — сколько слоёв,
     объектов, видов и листов, ошибки и замечания по-русски. На шаге И4 сюда добавится готовность листов. -->
<template>
  <div class="g3-panel">
    <p v-if="!r" class="g3-muted">Проект не открыт.</p>
    <template v-else>
      <p>Слоёв {{ r.layers }} · объектов {{ r.features.toLocaleString("ru-RU") }} · видов {{ r.views }} · листов {{ r.sheets }}</p>
      <p v-if="!r.issues.length">Замечаний нет.</p>
      <ul>
        <li v-for="(i, k) in r.issues" :key="k" :class="i.level">
          <b>{{ i.level === "error" ? "Ошибка" : "Замечание" }}</b> {{ i.text }} <span class="g3-muted">{{ i.path }}</span>
        </li>
      </ul>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useProject } from "../stores/project";

const project = useProject();
const r = computed(() => project.report);
</script>

<style scoped>
ul { padding-left: 18px; }
li { margin: 4px 0; }
li.error b { color: var(--wa-color-danger-on-quiet, #b3261e); }
li.warning b { color: var(--wa-color-warning-on-quiet, #a86400); }
</style>
