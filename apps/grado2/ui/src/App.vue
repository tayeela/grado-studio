<!-- ГРАДО 2 · каркас нового интерфейса: шапка с меню и кнопкой «Листы и альбом» (вкладка AlbumPanel.vue, движок — albumhost.js), лента инструментов, окна dockview, строка состояния;
     на общем сервере — вход, шапка и окна совместной работы (HubLogin, HubBar, HubWindows, окно «Комментарии»).
     Раскладку окон помнит браузер (localStorage «grado-next-layout»); панели — src/panels/*.vue. -->
<template>
  <div class="shell" :class="{ sheetmode }">
    <!-- переходы для клавиатуры и экранного диктора: видны только в фокусе, первый Tab на странице (#30) -->
    <nav class="skip" aria-label="Быстрый переход">
      <a v-for="s in SKIPS" :key="s[0]" href="#" @click.prevent="winApi.focus(s[0])">{{ s[1] }}</a>
    </nav>
    <header class="top">
      <span class="brand">ГРАДО 2</span>
      <!-- название открытой работы: щелчок — правка на месте (Enter — записать, Esc — отмена); сохранённый проект переименовывается в папке -->
      <input v-if="!shared && titleEdit" ref="titleInput" class="project ptitle-in" :value="project.name" maxlength="120" aria-label="Название проекта"
             placeholder="Название проекта" @keydown.enter.prevent="titleDone($event.target.value)" @keydown.esc.prevent="titleEdit = false" @blur="titleDone($event.target.value)">
      <button v-else-if="!shared" type="button" class="project ptitle" :class="{ none: !project.name }" :title="projTitle" @click="editTitle">
        {{ project.name || "Без названия" }}<span v-if="dirty || autoFail" class="dot" :class="{ fail: autoFail }" :aria-label="dotLabel"> •</span><Pencil class="pen" :size="13" /></button>

      <HubBar v-if="shared" />
      <wa-dropdown @wa-select="onProject">
        <wa-button slot="trigger" size="s" appearance="plain">Проект</wa-button>
        <template v-if="shared">
          <wa-dropdown-item value="hubprojects">Совместные проекты…</wa-dropdown-item>
          <wa-dropdown-item value="hubsave" :disabled="!hub.pid">Сохранить на сервере сейчас<span slot="details">Ctrl+S</span></wa-dropdown-item>
          <wa-dropdown-item value="hubshare" :disabled="!hub.pid">Доступ…</wa-dropdown-item>
          <wa-dropdown-item value="hubhistory" :disabled="!hub.pid">История версий…</wa-dropdown-item>
          <wa-divider></wa-divider>
          <wa-dropdown-item value="download">Скачать файл проекта</wa-dropdown-item>
        </template>
        <template v-else>
        <wa-dropdown-item value="open">Проекты…<span slot="details">Ctrl+O</span></wa-dropdown-item>
        <wa-dropdown-item value="save" :disabled="shared">Сохранить<span slot="details">Ctrl+S</span></wa-dropdown-item>
        <wa-dropdown-item value="saveas" :disabled="shared">Сохранить как…</wa-dropdown-item>
        <wa-dropdown-item value="rename">Переименовать…</wa-dropdown-item>
        <wa-dropdown-item value="new" :disabled="shared">Новый проект</wa-dropdown-item>
        <wa-divider></wa-divider>
        <wa-dropdown-item value="file">Открыть файл .grado2 с диска…</wa-dropdown-item>
        <wa-dropdown-item value="download">Скачать файл проекта</wa-dropdown-item>
        </template>
      </wa-dropdown>
      <input ref="fileInput" type="file" accept=".grado2,application/json" hidden @change="onFile">

      <wa-dropdown @wa-select="onWindow">
        <wa-button slot="trigger" size="s" appearance="plain">Окна</wa-button>
        <wa-dropdown-item v-for="p in PANELS.filter(x => x.id !== 'comments' || shared)" :key="p.id" type="checkbox" :value="p.id" :checked="open[p.id]">{{ p.title }}</wa-dropdown-item>
        <wa-divider></wa-divider>
        <wa-dropdown-item value="maponly">{{ mapOnly ? "Вернуть окна" : "Только карта" }}<span slot="details">Ctrl+\</span></wa-dropdown-item>
        <wa-dropdown-item value="reset">Раскладка по умолчанию</wa-dropdown-item>
        <!-- готовых раскладок под задачу и размера интерфейса в /next ещё нет (аудит 2.8) — они в прежней рабочей странице /old -->
        <wa-divider></wa-divider>
        <wa-dropdown-item value="oldpage">Готовые раскладки и размер — в рабочей странице →</wa-dropdown-item>
      </wa-dropdown>

      <wa-dropdown class="exportdd" @wa-select="onExport">
        <wa-button slot="trigger" size="s" appearance="plain" :disabled="busy">Выгрузка</wa-button>
        <template v-for="(sec, i) in EXPORTS" :key="sec.h">
          <wa-divider v-if="i"></wa-divider>
          <h4 class="menu-h">{{ sec.h }}</h4>
          <wa-dropdown-item v-for="it in sec.items" :key="it.v" :value.attr="it.v" :disabled="offOf(it)">{{ it.t }}<span slot="details">{{ detOf(it) }}</span></wa-dropdown-item>
        </template>
      </wa-dropdown>
      <wa-button size="s" appearance="plain" class="albumbtn" title="Листы и альбом (Ctrl+P): сборка альбома ППТ КРТ, штамп, листы, PDF и PPTX — вкладкой справа от карты"
                 @click="winApi.open('album')"><Printer slot="start" :size="16" />Листы и альбом<span v-if="album.sheets" class="cnt">{{ album.sheets }}</span></wa-button>
      <!-- узкий экран (панель владельца, 840 px, docs/ux/grado2-ux.md): «Выгрузка» и «Листы и альбом» собраны в «Ещё ▾» —
           те же команды, тот же обработчик; на широком экране меню скрыто, шапка как была -->
      <wa-dropdown class="more" @wa-select="onMore">
        <wa-button slot="trigger" size="s" appearance="plain" with-caret>Ещё</wa-button>
        <template v-for="(sec, i) in EXPORTS" :key="sec.h">
          <wa-divider v-if="i"></wa-divider>
          <h4 class="menu-h">{{ sec.h }}</h4>
          <wa-dropdown-item v-for="it in sec.items" :key="it.v" :value.attr="it.v" :disabled="offOf(it)">{{ it.t }}<span slot="details">{{ detOf(it) }}</span></wa-dropdown-item>
        </template>
        <wa-divider></wa-divider>
        <wa-dropdown-item value="album">Листы и альбом…<span slot="details">Ctrl+P</span></wa-dropdown-item>
      </wa-dropdown>

      <span class="grow"></span>
      <wa-button size="s" appearance="plain" :disabled="!history.undo" :aria-label="undoTip" :title.attr="undoTip" @click="undo"><Undo2 :size="16" /></wa-button>
      <wa-button size="s" appearance="plain" :disabled="!history.redo" :aria-label="redoTip" :title.attr="redoTip" @click="redo"><Redo2 :size="16" /></wa-button>
      <wa-button size="s" appearance="plain" aria-label="Справка" :title.attr="'Справка и клавиши (F1)'" @click="showHelp"><CircleHelp :size="16" /></wa-button>
      <wa-button size="s" appearance="plain" @click="toggleTheme" :aria-label="theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'" :title.attr="theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'">
        <Sun v-if="theme === 'dark'" :size="16" /><Moon v-else :size="16" />
      </wa-button>
    </header>

    <nav class="ribbon" aria-label="Команды черчения">
      <!-- «Выбор» — как в рабочей странице: прервать команду и вернуться к выбору объектов (то же, что Esc) -->
      <div class="tgroup">
        <div class="tbtns">
          <wa-button size="s" appearance="plain" :disabled="!cad.ready" :class="{ on: cad.ready && !cad.cmd }" aria-label="Выбор"
                     :title="cad.ready ? 'Выбор объектов: щелчок, Shift+щелчок, Shift+рамка. Esc — прервать команду и вернуться к выбору' : 'Откройте окно «Карта»: команды работают на ней'"
                     @click="cadApi.cancel()">
            <svg class="ci" aria-hidden="true"><use href="#ci-select" /></svg>
          </wa-button>
        </div>
        <div class="tlabel">Выбор</div>
      </div>
      <div v-for="g in TOOLS" :key="g.title" class="tgroup">
        <div class="tbtns">
          <wa-button v-for="id in g.items" :key="id" size="s" appearance="plain" :disabled="!cad.ready"
                     :class="{ on: cad.cmd === id }" :title="cmdTip(id)" :aria-label="cmdTitle(id)" @click="runCmd(id)">
            <svg class="ci" aria-hidden="true"><use :href="'#ci-' + id" /></svg>
          </wa-button>
          <wa-dropdown v-for="m in g.menus || []" :key="m.title" @wa-select="e => runCmd(e.detail.item.value)">
            <wa-button slot="trigger" size="s" appearance="plain" with-caret :disabled="!cad.ready" :aria-label="m.title" :title="m.title + ': ' + m.items.map(cmdTitle).join(', ').toLowerCase()">
              <template v-if="m.icon"><svg class="ci" aria-hidden="true"><use :href="'#ci-' + m.icon" /></svg></template><template v-else>Ещё</template>
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
      <!-- вид выделением (владелец 26.10.2026): выделил область на карте — вид готов, его ставят на лист -->
      <div class="tgroup">
        <div class="tbtns">
          <wa-button size="s" appearance="plain" :disabled="!cad.ready" :class="{ on: vframes.draw === NEW }" aria-label="Вид выделением" data-act="view-by-sel"
                     :title="cad.ready ? 'Вид выделением: тяните рамку на карте — выделенная область станет видом со слоями, как сейчас на карте. Вид ставят на лист' : 'Откройте окно «Карта»'"
                     @click="vframes.draw === NEW ? (vframes.draw = '') : newViewBySelection()"><SquareDashedMousePointer :size="18" :stroke-width="1.6" /></wa-button>
        </div>
        <div class="tlabel">Вид</div>
      </div>
      <!-- без окна «Карта» команды черчения недоступны: серые кнопки объясняются здесь же -->
      <div v-if="!cad.ready" class="nomap">Команды черчения работают на карте:
        <wa-button size="s" appearance="outlined" @click="winApi.open('map')">Открыть окно «Карта»</wa-button></div>
    </nav>

    <!-- плавающие окна двигаются за пустое место строки вкладок (без отдельной пустой полосы-шапки) и не уходят за край экрана -->
    <div class="dockwrap">
      <DockviewVue class="grado-dock dock" :theme="dockTheme" floating-group-drag-handle="titlebar" floating-group-bounds="boundedWithinViewport" @ready="onReady" />
      <!-- стартовый экран-состояние (project.js startup): проект не открылся — карточка поверх стола с причиной и действиями;
           исчезает, как только проект загружен (project.source), автосохранение при старте её не показывает -->
      <div v-if="showStartup" class="startup" role="status">
        <div class="card">
          <b>{{ startup.head }}</b>
          <p>{{ startup.text }}</p>
          <div class="acts">
            <wa-button v-if="startup.retry" size="s" appearance="outlined" :disabled="busy" @click="startup.retry()">Повторить</wa-button>
            <wa-button v-if="startup.shared" size="s" variant="brand" @click="openWin('projects')">Совместные проекты</wa-button>
            <wa-button v-else size="s" variant="brand" :disabled="busy" @click="newProject()">Новый проект</wa-button>
          </div>
        </div>
      </div>
    </div>

    <ProjectCatalog v-if="!shared" :open="openDlg" @close="openDlg = false" @open="choose" @file="fileInput.click()"
                    @new="openDlg = false; guard('Начать новый проект?', newProject)" />

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
      <CadModes class="mapbit" />
      <span class="cmdnow mapbit">{{ toolTitle }}</span>
      <span class="grow"></span>
      <span class="lay mapbit" :title="current?.title">Слой: {{ current?.title }}</span>
      <wa-dropdown class="mapbit" placement="top-end" @wa-select="e => setBasemap(e.detail.item.value)">
        <button slot="trigger" class="basebtn" title="Подложка карты">Подложка: {{ BASEMAPS[basemapId] }}</button>
        <wa-dropdown-item v-for="(t, id) in BASEMAPS" :key="id" type="checkbox" :value="id" :checked="basemapId === id">{{ t }}</wa-dropdown-item>
      </wa-dropdown>
      <span class="xy mapbit" title="Курсор над картой, МСК (как в QGIS)">{{ cursor ? `X ${fmtM(cursor[0])}  Y ${fmtM(cursor[1])}` : "X —  Y —" }}</span>
      <!-- масштаб, как в QGIS: «1 :» и число — вводится («2000» и Enter), стрелка — список стандартных (владелец 09.10.2026: поле было пустым и широким) -->
      <span class="scl mapbit" title="Масштаб карты: введите знаменатель, например 2000, и нажмите Enter, или выберите из списка">
        <span class="lbl">Масштаб</span>
        <span class="sbox" :class="{ off: !scale || !cad.ready }">
          <span class="pre">1&#8239;:</span>
          <input class="sclin" :value="scaleText" :disabled="!scale || !cad.ready" aria-label="Знаменатель масштаба" inputmode="numeric"
                 @focus="sclFresh = true" @mouseup="e => { if (sclFresh) e.target.select(); sclFresh = false; }"
                 @keydown.enter.prevent="setScale" @keydown.esc="e => { e.target.value = scaleText; e.target.blur(); }" @blur="e => e.target.value = scaleText">
          <wa-dropdown placement="top-end" @wa-select="e => setScaleTo(+e.detail.item.value)">
            <button slot="trigger" class="sdd" type="button" :disabled="!scale || !cad.ready" aria-label="Стандартные масштабы"><ChevronDown :size="12" /></button>
            <wa-dropdown-item v-for="d in SCALES" :key="d" :value="String(d)" :class="{ cur: Math.round(scale) === d }">1 : {{ d.toLocaleString("ru-RU") }}</wa-dropdown-item>
          </wa-dropdown>
        </span>
      </span>
    </footer>

    <!-- сообщения — тостами вместо серой строки: ошибка стоит с «Повторить», успех и действие уходят сами (toasts.js) -->
    <Toasts />
  </div>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue";
import { DockviewVue, themeLight } from "dockview-vue";
import { ChevronDown, Undo2, Redo2, CircleHelp, Pencil, Printer, SquareDashedMousePointer, Sun, Moon } from "@lucide/vue";
import ProjectCatalog from "./panels/ProjectCatalog.vue";
import CadModes from "./panels/CadModes.vue";
import Toasts from "./panels/Toasts.vue";
import HubBar from "./panels/HubBar.vue";
import HubLogin from "./panels/HubLogin.vue";
import HubWindows from "./panels/HubWindows.vue";
import { toast } from "./toasts.js";
import { flush as hubFlush, hub, openWin } from "./hub.js";
import { RIBBON, cad, cadApi, cadIcons } from "./cad.js";
import { exportDxf, exportGeojson, exportShp, exportXlsx } from "./exports.js";
import { album, albumFile, albumHooks, ogdDxf } from "./albumhost.js";
import { ogdResume, terrTool } from "./data.js";
import { NEW, newViewBySelection, vframes } from "./viewframesmap.js";
import { printAll } from "./panels/sheetmaps.js";
import { plural } from "./geom.js";
import { history, mapApi, redo, undo } from "./edit.js";
import { deleteFeatures, sel, selectAll, setSel } from "./features.js";
import { BASEMAPS, basemapId, current, cursor, mapOnly, project, scale, setBasemap, theme, toggleTheme, winApi } from "./store.js";
import {
  autoFail, busy, clashOf, dirty, downloadProject, listProjects, newProject, notice, openFile, openProject, openStartup, projDir, projects, retitle, saveProject, say, shared, startup,
} from "./project.js";

const dockTheme = { ...themeLight, className: "dockview-theme-grado", gap: 8 };   // окна — карточки на сером столе с зазором 8 px («Синька»)
const fmtM = v => v.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

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
  { id: "album", title: "Листы и альбом" },
  { id: "albumlay", title: "Макет надписей" },
];
const sheetmode = ref(false);
const open = reactive(Object.fromEntries(PANELS.map(p => [p.id, false])));

/* Лента — команды черчения как в рабочей странице (cad.js RIBBON): кнопка запускает команду, повторный щелчок прерывает. */
const TOOLS = [
  { title: "Рисование", items: RIBBON.draw, menus: [{ title: "Оформление", icon: "hatch", items: RIBBON.anno }] },
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
// идущая команда, её подсказка и сообщения — в командной строке над картой; здесь не повторяются (аудит 09.10.2026)
const toolTitle = computed(() => cad.ready ? "" : "Черчение работает в окне «Карта»");

/* подпись отмены в шапке: что именно отменит Ctrl+Z (edit.js history.label) — как в ленте «Макета листа» (Ribbon.vue) */
const undoTip = computed(() => history.label ? `Отменить: ${history.label} (Ctrl+Z)` : "Отменить (Ctrl+Z)");
const redoTip = computed(() => history.rlabel ? `Вернуть: ${history.rlabel} (Ctrl+Shift+Z)` : "Вернуть (Ctrl+Shift+Z)");
/* стартовый экран (project.js startup): карточка поверх стола, пока проект не открыт, — причина и действия */
const showStartup = computed(() => startup.value && !project.source);

/* Масштаб в строке состояния вводится: «1:2000», «2000», «1 : 2 000» и Enter (как в QGIS); карта меняет разрешение
   в той же пропорции — пересчёт масштаба с поправкой на широту остаётся в MapPanel (scaleDen). */
const SCALES = [500, 1000, 2000, 5000, 10000, 25000, 50000];
const scaleText = computed(() => scale.value ? Math.round(scale.value).toLocaleString("ru-RU") : "");
let sclFresh = false;   // первый щелчок в поле выделяет весь масштаб — набранное число заменит его
function setScale(e) {
  const el = e.target, t = el.value.replace(/\s|\u00a0/g, "").replace(",", ".");
  const d = Number(t.includes(":") ? t.split(":").pop() : t);
  const v = mapApi.view;
  if (!v || !scale.value || !(d >= 50 && d <= 5e6)) { el.value = scaleText.value; if (t) notice.value = "Масштаб — число, например 1:2000 или 2000"; return; }
  setScaleTo(d);
  el.blur();
}
function setScaleTo(d) { const v = mapApi.view; if (v && scale.value && d) v.setResolution(v.getResolution() * d / scale.value); }

/* «Восстановлена последняя работа» — коротким тостом после открытия, как тост рабочей страницы (web/app.js) */
watch(() => project.raw, () => { if (project.source === "autosave") toast("Восстановлена последняя работа", { timeout: 2500 }); });

const LAYOUT_KEY = "grado-next-layout";
let api = null;

/* Ширины по умолчанию от ширины экрана: на 1280 карта остаётся главной, на широком экране боковые окна просторнее,
   чтобы имена слоёв и вкладки «Свойства, Объект, Ограничения, Эскиз» не обрезались. Нижняя группа — две пятых высоты: «Схеме расчёта» и таблице есть где развернуться. */
const clamp = (v, a, b) => Math.round(Math.min(b, Math.max(a, v)));
const sizes = () => ({ left: clamp(innerWidth * .22, 270, 330), right: clamp(innerWidth * .26, 336, 390), bottom: clamp((innerHeight - 140) * .3, 180, 340) });   // низ — около трети высоты под картой: на 1280×720 карта не мельчает (UX-аудит 12.10 п. 17)

function defaultLayout() {
  api.clear();
  const z = sizes();
  api.addPanel({ id: "map", component: "map", title: "Карта" });
  api.addPanel({ id: "layers", component: "layers", title: "Слои", position: { referencePanel: "map", direction: "left" }, initialWidth: z.left });
  api.addPanel({ id: "props", component: "props", title: "Свойства", position: { referencePanel: "map", direction: "right" }, initialWidth: z.right });
  api.addPanel({ id: "object", component: "object", title: "Объект", position: { referencePanel: "props", direction: "within" } });
  api.addPanel({ id: "data", component: "data", title: "Данные", position: { referencePanel: "layers", direction: "within" } });
  api.addPanel({ id: "views", component: "views", title: "Виды", position: { referencePanel: "layers", direction: "within" } });
  api.addPanel({ id: "cons", component: "cons", title: "Ограничения", position: { referencePanel: "props", direction: "within" } });
  api.addPanel({ id: "tep", component: "tep", title: "Показатели (ТЭП)", position: { referencePanel: "map", direction: "below" }, initialHeight: z.bottom });
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
    api.addPanel({ id, component: id, title, ...(api.getPanel(ref) ? { position: { referencePanel: ref, direction } } : { floating: fit(300, 80, 440, 280) }), inactive: true });
  }
  try { localStorage.setItem("grado-next-seen", JSON.stringify(Object.keys(NEW_WINDOWS))); } catch { /* частный режим браузера */ }
}

