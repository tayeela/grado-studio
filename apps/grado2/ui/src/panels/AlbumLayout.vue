<!-- ГРАДО 2 · «Макет надписей» нового интерфейса (шаг 2 фаза 2, #94): правка надписей готового листа альбома, как макет
     печати QGIS. Лист — та же картинка печати (/api/print/svg, запрос листа даёт движок альбома albumApi.spec), любая надпись
     листа (заголовок, шапка, подписи карты, легенда) выбирается щелчком, рамкой или Shift+щелчком. Линейки в мм сверху и слева,
     направляющие тянутся от линеек (двойной щелчок или на линейку — убрать), надписи при перетаскивании встают к краям и
     серединам других надписей, листа и направляющих (web/snap.js; Alt — без привязки). Выравнивание выбранных по краям и
     серединам, равные промежутки, точное место X, Y в мм, стрелки — 0,5 мм (Shift — 5 мм), Ctrl+Z и Ctrl+Shift+Z.
     Правки хранятся в листе как у прежнего макета (edits по ключу «текст#n», items — свои надписи, layGuides — направляющие)
     и попадают в PDF и PPTX (print_io.apply_edits). Правила подписей не меняются: это ручная поправка поверх них. -->
<template>
  <div class="alay" tabindex="0" @keydown="keys">
    <div class="al-bar" role="toolbar" aria-label="Макет надписей">
      <b class="al-t" :title="title">{{ title }}</b>
      <span class="sp"></span>
      <wa-button size="s" appearance="plain" title="Мельче (Ctrl + колесо)" aria-label="Мельче" @click="zoomAt(1 / 1.25)"><ZoomOut :size="15" /></wa-button>
      <wa-button size="s" appearance="plain" title="Лист целиком" aria-label="Лист целиком" @click="fit"><Maximize :size="15" /></wa-button>
      <wa-button size="s" appearance="plain" title="Крупнее (Ctrl + колесо)" aria-label="Крупнее" @click="zoomAt(1.25)"><ZoomIn :size="15" /></wa-button>
      <span class="sep"></span>
      <wa-button size="s" appearance="plain" :disabled="!hist.u.length" title="Отменить (Ctrl+Z)" aria-label="Отменить" @click="undo(-1)"><Undo2 :size="15" /></wa-button>
      <wa-button size="s" appearance="plain" :disabled="!hist.r.length" title="Вернуть (Ctrl+Shift+Z)" aria-label="Вернуть" @click="undo(1)"><Redo2 :size="15" /></wa-button>
      <span class="sep"></span>
      <wa-button size="s" :appearance="adding ? 'filled' : 'outlined'" :variant="adding ? 'brand' : 'neutral'" :disabled="!ready || viewer" title="Своя надпись: затем щёлкните место на листе" @click="adding = !adding"><Type :size="15" /> Текст</wa-button>
      <wa-button size="s" appearance="outlined" :disabled="!ready || viewer" title="Вернуть на лист все скрытые надписи" @click="showHidden"><Eye :size="15" /> Скрытые</wa-button>
      <wa-button size="s" appearance="outlined" :disabled="!ready || viewer" title="Снять все правки надписей и удалить свои надписи этого листа" @click="askReset = true"><RotateCcw :size="15" /> Сбросить всё</wa-button>
      <wa-button size="s" variant="brand" :disabled="!ready" title="Этот лист одним PDF — с правками" @click="pdf"><FileDown :size="15" /> PDF листа</wa-button>
    </div>
    <div class="al-body">
      <div class="al-work">
        <div class="al-corner" title="Тяните от линейки, чтобы поставить направляющую"></div>
        <canvas ref="rulerX" class="al-rx" title="Тяните вниз — горизонтальная направляющая" @pointerdown="rulerDown('y', $event)"></canvas>
        <canvas ref="rulerY" class="al-ry" title="Тяните вправо — вертикальная направляющая" @pointerdown="rulerDown('x', $event)"></canvas>
        <div ref="stage" class="al-stage" :class="{ busy, adding, pan: panning }" @pointerdown="down" @pointermove="hover" @pointerleave="cursor = null" @wheel.prevent="wheel">
          <div ref="paper" class="al-paper" :style="paperStyle"></div>
          <p v-if="!sheet" class="al-empty">Выберите лист во вкладке «Листы и альбом» и нажмите «Надписи».</p>
          <p v-else-if="err" class="al-empty">Лист не собран: {{ err }}</p>
        </div>
      </div>
      <aside class="al-side" aria-label="Свойства надписи">
        <template v-if="selKeys.length === 1 && cur">
          <p class="al-h">{{ isItem(selKeys[0]) ? "Своя надпись" : "Надпись листа" }}</p>
          <wa-textarea size="s" label="Текст" rows="2" :value="cur.text" :readonly="viewer" @input="e => setProp('text', e.target.value)"></wa-textarea>
          <wa-select size="s" label="Шрифт" :value="cur.font || 'base'" :disabled="viewer" @change="e => setProp('font', e.target.value === 'base' ? '' : e.target.value)">
            <wa-option v-if="!isItem(selKeys[0])" value="base">как на листе</wa-option>
            <wa-option v-for="f in FONTS" :key="f[0]" :value="f[0]">{{ f[1] }}</wa-option>
          </wa-select>
          <div class="g2">
            <wa-number-input size="s" label="Кегль, пт" :value="cur.pt" min="2" max="170" step="0.5" :disabled="viewer" @change="e => setProp('size', +(e.target.value * PT).toFixed(3))"></wa-number-input>
            <wa-number-input size="s" label="Поворот, °" :value="cur.angle" min="-180" max="180" step="1" :disabled="viewer" @change="e => setProp('angle', e.target.value === '' ? '' : +e.target.value)"></wa-number-input>
          </div>
          <div class="g2">
            <wa-number-input size="s" label="X, мм" :value="r1(selBox.x0)" step="0.5" :disabled="viewer" title="Левый край надписи от левого края листа" @change="e => moveTo(+e.target.value, null)"></wa-number-input>
            <wa-number-input size="s" label="Y, мм" :value="r1(selBox.y0)" step="0.5" :disabled="viewer" title="Верх надписи от верхнего края листа" @change="e => moveTo(null, +e.target.value)"></wa-number-input>
          </div>
          <p class="hint">Размер: {{ r1(selBox.x1 - selBox.x0) }} × {{ r1(selBox.y1 - selBox.y0) }} мм</p>
          <div class="crow">
            <wa-color-picker size="s" :value="cur.color" aria-label="Цвет текста" :disabled="viewer" @change="e => setProp('color', e.target.value)"></wa-color-picker><span>Цвет текста</span>
          </div>
          <div class="crow">
            <wa-checkbox size="s" :checked="!!cur.halo" :disabled="viewer" @change="e => setHalo(e.target.checked ? (cur.halo || ['#ffffff', .6]) : null)">Обводка</wa-checkbox>
            <template v-if="cur.halo">
              <wa-color-picker size="s" :value="cur.halo[0]" aria-label="Цвет обводки" :disabled="viewer" @change="e => setHalo([e.target.value, cur.halo[1]])"></wa-color-picker>
              <wa-number-input size="s" class="hw" :value="cur.halo[1]" min="0.1" max="3" step="0.1" aria-label="Толщина обводки, мм" title="Толщина обводки, мм" :disabled="viewer" @change="e => setHalo([cur.halo[0], +e.target.value || .6])"></wa-number-input>
            </template>
          </div>
          <div class="row">
            <wa-button size="s" appearance="outlined" :disabled="viewer" @click="hideSel">{{ isItem(selKeys[0]) ? "Удалить" : "Скрыть" }}</wa-button>
            <wa-button v-if="!isItem(selKeys[0])" size="s" appearance="plain" :disabled="viewer" title="Вернуть надпись как была" @click="resetSel">Сбросить правку</wa-button>
          </div>
        </template>
        <template v-else-if="selKeys.length > 1">
          <p class="al-h">Выбрано надписей: {{ selKeys.length }}</p>
          <div class="g2">
            <wa-number-input size="s" label="X, мм" :value="r1(selBox.x0)" step="0.5" :disabled="viewer" @change="e => moveTo(+e.target.value, null)"></wa-number-input>
            <wa-number-input size="s" label="Y, мм" :value="r1(selBox.y0)" step="0.5" :disabled="viewer" @change="e => moveTo(null, +e.target.value)"></wa-number-input>
          </div>
          <wa-button size="s" appearance="outlined" :disabled="viewer" @click="hideSel">Скрыть выбранные</wa-button>
        </template>
        <p v-else class="hint">Щёлкните надпись на листе — заголовок, подпись улицы, строку легенды. Рамка мышью или Shift+щелчок выбирает несколько.
          Тянуть — сдвиг с привязкой к краям других надписей, листа и направляющих (Alt — без привязки); стрелки — 0,5 мм, Shift — 5 мм.</p>
        <template v-if="selKeys.length">
          <p class="al-h">Выровнять {{ selKeys.length === 1 ? "по листу" : "выбранные" }}</p>
          <div class="al-al" role="group" aria-label="Выровнять">
            <wa-button v-for="a in ALIGN" :key="a[0]" size="s" appearance="outlined" :disabled="viewer || (a[0].startsWith('d') && selKeys.length < 3)" :title="a[1]" :aria-label="a[1]" @click="alignSel(a[0])">
              <component :is="a[2]" :size="15" /></wa-button>
          </div>
        </template>
        <p class="hint">Правки — поверх автоматических подписей; правила подписей они не меняют. Попадают в PDF и PPTX.</p>
      </aside>
    </div>
    <div class="al-foot"><span>{{ cursor ? `X ${r1(cursor.x)}  Y ${r1(cursor.y)} мм` : "" }}</span><span class="sp"></span><span>{{ Math.round(k / pxmm * 100) }} %</span></div>
    <wa-dialog label="Сбросить всё" :open="askReset" @wa-after-hide="askReset = false">
      <p>Снять все правки надписей и удалить свои надписи этого листа? Направляющие останутся.</p>
      <wa-button slot="footer" size="s" appearance="plain" @click="askReset = false">Отмена</wa-button>
      <wa-button slot="footer" size="s" variant="danger" @click="resetAll">Сбросить</wa-button>
    </wa-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { AlignCenterHorizontal, AlignCenterVertical, AlignEndHorizontal, AlignEndVertical, AlignHorizontalSpaceAround, AlignStartHorizontal,
  AlignStartVertical, AlignVerticalSpaceAround, Eye, FileDown, Maximize, Redo2, RotateCcw, Type, Undo2, ZoomIn, ZoomOut } from "@lucide/vue";
import "../../../web/snap.js";                       // привязка и умные направляющие — та же, что у макетов (кладёт Snap в globalThis)
import { album, call, editSheet } from "../albumhost.js";
import { C } from "../collab.js";
import { notice } from "../project.js";
import { project } from "../store.js";
import { rulerStep } from "../sheet/model.js";

const Snap = globalThis.Snap;
const PT = 25.4 / 72;                                // 1 пт в мм: кегль — в пунктах, как в QGIS
const RULER = 22;
const FONTS = [["ui", "PT Sans"], ["ui-bold", "PT Sans полужирный"], ["serif", "PT Serif"], ["serif-bold", "PT Serif полужирный"], ["sans", "Montserrat"], ["sans-bold", "Montserrat полужирный"]];
const ALIGN = [["left", "По левому краю", AlignStartVertical], ["hcenter", "По середине по ширине", AlignCenterVertical], ["right", "По правому краю", AlignEndVertical],
  ["top", "По верху", AlignStartHorizontal], ["vcenter", "По середине по высоте", AlignCenterHorizontal], ["bottom", "По низу", AlignEndHorizontal],
  ["dx", "Равные промежутки по ширине (три и больше)", AlignHorizontalSpaceAround], ["dy", "Равные промежутки по высоте (три и больше)", AlignVerticalSpaceAround]];
const NS = "http://www.w3.org/2000/svg";
const r1 = v => Number.isFinite(v) ? Math.round(v * 10) / 10 : 0;
const r2 = v => +(+v).toFixed(2);

const stage = ref(null), paper = ref(null), rulerX = ref(null), rulerY = ref(null);
const busy = ref(false), err = ref(""), ready = ref(false), adding = ref(false), panning = ref(false), askReset = ref(false), cursor = ref(null);
const selKeys = ref([]), ver = ref(0);
const hist = reactive({ u: [], r: [], tag: null, t: 0 });
const view = reactive({ k: 2, ox: 30, oy: 30, w: 420, h: 297 });   // k — пикселей на мм, ox/oy — место листа в окне (px), w/h — лист, мм
const pxmm = 96 / 25.4;                              // 100 % — лист в натуральную величину
const k = computed(() => view.k);
const viewer = computed(() => C.role === "viewer");

const idx = computed(() => album.lay);
const sheet = computed(() => { ver.value; album.rev; return idx.value != null ? project.raw?.album?.sheets?.[idx.value] || null : null; });
const title = computed(() => sheet.value ? `Макет надписей · лист ${idx.value + 1} «${sheet.value.title || "без названия"}»` : "Макет надписей");
const paperStyle = computed(() => ({ left: view.ox + "px", top: view.oy + "px", width: view.w * view.k + "px", height: view.h * view.k + "px" }));
const isItem = key => String(key).startsWith("item:");

let svg = null, base = null, req = 0, ro = null;
/* ---------- лист: запрос печати у движка, картинка с правками ---------- */
async function open() {
  selKeys.value = []; hist.u = []; hist.r = []; svg = null; base = null; ready.value = false; err.value = "";
  if (paper.value) paper.value.innerHTML = "";
  if (!sheet.value) return;
  try { base = await call(a => a.spec(idx.value)); } catch (e) { err.value = e.message || String(e); return; }
  if (!base) { err.value = "нет листа"; return; }
  await render(true);
}
async function render(first) {
  if (!base || !sheet.value) return;
  const n = ++req, sh = sheet.value;
  busy.value = true;
  try {
    const spec = { ...base, sheets: [{ ...base.sheets[0], edits: sh.edits || {}, items: sh.items || [] }], index: 0 };
    const r = await fetch("/api/print/svg", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(spec) });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status);
    const t = await r.text(); if (n !== req) return;
    paper.value.innerHTML = t;
    svg = paper.value.querySelector("svg");
    const vb = svg.viewBox.baseVal; view.w = vb.width || 420; view.h = vb.height || 297;
    svg.setAttribute("width", "100%"); svg.setAttribute("height", "100%");
    svg.querySelectorAll("text[data-key]").forEach(x => x.classList.add("al-tx"));
    err.value = ""; ready.value = true;
    if (first) fit();
    selKeys.value = selKeys.value.filter(key => textsOf(key).length);
    overlay();
  } catch (e) { if (n === req) err.value = e.message || String(e); } finally { if (n === req) busy.value = false; }
}
let timer = 0;
const later = () => { clearTimeout(timer); timer = setTimeout(render, 300); };

