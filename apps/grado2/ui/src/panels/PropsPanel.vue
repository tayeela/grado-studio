<!-- ГРАДО 2 · окно «Свойства» нового интерфейса: оформление текущего слоя, как правая панель «Стиль» рабочей страницы
     (web/layers.js renderStyle): единое, категории, диапазоны, правила, знаки ЛГР; контур, прозрачность, видимость по масштабу,
     роль в расчётах, штриховка, подписи. Правка меняет слой в store.project — карта перерисовывается сама,
     project.js записывает правку в проект (автосохранение, Ctrl+S). Расчёт классов и цветов — symbology.js. -->
<template>
  <div class="pane props" v-if="l">
    <div class="ph"><span class="sw" :class="l.geom" :style="{ '--c': swatchColor(st) }"></span><b>{{ l.title || l.key }}</b></div>
    <div class="sub">{{ GEOM[l.geom] || l.geom }} · {{ plural(count, ["объект", "объекта", "объектов"]) }}</div>

    <!-- способ оформления — выпадающим списком: четыре-пять кнопок в ряд не помещаются в узкое окно -->
    <div class="modes">
      <span class="lbl">Оформление</span>
      <wa-select size="s" :value="st.mode" aria-label="Способ оформления" @change="e => setMode(e.target.value)">
        <wa-option v-for="[m, t] in modes" :key="m" :value="m">{{ t }}</wa-option>
      </wa-select>
    </div>

    <template v-if="st.mode === 'lgr'">
      <p class="hint">Знаки красных линий и ЛГР по стандарту REDLN97: тип линии выбирается по коду линии объекта.
        <a href="/linetypes.html" target="_blank">Каталог типов</a>.</p>
    </template>

    <template v-else-if="st.mode === 'single'">
      <div class="row">
        <wa-color-picker size="s" :label="l.geom === 'poly' ? 'Заливка' : 'Цвет'" :value="st.fill" @change="e => (st.fill = e.target.value)"></wa-color-picker>
        <wa-checkbox v-if="l.geom === 'poly'" size="s" :checked="!!st.hatch" @change="e => (st.hatch = e.target.checked)">штриховка</wa-checkbox>
      </div>
    </template>

    <template v-else-if="st.mode === 'cat'">
      <div class="row">
        <wa-select size="s" label="Поле" :value="st.cat.field" @change="e => { st.cat.field = e.target.value; assignCats(st, fc, false); }">
          <wa-option v-for="k in (txtFields.length ? txtFields : fields)" :key="k" :value="k">{{ k }}</wa-option>
        </wa-select>
        <wa-button size="s" appearance="outlined" title="Как «Классифицировать» в QGIS: заново собрать значения поля и раздать цвета"
                   @click="assignCats(st, fc, false)">Классифицировать</wa-button>
      </div>
      <table class="cl">
        <tr v-for="[v, n] in cats" :key="v" :class="{ off: st.cat.off.includes(v) }">
          <td><wa-checkbox size="s" :checked="!st.cat.off.includes(v)" title="Показывать" @change="e => catOff(v, !e.target.checked)"></wa-checkbox></td>
          <td><wa-color-picker size="s" :value="st.cat.colors[v] || OTHER" @change="e => (st.cat.colors[v] = e.target.value)"></wa-color-picker></td>
          <td class="v">{{ v || "—" }}</td><td class="n">{{ n }}</td>
        </tr>
      </table>
      <p v-if="catsAll > cats.length" class="hint">Показаны 80 значений из {{ catsAll }}.</p>
      <wa-checkbox v-if="l.geom === 'poly'" size="s" :checked="!!st.hatch" @change="e => (st.hatch = e.target.checked)">штриховка вместо заливки</wa-checkbox>
    </template>

    <template v-else-if="st.mode === 'grad'">
      <p v-if="!nf.length" class="hint">В слое нет числовых полей.</p>
      <template v-else>
        <wa-select size="s" label="Поле" :value="st.grad.field" @change="e => (st.grad.field = e.target.value)">
          <wa-option v-for="k in nf" :key="k" :value="k">{{ k }}</wa-option>
        </wa-select>
        <div class="row">
          <wa-select size="s" label="Классы" :value="String(st.grad.n)" @change="e => (st.grad.n = +e.target.value)">
            <wa-option v-for="n in [3, 4, 5, 6]" :key="n" :value="String(n)">{{ n }}</wa-option>
          </wa-select>
          <wa-select size="s" label="Способ" :value="st.grad.method" @change="e => (st.grad.method = e.target.value)">
            <wa-option value="quantile">Квантили</wa-option><wa-option value="equal">Равные интервалы</wa-option>
          </wa-select>
        </div>
        <div class="lbl">Шкала</div>
        <div class="ramps">
          <button v-for="(cs, r) in RAMPS" :key="r" class="ramp" :aria-pressed="st.grad.ramp === r" :title="'Шкала ' + RAMP_TITLES[r]" @click="st.grad.ramp = r">
            <i v-for="c in cs" :key="c" :style="{ background: c }"></i>
          </button>
        </div>
        <table class="cl">
          <tr v-for="it in legend" :key="it.v"><td><span class="chip" :style="{ background: it.c }"></span></td><td class="v">{{ it.v }}</td><td class="n">{{ it.n || "" }}</td></tr>
        </table>
      </template>
    </template>

    <template v-else-if="st.mode === 'rules'">
      <div v-for="(r, i) in st.rules.list" :key="i" class="rule">
        <div class="row">
          <wa-select size="s" :value="r.field" placeholder="Поле" @change="e => (r.field = e.target.value)">
            <wa-option v-for="k in fields" :key="k" :value="k">{{ k }}</wa-option>
          </wa-select>
          <wa-select size="s" class="op" :value="r.op" @change="e => (r.op = e.target.value)">
            <wa-option v-for="o in OPS" :key="o" :value="o">{{ o }}</wa-option>
          </wa-select>
          <wa-input size="s" :value="r.val" placeholder="значение" @change="e => (r.val = e.target.value)"></wa-input>
        </div>
        <div class="row">
          <wa-color-picker size="s" :value="r.fill" @change="e => (r.fill = e.target.value)"></wa-color-picker>
          <wa-checkbox v-if="l.geom === 'poly'" size="s" :checked="!!r.hatch" @change="e => (r.hatch = e.target.checked)">штриховка</wa-checkbox>
          <span class="grow"></span><span class="n" title="Объектов, подходящих под правило">{{ plural(ruleCount(r, fc), ["объект", "объекта", "объектов"]) }}</span>
          <wa-button size="s" appearance="plain" title="Удалить правило" @click="st.rules.list.splice(i, 1)"><X :size="14" /></wa-button>
        </div>
      </div>
      <wa-button size="s" appearance="outlined" @click="st.rules.list.push({ field: fields[0] || '', op: '=', val: '', fill: CAT[st.rules.list.length % CAT.length] })"><Plus :size="14" /> Правило</wa-button>
      <div class="row rule">
        <span>Остальные</span>
        <wa-color-picker size="s" :value="st.rules.elseFill" @change="e => (st.rules.elseFill = e.target.value)"></wa-color-picker>
        <wa-checkbox size="s" :checked="!!st.rules.elseHide" @change="e => (st.rules.elseHide = e.target.checked)">скрыть</wa-checkbox>
      </div>
    </template>

    <h3>Контур, прозрачность, подписи</h3>
    <div class="row" v-if="l.geom === 'poly'">
      <wa-color-picker size="s" label="Контур" :value="st.stroke" @change="e => (st.stroke = e.target.value)"></wa-color-picker>
      <wa-number-input size="s" label="Толщина, пикс." :value="st.width" step="0.1" min="0" max="8" @change="e => (st.width = num(e, 1))"></wa-number-input>
    </div>
    <wa-number-input v-else size="s" :label="l.geom === 'point' ? 'Размер, пикс.' : 'Толщина, пикс.'" :value="st.width" step="0.1" min="0.3" max="10"
                     @change="e => (st.width = num(e, 1))"></wa-number-input>
    <wa-slider v-if="l.geom === 'poly'" size="s" label="Непрозрачность заливки, %" min="0" max="100" with-tooltip :value="Math.round(st.opacity * 100)"
               @change="e => (st.opacity = num(e, 70) / 100)"></wa-slider>
    <wa-select size="s" label="Виден" :value="String(st.maxDen || 0)" @change="e => setDen(+e.target.value)"
               title="Как «Видимость в зависимости от масштаба» в QGIS: на более мелком масштабе слой не рисуется ни на карте, ни на листе. На расчёты не влияет">
      <wa-option v-for="d in DENS" :key="d" :value="String(d)">{{ d ? "крупнее 1:" + d.toLocaleString("ru-RU") : "на любом масштабе" }}</wa-option>
    </wa-select>
    <wa-select size="s" label="Роль в расчётах" :value="l.role || 'auto'" @change="e => setRole(e.target.value)"
               title="Какие расчёты берут этот слой: ограничения, анализ, эскиз. «Авто» — по источнику слоя; ручная роль заменяет её.">
      <wa-option v-for="[v, t] in roles" :key="v" :value="v">{{ t }}</wa-option>
    </wa-select>
    <wa-slider size="s" label="Непрозрачность слоя, %" min="0" max="100" with-tooltip :value="Math.round(okn(l.layerOpacity, 1) * 100)"
               @change="e => (l.layerOpacity = num(e, 100) / 100)"></wa-slider>
    <div class="row" v-if="l.geom === 'poly' && (st.hatch || st.rules.list.some(r => r.hatch))">
      <wa-select size="s" label="Узор штриховки" :value="st.hatchPat || '45'" @change="e => (st.hatchPat = e.target.value)">
        <wa-option v-for="(t, k) in HATCHES" :key="k" :value="k">{{ t }}</wa-option>
      </wa-select>
      <wa-number-input size="s" label="Шаг, пикс." :value="st.hatchStep || 8" min="4" max="40" @change="e => (st.hatchStep = num(e, 8))"></wa-number-input>
    </div>
    <div class="row">
      <wa-select size="s" label="Подпись" :value="st.label || '-'" @change="e => (st.label = e.target.value === '-' ? '' : e.target.value)">
        <wa-option value="-">нет</wa-option>
        <wa-option v-for="k in fields" :key="k" :value="k">{{ k }}</wa-option>
      </wa-select>
      <wa-number-input size="s" label="Кегль" :value="st.labelSize" min="7" max="24" @change="e => (st.labelSize = num(e, 11))"></wa-number-input>
    </div>
    <wa-select v-if="st.label === 'Этажность'" size="s" label="Подписи этажности" :value="String(floorsDenOf(l))" @change="e => (st.floorsDen = +e.target.value)">
      <wa-option value="0">всегда</wa-option><wa-option value="2000">от 1:2 000</wa-option><wa-option value="5000">от 1:5 000</wa-option>
    </wa-select>
    <wa-switch size="s" :checked="l.visible" @change="e => (l.visible = e.target.checked)">Показывать на карте</wa-switch>
  </div>
  <div class="pane" v-else><p class="hint">Выберите слой в окне «Слои».</p></div>