/* Место окна в раскладке по умолчанию: окно, открытое заново из меню «Окна», встаёт вкладкой к соседям по своей группе,
   если хоть один из них открыт и не плавает; иначе — краем к карте; иначе — плавающим. */
const LEFT = ["layers", "data", "views"], RIGHT = ["props", "object", "cons", "sketch", "album"], BOTTOM = ["tep", "table", "graph", "vars"];
function homeOf(id) {
  const docked = x => { const q = api.getPanel(x); return q && q.group?.api.location?.type === "grid" ? q : null; };
  const z = sizes();
  for (const [ids, dir, size] of [[LEFT, "left", { initialWidth: z.left }], [RIGHT, "right", { initialWidth: z.right }], [BOTTOM, "below", { initialHeight: z.bottom }]]) {
    if (!ids.includes(id)) continue;
    const mate = ids.find(x => x !== id && docked(x));
    if (mate) return { position: { referencePanel: mate, direction: "within" } };
    if (docked("map")) return { position: { referencePanel: "map", direction: dir }, ...size };
  }
  if (id === "map") {
    const near = ["tep", "table", "graph", "vars", "layers", "props"].find(docked);   // над нижней группой, иначе между боковыми
    if (near) return { position: { referencePanel: near, direction: { layers: "right", props: "left" }[near] || "above" } };
  }
  return null;
}

