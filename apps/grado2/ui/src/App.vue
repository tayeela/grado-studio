<!-- ГРАДО 2 · каркас нового интерфейса: шапка с меню, лента инструментов, окна dockview, строка состояния.
     Раскладку окон помнит браузер (localStorage «grado-next-layout»); панели — src/panels/*.vue. -->
<template>
  <div class="shell">
    <header class="top">
      <span class="brand">ГРАДО 2</span>
      <span class="project" :title="projTitle">{{ project.name || "Без названия" }}{{ dirty ? " •" : "" }}
        <wa-badge v-if="shared" variant="neutral" appearance="filled-outlined">общий сервер</wa-badge></span>

      <wa-dropdown @wa-select="onProject">
        <wa-button slot="trigger" size="s" appearance="plain" with-caret>Проект</wa-button>
        <wa-dropdown-item value="open">Открыть…</wa-dropdown-item>
        <wa-dropdown-item value="save" :disabled="shared">Сохранить<span slot="details">Ctrl+S</span></wa-dropdown-item>
        <wa-dropdown-item value="saveas" :disabled="shared">Сохранить как…</wa-dropdown-item>
        <wa-dropdown-item value="new" :disabled="shared">Новый проект</wa-dropdown-item>
        <wa-divider></wa-divider>
        <wa-dropdown-item value="file">Открыть файл .grado2 с диска…</wa-dropdown-item>
        <wa-dropdown-item value="download">Скачать файл проекта</wa-dropdown-item>
        <wa-divider></wa-divider>
        <wa-dropdown-item value="history" disabled>История версий</wa-dropdown-item>
        <wa-dropdown-item value="share" disabled>Совместная работа</wa-dropdown-item>
      </wa-dropdown>
      <input ref="fileInput" type="file" accept=".grado2,application/json" hidden @change="onFile">

      <wa-dropdown @wa-select="onWindow">
        <wa-button slot="trigger" size="s" appearance="plain" with-caret>Окна</wa-button>
        <wa-dropdown-item v-for="p in PANELS" :key="p.id" type="checkbox" :value="p.id" :checked="open[p.id]">{{ p.title }}</wa-dropdown-item>
        <wa-divider></wa-divider>
        <wa-dropdown-item value="reset">Раскладка по умолчанию</wa-dropdown-item>
      </wa-dropdown>

      <wa-dropdown @wa-select="onExport">
        <wa-button slot="trigger" size="s" appearance="plain" with-caret :disabled="busy">Выгрузка</wa-button>
        <h4 class="menu-h">Данные</h4>
        <wa-dropdown-item value="dxf">Чертёж DXF — слои проекта, МСК<span slot="details">МГГТ</span></wa-dropdown-item>
        <wa-dropdown-item value="geojson">GeoJSON для QGIS<span slot="details">МСК</span></wa-dropdown-item>
        <wa-divider></wa-divider>
        <h4 class="menu-h">Пока в рабочей странице</h4>
        <wa-dropdown-item value="pdf" disabled>PDF и PPTX альбома — с окном «Листы»</wa-dropdown-item>
        <wa-dropdown-item value="ogd" disabled>ГИС ОГД в DXF — с рамкой листа</wa-dropdown-item>
        <wa-dropdown-item value="xlsx" disabled>Excel: ТЭП и листы — с окном «Показатели»</wa-dropdown-item>
      </wa-dropdown>

      <span class="grow"></span>
      <wa-button size="s" appearance="plain" :disabled="!history.undo" title="Отменить (Ctrl+Z)" @click="undo"><Undo2 :size="16" /></wa-button>
      <wa-button size="s" appearance="plain" :disabled="!history.redo" title="Вернуть (Ctrl+Shift+Z)" @click="redo"><Redo2 :size="16" /></wa-button>
      <wa-button size="s" appearance="plain" title="Справка и клавиши (F1)" @click="showHelp"><CircleHelp :size="16" /></wa-button>
      <wa-button size="s" appearance="plain" @click="toggleTheme" :title="theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'">
        <Sun v-if="theme === 'dark'" :size="16" /><Moon v-else :size="16" />
      </wa-button>
    </header>

    <nav class="ribbon" aria-label="Инструменты">
      <div v-for="g in TOOLS" :key="g.title" class="tgroup">
        <div class="tbtns">
          <wa-button v-for="t in g.items" :key="t.id" size="s" appearance="plain"
                     :class="{ on: tool === t.id }" :title="t.title + (t.key ? ' (' + t.key + ')' : '')" @click="tool = tool === t.id ? '' : t.id">
            <component :is="t.icon" :size="18" :stroke-width="1.6" />
          </wa-button>
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

    <footer class="status">
      <span>{{ toolTitle }}</span>
      <span class="grow"></span>
      <span>Слой: {{ current?.title }}</span>
      <wa-dropdown placement="top-end" @wa-select="e => setBasemap(e.detail.item.value)">
        <button slot="trigger" class="basebtn" title="Подложка карты">Подложка: {{ BASEMAPS[basemapId] }}</button>
        <wa-dropdown-item v-for="(t, id) in BASEMAPS" :key="id" type="checkbox" :value="id" :checked="basemapId === id">{{ t }}</wa-dropdown-item>
      </wa-dropdown>
      <span>Масштаб 1:{{ scale.toLocaleString("ru-RU") }}</span>
      <span>{{ busy ? "Записываю…" : notice || (project.source === "autosave" ? "Восстановлена последняя работа" : "") }}</span>
    </footer>
  </div>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue";
import { DockviewVue, themeLight } from "dockview-vue";
import {
  Slash, Spline, Square, Circle, Type, Ruler, Move, Copy, RotateCw, Scissors, ArrowRightToLine,
  CopyPlus, Waypoints, Minus, Combine, SquareDashed, FileImage, Undo2, Redo2, CircleHelp,
} from "@lucide/vue";
import { exportDxf, exportGeojson } from "./exports.js";
import { terrTool } from "./data.js";
import { history, redo, undo } from "./edit.js";
import { deleteFeatures, sel, selectAll, setSel } from "./features.js";
import { BASEMAPS, basemapId, current, project, scale, setBasemap, theme, toggleTheme } from "./store.js";
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
  { id: "views", title: "Виды" },
  { id: "help", title: "Справка" },
];
const open = reactive(Object.fromEntries(PANELS.map(p => [p.id, false])));

const TOOLS = [
  { title: "Рисование", items: [
    { id: "line", title: "Отрезок", key: "L", icon: Slash },
    { id: "pline", title: "Полилиния", key: "PL", icon: Spline },
    { id: "rect", title: "Прямоугольник", key: "REC", icon: Square },
    { id: "circle", title: "Круг", key: "C", icon: Circle },
    { id: "text", title: "Текст", key: "T", icon: Type },
  ] },
  { title: "Правка", items: [
    { id: "move", title: "Переместить", key: "M", icon: Move },
    { id: "copy", title: "Копировать", key: "CO", icon: Copy },
    { id: "rotate", title: "Повернуть", key: "RO", icon: RotateCw },
    { id: "trim", title: "Обрезать", key: "TR", icon: Scissors },
    { id: "extend", title: "Удлинить", key: "EX", icon: ArrowRightToLine },
    { id: "offset", title: "Смещение", key: "O", icon: CopyPlus },
  ] },
  { title: "Геометрия", items: [
    { id: "buffer", title: "Буфер", icon: SquareDashed },
    { id: "subtract", title: "Вычесть", icon: Minus },
    { id: "union", title: "Объединить", icon: Combine },
    { id: "split", title: "Разрезать", icon: Waypoints },
  ] },
  { title: "Измерить и лист", items: [
    { id: "measure", title: "Измерить", icon: Ruler },
    { id: "sheet", title: "Рамка листа", icon: FileImage },
  ] },
];
const tool = ref("");
const toolTitle = computed(() => {
  const t = TOOLS.flatMap(g => g.items).find(i => i.id === tool.value);
  return t ? `Инструмент: ${t.title} (образец, команда не выполняется)` : "Выберите инструмент на ленте";
});

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
  api.addPanel({ id: "tep", component: "tep", title: "Показатели (ТЭП)", position: { referencePanel: "map", direction: "below" }, initialHeight: 190 });
  api.addPanel({ id: "table", component: "table", title: "Таблица атрибутов", position: { referencePanel: "tep", direction: "within" } });
  api.getPanel("layers")?.api.setActive();
  api.getPanel("props")?.api.setActive();
  api.getPanel("map")?.api.setActive();
  try { localStorage.setItem("grado-next-seen", JSON.stringify(Object.keys(NEW_WINDOWS))); } catch { /* частный режим браузера */ }
}

