<!-- ГРАДО 2 · окно «Нормативы расчёта» нового интерфейса (как web/norms.js): условия проекта (образовательная зона, свободные
     места рядом) и нормы пресета «Калькулятора 2.0» по группам, предзаполненные действующими значениями (GET /api/tep/norms).
     Правка хранится разницей в параметрах блока ТЭП (tp.constants, tp.free, tp.zone) — тот же файл, что у рабочей страницы. -->
<template>
  <div class="pane normsp">
    <p v-if="!tn" class="hint">В схеме расчёта нет блока «ТЭП КРТ».</p>
    <p v-else-if="NORMS.error && !cat" class="hint">Нормативы не загрузились: {{ NORMS.error }}. <wa-button size="s" appearance="outlined" @click="load">Ещё раз</wa-button></p>
    <p v-else-if="!cat" class="hint">Загружаю нормативы…</p>
    <template v-else>
      <section class="ncond">
        <div class="nct">Условия проекта</div>
        <div class="nrow">
          <div class="nt">Образовательная зона</div>
          <div class="nin"><select :value="String(tp.zone)" aria-label="Образовательная зона" @change="e => setZone(+e.target.value)"><option value="1">зона 1</option><option value="2">зона 2</option></select></div>
          <div class="ns">{{ zoneSrc }} <wa-button v-if="zoneManual && tp.zoneDist != null" size="s" appearance="outlined" title="Снова взять зону по району территории" @click="zoneAuto">по району</wa-button></div>
        </div>
        <div v-for="[k, title, unit, hint] in FREE" :key="k" class="nrow" :class="{ bad: bad['f' + k] }">
          <div class="nt">{{ title }}</div>
          <div class="nin"><input type="number" step="1" min="0" :max="FREE_MAX" :value="draft['f' + k] ?? tp.free?.[k] ?? 0" :aria-label="title" @input="e => onFree(k, e.target)" @change="e => onFree(k, e.target, true)"><span class="nu">{{ unit }}</span></div>
          <div class="ns">{{ hint }}</div>
          <div v-if="bad['f' + k]" class="nerr">Допустимо целое число от 0 до 100 000</div>
        </div>
      </section>
      <p class="hint">Действующие значения на {{ newest }}. Измените число, если норматив обновился, — расчёт пересчитается.</p>
      <div class="nbar">
        <wa-input size="s" type="search" placeholder="Найти норматив: сад, стоянка…" aria-label="Найти норматив" :value="query" @input="e => (query = e.target.value)"></wa-input>
        <wa-button size="s" appearance="outlined" :disabled="!changedN" title="Убрать все ручные правки и взять действующие значения" @click="resetAll">Вернуть все действующие</wa-button>
      </div>
      <details v-for="g in shownGroups" :key="g.name" class="ngrp" open>
        <summary>{{ g.name }} <small v-if="g.changed">изменено: {{ g.changed }}</small></summary>
        <div v-for="n in g.items" :key="n.id" class="nrow" :class="{ chg: n.id in consts, bad: bad[n.id] }">
          <div class="nt">{{ n.title }}</div>
          <div class="nin">
            <input type="number" step="any" :min="n.min" :max="n.max" :value="draft[n.id] ?? (n.id in consts ? consts[n.id] : n.value)" :aria-label="n.title" @input="e => onNorm(n, e.target)" @change="e => onNorm(n, e.target, true)">
            <span class="nu">{{ n.unit }}</span>
            <button v-if="n.id in consts" class="nrev" title="Вернуть действующее" aria-label="Вернуть действующее" @click="revert(n)"><RotateCcw :size="13" /></button>
          </div>
          <div class="ns">{{ n.source }}<template v-if="n.edition">, ред. {{ n.edition }}</template></div>
          <div v-if="n.id in consts" class="nch">действующее: {{ num(n.value) }}</div>
          <div v-if="bad[n.id]" class="nerr">Допустимо от {{ num(n.min) }} до {{ num(n.max) }}</div>
        </div>
      </details>
      <p v-if="!shownGroups.length" class="hint">Ничего не найдено.</p>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { RotateCcw } from "@lucide/vue";
import { notice } from "../project.js";
import { RESULT, edited, tick } from "../graph.js";
import { NORMS, cleanNorms, loadNorms, tepParams } from "../tep.js";

const FREE = [["doo", "Свободные места в ДОО", "мест", "Места в существующих детских садах рядом, которые не нужны нынешним жителям. Они уменьшают участок, который нужно зарезервировать."],
  ["school", "Свободные места в школах", "мест", "Места в существующих школах рядом, которые не нужны нынешним жителям. Они уменьшают участок школы."],
  ["clinic", "Свободные посещения в смену в поликлиниках", "посещ. в смену", "Незанятая мощность существующих поликлиник рядом. Если свободных нет, оставьте 0."]];
