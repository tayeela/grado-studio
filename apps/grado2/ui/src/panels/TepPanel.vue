<!-- ГРАДО 2 · окно «Показатели (ТЭП)» нового интерфейса (как web/app.js renderTep): территория расчёта (район, зона,
     K1, K2, ТиНАО, тип территории, проценты — правятся здесь), цель по ПЗЗ, итог эскиза и показатели «Калькулятора 2.0»
     по группам. Расчёт — блок ТЭП схемы (graph.js → tep.js → /api/tep); правки идут в параметры блока, как в рабочей странице. -->
<template>
  <div class="pane tep">
    <p v-if="!project.territory" class="hint">Показатели появятся, когда будет граница территории: окно «Данные» → «Нарисовать границу» или «Пример».</p>
    <p v-else-if="!tn" class="hint">В схеме расчёта нет блока «ТЭП КРТ».</p>
    <p v-else-if="!t" class="hint">Считаю…</p>
    <template v-else>
      <button v-if="t.constantsChanged?.length" class="normsline" title="Открыть окно «Нормативы расчёта»" @click="winApi.open('norms')">Нормативы изменены вручную: {{ t.constantsChanged.length }}</button>
      <div class="sect">Территория расчёта</div>
      <div class="tp">
        <label>Район</label><div><b>{{ tp.district || (rtBusy ? "определяется…" : "не определён") }}</b> <small v-if="tp.insideTtk">внутри ТТК</small>
          <small v-if="(tp.districts || []).length > 1" class="sub" title="Район, зона образования, K2 и ТиНАО взяты у района с наибольшей долей площади границы">{{ shares }}</small></div>
        <label title="2151-ПП п. 1.3.2: нормы ДОО и школ">Образование</label>
        <select :value="String(tp.zone)" aria-label="Образовательная зона" @change="e => setTp('zone', +e.target.value)"><option value="1">зона 1 — 44 / 90</option><option value="2">зона 2 — 63 / 124</option></select>
        <label title="945-ПП прил. 6: пешая доступность входа в метро, МЦК, МЦД">K1</label>
        <div><select :value="String(tp.k1)" aria-label="K1" @change="e => setTp('k1', +e.target.value)"><option value="0.75">0,75 · до 1200 м</option><option value="0.9">0,9 · 1200–2200 м</option><option value="1">1,0 · дальше</option></select>
          <small v-if="tp.walk != null" class="sub" :title="tp.walkRoute ? 'пешеходный маршрут по улицам и дорожкам OSM от центра территории' : 'прямое расстояние до ближайшего входа или станции метро, МЦК, МЦД × 1,3 (маршрут по улицам считается)'">{{ walkLine }}</small></div>
        <label title="945-ПП прил. 3: деловая активность района">K2</label>
        <div class="inl"><select :value="String(tp.k2)" aria-label="K2" @change="e => setTp('k2', +e.target.value)"><option v-for="v in [0.2, 0.5, 0.7, 0.9]" :key="v" :value="String(v)">{{ fmt(v, 1) }}</option></select>
          <label title="Отметьте, если территория в Троицком или Новомосковском округе: от этого зависит расчёт показателей"><input type="checkbox" :checked="!!tp.tinao" @change="e => setTp('tinao', e.target.checked ? 1 : 0)"> ТиНАО</label></div>
        <label title="2152-ПП табл. 1.4.2">Жилые территории</label>
        <select :value="String(tp.mode)" aria-label="Тип территории" @change="e => setTp('mode', +e.target.value)"><option v-for="(l, v) in MODES" :key="v" :value="v">{{ l }}</option></select>
        <label title="Доля встроенно-пристроенных нежилых помещений в МКД; по умолчанию 94 / 6">Нежилое в МКД, %</label>
        <input type="number" min="0" max="100" aria-label="Нежилое в МКД, %" :value="Number(tp.nonres)" @change="e => setTp('nonres', clamp(e.target, 0, 100))">
        <label title="Незастраиваемая территория в составе жилой (баланс территории)">Незастраиваемая, %</label>
        <input type="number" min="0" max="90" aria-label="Незастраиваемая, %" :value="Number(tp.unbuilt)" @change="e => setTp('unbuilt', clamp(e.target, 0, 90))">
        <label title="Нормы расчёта: 2151-ПП, 2152-ПП, 1557-ПП, 945-ПП. Поля уже заполнены действующими значениями; их можно изменить до расчёта">Нормативы</label>
        <div><wa-button size="s" appearance="outlined" title="Открыть окно «Нормативы расчёта»" @click="winApi.open('norms')">Нормативы…</wa-button></div>
        <template v-if="pz">
          <label title="Средняя предельная плотность подзон ПЗЗ внутри границы, взвешенная по площади">Цель по ПЗЗ</label>
          <div v-if="pz.value == null"><small>в подзонах внутри границы плотность не установлена числом («-», «Ф»)</small></div>
          <div v-else><b>{{ fmt(pz.value, 1) }}</b> <small>тыс. м²/га · {{ Math.round(pz.share * 100) }} % границы<template v-if="pz.vals.length > 1"> · подзоны {{ pz.vals.map(v => fmt(v, 1)).join(", ") }}</template></small>
            <wa-button v-if="Math.abs(t.target - pz.value) >= 0.5" size="s" appearance="outlined" title="Поставить цель плотности эскиза по ПЗЗ" @click="takePzzTarget()">взять цель</wa-button></div>
        </template>
      </div>
      <div class="row">
        <wa-button v-if="!(tp.auto && !tp.zoneSet)" size="s" appearance="outlined" title="Снова взять зону, K1, K2 и ТиНАО по району территории" @click="byDistrict">по району</wa-button>
        <wa-button v-if="tp.mode !== 1 || tp.nonres !== 6 || tp.unbuilt !== 25" size="s" appearance="outlined" title="Преобразование, нежилое 6 %, незастраиваемая 25 % — как в «Калькуляторе 2.0» по умолчанию" @click="resetTp">сбросить тип и проценты</wa-button>
      </div>
      <p v-for="(x, i) in tp.notes || []" :key="'n' + i" class="warn">{{ x }}</p>

      <div class="sect">Эскиз</div>
      <div v-if="noSk" class="warn box" role="status"><b>Эскиз не построен</b> — показатели новой застройки появятся после расчёта. Выберите типологию в окне «Эскиз» и нажмите «Построить эскиз». Территория и сохраняемая застройка ниже уже посчитаны.
        <div><wa-button size="s" appearance="outlined" @click="winApi.open('sketch')">Открыть «Эскиз»</wa-button></div></div>
      <div v-else class="resline" title="Площади участков — минимум по таблице норм; здания, СПП и плотность от резерва не меняются">{{ reserveSummary(t) }}</div>
      <table><tbody>
        <tr v-for="r in sketchRows" :key="r[0]"><td>{{ r[0] }}</td><td class="n" :class="r[2]">{{ r[1] }}</td></tr>
      </tbody></table>
      <template v-for="[g, ms] in groups" :key="g">
        <div class="sect">{{ g }}</div>
        <table><tbody>
          <tr v-for="(m, i) in ms" :key="i"><td>{{ m.title }}</td><td class="n">{{ noSk && !m.value ? "—" : fmt(m.value, m.precision ?? 3) + " " + m.unit }}</td></tr>
        </tbody></table>
        <template v-if="g === 'Резерв участков'"><p v-for="(x, i) in resWarns" :key="'w' + i" class="warn">{{ x }}</p></template>
      </template>
      <p class="hint">Методика «Калькулятора 2.0» (Москва): 2151-ПП, 2150-ПП, 2152-ПП, 1557-ПП, 945-ПП. Население, соцобъекты и машино-места — от новой застройки;
        люди, места и машино-места округлены вверх, площади — математически (СПП — 2 знака, остальное — 3). K1 — по пешеходному маршруту по улицам OSM от центра
        территории до ближайшего входа или станции (пока маршрут считается — прямое расстояние × 1,3).<template v-if="t.existKey === 'osm.buildings'"> Существующие здания взяты из OSM: ЕГРН не загружен.</template></p>
    </template>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { project, winApi } from "../store.js";
