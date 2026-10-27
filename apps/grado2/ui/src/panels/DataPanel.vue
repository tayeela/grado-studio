<!-- ГРАДО 2 · окно «Данные» нового интерфейса (как окно «Данные» и «Исходные данные» рабочей страницы, web/app.js и
     web/ogdpick.js): граница территории (нарисовать, изменить, из файла, по участкам, из выбранного, пример), область
     загрузки синей рамкой на карте (её тянут и растягивают, как рамку вида, — viewframesmap.js), что уже в проекте по источникам (число объектов, дата, ошибка, история
     перевыгрузок), документы ФГИС ТП и их слои, сводка существующего положения в границе, импорт файлов и окно выбора источников: дерево ЕГРН,
     подборок и всех слоёв ГИС ОГД, ЕГКО, OSM, Яндекса и рельефа с готовыми наборами и числом объектов в области.
     Логика — data.js. -->
<template>
  <div class="pane data">
    <!-- три шага сверху вниз, как в мастере: граница → загрузка → что в проекте (владелец 09.10.2026: «вкладка данные вообще непонятна») -->
    <section class="step">
      <div class="sh"><span class="num" :class="{ ok: !!project.territory }"><Check v-if="project.territory" :size="12" /><template v-else>1</template></span>Граница территории</div>
      <p class="lead" :class="{ none: !project.territory }">{{ coverInfo }}</p>
      <!-- своя область загрузки (рамку сдвинули или растянули на карте): вернуть — снова по границе, видам и листам -->
      <wa-button v-if="own" size="s" appearance="plain" class="reset" title="Область загрузки снова ставится сама: граница с запасом, рамки видов и листов" @click="setCover(null)"><RotateCcw :size="14" /> Область — по границе и видам</wa-button>
      <div class="btns">
        <wa-button size="s" :appearance="terrTool === 'draw' ? 'filled' : 'outlined'" :variant="terrTool === 'draw' ? 'brand' : 'neutral'"
                   title="Обвести контур щелчками на карте, двойной щелчок завершает, Esc — отмена" @click="toggle('draw')"><PenLine :size="14" /> Нарисовать</wa-button>
        <wa-button size="s" :appearance="terrTool === 'edit' ? 'filled' : 'outlined'" :variant="terrTool === 'edit' ? 'brand' : 'neutral'" :disabled="!project.territory"
                   title="Ручки на вершинах: тянуть, щелчок по стороне — новая вершина, Alt+щелчок — удалить" @click="toggle('edit')"><Spline :size="14" /> Изменить</wa-button>
        <wa-button size="s" appearance="outlined" title="DXF, DWG, GeoJSON, KML, Shapefile: самый большой замкнутый контур файла" @click="pick('terr')"><FileInput :size="14" /> Из файла</wa-button>
        <wa-button size="s" appearance="outlined" title="Объединение земельных участков по кадастровым номерам" @click="numsDlg = true"><Grid2x2 :size="14" /> По участкам</wa-button>
        <wa-button size="s" appearance="outlined" :disabled="!sel.length" title="Граница — объединение выбранных на карте площадных объектов" @click="territoryFromSelection(selected())"><SquareDashed :size="14" /> Из выбранного</wa-button>
        <wa-button size="s" :class="{ wide: askExample }" :appearance="askExample ? 'filled' : 'outlined'" :variant="askExample ? 'danger' : 'neutral'" @click="example">{{ askExample ? (project.territory ? "Заменить вашу границу примером?" : "Граница-пример на Ходынском поле — поставить?") : "Пример" }}</wa-button>
      </div>
    </section>

    <section class="step">
      <div class="sh"><span class="num">2</span>Загрузка данных</div>
      <div class="btns">
        <wa-button size="s" class="wide" variant="brand" :disabled="!cover || !!loading" :title="cover ? 'Окно всех источников: ЕГРН, ГИС ОГД, ЕГКО, OpenStreetMap, Яндекс, рельеф' : 'Сначала задайте границу территории'"
                   @click="openPicker()"><Download :size="14" /> Выбрать источники и загрузить…</wa-button>
      </div>
      <!-- «ГИС ОГД в DXF» (меню «Выгрузка»): выгрузка идёт на сервере фоном, ход — здесь -->
      <div v-if="ogd.running" class="job ogdjob" role="status" aria-live="polite">
        <div class="jh"><wa-spinner></wa-spinner><b>Слои в DXF по {{ ogd.where }}: слой {{ ogd.done }} из {{ ogd.total || "…" }}</b>
          <wa-button size="s" appearance="outlined" title="Остановить: текущий слой дочитывается, потом выгрузка встанет" @click="stopOgd">Остановить</wa-button></div>
        <wa-progress-bar :value="ogd.total ? Math.round(ogd.done / ogd.total * 100) : 0" label="Ход выгрузки ГИС ОГД"></wa-progress-bar>
        <p class="hint">{{ ogd.current ? `Сейчас «${ogd.current}»${ogd.msg ? ` (${ogd.msg})` : ""}. ` : "" }}С объектами на листе: {{ ogd.found }}.{{ ogd.left ? ` Осталось около ${ogd.left}.` : "" }} Работать можно дальше; архив скачается сам.</p>
      </div>
      <div class="imp">
        <wa-button size="s" appearance="outlined" title="DXF, DWG, GeoJSON, KML/KMZ, Shapefile — новым слоем; можно перетащить файл на карту" @click="pick('layer')"><FileUp :size="14" /> Свой файл…</wa-button>
        <span class="lbl">координаты DXF</span>
        <wa-select size="s" :value="localSys" title="В какой системе координат ваши файлы в метрах (DXF, DWG)" aria-label="Система координат файлов" @change="e => (localSys = e.target.value)">
          <wa-option value="msk">МСК (как в QGIS)</wa-option><wa-option value="ogd">система ГИС ОГД</wa-option>
        </wa-select>
      </div>
      <input ref="fileInput" type="file" multiple hidden :accept="FILE_ACCEPT" @change="onFile">

      <!-- ход выгрузки: общая полоса и строка на каждый слой — что идёт, что готово, что пусто, где ошибка -->
      <div v-if="job.items.length" class="job" :class="{ fin: !!job.t1 }" role="status" aria-live="polite">
        <div class="jh">
          <wa-spinner v-if="!job.t1"></wa-spinner><CircleCheck v-else-if="!jobN.error" :size="16" class="ic done" /><CircleAlert v-else :size="16" class="ic error" />
          <b>{{ jobHead }}</b><span class="t">{{ elapsed }}</span>
          <wa-button aria-label="Убрать отчёт о выгрузке" v-if="job.t1" size="s" appearance="plain" title="Убрать отчёт о выгрузке" @click="job.items = []"><X :size="14" /></wa-button>
        </div>
        <wa-progress-bar :value="jobPct" :label="jobHead"></wa-progress-bar>
        <p v-if="!job.t1" class="hint">Можно работать дальше: слои появятся на карте и в окне «Слои», как только придут.</p>
        <ul class="jl">
          <li v-for="it in jobShown" :key="it.key" :class="it.state" :title="it.title + (it.detail ? ' — ' + it.detail : '')">
            <span class="st"><wa-spinner v-if="it.state === 'run'"></wa-spinner><CircleCheck v-else-if="it.state === 'done'" :size="14" />
              <CircleMinus v-else-if="it.state === 'empty'" :size="14" /><CircleAlert v-else :size="14" /></span>
            <span class="nm">{{ it.title }}</span>
            <span class="dt">{{ it.state === "done" ? fmt(it.n) : it.state === "run" ? it.detail : it.state === "empty" ? "пусто" : "не ответил" }}</span>
            <span v-if="it.state === 'run' && it.pct != null" class="mini"><i :style="{ width: Math.round(it.pct * 100) + '%' }"></i></span>
            <span v-if="it.state !== 'run' && it.detail" class="sub">{{ it.state === "done" ? "перевыгрузка: " + it.detail : it.detail }}</span>
          </li>
        </ul>
        <wa-button v-if="job.t1 && jobN.error && !loading" size="s" variant="brand" appearance="outlined" class="all" @click="retryFailed">
          <RotateCw slot="start" :size="14" />Повторить: {{ plural(jobN.error, ["слой", "слоя", "слоёв"]) }}</wa-button>
        <wa-button v-if="job.t1 && jobN.done && !showAll" size="s" appearance="plain" class="all" @click="showAll = true">Загруженные слои ({{ jobN.done }}) — показать</wa-button>
      </div>
    </section>

    <section class="step">
      <!-- список слоёв свёрнут: окно не растёт и не прокручивается (владелец 09.10.2026, снимок); ошибки выгрузки видны и в свёрнутом -->
      <button class="sh tog" type="button" :aria-expanded="srcOpen" :disabled="!groups.length" @click="srcOpen = !srcOpen">
        <span class="num">3</span>В проекте<span v-if="groups.length" class="cnt">{{ totals }}</span>
        <ChevronRight v-if="groups.length" :size="14" class="chev" :class="{ open: srcOpen }" /></button>
      <p v-if="!groups.length" class="hint">Пока ничего не загружено.</p>
      <ul v-else-if="!srcOpen && errKeys.length" class="errs"><li v-for="k in errKeys" :key="k"><b>{{ srcTitle(k) }}:</b> {{ ERRORS[k] }}</li></ul>
      <table v-if="groups.length && srcOpen" class="srct">
        <thead><tr><th>Слой</th><th class="r">Объектов</th><th class="r">Выгрузка</th></tr></thead>
        <tbody v-for="g in groups" :key="g.kind">
          <tr class="g"><td colspan="3"><Database :size="12" /> {{ g.title }}</td></tr>
          <template v-for="k in g.keys" :key="k">
            <tr :class="{ bad: ERRORS[k] }" :title="srcTitle(k) + (project.data[k]?.source ? ' · ' + project.data[k].source : '') + hist(project.data[k])">
              <td class="nm">{{ srcTitle(k) }}</td><td class="r">{{ count(k) }}</td><td class="r d">{{ shortDate(project.data[k]?.fetched_at) }}</td>
            </tr>
            <tr v-if="ERRORS[k]" class="err"><td colspan="3">{{ ERRORS[k] }}</td></tr>
          </template>
        </tbody>
      </table>
      <p v-if="srcOpen" class="hint">Слои правятся в окне «Слои»; исходная выгрузка сохраняется (меню слоя → «Вернуть исходную выгрузку»).
        Повторная выгрузка покажет, что изменилось в источнике, и сохранит ваши правки.</p>
    </section>

    <section v-if="summary.length" class="step">
      <div class="sh"><span class="num"><Info :size="12" /></span>Существующее положение в границе</div>
      <div class="kv"><template v-for="r in summary" :key="r[0]"><div>{{ r[0] }}</div><div>{{ r[1] }}</div></template></div>
    </section>

    <wa-details class="fgd" summary="Документы территориального планирования (ФГИС ТП)">
      <div class="btns">
        <wa-button size="s" class="wide" appearance="outlined" :disabled="!project.territory || !!loading" title="Генпланы, схемы и их изменения, охват которых накрывает территорию (каталог Минэкономразвития)"
                   @click="fgFind"><Landmark :size="14" /> Найти по территории</wa-button>
      </div>
      <wa-input v-if="project.territory" size="s" type="search" with-clear placeholder="Найти документ по названию"
                title="Поиск по названию во всём каталоге ФГИС ТП, например «генеральный план Троицка»"
                aria-label="Поиск документа ФГИС ТП по названию" :value="FG.q" @input="fgTyped"></wa-input>
      <p v-if="FG.msg" class="hint">{{ FG.msg }}</p>
      <p v-if="inMoscow" class="hint">Генеральный план Москвы в ФГИС ТП не размещён (проверено по всему каталогу): его функциональные зоны — в источниках ГИС ОГД. Здесь для Москвы есть схемы РФ и генплан Троицка.</p>
      <wa-select v-if="FG.docs" size="s" :value="FG.uin" :placeholder="`Документ (${FG.docs.length}${FG.q ? ', найдено по названию' : ', по охвату территории'})`"
                 @change="e => fgPick(e.target.value)">
        <wa-option v-for="d in FG.docs" :key="d.uin" :value="d.uin">{{ d.name.slice(0, 140) }}{{ d.km ? ` · ${fmt(d.km)} км` : "" }}</wa-option>
      </wa-select>
      <template v-if="FG.layers">
        <wa-checkbox v-for="l in FG.layers" :key="l.classid" size="s" class="fgl" :checked="FG.sel.has(l.classid)" :title="l.class_name || ''"
                     @change="e => fgCheck(l.classid, e.target.checked)">{{ l.class_title || l.class_name || l.classid }} <span class="c">{{ GEOMW[l.geom_type] || "" }}</span></wa-checkbox>
        <div class="btns"><wa-button size="s" variant="brand" :disabled="!FG.sel.size || !cover || !!loading" @click="fgLoad"><Download :size="14" /> Загрузить выбранные</wa-button></div>
      </template>
    </wa-details>

    <wa-dialog label="Граница по участкам" :open="numsDlg" @wa-after-hide="numsDlg = false">
      <wa-textarea size="s" rows="4" label="Кадастровые номера (через запятую, пробел или с новой строки)" :value="nums" @input="e => (nums = e.target.value)"></wa-textarea>
      <p class="hint">Берутся участки, уже загруженные из ЕГРН; если их нет — номера ищутся на портале НСПД.</p>
      <wa-button slot="footer" size="s" appearance="plain" @click="numsDlg = false">Отмена</wa-button>
      <wa-button slot="footer" size="s" variant="brand" :disabled="!nums.trim()" @click="byNumbers">Сделать границей</wa-button>
    </wa-dialog>

    <wa-dialog class="picker" :label="pk.dxf ? 'Слои в DXF — ' + pk.dxf.where.replace(/^листу/, 'лист').replace(/^области/, 'область') : 'Исходные данные'" :open="pk.open" @wa-after-hide="pk.open = false; pk.dxf = null">
      <div class="pbar">
        <wa-input size="s" type="search" placeholder="Поиск слоя или папки" with-clear :value="pk.q" @input="e => (pk.q = e.target.value)"></wa-input>
        <wa-checkbox size="s" :checked="pk.only" title="Скрыть слои ГИС ОГД, у которых в области нет объектов" @change="e => (pk.only = e.target.checked)">ГИС ОГД — только с объектами</wa-checkbox>
        <wa-button size="s" appearance="outlined" :disabled="!pk.counts || !nObj" title="Отметить все слои ГИС ОГД, у которых в области есть объекты"
                   @click="ogdWithObjects">Отметить ГИС ОГД с объектами{{ nObj ? ` · ${plural(nObj, ["слой", "слоя", "слоёв"])}` : "" }}</wa-button>
        <wa-button size="s" appearance="outlined" @click="pk.sel = new Set()">Снять все</wa-button>
      </div>
      <div class="presets">Готовые наборы:
        <wa-button v-for="p in PRESETS" :key="p[0]" size="s" :appearance="presetOn(p) ? 'filled' : 'outlined'" :variant="presetOn(p) ? 'brand' : 'neutral'"
                   :title="p[2] + '.\nСлои (' + presetKeys(p).length + '): ' + presetKeys(p).map(k => SOURCES[k].title).join(', ')" @click="togglePreset(p)">{{ p[1] }} · {{ presetKeys(p).length }}</wa-button>
      </div>
      <div class="tree"><TreeNode v-for="n in tree" :key="n.num" :n="n" :depth="0" /><p v-if="!tree.length" class="hint">Ничего не найдено.</p></div>
      <span v-if="pk.dxf" slot="footer" class="hint foot">{{ pk.counts ? "" : (pk.dxf.sheet ? "Считаю объекты ГИС ОГД на листе… " : "Считаю объекты ГИС ОГД в области… ") }}Слоёв отмечено: <b>{{ pk.sel.size }}</b>. В DXF — каждый слой своим слоем{{ pk.dxf.sheet ? ", лист бумаги с видовым экраном в масштабе листа" : ", по области загрузки" }}.</span>
      <span v-else slot="footer" class="hint foot">{{ pk.counts ? "" : "Считаю объекты ГИС ОГД в области… " }}Отмечено: <b>{{ pk.sel.size }}</b>. Большая область для НСПД и OpenStreetMap загружается по частям.</span>
      <wa-button slot="footer" size="s" appearance="plain" @click="pk.open = false">Отмена</wa-button>
      <wa-button v-if="pk.dxf" slot="footer" size="s" variant="brand" :disabled="!pk.sel.size || ogd.running || !!loading" data-act="ogd-dxf" @click="runDxf"><FileDown :size="14" /> В DXF</wa-button>
      <wa-button v-else slot="footer" size="s" variant="brand" :disabled="!pk.sel.size" @click="loadPicked"><Download :size="14" /> Загрузить в проект</wa-button>
    </wa-dialog>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { Check, ChevronRight, CircleAlert, CircleCheck, CircleMinus, Database, Download, FileDown, FileInput, FileUp, Grid2x2, Info, Landmark, PenLine, RotateCcw, RotateCw, Spline, SquareDashed, X } from "@lucide/vue";
