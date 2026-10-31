<!-- ГРАДО 2 · сворачиваемый раздел инспектора; раскрытие сохраняется отдельно от проекта. -->
<template>
  <details class="inspector-section" :open="inspector.sections[section]" @toggle="inspector.sections[section] = $event.target.open">
    <summary>{{ title }}</summary>
    <slot />
  </details>
</template>
<script setup>
import { inspector } from "../inspector.js";
defineProps({ section: String, title: String });
</script>
<style>
.inspector-section { min-width: 0; border-top: 1px solid var(--g-line); margin-top: 8px; }
.inspector-section > summary { min-height: 30px; box-sizing: border-box; padding: 7px 0; font-size: var(--wa-font-size-s); font-weight: 600; cursor: pointer; }
.inspector-section > summary:focus-visible { outline: 2px solid var(--wa-color-focus); }
.inspector .source-value { overflow-wrap: anywhere; margin: 0 0 8px; font-size: var(--wa-font-size-s); }
</style>
