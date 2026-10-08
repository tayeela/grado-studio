<!-- ГРАДО 2 · редактор раскладки листа на Konva (шаг 2 плана замен, 08.10.2026): лист формата А4–А0 с рамкой и штампом
     по ГОСТ, на нём блоки — карта (видовое окно с масштабом), легенда, надпись, стрелка севера, масштабная линейка.
     Блок выбирается щелчком, тянется мышью (встаёт к краям и серединам рамки, штампа и других блоков — web/snap.js),
     меняет размер за ручки; стрелки — 0,5 мм, Shift — 5 мм; Delete — убрать; Ctrl+Z / Ctrl+Shift+Z — отмена и возврат;
     колесо — крупнее и мельче, перетаскивание пустого места — сдвиг листа. Модель листа — model.js (v-model),
     штамп — stamp.js. Компонент Vue 3 без глобальных переменных: встраивается в будущий каркас интерфейса. -->
<script setup>
import { onBeforeUnmount, onMounted, ref, computed, watch } from "vue";
import Konva from "konva";
import "../../../web/snap.js";                      // общая привязка с нынешним макетом листа: кладёт Snap в globalThis
import { FORMATS, FORMAT_T, KINDS, SCALES, PT, pageSize, frameRect, stampRect, newBlock, groundSize, scalebarStep,
  fmtM, fmtScale, toBox, snapTargets, problems, reformat, mainScale } from "./model.js";
import { stampOps } from "./stamp.js";

const props = defineProps({
  modelValue: { type: Object, required: true },     // лист: { format, orient, stamp, title, blocks }
  meta: { type: Object, default: () => ({}) },       // поля штампа альбома: object, code, stage, org
  page: { type: Object, default: () => ({}) },       // page_no, page_total
});
const emit = defineEmits(["update:modelValue"]);

const clone = x => JSON.parse(JSON.stringify(x));
const sheet = ref(clone(props.modelValue));
const sel = ref(null);
const zoom = ref(1);
const host = ref(null);
const hist = { u: [], r: [] };
const canUndo = ref(false), canRedo = ref(false);
let lastOut = null;

const Snap = globalThis.Snap;
const INK = "#1a1a1a", BLUE = "#1a5fb4", GUIDE = "#e0108a";
let stage, paper, blocks, guides, tr, k = 1;

const selBlock = computed(() => sheet.value.blocks.find(b => b.id === sel.value) || null);
const issues = computed(() => problems(sheet.value));
const ground = computed(() => selBlock.value?.kind === "map" && selBlock.value.scale > 0 ? groundSize(selBlock.value).map(fmtM).join(" × ") : "");

/* ---------- правка листа: история и выдача наружу ---------- */
function out() { lastOut = JSON.stringify(sheet.value); emit("update:modelValue", JSON.parse(lastOut)); }
function commit(fn) {
  hist.u.push(JSON.stringify(sheet.value)); if (hist.u.length > 100) hist.u.shift(); hist.r = [];
  fn(sheet.value); syncHist(); draw(); out();
}
function step(dir) {
  const from = dir < 0 ? hist.u : hist.r, to = dir < 0 ? hist.r : hist.u; if (!from.length) return;
  to.push(JSON.stringify(sheet.value)); sheet.value = JSON.parse(from.pop());
  if (sel.value && !selBlock.value) sel.value = null;
  syncHist(); draw(); out();
}
const syncHist = () => { canUndo.value = hist.u.length > 0; canRedo.value = hist.r.length > 0; };
const patchSel = (patch) => commit(s => Object.assign(s.blocks.find(b => b.id === sel.value), patch));
watch(() => props.modelValue, v => { if (JSON.stringify(v) !== lastOut) { sheet.value = clone(v); draw(); } }, { deep: true });

