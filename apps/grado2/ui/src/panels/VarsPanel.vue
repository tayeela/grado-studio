<!-- ГРАДО 2 · окно «Варианты» нового интерфейса (как окно «Варианты» рабочей страницы): «Подобрать варианты» (перебор
     типологий в пределах ограничений, «Стоп»), шесть лучших карточками и все — таблицей, «Сохранить слоем»; сверху —
     сохранённые варианты (открыть, переименовать, удалить). Логика — variants.js. -->
<template>
  <div class="pane varsp">
    <div class="vbar">
      <span class="msg" title="Перебор типологий и направления корпусов в пределах ограничений">{{ VS.msg || "Перебор типологий" }}</span>
      <wa-button v-if="!VS.running" size="s" variant="brand" title="Перебор типологий, ширины и направления корпусов с этажностью под цель плотности в пределах ограничений" @click="runVariants"><Sparkles :size="14" /> Подобрать варианты</wa-button>
      <wa-button v-else size="s" appearance="outlined" :disabled="VS.stop" title="Прервать подбор: уже посчитанные варианты останутся" @click="stopVariants"><Square :size="14" /> Стоп</wa-button>
      <wa-button size="s" appearance="outlined" :disabled="VS.running" title="Сделать выбранный вариант слоем проекта" @click="bakeVariant"><Stamp :size="14" /> Сохранить слоем</wa-button>
    </div>
    <div v-if="VS.running" class="vprog"><i :style="{ width: (VS.total ? VS.done / VS.total * 100 : 0).toFixed(1) + '%' }"></i></div>

    <div class="svh">
      <b>Сохранённые</b><small v-if="saved.length">{{ plural(saved.length, ["вариант", "варианта", "вариантов"]) }}</small><span class="sp"></span>
      <template v-if="SV.ask === 'vars'">
        <input v-model="SV.val" v-focus type="text" maxlength="60" aria-label="Название варианта" placeholder="Название варианта" @keydown.enter.prevent="svCommit" @keydown.esc.prevent="SV.ask = ''">
        <wa-button size="s" variant="brand" @click="svCommit">Сохранить</wa-button><wa-button size="s" appearance="outlined" @click="SV.ask = ''">Отмена</wa-button>
      </template>
      <wa-button v-else size="s" appearance="outlined" :disabled="!cur.sk.length" title="Запомнить текущий эскиз с показателями под своим названием" @click="svAsk('vars')"><BookmarkPlus :size="14" /> Сохранить текущий эскиз…</wa-button>
    </div>
    <p v-if="!saved.length" class="hint">Сохранённых вариантов пока нет: «Сохранить как вариант…» запомнит эскиз.<span class="gq" tabindex="0" role="note" title="Вариант хранит текущий эскиз вместе с показателями, в том числе ваши правки этажности и переносы корпусов. Новый подбор вариантов их не стирает." aria-label="Вариант хранит текущий эскиз вместе с показателями, в том числе ваши правки этажности и переносы корпусов. Новый подбор вариантов их не стирает.">?</span></p>
    <template v-else>
      <p class="hint">Числа в таблице — на момент сохранения; «Открыть» пересчитает их по нынешним нормативам.</p>
      <table class="vt">
        <thead><tr><th>Вариант</th><th>Корпусов</th><th>Ср. эт.</th><th>СПП новая, тыс. м²</th><th>Плотность (цель {{ fmt(target) }})</th>
          <th title="Доля фасадов новых домов, получающих норму, на момент сохранения; «—», если «Проверить нормы» не запускалась">Инсоляция новых</th><th>Население, чел.</th><th>ДОО, мест</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in saved" :key="r.id" :class="{ sel: r.sig === curSig }">
            <td :title="`Сохранён ${r.at}, ${r.typ}; показатели — на момент сохранения`">
              <input v-if="SV.ren === r.id" v-model="SV.val" v-focus type="text" maxlength="60" aria-label="Новое название варианта" @keydown.enter.prevent="svRename(r.id, SV.val)" @keydown.esc.prevent="SV.ren = null">
              <template v-else>{{ r.name }}</template><small v-if="r.sig === curSig"> · открыт сейчас</small></td>
            <td class="n">{{ r.n }}</td><td class="n">{{ fmt(r.avg, 1) }}</td><td class="n">{{ fmt(r.spp / 1000, 1) }}</td><td class="n" :class="dcls(r.density)">{{ fmt(r.density, 1) }}</td>
            <td class="n">{{ r.own == null ? "—" : r.own + " %" }}</td><td class="n">{{ r.pop == null ? "—" : fmt(r.pop) }}</td><td class="n">{{ r.doo == null ? "—" : fmt(r.doo) }}</td>
            <td class="ac">
              <template v-if="SV.ren === r.id"><wa-button size="s" variant="brand" @click="svRename(r.id, SV.val)">Готово</wa-button><wa-button size="s" appearance="outlined" @click="SV.ren = null">Отмена</wa-button></template>
              <template v-else>
                <wa-button size="s" appearance="outlined" title="Сделать вариант текущим эскизом: он станет слоем, показатели пересчитаются по нынешним нормативам" @click="svClick(r.id, 'open')">{{ isArmed(r.id, "open") ? "Заменить? Ещё раз" : "Открыть" }}</wa-button>
                <wa-button size="s" appearance="outlined" title="Изменить название" @click="SV.ren = r.id; SV.val = r.name">Переименовать</wa-button>
                <wa-button size="s" appearance="outlined" title="Убрать вариант из проекта (слои уже открытых эскизов остаются)" @click="svClick(r.id, 'del')">{{ isArmed(r.id, "del") ? "Удалить? Ещё раз" : "Удалить" }}</wa-button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </template>

    <p v-if="!VARS.length && !VS.running" class="hint">Нажмите «Подобрать варианты», чтобы сравнить типологии в пределах ограничений. Выбранный вариант переносит параметры в схему.</p>
    <p v-else-if="!VARS.length" class="hint">Подбор идёт: сначала посадка всех вариантов, потом инсоляция лучших восьми. «Стоп» оставит уже посчитанное.</p>
    <template v-else>
      <div class="vcards">
        <button v-for="(v, i) in VARS.slice(0, 6)" :key="i" class="vc" :aria-pressed="String(i === VS.sel)" @click="pickVariant(i)">
          <svg :viewBox="box.vb" preserveAspectRatio="xMidYMid meet"><g transform="scale(1,-1)">
            <polygon :points="box.terr" fill="#fff" stroke="#b3261e" :stroke-width="box.sw * 2" :stroke-dasharray="`${box.sw * 8} ${box.sw * 4}`" />
            <polygon v-for="(r, k) in box.kept" :key="'k' + k" :points="r" fill="#bdb8b0" />
            <polygon v-for="(r, k) in ringsOf(v)" :key="'b' + k" :points="r" fill="#6fa6e6" stroke="#1a4f94" :stroke-width="box.sw" />
          </g></svg>
          <div class="vt1">{{ i + 1 }}. {{ vName(v) }}</div>
          <div class="vm"><span>плотность</span><b :class="dcls(v.density)">{{ fmt(v.density, 1) }}</b><span>ср. эт.</span><b>{{ fmt(v.avg, 1) }}</b>
            <span>инсоляция</span><b>{{ v.own == null ? "—" : v.own + " %" }}</b><span>население</span><b>{{ v.tep ? fmt(v.tep.m.population) : "—" }}</b></div>
        </button>
      </div>
      <p class="hint">Все варианты по оценке — лучшие сверху. Этажность подобрана под цель плотности и не выше предельной высоты ограничений. Инсоляция новых — предварительная оценка по 22 апреля (подробно — «Проверить нормы» в окне «Эскиз»).</p>
      <table class="vt">
        <thead><tr><th>№</th><th>Вариант</th><th>Корпусов</th><th>Ср. эт.</th><th>СПП новая, тыс. м²</th><th>Плотность (цель {{ fmt(target) }})</th><th>Застроенность</th><th>Ниже предельной высоты</th>
          <th title="Доля фасадов новых домов (без северных), получающих норму 22 апреля, предварительно">Инсоляция новых</th><th title="По действующим нормативам окна «Нормативы расчёта»">Население, чел.</th><th title="Места в детских садах по нормативам зоны">ДОО, мест</th></tr></thead>
        <tbody>
          <tr v-for="(v, i) in VARS" :key="i" :class="{ sel: i === VS.sel }" @click="pickVariant(i)">
            <td class="n">{{ i + 1 }}</td><td>{{ vName(v) }}</td><td class="n">{{ v.n }}</td><td class="n">{{ fmt(v.avg, 1) }}</td><td class="n">{{ fmt(v.spp / 1000, 1) }}</td>
            <td class="n" :class="dcls(v.density)">{{ fmt(v.density, 1) }}</td><td class="n">{{ fmt(v.cover * 100, 1) }} %</td><td class="n">{{ v.capped || "" }}</td>
            <td class="n">{{ v.own == null ? "—" : v.own + " %" }}</td><td class="n">{{ v.tep ? fmt(v.tep.m.population) : "—" }}</td><td class="n">{{ v.tep ? fmt(v.tep.m.doo_places) : "—" }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted } from "vue";
