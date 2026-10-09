<!-- ГРАДО 2 · каркас нового интерфейса: шапка с меню и кнопкой «Листы и альбом» (отдельное окно, albumhost.js), лента инструментов, окна dockview, строка состояния;
     на общем сервере — вход, шапка и окна совместной работы (HubLogin, HubBar, HubWindows, окно «Комментарии»).
     Раскладку окон помнит браузер (localStorage «grado-next-layout»); панели — src/panels/*.vue. -->
<template>
  <div class="shell">
    <header class="top">
      <span class="brand">ГРАДО 2</span>
      <span v-if="!shared" class="project" :title="projTitle">{{ project.name || "Без названия" }}{{ dirty ? " •" : "" }}
        <wa-badge v-if="shared" variant="neutral" appearance="filled-outlined">общий сервер</wa-badge></span>

      <HubBar v-if="shared" />
      <wa-dropdown @wa-select="onProject">
        <wa-button slot="trigger" size="s" appearance="plain" with-caret>Проект</wa-button>
        <template v-if="shared">
          <wa-dropdown-item value="hubprojects">Совместные проекты…</wa-dropdown-item>
          <wa-dropdown-item value="hubsave" :disabled="!hub.pid">Сохранить на сервере сейчас<span slot="details">Ctrl+S</span></wa-dropdown-item>
          <wa-dropdown-item value="hubshare" :disabled="!hub.pid">Доступ…</wa-dropdown-item>
          <wa-dropdown-item value="hubhistory" :disabled="!hub.pid">История версий…</wa-dropdown-item>
          <wa-divider></wa-divider>
          <wa-dropdown-item value="download">Скачать файл проекта</wa-dropdown-item>
        </template>
        <template v-else>
        <wa-dropdown-item value="open">Открыть…</wa-dropdown-item>
        <wa-dropdown-item value="save" :disabled="shared">Сохранить<span slot="details">Ctrl+S</span></wa-dropdown-item>
        <wa-dropdown-item value="saveas" :disabled="shared">Сохранить как…</wa-dropdown-item>
        <wa-dropdown-item value="new" :disabled="shared">Новый проект</wa-dropdown-item>
        <wa-divider></wa-divider>
        <wa-dropdown-item value="file">Открыть файл .grado2 с диска…</wa-dropdown-item>
        <wa-dropdown-item value="download">Скачать файл проекта</wa-dropdown-item>
        </template>
      </wa-dropdown>
      <input ref="fileInput" type="file" accept=".grado2,application/json" hidden @change="onFile">

      <wa-dropdown @wa-select="onWindow">
        <wa-button slot="trigger" size="s" appearance="plain" with-caret>Окна</wa-button>
        <wa-dropdown-item v-for="p in PANELS.filter(x => x.id !== 'comments' || shared)" :key="p.id" type="checkbox" :value="p.id" :checked="open[p.id]">{{ p.title }}</wa-dropdown-item>
        <wa-divider></wa-divider>
        <wa-dropdown-item value="reset">Раскладка по умолчанию</wa-dropdown-item>
      </wa-dropdown>

      <wa-dropdown @wa-select="onExport">
        <wa-button slot="trigger" size="s" appearance="plain" with-caret :disabled="busy">Выгрузка</wa-button>
        <h4 class="menu-h">Данные</h4>
        <wa-dropdown-item value="dxf">Чертёж DXF — слои проекта, МСК<span slot="details">МГГТ</span></wa-dropdown-item>
        <wa-dropdown-item value="geojson">GeoJSON для QGIS<span slot="details">МСК</span></wa-dropdown-item>
        <wa-dropdown-item value="xlsx">Excel: показатели ТЭП и листы<span slot="details">XLSX</span></wa-dropdown-item>
        <wa-divider></wa-divider>
        <h4 class="menu-h">Альбом — в окне «Листы и альбом»</h4>
        <wa-dropdown-item value="pdf" :disabled="!album.sheets">PDF альбома<span slot="details">{{ album.sheets ? "все листы" : "нет листов" }}</span></wa-dropdown-item>
        <wa-dropdown-item value="pptx" :disabled="!album.sheets">PPTX альбома<span slot="details">PowerPoint</span></wa-dropdown-item>
        <wa-dropdown-item value="ogd">ГИС ОГД в DXF — по рамке листа<span slot="details">МСК</span></wa-dropdown-item>
      </wa-dropdown>
      <wa-button size="s" appearance="plain" title="Листы и альбом (Ctrl+P): рамки листов на карте, штамп, сборка альбома ППТ КРТ, PDF и PPTX — отдельным окном, как макет в QGIS"
                 @click="openAlbum()"><Printer :size="16" /> Листы и альбом<span v-if="album.sheets" class="cnt">{{ album.sheets }}</span></wa-button>

      <span class="grow"></span>
      <wa-button size="s" appearance="plain" :disabled="!history.undo" title="Отменить (Ctrl+Z)" @click="undo"><Undo2 :size="16" /></wa-button>
      <wa-button size="s" appearance="plain" :disabled="!history.redo" title="Вернуть (Ctrl+Shift+Z)" @click="redo"><Redo2 :size="16" /></wa-button>
      <wa-button size="s" appearance="plain" title="Справка и клавиши (F1)" @click="showHelp"><CircleHelp :size="16" /></wa-button>
      <wa-button size="s" appearance="plain" @click="toggleTheme" :title="theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'">
        <Sun v-if="theme === 'dark'" :size="16" /><Moon v-else :size="16" />
      </wa-button>
    </header>

    <nav class="ribbon" aria-label="Команды черчения">
      <div v-for="g in TOOLS" :key="g.title" class="tgroup">
        <div class="tbtns">
          <wa-button v-for="id in g.items" :key="id" size="s" appearance="plain" :disabled="!cad.ready"
                     :class="{ on: cad.cmd === id }" :title="cmdTip(id)" :aria-label="cmdTitle(id)" @click="runCmd(id)">
            <svg class="ci" aria-hidden="true"><use :href="'#ci-' + id" /></svg>
          </wa-button>
          <wa-dropdown v-for="m in g.menus || []" :key="m.title" @wa-select="e => runCmd(e.detail.item.value)">
            <wa-button slot="trigger" size="s" appearance="plain" with-caret :disabled="!cad.ready" :title="m.title + ': ' + m.items.map(cmdTitle).join(', ').toLowerCase()">
              <svg v-if="m.icon" class="ci" aria-hidden="true"><use :href="'#ci-' + m.icon" /></svg><template v-else>Ещё</template>
            </wa-button>
            <template v-for="sec in m.sections || [{ items: m.items }]" :key="sec.title || 'main'">
              <h4 v-if="sec.title" class="menu-h">{{ sec.title }}</h4>
              <wa-dropdown-item v-for="id in sec.items" :key="id" :value="id" :title="cmdHelp(id)">
                <svg slot="icon" class="ci" aria-hidden="true"><use :href="'#ci-' + id" /></svg>{{ cmdTitle(id) }}<span slot="details">{{ cmdKey(id) }}</span>
              </wa-dropdown-item>
            </template>
          </wa-dropdown>
        </div>
        <div class="tlabel">{{ g.title }}</div>
      </div>
    </nav>

    <DockviewVue class="grado-dock dock" :theme="dockTheme" @ready="onReady" />

    <wa-dialog label="Открыть проект" :open="openDlg" @wa-after-hide="openDlg = false" class="open-dlg">
      <p class="hint" :title="projDir">Папка проектов: {{ projDir }}</p>
      <p v-if="!projects.length" class="hint">В папке проектов нет файлов. Открытая работа сохраняется сама; «Сохранить» — под именем.</p>
      <div v-for="p in projects" :key="p.name" class="prow" :class="{ cur: p.name === project.file }" @click="choose(p.name)">
        <span>{{ p.name }}<span v-if="p.album_n" class="when"> · альбом: {{ p.album_n }} л.</span></span><span class="when">{{ when(p.modified) }}</span>
      </div>
    </wa-dialog>

    <wa-dialog label="Сохранить проект" :open="saveDlg" @wa-after-hide="saveDlg = false" class="save-dlg">
      <wa-input ref="nameInput" label="Название проекта" size="s" :value="saveName" @input="e => { saveName = e.target.value; clash = null; }"
                @keydown.enter="doSaveAs"></wa-input>
      <p v-if="clash" class="warn">В папке уже есть проект «{{ clash.name }}» (изменён {{ when(clash.modified) }}). Нажмите «Заменить», чтобы записать поверх него.</p>
      <p class="hint">Файл ляжет в папку проектов: {{ projDir }}</p>
      <wa-button slot="footer" size="s" appearance="plain" @click="saveDlg = false">Отмена</wa-button>
      <wa-button slot="footer" size="s" :variant="clash ? 'danger' : 'brand'" :disabled="!saveName.trim() || busy" @click="doSaveAs">{{ clash ? "Заменить" : "Сохранить" }}</wa-button>
    </wa-dialog>

    <wa-dialog label="Несохранённые изменения" :open="!!ask" @wa-after-hide="ask = null">
      <p>{{ ask?.text }} Изменения после последнего сохранения останутся только в автосохранении и пропадут при следующей правке.</p>
      <wa-button slot="footer" size="s" appearance="plain" @click="ask = null">Отмена</wa-button>
      <wa-button slot="footer" size="s" appearance="outlined" @click="saveThen">Сначала сохранить</wa-button>
      <wa-button slot="footer" size="s" variant="danger" @click="goAnyway">Не сохранять</wa-button>
    </wa-dialog>

    <HubWindows v-if="shared" />
    <HubLogin />

    <footer class="status">
      <CadModes />
      <span class="cmdnow">{{ toolTitle }}</span>
      <span class="grow"></span>
      <span>Слой: {{ current?.title }}</span>
      <wa-dropdown placement="top-end" @wa-select="e => setBasemap(e.detail.item.value)">
        <button slot="trigger" class="basebtn" title="Подложка карты">Подложка: {{ BASEMAPS[basemapId] }}</button>
        <wa-dropdown-item v-for="(t, id) in BASEMAPS" :key="id" type="checkbox" :value="id" :checked="basemapId === id">{{ t }}</wa-dropdown-item>
      </wa-dropdown>
      <span>Масштаб 1:{{ scale.toLocaleString("ru-RU") }}</span>
      <span class="note" :title="notice">{{ busy ? "Записываю…" : notice || (project.source === "autosave" ? "Восстановлена последняя работа" : "") }}</span>
    </footer>
  </div>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue";
import { DockviewVue, themeLight } from "dockview-vue";
import { Undo2, Redo2, CircleHelp, Printer } from "@lucide/vue";
import CadModes from "./panels/CadModes.vue";
import HubBar from "./panels/HubBar.vue";
import HubLogin from "./panels/HubLogin.vue";
import HubWindows from "./panels/HubWindows.vue";
import { flush as hubFlush, hub, openWin } from "./hub.js";
import { RIBBON, cad, cadApi, cadIcons } from "./cad.js";
import { exportDxf, exportGeojson, exportXlsx } from "./exports.js";
import { album, albumFile, albumHooks, ogdDxf, openAlbum } from "./albumhost.js";
import { terrTool } from "./data.js";
import { history, redo, undo } from "./edit.js";
import { deleteFeatures, sel, selectAll, setSel } from "./features.js";
import { BASEMAPS, basemapId, current, project, scale, setBasemap, theme, toggleTheme, winApi } from "./store.js";
import {
  busy, clashOf, dirty, downloadProject, listProjects, newProject, notice, openFile, openProject, openStartup, projDir, projects, saveProject, shared,
} from "./project.js";

const dockTheme = { ...themeLight, className: "dockview-theme-grado" };

const PANELS = [
  { id: "map", title: "Карта" },
  { id: "layers", title: "Слои" },
  { id: "props", title: "Свойства" },
  { id: "object", title: "Объект" },
  { id: "tep", title: "Показатели (ТЭП)" },
  { id: "table", title: "Таблица атрибутов" },
  { id: "data", title: "Данные" },
  { id: "cons", title: "Ограничения" },
  { id: "graph", title: "Схема расчёта" },
  { id: "sketch", title: "Эскиз" },
  { id: "norms", title: "Нормативы расчёта" },
  { id: "vars", title: "Варианты" },
  { id: "cmp", title: "Сравнение" },
  { id: "vol", title: "Объём" },
  { id: "views", title: "Виды" },
  { id: "help", title: "Справка" },
  { id: "comments", title: "Комментарии" },
  { id: "sheet", title: "Макет листа" },
];
const open = reactive(Object.fromEntries(PANELS.map(p => [p.id, false])));

/* Лента — команды черчения как в рабочей странице (cad.js RIBBON): кнопка запускает команду, повторный щелчок прерывает. */
const TOOLS = [
  { title: "Рисование", items: RIBBON.draw, menus: [{ title: "Оформление", icon: "dim", items: RIBBON.anno }] },
  { title: "Правка", items: RIBBON.modify, menus: [{ title: "Ещё команды", items: [...RIBBON.more, ...RIBBON.gis], sections: [{ items: RIBBON.more }, { title: "Полигоны и атрибуты", items: RIBBON.gis }] }] },
  { title: "Измерить", items: RIBBON.measure },
  { title: "Территория", items: RIBBON.terr },
];
cadIcons();
const cmdTitle = id => (cad.ready && cadApi.CMDS[id]?.title) || id;
const cmdKey = id => (cad.ready && cadApi.CMDS[id]?.alias[0]) || "";
const cmdHelp = id => (cad.ready && cadApi.HELP[id]) || "";
const cmdTip = id => cad.ready ? `${cmdTitle(id)} — ${cadApi.CMDS[id].alias.join(", ")} и Enter: ${cmdHelp(id)}` : "Откройте окно «Карта»: команды работают на ней";
function runCmd(id) { if (cad.cmd === id) cadApi.cancel(); else cadApi.start(id); }
const toolTitle = computed(() => cad.cmd ? `Команда: ${cmdTitle(cad.cmd)}` : cad.ready ? "Наберите команду (L, PL, C, M, TR…) и Enter или выберите на ленте" : "");

