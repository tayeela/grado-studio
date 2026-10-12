<!-- ГРАДО 2 · окно «Свойства» нового интерфейса: оформление текущего слоя, как панель «Стиль слоя» QGIS и правая панель «Стиль»
     рабочей страницы (web/layers.js renderStyle). Шапка — образец (тот же стиль, что на карте), название, глаз. Разделы:
     «Оформление» (способ: единый, категории, диапазоны, правила, знаки ЛГР; заливка с прозрачностью, штриховка, контур, тип линии),
     «Подписи», «Слой» (прозрачность, видимость по масштабу, роль в расчётах). В узком окне подпись встаёт над полем (theme.css, @container).
     Правка меняет слой в store.project — карта перерисовывается сама, project.js записывает правку в проект. Классы и цвета — symbology.js. -->
<template>
  <div class="pane props" v-if="l">
    <div class="ph">
      <LayerSwatch :l="l" />
      <div class="pt">
        <b :title="l.title || l.key">{{ l.title || l.key }}</b>
        <span class="sub">{{ GEOM[l.geom] || l.geom }} · {{ plural(count, ["объект", "объекта", "объектов"]) }}</span>
      </div>
      <wa-button :aria-label="l.visible ? 'Скрыть слой на карте' : 'Показать слой на карте'" size="s" appearance="plain" class="eyeb" :title="l.visible ? 'Скрыть слой на карте' : 'Показать слой на карте'"
                 :aria-pressed="String(!!l.visible)" @click="l.visible = !l.visible">
        <Eye v-if="l.visible" :size="16" /><EyeOff v-else :size="16" />
      </wa-button>
    </div>
    <p v-if="l.visible && !shown(l)" class="hint">Слой не виден на карте: скрыта его группа.</p>

    <h3>Оформление</h3>
    <!-- способ оформления — выпадающим списком: пять кнопок в ряд не помещаются в узкое окно -->
    <label class="f">
      <span>Способ</span>
      <wa-select size="s" :value="st.mode" @change="e => setMode(e.target.value)">
        <wa-option v-for="[m, t] in modes" :key="m" :value="m">{{ t }}</wa-option>
      </wa-select>
    </label>

    <p v-if="st.mode === 'lgr'" class="hint">Знаки красных линий и ЛГР по стандарту REDLN97: тип линии выбирается по коду линии объекта.
      <a href="/linetypes.html" target="_blank">Каталог типов</a>.</p>

    <template v-else-if="st.mode === 'cat'">
      <label class="f">
        <span>Поле</span>
        <wa-select size="s" :value="st.cat.field" @change="e => { st.cat.field = e.target.value; assignCats(st, fc, false); }">
          <wa-option v-for="k in (txtFields.length ? txtFields : fields)" :key="k" :value="k">{{ k }}</wa-option>
        </wa-select>
      </label>
      <wa-button size="s" appearance="outlined" class="wide" title="Как «Классифицировать» в QGIS: заново собрать значения поля и раздать цвета"
                 @click="assignCats(st, fc, false)">Классифицировать</wa-button>
      <table class="cl">
        <tr v-for="[v, n] in cats" :key="v" :class="{ off: st.cat.off.includes(v) }">
          <td><wa-checkbox size="s" :checked="!st.cat.off.includes(v)" :title="st.cat.off.includes(v) ? 'Показать' : 'Скрыть'" @change="e => catOff(v, !e.target.checked)"></wa-checkbox></td>
          <td><wa-color-picker size="s" :aria-label="'Цвет: ' + (v || '—')" :label="'Цвет: ' + (v || '—')" :value="st.cat.colors[v] || OTHER" @change="e => (st.cat.colors[v] = e.target.value)"></wa-color-picker></td>
          <td class="v" :title="v">{{ v || "—" }}</td><td class="n">{{ n }}</td>
        </tr>
      </table>
      <p v-if="catsAll > cats.length" class="hint">Показаны 80 значений из {{ catsAll }}.</p>
    </template>

    <template v-else-if="st.mode === 'grad'">
      <p v-if="!nf.length" class="hint">В слое нет числовых полей.</p>
      <template v-else>
        <label class="f">
          <span>Поле</span>
          <wa-select size="s" :value="st.grad.field" @change="e => (st.grad.field = e.target.value)">
            <wa-option v-for="k in nf" :key="k" :value="k">{{ k }}</wa-option>
          </wa-select>
        </label>
        <label class="f">
          <span>Классы</span>
          <wa-select size="s" :value="String(st.grad.n)" @change="e => (st.grad.n = +e.target.value)">
            <wa-option v-for="n in [3, 4, 5, 6]" :key="n" :value="String(n)">{{ n }}</wa-option>
          </wa-select>
        </label>
        <label class="f">
          <span>Границы</span>
          <wa-select size="s" :value="st.grad.method" @change="e => (st.grad.method = e.target.value)">
            <wa-option value="quantile">поровну объектов</wa-option><wa-option value="equal">равные интервалы</wa-option>
          </wa-select>
        </label>
        <div class="f top"><span>Шкала</span>
          <div class="ramps">
            <button v-for="(cs, r) in RAMPS" :key="r" class="ramp" :aria-pressed="st.grad.ramp === r" :title="'Шкала ' + RAMP_TITLES[r]" @click="st.grad.ramp = r">
              <i v-for="c in cs" :key="c" :style="{ background: c }"></i>
            </button>
          </div>
        </div>
        <table class="cl">
          <tr v-for="it in legend" :key="it.v"><td><span class="chip" :style="{ background: it.c }"></span></td><td class="v" :title="it.v">{{ it.v }}</td><td class="n">{{ it.n || "" }}</td></tr>
        </table>
      </template>
    </template>

    <template v-else-if="st.mode === 'rules'">
      <div v-for="(r, i) in st.rules.list" :key="i" class="rule">
        <div class="row">
          <wa-select size="s" :value="r.field" placeholder="Поле" aria-label="Поле" @change="e => (r.field = e.target.value)">
            <wa-option v-for="k in fields" :key="k" :value="k">{{ k }}</wa-option>
          </wa-select>
          <wa-select size="s" class="op" :value="r.op" aria-label="Условие" @change="e => (r.op = e.target.value)">
            <wa-option v-for="o in OPS" :key="o" :value="o">{{ o }}</wa-option>
          </wa-select>
          <wa-input size="s" :value="r.val" placeholder="значение" aria-label="Значение" @change="e => (r.val = e.target.value)"></wa-input>
        </div>
        <div class="row">
          <wa-color-picker size="s" aria-label="Цвет правила" label="Цвет правила" :value="r.fill" @change="e => (r.fill = e.target.value)"></wa-color-picker>
          <wa-checkbox v-if="l.geom === 'poly'" size="s" :checked="!!r.hatch" @change="e => (r.hatch = e.target.checked)">штриховка</wa-checkbox>
          <span class="grow"></span><span class="n" title="Объектов, подходящих под правило">{{ plural(ruleCount(r, fc), ["объект", "объекта", "объектов"]) }}</span>
          <wa-button aria-label="Удалить правило" size="s" appearance="plain" title="Удалить правило" @click="st.rules.list.splice(i, 1)"><X :size="14" /></wa-button>
        </div>
      </div>
      <div class="row rule">
        <span>Остальные</span>
        <wa-color-picker size="s" aria-label="Цвет остальных" label="Цвет остальных" :value="st.rules.elseFill" @change="e => (st.rules.elseFill = e.target.value)"></wa-color-picker>
        <wa-checkbox size="s" :checked="!!st.rules.elseHide" @change="e => (st.rules.elseHide = e.target.checked)">скрыть</wa-checkbox>
      </div>
      <wa-button size="s" appearance="outlined" class="wide" @click="st.rules.list.push({ field: fields[0] || '', op: '=', val: '', fill: CAT[st.rules.list.length % CAT.length] })"><Plus :size="14" /> Правило</wa-button>
    </template>

    <template v-if="st.mode !== 'lgr'">
      <!-- знак: заливка (цвет и прозрачность одной строкой), штриховка, контур, тип линии -->
      <div class="f" v-if="l.geom === 'poly'">
        <span>Заливка</span>
        <div class="fc">
          <wa-color-picker v-if="st.mode === 'single'" size="s" aria-label="Цвет заливки" :value="st.fill" @change="e => (st.fill = e.target.value)"></wa-color-picker>
          <span v-if="hatched" class="u">штриховка своей подложкой</span>
          <span v-else class="sl" title="Прозрачность заливки: 0 % — только контур">
            <wa-slider size="s" min="0" max="100" aria-label="Непрозрачность заливки" :value="Math.round(st.opacity * 100)" @input="e => (st.opacity = num(e, 70) / 100)"></wa-slider>
            <span class="u v">{{ Math.round(st.opacity * 100) }} %</span>
          </span>
        </div>
      </div>
      <div class="f" v-else-if="st.mode === 'single'">
        <span>Цвет</span>
        <div class="fc"><wa-color-picker size="s" aria-label="Цвет" label="Цвет" :value="st.fill" @change="e => (st.fill = e.target.value)"></wa-color-picker></div>
      </div>

      <template v-if="l.geom === 'poly' && (st.mode !== 'rules' || hatched)">
        <label class="f">
          <span>{{ st.mode === 'rules' ? 'Узор' : 'Штриховка' }}</span>
          <wa-select size="s" :value="st.mode !== 'rules' && !st.hatch ? 'none' : (st.hatchPat || '45')" @change="e => setHatch(e.target.value)">
            <wa-option v-if="st.mode !== 'rules'" value="none">нет</wa-option>
            <wa-option v-for="(t, k) in HATCHES" :key="k" :value="k">{{ t }}</wa-option>
          </wa-select>
        </label>
        <label class="f" v-if="hatched">
          <span>Шаг</span>
          <div class="fc">
            <wa-number-input size="s" class="num" :value="st.hatchStep || 8" min="4" max="40" @change="e => (st.hatchStep = num(e, 8))"></wa-number-input>
            <span class="u">пикс.</span>
          </div>
        </label>
      </template>

      <div class="f" v-if="l.geom !== 'line'">
        <span>Контур</span>
        <div class="fc">
          <wa-color-picker size="s" aria-label="Цвет контура" label="Цвет контура" :value="edge" @change="e => { st.stroke = e.target.value; st.strokeOwn = true; }"></wa-color-picker>
          <template v-if="l.geom === 'poly'">
            <wa-number-input size="s" class="num" aria-label="Толщина контура, пикс." :value="st.width" step="0.1" min="0" max="10" @change="e => (st.width = num(e, 1))"></wa-number-input>
            <span class="u">пикс.</span>
          </template>
        </div>
      </div>
      <label class="f" v-if="l.geom !== 'poly'">
        <span>{{ l.geom === 'point' ? 'Размер' : 'Толщина' }}</span>
        <div class="fc">
          <wa-number-input size="s" class="num" :value="st.width" step="0.1" min="0.3" max="10" @change="e => (st.width = num(e, 1))"></wa-number-input>
          <span class="u">пикс.</span>
        </div>
      </label>
      <label class="f" v-if="l.geom !== 'point'">
        <span>Линия</span>
        <wa-select size="s" :value="dashKey" @change="e => setDash(e.target.value)">
          <wa-option v-for="(t, k) in DASHES" :key="k" :value="k">{{ t }}</wa-option>
          <wa-option v-if="dashKey === 'own'" value="own">своя ({{ st.dash.join(" ") }})</wa-option>
        </wa-select>
      </label>
    </template>

    <h3>Подписи</h3>
    <label class="f">
      <span>Поле</span>
      <wa-select size="s" :value="st.label || '-'" @change="e => (st.label = e.target.value === '-' ? '' : e.target.value)">
        <wa-option value="-">без подписей</wa-option>
        <wa-option v-for="k in fields" :key="k" :value="k">{{ k }}</wa-option>
      </wa-select>
    </label>
    <div class="f" v-if="st.label">
      <span>Шрифт</span>
      <div class="fc">
        <wa-color-picker size="s" aria-label="Цвет подписи" label="Цвет подписи" :value="st.labelColor || '#1d1d1f'" @change="e => (st.labelColor = e.target.value)"></wa-color-picker>
        <wa-number-input size="s" class="num" aria-label="Кегль подписи, пт" :value="st.labelSize" min="7" max="24" @change="e => (st.labelSize = num(e, 11))"></wa-number-input>
        <span class="u">пт</span>
      </div>
    </div>
    <label class="f" v-if="st.label === 'Этажность'">
      <span>Показывать</span>
      <wa-select size="s" :value="String(floorsDenOf(l))" @change="e => (st.floorsDen = +e.target.value)">
        <wa-option value="0">всегда</wa-option><wa-option value="2000">от 1:2 000</wa-option><wa-option value="5000">от 1:5 000</wa-option>
      </wa-select>
    </label>

    <h3>Слой</h3>
    <div class="f">
      <span>Непрозрачность</span>
      <span class="sl" title="Непрозрачность всего слоя: заливки, контура и подписей">
        <wa-slider size="s" min="0" max="100" aria-label="Непрозрачность слоя" :value="Math.round(okn(l.layerOpacity, 1) * 100)" @input="e => (l.layerOpacity = num(e, 100) / 100)"></wa-slider>
        <span class="u v">{{ Math.round(okn(l.layerOpacity, 1) * 100) }} %</span>
      </span>
    </div>
    <label class="f" title="Как «Видимость в зависимости от масштаба» в QGIS: на более мелком масштабе слой не рисуется ни на карте, ни на листе. На расчёты не влияет">
      <span>Виден</span>
      <wa-select size="s" :value="String(st.maxDen || 0)" @change="e => setDen(+e.target.value)">
        <wa-option v-for="d in DENS" :key="d" :value="String(d)">{{ d ? "крупнее 1:" + d.toLocaleString("ru-RU") : "всегда" }}</wa-option>
      </wa-select>
    </label>
    <label class="f" title="Какие расчёты берут этот слой: ограничения, анализ, эскиз. «Авто» — по источнику слоя; ручная роль заменяет её.">
      <span>Роль</span>
      <wa-select size="s" :value="l.role || 'auto'" @change="e => setRole(e.target.value)">
        <wa-option v-for="[v, t] in roles" :key="v" :value="v">{{ t }}</wa-option>
      </wa-select>
    </label>
  </div>
  <div class="pane" v-else><p class="hint">Выберите слой в окне «Слои».</p></div>