import * as turf from "@turf/turf";
import { project } from "../store.js";
import { dataRev, lyr } from "../edit.js";
import { sel, selected } from "../features.js";
import { plural } from "../geom.js";
import {
  ERRORS, FG, FILE_ACCEPT, SOURCES, fgFind, fgLoad, fgPick, fgSearch, checked, coverBox, coverOn, coverOwn, coverRev, coverText, setCover, existingSummary, exampleTerritory, importBoundary, importFiles,
  job, keepChecked, loadKeys, retryFailed, loadSources, loading, localSys, ogd, startOgd, stopOgd, terrTool, territoryByNumbers, territoryFromSelection,
} from "../data.js";
import { album, call } from "../albumhost.js";
import { notice } from "../project.js";

const props = defineProps({ params: Object });

const GROUP = { gisogd_admin: "Административное деление Москвы (эталон)", fgistp: "ФГИС ТП (загруженные слои документов)", import: "Импорт файлов", nspd: "ЕГРН · НСПД", osm: "OpenStreetMap",
  gisogd: "ГИС ОГД Москвы", egko: "ЕГКО Москвы — картооснова ГИС ОГД", terrain: "Рельеф", yandex_sit: "Яндекс Карты для ситуационного плана",
  yandex: "Яндекс Карты (для анализа и эскиза, в сдаваемые материалы не включать)" };
