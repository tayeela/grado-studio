<!-- ГРАДО 2 · гнездо блока схемы расчёта: кружок цветом типа данных (геометрия, число, эскиз, ТЭП, предельная высота);
     связь соединяет только гнёзда одного типа (graph.js canConnect). -->
<template>
  <div class="gsock" :class="'t-' + data.name" :title="TIP[data.name] || data.name"></div>
</template>

<script setup>
defineProps(["data"]);
const TIP = { geom: "геометрия", num: "число", sketch: "эскиз (корпуса)", tep: "показатели", cap: "предельная высота" };
</script>
