// ГРАДО Студия — холст черчения. Мир: метры, ось Y вверх.

const VERSION = "0.2.1";

// любая ошибка интерфейса — на экран, а не молча в консоль
window.addEventListener("error", e => {
  const el = document.getElementById("errbar");
  if (el) {
    el.textContent = `Ошибка интерфейса (${VERSION}): ${e.message} — ${String(e.filename).split("/").pop()}:${e.lineno}`;
    el.style.display = "block";
  }
});

function on(id, event, fn) {
  const el = document.getElementById(id);
  if (!el) { console.warn("нет элемента #" + id); return; }
  el.addEventListener(event, fn);
}

const cv = document.getElementById("cv");
const ctx = cv.getContext("2d");

const STYLES = {
  zone:     { fill: "#faf0bf", stroke: "#b89e59", width: 1,   label: f => f.props.zone_title },
  public:   { fill: "#f7c2c9", stroke: "#bf596b", width: 1.2, label: f => f.props.purpose },
  restrict: { fill: "rgba(245,219,219,.85)", stroke: "#bf5959", width: 1.2, dash: [8, 4] },
  building: { fill: "#f5c76b", stroke: "#8c6626", width: 1,   label: f => f.props.floors },
  redline:  { stroke: "#d91a1a", width: 2.5 },
  boundary: { stroke: "#1c1c1a", width: 2.5, dash: [14, 5, 4, 5] },
  social:   { fill: "#2f6fde", stroke: "#1d4a9e", width: 1.2 },
  parcel:   { stroke: "#8a7a5c", width: 0.8, label: f => f.props.cad_num },
};
const Z_ORDER = ["zone", "public", "restrict", "parcel", "building", "redline", "boundary", "social"];
const KIND_NAMES = {
  boundary: "Граница территории", zone: "Функциональная зона",
  restrict: "Ограничение (ЗОУИТ)", building: "Здание", public: "Зона нежилых ОКС",
  redline: "Красная линия", social: "Объект социнфраструктуры",
  parcel: "Земельный участок (ЕГРН)",
};

const state = {
  features: [], tool: "select", selected: null,
  drawing: null, drag: null, snapOn: true, snapHit: null,
  view: { k: 1.1, tx: 120, ty: 0 },
  undo: [], redo: [], nextId: 1, mouse: null,
  edit: null,      // {f, vi | "body", last, moved}
  measure: null,   // {a, b|null}
};

function featurePts(f) { return f.ring || f.line || [f.point]; }
function selectedFeature() { return state.features.find(x => x.id === state.selected); }
function vertexAt(f, wx, wy) {
  const tolW = 8 / state.view.k;
  const pts = featurePts(f);
  for (let i = 0; i < pts.length; i++)
    if (Math.hypot(pts[i][0] - wx, pts[i][1] - wy) < tolW) return i;
  return null;
}

// ---------- координаты ----------
function w2s(x, y) { return [state.view.tx + x * state.view.k, state.view.ty - y * state.view.k]; }
function s2w(sx, sy) { return [(sx - state.view.tx) / state.view.k, (state.view.ty - sy) / state.view.k]; }

function resize() {
  const dpr = window.devicePixelRatio || 1;
  const r = cv.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return;  // панель ещё без layout
  cv.width = r.width * dpr; cv.height = r.height * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (state.features.length && !state._fitted) {
    state._fitted = true;
    fitView();
    return;
  }
  draw();
}
window.addEventListener("resize", resize);
new ResizeObserver(resize).observe(cv);

// ---------- сетка и привязки ----------
function gridStep() {
  for (const g of [1, 2, 5, 10, 20, 50, 100, 200, 500])
    if (g * state.view.k >= 26) return g;
  return 1000;
}

function snapPoints(excludeId) {
  const pts = [];
  for (const f of state.features) {
    if (f.id === excludeId) continue;
    const chains = f.ring ? [f.ring] : f.line ? [f.line] : [[f.point]];
    for (const chain of chains) {
      chain.forEach(p => pts.push({ p, kind: "вершина" }));
      for (let i = 0; i + 1 < chain.length; i++)
        pts.push({ p: [(chain[i][0] + chain[i + 1][0]) / 2, (chain[i][1] + chain[i + 1][1]) / 2], kind: "середина" });
      if (f.ring && chain.length > 2)
        pts.push({ p: [(chain[0][0] + chain[chain.length - 1][0]) / 2, (chain[0][1] + chain[chain.length - 1][1]) / 2], kind: "середина" });
    }
  }
  return pts;
}