const LAYOUT_KEY = "grado-next-layout";
let api = null;

function defaultLayout() {
  api.clear();
  api.addPanel({ id: "map", component: "map", title: "Карта" });
  api.addPanel({ id: "layers", component: "layers", title: "Слои", position: { referencePanel: "map", direction: "left" }, initialWidth: 260 });
  api.addPanel({ id: "props", component: "props", title: "Свойства", position: { referencePanel: "map", direction: "right" }, initialWidth: 280 });
  api.addPanel({ id: "object", component: "object", title: "Объект", position: { referencePanel: "props", direction: "within" } });
  api.addPanel({ id: "data", component: "data", title: "Данные", position: { referencePanel: "layers", direction: "within" } });
  api.addPanel({ id: "views", component: "views", title: "Виды", position: { referencePanel: "layers", direction: "within" } });
  api.addPanel({ id: "cons", component: "cons", title: "Ограничения", position: { referencePanel: "props", direction: "within" } });
  api.addPanel({ id: "tep", component: "tep", title: "Показатели (ТЭП)", position: { referencePanel: "map", direction: "below" }, initialHeight: 190 });
  api.addPanel({ id: "table", component: "table", title: "Таблица атрибутов", position: { referencePanel: "tep", direction: "within" } });
  api.addPanel({ id: "graph", component: "graph", title: "Схема расчёта", position: { referencePanel: "tep", direction: "within" }, inactive: true });
  api.addPanel({ id: "vars", component: "vars", title: "Варианты", position: { referencePanel: "tep", direction: "within" }, inactive: true });
  api.addPanel({ id: "sketch", component: "sketch", title: "Эскиз", position: { referencePanel: "props", direction: "within" }, inactive: true });
  api.getPanel("layers")?.api.setActive();
  api.getPanel("props")?.api.setActive();
  api.getPanel("map")?.api.setActive();
  try { localStorage.setItem("grado-next-seen", JSON.stringify(Object.keys(NEW_WINDOWS))); } catch { /* частный режим браузера */ }
}