/* ---------- вид: масштаб экрана и подгонка листа ---------- */
function fit() {
  if (!stage) return;
  const [pw, ph] = pageSize(sheet.value), W = stage.width(), H = stage.height();
  k = Math.max(.2, Math.min((W - 48) / pw, (H - 48) / ph));
  stage.scale({ x: k, y: k }); stage.position({ x: (W - pw * k) / 2, y: (H - ph * k) / 2 });
  zoom.value = k; draw();
}
function zoomAt(f, at) {
  const p = at || { x: stage.width() / 2, y: stage.height() / 2 }, old = k;
  k = Math.max(.2, Math.min(40, k * f));
  const o = stage.position(), mx = (p.x - o.x) / old, my = (p.y - o.y) / old;
  stage.scale({ x: k, y: k }); stage.position({ x: p.x - mx * k, y: p.y - my * k }); zoom.value = k; draw();
}

/* ---------- рисование: бумага, рамка, штамп, блоки ---------- */
const px = v => v / k;                                // толщина в пикселях экрана → мм листа
function drawPaper() {
  paper.destroyChildren();
  const s = sheet.value, [w, h] = pageSize(s), f = frameRect(s);
  paper.add(new Konva.Rect({ x: 0, y: 0, width: w, height: h, fill: "#fff", shadowColor: "#000", shadowBlur: 12, shadowOpacity: .18, shadowOffset: { x: 0, y: 2 }, listening: false }));
  paper.add(new Konva.Rect({ x: f.x, y: f.y, width: f.w, height: f.h, stroke: INK, strokeWidth: s.stamp === false ? .35 : .7, listening: false }));
  const st = stampOps(s, props.meta, props.page);
  if (st) {
    st.lines.forEach(l => paper.add(new Konva.Line({ points: l.pts, stroke: INK, strokeWidth: Math.max(l.w, .1), listening: false })));
    // в печати y — линия шрифта; у Konva — верх строки: поднимаем на высоту прописной
    st.texts.forEach(t => t.text && paper.add(new Konva.Text({ x: t.x - 60, y: t.y - t.size * .8, width: 120, align: "center", text: t.text,
      fontSize: t.size, fontFamily: "PT Sans, system-ui, sans-serif", fill: INK, wrap: "none", ellipsis: true, listening: false })));
  }
}
function blockNode(b) {
  const g = new Konva.Group({ id: b.id, x: b.x, y: b.y, draggable: true, name: "block" });
  const cap = (text, size) => new Konva.Text({ x: 0, y: 0, width: b.w, height: b.h, align: "center", verticalAlign: "middle",
    text, fontSize: size, fontFamily: "PT Sans, system-ui, sans-serif", fill: "#56606e", listening: false });
  if (b.kind === "map") {
    g.add(new Konva.Rect({ width: b.w, height: b.h, fill: "#eef3ea", stroke: "#4a6a3a", strokeWidth: .35 }));
    g.add(cap(`Карта · ${b.scale > 0 ? fmtScale(b.scale) : "масштаб не задан"}\n${b.scale > 0 ? groundSize(b).map(fmtM).join(" × ") + " на местности" : ""}`, Math.min(6, b.h / 6)));
  } else if (b.kind === "legend") {
    g.add(new Konva.Rect({ width: b.w, height: b.h, fill: "#fafafa", stroke: "#8a94a3", strokeWidth: .3, dash: [2, 1.2] }));
    g.add(cap("Легенда", Math.min(5, b.w / 8)));
  } else if (b.kind === "text") {
    g.add(new Konva.Rect({ width: b.w, height: b.h, fill: "rgba(255,255,255,0.01)" }));
    g.add(new Konva.Text({ width: b.w, text: b.text || "", fontSize: (b.size || 12) * PT, fontFamily: "PT Sans, system-ui, sans-serif", fill: b.color || INK, listening: false }));
  } else if (b.kind === "north") {
    g.add(new Konva.Rect({ width: b.w, height: b.h, fill: "rgba(255,255,255,0.01)" }));
    g.add(new Konva.Line({ points: [b.w / 2, b.h * .28, b.w * .85, b.h, b.w / 2, b.h * .8, b.w * .15, b.h], closed: true, fill: INK, listening: false }));
    g.add(new Konva.Text({ x: 0, y: 0, width: b.w, align: "center", text: "С", fontSize: b.h * .26, fontStyle: "bold", fontFamily: "PT Sans, system-ui, sans-serif", fill: INK, listening: false }));
  } else if (b.kind === "scalebar") {
    const sc = b.scale || mainScale(sheet.value) || 2000, stepM = scalebarStep({ ...b, scale: sc }), seg = stepM * 1000 / sc, bh = Math.min(2, b.h / 3);
    g.add(new Konva.Rect({ width: b.w, height: b.h, fill: "rgba(255,255,255,0.01)" }));
    for (let i = 0; i < 4; i++) g.add(new Konva.Rect({ x: i * seg, y: b.h - bh - 3.2, width: seg, height: bh, fill: i % 2 ? "#fff" : INK, stroke: INK, strokeWidth: .2, listening: false }));
    for (let i = 0; i <= 4; i += 2) g.add(new Konva.Text({ x: i * seg - 10, y: b.h - 2.6, width: 20, align: "center", text: i ? fmtM(stepM * i) : "0", fontSize: 2.2, fill: INK, listening: false }));
    g.add(new Konva.Text({ x: 0, y: 0, text: fmtScale(sc), fontSize: 2.4, fill: INK, listening: false }));
  }
  // выбор не перерисовывает лист: иначе узел, который начали тянуть, пропал бы из-под мыши
  g.on("mousedown touchstart", () => { if (sel.value !== b.id) { sel.value = b.id; attach(g, b); } });
  g.on("dragmove", e => dragSnap(g, b, e.evt?.altKey));
  g.on("dragend", () => { guides.destroyChildren(); guides.batchDraw(); const p = g.position(); commit(s => Object.assign(s.blocks.find(x => x.id === b.id), { x: +p.x.toFixed(2), y: +p.y.toFixed(2) })); });
  g.on("transformend", () => {
    const sx = g.scaleX(), sy = g.scaleY(), p = g.position(); g.scale({ x: 1, y: 1 });
    commit(s => Object.assign(s.blocks.find(x => x.id === b.id), { x: +p.x.toFixed(2), y: +p.y.toFixed(2), w: +(b.w * sx).toFixed(2), h: +(b.h * sy).toFixed(2) }));
  });
  return g;
}
// привязка при перетаскивании: края и середины к рамке, штампу, листу и другим блокам; Alt — без привязки
function dragSnap(g, b, free) {
  guides.destroyChildren();
  const p = g.position(), box = toBox({ x: p.x, y: p.y, w: b.w, h: b.h });
  if (!Snap || free) { guides.batchDraw(); return; }
  const s = Snap.snap(box, snapTargets(sheet.value, b.id), Snap.ZONE_PX / k);
  g.position({ x: p.x + s.dx, y: p.y + s.dy });
  s.guides.forEach(({ a, b: e }) => guides.add(new Konva.Line({ points: [a[0], a[1], e[0], e[1]], stroke: GUIDE, strokeWidth: px(1), listening: false })));
  guides.batchDraw();
}
function draw() {
  if (!stage) return;
  tr.nodes([]); tr.remove();                          // ручки живут дольше блоков: снять до очистки слоя, иначе их уничтожит destroyChildren
  drawPaper(); blocks.destroyChildren();
  sheet.value.blocks.forEach(b => blocks.add(blockNode(b)));
  blocks.add(tr);
  const n = sel.value && blocks.findOne("#" + sel.value);
  if (n) attach(n, selBlock.value);
  stage.batchDraw();
}
// ручки размера на выбранном блоке; у стрелки севера пропорции держатся
function attach(node, b) { tr.nodes([node]); tr.keepRatio(b?.kind === "north"); tr.moveToTop(); blocks.batchDraw(); }