function snap(wx, wy, excludeId) {
  if (!state.snapOn) return { p: [wx, wy], kind: null };
  const tolW = 9 / state.view.k;
  let best = null;
  for (const c of snapPoints(excludeId)) {
    const d = Math.hypot(c.p[0] - wx, c.p[1] - wy);
    if (d < tolW && (!best || d < best.d)) best = { ...c, d };
  }
  if (best) return best;
  const g = gridStep() / 2;
  return { p: [Math.round(wx / g) * g, Math.round(wy / g) * g], kind: "сетка" };
}

// ---------- геометрия ----------
function ringArea(ring) {
  let s = 0;
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i], [x2, y2] = ring[(i + 1) % ring.length];
    s += x1 * y2 - x2 * y1;
  }
  return Math.abs(s) / 2;
}
function lineLen(line) {
  let s = 0;
  for (let i = 0; i + 1 < line.length; i++) s += Math.hypot(line[i + 1][0] - line[i][0], line[i + 1][1] - line[i][1]);
  return s;
}
function pointInRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function nearChain(x, y, chain, tolW) {
  for (let i = 0; i + 1 < chain.length; i++) {
    const [ax, ay] = chain[i], [bx, by] = chain[i + 1];
    const l2 = (bx - ax) ** 2 + (by - ay) ** 2;
    const t = l2 ? Math.max(0, Math.min(1, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / l2)) : 0;
    if (Math.hypot(x - (ax + t * (bx - ax)), y - (ay + t * (by - ay))) < tolW) return true;
  }
  return false;
}

function hitTest(wx, wy) {
  const tolW = 7 / state.view.k;
  for (const kind of [...Z_ORDER].reverse()) {
    for (let i = state.features.length - 1; i >= 0; i--) {
      const f = state.features[i];
      if (f.kind !== kind) continue;
      if (f.point && Math.hypot(f.point[0] - wx, f.point[1] - wy) < tolW + 4 / state.view.k) return f;
      if (f.line && nearChain(wx, wy, f.line, tolW)) return f;
      if (f.ring && (kind === "boundary" ? nearChain(wx, wy, [...f.ring, f.ring[0]], tolW)
                                         : pointInRing(wx, wy, f.ring))) return f;
    }
  }
  return null;
}

// ---------- отрисовка ----------
function drawChain(chain, close) {
  ctx.beginPath();
  const [sx, sy] = w2s(...chain[0]);
  ctx.moveTo(sx, sy);
  for (let i = 1; i < chain.length; i++) ctx.lineTo(...w2s(...chain[i]));
  if (close) ctx.closePath();
}

