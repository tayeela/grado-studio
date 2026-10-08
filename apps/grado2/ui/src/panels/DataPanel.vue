<!-- ГРАДО 2 · окно «Данные» нового интерфейса (как окно «Данные» и «Исходные данные» рабочей страницы, web/app.js и
     web/ogdpick.js): граница территории (нарисовать, изменить, из файла, по участкам, из выбранного, пример), область
     загрузки синим пунктиром на карте, что уже в проекте по источникам (число объектов, дата, ошибка, история
     перевыгрузок), сводка существующего положения в границе, импорт файлов и окно выбора источников: дерево ЕГРН,
     подборок и всех слоёв ГИС ОГД, ЕГКО, OSM, Яндекса и рельефа с готовыми наборами и числом объектов в области.
     Логика — data.js. -->
<template>
  <div class="pane data">
    <div class="sect">Граница территории</div>
    <div class="btns">
      <wa-button size="s" :appearance="terrTool === 'draw' ? 'filled' : 'outlined'" :variant="terrTool === 'draw' ? 'brand' : 'neutral'"
                 title="Обвести контур щелчками на карте, двойной щелчок завершает, Esc — отмена" @click="toggle('draw')"><PenLine :size="14" /> Нарисовать</wa-button>
      <wa-button size="s" :appearance="terrTool === 'edit' ? 'filled' : 'outlined'" :variant="terrTool === 'edit' ? 'brand' : 'neutral'" :disabled="!project.territory"
                 title="Ручки на вершинах: тянуть, щелчок по стороне — новая вершина, Alt+щелчок — удалить" @click="toggle('edit')"><Spline :size="14" /> Изменить</wa-button>
      <wa-button size="s" appearance="outlined" title="DXF, DWG, GeoJSON, KML, Shapefile: самый большой замкнутый контур файла" @click="pick('terr')"><FileInput :size="14" /> Из файла</wa-button>
      <wa-button size="s" appearance="outlined" title="Объединение земельных участков по кадастровым номерам" @click="numsDlg = true"><Grid2x2 :size="14" /> По участкам</wa-button>
      <wa-button size="s" appearance="outlined" :disabled="!sel.length" title="Граница — объединение выбранных на карте площадных объектов" @click="territoryFromSelection(selected())"><SquareDashed :size="14" /> Из выбранного</wa-button>
      <wa-button size="s" :appearance="askExample ? 'filled' : 'outlined'" :variant="askExample ? 'danger' : 'neutral'" @click="example">{{ askExample ? "Заменить вашу границу примером?" : "Пример" }}</wa-button>
    </div>
    <p class="hint">{{ coverInfo }}</p>

    <div class="sect">Данные проекта</div>
    <div class="btns">
      <wa-button size="s" variant="brand" :disabled="!cover || !!loading" :title="cover ? 'Окно всех источников: ЕГРН, ГИС ОГД, ЕГКО, OpenStreetMap, Яндекс, рельеф' : 'Сначала нарисуйте границу территории'"
                 @click="openPicker"><Download :size="14" /> Выбрать и загрузить…</wa-button>
      <wa-button size="s" appearance="outlined" title="DXF, DWG, GeoJSON, KML/KMZ, Shapefile — новым слоем; можно перетащить файл на карту" @click="pick('layer')"><FileUp :size="14" /> Файл…</wa-button>
      <wa-select size="s" :value="localSys" title="В какой системе координат файлы в метрах" @change="e => (localSys = e.target.value)">
        <wa-option value="msk">МСК (как в QGIS)</wa-option><wa-option value="ogd">ГИС ОГД</wa-option>
      </wa-select>
    </div>
    <p v-if="loading" class="busy">{{ loading }}. Работать можно дальше.</p>
    <input ref="fileInput" type="file" multiple hidden :accept="FILE_ACCEPT" @change="onFile">

    <p v-if="!groups.length" class="hint">В проекте пока нет загруженных данных. «Выбрать и загрузить…» — окно всех источников.</p>
    <div v-for="g in groups" :key="g.kind" class="src">
      <div class="srch"><Database :size="13" /> <b>{{ g.title }}</b></div>
      <div v-for="k in g.keys" :key="k" class="lr">
        <div class="row"><span class="nm" :title="project.data[k]?.source || ''">{{ SOURCES[k]?.title || project.data[k]?.title || k }}</span><span class="c">{{ count(k) }}</span></div>
        <div v-if="ERRORS[k]" class="err">{{ ERRORS[k] }}</div>
        <div v-if="project.data[k]?.fetched_at" class="meta">выгрузка {{ project.data[k].fetched_at }}{{ hist(project.data[k]) }}{{ project.data[k].notes?.length ? " · " + project.data[k].notes[0] : "" }}</div>
      </div>
    </div>

    <template v-if="summary.length">
      <div class="sect">Существующее положение</div>
      <div class="kv"><template v-for="r in summary" :key="r[0]"><div>{{ r[0] }}</div><div>{{ r[1] }}</div></template></div>
    </template>
    <p class="hint">Загруженные слои появляются в окне «Слои»; их можно править, исходная выгрузка сохраняется (меню слоя → «Вернуть исходную выгрузку»).
      Повторная выгрузка покажет, что изменилось в источнике, и сохранит ваши правки.</p>

    <wa-dialog label="Граница по участкам" :open="numsDlg" @wa-after-hide="numsDlg = false">
      <wa-textarea size="s" rows="4" label="Кадастровые номера (через запятую, пробел или с новой строки)" :value="nums" @input="e => (nums = e.target.value)"></wa-textarea>
      <p class="hint">Берутся участки, уже загруженные из ЕГРН; если их нет — номера ищутся на портале НСПД.</p>
      <wa-button slot="footer" size="s" appearance="plain" @click="numsDlg = false">Отмена</wa-button>
      <wa-button slot="footer" size="s" variant="brand" :disabled="!nums.trim()" @click="byNumbers">Сделать границей</wa-button>
    </wa-dialog>

    <wa-dialog class="picker" label="Исходные данные" :open="pk.open" @wa-after-hide="pk.open = false">
      <div class="pbar">
        <wa-input size="s" type="search" placeholder="Поиск слоя или папки" with-clear :value="pk.q" @input="e => (pk.q = e.target.value)"></wa-input>
        <wa-checkbox size="s" :checked="pk.only" title="Скрыть слои ГИС ОГД, у которых в области нет объектов" @change="e => (pk.only = e.target.checked)">ГИС ОГД — только с объектами</wa-checkbox>
        <wa-button size="s" appearance="outlined" :disabled="!pk.counts" @click="ogdWithObjects">ГИС ОГД с объектами{{ nObj != null ? ` (${nObj})` : "" }}</wa-button>
        <wa-button size="s" appearance="outlined" @click="pk.sel = new Set()">Снять все</wa-button>
      </div>
      <div class="presets">Готовые наборы:
        <wa-button v-for="p in PRESETS" :key="p[0]" size="s" :appearance="presetOn(p) ? 'filled' : 'outlined'" :variant="presetOn(p) ? 'brand' : 'neutral'"
                   :title="p[2] + '. Слоёв: ' + presetKeys(p).length" @click="togglePreset(p)">{{ p[1] }} · {{ presetKeys(p).length }}</wa-button>
      </div>
      <div class="tree"><TreeNode v-for="n in tree" :key="n.num" :n="n" :depth="0" /><p v-if="!tree.length" class="hint">Ничего не найдено.</p></div>
      <span slot="footer" class="hint foot">{{ pk.counts ? "" : "Считаю объекты ГИС ОГД в области… " }}Отмечено: <b>{{ pk.sel.size }}</b>. Большая область для НСПД и OpenStreetMap загружается по частям.</span>
      <wa-button slot="footer" size="s" appearance="plain" @click="pk.open = false">Отмена</wa-button>
      <wa-button slot="footer" size="s" variant="brand" :disabled="!pk.sel.size" @click="loadPicked"><Download :size="14" /> Загрузить в проект</wa-button>
    </wa-dialog>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { Database, Download, FileInput, FileUp, Grid2x2, PenLine, Spline, SquareDashed } from "@lucide/vue";