</template>

<script setup>
import { computed } from "vue";
import { Plus, X } from "@lucide/vue";
import "../../../web/roles.js";
import { current, project } from "../store.js";
import { dataRev } from "../edit.js";
import { plural } from "../geom.js";
import {
  CAT, DENS, HATCHES, OPS, OTHER, RAMPS, RAMP_TITLES, assignCats, breaks, catValues, fieldsOf, floorsDenOf, legendItems, numFields, okn, ruleCount, swatchColor,
} from "../symbology.js";

window.Roles.load();                                // таблица кодов каталога ГИС ОГД → роль (GET /api/layer_roles)
const GEOM = { point: "Точки", line: "Линии", poly: "Полигоны" };
const l = current;
const st = computed(() => l.value.style);           // полный стиль: store.setProject дополняет его значениями по умолчанию
const fc = computed(() => (dataRev.value, project.data[l.value?.key]?.fc));   // данные слоя не реактивны (markRaw): правка — через dataRev
const count = computed(() => fc.value?.features?.length || 0);
const fields = computed(() => fieldsOf(fc.value));
const nf = computed(() => numFields(fc.value));
const txtFields = computed(() => fields.value.filter(k => !nf.value.includes(k)));
const hasLgr = computed(() => st.value.mode === "lgr" || (fc.value?.features || []).some(f => f.properties?._lt));
const modes = computed(() => [["single", "Единый цвет"], ["cat", "Категории по полю"], ["grad", "Диапазоны чисел"], ["rules", "Правила"]].concat(hasLgr.value ? [["lgr", "Знаки ЛГР"]] : []));
const allCats = computed(() => catValues(fc.value, st.value.cat.field));
const cats = computed(() => allCats.value.slice(0, 80));
const catsAll = computed(() => allCats.value.length);
const legend = computed(() => (st.value.grad.field, st.value.grad.n, st.value.grad.method, st.value.grad.ramp, legendItems(st.value, fc.value)));
const num = (e, d) => okn(e.target.value, d);