import { BookmarkPlus, Sparkles, Square, Stamp } from "@lucide/vue";
import { project } from "../store.js";
import { RESULT, inputOf, preview, tick } from "../graph.js";
import { keptBuildings } from "../tep.js";
import { bboxOf, fmt, plural, ringsXY } from "../geom.js";
import { SV, VARS, VS, bakeVariant, pickVariant, runVariants, savedList, stopVariants, svArmed, svAsk, svClick, svCommit, svCurrent, svRename, svSig, vName } from "../variants.js";

const props = defineProps(["params"]);
const vFocus = { mounted: el => { el.focus(); el.select(); } };
const saved = computed(() => { void tick.value; return savedList(); });
const cur = computed(() => svCurrent());
const curSig = computed(() => cur.value.sk.length ? svSig(cur.value.sk) : "");
const target = computed(() => { void tick.value; return RESULT.tepNode?.widgets_values?.[1] || 25; });
const dcls = d => d > target.value * 1.05 ? "bad" : d < target.value * .8 ? "warnc" : "good";
const isArmed = (id, act) => { void SV.arm; return svArmed(id, act); };
const pts = r => r.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
/* общая рамка карточек: территория, сохраняемые здания; толщина линий — от размера территории */
const box = computed(() => {
  void tick.value; const T = project.territory; if (!T) return { vb: "0 0 1 1", terr: "", kept: [], sw: 1 };
  const tr = ringsXY(T)[0], tb = bboxOf(tr), pad = 10;
  const kept = RESULT.tepNode ? keptBuildings(inputOf(RESULT.tepNode, 1)).flatMap(f => ringsXY(f)).map(pts) : [];
  return { vb: `${tb[0] - pad} ${-tb[3] - pad} ${tb[2] - tb[0] + 2 * pad} ${tb[3] - tb[1] + 2 * pad}`, terr: pts(tr), kept, sw: Math.max(1, (tb[2] - tb[0]) / 180) };
});
const RINGS = new WeakMap();
const ringsOf = v => { let r = RINGS.get(v); if (!r) RINGS.set(v, r = v.sk.flatMap(b => ringsXY(b.f)).map(pts)); return r; };