const SHEET_MIN = 560, MAP_MIN = 360;   // макет листа и карта рядом — не уже этого
const DOCK_NEAR = { norms: ["props", "object", "sketch"], vol: ["props", "object", "sketch"], comments: ["props", "object"], cmp: ["tep", "table", "vars"] };
function dockOf(id) {
  return (DOCK_NEAR[id] || []).find(x => api.getPanel(x)?.group?.api.location?.type === "grid") || null;
}
function addOne(id) {
  const p = PANELS.find(x => x.id === id);
  const home = homeOf(id);
  if (home) { api.addPanel({ id, component: id, title: p.title, ...home }); return; }
  // макет листа (аудит UX 12.10.2026, находки 1–3): окно «Листы и альбом» со списком листов и «Виды» остаются видны,
  // как страницы в Figma и менеджер макетов QGIS. Хватает места — встаёт рядом с картой, иначе вкладкой над картой
  // (карта — соседняя вкладка); во всё окно — двойной щелчок по вкладке. Второй макет — вкладкой к первому.
  // Окно не уже SHEET_MIN: лист не сжимается в полоску
  if (id === "sheet" || id === "albumlay") {
    const mate = ["sheet", "albumlay"].map(x => api.getPanel(x)).find(Boolean);
    const map = api.getPanel("map"), mw = map?.group?.api.width || 0;
    const ref = mate ? { referencePanel: mate.id, direction: "within" }
      : map && mw >= SHEET_MIN + MAP_MIN ? { referencePanel: "map", direction: "right" }
      : map ? { referencePanel: "map", direction: "within" } : null;
    api.addPanel({ id, component: id, title: p.title, minimumWidth: SHEET_MIN, ...(ref ? { position: ref } : {}),
      ...(ref?.direction === "right" ? { initialWidth: Math.max(SHEET_MIN, Math.round(mw * 0.6)) } : {}) });
    return;
  }
  // окна из меню «Окна» — вкладкой к боковой или нижней группе, не плавающей стопкой поверх карты (аудит UX, находка 7);
  // плавающим окно делает пользователь, вытащив вкладку
  const dock = dockOf(id);
  if (dock) { api.addPanel({ id, component: id, title: p.title, position: { referencePanel: dock, direction: "within" } }); return; }
  const [w, h] = { norms: [560, 600], sketch: [440, 600], comments: [380, 560], vars: [900, 420], cmp: [1000, 520], vol: [620, 460] }[id] || [440, 280];   // длинные и широкие окна — крупнее
  const k = api.groups.filter(g => g.api.location?.type === "floating").length % 6;   // плавающие окна — лесенкой, не одно на другом:
  api.addPanel({ id, component: id, title: p.title, floating: fit(300 + k * 32, 80 + k * 46, w, h) });         // шаг 46 px — вкладки нижнего окна видны
}

