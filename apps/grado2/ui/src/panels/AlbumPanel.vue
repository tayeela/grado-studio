<!-- ГРАДО 2 · вкладка «Листы и альбом» нового интерфейса (шаг 2 плана, #94): альбом ППТ КРТ без отдельного окна браузера.
     Сверху строка альбома и действия («Собрать», PDF, PPTX), ход сборки и выгрузки («PDF: лист 3 из 9 · 12 с», «Остановить»),
     вопросы «заменить или добавить» и «не всё готово»; ниже штамп, список листов и свойства выбранного листа с просмотром.
     Сборку и печать делает прежний движок альбома, скрытый в странице (albumhost.js call, web/albumapi.js), поэтому PDF и
     PPTX выходят лист в лист прежние. Простые правки (название, формат, масштаб, легенда, ТЭП, порядок, удаление, штамп)
     пишутся прямо в раздел album проекта. Пока вкладка на виду, рамки листов видны на карте (albumframes.js): щелчок выбирает
     лист здесь, рамку тянут и меняют угол там же. «Слои листа» — роли выбранного листа с глазом (sheetlayers.js rows).
     «Подробно» — прежнее окно: перетаскивание в «Слоях и листах», макет надписей. -->
<template>
  <div class="pane alb">
    <div class="ahead">
      <p class="stat" :title="st?.stat">{{ head }}</p>
      <div class="acts">
        <wa-dropdown @wa-select="e => add(e.detail.item.value)">
          <wa-button slot="trigger" size="s" appearance="outlined" with-caret :disabled="busy || viewer"><FilePlus2 :size="14" /> Добавить лист</wa-button>
          <wa-dropdown-item value="A3">Лист A3 (ГОСТ)<span slot="details">рамка и штамп</span></wa-dropdown-item>
          <wa-dropdown-item value="A1">Лист A1 (ГОСТ)<span slot="details">большой лист</span></wa-dropdown-item>
          <wa-dropdown-item value="P">Слайд 16:9<span slot="details">презентация</span></wa-dropdown-item>
        </wa-dropdown>
        <wa-dropdown @wa-select="e => build(e.detail.item.value)">
          <wa-button slot="trigger" size="s" appearance="outlined" with-caret :disabled="busy || viewer"><LayoutTemplate :size="14" /> Собрать</wa-button>
          <wa-dropdown-item value="pptkrt">Альбом ППТ КРТ<span slot="details">А3, красная шапка</span></wa-dropdown-item>
          <wa-dropdown-item value="sit">Ситуационный план A4<span slot="details">один лист</span></wa-dropdown-item>
          <wa-dropdown-item value="sec1">Раздел 1: существующее положение<span slot="details">слайды</span></wa-dropdown-item>
          <wa-divider></wa-divider>
          <wa-dropdown-item value="refresh" :disabled="!sheets.length">Обновить листы<span slot="details">по шаблону</span></wa-dropdown-item>
        </wa-dropdown>
        <wa-button size="s" variant="brand" :disabled="busy || !sheets.length" title="Все листы одним PDF: рамка, штамп, масштаб, легенда" @click="file('pdf')"><FileDown :size="14" /> PDF</wa-button>
        <wa-button size="s" appearance="outlined" :disabled="busy || !sheets.length" title="Все листы редактируемой презентацией PowerPoint: подписи — текстом, карты — фигурами по слоям" @click="file('pptx')"><Presentation :size="14" /> PPTX</wa-button>
        <wa-button size="s" appearance="plain" title="Прежнее окно альбома: «Слои и листы», макет надписей, фотографии" @click="detail"><ExternalLink :size="14" /> Подробно</wa-button>
      </div>
    </div>

    <!-- ход сборки или выгрузки: что идёт и сколько секунд; «Остановить» — после текущего листа -->
    <div v-if="st?.bp" class="job" role="status" aria-live="polite">
      <wa-spinner></wa-spinner><span class="jt">{{ st.bp.text }}</span><span class="t">{{ st.bp.secs }} с</span>
      <wa-button v-if="st.bp.canStop" size="s" appearance="outlined" :disabled="st.bp.stop" title="Уже собранные листы останутся" @click="act(a => a.stop())">{{ st.bp.stop ? "Остановлю после листа…" : "Остановить" }}</wa-button>
    </div>
    <div v-else-if="!engineReady" class="job quiet" role="status"><wa-spinner></wa-spinner><span class="jt">Готовлю сборку альбома…</span></div>

    <!-- вопрос движка: набор собирается поверх других листов -->
    <div v-if="st?.ask" class="ask" role="alertdialog" aria-label="Заменить или добавить листы">
      <p>«{{ st.ask.name }}»: {{ st.ask.n }} л. В альбоме уже есть другие листы ({{ st.ask.have }}).</p>
      <div class="row">
        <wa-button size="s" variant="brand" @click="act(a => a.answer('replace'))">Заменить листы альбома</wa-button>
        <wa-button size="s" appearance="outlined" @click="act(a => a.answer('add'))">Добавить после текущих</wa-button>
        <wa-button size="s" appearance="plain" @click="act(a => a.answer('cancel'))">Отмена</wa-button>
      </div>
    </div>
    <div v-if="legacy" class="ask" role="alertdialog" aria-label="Обновить старые листы">
      <p>Обновить {{ legacy }} {{ word(legacy, "старый лист", "старых листа", "старых листов") }} по шаблону? Ваши названия, рамки и фото сохранятся, набор слоёв и легенда станут как в шаблоне.</p>
      <div class="row">
        <wa-button size="s" variant="brand" @click="refresh(true)">Обновить и старые</wa-button>
        <wa-button size="s" appearance="outlined" @click="refresh(false)">Только листы по шаблону</wa-button>
        <wa-button size="s" appearance="plain" @click="legacy = 0">Отмена</wa-button>
      </div>
    </div>
    <!-- перед выгрузкой: что не готово; щелчок по строке выбирает лист или открывает штамп -->
    <div v-if="issues" class="ask warn" role="alertdialog" aria-label="Не всё готово к выгрузке">
      <p><b>{{ issues.kind === "pdf" ? "PDF" : "PPTX" }}{{ issues.i != null ? " листа" : "" }}: не всё готово</b></p>
      <ul><li v-for="(l, k) in issues.lines.slice(0, 8)" :key="k"><button class="lnk" type="button" @click="jump(l)">{{ l.text }}</button></li>
        <li v-if="issues.lines.length > 8">и ещё {{ issues.lines.length - 8 }}</li></ul>
      <div class="row">
        <wa-button size="s" variant="brand" @click="go">Выгрузить всё равно</wa-button>
        <wa-button size="s" appearance="plain" @click="issues = null">Отмена</wa-button>
      </div>
    </div>

    <wa-details class="stamp" :open="stampOpen" @wa-show="stampOpen = true" @wa-hide="stampOpen = false">
      <span slot="summary"><b>Штамп</b> <span class="sum">{{ stampSum }}</span></span>
      <div class="fields">
        <wa-input v-for="f in META" :key="f[0]" size="s" :label="f[1]" :value="meta[f[0]] || ''" :readonly="viewer" :data-meta="f[0]"
                  @change="e => setMeta(f[0], e.target.value)"></wa-input>
      </div>
      <wa-button size="s" appearance="outlined" :disabled="viewer || busy" title="Заполнить пустые поля «№ КРТ», «Округ, район» и «Адрес» по загруженным слоям; введённое вами не меняется" @click="fill"><WandSparkles :size="14" /> Заполнить по слоям</wa-button>
    </wa-details>

    <!-- настройки альбома (#89): цвет воды на белых схемах и шрифт подписей карт; пусто — как печаталось до настройки -->
    <wa-details class="stamp look" :open="lookOpen" @wa-show="lookOpen = true" @wa-hide="lookOpen = false">
      <span slot="summary"><b>Оформление карт</b> <span class="sum">{{ lookSum }}</span></span>
      <div class="lookrow">
        <wa-color-picker size="s" aria-label="Цвет воды на белых схемах" :value="meta.waterColor || WATER" :disabled="viewer" data-look="water"
                         @change="e => setLook('waterColor', e.target.value)"></wa-color-picker>
        <span class="lbl">Вода на белых схемах<small>сущпол и Генплан — своим цветом</small></span>
        <wa-button v-if="meta.waterColor && meta.waterColor !== WATER" size="s" appearance="plain" :disabled="viewer" title="Голубой #bfe0f5, как по умолчанию" @click="setLook('waterColor', '')">Как было</wa-button>
      </div>
      <wa-select size="s" label="Шрифт подписей карт" :value="meta.labelFont || 'base'" :disabled="viewer" data-look="font" @change="e => setLook('labelFont', e.target.value)">
        <wa-option v-for="f in FONTS" :key="f[0]" :value="f[0]">{{ f[1] }}</wa-option>
      </wa-select>
      <p class="hint">Заголовки и надписи листа — всегда Montserrat. Новые цвет и шрифт попадут в просмотр, PDF и PPTX.</p>
    </wa-details>

    <p v-if="!sheets.length" class="empty">Листов пока нет. «Добавить лист» — один лист по виду карты; «Собрать» → «Альбом ППТ КРТ» соберёт альбом по шаблону: титул, месторасположение, ортофотоплан, сущпол, документация, ПЗЗ, Генплан.</p>
    <ol v-else class="list" role="listbox" aria-label="Листы альбома" @keydown="keys">
      <li v-for="(s, i) in sheets" :key="s.id" role="option" :aria-selected="i === cur" :tabindex="i === cur ? 0 : -1" :class="{ on: i === cur, bad: !!why(s) }"
          :title="(s.title || 'без названия') + (why(s) ? ' — не готов: ' + why(s) : '')" @click="pick(i)">
        <span class="n">{{ i + 1 }}</span>
        <span class="t">{{ s.title || "без названия" }}</span>
        <span class="f">{{ row(s).size }}<template v-if="row(s).scale"> · {{ row(s).scale }}</template></span>
        <CircleAlert v-if="why(s)" :size="14" class="nr" aria-label="не готов" />
      </li>
    </ol>

    <section v-if="sel" class="det" :aria-label="'Лист ' + (cur + 1)">
      <wa-input size="s" label="Название" :value="sel.title || ''" :readonly="viewer" @change="e => setSheet('title', e.target.value)"></wa-input>
      <div class="g2">
        <wa-select size="s" label="Формат" :value="sel.size" :disabled="viewer || row(sel).frozen" @change="e => setSheet('size', e.target.value)">
          <wa-option v-for="(t, k) in sizes" :key="k" :value="k">{{ t }}</wa-option>
        </wa-select>
        <wa-select size="s" label="Масштаб" :value="String(sel.scale || 0)" :disabled="viewer || row(sel).noScale" @change="e => setSheet('scale', +e.target.value)">
          <wa-option value="0">авто{{ row(sel).auto && row(sel).scale ? " (" + row(sel).scale + ")" : "" }}</wa-option>
          <wa-option v-if="sel.scale && !scales.includes(sel.scale)" :value="String(sel.scale)">1:{{ sel.scale.toLocaleString("ru-RU") }} (рамка на карте)</wa-option>
          <wa-option v-for="v in scales" :key="v" :value="String(v)">1:{{ v.toLocaleString("ru-RU") }}</wa-option>
        </wa-select>
      </div>
      <div class="flags">
        <wa-checkbox size="s" :checked="!!sel.legend" :disabled="viewer || sel.kind === 'tep' || row(sel).frozen" @change="e => setSheet('legend', e.target.checked)">Легенда</wa-checkbox>
        <wa-checkbox size="s" :checked="!!sel.tep" :disabled="viewer || sel.kind === 'tep' || row(sel).frozen" @change="e => setSheet('tep', e.target.checked)">Таблица ТЭП</wa-checkbox>
      </div>
      <p v-if="why(sel)" class="nrw"><b>Не готов:</b> {{ why(sel) }}</p>
      <p v-if="row(sel).frozen" class="hint">Готовая вёрстка из файла: слои и оформление записаны в самом листе.</p>
      <p v-else-if="row(sel).tpl" class="hint">Лист по шаблону: слои и оформление — из шаблона; рамку на карте можно сдвинуть, за угол — сменить масштаб.</p>
      <div class="row">
        <wa-button size="s" appearance="outlined" :disabled="busy" @click="preview"><Eye :size="14" /> Просмотр</wa-button>
        <wa-button size="s" appearance="outlined" :disabled="busy" title="PDF только этого листа" @click="file('pdf', cur)"><FileDown :size="14" /> PDF листа</wa-button>
        <wa-button v-if="sel.kind !== 'tep'" size="s" appearance="outlined" data-act="lay" title="Двигать, выравнивать и править надписи листа — окно «Макет надписей»" @click="openLay"><Type :size="14" /> Надписи</wa-button>
        <wa-button size="s" appearance="plain" :disabled="viewer || cur === 0" title="Выше" aria-label="Выше" @click="up"><ArrowUp :size="14" /></wa-button>
        <wa-button size="s" appearance="plain" :disabled="viewer" title="Удалить лист" aria-label="Удалить лист" @click="askDrop = true"><Trash2 :size="14" /></wa-button>
      </div>
      <!-- слои листа (роли сверху вниз): глаз — только на этом листе; перетаскивание и слои проекта — в окне «Подробно» -->
      <wa-details v-if="roles && roles.kind === 'layout'" class="stamp lay" :open="layOpen" @wa-show="layOpen = true" @wa-hide="layOpen = false">
        <span slot="summary"><b>Слои листа</b> <span class="sum">{{ laySum }}</span></span>
        <ul class="roles" aria-label="Слои листа, сверху вниз">
          <li v-for="r in roles.rows" :key="r.id" :class="{ off: !r.on }" :title="'Слои: ' + r.layers.join('; ')">
            <wa-button size="s" appearance="plain" :disabled="!roles.editable" :aria-label="(r.on ? 'Скрыть' : 'Показать') + ' «' + r.title + '» на этом листе'"
                       :title="roles.editable ? (r.on ? 'Скрыть на этом листе' : 'Показать на этом листе') : roles.why" @click="roleEye(r)">
              <Eye v-if="r.on" :size="14" /><EyeOff v-else :size="14" /></wa-button>
            <span class="rt">{{ r.title }} <small>{{ r.count }}</small><small class="src">{{ r.source }}</small></span>
            <span class="cov" :class="{ w: r.cover != null && r.cover < .9 }">{{ r.cover == null ? "—" : Math.round(r.cover * 100) + " %" }}</span>
            <span class="chips">
              <button v-if="r.hand" class="chip hand" type="button" :disabled="!roles.editable" :title="r.hand + (roles.editable ? '. Щелчок — вернуть как по образцу' : '')" @click="roleReset(r)">вручную</button>
              <span v-if="r.badge" class="chip" :class="r.badge.tone">{{ r.badge.text }}</span>
            </span>
          </li>
        </ul>
        <p v-if="!roles.editable && roles.why" class="hint">{{ roles.why }}</p>
        <p class="hint">Порядок источников и перенос слоёв между листами — в окне «Подробно» → «Слои и листы».</p>
      </wa-details>
      <p v-else-if="roles && roles.kind === 'map'" class="hint">Лист показывает текущую карту: состава слоёв у него нет.</p>
      <div v-if="img.url && img.id === sel.id" class="prev"><img :src="img.url" :alt="'Лист ' + (cur + 1) + ': ' + (sel.title || '')"></div>
      <p v-else-if="img.busy" class="hint">Собираю картинку листа…</p>
    </section>

    <wa-dialog label="Удалить лист" :open="askDrop" @wa-after-hide="askDrop = false">
      <p>Удалить лист «{{ sel?.title || "без названия" }}» из альбома? Остальные листы останутся.</p>
      <wa-button slot="footer" size="s" appearance="plain" @click="askDrop = false">Отмена</wa-button>
      <wa-button slot="footer" size="s" variant="danger" @click="drop">Удалить</wa-button>
    </wa-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { ArrowUp, CircleAlert, ExternalLink, Eye, EyeOff, FileDown, FilePlus2, LayoutTemplate, Presentation, Trash2, Type, WandSparkles } from "@lucide/vue";
import { album, call, engineState, openAlbum, startEngine, sync } from "../albumhost.js";
import { C } from "../collab.js";
import { markDirty, notice } from "../project.js";
import { project, winApi } from "../store.js";

const WATER = "#bfe0f5";   // вода белых схем по умолчанию (albums.js C_WATER_VIS, print_io.WATER_VIS)
/* шрифт подписей карт: base — как печаталось до настройки (подписи альбома ППТ КРТ Montserrat жирным, у прочих листов PT Sans) */
const FONTS = [["base", "Как сейчас"], ["pt-sans", "PT Sans"], ["montserrat", "Montserrat"]];
const META = [["object", "Объект"], ["code", "Шифр"], ["stage", "Стадия: ПП, П, Р"], ["org", "Организация"], ["short", "№ КРТ"], ["place", "Округ, район"], ["address", "Адрес"]];
const props = defineProps({ params: Object });
/* выбранный лист — общий с рамками на карте (albumframes.js) */
const cur = computed({ get: () => album.cur, set: v => { album.cur = v; } });
const st = ref(null), stampOpen = ref(false), lookOpen = ref(false), askDrop = ref(false), legacy = ref(0), issues = ref(null), ver = ref(0);
const img = reactive({ id: null, url: "", busy: false });
const roles = ref(null), layOpen = ref(true);
const viewer = computed(() => C.role === "viewer");
const engineReady = computed(() => album.ready);

/* Альбом — в project.raw (без слежения Vue): ver заставляет перечитать его после правок здесь и приёма правок движка. */
const alb = computed(() => { ver.value; album.rev; return project.raw?.album || null; });
const sheets = computed(() => alb.value?.sheets || []);
const meta = computed(() => alb.value?.meta || {});
const sel = computed(() => sheets.value[cur.value] || null);
const sizes = computed(() => st.value?.sizes || {});
const scales = computed(() => st.value?.scales || []);
const busy = computed(() => !!st.value?.busy);
const row = s => st.value?.rows?.[s.id] || { size: s.size || "", scale: "" };
const why = s => st.value?.why?.[s.id] || "";
const word = (n, a, b, c) => n % 10 === 1 && n % 100 !== 11 ? a : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? b : c;
const stampSum = computed(() => { ver.value; album.rev; const p = [meta.value.object, meta.value.code, meta.value.stage].filter(Boolean); return p.length ? p.join(" · ") : "не заполнен"; });
const lookSum = computed(() => {
  ver.value; album.rev;   // meta — тот же объект project.raw, правится на месте: перечитать после каждой правки
  const w = meta.value.waterColor && meta.value.waterColor !== WATER ? "вода " + meta.value.waterColor : "";
  const f = FONTS.find(x => x[0] === meta.value.labelFont)?.[1] || "";
  return [w, f].filter(Boolean).join(" · ") || "как сейчас";
});
const head = computed(() => st.value?.stat || (sheets.value.length ? `Альбом: ${sheets.value.length} ${word(sheets.value.length, "лист", "листа", "листов")}` : "Альбом: листов нет"));

/* состояние движка (ход сборки, «не готов», строки листов) — раз в полсекунды, пока вкладка открыта */
let poll = 0;
let lastFrames = "";
function readState() {
  const s = engineState(); st.value = s ? JSON.parse(JSON.stringify(s)) : null;
  const f = JSON.stringify(st.value?.frames || []);
  if (f !== lastFrames) { lastFrames = f; album.frames = st.value?.frames || []; }   // рамки на карте — только когда изменились
}
/* рамки листов на карте — пока вкладка на виду */
let offVis = null;
onMounted(() => {
  startEngine(); readState(); poll = setInterval(readState, 500);
  const api = props.params?.api;
  album.tab = api ? api.isVisible : true;
  offVis = api?.onDidVisibilityChange?.(e => { album.tab = e.isVisible; });
});
onBeforeUnmount(() => { clearInterval(poll); offVis?.dispose?.(); album.tab = false; });
watch(() => sheets.value.length, n => { if (cur.value >= n) cur.value = Math.max(0, n - 1); });

/* действие движка: ошибки — в строку состояния */
async function act(fn) {
  try { return await call(fn); } catch (e) { notice.value = "Альбом: " + (e.message || e); } finally { readState(); }
}

/* правка альбома здесь: как touch() движка — время правки, проект изменён; движок получит проект перед следующим действием */
function edited() {
  const a = project.raw.album; if (a) { a.meta ||= {}; a.meta.editedAt = new Date().toISOString(); }
  markDirty(); ver.value++; sync();
}
function ensure() { project.raw.album ||= { meta: { object: "", code: "", stage: "ПП", org: "" }, sheets: [] }; return project.raw.album; }
function setMeta(k, v) { const a = ensure(); a.meta[k] = v; if (a.meta.auto) delete a.meta.auto[k]; edited(); }
/* настройка оформления: значение по умолчанию не хранится — альбом печатается как до настройки */
function setLook(k, v) {
  const a = ensure();
  if (!v || v === "base" || (k === "waterColor" && v.toLowerCase() === WATER)) delete a.meta[k]; else a.meta[k] = k === "waterColor" ? v.toLowerCase() : v;
  img.id = null; edited();
}
/* «Надписи» — окно «Макет надписей» (AlbumLayout.vue) для выбранного листа */
function openLay() { album.lay = cur.value; album.layTick++; winApi.open("albumlay"); }

/* «Слои листа»: роли выбранного листа от движка (окно «Слои и листы»); перечитываются при смене листа и после правок */
let rolesFor = null;
async function loadRoles() {
  const i = cur.value, id = sel.value?.id; if (!id) { roles.value = null; return; }
  if (!album.ready) return;
  try {
    const r = await call(a => a.roles(i));
    if (sel.value?.id === id) { roles.value = r ? JSON.parse(JSON.stringify(r)) : null; rolesFor = id; }
  } catch { roles.value = null; }
}
const laySum = computed(() => {
  const r = roles.value?.rows || [], off = r.filter(x => !x.on).length, bad = r.filter(x => x.badge && x.badge.tone !== "none").length;
  return [`${r.length} ${word(r.length, "роль", "роли", "ролей")}`, off ? `скрыто ${off}` : "", bad ? `${bad} с замечанием` : ""].filter(Boolean).join(" · ");
});
async function roleEye(r) { await act(a => a.role(cur.value, r.id)); setTimeout(loadRoles, 400); img.id = null; }
async function roleReset(r) { await act(a => a.resetRole(cur.value, r.id)); setTimeout(loadRoles, 400); img.id = null; }
watch(() => [sel.value?.id, album.rev, album.ready], ([id], [was] = []) => { if (id !== was) roles.value = rolesFor === id ? roles.value : null; loadRoles(); }, { immediate: true });
function setSheet(k, v) { if (!sel.value) return; sel.value[k] = v; edited(); }
function up() { const i = cur.value, l = sheets.value; if (i < 1) return; [l[i - 1], l[i]] = [l[i], l[i - 1]]; cur.value = i - 1; edited(); }
function drop() { askDrop.value = false; const l = sheets.value; if (!l.length) return; l.splice(cur.value, 1); cur.value = Math.min(cur.value, l.length - 1); edited(); }
function pick(i) { cur.value = i; album.fit++; }   // карта приближается к рамке листа
function keys(e) {
  const n = sheets.value.length; if (!n) return;
  const k = { ArrowDown: cur.value + 1, ArrowUp: cur.value - 1, Home: 0, End: n - 1 }[e.key];
  if (k == null) return;
  e.preventDefault(); cur.value = Math.min(Math.max(k, 0), n - 1);
  e.currentTarget.querySelector(`li:nth-child(${cur.value + 1})`)?.focus();
}

async function add(size) {
  const i = await act(a => a.add(size));
  if (Number.isInteger(i)) setTimeout(() => { cur.value = i; }, 400);   // движок вернёт альбом с новым листом через полсекунды
}
async function build(kind) {
  if (kind === "refresh") return refresh(null);
  if (!project.territory) { notice.value = "Сначала задайте границу территории — окно «Данные»: листы альбома строятся вокруг неё"; return; }
  await act(a => a.build(kind));
}
async function refresh(old) {
  legacy.value = 0;
  const r = await act(a => a.refresh(old));
  if (r?.old) legacy.value = r.old;
}
async function fill() {
  const d = await act(a => a.fillMeta());
  const names = { short: "№ КРТ", place: "округ, район", address: "адрес" };
  notice.value = d?.length ? "Заполнено: " + d.map(k => names[k] || k).join(", ") : "Нечего заполнять: поля уже заполнены или нужных слоёв нет";
}
/* PDF и PPTX: сначала «не всё готово» (если есть) — в этом окне; i — один лист */
async function file(kind, i) {
  issues.value = null;
  const lines = await act(a => a.issues(kind, i));
  if (lines?.length) { issues.value = { kind, i, lines: JSON.parse(JSON.stringify(lines)) }; return; }
  act(a => a.file(kind, i));
}
function go() { const q = issues.value; issues.value = null; if (q) act(a => a.file(q.kind, q.i)); }
function jump(l) {
  if (l.sheet != null) { cur.value = l.sheet; return; }
  if (l.stamp) stampOpen.value = true;
}
async function preview() {
  const s = sel.value; if (!s) return;
  img.busy = true; img.id = null;
  try { const url = await act(a => a.preview(cur.value)); if (url) { img.url = url; img.id = s.id; } } finally { img.busy = false; }
}
function detail() { openAlbum(); }

/* меню «Выгрузка» → PDF или PPTX альбома: вкладка открылась (или уже открыта), выгрузка идёт отсюда */
watch(() => album.want, k => { if (k) { album.want = null; file(k); } }, { immediate: true });
</script>

<style>
.alb .ahead { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; margin-bottom: 8px; }
.alb .stat { flex: 1 1 200px; margin: 0; min-width: 0; font-size: var(--wa-font-size-s); color: var(--g-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.alb .acts { display: flex; flex-wrap: wrap; gap: 6px; }
.alb wa-button::part(label) { display: inline-flex; gap: 4px; align-items: center; }
.alb .job { display: flex; align-items: center; gap: 8px; padding: 6px 10px; margin-bottom: 8px; border-radius: 10px; font-size: var(--wa-font-size-s);
  background: var(--wa-color-brand-fill-quiet); border: 1px solid var(--wa-color-brand-border-quiet); }
.alb .job.quiet { background: var(--wa-color-surface-lowered); border-color: var(--g-line); color: var(--g-muted); }
.alb .job wa-spinner { font-size: 14px; --track-width: 2px; flex: none; }
.alb .job .jt { flex: 1; min-width: 0; }
.alb .job .t { white-space: nowrap; color: var(--g-muted); font-variant-numeric: tabular-nums; font-size: var(--wa-font-size-xs); }
.alb .ask { padding: 8px 10px; margin-bottom: 8px; border-radius: 10px; border: 1px solid var(--wa-color-brand-border-quiet); background: var(--wa-color-surface-raised); font-size: var(--wa-font-size-s); }
.alb .ask.warn { border-color: var(--wa-color-warning-border-normal); }
.alb .ask p { margin: 0 0 6px; line-height: 1.4; }
.alb .ask ul { margin: 0 0 6px; padding-left: 18px; }
.alb .ask .lnk { all: unset; display: block; cursor: pointer; text-decoration: underline dotted; line-height: 1.4; }
.alb .ask .lnk:focus-visible { outline: 2px solid var(--wa-color-focus); }
.alb .row { display: flex; flex-wrap: wrap; gap: 6px; }
.alb .stamp { margin-bottom: 8px; }
.alb .stamp::part(header) { font-size: var(--wa-font-size-s); }
.alb .stamp .sum { color: var(--g-muted); font-weight: 400; margin-left: 6px; }
.alb .stamp .fields { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 6px; margin-bottom: 8px; }
.alb .lay .roles { list-style: none; margin: 0 0 6px; padding: 0; }
.alb .lay .roles li { display: grid; grid-template-columns: 28px minmax(0, 1fr) 44px auto; align-items: center; gap: 6px; padding: 2px 0;
  font-size: var(--wa-font-size-s); border-top: 1px solid var(--g-line); }
.alb .lay .roles li:first-child { border-top: 0; }
.alb .lay .roles li.off .rt { opacity: .55; }
.alb .lay .rt { min-width: 0; overflow-wrap: anywhere; line-height: 1.3; }
.alb .lay .rt small { color: var(--g-muted); font-size: var(--wa-font-size-xs); margin-left: 2px; }
.alb .lay .rt .src { display: block; margin-left: 0; }
.alb .lay .cov { text-align: right; font-variant-numeric: tabular-nums; font-size: var(--wa-font-size-xs); color: var(--g-muted); }
.alb .lay .cov.w { color: var(--wa-color-warning-on-quiet); }
.alb .lay .chips { display: flex; flex-wrap: wrap; gap: 4px; justify-content: flex-end; }
.alb .lay .chip { all: unset; font-size: var(--wa-font-size-xs); padding: 1px 6px; border-radius: 999px; background: var(--wa-color-neutral-fill-quiet); white-space: nowrap; }
.alb .lay .chip.warn { background: var(--wa-color-warning-fill-quiet); color: var(--wa-color-warning-on-quiet); }
.alb .lay .chip.bad { background: var(--wa-color-danger-fill-quiet); color: var(--wa-color-danger-on-quiet); }
.alb .lay .chip.hand { background: var(--wa-color-brand-fill-quiet); color: var(--wa-color-brand-on-quiet); cursor: pointer; }
.alb .lay .chip.hand:focus-visible { outline: 2px solid var(--wa-color-focus); }
.alb .look .lookrow { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.alb .look .lbl { flex: 1; display: grid; font-size: var(--wa-font-size-s); line-height: 1.3; }
.alb .look .lbl small { color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.alb .look wa-select { margin-bottom: 6px; }
.alb .look .hint { margin: 0; }
.alb .empty { color: var(--g-muted); font-size: var(--wa-font-size-s); line-height: 1.4; }
.alb .list { list-style: none; margin: 0 0 8px; padding: 0; border: 1px solid var(--g-line); border-radius: 8px; }
.alb .list li { display: grid; grid-template-columns: 22px minmax(0, 1fr) auto 16px; align-items: baseline; line-height: 16px; gap: 6px; padding: 6px 8px;
  font-size: var(--wa-font-size-s); cursor: pointer; border-top: 1px solid var(--g-line); }
.alb .list li:first-child { border-top: 0; }
.alb .list li:hover { background: var(--wa-color-neutral-fill-quiet); }
.alb .list li.on { background: var(--wa-color-brand-fill-quiet); }
.alb .list li:focus-visible { outline: 2px solid var(--wa-color-focus); outline-offset: -2px; }
.alb .list .n { color: var(--g-muted); font-variant-numeric: tabular-nums; text-align: right; }
.alb .list .t { overflow-wrap: anywhere; }   /* название целиком, длинное — в две строки (владелец 09.10.2026) */
.alb .list .f { color: var(--g-muted); font-size: var(--wa-font-size-xs); white-space: nowrap; font-variant-numeric: tabular-nums; }
.alb .list .nr { color: var(--wa-color-warning-on-quiet); align-self: start; margin-top: 1px; }   /* номер, формат и значок — на линии первой строки названия */
.alb .det { display: grid; gap: 8px; padding-top: 8px; border-top: 1px solid var(--g-line); }
.alb .det .g2 { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.alb .det .flags { display: flex; gap: 16px; }
.alb .det .nrw { margin: 0; font-size: var(--wa-font-size-s); color: var(--wa-color-warning-on-quiet); }
.alb .det .hint { margin: 0; }
.alb .det .prev { border: 1px solid var(--g-line); border-radius: 8px; background: #fff; }
.alb .det .prev img { display: block; width: 100%; height: auto; }
</style>