/* Раскладка из браузера сохранена до появления новых окон: перенесённое окно встаёт на своё место по умолчанию один раз,
   дальше пользователь закрывает и двигает его сам (список показанных — «grado-next-seen»). */
const NEW_WINDOWS = { object: ["props", "within"], table: ["tep", "within"], views: ["layers", "within"], data: ["layers", "within"] };
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
  api.addPanel({ id, component: id, title: p.title, floating: { x: 300, y: 80, width: 440, height: 280 } });
}

function showHelp() {
  const p = api?.getPanel("help");
  if (p) p.api.setActive(); else api?.addPanel({ id: "help", component: "help", title: "Справка", floating: { x: 360, y: 90, width: 520, height: 460 } });
  syncOpen();
}

function onExport(e) { const v = e.detail.item.value; if (v === "dxf") exportDxf(); else if (v === "geojson") exportGeojson(); }

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
  if (v === "open") { try { await listProjects(); } catch { /* список останется прежним */ } openDlg.value = true; }
  else if (v === "save") save();
  else if (v === "saveas") askName();
  else if (v === "new") guard("Начать новый проект?", newProject);
  else if (v === "file") fileInput.value.click();
  else if (v === "download") downloadProject();
}
function choose(name) { openDlg.value = false; guard(`Открыть «${name}»?`, () => openProject(name)); }
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
  if (e.code === "KeyS") { e.preventDefault(); if (!shared.value) save(); }
  else if (typing(e)) return;                       // в поле ввода Ctrl+Z правит текст поля
  else if (e.code === "KeyZ" && !e.shiftKey) { e.preventDefault(); if (!undo()) notice.value = "Отменять нечего"; }
  else if ((e.code === "KeyZ" && e.shiftKey) || e.code === "KeyY") { e.preventDefault(); redo(); }
});
watch(() => [project.name, dirty.value], () => { document.title = (project.name || "Без названия") + (dirty.value ? " •" : "") + " — ГРАДО 2"; });

openStartup();
</script>

<style>
.shell { display: grid; grid-template-rows: auto auto 1fr auto; height: 100%; }
.top {
  display: flex; align-items: center; gap: var(--wa-space-2xs);
  padding: 2px var(--wa-space-s); background: var(--g-bar); border-bottom: 1px solid var(--g-line); min-height: 34px;
}
.brand { font-weight: 700; letter-spacing: .02em; margin-right: var(--wa-space-s); }
.project { color: var(--g-muted); margin-right: var(--wa-space-m); display: inline-flex; gap: 6px; align-items: center; }
.grow { flex: 1; }
.menu-h { margin: 6px 12px 2px; font-size: var(--wa-font-size-2xs); color: var(--g-muted); font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
.ribbon {
  display: flex; gap: 0; padding: 2px var(--wa-space-xs) 0; background: var(--g-bar); border-bottom: 1px solid var(--g-line);
}
.tgroup { display: flex; flex-direction: column; align-items: center; padding: 0 var(--wa-space-s); border-right: 1px solid var(--g-line); }
.tgroup:last-child { border-right: 0; }
.tbtns { display: flex; }
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
</style>