/* пока окно на виду, эскиз схемы виден на карте (как окна «Эскиз» и «Схема расчёта») */
let off = null;
onMounted(() => {
  const api = props.params?.api;
  preview.vars = api ? api.isVisible : true;
  off = api?.onDidVisibilityChange?.(e => { preview.vars = e.isVisible; });
});
onBeforeUnmount(() => { off?.dispose?.(); preview.vars = false; });
</script>

<style>
.varsp .vbar { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 4px; }
.varsp .vbar .msg { flex: 1; min-width: 120px; color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.varsp wa-button::part(base) { gap: 4px; }
.varsp .vprog { height: 4px; background: var(--g-line); border-radius: 2px; overflow: hidden; margin: 2px 0 6px; }
.varsp .vprog i { display: block; height: 100%; background: var(--wa-color-brand-fill-loud); transition: width .2s; }
.varsp .svh { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin: 6px 0 2px; font-size: var(--wa-font-size-s); }
.varsp .svh small { color: var(--g-muted); }
.varsp .svh .sp { flex: 1; }
.varsp input[type=text] { font: inherit; font-size: var(--wa-font-size-s); padding: 2px 6px; border: 1px solid var(--g-line); border-radius: 4px; background: var(--wa-color-surface-default); color: inherit; }
.varsp .vt { border-collapse: collapse; width: 100%; font-size: var(--wa-font-size-xs); margin: 4px 0 8px; }
.varsp .vt th { text-align: left; font-weight: 600; color: var(--g-muted); background: var(--g-bar); padding: 3px 6px; position: sticky; top: 0; }
.varsp .vt td { padding: 2px 6px; border-bottom: 1px solid var(--g-line); }
.varsp .vt td.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.varsp .vt td.ac { white-space: nowrap; }
.varsp .vt td.ac wa-button { margin-left: 3px; }
.varsp .vt tbody tr { cursor: pointer; }
.varsp .vt tr.sel td { background: var(--wa-color-brand-fill-quiet); }
.varsp .good { color: var(--wa-color-success-on-quiet); } .varsp .bad { color: var(--wa-color-danger-on-quiet); } .varsp .warnc { color: var(--wa-color-warning-on-quiet); }
.varsp .vcards { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 6px; margin: 6px 0; }
.varsp .vc { display: flex; flex-direction: column; gap: 3px; text-align: left; border: 1px solid var(--g-line); border-radius: 6px; background: var(--wa-color-surface-default); color: inherit; padding: 5px; cursor: pointer; font: inherit; }
.varsp .vc[aria-pressed=true] { outline: 2px solid var(--wa-color-brand-fill-loud); outline-offset: -1px; }
.varsp .vc:hover { border-color: var(--wa-color-brand-border-loud); }
.varsp .vc svg { width: 100%; height: 110px; background: var(--g-canvas); border-radius: 4px; }
.varsp .vt1 { font-weight: 600; font-size: var(--wa-font-size-xs); }
.varsp .vm { display: grid; grid-template-columns: auto auto auto auto; gap: 0 6px; font-size: 11px; color: var(--g-muted); }
.varsp .vm b { color: var(--wa-color-text-normal); font-variant-numeric: tabular-nums; }
</style>