</template>

<script setup>
import { computed } from "vue";
import { Eye, EyeOff, Plus, X } from "@lucide/vue";
import "../../../web/roles.js";
import { current, project, shown } from "../store.js";
import { dataRev } from "../edit.js";
import { plural } from "../geom.js";
import LayerSwatch from "./LayerSwatch.vue";
import {
  CAT, DASHES, DENS, HATCHES, OPS, OTHER, RAMPS, RAMP_TITLES, assignCats, breaks, catValues, edgeColor, fieldsOf, floorsDenOf, legendItems, numFields, okn, ruleCount,
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
/* штриховка задана: у правил — хоть у одного правила, иначе — у слоя */
const hatched = computed(() => st.value.mode === "rules" ? st.value.rules.list.some(r => r.hatch) : !!st.value.hatch);
/* цвет контура как на карте: у штриховки без своего цвета контура — цвет штриховки (symbology.js edgeColor) */
const edge = computed(() => edgeColor(st.value, { fill: st.value.fill, hatch: hatched.value }));
const dashKey = computed(() => { const d = (st.value.dash || []).join(","); return !d ? "solid" : Object.hasOwn(DASHES, d) ? d : "own"; });
const num = (e, d) => okn(e.target.value, d);

function setMode(m) {
  const s = st.value; s.mode = m;
  if (m === "cat" && !Object.keys(s.cat.colors).length) assignCats(s, fc.value, false);
  if (m === "grad" && !nf.value.includes(s.grad.field)) s.grad.field = nf.value[0] || "";
  if (m === "grad") void breaks(s, fc.value);
}
function setHatch(v) { const s = st.value; if (v === "none") s.hatch = false; else { s.hatchPat = v; if (s.mode !== "rules") s.hatch = true; } }
function setDash(v) { if (v === "own") return; if (v === "solid") delete st.value.dash; else st.value.dash = v.split(",").map(Number); }
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
/* шапка: образец, название в две строки, тип и число объектов, глаз справа */
.props .ph { display: flex; align-items: flex-start; gap: 8px; margin-bottom: var(--wa-space-xs); }
.props .ph .lsw { margin-top: 4px; }
.props .pt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.props .pt b { font-weight: 600; line-height: 1.3; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow-wrap: anywhere; }
.props .sub { color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.props .eyeb { flex: none; margin: -4px -4px 0 0; color: var(--g-muted); }
.props .eyeb[aria-pressed="false"] { color: var(--wa-color-text-quiet); opacity: .7; }
.props wa-button.wide { display: block; width: 100%; margin-bottom: var(--wa-space-s); }
.props .row { display: flex; gap: var(--wa-space-s); align-items: center; flex-wrap: wrap; margin-bottom: var(--wa-space-s); }
.props .row > * { margin-bottom: 0 !important; }
.props .row wa-select, .props .row wa-input { flex: 1 1 90px; min-width: 0; }
.props .row wa-select.op { flex: 0 0 76px; }
.props table.cl { width: 100%; border-collapse: collapse; margin-bottom: var(--wa-space-s); font-size: var(--wa-font-size-s); }
.props table.cl td { padding: 2px 4px; border-bottom: 1px solid var(--g-line); vertical-align: middle; }
.props table.cl tr.off .v { color: var(--g-muted); text-decoration: line-through; }
.props table.cl td.v { width: 100%; max-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }   /* длинное значение — в одну строку с многоточием, целиком — в подсказке */
.props table.cl wa-checkbox, .props table.cl wa-color-picker { margin: 0; min-height: 0; }
.props .n { color: var(--g-muted); text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; font-size: var(--wa-font-size-xs); }
.props .chip { display: inline-block; width: 16px; height: 12px; border: 1px solid var(--g-line); vertical-align: middle; }
.props .ramps { display: flex; gap: 8px; flex-wrap: wrap; }
.props .ramp { all: unset; display: inline-flex; border: 1px solid var(--g-line); padding: 2px; border-radius: 4px; cursor: pointer; }
.props .ramp:focus-visible { outline: 2px solid var(--wa-color-focus); }
.props .ramp[aria-pressed="true"] { outline: 2px solid var(--wa-color-brand-fill-loud); }
.props .ramp i { width: 10px; height: 12px; }
.props .rule { border: 1px solid var(--g-line); border-radius: var(--wa-border-radius-s); padding: 8px; margin-bottom: var(--wa-space-s); }
.props .rule .row:last-child { margin-bottom: 0; }
.props .grow { flex: 1; }
</style>
