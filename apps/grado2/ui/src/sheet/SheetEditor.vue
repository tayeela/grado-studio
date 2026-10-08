<!-- ГРАДО 2 · редактор раскладки листа на Konva — как «Макет» QGIS (шаг 2 плана замен, 08.10.2026). Слева «Элементы»,
     в середине лист с линейками, справа «Свойства», сверху лента, снизу строка состояния (координаты курсора в мм).
     Лист А4–А0 с рамкой и штампом по ГОСТ; элементы: карта (видовое окно с масштабом), легенда, надпись, картинка,
     стрелка севера, масштабная линейка, таблица, прямоугольник, эллипс, линия. Добавление — инструментом ленты и рамкой
     мышью; выбор — щелчком, Shift — добавить, рамкой по пустому месту — несколько; тянуть, ручки размера и поворота;
     привязка к направляющим, элементам, рамке и сетке (web/snap.js); направляющие — тянуть от линейки.
     Клавиши: стрелки 0,5 мм (Shift — 5 мм), Delete, Ctrl+Z/Shift+Z, Ctrl+C/V/D/A, Ctrl+[ ], Ctrl+L, Ctrl+0, пробел — сдвиг листа.
     Карта блока — картинка печати (проп maps, panels/sheetmaps.js): «Как на карте» берёт место окна «Карта», инструмент
     «Сдвиг карты в рамке» двигает её мышью, колесо меняет масштаб; «PDF» печатает лист тем же рендером, что альбом.
     Лист — через v-model (model.js), рисование элементов — draw.js, штамп — stamp.js. -->
<script setup>
import { onBeforeUnmount, onMounted, ref, computed, watch } from "vue";
import Konva from "konva";
import "../../../web/snap.js";                      // общая привязка с нынешним макетом листа: кладёт Snap в globalThis
import { FORMAT_T, KINDS, pageSize, frameRect, newBlock, snapBox, problems, reformat, align, distribute, sameSize, reorder,
  duplicate, bounds, rulerStep, label, moveCenter, nextScale } from "./model.js";
import { stampOps } from "./stamp.js";
import { blockNode, INK } from "./draw.js";
import Ribbon from "./Ribbon.vue";
import ItemsPanel from "./ItemsPanel.vue";
import PropsPanel from "./PropsPanel.vue";

const props = defineProps({
  modelValue: { type: Object, required: true },     // лист: { format, orient, stamp, title, blocks, guides, grid, snap }
  meta: { type: Object, default: () => ({}) },       // поля штампа альбома: object, code, stage, org
  page: { type: Object, default: () => ({}) },       // page_no, page_total
  // карта проекта и печать (panels/sheetmaps.js): image(b, redraw), here(), legend(), pdf(sheet, meta); нет — карта-заглушка
  maps: { type: Object, default: null },
});
const emit = defineEmits(["update:modelValue"]);
const busy = ref("");                                 // строка состояния: идёт печать PDF или она не удалась

const clone = x => JSON.parse(JSON.stringify(x));
// старые листы без направляющих, сетки и настроек привязки получают их по умолчанию
const normalize = s => ({ guides: { x: [], y: [] }, grid: { step: 5, show: false, snap: true }, snap: { guides: true, items: true }, ...s,
  blocks: s.blocks || [] });
const sheet = ref(normalize(clone(props.modelValue)));
const sel = ref([]);                                  // id выбранных элементов, первый — «главный» (по нему одинаковый размер)
const tool = ref("select");
const zoom = ref(1);
const cursor = ref(null);
const host = ref(null), root = ref(null), rulerX = ref(null), rulerY = ref(null);
const hist = { u: [], r: [] };
const canUndo = ref(false), canRedo = ref(false), canPaste = ref(false);
let clip = null, lastOut = null;

const Snap = globalThis.Snap;
const ACCENT = "#1f6feb", GUIDE = "#e5368f", SMART = "#e0108a", PX_MM = 96 / 25.4;
const RULER = 22;
let stage, paper, blocks, guideL, over, tr, k = 1, hovered = false, space = false;

const selBlocks = computed(() => sel.value.map(id => sheet.value.blocks.find(b => b.id === id)).filter(Boolean));
const issues = computed(() => problems(sheet.value));
const anyLocked = computed(() => sheet.value.blocks.some(b => b.locked));
const statusSel = computed(() => !sel.value.length ? "" : sel.value.length === 1 ? `Выбрано: ${label(selBlocks.value[0] || {})}` : `Выбрано элементов: ${sel.value.length}`);
const fmt1 = v => String(+v.toFixed(1)).replace(".", ",");