/* Раскладка из браузера сохранена до появления новых окон: перенесённое окно встаёт на своё место по умолчанию один раз,
   дальше пользователь закрывает и двигает его сам (список показанных — «grado-next-seen»). */
const NEW_WINDOWS = { object: ["props", "within"], table: ["tep", "within"], views: ["layers", "within"], data: ["layers", "within"], cons: ["props", "within"], graph: ["tep", "within"], sketch: ["props", "within"], vars: ["tep", "within"] };
function addNewWindows() {
  let seen = [];
  try { seen = JSON.parse(localStorage.getItem("grado-next-seen") || "[]"); } catch { /* нет — все новые */ }
  for (const [id, [ref, direction]] of Object.entries(NEW_WINDOWS)) {
    if (seen.includes(id) || api.getPanel(id)) continue;
    const title = PANELS.find(x => x.id === id).title;
    api.addPanel({ id, component: id, title, ...(api.getPanel(ref) ? { position: { referencePanel: ref, direction } } : { floating: { x: 300, y: 80, width: 440, height: 280 } }), inactive: true });
  }
  try { localStorage.setItem("grado-next-seen", JSON.stringify(Object.keys(NEW_WINDOWS))); } catch { /* частный режим браузера */ }
}

function addOne(id) {
  const p = PANELS.find(x => x.id === id);
  // макет листа — большое окно: вкладкой рядом с картой, как макет в QGIS открывается отдельным окном во всю ширину
  // и сразу во всё окно (остальные окна прячутся, вернуть — двойной щелчок по вкладке или кнопка группы)
  if (id === "sheet") {
    const panel = api.addPanel({ id, component: id, title: p.title, position: api.getPanel("map") ? { referencePanel: "map", direction: "within" } : undefined });
    panel.api.maximize();
    return;
  }
  const [w, h] = { norms: [560, 600], sketch: [440, 600], comments: [380, 560], vars: [900, 420], cmp: [1000, 520], vol: [620, 460] }[id] || [440, 280];   // длинные и широкие окна — крупнее
  const k = api.groups.filter(g => g.api.location?.type === "floating").length % 6;   // плавающие окна — лесенкой, не одно на другом
  api.addPanel({ id, component: id, title: p.title, floating: { x: 300 + k * 28, y: 80 + k * 28, width: w, height: h } });
}