/* ---------- клавиши и действия панели ---------- */
function onKey(e) {
  const mod = e.ctrlKey || e.metaKey;
  if (mod && e.code === "KeyZ") { e.preventDefault(); step(e.shiftKey ? 1 : -1); return; }
  if (mod && e.code === "KeyY") { e.preventDefault(); step(1); return; }
  if (e.key === "Escape") { sel.value = null; draw(); return; }
  if (!selBlock.value) return;
  const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
  if (d) { e.preventDefault(); const st = e.shiftKey ? 5 : .5, b = selBlock.value; patchSel({ x: +(b.x + d[0] * st).toFixed(2), y: +(b.y + d[1] * st).toFixed(2) }); }
  if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); remove(); }
}
function add(kind) { const b = newBlock(kind, sheet.value); commit(s => s.blocks.push(b)); sel.value = b.id; draw(); host.value?.focus(); }
function remove() { const id = sel.value; if (!id) return; sel.value = null; commit(s => { s.blocks = s.blocks.filter(b => b.id !== id); }); }
function setFormat(patch) { hist.u.push(JSON.stringify(sheet.value)); hist.r = []; sheet.value = reformat(sheet.value, patch); syncHist(); out(); fit(); }
function num(key, v) { const x = parseFloat(String(v).replace(",", ".")); if (Number.isFinite(x)) patchSel({ [key]: key === "w" || key === "h" ? Math.max(1, x) : x }); }
function pick(id) { sel.value = id; draw(); }