/* Плавающее окно вписывается в область окон: на узком экране — уже и ниже, левее, но целиком видно. */
function fit(x, y, w, h) {
  const W = api.width || innerWidth, H = api.height || innerHeight;
  w = Math.min(w, W - 32); h = Math.min(h, H - 32);
  return { x: Math.max(16, Math.min(x, W - w - 16)), y: Math.max(16, Math.min(y, H - h - 16)), width: w, height: h };
}

function showHelp() {
  const p = api?.getPanel("help");
  if (p) p.api.setActive(); else api?.addPanel({ id: "help", component: "help", title: "Справка", floating: fit(360, 90, 520, 460) });   // справка — плавающей подсказкой поверх карты
  syncOpen();
}

function onExport(e) {
  const v = e.detail.item.value;
  if (v === "dxf") exportDxf(); else if (v === "geojson") exportGeojson(); else if (v === "shp") exportShp(); else if (v === "xlsx") exportXlsx();
  else if (v === "pdf" || v === "pptx") albumFile(v); else if (v === "ogd") ogdDxf();
  else if (v === "sheets") printSheets();
}

/* Меню «Выгрузка» и его узкоэкранная копия в «Ещё ▾» — один список, чтобы команды не разъезжались.
   off и d могут быть функциями: отключение и подпись листов зависят от проекта и альбома. */