function showHelp() {
  const p = api?.getPanel("help");
  if (p) p.api.setActive(); else api?.addPanel({ id: "help", component: "help", title: "Справка", floating: { x: 360, y: 90, width: 520, height: 460 } });
  syncOpen();
}

function onExport(e) {
  const v = e.detail.item.value;
  if (v === "dxf") exportDxf(); else if (v === "geojson") exportGeojson(); else if (v === "xlsx") exportXlsx();
  else if (v === "pdf" || v === "pptx") albumFile(v); else if (v === "ogd") ogdDxf();
}

winApi.open = id => { const p = api?.getPanel(id); if (p) p.api.setActive(); else if (api) addOne(id); syncOpen(); };
function syncOpen() { for (const p of PANELS) open[p.id] = !!api.getPanel(p.id); }

function onReady(event) {
  api = event.api;
  let restored = false;
  try {
    const s = localStorage.getItem(LAYOUT_KEY);
    if (s) { api.fromJSON(JSON.parse(s)); restored = true; }
  } catch { restored = false; }
  if (!restored) defaultLayout();
  else addNewWindows();
  syncOpen();
  api.onDidLayoutChange(() => {
    syncOpen();
    try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(api.toJSON())); } catch { /* частный режим браузера */ }
  });
}

function onWindow(e) {
  const v = e.detail.item.value;
  if (v === "reset") { defaultLayout(); return; }
  const panel = api.getPanel(v);
  if (panel) panel.api.close(); else addOne(v);
  syncOpen();
}