/* ---------- правка листа: история и выдача наружу ---------- */
function out() { lastOut = JSON.stringify(sheet.value); emit("update:modelValue", JSON.parse(lastOut)); }
function remember() { hist.u.push(JSON.stringify(sheet.value)); if (hist.u.length > 200) hist.u.shift(); hist.r = []; }
function commit(fn) { remember(); fn(sheet.value); syncHist(); draw(); out(); }
function step(dir) {
  const from = dir < 0 ? hist.u : hist.r, to = dir < 0 ? hist.r : hist.u; if (!from.length) return;
  to.push(JSON.stringify(sheet.value)); sheet.value = JSON.parse(from.pop());
  sel.value = sel.value.filter(id => sheet.value.blocks.some(b => b.id === id));
  syncHist(); draw(); out();
}
const syncHist = () => { canUndo.value = hist.u.length > 0; canRedo.value = hist.r.length > 0; };
const blk = (s, id) => s.blocks.find(b => b.id === id);
const patch = (id, p) => commit(s => Object.assign(blk(s, id), p));
const patchMany = map => { if (Object.keys(map).length) commit(s => Object.entries(map).forEach(([id, p]) => Object.assign(blk(s, id), p))); };
watch(() => props.modelValue, v => { if (JSON.stringify(v) !== lastOut) { sheet.value = normalize(clone(v)); sel.value = []; draw(); } }, { deep: true });

/* ---------- вид: масштаб экрана, сдвиг, линейки ---------- */
function setView(nk, ox, oy) { k = nk; stage.scale({ x: k, y: k }); stage.position({ x: ox, y: oy }); zoom.value = k; draw(); }
function fit() {
  if (!stage) return;
  const [pw, ph] = pageSize(sheet.value), W = stage.width(), H = stage.height(), nk = Math.max(.2, Math.min((W - 48) / pw, (H - 48) / ph));
  setView(nk, (W - pw * nk) / 2, (H - ph * nk) / 2);
}
function zoomAt(f, at) {
  const p = at || { x: stage.width() / 2, y: stage.height() / 2 }, o = stage.position(), nk = Math.max(.2, Math.min(60, k * f));
  setView(nk, p.x - (p.x - o.x) / k * nk, p.y - (p.y - o.y) / k * nk);
}
function zoomTo(r) {                                  // показать прямоугольник листа (мм)
  const W = stage.width(), H = stage.height(), nk = Math.max(.2, Math.min(60, Math.min((W - 80) / r.w, (H - 80) / r.h)));
  setView(nk, W / 2 - (r.x + r.w / 2) * nk, H / 2 - (r.y + r.h / 2) * nk);
}
const toMM = (cx, cy) => { const r = host.value.getBoundingClientRect(), o = stage.position(); return { x: (cx - r.left - o.x) / k, y: (cy - r.top - o.y) / k }; };
const pt = () => stage.getRelativePointerPosition();

function drawRulers() {
  const o = stage?.position(); if (!o) return;
  const st = rulerStep(k), minor = st / (String(st)[0] === "2" ? 4 : 5);
  const selB = selBlocks.value.length ? bounds(selBlocks.value) : null;
  [[rulerX.value, "x"], [rulerY.value, "y"]].forEach(([cv, ax]) => {
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
    if (cv.width !== W * dpr || cv.height !== H * dpr) { cv.width = W * dpr; cv.height = H * dpr; }
    const c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, W, H);
    const css = getComputedStyle(root.value), bg = css.getPropertyValue("--g-panel").trim() || "#f7f8fa", ink = css.getPropertyValue("--g-mute").trim() || "#5f6b7a";
    c.fillStyle = bg; c.fillRect(0, 0, W, H);
    const len = ax === "x" ? W : H, off = ax === "x" ? o.x : o.y, at = mm => off + mm * k;
    if (selB) {                                       // выбранное — полоса на линейке, как в QGIS
      const a = at(ax === "x" ? selB.x : selB.y), b = at(ax === "x" ? selB.x + selB.w : selB.y + selB.h);
      c.fillStyle = "rgba(31,111,235,.14)"; ax === "x" ? c.fillRect(a, 0, b - a, H) : c.fillRect(0, a, W, b - a);
    }
    c.strokeStyle = ink; c.fillStyle = ink; c.lineWidth = 1; c.font = "10px Inter, system-ui, sans-serif";
    const from = Math.floor(-off / k / minor) * minor, to = (len - off) / k;
    c.beginPath();
    for (let mm = from; mm <= to; mm += minor) {
      const p = Math.round(at(mm)) + .5, major = Math.abs(mm / st - Math.round(mm / st)) < 1e-6, half = !major && Math.abs(mm / (st / 2) - Math.round(mm / (st / 2))) < 1e-6;
      const t = major ? RULER - 2 : half ? 8 : 4;
      if (ax === "x") { c.moveTo(p, RULER); c.lineTo(p, RULER - t); } else { c.moveTo(RULER, p); c.lineTo(RULER - t, p); }
      if (major) {
        const txt = String(Math.round(mm));
        if (ax === "x") c.fillText(txt, p + 3, 10);
        else { c.save(); c.translate(10, p - 3); c.rotate(-Math.PI / 2); c.fillText(txt, 0, 0); c.restore(); }
      }
    }
    c.stroke();
    c.strokeStyle = "#d5dae1"; c.beginPath(); ax === "x" ? (c.moveTo(0, H - .5), c.lineTo(W, H - .5)) : (c.moveTo(W - .5, 0), c.lineTo(W - .5, H)); c.stroke();
    if (cursor.value) {                               // положение курсора
      const p = Math.round(at(ax === "x" ? cursor.value.x : cursor.value.y)) + .5;
      c.strokeStyle = "#d1242f"; c.beginPath(); ax === "x" ? (c.moveTo(p, 0), c.lineTo(p, H)) : (c.moveTo(0, p), c.lineTo(W, p)); c.stroke();
    }
  });
}