const EXPORTS = [
  { h: "Данные", items: [
    { v: "dxf", t: "Чертёж DXF — слои проекта, МСК", d: "МГГТ" },
    { v: "geojson", t: "GeoJSON для QGIS", d: "МСК" },
    { v: "shp", t: "SHP как в ГИС ОГД", d: "МСК" },
    { v: "xlsx", t: "Excel: показатели ТЭП и листы", d: "XLSX" }] },
  { h: "Листы", items: [
    { v: "sheets", t: "Все листы в PDF", d: () => project.layouts?.length ? plural(project.layouts.length, ["лист", "листа", "листов"]) : "нет листов", off: () => !project.layouts?.length },
    { v: "ogd", t: "Слои порталов в DXF — по области", d: "МСК" }] },
  { h: "Альбом ППТ КРТ — во вкладке «Листы и альбом»", items: [
    { v: "pdf", t: "PDF альбома", d: () => album.sheets ? "все листы" : "альбом не собран", off: () => !album.sheets },
    { v: "pptx", t: "PPTX альбома", d: "PowerPoint", off: () => !album.sheets }] },
];
const detOf = it => typeof it.d === "function" ? it.d() : it.d;
const offOf = it => typeof it.off === "function" ? it.off() : false;
/* «Ещё ▾» (узкий экран): те же выгрузки и вкладка альбома */
function onMore(e) { e.detail.item.value === "album" ? winApi.open("album") : onExport(e); }