/* Проект: открыть, сохранить, сохранить как, новый, файл с диска и на диск (project.js). */
const openDlg = ref(false), saveDlg = ref(false), saveName = ref(""), clash = ref(null), ask = ref(null);
const fileInput = ref(null), nameInput = ref(null);
const projTitle = computed(() => (project.file ? `Проект «${project.file}» в папке проектов` : "Проект ещё не сохранён под именем")
  + (dirty.value ? " · есть несохранённые изменения (автосохранение держит их до сохранения)" : ""));

/* Действие, после которого открытая работа сменится: при несохранённых правках сначала спросить. */
function guard(text, go) { if (dirty.value && !shared.value) ask.value = { text, go }; else go(); }
async function saveThen() {
  const a = ask.value; ask.value = null;
  if (project.file) { if (await saveProject()) a.go(); } else { pending = a.go; askName(); }
}
function goAnyway() { const a = ask.value; ask.value = null; a.go(); }
let pending = null;

async function askName() {
  saveName.value = project.name || ""; clash.value = null; saveDlg.value = true;
  try { await listProjects(); } catch { /* список для подсказки папки */ }
  await nextTick(); nameInput.value?.focus();
}
async function doSaveAs() {
  const name = saveName.value.trim(); if (!name) return;
  if (!clash.value) { const c = await clashOf(name); if (c) { clash.value = c; return; } }
  if (await saveProject(name)) { saveDlg.value = false; const p = pending; pending = null; p?.(); }
}
async function save() { if (project.file && project.name === project.file) await saveProject(); else await askName(); }