/* ---------- рисование: бумага, сетка, рамка, штамп, элементы, направляющие ---------- */
const px = v => v / k;                                // толщина в пикселях экрана → мм листа
function drawPaper() {
  paper.destroyChildren();
  const s = sheet.value, [w, h] = pageSize(s), f = frameRect(s);
  paper.add(new Konva.Rect({ x: 0, y: 0, width: w, height: h, fill: "#fff", shadowColor: "#0b1f33", shadowBlur: 18, shadowOpacity: .16, shadowOffset: { x: 0, y: 3 }, shadowForStrokeEnabled: false }));
  if (s.grid?.show && s.grid.step > 0) {             // сетка — тонкие линии, каждая пятая темнее (только на экране)
    const g = s.grid.step;
    for (let i = 1; i * g < w; i++) paper.add(new Konva.Line({ points: [i * g, 0, i * g, h], stroke: i % 5 ? "#edf0f4" : "#dde2e9", strokeWidth: px(1) }));
    for (let i = 1; i * g < h; i++) paper.add(new Konva.Line({ points: [0, i * g, w, i * g], stroke: i % 5 ? "#edf0f4" : "#dde2e9", strokeWidth: px(1) }));
  }
  paper.add(new Konva.Rect({ x: f.x, y: f.y, width: f.w, height: f.h, stroke: INK, strokeWidth: s.stamp === false ? .35 : .7 }));
  const st = stampOps(s, props.meta, props.page);
  if (st) {
    st.lines.forEach(l => paper.add(new Konva.Line({ points: l.pts, stroke: INK, strokeWidth: Math.max(l.w, .1) })));
    // в печати y — линия шрифта; у Konva — верх строки: поднимаем на высоту прописной
    st.texts.forEach(t => t.text && paper.add(new Konva.Text({ x: t.x - 60, y: t.y - t.size * .8, width: 120, align: "center", text: t.text,
      fontSize: t.size, fontFamily: "PT Sans, Inter, system-ui, sans-serif", fill: INK, wrap: "none", ellipsis: true })));
  }
}
function drawGuides() {
  guideL.destroyChildren();
  const s = sheet.value, [w, h] = pageSize(s);
  ["x", "y"].forEach(ax => (s.guides?.[ax] || []).forEach((v, i) => {
    const line = new Konva.Line({ points: ax === "x" ? [v, -8, v, h + 8] : [-8, v, w + 8, v], stroke: GUIDE, strokeWidth: px(1), hitStrokeWidth: px(8), draggable: true,
      dragBoundFunc: p => ax === "x" ? { x: p.x, y: line.absolutePosition().y } : { x: line.absolutePosition().x, y: p.y } });
    line.on("mouseenter", () => { host.value.style.cursor = ax === "x" ? "ew-resize" : "ns-resize"; });
    line.on("mouseleave", () => { host.value.style.cursor = ""; });
    line.on("dblclick dbltap", () => commit(s2 => s2.guides[ax].splice(i, 1)));
    line.on("dragmove", () => { const p = pt(); cursor.value = p; drawRulers(); });
    line.on("dragend", () => {
      const nv = +(v + (ax === "x" ? line.x() : line.y())).toFixed(1), lim = ax === "x" ? w : h;
      commit(s2 => { if (nv < 0 || nv > lim) s2.guides[ax].splice(i, 1); else s2.guides[ax][i] = nv; });   // на линейку или за лист — убрать
    });
    guideL.add(line);
  }));
}
function draw() {
  if (!stage) return;
  tr.nodes([]); tr.remove();                          // ручки живут дольше элементов: снять до очистки слоя, иначе их уничтожит destroyChildren
  drawPaper(); blocks.destroyChildren(); drawGuides();
  sheet.value.blocks.forEach(b => blocks.add(bind(blockNode(b, sheet.value, draw, props.maps), b)));
  blocks.add(tr); attach();
  stage.batchDraw(); drawRulers();
}
// ручки на выбранных незакреплённых видимых элементах; у стрелки севера и картинки пропорции держатся
function attach() {
  const nodes = selBlocks.value.filter(b => !b.locked && !b.hidden).map(b => blocks.findOne("#" + b.id)).filter(Boolean);
  tr.nodes(nodes); tr.keepRatio(nodes.length === 1 && ["north", "picture"].includes(selBlocks.value[0]?.kind)); tr.moveToTop(); blocks.batchDraw(); drawRulers();
}
function select(ids) { sel.value = ids; attach(); }

