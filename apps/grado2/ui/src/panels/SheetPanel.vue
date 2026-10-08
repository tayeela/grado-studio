<!-- ГРАДО 2 · окно «Макет листа» нового интерфейса: редактор раскладки листа на Konva (src/sheet/SheetEditor.vue)
     во вкладке dockview рядом с картой. Карта блока — настоящая карта проекта в масштабе блока, нарисованная печатью
     сервера; «PDF» печатает лист тем же рендером (sheetmaps.js). Штамп берёт поля альбома открытого проекта (store.js
     album.meta). Новый лист ставит карту туда, где открыт проект, легенду собирает из его слоёв. Пока лист живёт
     только в окне и в проект не записывается: новый интерфейс — только просмотр. -->
<template>
  <SheetEditor v-model="sheet" :maps="maps" :meta="project.album?.meta || {}" :page="{ page_no: 1, page_total: project.album?.sheets?.length || 1 }" />
</template>

<script setup>
import { ref, watch } from "vue";
import SheetEditor from "../sheet/SheetEditor.vue";
import { newSheet, LEGEND_SAMPLE } from "../sheet/model.js";
import { project } from "../store.js";
import { mapImage, here, legendItems, printPdf } from "./sheetmaps.js";

const maps = { image: mapImage, here, legend: legendItems, pdf: printPdf };
const sheet = ref(newSheet({ format: "A3", title: "Новый лист" }));
const SAMPLE = JSON.stringify(LEGEND_SAMPLE);

/* Открыт проект: карты без места встают туда, где он открыт, условная легенда — по его слоям. */
function adopt() {
  const c = here()?.center, items = legendItems();
  if (!c && !items.length) return;
  const s = JSON.parse(JSON.stringify(sheet.value));
  s.blocks.forEach(b => {
    if (b.kind === "map" && !b.center && c) b.center = c;
    if (b.kind === "legend" && JSON.stringify(b.items) === SAMPLE && items.length) b.items = items;
  });
  sheet.value = s;
}
watch(() => project.name, adopt, { immediate: true });
</script>