async function onProject(e) {
  const v = e.detail.item.value;
  if (v === "hubprojects") openWin("projects");
  else if (v === "hubsave") hubFlush();
  else if (v === "hubshare") openWin("share");
  else if (v === "hubhistory") openWin("history");
  else if (v === "open") { try { await listProjects(); } catch { /* список останется прежним */ } openDlg.value = true; }
  else if (v === "save") save();
  else if (v === "saveas") askName();
  else if (v === "new") guard("Начать новый проект?", newProject);
  else if (v === "file") fileInput.value.click();
  else if (v === "download") downloadProject();
}
function choose(name) { openDlg.value = false; guard(`Открыть «${name}»?`, () => openProject(name)); }
albumHooks.save = () => shared.value ? hubFlush() : save();     // Ctrl+S в окне «Листы и альбом»
albumHooks.open = choose;
function onFile(e) { const f = e.target.files[0]; e.target.value = ""; if (f) guard(`Открыть «${f.name}»?`, () => openFile(f)); }
const when = t => t ? new Date(t * 1000).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "";

const typing = e => e.composedPath().some(n => n instanceof HTMLElement && (n.matches("input, textarea, select, [contenteditable]")));
addEventListener("keydown", e => {
  if (e.key === "F1") { e.preventDefault(); showHelp(); return; }
  if (!(e.metaKey || e.ctrlKey)) {
    if (typing(e) || e.altKey) return;
    if ((e.key === "Delete" || e.key === "Backspace") && sel.length) {
      e.preventDefault(); const n = sel.length; deleteFeatures([...sel]); notice.value = `Удалено объектов: ${n}. Ctrl+Z — вернуть`;
    } else if (e.key === "Escape" && terrTool.value) terrTool.value = "";
    else if (e.key === "Escape" && sel.length) setSel([]);
    return;
  }
  if (e.code === "KeyA" && !typing(e) && current.value) {
    e.preventDefault(); selectAll(current.value.key); notice.value = `Выбраны все объекты слоя «${current.value.title}»: ${sel.length}`; return;
  }
  if (e.code === "KeyS") { e.preventDefault(); if (shared.value) hubFlush(); else save(); }
  else if (e.code === "KeyP" && !e.shiftKey && !e.altKey) { e.preventDefault(); openAlbum(); }   // как в рабочей странице: листы вместо печати страницы
  else if (typing(e)) return;                       // в поле ввода Ctrl+Z правит текст поля
  else if (e.code === "KeyZ" && !e.shiftKey) { e.preventDefault(); if (!undo()) notice.value = "Отменять нечего"; }
  else if ((e.code === "KeyZ" && e.shiftKey) || e.code === "KeyY") { e.preventDefault(); redo(); }
});
watch(() => [project.name, dirty.value], () => { document.title = (project.name || "Без названия") + (dirty.value ? " •" : "") + " — ГРАДО 2"; });