/* ---------- вид: масштаб, сдвиг, линейки ---------- */
function fit() {
  const el = stage.value; if (!el) return;
  const W = el.clientWidth, H = el.clientHeight, nk = Math.max(.3, Math.min((W - 48) / view.w, (H - 48) / view.h));
  Object.assign(view, { k: nk, ox: (W - view.w * nk) / 2, oy: (H - view.h * nk) / 2 });
}
function zoomAt(f, at) {
  const el = stage.value; if (!el) return;
  const p = at || { x: el.clientWidth / 2, y: el.clientHeight / 2 }, nk = Math.max(.3, Math.min(80, view.k * f));
  Object.assign(view, { ox: p.x - (p.x - view.ox) / view.k * nk, oy: p.y - (p.y - view.oy) / view.k * nk, k: nk });
}
function wheel(e) {
  const r = stage.value.getBoundingClientRect();
  if (e.ctrlKey || e.metaKey) zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, { x: e.clientX - r.left, y: e.clientY - r.top });
  else { view.ox -= e.shiftKey ? e.deltaY : e.deltaX; view.oy -= e.shiftKey ? 0 : e.deltaY; }
}
const toMM = e => { const r = stage.value.getBoundingClientRect(); return { x: (e.clientX - r.left - view.ox) / view.k, y: (e.clientY - r.top - view.oy) / view.k }; };