let ro;
onMounted(() => {
  const el = host.value;
  stage = new Konva.Stage({ container: el, width: el.clientWidth || 800, height: el.clientHeight || 600, draggable: true });
  paper = new Konva.Layer({ listening: false }); blocks = new Konva.Layer(); guides = new Konva.Layer({ listening: false });
  stage.add(paper, blocks, guides);
  tr = new Konva.Transformer({ rotateEnabled: false, flipEnabled: false, anchorSize: 8, borderStroke: BLUE, anchorStroke: BLUE, anchorCornerRadius: 1,
    ignoreStroke: true, boundBoxFunc: (o, n) => (n.width < 8 || n.height < 8 ? o : n) });
  // щелчок по пустому месту снимает выбор; перетаскивание пустого места двигает лист
  stage.on("mousedown touchstart", e => { if (e.target === stage) { sel.value = null; draw(); } el.focus(); });
  stage.on("wheel", e => { e.evt.preventDefault(); zoomAt(e.evt.deltaY < 0 ? 1.12 : 1 / 1.12, stage.getPointerPosition()); });
  ro = new ResizeObserver(() => { stage.size({ width: el.clientWidth, height: el.clientHeight }); fit(); }); ro.observe(el);
  fit();
});
onBeforeUnmount(() => { ro?.disconnect(); stage?.destroy(); });
defineExpose({ fit, undo: () => step(-1), redo: () => step(1) });
</script>