const fmt = v => Number(v).toLocaleString("ru-RU");

const cover = computed(() => (project.territory, project.raw, coverRev.value, JSON.stringify(project.views), coverBox()));
const own = computed(() => (project.raw, coverRev.value, coverOwn()));
const srcOpen = ref(false);
const errKeys = computed(() => (dataRev.value, Object.keys(ERRORS)));
const coverInfo = computed(() => (project.territory, project.raw, coverRev.value, JSON.stringify(project.views), coverText()));
const summary = computed(() => (dataRev.value, project.territory, existingSummary()));
const groups = computed(() => {
  dataRev.value;
  const by = {};
  const keys = new Set([...Object.keys(project.data), ...Object.keys(ERRORS)]);
  keys.forEach(k => { const kind = SOURCES[k]?.kind || (k.startsWith("import:") ? "import" : k.startsWith("user:") || k.startsWith("sketch.") ? "" : k.split(".")[0]); if (kind) (by[kind] ||= []).push(k); });
  const known = Object.entries(by).filter(([kind]) => GROUP[kind]), other = Object.entries(by).filter(([kind]) => !GROUP[kind]).flatMap(([, ks]) => ks);
  return known.map(([kind, keys]) => ({ kind, title: GROUP[kind], keys })).concat(other.length ? [{ kind: "other", title: "Прочие слои", keys: other }] : []);
});
/* Подпись источника — как имя его слоя в окне «Слои» (слой могли переименовать), иначе название источника */
const srcTitle = k => lyr(k)?.title || SOURCES[k]?.title || project.data[k]?.title || k;
const count = k => { const n = project.data[k]?.fc?.features?.length; return n == null ? "" : fmt(n); };
const shortDate = d => d ? d.slice(8, 10) + "." + d.slice(5, 7) + "." + d.slice(2, 4) : "—";   // нарисованный или импортированный слой даты выгрузки не имеет
const totals = computed(() => { dataRev.value; const ks = groups.value.flatMap(g => g.keys).filter(k => project.data[k]);
  return plural(ks.length, ["слой", "слоя", "слоёв"]) + " · " + plural(ks.reduce((a, k) => a + (project.data[k].fc?.features?.length || 0), 0), ["объект", "объекта", "объектов"]); });