/* ---------- перетаскивание и размер элементов ---------- */
let pending = null;
function flushNodes() {                                // по концу перетаскивания или ручек — одна запись в историю на всех
  pending = null;
  const nodes = tr.nodes(); if (!nodes.length) return;
  commit(s => nodes.forEach(n => {
    const b = blk(s, n.id()); if (!b) return;
    const sx = n.scaleX(), sy = n.scaleY(); n.scale({ x: 1, y: 1 });
    Object.assign(b, { x: +n.x().toFixed(2), y: +n.y().toFixed(2), w: +Math.max(1, b.w * sx).toFixed(2), h: +Math.max(1, b.h * sy).toFixed(2), rotation: +(n.rotation() % 360).toFixed(2) || undefined });
  }));
}
const later = () => { if (!pending) pending = queueMicrotask(flushNodes) || true; };
function bind(g, b) {
  g.on("dragmove", e => {
    over.destroyChildren();
    if (sel.value.length !== 1 || e.evt?.altKey || b.rotation) { over.batchDraw(); return; }
    const p = g.position(), s = snapBox({ x0: p.x, y0: p.y, x1: p.x + b.w, y1: p.y + b.h }, sheet.value, { snapFn: Snap?.snap, tol: Snap.ZONE_PX * 1.5 / k, except: b.id });
    g.position({ x: p.x + s.dx, y: p.y + s.dy });
    s.guides.forEach(({ a, b: e2 }) => over.add(new Konva.Line({ points: [a[0], a[1], e2[0], e2[1]], stroke: SMART, strokeWidth: px(1), listening: false })));
    over.batchDraw(); cursor.value = pt(); drawRulers();
  });
  g.on("dragend", () => { over.destroyChildren(); over.batchDraw(); later(); });
  g.on("transformend", later);
  return g;
}
// ручки размера встают к направляющим, сетке и краям других элементов
function anchorSnap(oldPos, newPos) {
  const t = stage.getAbsoluteTransform().copy().invert(), m = t.point(newPos);
  const s = snapBox({ x0: m.x, y0: m.y, x1: m.x, y1: m.y }, sheet.value, { snapFn: Snap?.snap, tol: Snap.ZONE_PX * 1.5 / k, except: sel.value });
  return stage.getAbsoluteTransform().point({ x: m.x + s.dx, y: m.y + s.dy });
}

/* ---------- мышь на листе: выбор, рамка выбора, новый элемент, сдвиг листа ---------- */
let drag = null;                                      // { kind: "marquee" | "add" | "pan", ... }
function onDown(e) {
  const ev = e.evt; host.value.focus({ preventScroll: true });
  if (ev.button === 1 || space || tool.value === "pan") { ev.preventDefault(); drag = { kind: "pan", cx: ev.clientX, cy: ev.clientY, o: stage.position() }; host.value.style.cursor = "grabbing"; return; }
  if (ev.button !== 0) return;
  if (tool.value === "content") {                     // сдвиг карты внутри рамки (QGIS «Сдвинуть содержимое элемента»)
    const b = mapAt(pt()); if (!b) return;
    select([b.id]); drag = { kind: "content", id: b.id, p0: pt(), node: blocks.findOne("#" + b.id)?.findOne(".mapimg-pic") };
    if (drag.node) drag.o = drag.node.position();
    host.value.style.cursor = "grabbing"; return;
  }
  if (KINDS[tool.value]) { const p = snapPt(pt()); drag = { kind: "add", p0: p, p1: p }; return; }
  if (e.target.getParent?.() === tr || e.target === tr) return;      // ручки
  const g = e.target.findAncestor?.(".block", true);
  if (g) {
    const id = g.id(), add = ev.shiftKey || ev.ctrlKey || ev.metaKey;
    if (add) select(sel.value.includes(id) ? sel.value.filter(x => x !== id) : [...sel.value, id]);
    else if (!sel.value.includes(id)) select([id]);
    return;
  }
  if (e.target.getLayer?.() === guideL) return;
  drag = { kind: "marquee", p0: pt(), p1: pt(), add: ev.shiftKey || ev.ctrlKey || ev.metaKey, base: [...sel.value] };
  if (!drag.add) select([]);
}
// верхняя незакреплённая видимая карта под точкой листа (поворот карты не учитывается — как в печати)
const mapAt = p => [...sheet.value.blocks].reverse().find(b => b.kind === "map" && !b.locked && !b.hidden && p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h);
function snapPt(p) {
  const s = snapBox({ x0: p.x, y0: p.y, x1: p.x, y1: p.y }, sheet.value, { snapFn: Snap?.snap, tol: Snap.ZONE_PX * 1.5 / k });
  return { x: p.x + s.dx, y: p.y + s.dy };
}
const rectOf = (a, b) => ({ x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y) });
function onMove(ev) {
  if (!stage) return;
  if (host.value && ev.target && host.value.contains(ev.target)) { cursor.value = toMM(ev.clientX, ev.clientY); drawRulers(); }
  if (!drag) return;
  if (drag.kind === "pan") { setView(k, drag.o.x + ev.clientX - drag.cx, drag.o.y + ev.clientY - drag.cy); return; }
  const p = toMM(ev.clientX, ev.clientY);
  if (drag.kind === "content") {
    drag.p1 = p;
    if (drag.node) { drag.node.position({ x: drag.o.x + p.x - drag.p0.x, y: drag.o.y + p.y - drag.p0.y }); blocks.batchDraw(); }
    return;
  }
  drag.p1 = drag.kind === "add" ? snapPt(p) : p;
  const r = rectOf(drag.p0, drag.p1); over.destroyChildren();
  over.add(new Konva.Rect({ x: r.x, y: r.y, width: r.w, height: r.h, stroke: ACCENT, strokeWidth: px(1), dash: drag.kind === "add" ? undefined : [px(4), px(3)], fill: "rgba(31,111,235,.07)", listening: false }));
  over.batchDraw();
}
function onUp() {
  if (!drag) return;
  const d = drag; drag = null; over.destroyChildren(); over.batchDraw(); host.value.style.cursor = tool.value === "content" ? "move" : "";
  if (d.kind === "content") {
    const b = blk(sheet.value, d.id), dx = (d.p1?.x ?? d.p0.x) - d.p0.x, dy = (d.p1?.y ?? d.p0.y) - d.p0.y;
    if (b?.center && Math.hypot(dx, dy) > .05) patch(b.id, { center: moveCenter(b.center, b.scale, -dx, -dy) });
    return;
  }
  if (d.kind === "marquee") {
    const r = rectOf(d.p0, d.p1); if (r.w < .5 && r.h < .5) return;
    const hit = sheet.value.blocks.filter(b => !b.locked && !b.hidden && b.x < r.x + r.w && r.x < b.x + b.w && b.y < r.y + r.h && r.y < b.y + b.h).map(b => b.id);
    select(d.add ? [...new Set([...d.base, ...hit])] : hit);
  }
  if (d.kind === "add") {
    const r = rectOf(d.p0, d.p1), big = r.w > 2 && r.h > 1;
    const b = newBlock(tool.value, sheet.value, big ? r : null);
    if (!big) { b.x = +d.p0.x.toFixed(2); b.y = +d.p0.y.toFixed(2); }   // щелчок — размер по умолчанию от точки щелчка
    commit(s => s.blocks.push(b)); tool.value = "select"; select([b.id]);
  }
}