import { project } from "../store.js";
import { dataRev } from "../edit.js";
import { sel, selected } from "../features.js";
import {
  ERRORS, FILE_ACCEPT, SOURCES, checked, coverBox, coverOn, coverText, existingSummary, exampleTerritory, importBoundary, importFiles,
  keepChecked, loadKeys, loadSources, loading, localSys, terrTool, territoryByNumbers, territoryFromSelection,
} from "../data.js";

const props = defineProps({ params: Object });

const GROUP = { gisogd_admin: "Административное деление Москвы (эталон)", fgistp: "ФГИС ТП (загруженные слои документов)", import: "Импорт файлов", nspd: "ЕГРН · НСПД", osm: "OpenStreetMap",
  gisogd: "ГИС ОГД Москвы", egko: "ЕГКО Москвы — картооснова ГИС ОГД", terrain: "Рельеф", yandex_sit: "Яндекс Карты для ситуационного плана",
  yandex: "Яндекс Карты (для анализа и эскиза, в сдаваемые материалы не включать)" };
const fmt = v => Number(v).toLocaleString("ru-RU");

const cover = computed(() => (project.territory, project.raw, coverBox()));
const coverInfo = computed(() => (project.territory, project.raw, coverText()));
const summary = computed(() => (dataRev.value, project.territory, existingSummary()));
const groups = computed(() => {
  dataRev.value;
  const by = {};
  const keys = new Set([...Object.keys(project.data), ...Object.keys(ERRORS)]);
  keys.forEach(k => { const kind = SOURCES[k]?.kind || (k.startsWith("import:") ? "import" : k.startsWith("user:") ? "" : k.split(".")[0]); if (kind) (by[kind] ||= []).push(k); });
  const known = Object.entries(by).filter(([kind]) => GROUP[kind]), other = Object.entries(by).filter(([kind]) => !GROUP[kind]).flatMap(([, ks]) => ks);
  return known.map(([kind, keys]) => ({ kind, title: GROUP[kind], keys })).concat(other.length ? [{ kind: "other", title: "Прочие слои", keys: other }] : []);
});
const count = k => { const n = project.data[k]?.fc?.features?.length; return n == null ? "" : fmt(n); };
const hist = d => { const hh = d.history || [], x = hh[hh.length - 1]; return hh.length > 1 && x.added != null ? ` · выгрузок ${hh.length}, в последней +${x.added} −${x.removed} ~${x.changed}` : ""; };

