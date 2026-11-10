<!-- ГРАДО · окно, которое переезжает на следующих шагах плана: что в нём будет и когда. Пока все эти окна работают
     в нынешнем интерфейсе по адресу /next/. -->
<template>
  <div class="g3-panel">
    <p>{{ params.params?.stub || "Это окно переезжает на следующих шагах." }}</p>
    <p class="g3-muted">Пока оно работает в нынешнем интерфейсе: <a href="/next/" target="_blank">/next/</a>.</p>
  </div>
</template>

<script setup lang="ts">
defineProps<{ params: { params?: { stub?: string } } }>();
</script>