function draw() {
  const w = cv.clientWidth, h = cv.clientHeight;
  ctx.clearRect(0, 0, w, h);
  // сетка
  const g = gridStep();
  const [wx0, wy1] = s2w(0, 0), [wx1, wy0] = s2w(w, h);
  ctx.lineWidth = 1;
  for (let x = Math.floor(wx0 / g) * g; x <= wx1; x += g) {
    ctx.strokeStyle = (Math.round(x / g) % 5 === 0) ? "#e7e5e0" : "#f3f2ee";
    ctx.beginPath(); ctx.moveTo(...w2s(x, wy0)); ctx.lineTo(...w2s(x, wy1)); ctx.stroke();
  }
  for (let y = Math.floor(wy0 / g) * g; y <= wy1; y += g) {
    ctx.strokeStyle = (Math.round(y / g) % 5 === 0) ? "#e7e5e0" : "#f3f2ee";
    ctx.beginPath(); ctx.moveTo(...w2s(wx0, y)); ctx.lineTo(...w2s(wx1, y)); ctx.stroke();
  }
  // объекты
  for (const kind of Z_ORDER) {
    for (const f of state.features) {
      if (f.kind !== kind) continue;
      const st = STYLES[kind];
      ctx.setLineDash(st.dash || []);
      ctx.lineWidth = st.width; ctx.strokeStyle = st.stroke || "#000";
      if (f.point) {
        const [sx, sy] = w2s(...f.point);
        ctx.beginPath(); ctx.arc(sx, sy, 6, 0, 7); ctx.fillStyle = st.fill; ctx.fill(); ctx.stroke();
      } else {
        if (kind === "redline" && (f.props.radius || 0) > 0 && f.line.length > 2) {
          // сопряжение углов дугами (как Path.fillet_polyline в ядре)
          ctx.beginPath();
          ctx.moveTo(...w2s(...f.line[0]));
          for (let i = 1; i < f.line.length - 1; i++)
            ctx.arcTo(...w2s(...f.line[i]), ...w2s(...f.line[i + 1]),
                      f.props.radius * state.view.k);
          ctx.lineTo(...w2s(...f.line[f.line.length - 1]));
        } else {
          drawChain(f.ring || f.line, !!f.ring);
        }
        if (st.fill && f.ring) { ctx.fillStyle = st.fill; ctx.fill(); }
        ctx.stroke();
      }
      ctx.setLineDash([]);
      if (st.label && f.ring) {
        const c = f.ring.reduce((a, p) => [a[0] + p[0] / f.ring.length, a[1] + p[1] / f.ring.length], [0, 0]);
        const v = st.label(f);
        if (v !== undefined && v !== "") {
          ctx.fillStyle = "#5c5a54"; ctx.font = "11px sans-serif"; ctx.textAlign = "center";
          ctx.fillText(String(v), ...w2s(...c));
        }
      }
      if (f.id === state.selected) {
        ctx.strokeStyle = "#2f6fde"; ctx.lineWidth = 1.5; ctx.setLineDash([4, 3]);
        if (f.point) { const [sx, sy] = w2s(...f.point); ctx.strokeRect(sx - 9, sy - 9, 18, 18); }
        else { drawChain(f.ring || f.line, !!f.ring); ctx.stroke(); }
        ctx.setLineDash([]);
        for (const p of (f.ring || f.line || [f.point])) {
          const [sx, sy] = w2s(...p);
          ctx.fillStyle = "#fff"; ctx.strokeStyle = "#2f6fde"; ctx.lineWidth = 1.2;
          ctx.fillRect(sx - 3, sy - 3, 6, 6); ctx.strokeRect(sx - 3, sy - 3, 6, 6);
        }
      }
    }
  }
  // черчение в процессе
  if (state.drawing && state.drawing.pts.length) {
    const st = STYLES[state.tool];
    ctx.strokeStyle = st.stroke || "#000"; ctx.lineWidth = st.width; ctx.setLineDash([5, 4]);
    const pts = state.mouse ? [...state.drawing.pts, state.mouse] : state.drawing.pts;
    drawChain(pts, false); ctx.stroke(); ctx.setLineDash([]);
  }
  if (state.drag && state.drag.rect) {
    const { a, b } = state.drag;
    ctx.strokeStyle = STYLES.building.stroke; ctx.fillStyle = STYLES.building.fill + "88";
    const [sx1, sy1] = w2s(...a), [sx2, sy2] = w2s(...b);
    ctx.fillRect(Math.min(sx1, sx2), Math.min(sy1, sy2), Math.abs(sx2 - sx1), Math.abs(sy2 - sy1));
    ctx.strokeRect(Math.min(sx1, sx2), Math.min(sy1, sy2), Math.abs(sx2 - sx1), Math.abs(sy2 - sy1));
  }
  // измерение
  if (state.measure) {
    const a = state.measure.a;
    const b = state.measure.b || state.mouse;
    if (b) {
      ctx.strokeStyle = "#2f6fde"; ctx.lineWidth = 1.2; ctx.setLineDash([6, 3]);
      drawChain([a, b], false); ctx.stroke(); ctx.setLineDash([]);
      const dist = Math.hypot(b[0] - a[0], b[1] - a[1]);
      const [mx, my] = w2s((a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
      ctx.fillStyle = "#2f6fde"; ctx.font = "600 12px sans-serif"; ctx.textAlign = "center";
      ctx.fillText(dist.toFixed(1) + " м", mx, my - 6);
    }
  }
  // маркер привязки
  if (state.snapHit && state.snapHit.kind && state.tool !== "select") {
    const [sx, sy] = w2s(...state.snapHit.p);
    ctx.strokeStyle = "#12a150"; ctx.lineWidth = 1.5;
    ctx.strokeRect(sx - 5, sy - 5, 10, 10);
  }
  document.getElementById("st-grid").textContent = `сетка ${g} м`;
}

function fitView() {
  const pts = [];
  for (const f of state.features)
    for (const p of (f.ring || f.line || [f.point])) pts.push(p);
  if (!pts.length) return;
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const w = cv.clientWidth, h = cv.clientHeight;
  if (w < 2 || h < 2) return;
  const dx = Math.max(Math.max(...xs) - Math.min(...xs), 10);
  const dy = Math.max(Math.max(...ys) - Math.min(...ys), 10);
  state.view.k = Math.max(0.05, Math.min(40, Math.min(w / dx, h / dy) * 0.82));
  state.view.tx = w / 2 - (Math.min(...xs) + dx / 2) * state.view.k;
  state.view.ty = h / 2 + (Math.min(...ys) + dy / 2) * state.view.k;
  draw();
}

// ---------- история ----------
function snapshot() {
  state.undo.push(JSON.stringify(state.features));
  if (state.undo.length > 100) state.undo.shift();
  state.redo = [];
}
function undo() {
  if (!state.undo.length) return;
  state.redo.push(JSON.stringify(state.features));
  state.features = JSON.parse(state.undo.pop());
  state.selected = null; afterChange();
}
function redo() {
  if (!state.redo.length) return;
  state.undo.push(JSON.stringify(state.features));
  state.features = JSON.parse(state.redo.pop());
  state.selected = null; afterChange();
}

// ---------- ТЭП ----------
let tepTimer = null;
function params() {
  return { density: +document.getElementById("p-density").value || 25,
           ratio_zh: +document.getElementById("p-ratio").value || 80 };
}
function refreshTep() {
  clearTimeout(tepTimer);
  document.getElementById("tep-status").textContent = "…";
  tepTimer = setTimeout(async () => {
    try {
      const r = await fetch("/api/tep", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ features: state.features, params: params() }) });
      const data = await r.json();
      renderTep(data);
      document.getElementById("tep-status").textContent = "";
      document.getElementById("st-core").textContent = `ядро: ок · v${VERSION}`;
    } catch (e) {
      document.getElementById("tep-status").textContent = "нет связи с ядром";
      document.getElementById("st-core").textContent = "ядро: НЕДОСТУПНО";
    }
  }, 250);
}
function renderTep(data) {
  const fact = document.getElementById("tep-fact");
  fact.innerHTML = `<div class="tep-row"><span>По посадке зданий</span><span></span></div>
    <div class="tep-row"><span>СПП факт</span><span class="v">${data.fact.spp} <small>тыс. м²</small></span></div>
    <div class="tep-row"><span>Плотность факт</span><span class="v">${data.fact.density} <small>тыс. м²/га</small></span></div>`;
  const body = document.getElementById("tep-body");
  body.classList.remove("muted");
  let html = "", group = null;
  for (const r of data.results) {
    if (r.group !== group) { group = r.group; html += `<div class="tep-group">${group}</div>`; }
    html += `<div class="tep-row"><span>${r.title}</span><span class="v">${r.value} <small>${r.unit}</small></span></div>`;
  }
  body.innerHTML = html;
}