/* ход выгрузки: идущие сверху, затем ошибки, пустые и готовые; время — от начала, тикает раз в секунду */
const now = ref(Date.now()); let tick = null;
const ORDER = { run: 0, error: 1, empty: 2, done: 3 };
const jobSorted = computed(() => [...job.items].sort((a, b) => ORDER[a.state] - ORDER[b.state]));
// после выгрузки на виду только то, что требует внимания (ошибки, пустые); загруженное — по кнопке
const showAll = ref(false);
watch(() => job.t0, () => { showAll.value = false; });
const jobShown = computed(() => job.t1 && !showAll.value ? jobSorted.value.filter(i => i.state !== "done") : jobSorted.value);
const jobN = computed(() => { const n = { run: 0, done: 0, empty: 0, error: 0 }; job.items.forEach(i => n[i.state]++); return n; });
const jobPct = computed(() => { const t = job.items.length; if (!t) return 0; const part = job.items.reduce((a, i) => a + (i.state === "run" ? (i.pct || 0) : 1), 0); return Math.round(part / t * 100); });
const jobHead = computed(() => {
  const n = jobN.value, t = job.items.length;
  if (!job.t1) return `Выгрузка: готово ${t - n.run} из ${t}`;
  const rest = [n.empty ? `пусты ${n.empty}` : "", n.error ? `портал не ответил ${n.error}` : ""].filter(Boolean).join(", ");
  if (!n.done) return `Ничего не загружено${rest ? ": " + rest : ""}`;
  return `Загружено ${plural(n.done, ["слой", "слоя", "слоёв"])}${rest ? "; " + rest : ""}`;
});
const elapsed = computed(() => { if (!job.t0) return ""; const sec = Math.max(0, Math.round(((job.t1 || now.value) - job.t0) / 1000)); return sec < 60 ? `${sec} с` : `${Math.floor(sec / 60)} мин ${sec % 60} с`; });
const hist = d => { if (!d) return ""; const hh = d.history || [], x = hh[hh.length - 1]; return hh.length > 1 && x.added != null ? ` · выгрузок ${hh.length}, в последней +${x.added} −${x.removed} ~${x.changed}` : ""; };

