<!-- ГРАДО 2 · панель «Свойства» редактора раскладки (как «Свойства элемента» и «Макет» в QGIS). Ничего не выбрано —
     свойства листа: формат, ориентация, штамп, сетка, привязки, направляющие. Выбран элемент — положение и размер
     с опорной точкой, поворот, свои настройки вида (масштаб карты, текст надписи, файл картинки…), рамка, фон,
     непрозрачность, скрыть и закрепить. Выбрано несколько — подсказка про выравнивание. Правки уходят событиями.
     У карты — «Вид» (#119): вид проекта с рамкой на карте задаёт слои, место и масштаб блока («Вписать» или «Заполнить»,
     круглый масштаб), «Блок по рамке» подгоняет высоту блока под пропорции рамки. Масштаб, заданный числом, меняет размер
     рамки на карте; вид стоит на нескольких картах — подсказка и «Отдельный вид» (копия вида только для этого блока). -->
<script setup>
import { ref, computed } from "vue";
import NumField from "./NumField.vue";
import { blockFromView, blockHeightFor, frameLabel } from "../viewframes.js";
import { FORMATS, FORMAT_T, KINDS, SCALES, FONTS, REFS, refPos, fromRef, fmtScale, fmtM, groundSize, label, linkedScale } from "./model.js";

const props = defineProps({ sheet: Object, sel: Array, hasMaps: Boolean, views: { type: Array, default: () => [] } });
const emit = defineEmits(["patch", "format", "set", "act"]);
const ref0 = ref("tl");
const b = computed(() => props.sel.length === 1 ? props.sel[0] : null);
const maps = computed(() => props.sheet.blocks.filter(x => x.kind === "map"));
const p = (patch) => emit("patch", b.value.id, patch);
const vw = computed(() => b.value?.view && props.views.find(v => v.id === b.value.view));
const linked = computed(() => !!vw.value?.frame);       // место и масштаб блока — из рамки вида
// выбрать вид: блок сразу встаёт по рамке вида; «Текущая карта» — блок отвязан, слои — как на карте
function setView(id) {
  const v = props.views.find(x => x.id === id);
  p(v ? { view: id, ...(blockFromView(b.value, v) || {}) } : { view: undefined });
}
const pos = (i, v) => { const [x, y] = refPos(b.value, ref0.value); p(fromRef(b.value, ref0.value, i ? x : v, i ? v : y)); };
const sub = (key, k, v) => p({ [key]: { ...(b.value[key] || {}), [k]: v } });
const gridSet = (k, v) => emit("set", { grid: { ...(props.sheet.grid || {}), [k]: v } });
const snapSet = (k, v) => emit("set", { snap: { ...(props.sheet.snap || {}), [k]: v } });
const guides = computed(() => [...(props.sheet.guides?.x || []).map((v, i) => ({ ax: "x", i, v })), ...(props.sheet.guides?.y || []).map((v, i) => ({ ax: "y", i, v }))]);
function guideSet(ax, i, v) { const g = { x: [...(props.sheet.guides?.x || [])], y: [...(props.sheet.guides?.y || [])] }; if (v == null) g[ax].splice(i, 1); else g[ax][i] = v; emit("set", { guides: g }); }
function file(e) {
  const f = e.target.files?.[0]; if (!f) return;
  const r = new FileReader(); r.onload = () => p({ src: r.result, file: f.name }); r.readAsDataURL(f);
}
const legendRows = computed(() => (b.value?.items || []).map(x => x.t).join("\n"));
function legendText(v) { const t = v.split("\n"), old = b.value.items || []; p({ items: t.filter(s => s.trim()).map((s, i) => ({ ...(old[i] || { s: "fill", c: "#6b7280", f: "#e5e7eb" }), t: s.trim() })) }); }
</script>