openStartup();
</script>

<style>
.shell { display: grid; grid-template-rows: auto auto 1fr auto; grid-template-columns: minmax(0, 1fr); height: 100%; }
.top {
  display: flex; align-items: center; gap: var(--wa-space-2xs);
  padding: 2px var(--wa-space-s); background: var(--g-bar); border-bottom: 1px solid var(--g-line); min-height: 34px; min-width: 0; overflow: hidden;
}
.top .cnt { margin-left: 6px; padding: 0 6px; border-radius: 8px; font-size: var(--wa-font-size-2xs); line-height: 16px; background: var(--wa-color-neutral-fill-normal); }
.brand { font-weight: 700; letter-spacing: .02em; margin-right: var(--wa-space-s); }
.project { color: var(--g-muted); margin-right: var(--wa-space-m); display: inline-flex; gap: 6px; align-items: center; }
.grow { flex: 1; }
.menu-h { margin: 6px 12px 2px; font-size: var(--wa-font-size-2xs); color: var(--g-muted); font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
.ribbon {
  display: flex; gap: 0; padding: 2px var(--wa-space-xs) 0; background: var(--g-bar); border-bottom: 1px solid var(--g-line);
}
.tgroup { display: flex; flex-direction: column; align-items: center; padding: 0 var(--wa-space-s); border-right: 1px solid var(--g-line); }
.tgroup:last-child { border-right: 0; }
.tbtns { display: flex; align-items: center; }
.ribbon .ci { width: 18px; height: 18px; display: block; }
wa-dropdown-item .ci { width: 16px; height: 16px; }
.status > .cmdnow { flex: 0 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.tbtns wa-button::part(base) { padding-inline: 6px; }
.tbtns wa-button.on::part(base) { background: var(--wa-color-brand-fill-quiet); color: var(--wa-color-brand-on-quiet); }
.tlabel { font-size: var(--wa-font-size-2xs); color: var(--g-muted); padding-bottom: 2px; }
.dock { min-height: 0; }
.open-dlg .prow { display: flex; justify-content: space-between; gap: var(--wa-space-m); padding: 5px 8px; border-radius: var(--wa-border-radius-s); cursor: pointer; }
.open-dlg .prow:hover { background: var(--wa-color-neutral-fill-quiet); }
.open-dlg .prow.cur { background: var(--wa-color-brand-fill-quiet); }
.save-dlg .warn { color: var(--wa-color-danger-on-quiet); font-size: var(--wa-font-size-s); }
.open-dlg .when { color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.status wa-dropdown { display: inline-flex; }
.status .basebtn { font: inherit; font-size: var(--wa-font-size-xs); color: inherit; background: none; border: 0; padding: 0 2px; cursor: pointer; }
.status .basebtn:hover { color: var(--wa-color-text-normal); text-decoration: underline; }
.status {
  display: flex; gap: var(--wa-space-l); align-items: center; padding: 0 var(--wa-space-s);
  height: 22px; font-size: var(--wa-font-size-xs); color: var(--g-muted); background: var(--g-bar); border-top: 1px solid var(--g-line);
}
.status > * { flex: none; white-space: nowrap; }
.status > .grow { flex: 1; }
/* длинное сообщение («Эскиз сохранён слоем…») не ломает строку: обрезается многоточием, целиком — в подсказке */
.status > .note { flex: 0 1 auto; min-width: 0; max-width: 50%; overflow: hidden; text-overflow: ellipsis; }
</style>