// ---------- свойства ----------
function renderProps() {
  const el = document.getElementById("props-body");
  const f = state.features.find(x => x.id === state.selected);
  if (!f) { el.className = "muted"; el.textContent = "Ничего не выбрано"; return; }
  el.className = "";
  let metric = "";
  if (f.ring) {
    metric = `площадь: ${(ringArea(f.ring) / 10000).toFixed(2)} га`;
    if (f.kind === "building")
      metric += ` · СПП: ${(ringArea(f.ring) * (f.props.floors || 1) / 1000).toFixed(1)} тыс. м²`;
  }
  if (f.line) metric = `длина: ${lineLen(f.line).toFixed(0)} м`;
  let extra = "";
  if (f.kind === "building")
    extra = `<label>Этажность<input type="number" id="f-floors" value="${f.props.floors}" min="1" max="75"></label>`;
  if (f.kind === "redline")
    extra = `<label>Радиус сопряжения, м<input type="number" id="f-radius" value="${f.props.radius || 0}" min="0" max="500" step="5"></label>`;
  if (f.kind === "zone")
    extra = `<label>Наименование зоны<input type="text" id="f-zone" value="${f.props.zone_title}"></label>`;
  if (f.kind === "public")
    extra = `<label>Назначение<input type="text" id="f-purpose" value="${f.props.purpose}"></label>`;
  el.innerHTML = `<div class="kind">${KIND_NAMES[f.kind]}</div>
    <div class="metric">${metric}</div>${extra}
    <button class="danger" id="f-del">Удалить (Del)</button>`;
  const bind = (id, key, cast) => {
    const inp = document.getElementById(id);
    if (inp) inp.addEventListener("change", () => {
      snapshot(); f.props[key] = cast ? cast(inp.value) : inp.value; afterChange();
    });
  };
  bind("f-floors", "floors", v => Math.max(1, parseInt(v) || 9));
  bind("f-radius", "radius", v => Math.max(0, parseFloat(v) || 0));
  bind("f-zone", "zone_title");
  bind("f-purpose", "purpose");
  document.getElementById("f-del").onclick = deleteSelected;
}
function deleteSelected() {
  if (state.selected == null) return;
  snapshot();
  state.features = state.features.filter(f => f.id !== state.selected);
  state.selected = null; afterChange();
}
function persist() {
  try {
    localStorage.setItem("grado_studio_v1", JSON.stringify({
      features: state.features, nextId: state.nextId,
      name: document.getElementById("project-name").value,
      density: document.getElementById("p-density").value,
      ratio: document.getElementById("p-ratio").value,
    }));
  } catch (e) { /* приватный режим — работаем без сохранения */ }
}
function afterChange() { draw(); renderProps(); refreshTep(); persist(); }

