<!-- ГРАДО 2 · окно «Справка» нового интерфейса (F1): что уже работает в /next/, клавиши и приёмы мыши, поиск по словам —
     как окно «Справка и клавиши» рабочей страницы (web/layers.js renderKeys). Разделы описывают только перенесённые окна;
     команды черчения появятся здесь вместе с командной строкой. -->
<template>
  <div class="pane help">
    <wa-input ref="q" size="s" type="search" placeholder="Найти в справке" with-clear :value="query" @input="e => (query = e.target.value)"
              @keydown.esc.stop="query = ''"></wa-input>
    <section v-for="s in shownSecs" :key="s.title">
      <div class="sect">{{ s.title }}</div>
      <table class="keys"><tr v-for="r in s.rows" :key="r[0]"><td><kbd v-if="s.keys">{{ r[0] }}</kbd><b v-else>{{ r[0] }}</b></td><td>{{ r[1] }}</td></tr></table>
    </section>
    <p v-if="!shownSecs.length" class="hint">В справке нет таких слов. Esc — сбросить поиск.</p>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";

const MOD = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl";
const SECS = [
  { title: "Новый интерфейс", rows: [
    ["Что это", "Тот же проект и тот же файл, что в рабочей странице; окна переезжают по одному. Чего здесь ещё нет — делайте в рабочей странице, правки видны в обеих."],
    ["Окна", "Меню «Окна»: открыть или закрыть окно, «Раскладка по умолчанию». Окно перетаскивается за вкладку: к краю — встроить, на карту — сделать плавающим."],
    ["Проект", "Сохраняется сам через 1,5 с после правки. Меню «Проект»: открыть, сохранить, сохранить как, новый, файл .grado2 с диска и на диск."],
    ["Слои", "Окно «Слои»: «+» — новый слой, перетаскивание — порядок и группы, двойной щелчок — переименовать, «⋯» или правая кнопка — меню слоя."],
    ["Оформление", "Окно «Свойства»: единое, категории, диапазоны, правила, ЛГР; контур, прозрачность, штриховка, подписи, видимость по масштабу."],
    ["Объекты", "Щелчок по объекту — окно «Объект» с площадью в МСК и атрибутами. «Таблица атрибутов» — все объекты слоя, поиск и правка ячеек."],
    ["Виды", "Окно «Виды»: запомнить видимые слои, оформление и подложку под именем и вернуть их одним щелчком."],
    ["Выгрузка", "Меню «Выгрузка»: чертёж DXF и GeoJSON для QGIS в МСК. PDF, PPTX, ГИС ОГД и Excel — пока в рабочей странице."],
  ] },
  { title: "Выбор", keys: true, rows: [
    ["щелчок", "выбрать объект; по пустому месту — снять выбор"],
    ["Shift+щелчок", "добавить к выбору или убрать из него"],
    ["Shift+тянуть", "рамка: добавить объекты к выбору"],
    [`${MOD}+A`, "все объекты текущего слоя"],
    ["Esc", "снять выбор"],
  ] },
  { title: "Правка", keys: true, rows: [
    ["Del, Backspace", "удалить выбранные объекты"],
    [`${MOD}+Z`, "отменить правку слоёв, групп, оформления, видов и объектов"],
    [`${MOD}+Shift+Z, ${MOD}+Y`, "вернуть отменённое"],
    ["двойной щелчок", "в таблице — править ячейку; в окне «Слои» — переименовать"],
  ] },
  { title: "Проект и окна", keys: true, rows: [
    [`${MOD}+S`, "сохранить проект"],
    ["F1", "это окно"],
  ] },
  { title: "Карта", keys: true, rows: [
    ["колесо, щипок", "масштаб"],
    ["тянуть", "сдвиг карты"],
    ["Подложка", "строка состояния внизу: схема OSM, спутник Esri, Sentinel-2"],
  ] },
];

const query = ref(""), q = ref(null);
const norm = s => s.toLowerCase().replace(/ё/g, "е");
const shownSecs = computed(() => {
  const w = norm(query.value.trim()); if (!w) return SECS;
  return SECS.map(s => norm(s.title).includes(w) ? s : { ...s, rows: s.rows.filter(r => norm(r.join(" ")).includes(w)) }).filter(s => s.rows.length);
});
defineExpose({ focus: () => q.value?.focus() });
</script>

<style>
.help wa-input { margin-bottom: var(--wa-space-s); }
.help .sect { margin: var(--wa-space-m) 0 4px; font-weight: 600; font-size: var(--wa-font-size-s); }
.help table.keys { border-collapse: collapse; width: 100%; font-size: var(--wa-font-size-s); }
.help table.keys td { padding: 3px 6px; border-bottom: 1px solid var(--g-line); vertical-align: top; }
.help table.keys td:first-child { width: 34%; white-space: nowrap; }
.help kbd { font: inherit; font-size: var(--wa-font-size-xs); padding: 1px 5px; border: 1px solid var(--g-line); border-bottom-width: 2px; border-radius: 4px; background: var(--g-bar); }
</style>