/* Все листы в PDF: не собрался — тост-ошибка с «Повторить» (сборка повторяема) */
function printSheets() {
  const layouts = JSON.parse(JSON.stringify(project.layouts)), meta = project.raw?.album?.meta || {}, name = project.name || "листы";
  printAll(layouts, meta, name).catch(e => say("PDF не собран: " + e.message, { level: "error", retry: printSheets }));
}

winApi.open = id => { const p = api?.getPanel(id); if (p) p.api.setActive(); else if (api) addOne(id); syncOpen(); };
function syncOpen() { for (const p of PANELS) open[p.id] = !!api.getPanel(p.id); }

/* «Только карта» (#26, аудит 07.10.2026: на ноутбуке карта теряется за окнами): группа карты разворачивается во всё рабочее
   поле, как «Скрыть панели» в QGIS (Ctrl+Tab) и «Show/Hide UI» в Figma (Ctrl+\). Повтор, Ctrl+\ или Esc без выбора — окна на месте. */
winApi.mapOnly = on => {
  const g = api?.getPanel("map")?.group; if (!g) return;
  on ??= !g.api.isMaximized();
  if (on && !g.api.isMaximized()) g.api.maximize(); else if (!on && api.hasMaximizedGroup()) api.exitMaximizedGroup();
};

/* Переход клавиатурой в окно (#30): окно выводится вперёд, фокус — в его главную часть: карта (стрелки двигают, +/− масштаб),
   текущий слой в «Слоях», строки «Таблицы атрибутов». */
const SKIPS = [["map", "К карте"], ["layers", "К слоям"], ["table", "К таблице объектов"]];
const FOCUS = { map: ".mapbox .map", layers: ".pane.layers .row[tabindex='0']", table: ".pane.tbl .tabulator-tableholder" };
winApi.focus = id => {
  if (mapOnly.value && id !== "map") winApi.mapOnly(false);
  winApi.open(id);
  requestAnimationFrame(() => document.querySelector(FOCUS[id])?.focus());
};

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
  // «только карта» не запоминается: раскладка пишется без развёрнутой карты, после выхода из режима — заново
  const keep = () => { if (api.hasMaximizedGroup()) return; try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(api.toJSON())); } catch { /* частный режим браузера */ } };
  api.onDidMaximizedGroupChange(() => { mapOnly.value = !!api.getPanel("map")?.group?.api.isMaximized(); keep(); });
  api.onDidLayoutChange(() => { syncOpen(); keep(); });
  // активен лист — лента и строка карты прячутся: у листа своя лента и своя строка состояния (аудит UX, находка 2)
  api.onDidActivePanelChange(e => { sheetmode.value = ["sheet", "albumlay"].includes(e?.panel?.id); });
}

function onWindow(e) {
  const v = e.detail.item.value;
  if (v === "reset") { winApi.mapOnly(false); defaultLayout(); return; }
  if (v === "maponly") { winApi.mapOnly(); return; }
  if (v === "oldpage") { window.open("/old"); return; }   // прежняя рабочая страница — обычный URL, там же файл проекта
  const panel = api.getPanel(v);
  if (panel) panel.api.close(); else addOne(v);
  syncOpen();
}

/* Проект: открыть, сохранить, сохранить как, новый, файл с диска и на диск (project.js). */
const openDlg = ref(false), saveDlg = ref(false), saveName = ref(""), clash = ref(null), ask = ref(null);
const fileInput = ref(null), nameInput = ref(null);
const projTitle = computed(() => (project.file ? `Проект «${project.file}» в папке проектов` : "Проект ещё не сохранён под именем")
  + (dirty.value ? " · есть несохранённые изменения (автосохранение держит их до сохранения)" : "")
  + (autoFail.value ? " · автосохранение не прошло: нет связи с сервером, правки сохранятся, когда связь вернётся" : "") + ". Щёлкните, чтобы изменить название");
/* точка у названия: серая — есть правки, красная — последняя попытка автосохранения не прошла (project.js autoFail) */
const dotLabel = computed(() => autoFail.value ? "автосохранение не прошло: нет связи с сервером" + (dirty.value ? ", есть несохранённые изменения" : "") : "есть несохранённые изменения");
const titleEdit = ref(false), titleInput = ref(null);
async function editTitle() { titleEdit.value = true; await nextTick(); titleInput.value?.focus(); titleInput.value?.select(); }
async function titleDone(v) {
  if (!titleEdit.value) return;
  titleEdit.value = false;
  if (!(await retitle(v))) await editTitle();          // занято или недопустимо: причина — карточкой внизу справа, поле остаётся открытым
}

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
  if (await saveProject(name, { replace: !!clash.value })) { saveDlg.value = false; const p = pending; pending = null; p?.(); }
}
async function save() { if (project.file && project.name === project.file) await saveProject(); else await askName(); }

