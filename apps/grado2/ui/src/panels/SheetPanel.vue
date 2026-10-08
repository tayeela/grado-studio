<!-- ГРАДО 2 · окно «Макет листа» нового интерфейса: редактор раскладки листа на Konva (src/sheet/SheetEditor.vue)
     во вкладке dockview рядом с картой. Штамп берёт поля альбома открытого проекта (store.js album.meta). Пока лист
     живёт только в окне и в проект не записывается: новый интерфейс — только просмотр. -->
<template>
  <SheetEditor v-model="sheet" :meta="project.album?.meta || {}" :page="{ page_no: 1, page_total: project.album?.sheets?.length || 1 }" />
</template>

<script setup>
import { ref } from "vue";
import SheetEditor from "../sheet/SheetEditor.vue";
import { newSheet } from "../sheet/model.js";
import { project } from "../store.js";

const sheet = ref(newSheet({ format: "A3", title: "Новый лист" }));
</script>