function toggle(t) { terrTool.value = terrTool.value === t ? "" : t; }
let askT = null; const askExample = ref(false);
function example() {
  if (project.territory && !askExample.value) { askExample.value = true; askT = setTimeout(() => (askExample.value = false), 5000); return; }
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
const pk = reactive({ open: false, q: "", only: true, sel: new Set(), counts: null, ogd: null, opened: new Map() });
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
  if (!isOgd(k)) return project.data[k] ? h("span", { class: "n has", title: "Уже в проекте: объектов" }, fmt(project.data[k].fc?.features?.length || 0)) : null;
  const v = cnt(k);
  return v === undefined ? h("span", { class: "n" }, "…") : v === null ? h("span", { class: "n", title: "Слоя нет в кэше на диске — число объектов станет известно при выгрузке" }, "?") : h("span", { class: "n" + (v ? " has" : "") }, fmt(v));
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

async function openPicker() {
  const bb = coverBox(); if (!bb) return;
  pk.sel = checked(); pk.q = ""; pk.counts = null; pk.open = true;
  if (!Object.keys(SOURCES).length) await loadSources();
  try { if (!pk.ogd) pk.ogd = (await (await fetch("/api/ogd_all/tree")).json()).tree || []; } catch { pk.ogd = []; }
  try {
    const r = await fetch("/api/ogd_all/scan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ bbox: bb }) });
    pk.counts = r.ok ? (await r.json()).counts || {} : {};
  } catch { pk.counts = {}; }
}
function loadPicked() {
  const keys = [...pk.sel];
  tree.value.flatMap(leaves).filter(l => isOgd(l.key) && pk.sel.has(l.key)).forEach(l => { SOURCES[l.key] ||= { title: `${l.name} (ОГД)`, kind: "gisogd" }; });
  keepChecked(pk.sel); pk.open = false;
  loadKeys(keys, coverBox());
}

/* область загрузки видна на карте, пока окно на виду */
let off = null;
onMounted(() => {
  loadSources();
  const api = props.params?.api;
  coverOn.value = api ? api.isVisible : true;
  off = api?.onDidVisibilityChange?.(e => { coverOn.value = e.isVisible; });
});
onBeforeUnmount(() => { off?.dispose?.(); coverOn.value = false; terrTool.value = ""; });
</script>

<style>
.data .sect { margin: var(--wa-space-s) 0 4px; font-weight: 600; font-size: var(--wa-font-size-s); }
.data .btns { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.data .btns wa-select { width: 160px; }
.data .btns wa-button::part(label) { display: inline-flex; gap: 4px; align-items: center; }
.data .busy { color: var(--wa-color-brand-on-quiet); font-size: var(--wa-font-size-xs); }
.data .src { margin-top: var(--wa-space-s); }
.data .srch { display: flex; gap: 5px; align-items: center; font-size: var(--wa-font-size-xs); color: var(--g-muted); margin-bottom: 2px; }
.data .lr { padding: 2px 0 3px 18px; border-bottom: 1px solid var(--g-line); }
.data .lr .row { display: flex; gap: 6px; font-size: var(--wa-font-size-s); }
.data .lr .nm { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.data .lr .c { font-variant-numeric: tabular-nums; color: var(--g-muted); }
.data .err { color: var(--wa-color-danger-on-quiet); font-size: var(--wa-font-size-xs); }
.data .meta { color: var(--g-muted); font-size: var(--wa-font-size-2xs); }
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