async function onProject(e) {
  const v = e.detail.item.value;
  if (v === "hubprojects") openWin("projects");
  else if (v === "hubsave") hubFlush();
  else if (v === "hubshare") openWin("share");
  else if (v === "hubhistory") openWin("history");
  else if (v === "open") openCatalog();
  else if (v === "rename") editTitle();
  else if (v === "save") save();
  else if (v === "saveas") askName();
  else if (v === "new") guard("Начать новый проект?", newProject);
  else if (v === "file") fileInput.value.click();
  else if (v === "download") downloadProject();
}
async function openCatalog() { try { await listProjects(); } catch { /* список останется прежним */ } openDlg.value = true; }
function choose(name) { openDlg.value = false; if (name !== project.file || dirty.value) guard(`Открыть «${name}»?`, () => openProject(name)); }
albumHooks.save = () => shared.value ? hubFlush() : save();     // Ctrl+S в окне «Листы и альбом»
albumHooks.open = choose;
albumHooks.panel = () => winApi.open("album");       // меню «Выгрузка» → PDF или PPTX альбома
albumHooks.data = () => winApi.open("data");         // меню «Выгрузка» → «ГИС ОГД в DXF»: выбор слоёв портала в окне «Данные»
ogdResume();                                          // выгрузка ГИС ОГД в DXF шла до перезагрузки — показать её ход и забрать файл
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
    else if (e.key === "Escape" && mapOnly.value) winApi.mapOnly(false);
    return;
  }
  if (e.code === "Backslash" && !e.shiftKey && !e.altKey) { e.preventDefault(); winApi.mapOnly(); return; }
  if (e.code === "KeyA" && !typing(e) && current.value) {
    e.preventDefault(); selectAll(current.value.key); notice.value = `Выбраны все объекты слоя «${current.value.title}»: ${sel.length}`; return;
  }
  if (e.code === "KeyS") { e.preventDefault(); if (shared.value) hubFlush(); else save(); }
  else if (e.code === "KeyO" && !e.shiftKey && !e.altKey) { e.preventDefault(); if (shared.value) openWin("projects"); else openCatalog(); }
  else if (e.code === "KeyP" && !e.shiftKey && !e.altKey) { e.preventDefault(); winApi.open("album"); }   // как в рабочей странице: листы вместо печати страницы
  else if (typing(e)) return;                       // в поле ввода Ctrl+Z правит текст поля
  else if (e.code === "KeyZ" && !e.shiftKey) { e.preventDefault(); if (!undo()) notice.value = history.dropped ? "Отменять нечего: чужая правка сбросила историю" : "Отменять нечего"; }
  else if ((e.code === "KeyZ" && e.shiftKey) || e.code === "KeyY") { e.preventDefault(); redo(); }
});
watch(() => [project.name, dirty.value], () => { document.title = (project.name || "Без названия") + (dirty.value ? " •" : "") + " — ГРАДО 2"; });

openStartup();
</script>

<style>
.shell { display: grid; grid-template-rows: auto auto 1fr auto; grid-template-columns: minmax(0, 1fr); height: 100%; }
/* переходы клавиатуры (#30): вне потока сетки, появляются поверх шапки только в фокусе */
.skip { position: fixed; left: 8px; top: 4px; z-index: 1000; display: flex; gap: 8px; }
.skip a { position: absolute; left: -9999px; padding: 4px 12px; border-radius: 6px; background: var(--wa-color-brand-fill-loud); color: var(--wa-color-brand-on-loud);
  font-size: var(--wa-font-size-s); text-decoration: none; white-space: nowrap; }