<template>
  <div class="pp">
    <!-- лист -->
    <template v-if="!sel.length">
      <div class="pp-h">Лист</div>
      <label class="pp-f">Название<input :value="sheet.title" @change="emit('set', { title: $event.target.value })"></label>
      <div class="pp-2">
        <label class="pp-f">Формат<select :value="sheet.format" @change="emit('format', { format: $event.target.value })" aria-label="Формат листа">
          <option v-for="(_, f) in FORMATS" :key="f" :value="f">{{ FORMAT_T[f] }}</option></select></label>
        <label class="pp-f">Ориентация<select :value="sheet.orient" @change="emit('format', { orient: $event.target.value })" aria-label="Ориентация листа">
          <option value="L">альбомная</option><option value="P">книжная</option></select></label>
      </div>
      <label class="tg"><input type="checkbox" :checked="sheet.stamp !== false" @change="emit('format', { stamp: $event.target.checked })"><i></i>Рамка и штамп по ГОСТ</label>
      <div class="pp-h">Сетка и привязки</div>
      <label class="pp-f">Шаг сетки, мм<NumField :model-value="sheet.grid?.step || 5" :min="1" :max="100" :step="1" :digits="1" label="Шаг сетки" @update:model-value="gridSet('step', $event)" /></label>
      <label class="tg"><input type="checkbox" :checked="!!sheet.grid?.show" @change="gridSet('show', $event.target.checked)"><i></i>Показать сетку</label>
      <label class="tg"><input type="checkbox" :checked="!!sheet.grid?.snap" @change="gridSet('snap', $event.target.checked)"><i></i>Привязка к сетке</label>
      <label class="tg"><input type="checkbox" :checked="sheet.snap?.guides !== false" @change="snapSet('guides', $event.target.checked)"><i></i>Привязка к направляющим</label>
      <label class="tg"><input type="checkbox" :checked="sheet.snap?.items !== false" @change="snapSet('items', $event.target.checked)"><i></i>Привязка к элементам и рамке</label>
      <div class="pp-h">Направляющие</div>
      <div v-if="!guides.length" class="pp-note">Тяните от линейки сверху или слева, чтобы поставить направляющую. Обратно на линейку — убрать.</div>
      <div v-for="g in guides" :key="g.ax + g.i" class="pp-g">
        <span>{{ g.ax === 'x' ? 'Вертикальная, X' : 'Горизонтальная, Y' }}</span>
        <NumField :model-value="g.v" :step="1" :digits="1" :label="'Направляющая ' + g.ax" @update:model-value="guideSet(g.ax, g.i, $event)" />
        <button class="pp-x" title="Убрать" aria-label="Убрать направляющую" @click="guideSet(g.ax, g.i, null)">×</button>
      </div>
      <button v-if="guides.length" class="pp-btn" @click="emit('set', { guides: { x: [], y: [] } })">Убрать все направляющие</button>
    </template>

    <!-- несколько элементов -->
    <template v-else-if="!b">
      <div class="pp-h">Выбрано элементов: {{ sel.length }}</div>
      <div class="pp-note">Выровнять, распределить, сделать одного размера, поменять порядок — кнопки «Упорядочить» на ленте. Тянуть — двигаются все вместе.</div>
      <div class="pp-list">{{ sel.map(label).join(", ") }}</div>
    </template>

    <!-- один элемент -->
    <template v-else>
      <div class="pp-cap">{{ KINDS[b.kind] }}</div>
      <input class="pp-name" :value="label(b, sheet.blocks)" aria-label="Имя элемента" @change="p({ name: $event.target.value.trim() || undefined })">

      <div class="pp-h">Положение и размер</div>
      <div class="pp-ref">
        <div class="rp" role="radiogroup" aria-label="Опорная точка">
          <button v-for="r in REFS" :key="r" :class="{ on: ref0 === r }" role="radio" :aria-checked="ref0 === r" :title="'Опорная точка: ' + r" @click="ref0 = r"></button>
        </div>
        <div class="pp-2 grow">
          <label class="pp-f">X, мм<NumField :model-value="refPos(b, ref0)[0]" label="X" @update:model-value="pos(0, $event)" /></label>
          <label class="pp-f">Y, мм<NumField :model-value="refPos(b, ref0)[1]" label="Y" @update:model-value="pos(1, $event)" /></label>
        </div>
      </div>
      <div class="pp-2">
        <label class="pp-f">Ширина, мм<NumField :model-value="b.w" :min="1" label="Ширина" @update:model-value="p({ w: $event })" /></label>
        <label class="pp-f">Высота, мм<NumField :model-value="b.h" :min="1" label="Высота" @update:model-value="p({ h: $event })" /></label>
      </div>
      <label class="pp-f">Поворот, °<NumField :model-value="b.rotation || 0" :min="-360" :max="360" :step="15" :digits="1" label="Поворот" @update:model-value="p({ rotation: $event })" /></label>

      <template v-if="b.kind === 'map'">
        <div class="pp-h">Карта</div>
        <label class="pp-f">Вид<select :value="b.view || ''" @change="setView($event.target.value)">
          <option value="">Текущая карта</option>
          <option v-for="v in views" :key="v.id" :value="v.id">{{ v.name }}{{ v.frame ? '' : ' (без рамки)' }}</option></select></label>
        <div v-if="!views.length" class="pp-note">Видов пока нет: сохраните вид в окне «Виды» и нарисуйте ему рамку на карте — блок встанет по ней.</div>
        <template v-if="vw">
          <div class="pp-note">{{ vw.frame ? `Рамка вида на карте: ${frameLabel('', vw.frame).slice(3)}. Двигайте и растягивайте её на карте — блок следует за ней.` : 'У вида нет рамки: слои — из вида, место — своё. Нарисуйте рамку в окне «Виды».' }}</div>
          <template v-if="linked">
            <label class="pp-f">Рамка в блоке<select :value="b.fit || 'fit'" @change="p({ fit: $event.target.value })">
              <option value="fit">Вписать — рамка видна целиком</option><option value="fill">Заполнить — блок закрыт целиком</option></select></label>
            <label class="tg"><input type="checkbox" :checked="b.round !== false" @change="p({ round: $event.target.checked })"><i></i>Круглый масштаб (1:2 000, 1:2 500…)</label>
            <label class="pp-f">Масштаб<select :value="SCALES.includes(b.scale) ? b.scale : ''" @change="$event.target.value && emit('act', 'scale', [+$event.target.value])">
              <option v-if="!SCALES.includes(b.scale)" value="">{{ b.scale ? fmtScale(b.scale) : 'не задан' }}</option>
              <option v-for="s in SCALES" :key="s" :value="s">{{ fmtScale(s) }}</option></select></label>
            <label class="pp-f">Свой масштаб, 1:<NumField :model-value="b.scale" :min="100" :step="100" :digits="0" label="Масштаб" @update:model-value="emit('act', 'scale', [$event])" /></label>
            <div class="pp-note">Масштаб меняет размер рамки вида на карте, середина остаётся. Растянули рамку на карте — масштаб считается по ней.</div>
            <div v-if="vw.on > 1" class="pp-note pp-warn">Вид стоит на картах: {{ vw.on }} ({{ vw.sheets.join(', ') }}). Сдвиг и масштаб меняют их все.</div>
            <button class="pp-btn" title="Высота блока — под пропорции рамки вида, ширина та же" @click="p({ h: blockHeightFor(b, vw.frame) })">Блок по рамке</button>
            <button class="pp-btn" :disabled="!hasMaps" title="Показать рамку вида на карте" @click="emit('act', 'view:show')">Рамка на карте</button>
            <button class="pp-btn" :disabled="!hasMaps" title="Копия вида со своей рамкой — только для этой карты, другие листы не меняются" @click="emit('act', 'view:own')">Отдельный вид</button>
          </template>
        </template>
        <label class="pp-f">Подложка<select :value="b.basemap || 'none'" @change="p({ basemap: $event.target.value })">
          <option value="none">без подложки</option><option value="light">светлая карта</option><option value="sat">снимок</option></select></label>
        <template v-if="!linked">
        <label class="pp-f">Масштаб<select :value="SCALES.includes(b.scale) ? b.scale : ''" @change="$event.target.value && p({ scale: +$event.target.value })">
          <option v-if="!SCALES.includes(b.scale)" value="">{{ b.scale ? fmtScale(b.scale) : 'не задан' }}</option>
          <option v-for="s in SCALES" :key="s" :value="s">{{ fmtScale(s) }}</option></select></label>
        <label class="pp-f">Свой масштаб, 1:<NumField :model-value="b.scale" :min="1" :step="100" :digits="0" label="Масштаб" @update:model-value="p({ scale: $event })" /></label>
        <div v-if="b.scale > 0" class="pp-note">На местности: {{ groundSize(b).map(fmtM).join(' × ') }}. Размер рамки меняет охват, масштаб остаётся.</div>
        <button class="pp-btn" :disabled="!hasMaps" title="Середина и масштаб — как сейчас в окне «Карта»" @click="emit('act', 'map:here')">Как на карте</button>
        <div class="pp-note">{{ b.center ? 'Сдвинуть карту в рамке — инструмент «Сдвиг карты» на ленте (C), колесо над картой меняет масштаб.' : 'Место карты не задано: выберите вид или нажмите «Как на карте».' }}</div>
        </template>
      </template>

      <template v-if="b.kind === 'text'">
        <div class="pp-h">Надпись</div>
        <label class="pp-f">Текст<textarea rows="3" :value="b.text" @change="p({ text: $event.target.value })"></textarea></label>
        <div class="pp-2">
          <label class="pp-f">Шрифт<select :value="b.font || 'PT Sans'" @change="p({ font: $event.target.value })"><option v-for="f in FONTS" :key="f">{{ f }}</option></select></label>
          <label class="pp-f">Кегль, пт<NumField :model-value="b.size" :min="2" :max="200" :step="1" :digits="1" label="Кегль" @update:model-value="p({ size: $event })" /></label>
        </div>
        <div class="pp-row">
          <button class="pp-seg" :class="{ on: b.bold }" title="Полужирный" @click="p({ bold: !b.bold })"><b>Ж</b></button>
          <button class="pp-seg" :class="{ on: b.italic }" title="Курсив" @click="p({ italic: !b.italic })"><i>К</i></button>
          <span class="pp-sp"></span>
          <button v-for="[v, t] in [['left', 'влево'], ['center', 'по центру'], ['right', 'вправо']]" :key="v" class="pp-seg" :class="{ on: (b.align || 'left') === v }" :title="'Выключка ' + t" @click="p({ align: v })">{{ t }}</button>
        </div>
        <label class="pp-f">Цвет<input type="color" :value="b.color || '#1a1a1a'" @input="p({ color: $event.target.value })"></label>
      </template>

      <template v-if="b.kind === 'legend'">
        <div class="pp-h">Легенда</div>
        <label class="pp-f">Заголовок<input :value="b.title" @change="p({ title: $event.target.value })"></label>
        <label class="pp-f">Строки (по одной в строке)<textarea rows="5" :value="legendRows" @change="legendText($event.target.value)"></textarea></label>
        <button class="pp-btn" :disabled="!hasMaps" title="Строки — видимые слои проекта, сверху вниз, с их цветами" @click="emit('act', 'legend:layers')">Из слоёв карты</button>
      </template>

      <template v-if="b.kind === 'table'">
        <div class="pp-h">Таблица</div>
        <label class="pp-f">Заголовок<input :value="b.title" @change="p({ title: $event.target.value })"></label>
        <div class="pp-2">
          <label class="pp-f">Строк<NumField :model-value="b.rows" :min="1" :max="60" :digits="0" label="Строк" @update:model-value="p({ rows: $event })" /></label>
          <label class="pp-f">Столбцов<NumField :model-value="b.cols" :min="1" :max="12" :digits="0" label="Столбцов" @update:model-value="p({ cols: $event })" /></label>
        </div>
      </template>

      <template v-if="b.kind === 'picture'">
        <div class="pp-h">Картинка</div>
        <label class="pp-btn file">Выбрать файл…<input type="file" accept="image/png,image/jpeg" @change="file"></label>
        <div v-if="b.file" class="pp-note">{{ b.file }}</div>
      </template>

      <template v-if="b.kind === 'scalebar' || b.kind === 'north'">
        <div class="pp-h">{{ KINDS[b.kind] }}</div>
        <label class="pp-f">По карте<select :value="b.map || ''" @change="p({ map: $event.target.value })">
          <option value="">первая карта листа</option><option v-for="m in maps" :key="m.id" :value="m.id">{{ label(m, sheet.blocks) }}</option></select></label>
        <div v-if="b.kind === 'scalebar'" class="pp-note">Масштаб {{ fmtScale(linkedScale(b, sheet)) }} — берётся у карты.</div>
      </template>

      <template v-if="b.kind === 'line'">
        <div class="pp-h">Линия</div>
        <label class="tg"><input type="checkbox" :checked="!!b.arrow" @change="p({ arrow: $event.target.checked })"><i></i>Стрелка на конце</label>
      </template>

      <div class="pp-h">Оформление</div>
      <label class="tg"><input type="checkbox" :checked="!!b.frame?.on" @change="sub('frame', 'on', $event.target.checked)"><i></i>{{ b.kind === 'line' ? 'Линия видна' : 'Рамка' }}</label>
      <div v-if="b.frame?.on" class="pp-2">
        <label class="pp-f">Цвет<input type="color" :value="b.frame.color || '#1a1a1a'" @input="sub('frame', 'color', $event.target.value)"></label>
        <label class="pp-f">Толщина, мм<NumField :model-value="b.frame.width || .25" :min=".05" :max="5" :step=".05" label="Толщина" @update:model-value="sub('frame', 'width', $event)" /></label>
      </div>
      <template v-if="b.kind !== 'line'">
        <label class="tg"><input type="checkbox" :checked="!!b.bg?.on" @change="sub('bg', 'on', $event.target.checked)"><i></i>Фон</label>
        <label v-if="b.bg?.on" class="pp-f">Цвет фона<input type="color" :value="b.bg.color || '#ffffff'" @input="sub('bg', 'color', $event.target.value)"></label>
      </template>
      <label class="pp-f">Непрозрачность, {{ Math.round((b.opacity ?? 1) * 100) }} %<input type="range" min="0" max="100" :value="Math.round((b.opacity ?? 1) * 100)" @change="p({ opacity: +$event.target.value / 100 })"></label>
      <label class="tg"><input type="checkbox" :checked="!!b.hidden" @change="p({ hidden: $event.target.checked })"><i></i>Скрыть на листе</label>
      <label class="tg"><input type="checkbox" :checked="!!b.locked" @change="p({ locked: $event.target.checked })"><i></i>Закрепить (не двигается мышью)</label>
      <button class="pp-btn danger" @click="emit('act', 'del')">Удалить элемент</button>
    </template>
  </div>
