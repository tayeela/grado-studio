<!-- ГРАДО 2 · окно «Показатели (ТЭП)» нового интерфейса: таблица показателей.
     Образец: числа условные; при переносе таблица возьмёт расчёт ТЭП проекта (Tabulator, карта ядер). -->
<template>
  <div class="pane tep">
    <table>
      <thead><tr><th>Показатель</th><th>Ед.</th><th>Существующее</th><th>Эскиз</th></tr></thead>
      <tbody>
        <tr v-for="r in ROWS" :key="r[0]"><td>{{ r[0] }}</td><td>{{ r[1] }}</td><td class="n">{{ r[2] }}</td><td class="n">{{ r[3] }}</td></tr>
      </tbody>
    </table>
    <p class="hint">Образец: числа условные, расчёта нет.</p>
  </div>
</template>

<script setup>
const ROWS = [
  ["Площадь территории", "га", "—", "—"],
  ["Суммарная поэтажная площадь", "тыс. м²", "—", "—"],
  ["Плотность застройки", "тыс. м²/га", "—", "—"],
  ["Жилой фонд", "тыс. м²", "—", "—"],
  ["Места в ДОО", "мест", "—", "—"],
  ["Места в школах", "мест", "—", "—"],
  ["Машино-места", "м/м", "—", "—"],
];
</script>

<style>
.tep table { border-collapse: collapse; width: 100%; font-size: var(--wa-font-size-s); }
.tep th, .tep td { padding: 3px 8px; border-bottom: 1px solid var(--g-line); text-align: left; }
.tep th:nth-child(n+3) { text-align: right; }
.tep th { font-weight: 600; color: var(--g-muted); background: var(--g-bar); position: sticky; top: 0; }
.tep td.n { text-align: right; font-variant-numeric: tabular-nums; }
</style>