const FREE_MAX = 100000;
const cat = ref(null), query = ref(""), bad = reactive({}), timers = {};
const draft = reactive({});                 // набранное, но ещё не принятое (неверное или ждёт 0,45 с): перерисовка его не стирает
const num = v => Number(v).toLocaleString("ru-RU", { maximumFractionDigits: 6 });
const fold = s => String(s || "").toLowerCase().replace(/ё/g, "е");
const tn = computed(() => { void tick.value; return RESULT.tepNode; });
const tp = computed(() => { void tick.value; return tn.value ? tepParams(tn.value) : {}; });
const consts = computed(() => { void tick.value; return tp.value.constants || {}; });
const changedN = computed(() => Object.keys(consts.value).length);
const q = computed(() => fold(query.value.trim()));
const newest = computed(() => cat.value?.norms.map(n => n.edition).filter(Boolean).map(e => ({ e, k: e.split(".").reverse().join("") })).sort((a, b) => b.k.localeCompare(a.k))[0]?.e || "—");
const shownGroups = computed(() => {
  const out = [];
  for (const n of cat.value?.norms || []) {
    if (q.value && !fold(n.title).includes(q.value)) continue;
    let g = out.find(x => x.name === n.group); if (!g) out.push(g = { name: n.group, items: [], changed: 0 });
    g.items.push(n); if (n.id in consts.value) g.changed++;
  }
  return out;
});
// вручную: выбрана здесь или в «Показателях» (zoneSet), либо в старом проекте зона расходится с зоной района
const zoneManual = computed(() => !!tp.value.zoneSet || (tp.value.zoneDist != null && tp.value.zone !== tp.value.zoneDist));
const zoneSrc = computed(() => { const p = tp.value;
  if (zoneManual.value) return "выбрана вручную";
  if (p.zoneNote) return "зона 2 принята: район не в списках 2151-ПП";
  return p.district ? `по району ${p.district}` : p.rev === -1 ? "район определяется…" : "район не определён — выберите зону"; });

function load() {
  loadNorms().then(j => { cat.value = j; clean(); }).catch(() => { /* текст ошибки — NORMS.error */ });
}
/* правки из проекта, убранные из пресета или вне пределов, отбрасываются с сообщением */
function clean() {
  if (!tn.value) return; const bad = cleanNorms(tepParams(tn.value)); if (!bad.length) return;
  notice.value = bad.length === 1 ? `Норматив «${bad[0]}» из проекта убран из расчёта или вне допустимых пределов — взято действующее значение`
    : `Нормативов из проекта убрано из расчёта или вне допустимых пределов: ${bad.length} — взяты действующие значения`;
  edited();
}
onMounted(load);
watch(tn, () => { if (cat.value) clean(); });

function apply(id, v) {
  delete draft[id];
  const p = tepParams(tn.value), n = NORMS.by[id], o = p.constants ||= {};
  if (v === n.value) delete o[id]; else o[id] = v;
  if (!Object.keys(o).length) delete p.constants;
  edited();
}
function onNorm(n, el, now) {
  const v = Number(el.value), ok = !el.validity?.badInput && el.value.trim() !== "" && Number.isFinite(v) && v >= n.min && v <= n.max;
  bad[n.id] = !ok; draft[n.id] = el.value; clearTimeout(timers[n.id]);
  if (ok) { if (now) apply(n.id, v); else timers[n.id] = setTimeout(() => apply(n.id, v), 450); }
}
function revert(n) { bad[n.id] = false; delete draft[n.id]; clearTimeout(timers[n.id]); apply(n.id, n.value); }
function resetAll() { delete tepParams(tn.value).constants; Object.keys(bad).forEach(k => delete bad[k]); Object.keys(draft).forEach(k => delete draft[k]); edited(); }
function onFree(k, el, now) {
  const v = Number(el.value), ok = !el.validity?.badInput && el.value.trim() !== "" && Number.isInteger(v) && v >= 0 && v <= FREE_MAX;
  bad["f" + k] = !ok; draft["f" + k] = el.value; clearTimeout(timers["f" + k]);
  const go = () => { delete draft["f" + k]; const p = tepParams(tn.value); if ((p.free?.[k] ?? 0) === v) return; (p.free ||= {})[k] = v; edited(); };
  if (ok) { if (now) go(); else timers["f" + k] = setTimeout(go, 450); }
}
function setZone(z) { const p = tepParams(tn.value); if (p.zoneSet && p.zone === z) return; p.zone = z; p.zoneSet = true; edited(); }   // p.auto не трогаем: K1, K2, ТиНАО остаются «по району»
function zoneAuto() { const p = tepParams(tn.value); delete p.zoneSet; p.zone = p.zoneDist ?? p.zone; edited(); }
</script>

<style>
.normsp .ncond { border: 1px solid var(--g-line); border-radius: 6px; padding: 4px 8px 6px; margin-bottom: 6px; }
.normsp .nct { font-weight: 600; font-size: var(--wa-font-size-s); margin: 2px 0 4px; }
.normsp .nbar { display: flex; gap: 6px; align-items: center; margin: 4px 0 6px; }
.normsp .nbar wa-input { flex: 1; margin: 0 !important; }
.normsp .ngrp { margin: 4px 0; }
.normsp .ngrp summary { font-weight: 600; font-size: var(--wa-font-size-s); cursor: pointer; padding: 3px 0; }
.normsp .ngrp summary small { font-weight: 400; color: var(--wa-color-warning-on-quiet); margin-left: 6px; }
.normsp .nrow { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 1px 8px; padding: 4px 0; border-bottom: 1px solid var(--g-line); font-size: var(--wa-font-size-s); }
.normsp .nrow.chg .nt { font-weight: 600; }
.normsp .nrow .nin { display: flex; align-items: center; gap: 4px; grid-row: span 2; }
.normsp .nrow input, .normsp .nrow select { font: inherit; width: 90px; padding: 1px 4px; border: 1px solid var(--g-line); border-radius: 4px; background: var(--wa-color-surface-default); color: inherit; }
.normsp .nrow.bad input { border-color: var(--wa-color-danger-border-loud); }
.normsp .nrow .nu { color: var(--g-muted); font-size: var(--wa-font-size-xs); min-width: 54px; }
.normsp .nrow .ns, .normsp .nrow .nch { color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.normsp .nrow .nch { color: var(--wa-color-warning-on-quiet); }
.normsp .nrow .nerr { color: var(--wa-color-danger-on-quiet); font-size: var(--wa-font-size-xs); grid-column: 1 / -1; }
.normsp .nrev { border: 0; background: none; cursor: pointer; color: inherit; padding: 0 2px; display: inline-flex; }
</style>
