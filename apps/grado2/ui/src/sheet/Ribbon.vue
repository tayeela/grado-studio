<!-- ГРАДО 2 · лента инструментов редактора раскладки листа (как панели инструментов «Макета» QGIS): выбор и сдвиг листа,
     добавление элементов, правка, упорядочивание (выравнивание, распределение, порядок, закрепление), вид (сетка,
     привязки, увеличение) и выгрузка. Только кнопки: действия выполняет SheetEditor.vue по событию act.
     Узкое окно (меньше полной ширины ленты, например 1280): «Упорядочить» сворачивается в выпадающие кнопки «Выровнять»,
     «Распределить и размер», «Порядок», «Группа и отражение» — как кнопки-списки на панели «Действия» макета QGIS.
     Каждая кнопка — команда из commands.js (её же можно набрать в командной строке); группы, отражение и «Формат по образцу» —
     с deckcraft (arrange.js). -->
<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from "vue";
import { ChevronDown, MousePointer2, Hand, Map, List, Type, Image, Compass, Ruler, Table, Square, Circle, MoveRight, Undo2, Redo2, Copy,
  ClipboardPaste, CopyPlus, Trash2, AlignStartVertical, AlignCenterVertical, AlignEndVertical, AlignStartHorizontal,
  AlignCenterHorizontal, AlignEndHorizontal, AlignHorizontalDistributeCenter, AlignVerticalDistributeCenter, StretchHorizontal,
  StretchVertical, BringToFront, SendToBack, ArrowUp, ArrowDown, Lock, LockOpen, Grid3x3, Magnet, ZoomIn, ZoomOut, Maximize, Scan,
  FileImage, FileDown, Move, Group, Ungroup, FlipHorizontal2, FlipVertical2, Paintbrush } from "@lucide/vue";

const props = defineProps({ tool: String, hasMaps: Boolean, canUndo: Boolean, canRedo: Boolean, nSel: Number, canPaste: Boolean, grid: Object, anyLocked: Boolean,
  undoT: String, redoT: String, grouped: Boolean });
const emit = defineEmits(["act"]);
const S = 18;                                          // размер значка, px
/* свёрнутая «Упорядочить»: кнопка-список вместо ряда кнопок (id — элементы группы по порядку) */
const FOLD = [
  { id: "m:align", i: AlignStartVertical, t: "Выровнять", ids: ["align:left", "align:hcenter", "align:right", "align:top", "align:vcenter", "align:bottom"] },
  { id: "m:dist", i: AlignHorizontalDistributeCenter, t: "Распределить и размер", ids: ["dist:x", "dist:y", "same:w", "same:h"] },
  { id: "m:order", i: BringToFront, t: "Порядок", ids: ["order:top", "order:up", "order:down", "order:bottom"] },
  { id: "m:group", i: Group, t: "Группа и отражение", ids: ["group", "ungroup", "flip:h", "flip:v"] }];
const rb = ref(null), compact = ref(false);
let fullW = 0, ro = null;
// полная ширина ленты — сумма групп в развёрнутом виде (меряется, пока лента развёрнута; окно могло быть скрыто — тогда 0)
function fit() {
  const el = rb.value; if (!el) return;
  if (!compact.value) { const w = [...el.children].reduce((s, c) => s + c.offsetWidth, 0); if (w) fullW = w + 12; }
  compact.value = !!fullW && el.clientWidth < fullW;
}
onMounted(() => nextTick(() => { fit(); ro = new ResizeObserver(fit); ro.observe(rb.value); }));
onBeforeUnmount(() => ro?.disconnect());
/* ряд группы: в узком окне элементы из FOLD заменяются своей кнопкой-списком (на месте первого из них) */
function row(g) {
  if (!compact.value || g.t !== "Упорядочить") return g.items;
  const out = [];
  for (const it of g.items) {
    const f = FOLD.find(m => m.ids.includes(it.id));
    if (!f) { out.push(it); continue; }
    if (f.ids[0] !== it.id) continue;
    const sub = f.ids.map(id => g.items.find(x => x.id === id));
    out.push({ ...f, menu: sub, off: sub.every(x => x.off) });
  }
  return out;
}
const pick = e => emit("act", e.detail.item.value);