// ---------- добавление фигур ----------
const DEFAULT_PROPS = {
  boundary: () => ({}), restrict: () => ({ kind: "охранная зона" }),
  zone: () => ({ zone_title: "Ж-" + (state.features.filter(f => f.kind === "zone").length + 1) }),
  building: () => ({ floors: 9, purpose: "МКД" }),
  public: () => ({ purpose: "Общественный центр" }),
  redline: () => ({ radius: 0 }), social: () => ({ kind: "ОО+ДОО", capacity: 750 }),
  measure: () => ({}), parcel: () => ({}),
};
function addFeature(kind, geom) {
  snapshot();
  const f = { id: state.nextId++, kind, props: DEFAULT_PROPS[kind](), ...geom };
  state.features.push(f);
  state.selected = f.id;
  afterChange();
}
function finishDrawing() {
  const d = state.drawing;
  if (!d) return;
  const isPoly = state.tool !== "redline";
  if (isPoly && d.pts.length >= 3) addFeature(state.tool, { ring: d.pts });
  else if (!isPoly && d.pts.length >= 2) addFeature("redline", { line: d.pts });
  state.drawing = null; draw();
}

// ---------- события мыши ----------
cv.addEventListener("contextmenu", e => e.preventDefault());
cv.addEventListener("mousedown", e => {
  const [wxr, wyr] = s2w(e.offsetX, e.offsetY);
  if (e.button === 2 || e.button === 1 || (e.button === 0 && spaceDown)) {
    state.pan = { sx: e.offsetX, sy: e.offsetY, tx: state.view.tx, ty: state.view.ty };
    return;
  }
  if (e.button !== 0) return;
  const s = snap(wxr, wyr);
  if (state.tool === "select") {
    const cur = selectedFeature();
    if (cur) {
      const vi = vertexAt(cur, wxr, wyr);
      if (vi != null) { state.edit = { f: cur, vi, moved: false }; return; }
    }
    const f = hitTest(wxr, wyr);
    state.selected = f ? f.id : null;
    if (f) state.edit = { f, vi: "body", last: [wxr, wyr], moved: false };
    draw(); renderProps();
  } else if (state.tool === "measure") {
    if (!state.measure || state.measure.b) state.measure = { a: s.p, b: null };
    else state.measure.b = s.p;
    draw();
  } else if (state.tool === "social") {
    addFeature("social", { point: s.p });
  } else if (state.tool === "building") {
    state.drag = { a: s.p, b: s.p, rect: true };
  } else {
    if (!state.drawing) state.drawing = { pts: [] };
    const first = state.drawing.pts[0];
    if (first && state.tool !== "redline" &&
        Math.hypot(first[0] - s.p[0], first[1] - s.p[1]) < 9 / state.view.k) {
      finishDrawing();
    } else {
      state.drawing.pts.push(s.p);
      draw();
    }
  }
});
cv.addEventListener("mousemove", e => {
  const [wx, wy] = s2w(e.offsetX, e.offsetY);
  document.getElementById("st-coords").textContent = `x: ${wx.toFixed(1)}  y: ${wy.toFixed(1)} м`;
  if (state.pan) {
    state.view.tx = state.pan.tx + (e.offsetX - state.pan.sx);
    state.view.ty = state.pan.ty + (e.offsetY - state.pan.sy);
    draw(); return;
  }
  if (state.edit) {
    const ed = state.edit;
    if (!ed.moved) { snapshot(); ed.moved = true; }
    if (ed.vi === "body") {
      const dx = wx - ed.last[0], dy = wy - ed.last[1];
      ed.last = [wx, wy];
      for (const p of featurePts(ed.f)) { p[0] += dx; p[1] += dy; }
    } else {
      const s = snap(wx, wy, ed.f.id);
      state.snapHit = s;
      const pts = featurePts(ed.f);
      pts[ed.vi][0] = s.p[0]; pts[ed.vi][1] = s.p[1];
    }
    draw(); return;
  }
  const s = snap(wx, wy);
  state.snapHit = s;
  document.getElementById("st-snap").textContent = s.kind ? `привязка: ${s.kind}` : "";
  if (state.drag && state.drag.rect) { state.drag.b = s.p; draw(); return; }
  state.mouse = s.p;
  if (state.tool === "select") {
    const cur = selectedFeature();
    cv.style.cursor = (cur && vertexAt(cur, wx, wy) != null) ? "move"
      : hitTest(wx, wy) ? "pointer" : "default";
  }
  if (state.drawing || state.tool !== "select") draw();
});
cv.addEventListener("mouseup", e => {
  if (state.pan) { state.pan = null; return; }
  if (state.edit) {
    const moved = state.edit.moved;
    state.edit = null;
    if (moved) afterChange();
    return;
  }
  if (state.drag && state.drag.rect) {
    const { a, b } = state.drag;
    state.drag = null;
    if (Math.abs(a[0] - b[0]) > 1 && Math.abs(a[1] - b[1]) > 1) {
      addFeature("building", { ring: [[a[0], a[1]], [b[0], a[1]], [b[0], b[1]], [a[0], b[1]]] });
    } else draw();
  }
});
cv.addEventListener("dblclick", e => { e.preventDefault(); finishDrawing(); });
cv.addEventListener("wheel", e => {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
  const [wx, wy] = s2w(e.offsetX, e.offsetY);
  state.view.k = Math.min(40, Math.max(0.05, state.view.k * factor));
  state.view.tx = e.offsetX - wx * state.view.k;
  state.view.ty = e.offsetY + wy * state.view.k;
  draw();
}, { passive: false });