/* ---------- направляющие от линеек ---------- */
function rulerDown(ax, ev) {
  // с верхней линейки тянется горизонтальная направляющая (y), с левой — вертикальная (x), как в QGIS
  if (ev.button !== 0) return; ev.preventDefault();
  const g = ax === "x" ? "y" : "x";
  const mv = e => {
    const p = toMM(e.clientX, e.clientY), [w, h] = pageSize(sheet.value); over.destroyChildren(); cursor.value = p;
    over.add(new Konva.Line({ points: g === "x" ? [p.x, -8, p.x, h + 8] : [-8, p.y, w + 8, p.y], stroke: GUIDE, strokeWidth: px(1), dash: [px(5), px(3)], listening: false }));
    over.batchDraw(); drawRulers();
  };
  const up = e => {
    window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up);
    over.destroyChildren(); over.batchDraw();
    const r = host.value.getBoundingClientRect(); if (e.clientX < r.left || e.clientY < r.top || e.clientX > r.right || e.clientY > r.bottom) return;
    const p = toMM(e.clientX, e.clientY), sn = sheet.value.grid?.snap && sheet.value.grid.step > 0 ? snapPt(p) : p;
    commit(s => s.guides[g].push(+(g === "x" ? sn.x : sn.y).toFixed(1)));
  };
  window.addEventListener("pointermove", mv); window.addEventListener("pointerup", up);
}