/* ФГИС ТП: поиск по названию — через 450 мс после ввода, как в рабочей странице */
const GEOMW = { "100": "полигоны", "010": "линии", "001": "точки" };
const inMoscow = computed(() => { const t = project.territory; if (!t) return false; const [x, y] = turf.centroid(t).geometry.coordinates; return x > 36.8 && x < 37.97 && y > 55.1 && y < 56.02; });
let fgT = null;
function fgTyped(e) { clearTimeout(fgT); const v = e.target.value; fgT = setTimeout(() => fgSearch(v), 450); }
function fgCheck(id, on) { const s = new Set(FG.sel); if (on) s.add(id); else s.delete(id); FG.sel = s; }

function toggle(t) { terrTool.value = terrTool.value === t ? "" : t; }
let askT = null; const askExample = ref(false);
function example() {
  // граница или данные уже есть — пример уводит карту в другой район: второе нажатие подтверждает (аудит UX, находка 6)
  if ((project.territory || Object.keys(project.data || {}).length) && !askExample.value) { askExample.value = true; askT = setTimeout(() => (askExample.value = false), 5000); return; }
  clearTimeout(askT); askExample.value = false; exampleTerritory();
}
const numsDlg = ref(false), nums = ref("");
async function byNumbers() { if (await territoryByNumbers(nums.value)) { numsDlg.value = false; nums.value = ""; } }

const fileInput = ref(null); let pickFor = "layer";
function pick(what) { pickFor = what; fileInput.value.click(); }
function onFile(e) { const fs = [...e.target.files]; e.target.value = ""; if (!fs.length) return; if (pickFor === "terr") importBoundary(fs); else importFiles(fs); }

/* ---------- окно «Исходные данные» ---------- */
const PRESETS = [
  ["exist", "Существующее положение", "Здания, вода, землепользование, дороги и ж/д, участки ЕГРН, районы и подписи — основа любой схемы",
    ["egko.buildings", "egko.water", "egko.water_labels", "egko.green", "osm.landuse", "osm.roads", "yandex.hd_roads", "yandex.rail", "yandex.stations", "nspd.parcels", "gisogd.admin", "egko.place_labels", "egko.addresses"]],
  ["limits", "Ограничения", "ЗОУИТ, СЗЗ, водоохранные зоны, красные линии, аэродромы, ОКН — для проверки ограничений и эскиза",
    ["gisogd.zouit", "nspd.zouit", "gisogd.szz", "gisogd.vodookhr", "gisogd.red_lines", "gisogd.airfield", "gisogd.okn"]],
  ["docs", "Градостроительная документация", "Функциональные зоны ГП, зоны ПЗЗ, ППТ, ПМТ, ГПЗУ, АГР, КРТ",
    ["gisogd.func_zones", "gisogd.func_zones_tinao", "gisogd.pzz_zones", "gisogd.ppt", "gisogd.pmt", "gisogd.gpzu", "gisogd.agr", "gisogd.krt"]],
];
const TREE_GROUPS = [["nspd", "ЕГРН · НСПД"], ["gisogd", "ГИС ОГД — подборки ГРАДО"], ["ogd", "ГИС ОГД — все слои портала"],
  ["egko", "ЕГКО — картооснова ГИС ОГД"], ["osm", "OpenStreetMap"], ["yandex", "Яндекс Карты (для анализа и эскиза, не для сдачи)"], ["terrain", "Рельеф"]];
const pk = reactive({ open: false, q: "", only: true, sel: new Set(), counts: null, ogd: null, opened: new Map(), dxf: null });   // dxf — окно открыто для «ГИС ОГД в DXF» (запрос ogd.req)
const isOgd = k => k.startsWith("ogd.");
const presetKeys = p => p[3].filter(k => SOURCES[k]);
const presetOn = p => { const ks = presetKeys(p); return ks.length > 0 && ks.every(k => pk.sel.has(k)); };
function togglePreset(p) { const on = presetOn(p), s = new Set(pk.sel); presetKeys(p).forEach(k => on ? s.delete(k) : s.add(k)); pk.sel = s; }
const ogdNode = n => n.code ? { key: "ogd." + n.code, num: n.num, name: n.name, path: n.path } : { num: "ogd:" + n.num, name: n.name, label: n.num, children: (n.children || []).map(ogdNode) };
const leaves = n => n.key ? [n] : n.children.flatMap(leaves);
const cnt = k => isOgd(k) && pk.counts ? pk.counts[k.slice(4)] : undefined;
const shownNode = n => {
  const q = pk.q.trim().toLowerCase();
  if (n.key) return (!pk.only || !isOgd(n.key) || !pk.counts || cnt(n.key) !== 0 || pk.sel.has(n.key)) && (!q || n.name.toLowerCase().includes(q) || (n.path || "").toLowerCase().includes(q));
  return n.children.some(shownNode);
};
const tree = computed(() => TREE_GROUPS.map(([g, name]) => {
  const ch = g === "ogd" ? (pk.ogd || []).map(ogdNode)
    : Object.entries(SOURCES).filter(([k, s]) => (s.kind === g || (g === "gisogd" && s.kind === "gisogd_admin")) && !isOgd(k)).map(([k, s]) => ({ key: k, name: s.title }));
  return { num: "g:" + g, name, children: ch, loading: g === "ogd" && !pk.ogd };
}).filter(n => (n.children.length && shownNode(n)) || n.loading));
const nObj = computed(() => pk.counts ? tree.value.flatMap(leaves).filter(l => isOgd(l.key) && cnt(l.key)).length : null);
function ogdWithObjects() { const s = new Set(pk.sel); Object.keys(pk.counts || {}).filter(c => pk.counts[c]).forEach(c => s.add("ogd." + c)); pk.sel = s; }