function setMode(m) {
  const s = st.value; s.mode = m;
  if (m === "cat" && !Object.keys(s.cat.colors).length) assignCats(s, fc.value, false);
  if (m === "grad" && !nf.value.includes(s.grad.field)) s.grad.field = nf.value[0] || "";
  if (m === "grad") void breaks(s, fc.value);
}
function catOff(v, off) { const s = st.value; s.cat.off = off ? [...s.cat.off, v] : s.cat.off.filter(x => x !== v); }
function setDen(d) { if (d) st.value.maxDen = d; else delete st.value.maxDen; }

/* Роль слоя в расчётах (web/roles.js): «авто» — по источнику; поле role в файле — только при ручной роли. */
const roles = computed(() => {
  const R = window.Roles, a = R.autoRole(l.value.key);
  return [["auto", "авто" + (a ? ": " + R.LABELS[a] : ": не участвует")], ...Object.entries(R.LABELS), ["none", "не участвует в расчётах"]];
});
function setRole(v) { if (v === "auto") delete l.value.role; else l.value.role = window.Roles.sane(v); }
</script>

<style>
.props .ph { display: flex; align-items: center; gap: 8px; }
.props .sub { color: var(--g-muted); font-size: var(--wa-font-size-xs); margin: 2px 0 var(--wa-space-s); }
.props .sw { width: 16px; height: 10px; flex: none; background: color-mix(in srgb, var(--c) 45%, transparent); border: 1px solid var(--c); }
.props .sw.line { background: none; border: 0; border-bottom: 2.5px solid var(--c); height: 6px; }
.props .sw.point { width: 10px; border-radius: 50%; background: var(--c); }
.props .modes { display: flex; align-items: center; gap: var(--wa-space-s); margin-bottom: var(--wa-space-m); }
.props .modes .lbl { margin: 0; flex: none; }
.props .modes wa-select { flex: 1; min-width: 0; }
.props .row { display: flex; gap: var(--wa-space-s); align-items: flex-end; flex-wrap: wrap; margin-bottom: var(--wa-space-s); }
.props .row > * { margin-bottom: 0 !important; }
.props .row wa-select, .props .row wa-input { flex: 1; min-width: 90px; }
.props .row wa-select.op { flex: 0 0 76px; min-width: 0; }
.props .lbl { font-size: var(--wa-font-size-s); margin-bottom: 4px; }
.props table.cl { width: 100%; border-collapse: collapse; margin-bottom: var(--wa-space-s); font-size: var(--wa-font-size-s); }
.props table.cl td { padding: 1px 4px; border-bottom: 1px solid var(--g-line); }
.props table.cl tr.off .v { color: var(--g-muted); text-decoration: line-through; }
.props table.cl td.v { width: 100%; overflow-wrap: anywhere; }
.props .n { color: var(--g-muted); text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; font-size: var(--wa-font-size-xs); }
.props .chip { display: inline-block; width: 18px; height: 12px; border: 1px solid var(--g-line); vertical-align: middle; }
.props .ramps { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: var(--wa-space-s); }
.props .ramp { all: unset; display: inline-flex; border: 1px solid var(--g-line); padding: 2px; border-radius: 3px; cursor: pointer; }
.props .ramp[aria-pressed="true"] { outline: 2px solid var(--wa-color-brand-fill-loud); }
.props .ramp i { width: 10px; height: 12px; }
.props .rule { border: 1px solid var(--g-line); border-radius: var(--wa-border-radius-s); padding: 6px; margin-bottom: var(--wa-space-s); align-items: center; }
.props .grow { flex: 1; }
</style>