/* ---------- действия ленты и клавиши ---------- */
function setFormat(p) { remember(); sheet.value = { ...reformat(sheet.value, p), guides: { x: [], y: [] } }; syncHist(); out(); fit(); }
function setSheet(p) { commit(s => Object.assign(s, clone(p))); }
function exportPng() {
  const [pw, ph] = pageSize(sheet.value), o = stage.position(), keep = sel.value, gridOn = sheet.value.grid?.show;
  select([]); guideL.hide(); over.hide(); if (gridOn) { sheet.value.grid.show = false; drawPaper(); }
  paper.findOne("Rect")?.shadowEnabled(false);
  const url = stage.toDataURL({ x: o.x, y: o.y, width: pw * k, height: ph * k, pixelRatio: 300 / 25.4 / k, mimeType: "image/png" });
  if (gridOn) sheet.value.grid.show = true; guideL.show(); over.show(); draw(); select(keep);
  const a = document.createElement("a"); a.href = url; a.download = `${(sheet.value.title || "лист").replace(/[\\/:*?"<>|]/g, "_")}.png`; a.click();
}
async function printPdf() {
  if (!props.maps?.pdf || busy.value === "PDF собирается…") return;
  busy.value = "PDF собирается…";
  try { await props.maps.pdf(clone(sheet.value), props.meta); busy.value = ""; } catch (e) { busy.value = e.message || "PDF не собрался"; }
}
function act(id) {
  const [a, b] = id.split(":"), bs = selBlocks.value;
  if (id === "map:here") {                            // «Как на карте»: место и масштаб окна «Карта»
    const h = props.maps?.here?.(), ms = bs.filter(x => x.kind === "map"); if (!h || !ms.length) return;
    const m = {}; ms.forEach(x => { m[x.id] = h.scale > 0 ? { center: h.center, scale: h.scale } : { center: h.center }; }); return patchMany(m);
  }
  if (id === "legend:layers") {                       // строки легенды — из видимых слоёв проекта
    const items = props.maps?.legend?.(); if (!items?.length) return;
    const m = {}; bs.filter(x => x.kind === "legend").forEach(x => { m[x.id] = { items }; }); return patchMany(m);
  }
  if (id === "export:pdf") return printPdf();
  if (a === "tool") { tool.value = b; return; }
  if (a === "add") { tool.value = tool.value === b ? "select" : b; host.value?.focus(); return; }
  if (id === "undo") return step(-1);
  if (id === "redo") return step(1);
  if (id === "copy") { clip = clone(bs); canPaste.value = !!clip.length; return; }
  if (id === "cut") { act("copy"); return act("del"); }
  if (id === "paste") { if (!clip?.length) return; const c = duplicate(clip); clip = clone(c); commit(s => s.blocks.push(...c)); return select(c.map(x => x.id)); }
  if (id === "dup") { const c = duplicate(bs); commit(s => s.blocks.push(...c)); return select(c.map(x => x.id)); }
  if (id === "del") { const ids = new Set(sel.value); if (!ids.size) return; sel.value = []; return commit(s => { s.blocks = s.blocks.filter(x => !ids.has(x.id)); }); }
  if (id === "all") return select(sheet.value.blocks.filter(x => !x.locked && !x.hidden).map(x => x.id));
  if (a === "align") return patchMany(align(bs, b, bs.length === 1 ? frameRect(sheet.value) : null));
  if (a === "dist") return patchMany(distribute(bs, b));
  if (a === "same") return patchMany(sameSize(bs, b));
  if (a === "order") return commit(s => { s.blocks = reorder(s.blocks, sel.value, b); });
  if (id === "lock") { const ids = new Set(sel.value); sel.value = []; return commit(s => s.blocks.forEach(x => { if (ids.has(x.id)) x.locked = true; })); }
  if (id === "unlock") return commit(s => s.blocks.forEach(x => { delete x.locked; }));
  if (id === "grid:show") return setSheet({ grid: { ...sheet.value.grid, show: !sheet.value.grid?.show } });
  if (id === "grid:snap") return setSheet({ grid: { ...sheet.value.grid, snap: !sheet.value.grid?.snap } });
  if (id === "zoom:in") return zoomAt(1.25);
  if (id === "zoom:out") return zoomAt(1 / 1.25);
  if (id === "zoom:fit") return fit();
  if (id === "zoom:100") return zoomAt(PX_MM / k);
  if (id === "zoom:sel") return bs.length && zoomTo(bounds(bs));
  if (id === "export:png") return exportPng();
}
function onKey(e) {
  const t = e.target, typing = /INPUT|TEXTAREA|SELECT/.test(t?.tagName || "") || t?.isContentEditable;
  if (typing || !(hovered || root.value?.contains(document.activeElement))) return;
  const mod = e.ctrlKey || e.metaKey, c = e.code;
  const run = (id) => { e.preventDefault(); act(id); };
  if (e.key === " " && !space) { space = true; listen(false); host.value.style.cursor = "grab"; e.preventDefault(); return; }
  if (mod && c === "KeyZ") return run(e.shiftKey ? "redo" : "undo");
  if (mod && c === "KeyY") return run("redo");
  if (mod && c === "KeyC") return run("copy");
  if (mod && c === "KeyX") return run("cut");
  if (mod && c === "KeyV") return run("paste");
  if (mod && c === "KeyD") return run("dup");
  if (mod && c === "KeyA") return run("all");
  if (mod && c === "KeyL") return run(e.shiftKey ? "unlock" : "lock");
  if (mod && c === "BracketRight") return run(e.shiftKey ? "order:top" : "order:up");
  if (mod && c === "BracketLeft") return run(e.shiftKey ? "order:bottom" : "order:down");
  if (mod && c === "Digit0") return run("zoom:fit");
  if (mod && c === "Digit1") return run("zoom:100");
  if (mod && c === "Quote") return run("grid:show");
  if (mod) return;
  if (e.key === "Escape") { e.preventDefault(); tool.value = "select"; return select([]); }
  if (e.key === "v" || e.key === "м") { tool.value = "select"; return; }
  if (e.key === "c" || e.key === "с") { tool.value = "content"; return; }
  if (e.key === "Delete" || e.key === "Backspace") return run("del");
  const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
  if (d && selBlocks.value.length) {
    e.preventDefault(); const st = e.shiftKey ? 5 : .5, m = {};
    selBlocks.value.filter(b => !b.locked).forEach(b => { m[b.id] = { x: +(b.x + d[0] * st).toFixed(2), y: +(b.y + d[1] * st).toFixed(2) }; });
    patchMany(m);
  }
}
const onKeyUp = e => { if (e.key === " ") { space = false; listen(tool.value === "select"); if (host.value) host.value.style.cursor = ""; } };
function pick(id, add) { select(add ? (sel.value.includes(id) ? sel.value.filter(x => x !== id) : [...sel.value, id]) : [id]); }