const badge = k => {
  if (!isOgd(k)) return project.data[k] ? h("span", { class: "n has", title: "Слой уже загружен в проект" }, "в проекте: " + plural(project.data[k].fc?.features?.length || 0, ["объект", "объекта", "объектов"])) : null;
  const v = cnt(k);
  return v === undefined ? h("span", { class: "n", title: "Считаю объекты в области" }, "…")
    : v === null ? h("span", { class: "n", title: "Слоя нет в кэше на диске — число объектов станет известно при выгрузке" }, "не подсчитано")
    : h("span", { class: "n" + (v ? " has" : ""), title: "Объектов в области загрузки" }, fmt(v));
};
/* Узел дерева: слой — флажок; папка — раскрывается, флажок отмечает все показанные слои папки. */
const TreeNode = defineComponent({
  name: "TreeNode", props: { n: Object, depth: Number },
  setup(p) {
    return () => {
      const n = p.n, d = p.depth;
      if (n.loading && !n.children.length) return h("div", { class: "fold", style: { "--d": d } }, [h("span", { class: "nm" }, n.name), h("span", { class: "n" }, " каталог портала…")]);
      if (!shownNode(n)) return null;
      if (n.key) return h("label", { class: "ly", style: { "--d": d } }, [
        h("input", { type: "checkbox", checked: pk.sel.has(n.key), onChange: e => { const s = new Set(pk.sel); e.target.checked ? s.add(n.key) : s.delete(n.key); pk.sel = s; } }),
        h("span", { class: "nm" }, [n.num ? h("b", n.num + " ") : null, n.name]), badge(n.key)]);
      const ls = leaves(n).filter(shownNode), on = ls.filter(l => pk.sel.has(l.key)).length;
      const open = !!pk.q.trim() || (pk.opened.has(n.num) ? pk.opened.get(n.num) : (d === 0 && n.num !== "g:ogd") || (on > 0 && d < 3));
      return h("details", { open, style: { "--d": d }, onToggle: e => pk.opened.set(n.num, e.target.open) }, [
        h("summary", [
          h("input", { type: "checkbox", checked: on > 0 && on === ls.length, indeterminate: on > 0 && on < ls.length, "aria-label": `Вся папка «${n.name}»`,
            onClick: e => { e.stopPropagation(); e.preventDefault(); const all = ls.every(l => pk.sel.has(l.key)), s = new Set(pk.sel); ls.forEach(l => all ? s.delete(l.key) : s.add(l.key)); pk.sel = s; } }),
          h("span", { class: "nm" }, [n.label && !/^\d/.test(n.name) && n.label !== "Т" ? h("b", n.label + " ") : null, n.name]),
          h("span", { class: "n", title: "Отмечено из показанных слоёв папки" }, `${on} из ${ls.length}`)]),
        ...(open ? n.children.map(c => h(TreeNode, { n: c, depth: d + 1, key: c.key || c.num })) : []),
      ]);
    };
  },
});

/* dxf — запрос «ГИС ОГД в DXF» (лист, его рамка, прежний выбор слоёв портала): объекты считаются по листу; в первый раз
   отмечаются слои портала, у которых на листе есть объекты (как окно выбора рабочей страницы, ogdpick.js) */