const groups = () => [
  { t: "Выбор", items: [
    { id: "tool:select", i: MousePointer2, t: "Выбор и перемещение элементов (V)", on: props.tool === "select" },
    { id: "tool:pan", i: Hand, t: "Сдвиг листа (пробел или средняя кнопка мыши)", on: props.tool === "pan" },
    { id: "tool:content", i: Move, t: "Сдвиг карты внутри рамки; колесо — масштаб карты (C)", on: props.tool === "content" }] },
  { t: "Добавить", items: [
    { id: "add:map", i: Map, t: "Карта: растяните рамку на листе", on: props.tool === "map" },
    { id: "add:legend", i: List, t: "Легенда", on: props.tool === "legend" },
    { id: "add:text", i: Type, t: "Надпись", on: props.tool === "text" },
    { id: "add:picture", i: Image, t: "Картинка", on: props.tool === "picture" },
    { id: "add:north", i: Compass, t: "Стрелка севера", on: props.tool === "north" },
    { id: "add:scalebar", i: Ruler, t: "Масштабная линейка", on: props.tool === "scalebar" },
    { id: "add:table", i: Table, t: "Таблица", on: props.tool === "table" },
    { id: "add:rect", i: Square, t: "Прямоугольник", on: props.tool === "rect" },
    { id: "add:ellipse", i: Circle, t: "Эллипс", on: props.tool === "ellipse" },
    { id: "add:line", i: MoveRight, t: "Линия со стрелкой", on: props.tool === "line" }] },
  { t: "Правка", items: [
    { id: "undo", i: Undo2, t: props.undoT ? `Отменить: ${props.undoT} (Ctrl+Z)` : "Отменить (Ctrl+Z)", off: !props.canUndo },
    { id: "redo", i: Redo2, t: props.redoT ? `Вернуть: ${props.redoT} (Ctrl+Shift+Z)` : "Вернуть (Ctrl+Shift+Z)", off: !props.canRedo },
    { id: "copy", i: Copy, t: "Копировать (Ctrl+C)", off: !props.nSel },
    { id: "paste", i: ClipboardPaste, t: "Вставить (Ctrl+V)", off: !props.canPaste },
    { id: "dup", i: CopyPlus, t: "Дублировать (Ctrl+D)", off: !props.nSel },
    { id: "del", i: Trash2, t: "Удалить (Delete)", off: !props.nSel },
    { id: "painter", i: Paintbrush, t: "Формат по образцу: выберите образец, затем щёлкайте по элементам (Esc — закончить)", on: props.tool === "painter", off: !props.nSel && props.tool !== "painter" }] },
  { t: "Упорядочить", items: [
    { id: "align:left", i: AlignStartVertical, t: "По левому краю (один элемент — по рамке листа)", off: !props.nSel },
    { id: "align:hcenter", i: AlignCenterVertical, t: "По центру по горизонтали", off: !props.nSel },
    { id: "align:right", i: AlignEndVertical, t: "По правому краю", off: !props.nSel },
    { id: "align:top", i: AlignStartHorizontal, t: "По верхнему краю", off: !props.nSel },
    { id: "align:vcenter", i: AlignCenterHorizontal, t: "По центру по вертикали", off: !props.nSel },
    { id: "align:bottom", i: AlignEndHorizontal, t: "По нижнему краю", off: !props.nSel },
    { id: "dist:x", i: AlignHorizontalDistributeCenter, t: "Распределить по горизонтали (от трёх элементов)", off: props.nSel < 3 },
    { id: "dist:y", i: AlignVerticalDistributeCenter, t: "Распределить по вертикали (от трёх элементов)", off: props.nSel < 3 },
    { id: "same:w", i: StretchHorizontal, t: "Одинаковая ширина (по первому выбранному)", off: props.nSel < 2 },
    { id: "same:h", i: StretchVertical, t: "Одинаковая высота (по первому выбранному)", off: props.nSel < 2 },
    { id: "order:top", i: BringToFront, t: "На передний план", off: !props.nSel },
    { id: "order:up", i: ArrowUp, t: "Выше (Ctrl+])", off: !props.nSel },
    { id: "order:down", i: ArrowDown, t: "Ниже (Ctrl+[)", off: !props.nSel },
    { id: "order:bottom", i: SendToBack, t: "На задний план", off: !props.nSel },
    { id: "group", i: Group, t: "Сгруппировать (Ctrl+G): щелчок выбирает всю группу, Alt+щелчок — один элемент", off: props.nSel < 2 },
    { id: "ungroup", i: Ungroup, t: "Разгруппировать (Ctrl+Shift+G)", off: !props.grouped },
    { id: "flip:h", i: FlipHorizontal2, t: "Отразить слева направо (места и углы; картинка не зеркалится)", off: !props.nSel },
    { id: "flip:v", i: FlipVertical2, t: "Отразить сверху вниз", off: !props.nSel },
    { id: "lock", i: Lock, t: "Закрепить выбранные (Ctrl+L)", off: !props.nSel },
    { id: "unlock", i: LockOpen, t: "Открепить все (Ctrl+Shift+L)", off: !props.anyLocked }] },
  { t: "Вид", items: [
    { id: "grid:show", i: Grid3x3, t: "Показать сетку (Ctrl+')", on: props.grid?.show },
    { id: "grid:snap", i: Magnet, t: "Привязка к сетке", on: props.grid?.snap },
    { id: "zoom:out", i: ZoomOut, t: "Мельче (колесо мыши)" },
    { id: "zoom:in", i: ZoomIn, t: "Крупнее (колесо мыши)" },
    { id: "zoom:fit", i: Maximize, t: "Весь лист (Ctrl+0)" },
    { id: "zoom:sel", i: Scan, t: "Показать выбранное", off: !props.nSel }] },
  { t: "Выгрузка", items: [
    { id: "export:pdf", i: FileDown, t: "Лист в PDF — тем же рендером, что альбом", off: !props.hasMaps },
    { id: "export:png", i: FileImage, t: "Лист картинкой PNG, 300 точек на дюйм" }] },
];
</script>

