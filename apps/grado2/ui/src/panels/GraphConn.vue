<!-- ГРАДО 2 · связь блоков схемы расчёта: кривая цветом типа данных, как связи litegraph рабочей страницы. -->
<template>
  <svg class="gconn" data-testid="connection"><path :d="path" :class="'t-' + (data.type || 'geom')"></path></svg>
</template>

<script setup>
defineProps(["data", "start", "end", "path"]);
</script>

<style>
svg.gconn { overflow: visible !important; position: absolute; pointer-events: none; width: 9999px; height: 9999px; }
svg.gconn path { fill: none; stroke-width: 2.5px; stroke: var(--gl-geom); pointer-events: auto; }
svg.gconn path.t-num { stroke: var(--gl-num); } svg.gconn path.t-sketch { stroke: var(--gl-sketch); }
svg.gconn path.t-tep { stroke: var(--gl-tep); } svg.gconn path.t-cap { stroke: var(--gl-cap); }
</style>