import { RESULT, edited, tick } from "../graph.js";
import { pzzTarget, reserveSummary, tepParams } from "../tep.js";
import { reserveState, takePzzTarget } from "../sketch.js";
import { fmt } from "../geom.js";

const GROUP_ORDER = ["Основные показатели", "СПП в ГНС", "Наземная площадь", "Единый показатель", "Баланс территории", "Социальные объекты", "Участки социальных объектов", "Резерв участков", "Обслуживание", "Машино-места", "Элементы жилых территорий"];
const MODES = { 1: "преобразование", 2: "реконструкция", 3: "малоэтажный комплекс" };
const tn = computed(() => { void tick.value; return RESULT.tepNode; });
const t = computed(() => { void tick.value; return RESULT.tep; });
const tp = computed(() => { void tick.value; return tn.value ? tepParams(tn.value) : {}; });
const rtBusy = computed(() => { void tick.value; return !tp.value.notes?.length && tp.value.rev === -1; });
const pz = computed(() => { void tick.value; return pzzTarget(); });
const noSk = computed(() => !(t.value?.n > 0));
const resWarns = computed(() => { void tick.value; return reserveState().warns; });
// «по большей доле площади: Хорошёвский 62 %, Беговой 38 %» — не больше трёх районов, остальные «и ещё N»
const shares = computed(() => { const ds = tp.value.districts || []; return "по большей доле площади: " + ds.slice(0, 3).map(d => `${d.name} ${d.share > 0 && d.share < .005 ? "<1" : Math.round(d.share * 100)} %`).join(", ") + (ds.length > 3 ? ` и ещё ${ds.length - 3}` : ""); });
const walkLine = computed(() => { const p = tp.value; return `${p.walkRoute ? "" : "≈ "}${fmt(p.walk)} м ${p.walkRoute ? "пешком по улицам" : "до станции"}${p.station ? ` · ${p.station}` : ""}${p.routing ? " · маршрут по улицам считается (первый раз до 2 минут)…" : ""}`; });
const sketchRows = computed(() => {
  const x = t.value, no = noSk.value, val = (v, s) => no && !v ? "—" : s, dCls = x.density > x.target * 1.05 ? "bad" : x.density < x.target * .8 ? "warnc" : "good";
  return [["Новые корпуса", x.n], ["СПП новая", val(x.sppNew, fmt(x.sppNew / 1000, 2) + " тыс. м²")], ["СПП сохраняемая", fmt(x.sppKept / 1000, 2) + " тыс. м²"],
    ["Плотность итоговая", val(x.density, fmt(x.density, 2) + " тыс. м²/га"), no && !x.density ? "" : dCls], ["Цель", fmt(x.target) + " тыс. м²/га"],
    ["Застроенность", val(x.cover, fmt(x.cover * 100, 1) + " %")], ["Сохраняется", x.kept.length + " зд."], ["Под снос", x.demolN + " зд. · " + fmt(x.demolSpp / 1000, 2) + " тыс. м²"]];
});
const groups = computed(() => {
  const by = {}; (t.value?.metrics || []).forEach(m => (by[m.group || "Прочее"] ||= []).push(m));
  const rank = g => (GROUP_ORDER.indexOf(g) + 99) % 99;
  return Object.entries(by).sort((a, b) => rank(a[0]) - rank(b[0]));
});