</template>

<style scoped>
.pp { padding: 10px 12px 16px; display: flex; flex-direction: column; gap: 8px; }
.pp-h { font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--g-mute); margin-top: 8px; }
.pp-cap { font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--g-mute); }
.pp-name { font: inherit; font-weight: 600; font-size: 14px; border: 1px solid transparent; border-radius: 4px; padding: 2px 4px; margin: 0 -5px; background: none; }
.pp-name:hover { border-color: var(--g-line-strong); }
.pp-name:focus { border-color: var(--g-accent); outline: none; background: var(--g-panel); }
.pp-f { display: flex; flex-direction: column; gap: 3px; font-weight: 500; }
.pp-2 { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px; }
.pp-2.grow { flex: 1; }
.pp-ref { display: flex; gap: 10px; align-items: flex-end; }
.pp-row { display: flex; gap: 4px; align-items: center; }
.pp-sp { flex: 1; }
.pp-note { color: var(--g-mute); font-size: 12px; line-height: 1.4; }
.pp-warn { color: #8a5a00; }
.pp-list { line-height: 1.5; }
select, input:not([type]), textarea { font: inherit; border: 1px solid var(--g-line-strong); border-radius: 5px; padding: 3px 8px; background: var(--g-panel); color: inherit; min-width: 0; width: 100%; box-sizing: border-box; height: 26px; }
textarea { height: auto; resize: vertical; padding: 4px 8px; }
select:focus, input:not([type]):focus, textarea:focus { border-color: var(--g-accent); outline: none; box-shadow: 0 0 0 2px var(--g-ring); }
input[type=color] { width: 30px; height: 24px; padding: 1px; border: 1px solid var(--g-line-strong); border-radius: 4px; background: var(--g-panel); }
input[type=range] { accent-color: var(--g-accent); width: 100%; }
.pp-g { display: grid; grid-template-columns: 1fr 96px 22px; gap: 6px; align-items: center; font-size: 12px; }
.pp-x { border: 0; background: none; color: var(--g-mute); font-size: 16px; cursor: pointer; padding: 0; }
.pp-x:hover { color: var(--g-warn); }
.pp-btn { align-self: flex-start; font: inherit; color: inherit; padding: 4px 10px; border: 1px solid var(--g-line-strong); border-radius: 5px; background: var(--g-panel); cursor: pointer; margin-top: 4px; }
.pp-btn:hover:not(:disabled) { border-color: var(--g-accent); color: var(--g-accent); }
.pp-btn:disabled { opacity: .45; cursor: default; }
.pp-btn.danger { color: var(--g-warn); }
.pp-btn.file { position: relative; overflow: hidden; }
.pp-btn.file input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.pp-seg { font: inherit; font-size: 12px; min-width: 26px; height: 24px; padding: 0 6px; border: 1px solid var(--g-line-strong); border-radius: 4px; background: var(--g-panel); cursor: pointer; }
.pp-seg.on { background: var(--g-sel); border-color: var(--g-sel-line); color: var(--g-accent); }
/* переключатель как в образце: синяя «таблетка» */
.tg { display: flex; align-items: center; gap: 8px; cursor: pointer; user-select: none; }
.tg input { position: absolute; opacity: 0; pointer-events: none; }
.tg i { width: 26px; height: 15px; border-radius: 8px; background: #c9ced6; position: relative; flex: none; transition: background .15s; }
.tg i::after { content: ""; position: absolute; left: 2px; top: 2px; width: 11px; height: 11px; border-radius: 50%; background: var(--g-panel); transition: left .15s; }
.tg input:checked + i { background: var(--g-accent); }
.tg input:checked + i::after { left: 13px; }
.tg input:focus-visible + i { box-shadow: 0 0 0 2px var(--g-ring); }
/* опорная точка: 3 × 3 */
.rp { display: grid; grid-template-columns: repeat(3, 12px); gap: 3px; padding: 4px; border: 1px solid var(--g-line-strong); border-radius: 5px; margin-bottom: 1px; }
.rp button { width: 12px; height: 12px; border: 1px solid #9aa3ae; border-radius: 2px; background: var(--g-panel); padding: 0; cursor: pointer; }
.rp button.on { background: var(--g-accent); border-color: var(--g-accent); }
</style>