<template>
  <div class="sed">
    <header class="sed-bar">
      <label>Формат <select :value="sheet.format" @change="setFormat({ format: $event.target.value })" aria-label="Формат листа">
        <option v-for="(_, f) in FORMATS" :key="f" :value="f">{{ FORMAT_T[f] }}</option></select></label>
      <label>Ориентация <select :value="sheet.orient" @change="setFormat({ orient: $event.target.value })" aria-label="Ориентация листа">
        <option value="L">альбомная</option><option value="P">книжная</option></select></label>
      <label class="chk"><input type="checkbox" :checked="sheet.stamp !== false" @change="setFormat({ stamp: $event.target.checked })">Штамп по ГОСТ</label>
      <span class="sep"></span>
      <button v-for="(t, kind) in KINDS" :key="kind" @click="add(kind)" :title="`Добавить: ${t.toLowerCase()}`">+ {{ t }}</button>
      <span class="sp"></span>
      <button @click="step(-1)" :disabled="!canUndo" title="Отменить (Ctrl+Z)">Отменить</button>
      <button @click="step(1)" :disabled="!canRedo" title="Вернуть (Ctrl+Shift+Z)">Вернуть</button>
      <button @click="zoomAt(1 / 1.25)" title="Мельче (колесо)">−</button>
      <button @click="fit" title="Лист целиком">{{ Math.round(zoom * 100 / 3.78) }} %</button>
      <button @click="zoomAt(1.25)" title="Крупнее (колесо)">+</button>
    </header>
    <div class="sed-body">
      <div ref="host" class="sed-stage" tabindex="0" @keydown="onKey" aria-label="Лист"></div>
      <aside class="sed-panel">
        <template v-if="selBlock">
          <div class="sect">{{ KINDS[selBlock.kind] }}</div>
          <div class="grid">
            <label>X, мм<input :value="selBlock.x" @change="num('x', $event.target.value)"></label>
            <label>Y, мм<input :value="selBlock.y" @change="num('y', $event.target.value)"></label>
            <label>Ширина, мм<input :value="selBlock.w" @change="num('w', $event.target.value)"></label>
            <label>Высота, мм<input :value="selBlock.h" @change="num('h', $event.target.value)"></label>
          </div>
          <template v-if="selBlock.kind === 'map' || selBlock.kind === 'scalebar'">
            <label>Масштаб<select :value="selBlock.scale || ''" @change="patchSel({ scale: +$event.target.value || undefined })">
              <option v-if="selBlock.kind === 'scalebar'" value="">как у карты</option>
              <option v-for="s in SCALES" :key="s" :value="s">{{ fmtScale(s) }}</option></select></label>
            <div v-if="ground" class="note">На местности: {{ ground }}. Размер карты меняет охват, масштаб остаётся.</div>
          </template>
          <template v-if="selBlock.kind === 'text'">
            <label>Текст<textarea rows="3" :value="selBlock.text" @change="patchSel({ text: $event.target.value })"></textarea></label>
            <label>Кегль, пт<input :value="selBlock.size" @change="num('size', $event.target.value)"></label>
          </template>
          <button class="danger" @click="remove">Убрать с листа</button>
        </template>
        <div v-else class="note">Щёлкните блок на листе, чтобы изменить его место, размер и масштаб. Кнопки сверху добавляют карту, легенду, надпись, стрелку севера и масштабную линейку.</div>
        <div class="sect">Замечания</div>
        <div v-if="!issues.length" class="note">Нет: все блоки внутри рамки и не заходят на штамп.</div>
        <button v-for="(p, i) in issues" :key="i" class="issue" @click="pick(p.id)">{{ p.text }}</button>
        <div class="note hint">Тянуть — сдвинуть (встаёт к краям и серединам, Alt — без привязки); ручки — размер; стрелки — 0,5 мм, Shift — 5 мм; Delete — убрать; колесо — крупнее и мельче; пустое место — сдвиг листа.</div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.sed { --bg: #e9ecf0; --panel: #fff; --line: #d5dae1; --ink: #1a1a1a; --mute: #56606e; --blue: #1a5fb4; --warn: #a3470b;
  display: flex; flex-direction: column; height: 100%; font: 13px "PT Sans", system-ui, sans-serif; color: var(--ink); background: var(--bg); }
.sed-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 6px 10px; background: var(--panel); border-bottom: 1px solid var(--line); }
.sed-bar label { display: flex; align-items: center; gap: 4px; }
.sed-bar .sep { width: 1px; height: 20px; background: var(--line); margin: 0 4px; }
.sed-bar .sp { flex: 1; }
button { font: inherit; padding: 3px 8px; border: 1px solid var(--line); border-radius: 4px; background: #fff; cursor: pointer; }
button:hover:not(:disabled) { border-color: var(--blue); color: var(--blue); }
button:disabled { opacity: .45; cursor: default; }
select, input, textarea { font: inherit; padding: 2px 4px; border: 1px solid var(--line); border-radius: 3px; min-width: 0; }
.sed-body { flex: 1; display: flex; min-height: 0; }
.sed-stage { flex: 1; min-width: 0; outline: none; }
.sed-stage:focus-visible { box-shadow: inset 0 0 0 2px var(--blue); }
.sed-panel { width: 260px; flex: none; overflow: auto; padding: 10px; background: var(--panel); border-left: 1px solid var(--line); display: flex; flex-direction: column; gap: 8px; }
.sed-panel label { display: flex; flex-direction: column; gap: 2px; color: var(--mute); }
.sed-panel .grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 6px; }
.sed-panel input, .sed-panel select, .sed-panel textarea { width: 100%; box-sizing: border-box; }
.sect { font-weight: 700; margin-top: 4px; }
.note { color: var(--mute); line-height: 1.35; }
.hint { margin-top: auto; font-size: 12px; }
.issue { text-align: left; border-color: transparent; color: var(--warn); padding: 2px 0; background: none; }
.danger { align-self: flex-start; color: var(--warn); }
</style>