const clamp = (el, lo, hi) => { const v = +el.value; const r = el.value === "" || !isFinite(v) ? null : Math.min(hi, Math.max(lo, v)); if (r != null) el.value = r; return r; };
function setTp(k, v) {
  if (v == null || !tn.value) return; const p = tepParams(tn.value);
  p[k] = v;
  if (["k1", "k2", "tinao"].includes(k)) p.auto = false;
  if (k === "zone") p.zoneSet = true;        // зона правится отдельно от K1, K2, ТиНАО: p.auto не трогаем
  edited();
}
function byDistrict() { const p = tepParams(tn.value); p.auto = true; if (p.zoneSet) { delete p.zoneSet; p.zone = p.zoneDist ?? p.zone; } p.rev = -1; edited(); }
function resetTp() { Object.assign(tepParams(tn.value), { mode: 1, nonres: 6, unbuilt: 25 }); edited(); }
</script>

<style>
.tep table { border-collapse: collapse; width: 100%; font-size: var(--wa-font-size-s); }
.tep td { padding: 2px 6px; border-bottom: 1px solid var(--g-line); text-align: left; }
.tep td.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.tep td.good { color: var(--wa-color-success-on-quiet); } .tep td.bad { color: var(--wa-color-danger-on-quiet); } .tep td.warnc { color: var(--wa-color-warning-on-quiet); }
.tep .tp { display: grid; grid-template-columns: 130px minmax(0, 1fr); gap: 4px 8px; align-items: center; font-size: var(--wa-font-size-s); }
.tep .tp > label { color: var(--g-muted); }
.tep .tp select, .tep .tp input[type=number] { justify-self: start; font: inherit; padding: 1px 4px; border: 1px solid var(--g-line); border-radius: 4px; background: var(--wa-color-surface-default); color: inherit; max-width: 100%; }
.tep .tp input[type=number] { width: 64px; }
.tep .tp .inl { display: flex; align-items: center; gap: 10px; }
.tep .tp .inl label { display: flex; align-items: center; gap: 4px; cursor: pointer; }
.tep .tp .sub { display: block; color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.tep .row { display: flex; gap: 6px; flex-wrap: wrap; margin: 6px 0; }
.tep .warn { color: var(--wa-color-warning-on-quiet); font-size: var(--wa-font-size-xs); margin: 3px 0; }
.tep .warn.box { border: 1px solid var(--wa-color-warning-border-quiet); border-radius: 6px; padding: 6px 8px; background: var(--wa-color-warning-fill-quiet); }
.tep .warn.box div { margin-top: 4px; }
.tep .resline { font-size: var(--wa-font-size-xs); color: var(--g-muted); margin: 2px 0 4px; }
.tep .normsline { display: block; width: 100%; text-align: left; border: 1px solid var(--wa-color-warning-border-quiet); background: var(--wa-color-warning-fill-quiet); color: var(--wa-color-warning-on-quiet);
  border-radius: 6px; padding: 4px 8px; cursor: pointer; font: inherit; font-size: var(--wa-font-size-xs); margin-bottom: 4px; }
</style>
