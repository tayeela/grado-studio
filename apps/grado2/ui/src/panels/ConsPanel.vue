<!-- ГРАДО 2 · окно «Ограничения» нового интерфейса (как web/constraints.js renderCons): что учитывать, параметры
     расчёта, кнопка «Рассчитать ограничения» и журнал — из каких слоёв что взято. Расчёт — constraints.js; результат —
     слои группы «Ограничения» в окне «Слои». -->
<template>
  <div class="pane cons">
    <p class="hint">Запреты вычитаются из пятна застройки; предельная высота ограничивает высоту корпусов. Всё строится из
      загруженных данных и появляется в группе слоёв «Ограничения»: выключите слой — генерация перестанет его учитывать.</p>
    <div class="sect">Что учитывать</div>
    <wa-checkbox v-for="u in USE" :key="u[0]" size="s" :checked="CONS.use[u[0]]" :title="u[2]" @change="e => { CONS.use[u[0]] = e.target.checked; keepCons(); }">{{ u[1] }}</wa-checkbox>
    <div class="sect">Параметры</div>
    <div class="grid">
      <template v-for="n in NUMS" :key="n[0]">
        <label :title="n[5]">{{ n[1] }}</label>
        <wa-number-input size="s" :value="CONS[n[0]]" :min="n[2]" :max="n[3]" :step="n[4]" :title="n[5]" @change="e => setNum(n, e.target)"></wa-number-input>
      </template>
    </div>
    <wa-button size="s" variant="brand" :disabled="!project.territory || !!CONS.running" :loading="!!CONS.running"
               :title="project.territory ? 'Построить запреты и предельную высоту из загруженных данных' : 'Сначала задайте границу территории (окно «Данные»)'"
               @click="computeConstraints"><ShieldCheck :size="14" /> Рассчитать ограничения</wa-button>
    <p v-if="CONS.running" class="busy">{{ CONS.running }}</p>
    <template v-if="CONS.log">
      <div class="sect">Результат</div>
      <ul class="log"><li v-for="(l, i) in CONS.log" :key="i">{{ l }}</li></ul>
    </template>
    <p class="warn">Инсоляция — предпроектная оценка по методам ГОСТ Р 57795-2017 (22 апреля и 22 августа, солнечное время, без первого
      часа после восхода и последнего перед заходом). Не заменяет сертифицированный расчёт для экспертизы. Высота зданий —
      этажность × высота этажа.</p>
  </div>
</template>

<script setup>
import { ShieldCheck } from "@lucide/vue";
import { project } from "../store.js";
import { CONS, computeConstraints, keepCons } from "../constraints.js";

const USE = [
  ["zouit", "ЗОУИТ, СЗЗ, водоохранные, зоны ОКН", "Из загруженных слоёв ЕГРН и ГИС ОГД. Зоны регулирования застройки ОКН не запрещают строить и не учитываются."],
  ["red", "Отступ от красных линий", "Буфер от красных линий ГИС ОГД, СП 42.13330.2016"],
  ["fire", "Сохраняемые здания и противопожарные разрывы", "Все здания, кроме отмеченных «сносим». Разрыв 6/8/10 м по материалу стен, СП 4.13130.2013 табл. 1"],
  ["pzz", "Подзоны ПЗЗ без нового строительства", "Подзоны с нулевыми параметрами (плотность, высота и застроенность — 0)"],
  ["gp", "Природные зоны Генплана", "Природные, озеленённые, парковые зоны, в составе ООПТ. Природно-жилая зона застройку допускает."],
  ["insol", "Инсоляция окон соседей и предельная высота по солнцу", "Расчётные точки на фасадах сохраняемых жилых домов; предельная высота — наибольшая, при которой соседи не теряют норму"],
];
const NUMS = [
  ["redline", "Отступ от КЛ, м", 0, 30, 1, "Расстояние от красной линии до застройки"],
  ["norm", "Норма инсоляции, ч", 1, 3, 0.5, "Норма выполнена при N часах непрерывно или N + 0,5 ч с перерывом (СанПиН 1.2.3685-21)"],
  ["z", "Высота окна, м", 0.5, 30, 0.1, "Высота расчётной точки над землёй: окно нижнего жилого этажа"],
  ["step", "Шаг точек, м", 2, 20, 1, "Через сколько метров по фасаду ставить расчётную точку"],
  ["reveal", "Теневой угол окна, °", 0, 45, 1, "Откосы окна и лоджии: солнце под более острым углом к фасаду в окно не попадает"],
  ["floorH", "Высота этажа, м", 2.7, 4.5, 0.1, "Для высоты существующих зданий и перевода предельной высоты в этажи"],
  ["cell", "Шаг сетки предельной высоты, м", 4, 20, 1, "Размер клетки сетки предельной высоты по солнцу"],
];
/* пустое и вне пределов поля не принимается: значение возвращается к прежнему или к границе */
function setNum(n, el) {
  const v = +el.value;
  if (el.value === "" || !isFinite(v)) { el.value = CONS[n[0]]; return; }
  CONS[n[0]] = Math.min(n[3], Math.max(n[2], v)); el.value = CONS[n[0]]; keepCons();
}
</script>

<style>
.cons wa-checkbox { display: block; margin: 2px 0 !important; font-size: var(--wa-font-size-s); }
.cons .grid { display: grid; grid-template-columns: minmax(0, 1fr) 110px; gap: 3px 8px; align-items: center; margin-bottom: var(--wa-space-s); font-size: var(--wa-font-size-s); }
.cons .grid wa-number-input { margin: 0 !important; }
.cons .busy { color: var(--wa-color-brand-on-quiet); font-size: var(--wa-font-size-xs); }
.cons .log { margin: 0; padding-left: 18px; font-size: var(--wa-font-size-xs); }
.cons .warn { color: var(--wa-color-warning-on-quiet); font-size: var(--wa-font-size-xs); }
</style>
