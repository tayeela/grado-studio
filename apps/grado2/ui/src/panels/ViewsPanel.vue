<!-- ГРАДО 2 · окно «Виды» нового интерфейса (как «Темы карты» в QGIS и web/views.js рабочей страницы): вид запоминает,
     какие слои видны, их оформление и прозрачность, видимость групп, подложку и, по желанию, масштаб. «Показать»
     возвращает карту к виду одним щелчком; легенда вида — его видимые слои с классами. Виды хранятся в файле проекта
     (поле views, тот же формат) и служат листам альбома: удалённый вид переводит свои листы на текущую карту.
     Рамка вида (#119): вид — это ещё и «где». Кнопка-рамка в строке вида рисует на карте прямоугольник с пропорциями
     (А-формат, 4 : 3, 16 : 9, свои) или размером в метрах; блок «Карта» на листе выбирает вид и показывает его рамку
     (viewframes.js, viewframesmap.js). Пока окно открыто, рамки видов видны на карте, с ними — рамки листов альбома ППТ КРТ (список «Листы альбома»). Строку вида тянут на лист в «Макете
     листа» — там встаёт карта этого вида (SheetEditor.vue dropView). -->
<template>
  <div class="pane views">
    <div class="bar">
      <wa-input size="s" placeholder="Название вида" title="Название нового вида, например «Ограничения»" :value="name" @input="e => (name = e.target.value)" @keydown.enter="add"></wa-input>
      <wa-checkbox size="s" :checked="withExt" title="Вид запомнит и масштаб карты" @change="e => (withExt = e.target.checked)">с масштабом</wa-checkbox>
      <wa-button size="s" variant="brand" title="Запомнить видимые слои, их оформление и подложку" @click="add"><BookmarkPlus :size="15" /> Сохранить вид</wa-button>
    </div>

    <p v-if="!project.views.length" class="hint">Видов пока нет. Настройте карту (какие слои видны, их стиль, подложку) и сохраните вид —
      например «Существующее положение», «Ограничения», «Эскиз». Переключение вида меняет карту одним щелчком.</p>
    <table v-else class="vl">
      <tr v-for="v in project.views" :key="v.id" :class="{ cur: v.id === viewCur }" draggable="true" @dragstart="dragOut(v, $event)">
        <td class="nm" :title="`Показать вид «${v.name}»: ${plural(nOn(v), ['видимый слой', 'видимых слоя', 'видимых слоёв'])}${v.extent ? ', с масштабом' : ''}. Перетащите строку на лист в «Макете листа» — там встанет карта этого вида`" @click="show(v)">
          <div class="t"><Eye :size="14" /><span>{{ v.name }}</span></div>
          <div class="n">{{ plural(nOn(v), ["слой", "слоя", "слоёв"]) }}{{ v.extent ? " · с масштабом" : "" }}<span v-if="v.frame" class="fr"> · рамка {{ sizeT(v.frame) }}</span></div></td>
        <td class="act">
          <wa-button size="s" :appearance="vframes.draw === v.id || vframes.sel === v.id ? 'filled' : 'plain'" :variant="vframes.sel === v.id ? 'brand' : 'neutral'"
                     :title="v.frame ? 'Рамка вида на карте: показать и править' : 'Нарисовать рамку вида на карте — где этот вид встанет на лист'" @click="frameBtn(v)"><Frame :size="14" /></wa-button>
          <wa-button size="s" appearance="plain" title="Заменить вид текущим состоянием карты" @click="update(v)"><RefreshCw :size="14" /></wa-button>
          <wa-button size="s" :appearance="confirmId === v.id ? 'filled' : 'plain'" :variant="confirmId === v.id ? 'danger' : 'neutral'"
                     :title="confirmId === v.id ? 'Нажмите ещё раз, чтобы удалить' : 'Удалить вид'" @click="remove(v)">
            <Trash2 :size="14" /></wa-button>
        </td>
      </tr>
    </table>
    <p v-if="confirmId" class="hint">Нажмите красную корзину ещё раз, чтобы удалить вид.<template v-if="usedBy(confirmId).length">
      Листов с этим видом: {{ usedBy(confirmId).length }} — они перейдут на текущую карту.</template></p>

    <template v-if="album.frames?.length">
      <div class="sect">Листы альбома ППТ КРТ</div>
      <table class="vl">
        <tr v-for="f in album.frames" :key="f.id" :class="{ cur: vframes.sel === ALB + f.id }">
          <td class="nm" :title="`${f.title || f.label}. Рамка листа на карте — серым пунктиром, как рамка вида: тяните внутри — сдвиг, за угол — масштаб`" @click="showSheet(f)">
            <div class="t"><Frame :size="14" /><span>{{ f.label }}</span></div></td>
        </tr>
      </table>
    </template>

    <p v-if="vframes.draw" class="hint drawing">Тяните рамку на карте для вида «{{ viewOf(vframes.draw)?.name }}». Shift — без пропорций, Esc — отмена.</p>

    <template v-if="fv">
      <div class="sect">Рамка вида «{{ fv.name }}»</div>
      <div class="frow">
        <label>Пропорции<select :value="aspectSel" @change="setAspect($event.target.value)">
          <option v-for="a in ASPECTS" :key="a.id" :value="a.id">{{ a.t }}</option><option value="own">Свои…</option></select></label>
        <wa-input v-if="aspectSel === 'own'" size="s" class="own" placeholder="3:2" title="Свои пропорции, например 3:2 или 5:4" :value="ownAspect"
          @change="e => setAspect(e.target.value)"></wa-input>
      </div>
      <div v-if="fv.frame" class="frow">
        <label>Ширина, м<input type="number" min="1" step="10" :value="Math.round(fv.frame.w)" @change="setSide('w', +$event.target.value)"></label>
        <label>Высота, м<input type="number" min="1" step="10" :value="Math.round(fv.frame.h)" @change="setSide('h', +$event.target.value)"></label>
      </div>
      <p class="hint">{{ fv.frame ? `На карте тяните рамку внутри — сдвиг, за угол — размер (Shift — без пропорций).${uses(fv.id) ? ` Вид стоит на листах: ${uses(fv.id)}.` : " Перетащите строку вида на лист в «Макете листа» или выберите вид в блоке «Карта»."}` : "У вида ещё нет рамки: нарисуйте её на карте или возьмите экран карты." }}</p>
      <div class="frow">
        <wa-button size="s" @click="draw(fv)"><Frame :size="14" /> {{ fv.frame ? "Нарисовать заново" : "Нарисовать" }}</wa-button>
        <wa-button size="s" title="Рамка по тому, что сейчас видно на карте" @click="byScreen(fv)"><Scan :size="14" /> По экрану</wa-button>
        <wa-button v-if="fv.frame" size="s" appearance="plain" title="Приблизить карту к рамке" @click="vframes.fit = fv.id">Показать</wa-button>
        <wa-button v-if="fv.frame" size="s" appearance="plain" variant="danger" title="Убрать рамку: листы с этим видом останутся на прежнем месте" @click="dropFrame(fv)">Убрать</wa-button>
      </div>
    </template>

    <template v-if="cur">
      <div class="sect">Легенда вида «{{ cur.name }}»</div>
      <p v-if="!legend.length" class="hint">В виде нет видимых слоёв</p>
      <div v-for="g in legend" :key="g.key" class="lg">
        <div class="lgh"><LayerSwatch :l="g.l" :style="g.st" :opacity="g.op" />{{ g.title }}</div>
        <div v-for="(it, i) in g.items" :key="i" class="lgi">
          <LayerSwatch :l="g.l" :style="{ ...g.st, mode: 'single', fill: it.c }" :opacity="g.op" />{{ it.v || "—" }}</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { BookmarkPlus, Eye, Frame, RefreshCw, Scan, Trash2 } from "@lucide/vue";
import { ASPECTS, frameLabel, ratioOf, withRatio, VIEW_MIME } from "../viewframes.js";
import { ALB, frameFromExtent, vframes, viewOf } from "../viewframesmap.js";
import { album } from "../albumhost.js";
import { basemapId, project, setBasemap, viewCur, viewNow } from "../store.js";
import LayerSwatch from "./LayerSwatch.vue";
import { dataRev, grp, mapApi } from "../edit.js";
import { notice } from "../project.js";
import { fullStyle, legendItems, okn } from "../symbology.js";
import { plural } from "../geom.js";

const name = ref(""), withExt = ref(false), confirmId = ref("");
const clone = o => JSON.parse(JSON.stringify(o));
const nOn = v => v.layers.filter(x => x.visible).length;

function capture(title, ext) {
  return { id: "v" + Date.now().toString(36), name: title, basemap: basemapId.value,
    layers: project.layers.map(l => ({ key: l.key, visible: l.visible, style: clone(l.style), layerOpacity: l.layerOpacity })),
    groups: project.groups.map(g => ({ id: g.id, visible: g.visible })),
    extent: ext && viewNow.center ? { center: [...viewNow.center], zoom: viewNow.zoom } : null };
}
function add() {
  const t = name.value.trim() || `Вид ${project.views.length + 1}`, v = capture(t, withExt.value);
  project.views.push(v); viewCur.value = v.id; name.value = "";
  notice.value = `Вид «${t}» сохранён`;
}
/* Слой, которого в виде нет (добавлен позже), скрывается — как у рабочей страницы. */
// строку вида тянут на лист «Макета листа»: туда уходит id вида
function dragOut(v, e) { e.dataTransfer.setData(VIEW_MIME, v.id); e.dataTransfer.setData("text/plain", v.name); e.dataTransfer.effectAllowed = "copy"; }
function show(v) {
  const by = new Map(v.layers.map(x => [x.key, x]));
  project.layers.forEach(l => {
    const x = by.get(l.key); if (!x) { l.visible = false; return; }
    l.visible = x.visible; l.layerOpacity = okn(x.layerOpacity, 1); l.style = fullStyle(clone(x.style));
  });
  v.groups.forEach(x => { const g = grp(x.id); if (g) g.visible = x.visible; });
  if (v.basemap) setBasemap(v.basemap);
  if (v.extent?.center) mapApi.setView?.(v.extent.center, v.extent.zoom);
  viewCur.value = v.id; confirmId.value = ""; vframes.sel = v.id;
}
function update(v) {
  const i = project.views.indexOf(v);
  project.views.splice(i, 1, { ...capture(v.name, !!v.extent), id: v.id, ...(v.frame ? { frame: v.frame } : {}) }); viewCur.value = v.id;   // рамка остаётся
  notice.value = `Вид «${v.name}» обновлён`;
}
const sheets = () => project.raw?.album?.sheets || [];
const usedBy = id => sheets().filter(s => s.view === id);
/* Удаление — со второго нажатия. Лист на удалённом виде не печатает молча «что сейчас на карте»: он явно переводится
   на текущую карту (album.sheets[].view = ""), как в web/views.js. */
function remove(v) {
  if (confirmId.value !== v.id) { confirmId.value = v.id; return; }
  const used = usedBy(v.id);
  used.forEach(s => { s.view = ""; });
  project.views.splice(project.views.indexOf(v), 1);
  if (viewCur.value === v.id) viewCur.value = null;
  confirmId.value = "";
  notice.value = used.length ? `Вид «${v.name}» удалён. Листы ${used.map(s => `«${s.title}»`).join(", ")} теперь показывают текущую карту`
    : `Вид «${v.name}» удалён. Ctrl+Z — вернуть`;
}

const cur = computed(() => project.views.find(v => v.id === viewCur.value));

/* ---------- рамка вида (#119) ---------- */
onMounted(() => { vframes.on++; });
onBeforeUnmount(() => { vframes.on--; if (vframes.draw) vframes.draw = ""; });
/* лист альбома в списке — выбрать его рамку и приблизить карту */
const showSheet = f => { album.cur = f.i; vframes.sel = ALB + f.id; vframes.fit = ALB + f.id; };
const ownView = id => project.views.find(v => v.id === id);   // у области данных и листов альбома своей панели рамки нет
const fv = computed(() => ownView(vframes.sel) || ownView(vframes.draw) || cur.value);
const sizeT = f => frameLabel("", f).slice(3);
const aspectOf = v => v?.frame?.aspect || vframes.aspect;
const aspectSel = computed(() => { const a = aspectOf(fv.value); return ASPECTS.some(x => x.id === a) ? a : "own"; });
const ownAspect = computed(() => aspectSel.value === "own" && aspectOf(fv.value) !== "own" ? aspectOf(fv.value) : "");
function setAspect(a) {
  vframes.aspect = a;
  const v = fv.value; if (!v?.frame || a === "own") return;
  const r = ratioOf(a); if (a !== "free" && !r) { notice.value = "Пропорции пишутся так: 3:2"; return; }
  const [w, h] = withRatio(v.frame.w, v.frame.h, r);
  v.frame = { ...v.frame, aspect: a, w: Math.round(w * 10) / 10, h: Math.round(h * 10) / 10 };
}
function setSide(k, val) {
  const v = fv.value; if (!v?.frame || !(val > 0)) return;
  const r = ratioOf(v.frame.aspect), f = { ...v.frame, [k]: val };
  if (r) { const land = v.frame.w >= v.frame.h; if (k === "w") f.h = land ? val / r : val * r; else f.w = land ? val * r : val / r; }
  f.w = Math.round(f.w * 10) / 10; f.h = Math.round(f.h * 10) / 10; v.frame = f;
}
function draw(v) { vframes.sel = v.id; vframes.draw = v.id; if (v.frame?.aspect) vframes.aspect = v.frame.aspect; }
function frameBtn(v) {
  if (!v.frame) return draw(v);
  vframes.sel = v.id; vframes.fit = v.id;
}
function byScreen(v) {
  const ext = mapApi.extent?.(); if (!ext) { notice.value = "Откройте окно «Карта»"; return; }
  v.frame = frameFromExtent(ext, aspectOf(v) === "own" ? "free" : aspectOf(v)); vframes.sel = v.id; vframes.draw = "";
}
function dropFrame(v) { delete v.frame; vframes.sel = v.id; }
/* на каких листах «Макета листа» стоит вид: «Лист 1, Лист 3» */
const uses = id => (project.layouts || []).filter(s => (s.blocks || []).some(b => b.kind === "map" && b.view === id)).map(s => s.title || "без названия").join(", ");
/* Легенда: видимые в виде слои сверху вниз (в порядке окна «Слои») с их знаком и до 12 классов. */
const legend = computed(() => {
  const v = cur.value; if (!v) return [];
  dataRev.value;
  const on = new Map(v.layers.filter(x => x.visible).map(x => [x.key, x]));
  return project.layers.filter(l => on.has(l.key) && (!l.group || v.groups.find(g => g.id === l.group)?.visible !== false)).map(l => {
    const st = fullStyle(clone(on.get(l.key).style));
    return { key: l.key, title: l.title, l, st, op: okn(on.get(l.key).layerOpacity, okn(l.layerOpacity, 1)), items: legendItems(st, project.data[l.key]?.fc).filter(it => !it.off).slice(0, 12) };
  });
});
</script>

<style>
.views .bar { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-bottom: var(--wa-space-s); }
.views .bar wa-input { flex: 1 1 180px; min-width: 0; margin: 0 !important; }
.views .bar wa-checkbox { margin: 0 !important; }
.views table.vl { width: 100%; border-collapse: collapse; font-size: var(--wa-font-size-s); table-layout: fixed; }
.views table.vl td { padding: 3px 4px; border-bottom: 1px solid var(--g-line); vertical-align: top; }
.views table.vl tr.cur td { background: var(--wa-color-brand-fill-quiet); }
/* строка вида: название во всю ширину (длинное переносится), число слоёв второй строкой, кнопки узкие справа */
.views td.nm { cursor: pointer; overflow-wrap: anywhere; }
.views td.nm .t { display: flex; gap: 5px; align-items: flex-start; line-height: 1.3; }
.views td.nm .t svg { flex: none; margin-top: 2px; color: var(--g-muted); }
.views td.nm:hover { color: var(--wa-color-brand-on-quiet); }
.views td.nm .n { padding-left: 19px; }
.views .n { color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.views td.act { width: 84px; white-space: nowrap; text-align: right; }
.views td.act wa-button::part(base) { padding-inline: 3px; }
.views td.act wa-button { --wa-form-control-height: 24px; }
.views .fr { color: #7a3fd1; }
.views .frow { display: flex; gap: 6px; align-items: flex-end; flex-wrap: wrap; margin: 4px 0; font-size: var(--wa-font-size-s); }
.views .frow label { display: flex; flex-direction: column; gap: 2px; color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.views .frow select, .views .frow input { font: inherit; font-size: var(--wa-font-size-s); color: var(--wa-color-text-normal); background: var(--wa-color-surface-default); border: 1px solid var(--g-line); border-radius: 4px; padding: 2px 4px; height: 26px; }
.views .frow input[type=number] { width: 92px; }
.views .frow .own { width: 80px; }
.views .hint.drawing { color: #7a3fd1; }
.views .lg { margin-bottom: 6px; font-size: var(--wa-font-size-s); }
.views .lgh { display: flex; gap: 6px; align-items: center; }
.views .lgi { display: flex; gap: 6px; align-items: center; padding-left: 22px; color: var(--g-muted); font-size: var(--wa-font-size-xs); }
</style>