let ro;
onMounted(() => {
  const el = host.value;
  stage = new Konva.Stage({ container: el, width: el.clientWidth || 800, height: el.clientHeight || 600 });
  paper = new Konva.Layer({ listening: false }); blocks = new Konva.Layer(); guideL = new Konva.Layer(); over = new Konva.Layer({ listening: false });
  stage.add(paper, blocks, guideL, over);
  tr = new Konva.Transformer({ rotateEnabled: true, rotationSnaps: [0, 45, 90, 135, 180, 225, 270, 315], rotationSnapTolerance: 4, flipEnabled: false,
    anchorSize: 8, anchorCornerRadius: 2, borderStroke: ACCENT, anchorStroke: ACCENT, anchorFill: "#fff", rotateAnchorOffset: 22,
    ignoreStroke: true, anchorDragBoundFunc: anchorSnap, boundBoxFunc: (o, n) => (Math.abs(n.width) < 4 || Math.abs(n.height) < 4 ? o : n) });
  stage.on("mousedown touchstart", onDown);
  stage.on("wheel", e => {
    e.evt.preventDefault(); const d = e.evt.deltaY;
    const mb = tool.value === "content" && !e.evt.ctrlKey && !e.evt.metaKey ? mapAt(pt()) : null;   // колесо над картой — масштаб карты
    if (mb) { if (Math.abs(d) > 2) patch(mb.id, { scale: nextScale(mb.scale, d > 0 ? 1 : -1) }); return; }
    zoomAt(Math.exp(-Math.max(-60, Math.min(60, d)) * .004), stage.getPointerPosition());
  });
  window.addEventListener("pointermove", onMove); window.addEventListener("pointerup", onUp);
  window.addEventListener("keydown", onKey); window.addEventListener("keyup", onKeyUp);
  ro = new ResizeObserver(() => { stage.size({ width: el.clientWidth, height: el.clientHeight }); fit(); }); ro.observe(el);
  fit();
});
onBeforeUnmount(() => {
  ro?.disconnect(); stage?.destroy();
  window.removeEventListener("pointermove", onMove); window.removeEventListener("pointerup", onUp);
  window.removeEventListener("keydown", onKey); window.removeEventListener("keyup", onKeyUp);
});
// в режиме добавления и сдвига листа элементы и направляющие не ловят мышь: иначе рамка нового элемента утащила бы их
function listen(on) { blocks?.listening(on); guideL?.listening(on); }
watch(tool, t => { if (host.value) host.value.style.cursor = KINDS[t] ? "crosshair" : t === "pan" ? "grab" : t === "content" ? "move" : ""; listen(t === "select"); });
defineExpose({ fit, act });
</script>

<template>
  <div ref="root" class="sed" @mouseenter="hovered = true" @mouseleave="hovered = false">
    <Ribbon :tool="tool" :has-maps="!!maps" :can-undo="canUndo" :can-redo="canRedo" :n-sel="sel.length" :can-paste="canPaste" :grid="sheet.grid" :any-locked="anyLocked" @act="act" />
    <div class="sed-main">
      <aside class="sed-side left">
        <div class="sed-tab"><span>Элементы</span></div>
        <div class="sed-scroll">
          <ItemsPanel :blocks="sheet.blocks" :sel="sel" @pick="pick" @patch="patch" />
          <template v-if="issues.length">
            <div class="sed-h">Замечания</div>
            <button v-for="(p, i) in issues" :key="i" class="sed-issue" @click="pick(p.id)">{{ p.text }}</button>
          </template>
        </div>
      </aside>
      <section class="sed-center">
        <div class="sed-tab"><span>Макет · {{ sheet.title || 'лист' }}</span></div>
        <div class="sed-canvas">
          <div class="sed-corner" title="Тяните от линейки, чтобы поставить направляющую"></div>
          <canvas ref="rulerX" class="sed-rx" @pointerdown="rulerDown('x', $event)" title="Тяните вниз — горизонтальная направляющая"></canvas>
          <canvas ref="rulerY" class="sed-ry" @pointerdown="rulerDown('y', $event)" title="Тяните вправо — вертикальная направляющая"></canvas>
          <div ref="host" class="sed-stage" tabindex="0" aria-label="Лист" @mouseleave="cursor = null; drawRulers()"></div>
        </div>
      </section>
      <aside class="sed-side right">
        <div class="sed-tab"><span>Свойства</span></div>
        <div class="sed-scroll">
          <PropsPanel :sheet="sheet" :sel="selBlocks" :has-maps="!!maps" @patch="patch" @format="setFormat" @set="setSheet" @act="act" />
        </div>
      </aside>
    </div>
    <footer class="sed-status">
      <span>{{ KINDS[tool] ? `${KINDS[tool]}: растяните рамку на листе или щёлкните; Esc — отмена` : tool === 'pan' ? 'Сдвиг листа: тяните мышью' : tool === 'content' ? 'Сдвиг карты в рамке: тяните мышью; колесо — масштаб карты' : 'Щелчок — выбрать, Shift — добавить, рамка по пустому месту — несколько' }}</span>
      <span class="sp"></span>
      <span v-if="busy" class="sed-busy">{{ busy }}</span>
      <span v-if="statusSel">{{ statusSel }}</span>
      <span class="mono">{{ cursor ? `X ${fmt1(cursor.x)}  Y ${fmt1(cursor.y)} мм` : 'X —  Y —' }}</span>
      <span>{{ FORMAT_T[sheet.format] }} {{ sheet.orient === 'P' ? 'книжный' : 'альбомный' }}</span>
      <button class="sed-zoom" title="Масштаб экрана; щелчок — 100 %" @click="act('zoom:100')">{{ Math.round(zoom / PX_MM * 100) }} %</button>
    </footer>
  </div>