<template>
  <div ref="rb" class="rb" :class="{ compact }" role="toolbar" aria-label="Инструменты макета">
    <div v-for="g in groups()" :key="g.t" class="rb-g">
      <div class="rb-row">
        <template v-for="it in row(g)" :key="it.id">
        <wa-dropdown v-if="it.menu" placement="bottom-start" @wa-select="pick">
          <button slot="trigger" class="rb-b rb-m" :disabled="it.off" :title="it.t" :aria-label="it.t">
            <component :is="it.i" :size="S" :stroke-width="1.6" /><ChevronDown :size="11" :stroke-width="2" class="rb-c" />
          </button>
          <wa-dropdown-item v-for="x in it.menu" :key="x.id" :value="x.id" :disabled="x.off">
            <component :is="x.i" slot="icon" :size="16" :stroke-width="1.6" />{{ x.t }}</wa-dropdown-item>
        </wa-dropdown>
        <button v-else class="rb-b" :class="{ on: it.on }" :disabled="it.off" :title="it.t" :aria-label="it.t"
          :aria-pressed="it.on === undefined ? undefined : !!it.on" @click="emit('act', it.id)">
          <component :is="it.i" :size="S" :stroke-width="1.6" />
        </button>
        </template>
      </div>
      <div class="rb-t">{{ g.t }}</div>
    </div>
  </div>
</template>

<style scoped>
.rb { display: flex; align-items: stretch; gap: 0; padding: 4px 6px 2px; background: var(--g-panel); border-bottom: 1px solid var(--g-line); overflow-x: auto; }
.rb-g { display: flex; flex-direction: column; align-items: center; padding: 0 8px; border-right: 1px solid var(--g-line); }
.rb-g:last-child { border-right: 0; }
.rb-row { display: flex; gap: 1px; }
.rb-t { font-size: 11px; color: var(--g-mute); margin-top: 1px; white-space: nowrap; }
.rb-b { width: 30px; height: 28px; display: grid; place-items: center; border: 1px solid transparent; border-radius: 5px; background: none; color: var(--g-ink); cursor: pointer; padding: 0; }
.rb-b:hover:not(:disabled) { background: var(--g-hover); }
.rb-b.on { background: var(--g-sel); color: var(--g-accent); border-color: var(--g-sel-line); }
.rb-b:disabled { opacity: .32; cursor: default; }
.rb-m { width: 40px; grid-template-columns: auto auto; gap: 1px; }
.rb-c { color: var(--g-mute); }
.rb-b:focus-visible { outline: 2px solid var(--g-accent); outline-offset: -1px; }
</style>