async function openPicker(dxf = null) {
  const bb = dxf ? dxf.bbox : coverBox(); if (!bb) return;
  const sel = checked(); if (dxf) (dxf.codes || []).forEach(c => sel.add("ogd." + c));
  const first = !!dxf && ![...sel].some(isOgd);
  pk.sel = sel; pk.q = ""; pk.counts = null; pk.dxf = dxf; pk.open = true;
  if (!Object.keys(SOURCES).length) await loadSources();
  try { if (!pk.ogd) pk.ogd = (await (await fetch("/api/ogd_all/tree")).json()).tree || []; } catch { pk.ogd = []; }
  try {
    const r = await fetch("/api/ogd_all/scan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dxf?.sheet ? { sheet: dxf.sheet } : { bbox: bb }) });
    pk.counts = r.ok ? (await r.json()).counts || {} : {};
  } catch { pk.counts = {}; }
  if (first && pk.dxf === dxf) ogdWithObjects();
}
/* «В DXF»: слои портала ГИС ОГД (ogd.*) сервер берёт сам; остальные отмеченные (ЕГКО, OSM, ЕГРН…) сначала загружаются в проект
   по той же области, потом уходят в тот же чертёж своими слоями (26.10.2026: кнопка была серой, если отмечены только ЕГКО). */
async function runDxf() {
  const req = pk.dxf, codes = [...pk.sel].filter(isOgd).map(k => k.slice(4)), rest = [...pk.sel].filter(k => !isOgd(k));
  if (!req || !pk.sel.size) return;
  keepChecked(pk.sel); pk.open = false;
  if (rest.length) await loadKeys(rest, req.bbox);
  const [w, s, e, n] = req.bbox;
  const inBox = f => { try { const b = turf.bbox(f); return b[0] <= e && b[2] >= w && b[1] <= n && b[3] >= s; } catch { return false; } };
  const extra = rest.filter(k => project.data[k]?.fc?.features?.length).map(k => {
    const l = project.layers.find(x => x.key === k);
    return { title: project.data[k].title || SOURCES[k]?.title || k, color: l?.style?.stroke || l?.style?.fill || null, lgr: l?.style?.lgrLine || null,
      features: project.data[k].fc.features.filter(f => f.geometry && inBox(f)).map(f => ({ geometry: f.geometry, properties: f.properties || {} })) };
  }).filter(x => x.features.length);
  if (!codes.length && !extra.length) { ogd.where = req.where; notice.value = `В DXF нечего класть: у отмеченных слоёв нет объектов по ${req.where}.`; return; }
  startOgd(req, codes, extra);
  if (codes.length && album.sheets) call(a => a.keepOgd(codes)).catch(() => { });   // выбор слоёв — в альбом; не ждём движок (он мог не ответить, и выгрузка не начиналась)
}
watch(() => ogd.req, r => { if (!r) return; ogd.req = null; openPicker(r); }, { immediate: true });
function loadPicked() {
  const keys = [...pk.sel];
  tree.value.flatMap(leaves).filter(l => isOgd(l.key) && pk.sel.has(l.key)).forEach(l => { SOURCES[l.key] ||= { title: `${l.name} (ОГД)`, kind: "gisogd" }; });
  keepChecked(pk.sel); pk.open = false;
  loadKeys(keys, coverBox());
}

/* область загрузки видна на карте, пока окно на виду */
let off = null;
onMounted(() => {
  tick = setInterval(() => { if (job.t0 && !job.t1) now.value = Date.now(); }, 1000);
  loadSources();
  const api = props.params?.api;
  coverOn.value = api ? api.isVisible : true;
  off = api?.onDidVisibilityChange?.(e => { coverOn.value = e.isVisible; });
});
onBeforeUnmount(() => { clearInterval(tick); off?.dispose?.(); coverOn.value = false; terrTool.value = ""; });
</script>

<style>
/* шаги «граница → загрузка → в проекте»: номер в кружке, под ним карточка; кнопки — сеткой равных колонок (аудит 09.10.2026) */
.data .reset { margin: -2px 0 6px -8px; }
.data .step { padding-bottom: var(--wa-space-m); margin-bottom: var(--wa-space-m); border-bottom: 1px solid var(--g-line); }
.data .sh { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: var(--wa-font-size-s); margin-bottom: 6px; }
.data .sh .num { display: inline-grid; place-items: center; width: 18px; height: 18px; border-radius: 50%; flex: none;
  background: var(--wa-color-neutral-fill-normal); color: var(--wa-color-text-normal); font-size: var(--wa-font-size-2xs); font-weight: 700; }
.data .sh .num.ok { background: var(--wa-color-success-fill-loud); color: #fff; }
.data .sh.tog { all: unset; display: flex; align-items: center; gap: 8px; width: 100%; box-sizing: border-box; font-weight: 600; font-size: var(--wa-font-size-s); margin-bottom: 6px; cursor: pointer; min-height: 24px; }
.data .sh.tog:disabled { cursor: default; }
.data .sh.tog:focus-visible { outline: 2px solid var(--wa-color-focus); outline-offset: 2px; border-radius: 4px; }
.data .sh .chev { flex: none; color: var(--g-muted); transition: transform .15s; }
.data .sh .chev.open { transform: rotate(90deg); }
.data .errs { list-style: none; margin: 0; padding: 0; font-size: var(--wa-font-size-xs); color: var(--wa-color-danger-on-quiet); line-height: 1.4; }
.data .sh .cnt { margin-left: auto; font-weight: 400; color: var(--g-muted); font-size: var(--wa-font-size-xs); font-variant-numeric: tabular-nums; }
.data .lead { margin: 0 0 8px; font-size: var(--wa-font-size-s); line-height: 1.4; }
.data .lead.none { color: var(--g-muted); }
.data .btns { display: grid; grid-template-columns: repeat(auto-fill, minmax(118px, 1fr)); gap: 6px; }
.data .btns > * { margin: 0; min-width: 0; }
.data .btns > .wide { grid-column: 1 / -1; }
.data .btns wa-button::part(label) { display: inline-flex; gap: 4px; align-items: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.data .btns wa-button::part(base) { width: 100%; }
.data .imp { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 6px; align-items: center; margin-top: 6px; }
.data .imp .lbl { color: var(--g-muted); font-size: var(--wa-font-size-xs); white-space: nowrap; }
.data .imp wa-select { margin: 0 !important; min-width: 0; }
.data .imp > wa-button { grid-column: 1 / -1; }   /* кнопка во всю ширину, ниже подпись и выбор системы — текст выбора не обрезается */
.data .imp > wa-button::part(base) { width: 100%; }
.data .imp wa-button::part(label) { display: inline-flex; gap: 4px; align-items: center; }
/* карточка хода выгрузки */
.data .job { margin-top: 10px; padding: 8px 10px; border-radius: 10px; background: var(--wa-color-brand-fill-quiet); border: 1px solid var(--wa-color-brand-border-quiet); }
.data .job.fin { background: var(--wa-color-surface-lowered); border-color: var(--g-line); }
.data .job .jh { display: flex; align-items: center; gap: 8px; font-size: var(--wa-font-size-s); margin-bottom: 6px; }
.data .job .jh .t { white-space: nowrap; margin-left: auto; color: var(--g-muted); font-variant-numeric: tabular-nums; font-size: var(--wa-font-size-xs); }
.data .job .jh wa-button { margin: -4px -6px -4px 0; }
.data .job wa-spinner { font-size: 14px; --track-width: 2px; flex: none; }
.data .job wa-progress-bar { --height: 6px; margin-bottom: 4px; }
.data .job .hint { margin: 4px 0; }
.data .ic.done, .data .jl .done .st { color: var(--wa-color-success-fill-loud); }
.data .ic.error, .data .jl .error .st, .data .jl .error .dt { color: var(--wa-color-danger-on-quiet); }
.data .jl { list-style: none; margin: 6px 0 0; padding: 0; }   /* без своей прокрутки: прокручивается окно (одна полоса на окно) */
.data .jl li { display: grid; grid-template-columns: 16px minmax(0, 1fr) auto; column-gap: 6px; align-items: center; padding: 3px 0; font-size: var(--wa-font-size-s);
  border-top: 1px solid color-mix(in srgb, var(--g-line) 70%, transparent); }
.data .jl li .st { display: inline-grid; place-items: center; color: var(--g-muted); }
.data .jl li .nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.data .jl li .dt { color: var(--g-muted); font-size: var(--wa-font-size-xs); font-variant-numeric: tabular-nums; white-space: nowrap; }
.data .jl li .sub { grid-column: 2 / -1; color: var(--g-muted); font-size: var(--wa-font-size-xs); line-height: 1.35; }
.data .jl li.error .sub { color: var(--wa-color-danger-on-quiet); }
.data .job .all { margin: 2px 0 -4px -8px; }
.data .jl li.run .nm { font-weight: 500; }
.data .jl li .mini { grid-column: 2 / -1; height: 3px; border-radius: 2px; background: var(--wa-color-brand-fill-normal); overflow: hidden; margin-top: 3px; }
.data .jl li .mini i { display: block; height: 100%; background: var(--wa-color-brand-fill-loud); transition: width .3s; }
/* что в проекте — таблица: слой, объектов, дата выгрузки */
.data .srct { width: 100%; border-collapse: collapse; font-size: var(--wa-font-size-s); }
.data .srct th { text-align: left; font-weight: 500; color: var(--g-muted); font-size: var(--wa-font-size-xs); padding: 2px 4px; border-bottom: 1px solid var(--g-line); }
.data .srct th.r, .data .srct td.r { white-space: nowrap; padding-left: 8px; }
.data .srct td { padding: 3px 4px; border-bottom: 1px solid var(--g-line); }
.data .srct .r { text-align: right; font-variant-numeric: tabular-nums; }
.data .srct .d { color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.data .srct .nm { width: 100%; max-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }   /* имя берёт всё, что осталось от чисел */
.data .srct tr.g td { padding-top: 8px; color: var(--g-muted); font-size: var(--wa-font-size-xs); font-weight: 600; border-bottom: 0; }
.data .srct tr.g td svg { vertical-align: -2px; }
.data .srct tr.bad .nm { color: var(--wa-color-danger-on-quiet); }
.data .srct tr.err td { color: var(--wa-color-danger-on-quiet); font-size: var(--wa-font-size-xs); padding-top: 0; }
.data .srct tbody tr:not(.g):not(.err):hover td { background: var(--wa-color-neutral-fill-quiet); }
.data .fgd { margin-top: 2px; }
.data .fgd::part(header) { font-size: var(--wa-font-size-s); font-weight: 600; }
.data .fgd wa-input, .data .fgd wa-select { margin-top: 6px; }
.data .fgl { display: flex; padding: 2px 0; font-size: var(--wa-font-size-s); }
.data .fgl .c { color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.data .kv { display: grid; grid-template-columns: 1fr auto; gap: 2px 10px; font-size: var(--wa-font-size-s); }
.data .kv > div:nth-child(even) { text-align: right; font-variant-numeric: tabular-nums; }
.picker::part(dialog) { width: min(860px, 94vw); }
.picker .pbar, .picker .presets { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-bottom: 6px; font-size: var(--wa-font-size-s); }
.picker .pbar wa-input { flex: 1 1 220px; }
.picker .tree { height: min(56vh, 520px); overflow: auto; border: 1px solid var(--g-line); border-radius: var(--wa-border-radius-s); padding: 4px; font-size: var(--wa-font-size-s); }
.picker .tree details > summary, .picker .tree .ly, .picker .tree .fold { display: flex; gap: 6px; align-items: center; padding: 2px 4px 2px calc(4px + var(--d) * 16px); cursor: pointer; }
.picker .tree details > summary { list-style: none; font-weight: 500; }
.picker .tree details > summary::before { content: "▸"; color: var(--g-muted); width: 10px; }
.picker .tree details[open] > summary::before { content: "▾"; }
.picker .tree .ly:hover, .picker .tree summary:hover { background: var(--wa-color-neutral-fill-quiet); }
.picker .tree .nm { flex: 1; }
.picker .tree .n { color: var(--g-muted); font-variant-numeric: tabular-nums; font-size: var(--wa-font-size-xs); }
.picker .tree .n.has { color: var(--wa-color-brand-on-quiet); font-weight: 600; }
.picker .foot { margin-right: auto; }
</style>