// ---------- клавиатура ----------
let spaceDown = false;
const TOOL_KEYS = { v: "select", g: "boundary", z: "zone", o: "restrict",
                    b: "building", p: "public", l: "redline", s: "social",
                    m: "measure" };
document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT") return;
  if (e.code === "Space") { spaceDown = true; e.preventDefault(); return; }
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
    e.preventDefault(); e.shiftKey ? redo() : undo(); return;
  }
  if (e.key === "Enter") { finishDrawing(); return; }
  if (e.key === "Escape") {
    state.drawing = null; state.drag = null; state.measure = null; draw(); return;
  }
  if (e.key === "Delete" || e.key === "Backspace") { deleteSelected(); return; }
  if (e.key.toLowerCase() === "x") { toggleSnap(); return; }
  if (e.key.toLowerCase() === "f") { fitView(); return; }
  const tool = TOOL_KEYS[e.key.toLowerCase()];
  if (tool) setTool(tool);
});
document.addEventListener("keyup", e => { if (e.code === "Space") spaceDown = false; });

// ---------- инструменты и кнопки ----------
function setTool(tool) {
  state.tool = tool; state.drawing = null; state.drag = null;
  state.edit = null;
  if (tool !== "measure") state.measure = null;
  document.querySelectorAll("#toolbar button[data-tool]").forEach(
    b => b.classList.toggle("active", b.dataset.tool === tool));
  cv.style.cursor = tool === "select" ? "default" : "crosshair";
  draw();
}
document.querySelectorAll("#toolbar button[data-tool]").forEach(
  b => b.addEventListener("click", () => setTool(b.dataset.tool)));