function drawRulers() {
  const st = rulerStep(view.k), minor = st / (String(st)[0] === "2" ? 4 : 5), sb = selKeys.value.length ? selBox.value : null;
  [[rulerX.value, "x"], [rulerY.value, "y"]].forEach(([cv, ax]) => {
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
    if (!W || !H) return;
    if (cv.width !== W * dpr || cv.height !== H * dpr) { cv.width = W * dpr; cv.height = H * dpr; }
    const c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, W, H);
    const css = getComputedStyle(cv), bg = css.getPropertyValue("--g-panel").trim() || "#f7f8fa", ink = css.getPropertyValue("--g-muted").trim() || "#5f6b7a";
    c.fillStyle = bg; c.fillRect(0, 0, W, H);
    const len = ax === "x" ? W : H, off = ax === "x" ? view.ox : view.oy, at = mm => off + mm * view.k;
    if (sb) {                                         // выбранное — полоса на линейке, как в QGIS
      const a = at(ax === "x" ? sb.x0 : sb.y0), b = at(ax === "x" ? sb.x1 : sb.y1);
      c.fillStyle = "rgba(31,111,235,.16)"; ax === "x" ? c.fillRect(a, 0, b - a, H) : c.fillRect(0, a, W, b - a);
    }
    c.strokeStyle = ink; c.fillStyle = ink; c.lineWidth = 1; c.font = "10px Onest, system-ui, sans-serif";
    const from = Math.floor(-off / view.k / minor) * minor, to = (len - off) / view.k;
    c.beginPath();
    for (let mm = from; mm <= to; mm += minor) {
      const p = Math.round(at(mm)) + .5, major = Math.abs(mm / st - Math.round(mm / st)) < 1e-6, half = !major && Math.abs(mm / (st / 2) - Math.round(mm / (st / 2))) < 1e-6;
      const t = major ? RULER - 2 : half ? 8 : 4;
      if (ax === "x") { c.moveTo(p, RULER); c.lineTo(p, RULER - t); } else { c.moveTo(RULER, p); c.lineTo(RULER - t, p); }
      if (major) {
        const txt = String(Math.round(mm));
        if (ax === "x") c.fillText(txt, p + 3, 10); else { c.save(); c.translate(10, p - 3); c.rotate(-Math.PI / 2); c.fillText(txt, 0, 0); c.restore(); }
      }
    }
    c.stroke();
    if (cursor.value) {
      const p = Math.round(at(ax === "x" ? cursor.value.x : cursor.value.y)) + .5;
      c.strokeStyle = "#d1242f"; c.beginPath(); ax === "x" ? (c.moveTo(p, 0), c.lineTo(p, H)) : (c.moveTo(0, p), c.lineTo(W, p)); c.stroke();
    }
  });
}