.skip a:focus { position: static; outline: 2px solid var(--wa-color-focus); outline-offset: 2px; }
.top {
  display: flex; align-items: center; flex-wrap: wrap; gap: var(--wa-space-2xs);
  padding: 2px var(--wa-space-s); background: var(--g-bar); border-bottom: 1px solid var(--g-line); min-height: 34px; min-width: 0;
}
.top .cnt { margin-left: 6px; padding: 0 6px; border-radius: 8px; font-size: var(--wa-font-size-2xs); line-height: 16px; background: var(--wa-color-neutral-fill-normal); }
.brand { font-weight: 700; letter-spacing: .02em; margin-right: 12px; }
.project { color: var(--g-muted); margin-right: 16px; display: inline-flex; gap: 6px; align-items: center; }
/* название проекта в шапке: выглядит текстом, при наведении — поле с карандашом; щелчок открывает правку на месте */
.ptitle { font: inherit; font-size: var(--wa-font-size-m); color: var(--wa-color-text-normal); background: none; border: 1px solid transparent; border-radius: 6px;
  padding: 2px 6px; margin-left: -6px; gap: 4px; max-width: 360px; cursor: text; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ptitle.none { color: var(--g-muted); }
.ptitle .dot { color: var(--g-muted); }
/* автосохранение не прошло: точка у названия красная (цвет ошибок, как значки ошибок в окне «Данные») */
.ptitle .dot.fail { color: var(--wa-color-danger-on-quiet); }
.ptitle .pen { flex: none; color: var(--g-muted); opacity: 0; transition: opacity .12s; }
.ptitle:hover, .ptitle:focus-visible { border-color: var(--g-line); background: var(--wa-color-surface-default); outline: none; }
.ptitle:hover .pen, .ptitle:focus-visible .pen { opacity: 1; }
.ptitle-in { font: inherit; font-size: var(--wa-font-size-m); width: 300px; padding: 2px 6px; margin-left: -6px; border: 1px solid var(--wa-color-focus); border-radius: 6px;
  background: var(--wa-color-surface-default); color: var(--wa-color-text-normal); outline: 2px solid color-mix(in srgb, var(--wa-color-focus) 25%, transparent); }
/* строка меню как в QGIS и macOS: пункты без стрелок, ровный шаг, одна высота и одна линия текста (владелец 09.10.2026, снимок) */
.top > wa-dropdown > wa-button::part(base), .top > wa-button::part(base) { padding-inline: 8px; height: 28px; font-size: var(--wa-font-size-m); }   /* тот же кегль, что у названия: одна линия текста */
.top > wa-dropdown, .top > wa-button { display: inline-flex; align-items: center; }
/* узкий экран (панель владельца, 840 px, docs/ux/grado2-ux.md): «Выгрузка» и «Листы и альбом» — в «Ещё ▾», шапка остаётся одним рядом;
   на широком экране «Ещё» скрыт. flex-wrap выше — страховка: даже если что-то не влезло, это переносится, а не режется */
.top > .more { display: none; }
@media (max-width: 899px) {
  .top > .more { display: inline-flex; }
  .top > .exportdd, .top > .albumbtn { display: none; }
}
.grow { flex: 1; }
.menu-h { margin: 6px 12px 2px; font-size: var(--wa-font-size-2xs); color: var(--g-muted); font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
.ribbon {
  display: flex; flex-wrap: wrap; gap: 4px 0; padding: 2px var(--wa-space-xs) 0; background: var(--g-bar); border-bottom: 1px solid var(--g-line);
}
.tgroup { display: flex; flex-direction: column; align-items: center; padding: 0 var(--wa-space-s); border-right: 1px solid var(--g-line); }
.tgroup:last-child { border-right: 0; }
.tbtns { display: flex; align-items: center; }
.ribbon .ci { width: 18px; height: 18px; display: block; }
.shell.sheetmode .ribbon, .shell.sheetmode .mapbit { display: none !important; }   /* активен лист: своя лента и строка у листа */
.shell.sheetmode { grid-template-rows: auto 1fr auto; }   /* без ленты — на одну строку сетки меньше */
wa-dropdown-item .ci { width: 16px; height: 16px; }
.status > .xy { white-space: pre; min-width: 22ch; font-variant-numeric: tabular-nums; }
.status > .cmdnow { flex: 0 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.tbtns wa-button::part(base) { padding-inline: 6px; }
.tbtns wa-button.on::part(base) { background: var(--wa-color-brand-fill-quiet); color: var(--wa-color-brand-on-quiet); }
.tlabel { font-size: var(--wa-font-size-2xs); color: var(--g-muted); padding-bottom: 2px; }
.dockwrap { position: relative; display: grid; min-height: 0; }
.dockwrap > .dock { min-height: 0; }
/* стартовый экран-состояние (аудит, п. 2.2): пока проекта нет — карточка по центру поверх стола, в стиле .empty панелей */
.startup { position: absolute; inset: 0; z-index: 20; display: grid; place-items: center; background: var(--g-desk); }
.startup .card { display: flex; flex-direction: column; align-items: center; gap: 8px; max-width: 480px; margin: 0 16px; padding: 24px 28px;
  text-align: center; background: var(--wa-color-surface-default); border: 1px solid var(--g-line); border-radius: 12px; box-shadow: 0 6px 24px rgba(11, 31, 51, .14); }
.startup .card b { font-size: var(--wa-font-size-m); }
.startup .card p { margin: 0; color: var(--g-muted); font-size: var(--wa-font-size-s); line-height: 1.45; }
.startup .acts { display: flex; gap: 8px; justify-content: center; margin-top: 4px; }
.save-dlg .warn { color: var(--wa-color-danger-on-quiet); font-size: var(--wa-font-size-s); }
.status wa-dropdown { display: inline-flex; }
.status .basebtn { font: inherit; font-size: var(--wa-font-size-xs); line-height: 20px; color: inherit; background: none; border: 0; padding: 0 2px; cursor: pointer; }
.status .basebtn:hover { color: var(--wa-color-text-normal); text-decoration: underline; }
.status {
  display: flex; gap: var(--wa-space-l); align-items: center; padding: 0 var(--wa-space-s);
  height: 26px; font-size: var(--wa-font-size-xs); color: var(--g-muted); background: var(--g-bar); border-top: 1px solid var(--g-line);
}
.status > * { flex: none; white-space: nowrap; }
.status > .grow { flex: 1; }
/* узкий экран (1024 px): строка не шире окна — слой сжимается многоточием, подписи «Масштаб» и «Подложка:» и сам слой уходят (UX-аудит 12.10 п. 12) */
.status > .lay { flex: 0 1 auto; min-width: 0; max-width: 24ch; overflow: hidden; text-overflow: ellipsis; }
@media (max-width: 1180px) {
  .status { gap: var(--wa-space-s); }
  .status > .lay, .status .scl .lbl { display: none; }
}
.status > .scl { display: inline-flex; align-items: center; gap: 6px; }
.status > .scl { margin-right: 2px; }
.status wa-dropdown-item.cur { font-weight: 600; color: var(--wa-color-brand-on-quiet); }
/* поле масштаба: «1 :» + число по ширине цифр + стрелка списка — одна рамка 20 px, как поле масштаба QGIS */
.status .sbox { display: inline-flex; align-items: center; height: 22px; box-sizing: border-box; border: 1px solid var(--g-line); border-radius: 5px;
  background: var(--wa-color-surface-default); color: var(--wa-color-text-normal); }
.status .sbox:focus-within { border-color: var(--wa-color-focus); }
.status .sbox.off { opacity: .55; }
.status .sbox .pre { padding-left: 6px; color: var(--g-muted); font-variant-numeric: tabular-nums; }
.status .sclin { width: 7.5ch; height: 20px; box-sizing: border-box; padding: 0 2px 0 3px; border: 0; background: transparent; font: inherit; font-size: var(--wa-font-size-xs);
  color: inherit; font-variant-numeric: tabular-nums; text-align: left; }
.status .sclin:focus { outline: none; }
.status .sdd { display: inline-grid; place-items: center; width: 20px; height: 20px; padding: 0; border: 0; border-left: 1px solid var(--g-line); background: none;
  color: var(--g-muted); cursor: pointer; border-radius: 0 4px 4px 0; }
.status .sdd:hover:not(:disabled) { background: var(--wa-color-neutral-fill-quiet); color: var(--wa-color-text-normal); }
/* лента без карты: пояснение вместо безмолвно серых кнопок */
.ribbon .nomap { display: flex; white-space: nowrap; align-items: center; gap: 8px; padding: 0 var(--wa-space-m); color: var(--g-muted); font-size: var(--wa-font-size-xs); }
</style>