</template>

<style scoped>
/* цвета — из темы Web Awesome каркаса (светлая и тёмная), запасные — для отдельной страницы */
.sed { --g-ink: var(--wa-color-text-normal, #1f2328); --g-mute: var(--wa-color-text-quiet, #66707c); --g-line: var(--wa-color-surface-border, #e3e6ea);
  --g-line-strong: var(--wa-color-neutral-border-normal, #cfd4da); --g-panel: var(--wa-color-surface-default, #fff); --g-bg: var(--wa-color-surface-lowered, #eef0f3);
  --g-hover: var(--wa-color-neutral-fill-quiet, #f0f2f5); --g-sel: var(--wa-color-brand-fill-quiet, #e8f0fe); --g-sel-line: var(--wa-color-brand-border-quiet, #b9d0f7);
  --g-accent: var(--wa-color-brand-fill-loud, #1f6feb); --g-ring: rgba(31,111,235,.18); --g-warn: var(--wa-color-danger-on-quiet, #b4441b);
  display: flex; flex-direction: column; height: 100%; font: 13px/1.3 var(--wa-font-family-body, system-ui), sans-serif; color: var(--g-ink); background: var(--g-panel); }
.sed-main { flex: 1; display: flex; min-height: 0; }
.sed-side { flex: none; display: flex; flex-direction: column; min-height: 0; background: var(--g-panel); }
.sed-side.left { width: 236px; border-right: 1px solid var(--g-line); }
.sed-side.right { width: 280px; border-left: 1px solid var(--g-line); }
.sed-scroll { flex: 1; overflow: auto; }
.sed-tab { height: 30px; flex: none; display: flex; align-items: flex-end; padding: 0 8px; border-bottom: 1px solid var(--g-line); }
.sed-tab span { padding: 0 2px 6px; border-bottom: 2px solid var(--g-accent); margin-bottom: -1px; font-weight: 500; }
.sed-h { font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--g-mute); margin: 12px 10px 4px; }
.sed-issue { display: block; width: calc(100% - 12px); margin: 0 6px; text-align: left; font: inherit; color: var(--g-warn); background: none; border: 0; padding: 4px; border-radius: 4px; cursor: pointer; }
.sed-issue:hover { background: #fdf1ec; }
.sed-center { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.sed-canvas { flex: 1; position: relative; min-height: 0; background: var(--g-bg); }
.sed-corner { position: absolute; left: 0; top: 0; width: 22px; height: 22px; background: var(--g-panel); border-right: 1px solid var(--g-line); border-bottom: 1px solid var(--g-line); }
.sed-rx { position: absolute; left: 22px; top: 0; right: 0; height: 22px; width: calc(100% - 22px); cursor: s-resize; }
.sed-ry { position: absolute; left: 0; top: 22px; bottom: 0; width: 22px; height: calc(100% - 22px); cursor: e-resize; }
.sed-stage { position: absolute; left: 22px; top: 22px; right: 0; bottom: 0; outline: none; overflow: hidden; }
.sed-status { height: 24px; flex: none; display: flex; align-items: center; gap: 16px; padding: 0 10px; border-top: 1px solid var(--g-line); color: var(--g-mute); font-size: 12px; white-space: nowrap; overflow: hidden; }
.sed-status .sp { flex: 1; }
.sed-busy { color: var(--g-accent); }
.sed-status .mono { font-variant-numeric: tabular-nums; min-width: 150px; }
.sed-zoom { font: inherit; color: inherit; background: none; border: 1px solid transparent; border-radius: 4px; padding: 0 6px; cursor: pointer; font-variant-numeric: tabular-nums; }
.sed-zoom:hover { border-color: var(--g-line-strong); color: var(--g-ink); }
</style>