/* ---------- надписи листа: рамки в мм ---------- */
const allTexts = () => svg ? [...svg.querySelectorAll("text[data-key]")] : [];
const textsOf = key => allTexts().filter(t => t.dataset.key === key);
// рамка элемента в мм листа без наклона: углы getBBox через его преобразование (повёрнутая подпись — по описанной рамке)
function boxOf(el) {
  const b = el.getBBox(), m = svg.getScreenCTM().inverse().multiply(el.getScreenCTM()), p = svg.createSVGPoint();
  const c = [[b.x, b.y], [b.x + b.width, b.y], [b.x, b.y + b.height], [b.x + b.width, b.y + b.height]].map(([x, y]) => { p.x = x; p.y = y; return p.matrixTransform(m); });
  const xs = c.map(q => q.x), ys = c.map(q => q.y);
  return { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) };
}
const union = bs => bs.length ? { x0: Math.min(...bs.map(b => b.x0)), y0: Math.min(...bs.map(b => b.y0)), x1: Math.max(...bs.map(b => b.x1)), y1: Math.max(...bs.map(b => b.y1)) } : null;
const keyBox = key => union(textsOf(key).map(boxOf));
const selBox = computed(() => { ver.value; return (svg && union(selKeys.value.map(keyBox).filter(Boolean))) || { x0: 0, y0: 0, x1: 0, y1: 0 }; });
const guides = () => sheet.value?.layGuides || { x: [], y: [] };