function toggleSnap() {
  state.snapOn = !state.snapOn;
  document.getElementById("btn-snap").classList.toggle("active", state.snapOn);
}
on("btn-snap", "click", toggleSnap);
on("btn-undo", "click", undo);
on("btn-redo", "click", redo);
on("btn-clear", "click", () => {
  snapshot(); state.features = []; state.selected = null; afterChange();
});
on("p-density", "change", refreshTep);
on("p-ratio", "change", refreshTep);

async function download(url, filename) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ features: state.features, params: params(),
                           name: document.getElementById("project-name").value }) });
  if (!r.ok) { alert("Ошибка сборки: " + (await r.text()).slice(0, 200)); return; }
  const blob = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  if (filename.endsWith(".pdf")) window.open(a.href, "_blank");
  a.download = filename; a.click();
}
on("btn-album", "click", () => download("/api/album", "grado_agk_album.pdf"));
on("btn-grado", "click", () => download("/api/grado", "project.grado"));

// импорт захвата НСПД (JSON браузерного моста GRADO)
on("btn-nspd", "click", () => document.getElementById("nspd-file").click());
on("nspd-file", "change", async e => {
  const file = e.target.files[0];
  if (!file) return;
  e.target.value = "";
  try {
    const payload = JSON.parse(await file.text());
    const r = await fetch("/api/import-nspd", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload }) });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    if (!data.features.length) { alert("В захвате нет полигонов НСПД"); return; }
    snapshot();
    for (const f of data.features)
      state.features.push({ id: state.nextId++, ...f });
    state.selected = null;
    afterChange();
    fitView();
  } catch (err) {
    alert("Не удалось импортировать захват: " + String(err).slice(0, 200));
  }
});

// ---------- демо-наполнение ----------
on("btn-demo", "click", () => {
  snapshot();
  const B = [[0, 0], [650, 0], [650, 180], [520, 180], [520, 420], [300, 420],
             [300, 560], [60, 560], [60, 300], [0, 300]];
  state.features = [];
  state.nextId = 1;
  const add = (kind, geom, props = {}) => state.features.push(
    { id: state.nextId++, kind, props: { ...DEFAULT_PROPS[kind](), ...props }, ...geom });
  add("boundary", { ring: B });
  add("zone", { ring: [[60, 180], [520, 180], [520, 420], [60, 420]] }, { zone_title: "Ж-1" });
  add("zone", { ring: [[0, 0], [520, 0], [520, 180], [0, 180]] }, { zone_title: "О-1" });
  add("restrict", { ring: [[520, 0], [650, 0], [650, 180], [520, 180]] });
  for (let r = 0; r < 3; r++) for (let c = 0; c < 5; c++)
    add("building", { ring: [[90 + c * 82, 215 + r * 62], [120 + c * 82, 215 + r * 62],
                             [120 + c * 82, 232 + r * 62], [90 + c * 82, 232 + r * 62]] },
        { floors: [9, 12, 14, 12, 9][c] });
  add("public", { ring: [[90, 40], [220, 40], [220, 130], [90, 130]] });
  add("redline", { line: [[-30, 190], [400, 190], [400, 590]] });
  add("social", { point: [470, 350] });
  state.selected = null;
  afterChange();
  fitView();
});

// ---------- старт ----------
(function restore() {
  try {
    const raw = localStorage.getItem("grado_studio_v1");
    if (!raw) return;
    const d = JSON.parse(raw);
    state.features = d.features || [];
    state.nextId = d.nextId || 1;
    if (d.name) document.getElementById("project-name").value = d.name;
    if (d.density) document.getElementById("p-density").value = d.density;
    if (d.ratio) document.getElementById("p-ratio").value = d.ratio;
  } catch (e) { /* повреждённое сохранение игнорируем */ }
})();
on("project-name", "change", persist);
window.studio = { state, addFeature, refreshTep, fitView };  // для автотестов
setTool("select");
requestAnimationFrame(resize);
refreshTep();