/* свойства выбранной надписи: с листа (как нарисовано), правка поверх */
const cur = computed(() => {
  ver.value; const key = selKeys.value[0], t = key && textsOf(key)[0]; if (!t) return null;
  const rgb = s => { const m = String(s || "").match(/\d+/g); return m ? "#" + m.slice(0, 3).map(v => (+v).toString(16).padStart(2, "0")).join("") : "#000000"; };
  const rot = (t.getAttribute("transform") || "").match(/rotate\(([-\d.]+)/), e = editOf(key, false) || {};
  const halo = e.halo !== undefined ? e.halo : t.getAttribute("stroke") ? [rgb(t.getAttribute("stroke")), r2(+t.getAttribute("stroke-width") / 2)] : null;
  return { text: isItem(key) ? e.text : e.text ?? t.textContent, font: e.font || (isItem(key) ? "ui" : ""), pt: r1(+t.getAttribute("font-size") / PT),
    color: e.color || rgb(t.getAttribute("fill")), angle: e.angle ?? (rot ? r1(+rot[1]) : 0), halo };
});

/* ---------- поверх листа: выбор, направляющие, умные направляющие, рамка выбора ---------- */
function layer(id, events) {
  let g = svg.querySelector("#" + id);
  if (!g) { g = document.createElementNS(NS, "g"); g.id = id; if (!events) g.setAttribute("pointer-events", "none"); svg.appendChild(g); }
  g.replaceChildren(); return g;
}
const el = (tag, at) => { const x = document.createElementNS(NS, tag); Object.entries(at).forEach(([a, v]) => x.setAttribute(a, v)); return x; };
function overlay() {               // рамки выбранных — по тому, где надписи нарисованы сейчас (сдвиг перетаскивания уже в их transform)
  if (!svg) return;
  const gu = layer("al-guides", true), G = guides();
  ["x", "y"].forEach(ax => (G[ax] || []).forEach((v, i) => {
    const a = ax === "x" ? { x1: v, y1: -10, x2: v, y2: view.h + 10 } : { x1: -10, y1: v, x2: view.w + 10, y2: v };
    gu.appendChild(el("line", { ...a, stroke: "#00a3d9", "stroke-width": 1, "vector-effect": "non-scaling-stroke", "pointer-events": "none" }));
    gu.appendChild(el("line", { ...a, stroke: "transparent", "stroke-width": 8, "vector-effect": "non-scaling-stroke", "data-guide": `${ax}:${i}`, class: ax === "x" ? "al-gx" : "al-gy" }));
  }));
  const g = layer("al-sel");
  selKeys.value.forEach(key => textsOf(key).forEach(t => {
    const b = boxOf(t);
    g.appendChild(el("rect", { x: b.x0 - .5, y: b.y0 - .4, width: b.x1 - b.x0 + 1, height: b.y1 - b.y0 + .8, fill: "rgba(31,111,235,.06)",
      stroke: "#1f6feb", "stroke-width": 1.2, "vector-effect": "non-scaling-stroke" }));
  }));
  ver.value++; drawRulers();
}
function smart(list) {
  const g = layer("al-smart"); (list || []).forEach(({ a, b }) => g.appendChild(el("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: "#e0108a", "stroke-width": 1, "vector-effect": "non-scaling-stroke" })));
}

/* ---------- правки: в листе альбома, с историей ---------- */
const snap = () => JSON.stringify({ edits: sheet.value?.edits || {}, items: sheet.value?.items || [], layGuides: sheet.value?.layGuides || null });
function remember(tag) {
  const now = Date.now();
  if (tag && tag === hist.tag && now - hist.t < 1500) { hist.t = now; return; }
  hist.u.push(snap()); if (hist.u.length > 100) hist.u.shift(); hist.r = []; hist.tag = tag; hist.t = now;
}
function save(patch, rerender = true) {
  const sh = sheet.value; if (!sh) return;
  editSheet(idx.value, patch);
  if (rerender) later(); else overlay();
}
function undo(dir) {
  const from = dir < 0 ? hist.u : hist.r, to = dir < 0 ? hist.r : hist.u;
  if (!from.length) return;
  to.push(snap()); const x = JSON.parse(from.pop()); hist.tag = null;
  save({ edits: x.edits, items: x.items, layGuides: x.layGuides || undefined });
}
// запись правки надписи: у своей надписи — сама надпись (x, y), у надписи листа — edits[key] (dx, dy)
function editOf(key, make = true) {
  const sh = sheet.value; if (!sh) return null;
  if (isItem(key)) return (sh.items || []).find(x => "item:" + x.id === key) || null;
  if (!make) return sh.edits?.[key] || null;
  sh.edits ||= {}; return (sh.edits[key] ||= {});
}
function setProp(name, v) {
  const key = selKeys.value[0]; if (!key || viewer.value) return;
  if (name === "text" && isItem(key) && !String(v).trim()) return;   // пустая своя надпись пропала бы — её удаляют кнопкой
  remember(name + ":" + key); const e = editOf(key);
  if (v === "" || v == null) delete e[name]; else e[name] = v;
  save({ edits: sheet.value.edits, items: sheet.value.items });
}
function setHalo(h) { const key = selKeys.value[0]; if (!key) return; remember("halo:" + key); editOf(key).halo = h; save({ edits: sheet.value.edits, items: sheet.value.items }); }
function moveKeys(keys, dx, dy, tag) {
  if (viewer.value || !keys.length || (!dx && !dy)) return;
  remember(tag);
  keys.forEach(key => { const e = editOf(key); if (!e) return;
    if (isItem(key)) { e.x = r2(e.x + dx); e.y = r2(e.y + dy); } else { e.dx = r2((e.dx || 0) + dx); e.dy = r2((e.dy || 0) + dy); } });
  // надпись сразу на новом месте, лист перерисуется следом
  keys.forEach(key => textsOf(key).forEach(t => t.setAttribute("transform", `translate(${dx} ${dy}) ${t.getAttribute("transform") || ""}`)));
  overlay();
  save({ edits: sheet.value.edits, items: sheet.value.items });
}
function moveTo(x, y) { const b = selBox.value; moveKeys(selKeys.value, x == null ? 0 : x - b.x0, y == null ? 0 : y - b.y0); }
function hideSel() {
  if (!selKeys.value.length || viewer.value) return; remember(); const sh = sheet.value;
  selKeys.value.forEach(key => { if (isItem(key)) sh.items = (sh.items || []).filter(x => "item:" + x.id !== key); else editOf(key).hide = true; });
  selKeys.value = []; save({ edits: sh.edits, items: sh.items });
}
function resetSel() { const key = selKeys.value[0]; if (!key || !sheet.value.edits) return; remember(); delete sheet.value.edits[key]; save({ edits: sheet.value.edits }); }
function showHidden() {
  const e = sheet.value?.edits || {}; let n = 0; remember();
  Object.values(e).forEach(x => { if (x.hide) { delete x.hide; n++; } });
  notice.value = n ? `Возвращено надписей: ${n}` : "Скрытых надписей нет"; if (n) save({ edits: e });
}
function resetAll() { askReset.value = false; remember(); selKeys.value = []; save({ edits: {}, items: [] }); }
function alignSel(mode) {
  const keys = selKeys.value, bs = keys.map(key => ({ key, b: keyBox(key) })).filter(x => x.b); if (!bs.length) return;
  const to = bs.length === 1 ? { x0: 0, y0: 0, x1: view.w, y1: view.h } : union(bs.map(x => x.b)), out = [];
  if (mode === "dx" || mode === "dy") {                  // равные промежутки между надписями, крайние стоят на месте
    const ax = mode === "dx" ? "x" : "y", s = [...bs].sort((a, b) => a.b[ax + "0"] - b.b[ax + "0"]);
    const span = s[s.length - 1].b[ax + "1"] - s[0].b[ax + "0"], sum = s.reduce((a, x) => a + x.b[ax + "1"] - x.b[ax + "0"], 0), gap = (span - sum) / (s.length - 1);
    let at = s[0].b[ax + "0"];
    s.forEach(x => { const d = at - x.b[ax + "0"]; out.push([x.key, ax === "x" ? d : 0, ax === "y" ? d : 0]); at += x.b[ax + "1"] - x.b[ax + "0"] + gap; });
  } else bs.forEach(({ key, b }) => {
    const w = b.x1 - b.x0, h = b.y1 - b.y0;
    const dx = { left: to.x0 - b.x0, hcenter: (to.x0 + to.x1 - w) / 2 - b.x0, right: to.x1 - b.x1 }[mode] || 0;
    const dy = { top: to.y0 - b.y0, vcenter: (to.y0 + to.y1 - h) / 2 - b.y0, bottom: to.y1 - b.y1 }[mode] || 0;
    out.push([key, dx, dy]);
  });
  remember();
  out.forEach(([key, dx, dy]) => { if (Math.abs(dx) < .01 && Math.abs(dy) < .01) return; const e = editOf(key);
    if (isItem(key)) { e.x = r2(e.x + dx); e.y = r2(e.y + dy); } else { e.dx = r2((e.dx || 0) + dx); e.dy = r2((e.dy || 0) + dy); } });
  save({ edits: sheet.value.edits, items: sheet.value.items });
}
function pdf() { call(a => a.file("pdf", idx.value)).catch(e => { notice.value = "PDF листа: " + (e.message || e); }); }

/* ---------- мышь: выбор, рамка, перетаскивание, своя надпись, сдвиг листа ---------- */
let space = false;
function hover(e) { if (svg) { cursor.value = toMM(e); drawRulers(); } }
function down(e) {
  stage.value.closest(".alay")?.focus({ preventScroll: true });
  if (e.button === 1 || space) {                         // сдвиг листа: средняя кнопка или пробел
    e.preventDefault(); panning.value = true;
    const c0 = [e.clientX, e.clientY], o0 = [view.ox, view.oy];
    track(e, ev => { view.ox = o0[0] + ev.clientX - c0[0]; view.oy = o0[1] + ev.clientY - c0[1]; drawRulers(); }, () => { panning.value = false; });
    return;
  }
  if (e.button !== 0 || !svg) return;
  const p = toMM(e);
  if (adding.value) {
    if (viewer.value) return;
    const sh = sheet.value, id = Date.now().toString(36); remember();
    sh.items = [...(sh.items || []), { id, x: r2(p.x), y: r2(p.y), text: "Надпись", size: 3.5, font: "ui", color: "#1a1a1a" }];
    adding.value = false; selKeys.value = ["item:" + id]; save({ items: sh.items }); return;
  }
  const gd = e.target.closest?.("[data-guide]");
  if (gd) return guideDrag(e, ...gd.dataset.guide.split(":"));
  const t = e.target.closest?.("text[data-key]"), add = e.shiftKey || e.ctrlKey || e.metaKey;
  if (!t) {                                              // рамка выбора
    const base = add ? [...selKeys.value] : []; if (!add) selKeys.value = [];
    const g = layer("al-marq"), r = el("rect", { fill: "rgba(31,111,235,.08)", stroke: "#1f6feb", "stroke-width": 1, "vector-effect": "non-scaling-stroke", "stroke-dasharray": "4 3" });
    g.appendChild(r); overlay();
    track(e, ev => {
      const q = toMM(ev), b = { x0: Math.min(p.x, q.x), y0: Math.min(p.y, q.y), x1: Math.max(p.x, q.x), y1: Math.max(p.y, q.y) };
      Object.entries({ x: b.x0, y: b.y0, width: b.x1 - b.x0, height: b.y1 - b.y0 }).forEach(([a, v]) => r.setAttribute(a, v));
      const hit = [...new Set(allTexts().filter(x => { const c = boxOf(x); return c.x0 < b.x1 && b.x0 < c.x1 && c.y0 < b.y1 && b.y0 < c.y1; }).map(x => x.dataset.key))];
      selKeys.value = [...new Set([...base, ...hit])]; overlay();
    }, () => { layer("al-marq"); });
    return;
  }
  const key = t.dataset.key;
  if (add) { selKeys.value = selKeys.value.includes(key) ? selKeys.value.filter(x => x !== key) : [...selKeys.value, key]; overlay(); return; }
  if (!selKeys.value.includes(key)) selKeys.value = [key];
  overlay();
  if (viewer.value) return;
  // перетаскивание выбранных: едут за мышью сразу, правка — по отпусканию; цели привязки — прочие надписи, лист, направляющие
  const moving = selKeys.value.flatMap(textsOf), base0 = moving.map(x => x.getAttribute("transform") || ""), box = selBox.value;
  const G = guides(), targets = allTexts().filter(x => !moving.includes(x)).map(boxOf);
  targets.push({ x0: 0, y0: 0, x1: view.w, y1: view.h });
  (G.x || []).forEach(v => targets.push({ x0: v, y0: 0, x1: v, y1: view.h }));
  (G.y || []).forEach(v => targets.push({ x0: 0, y0: v, x1: view.w, y1: v }));
  let d = [0, 0];
  track(e, ev => {
    const q = toMM(ev); d = [q.x - p.x, q.y - p.y];
    const s = ev.altKey ? { dx: 0, dy: 0, guides: [] } : Snap.snap({ x0: box.x0 + d[0], y0: box.y0 + d[1], x1: box.x1 + d[0], y1: box.y1 + d[1] }, targets, Snap.ZONE_PX * 1.5 / view.k);
    d = [d[0] + s.dx, d[1] + s.dy]; smart(s.guides);
    moving.forEach((x, i) => x.setAttribute("transform", `translate(${d[0]} ${d[1]}) ${base0[i]}`));
    overlay(); cursor.value = q;
  }, () => {
    smart(null); moving.forEach((x, i) => x.setAttribute("transform", base0[i]));
    if (Math.hypot(d[0], d[1]) > .15) moveKeys(selKeys.value, r2(d[0]), r2(d[1])); else overlay();
  });
}
function track(e, move, up) {
  const t = e.currentTarget || stage.value; t.setPointerCapture?.(e.pointerId);
  const mv = ev => move(ev), fin = ev => { t.removeEventListener("pointermove", mv); t.removeEventListener("pointerup", fin); t.removeEventListener("pointercancel", fin); up?.(ev); };
  t.addEventListener("pointermove", mv); t.addEventListener("pointerup", fin); t.addEventListener("pointercancel", fin);
}
/* направляющие: от линейки (ax — какая координата: y — горизонтальная с верхней линейки, x — вертикальная с левой) */
function rulerDown(ax, e) {
  if (!svg || viewer.value) return;
  const G = { x: [...(guides().x || [])], y: [...(guides().y || [])] }; G[ax].push(-1000); const i = G[ax].length - 1;
  // захват — на самой линейке (на ней нажали): движение и отпускание над листом приходят к ней же
  track(e, ev => { const q = toMM(ev); G[ax][i] = r1(q[ax]); sheet.value.layGuides = G; overlay(); cursor.value = q; }, ev => {
    const v = r1(toMM(ev)[ax]), lim = ax === "x" ? view.w : view.h;
    G[ax].splice(i, 1); sheet.value.layGuides = { x: [...G.x], y: [...G.y] };
    if (v > 0 && v < lim) { remember(); const N = { x: [...G.x], y: [...G.y] }; N[ax].push(v); save({ layGuides: N }, false); } else overlay();
  });
}
function guideDrag(e, ax, i) {
  if (viewer.value) return;
  i = +i; const G = { x: [...(guides().x || [])], y: [...(guides().y || [])] }, was = G[ax][i];
  if (e.detail === 2) { remember(); G[ax].splice(i, 1); save({ layGuides: G }, false); return; }   // двойной щелчок — убрать
  track(e, ev => { const q = toMM(ev); G[ax][i] = r1(q[ax]); sheet.value.layGuides = G; overlay(); cursor.value = q; }, () => {
    const v = G[ax][i], lim = ax === "x" ? view.w : view.h;
    sheet.value.layGuides = { x: [...G.x], y: [...G.y] }; G[ax][i] = was; remember(); G[ax][i] = v;
    if (!(v > 0 && v < lim)) G[ax].splice(i, 1);           // на линейку или за лист — убрать
    save({ layGuides: G }, false);
  });
}

/* ---------- клавиши ---------- */
function keys(e) {
  const tag = e.target?.tagName || "";
  if (/INPUT|TEXTAREA|WA-INPUT|WA-TEXTAREA|WA-NUMBER-INPUT|WA-SELECT/.test(tag)) return;
  if ((e.ctrlKey || e.metaKey) && (e.code === "KeyZ" || e.code === "KeyY")) { e.preventDefault(); undo(e.code === "KeyY" || e.shiftKey ? 1 : -1); return; }
  if (e.code === "Space") { space = true; e.preventDefault(); return; }
  if (e.key === "Escape") { if (adding.value) adding.value = false; else { selKeys.value = []; overlay(); } return; }
  const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
  if (d && selKeys.value.length) { e.preventDefault(); const s = e.shiftKey ? 5 : .5; moveKeys(selKeys.value, d[0] * s, d[1] * s, "arrow"); return; }
  if ((e.key === "Delete" || e.key === "Backspace") && selKeys.value.length) { e.preventDefault(); hideSel(); }
}
const keyUp = e => { if (e.code === "Space") space = false; };

watch(() => [album.lay, album.layTick], open);
watch(() => [view.k, view.ox, view.oy], () => nextTick(drawRulers));
onMounted(() => {
  addEventListener("keyup", keyUp);
  ro = new ResizeObserver(() => drawRulers()); ro.observe(stage.value);
  open();
});
onBeforeUnmount(() => { removeEventListener("keyup", keyUp); ro?.disconnect(); clearTimeout(timer); album.lay = null; });
</script>

<style>
.alay { display: flex; flex-direction: column; height: 100%; min-height: 0; outline: none; background: var(--g-canvas); }
.alay .al-bar { display: flex; align-items: center; gap: 4px; padding: 6px 10px; border-bottom: 1px solid var(--g-line); background: var(--g-panel); flex-wrap: wrap; }
.alay .al-bar wa-button::part(label) { display: inline-flex; gap: 4px; align-items: center; }
.alay .al-t { font-size: var(--wa-font-size-s); min-width: 0; max-width: 46ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.alay .sp { flex: 1; }
.alay .sep { width: 1px; height: 20px; background: var(--g-line); margin: 0 4px; }
.alay .al-body { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) 300px; }
.alay .al-work { position: relative; min-width: 0; min-height: 0; overflow: hidden; }
.alay .al-corner { position: absolute; left: 0; top: 0; width: 22px; height: 22px; background: var(--g-panel); border-right: 1px solid var(--g-line); border-bottom: 1px solid var(--g-line); z-index: 2; }
.alay .al-rx { position: absolute; left: 22px; top: 0; height: 22px; width: calc(100% - 22px); cursor: s-resize; border-bottom: 1px solid var(--g-line); z-index: 2; }
.alay .al-ry { position: absolute; left: 0; top: 22px; width: 22px; height: calc(100% - 22px); cursor: e-resize; border-right: 1px solid var(--g-line); z-index: 2; }
.alay .al-stage { position: absolute; left: 22px; top: 22px; right: 0; bottom: 0; overflow: hidden; touch-action: none; user-select: none; -webkit-user-select: none; }
.alay .al-stage.busy .al-paper { opacity: .85; }
.alay .al-stage.adding { cursor: crosshair; }
.alay .al-stage.pan { cursor: grabbing; }
.alay .al-paper { position: absolute; background: #fff; box-shadow: 0 3px 18px rgba(11, 31, 51, .16); }
.alay .al-paper svg { display: block; overflow: visible; }
.alay .al-paper .al-tx { cursor: move; }
.alay .al-paper .al-gx { cursor: ew-resize; }
.alay .al-paper .al-gy { cursor: ns-resize; }
.alay .al-empty { position: absolute; inset: 40% 24px auto; text-align: center; color: var(--g-muted); font-size: var(--wa-font-size-s); }
.alay .al-side { border-left: 1px solid var(--g-line); background: var(--g-panel); padding: 10px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
.alay .al-h { margin: 4px 0 0; font-weight: 600; font-size: var(--wa-font-size-s); }
.alay .g2 { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 6px; }
.alay .g2 > * { min-width: 0; }
.alay .crow { display: flex; align-items: center; gap: 8px; font-size: var(--wa-font-size-s); }
.alay .crow .hw { width: 84px; }
.alay .row { display: flex; flex-wrap: wrap; gap: 6px; }
.alay .al-al { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; }
.alay .al-al wa-button::part(base) { width: 100%; }
.alay .hint { margin: 0; color: var(--g-muted); font-size: var(--wa-font-size-xs); line-height: 1.4; }
.alay .al-foot { display: flex; gap: 12px; padding: 3px 10px; border-top: 1px solid var(--g-line); background: var(--g-panel); font-size: var(--wa-font-size-xs); color: var(--g-muted);
  font-variant-numeric: tabular-nums; }
</style>
