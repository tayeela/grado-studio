// ГРАДО Студия — холст черчения. Мир: метры, ось Y вверх.

const VERSION = "0.5.0";

// любая ошибка интерфейса — на экран, а не молча в консоль
window.addEventListener("error", e => {
  if (/ResizeObserver loop/.test(e.message || "")) return; // безобидное предупреждение браузера
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
  drawing: null, drag: null, pan: null, edit: null, measure: null,
  snapHit: null, guides: [], typed: "", mouse: null,
  view: { k: 1.1, tx: 120, ty: 0 },
  undo: [], redo: [], nextId: 1,
  gridShow: true, gridSnap: true, osnap: true, gridMode: "auto",
  hidden: {},                    // kind -> true (слой выключен)
  _fitted: false, _ix: null,
};

function isHidden(f) { return !!state.hidden[f.kind]; }

let shiftDown = false, spaceDown = false;

// ---------- координаты ----------
function w2s(x, y) { return [state.view.tx + x * state.view.k, state.view.ty - y * state.view.k]; }
function s2w(sx, sy) { return [(sx - state.view.tx) / state.view.k, (state.view.ty - sy) / state.view.k]; }
function featurePts(f) { return f.ring || f.line || [f.point]; }
function selectedFeature() { return state.features.find(x => x.id === state.selected); }
function vertexAt(f, wx, wy) {
  const tolW = 8 / state.view.k;
  const pts = featurePts(f);
  for (let i = 0; i < pts.length; i++)
    if (Math.hypot(pts[i][0] - wx, pts[i][1] - wy) < tolW) return i;
  return null;
}

// Safari отмечен глюками ResizeObserver + <canvas>: назначение canvas.width
// сбрасывает битмап, и если наблюдатель перевызывает resize() синхронно
// в цикле (даже когда CSS-размер элемента фактически не изменился),
// холст может гаситься быстрее, чем успевает перерисоваться — экран
// «на секунду показывает точки сетки и белеет». Защита: (1) менять
// битмап только когда размер реально изменился; (2) события наблюдателя
// схлопывать через requestAnimationFrame, чтобы разорвать возможный
// синхронный цикл переисчисления layout.
let lastBufW = 0, lastBufH = 0;
function resize() {
  const dpr = window.devicePixelRatio || 1;
  const r = cv.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return;
  const w = Math.round(r.width * dpr), h = Math.round(r.height * dpr);
  if (w === lastBufW && h === lastBufH) { draw(); return; }
  lastBufW = w; lastBufH = h;
  cv.width = w; cv.height = h;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (state.features.length && !state._fitted) {
    state._fitted = true;
    fitView();
    return;
  }
  draw();
}
window.addEventListener("resize", resize);
let roPending = false;
new ResizeObserver(() => {
  if (roPending) return;
  roPending = true;
  requestAnimationFrame(() => { roPending = false; resize(); });
}).observe(cv);

// ---------- сетка ----------
function gridStep() {
  if (state.gridMode !== "auto") return +state.gridMode;
  for (const g of [1, 2, 5, 10, 20, 50, 100, 200, 500])
    if (g * state.view.k >= 22) return g;
  return 1000;
}

// ---------- подложка (тайлы XYZ) ----------
// Локальные метры холста → долгота/широта: приближение локальной
// касательной плоскости вокруг ORIGIN (см. crs.ORIGIN_LON/LAT в ядре).
// На масштабе территории (км, не сотни км) погрешность на два порядка
// меньше пиксела тайла — для фоновой подложки этого достаточно; точная
// проекция (обратный UTM) считается на сервере и используется только
// для получения самой точки ORIGIN.
const basemap = {
  on: false, opacity: 0.85, originLon: null, originLat: null, attribution: "",
  mPerDegLon: null, mPerDegLat: 111320,
  cache: new Map(),   // "z/x/y" -> {img, loaded, failed}
};

async function initBasemap() {
  try {
    const r = await fetch("/api/basemap-info");
    const d = await r.json();
    basemap.originLon = d.origin_lon;
    basemap.originLat = d.origin_lat;
    basemap.attribution = d.attribution;
    basemap.mPerDegLon = 111320 * Math.cos(d.origin_lat * Math.PI / 180);
  } catch (e) { /* сервер без /api/basemap-info — подложка недоступна */ }
}

function localToLonLat(x, y) {
  return [basemap.originLon + x / basemap.mPerDegLon,
          basemap.originLat + y / basemap.mPerDegLat];
}
function lonLatToLocal(lon, lat) {
  return [(lon - basemap.originLon) * basemap.mPerDegLon,
          (lat - basemap.originLat) * basemap.mPerDegLat];
}
function lonToTileX(lon, z) { return (lon + 180) / 360 * 2 ** z; }
function latToTileY(lat, z) {
  const r = lat * Math.PI / 180;
  return (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * 2 ** z;
}
function tileXToLon(tx, z) { return tx / 2 ** z * 360 - 180; }
function tileYToLat(ty, z) {
  const n = Math.PI - 2 * Math.PI * ty / 2 ** z;
  return 180 / Math.PI * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
}

function tileImage(z, x, y) {
  const key = `${z}/${x}/${y}`;
  let e = basemap.cache.get(key);
  if (!e) {
    e = { img: new Image(), loaded: false, failed: false };
    e.img.onload = () => { e.loaded = true; draw(); };
    e.img.onerror = () => { e.failed = true; };
    e.img.src = `/api/tiles/${z}/${x}/${y}.png`;
    basemap.cache.set(key, e);
  }
  return e;
}

function drawBasemap(w, h) {
  if (!basemap.on || basemap.originLon == null) return;
  const [wx0, wy1] = s2w(0, 0), [wx1, wy0] = s2w(w, h);
  const [lon0, lat0] = localToLonLat(wx0, wy0);
  const [lon1, lat1] = localToLonLat(wx1, wy1);
  // подбор зума: метры на тайл-пиксель ≈ метры на экранный пиксель
  const mppTile0 = 156543.03392804097 * Math.cos(basemap.originLat * Math.PI / 180);
  let z = Math.round(Math.log2(mppTile0 * state.view.k));
  z = Math.max(1, Math.min(19, z));

  const txMin = Math.floor(lonToTileX(Math.min(lon0, lon1), z));
  const txMax = Math.floor(lonToTileX(Math.max(lon0, lon1), z));
  const tyMin = Math.floor(latToTileY(Math.max(lat0, lat1), z));
  const tyMax = Math.floor(latToTileY(Math.min(lat0, lat1), z));
  const maxTiles = 2 ** z;
  const budget = 300;  // защита от случайного запроса тысяч тайлов при рывке зума
  let drawn = 0;
  ctx.save();
  ctx.globalAlpha = basemap.opacity;
  for (let ty = tyMin; ty <= tyMax; ty++) {
    for (let tx = txMin; tx <= txMax; tx++) {
      if (++drawn > budget) break;
      const cx = ((tx % maxTiles) + maxTiles) % maxTiles;
      if (ty < 0 || ty >= maxTiles) continue;
      const e = tileImage(z, cx, ty);
      if (!e.loaded) continue;
      const nw = lonLatToLocal(tileXToLon(tx, z), tileYToLat(ty, z));
      const se = lonLatToLocal(tileXToLon(tx + 1, z), tileYToLat(ty + 1, z));
      const [sx0, sy0] = w2s(...nw), [sx1, sy1] = w2s(...se);
      // расширяем на 0.5px — прячет тонкие щели между соседними тайлами
      ctx.drawImage(e.img, sx0 - 0.5, sy0 - 0.5, sx1 - sx0 + 1, sy1 - sy0 + 1);
    }
  }
  ctx.restore();
  ctx.fillStyle = "rgba(255,255,255,.82)";
  ctx.fillRect(6, h - 18, ctx.measureText(basemap.attribution).width + 14, 14);
  ctx.fillStyle = "#5c5a54"; ctx.font = "10px sans-serif"; ctx.textAlign = "left";
  ctx.fillText(basemap.attribution, 10, h - 7);
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
  for (let i = 0; i + 1 < line.length; i++)
    s += Math.hypot(line[i + 1][0] - line[i][0], line[i + 1][1] - line[i][1]);
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
function nearestOnSeg(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const l2 = dx * dx + dy * dy;
  const t = l2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)) : 0;
  return [a[0] + dx * t, a[1] + dy * t];
}
function nearChain(x, y, chain, tolW) {
  for (let i = 0; i + 1 < chain.length; i++) {
    const q = nearestOnSeg([x, y], chain[i], chain[i + 1]);
    if (Math.hypot(x - q[0], y - q[1]) < tolW) return i;
  }
  return null;
}
function segIntersect(a0, a1, b0, b1) {
  const d0 = [a1[0] - a0[0], a1[1] - a0[1]], d1 = [b1[0] - b0[0], b1[1] - b0[1]];
  const det = d0[0] * d1[1] - d0[1] * d1[0];
  if (Math.abs(det) < 1e-12) return null;
  const t = ((b0[0] - a0[0]) * d1[1] - (b0[1] - a0[1]) * d1[0]) / det;
  const u = ((b0[0] - a0[0]) * d0[1] - (b0[1] - a0[1]) * d0[0]) / det;
  if (t < -1e-9 || t > 1 + 1e-9 || u < -1e-9 || u > 1 + 1e-9) return null;
  return [a0[0] + d0[0] * t, a0[1] + d0[1] * t];
}

function featureChains(f) {
  if (f.ring) return [[...f.ring, f.ring[0]]];
  if (f.line) return [f.line];
  return [];
}

// ---------- привязки (уровень CAD) ----------
const SNAP_PRIORITY = { "вершина": 0, "пересечение": 1, "середина": 2, "центр": 3 };

function collectSnapPts(excludeId) {
  const out = [];
  for (const f of state.features) {
    if (f.id === excludeId || isHidden(f)) continue;
    if (f.point) { out.push({ p: f.point, kind: "вершина" }); continue; }
    for (const chain of featureChains(f)) {
      for (let i = 0; i + 1 < chain.length; i++) {
        out.push({ p: chain[i], kind: "вершина" });
        out.push({ p: [(chain[i][0] + chain[i + 1][0]) / 2,
                       (chain[i][1] + chain[i + 1][1]) / 2], kind: "середина" });
      }
    }
    if (f.ring) {
      const xs = f.ring.map(p => p[0]), ys = f.ring.map(p => p[1]);
      out.push({ p: [(Math.min(...xs) + Math.max(...xs)) / 2,
                     (Math.min(...ys) + Math.max(...ys)) / 2], kind: "центр" });
    }
  }
  return out;
}

function intersections() {
  if (state._ix) return state._ix;
  const segs = [];
  for (const f of state.features) {
    if (isHidden(f)) continue;
    for (const chain of featureChains(f))
      for (let i = 0; i + 1 < chain.length; i++)
        segs.push([chain[i], chain[i + 1]]);
  }
  const out = [];
  for (let i = 0; i < segs.length && i < 400; i++)
    for (let j = i + 1; j < segs.length && j < 400; j++) {
      const p = segIntersect(segs[i][0], segs[i][1], segs[j][0], segs[j][1]);
      if (p) out.push(p);
    }
  state._ix = out;
  return out;
}

function snapPoint(wx, wy, excludeId) {
  state.guides = [];
  const tolW = 10 / state.view.k;
  // 1. объектные привязки по приоритету
  if (state.osnap) {
    let best = null;
    for (const c of collectSnapPts(excludeId)) {
      const d = Math.hypot(c.p[0] - wx, c.p[1] - wy);
      if (d > tolW) continue;
      const key = [SNAP_PRIORITY[c.kind], d];
      if (!best || key[0] < best.key[0] || (key[0] === best.key[0] && key[1] < best.key[1]))
        best = { p: [...c.p], kind: c.kind, key };
    }
    for (const p of intersections()) {
      const d = Math.hypot(p[0] - wx, p[1] - wy);
      if (d <= tolW && (!best || best.key[0] > 1 || (best.key[0] === 1 && d < best.key[1])))
        best = { p: [...p], kind: "пересечение", key: [1, d] };
    }
    if (best) return { p: best.p, kind: best.kind };
    // 2. направляющие выравнивания по вершинам
    let gx = null, gy = null;
    for (const c of collectSnapPts(excludeId)) {
      if (c.kind !== "вершина") continue;
      if (Math.abs(c.p[0] - wx) < tolW && (!gx || Math.abs(c.p[0] - wx) < Math.abs(gx.p[0] - wx))) gx = c;
      if (Math.abs(c.p[1] - wy) < tolW && (!gy || Math.abs(c.p[1] - wy) < Math.abs(gy.p[1] - wy))) gy = c;
    }
    if (gx || gy) {
      const p = [gx ? gx.p[0] : wx, gy ? gy.p[1] : wy];
      if (gx) state.guides.push([gx.p, p]);
      if (gy) state.guides.push([gy.p, p]);
      return { p, kind: "выравнивание" };
    }
  }
  // 3. сетка
  if (state.gridSnap) {
    const g = gridStep();
    return { p: [Math.round(wx / g) * g, Math.round(wy / g) * g], kind: "сетка" };
  }
  return { p: [wx, wy], kind: null };
}

function lastDrawingPt() {
  return state.drawing && state.drawing.pts.length
    ? state.drawing.pts[state.drawing.pts.length - 1] : null;
}

function orthoProject(base, wx, wy) {
  // фиксация направления на 0/45/90° (Shift)
  const dx = wx - base[0], dy = wy - base[1];
  const dist = Math.hypot(dx, dy);
  if (dist < 1e-9) return [wx, wy];
  const a = Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4);
  return [base[0] + dist * Math.cos(a), base[1] + dist * Math.sin(a)];
}

function cursorPoint(wx, wy) {
  const base = lastDrawingPt();
  if (shiftDown && base) {
    const [ox, oy] = orthoProject(base, wx, wy);
    if (state.gridSnap) {
      // выравниваем длину по шагу сетки вдоль зафиксированного направления
      const g = gridStep();
      const d = Math.round(Math.hypot(ox - base[0], oy - base[1]) / g) * g;
      const a = Math.atan2(oy - base[1], ox - base[0]);
      return { p: [base[0] + d * Math.cos(a), base[1] + d * Math.sin(a)], kind: "орто" };
    }
    return { p: [ox, oy], kind: "орто" };
  }
  return snapPoint(wx, wy, state.edit ? state.edit.f.id : undefined);
}

// ---------- отрисовка ----------
function drawChain(chain, close) {
  ctx.beginPath();
  ctx.moveTo(...w2s(...chain[0]));
  for (let i = 1; i < chain.length; i++) ctx.lineTo(...w2s(...chain[i]));
  if (close) ctx.closePath();
}

function drawGrid(w, h) {
  if (!state.gridShow) return;
  const g = gridStep();
  const [wx0, wy1] = s2w(0, 0), [wx1, wy0] = s2w(w, h);
  const px = g * state.view.k;
  // крупные линии каждые 5 шагов
  ctx.lineWidth = 1;
  for (let x = Math.floor(wx0 / (g * 5)) * g * 5; x <= wx1; x += g * 5) {
    ctx.strokeStyle = x === 0 ? "#d5d2ca" : "#eceae5";
    ctx.beginPath(); ctx.moveTo(...w2s(x, wy0)); ctx.lineTo(...w2s(x, wy1)); ctx.stroke();
  }
  for (let y = Math.floor(wy0 / (g * 5)) * g * 5; y <= wy1; y += g * 5) {
    ctx.strokeStyle = y === 0 ? "#d5d2ca" : "#eceae5";
    ctx.beginPath(); ctx.moveTo(...w2s(wx0, y)); ctx.lineTo(...w2s(wx1, y)); ctx.stroke();
  }
  // точки в узлах мелкого шага (как в Rayon)
  if (px >= 11) {
    ctx.fillStyle = "#c9c6bd";
    for (let x = Math.floor(wx0 / g) * g; x <= wx1; x += g)
      for (let y = Math.floor(wy0 / g) * g; y <= wy1; y += g) {
        const [sx, sy] = w2s(x, y);
        ctx.fillRect(sx - 0.75, sy - 0.75, 1.5, 1.5);
      }
  }
  document.getElementById("st-grid").textContent =
    `сетка ${g} м${state.gridSnap ? "" : " (без привязки)"}`;
}

function drawSnapMarker() {
  const s = state.snapHit;
  if (!s || !s.kind || state.tool === "select") return;
  const [sx, sy] = w2s(...s.p);
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = "#12a150";
  if (s.kind === "вершина") ctx.strokeRect(sx - 5, sy - 5, 10, 10);
  else if (s.kind === "середина") {
    ctx.beginPath(); ctx.moveTo(sx, sy - 6); ctx.lineTo(sx + 6, sy + 5); ctx.lineTo(sx - 6, sy + 5);
    ctx.closePath(); ctx.stroke();
  } else if (s.kind === "пересечение") {
    ctx.beginPath();
    ctx.moveTo(sx - 5, sy - 5); ctx.lineTo(sx + 5, sy + 5);
    ctx.moveTo(sx - 5, sy + 5); ctx.lineTo(sx + 5, sy - 5); ctx.stroke();
  } else if (s.kind === "центр") {
    ctx.beginPath(); ctx.arc(sx, sy, 5.5, 0, 7); ctx.stroke();
  } else if (s.kind === "выравнивание" || s.kind === "орто") {
    ctx.beginPath(); ctx.arc(sx, sy, 3, 0, 7); ctx.stroke();
  } else if (s.kind === "сетка") {
    ctx.strokeStyle = "#9a978f";
    ctx.beginPath();
    ctx.moveTo(sx - 4, sy); ctx.lineTo(sx + 4, sy);
    ctx.moveTo(sx, sy - 4); ctx.lineTo(sx, sy + 4); ctx.stroke();
  }
}

function draw() {
  const w = cv.clientWidth, h = cv.clientHeight;
  ctx.clearRect(0, 0, w, h);
  drawBasemap(w, h);
  drawGrid(w, h);

  for (const kind of Z_ORDER) {
    if (state.hidden[kind]) continue;
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
        if (v !== undefined && v !== "" && v !== null) {
          ctx.fillStyle = "#5c5a54"; ctx.font = "11px sans-serif"; ctx.textAlign = "center";
          ctx.fillText(String(v), ...w2s(...c));
        }
      }
      if (f.id === state.selected) {
        ctx.strokeStyle = "#2f6fde"; ctx.lineWidth = 1.5; ctx.setLineDash([4, 3]);
        if (f.point) { const [sx, sy] = w2s(...f.point); ctx.strokeRect(sx - 9, sy - 9, 18, 18); }
        else { drawChain(f.ring || f.line, !!f.ring); ctx.stroke(); }
        ctx.setLineDash([]);
        for (const p of featurePts(f)) {
          const [sx, sy] = w2s(...p);
          ctx.fillStyle = "#fff"; ctx.strokeStyle = "#2f6fde"; ctx.lineWidth = 1.2;
          ctx.fillRect(sx - 3, sy - 3, 6, 6); ctx.strokeRect(sx - 3, sy - 3, 6, 6);
        }
      }
    }
  }

  // направляющие выравнивания
  if (state.guides.length) {
    ctx.strokeStyle = "#12a150"; ctx.lineWidth = 0.8; ctx.setLineDash([4, 4]);
    for (const [a, b] of state.guides) { drawChain([a, b], false); ctx.stroke(); }
    ctx.setLineDash([]);
  }

  // черчение в процессе + живой размер
  if (state.drawing && state.drawing.pts.length) {
    const st = STYLES[state.tool] || {};
    ctx.strokeStyle = st.stroke || "#000"; ctx.lineWidth = st.width || 1; ctx.setLineDash([5, 4]);
    const pts = state.mouse ? [...state.drawing.pts, state.mouse] : state.drawing.pts;
    drawChain(pts, false); ctx.stroke(); ctx.setLineDash([]);
    const base = lastDrawingPt();
    if (base && state.mouse) {
      const len = Math.hypot(state.mouse[0] - base[0], state.mouse[1] - base[1]);
      const [mx, my] = w2s(...state.mouse);
      ctx.font = "600 12px sans-serif"; ctx.textAlign = "left";
      if (state.typed) {
        ctx.fillStyle = "#1c1c1a";
        ctx.fillRect(mx + 10, my - 24, ctx.measureText(state.typed + " м").width + 12, 18);
        ctx.fillStyle = "#fff";
        ctx.fillText(state.typed + " м", mx + 16, my - 11);
      } else {
        ctx.fillStyle = "#8b8a85";
        ctx.fillText(len.toFixed(1) + " м", mx + 12, my - 10);
      }
    }
    // замыкание: подсветка первой точки
    if (state.tool !== "redline" && state.drawing.pts.length > 2 && state.mouse) {
      const first = state.drawing.pts[0];
      if (Math.hypot(first[0] - state.mouse[0], first[1] - state.mouse[1]) < 12 / state.view.k) {
        const [fx, fy] = w2s(...first);
        ctx.strokeStyle = "#12a150"; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(fx, fy, 8, 0, 7); ctx.stroke();
      }
    }
  }
  if (state.drag && state.drag.rect) {
    const { a, b } = state.drag;
    const [sx1, sy1] = w2s(...a), [sx2, sy2] = w2s(...b);
    ctx.strokeStyle = STYLES.building.stroke; ctx.fillStyle = STYLES.building.fill + "88";
    ctx.fillRect(Math.min(sx1, sx2), Math.min(sy1, sy2), Math.abs(sx2 - sx1), Math.abs(sy2 - sy1));
    ctx.strokeRect(Math.min(sx1, sx2), Math.min(sy1, sy2), Math.abs(sx2 - sx1), Math.abs(sy2 - sy1));
    ctx.fillStyle = "#5c5a54"; ctx.font = "600 12px sans-serif"; ctx.textAlign = "left";
    ctx.fillText(`${Math.abs(b[0] - a[0]).toFixed(1)} × ${Math.abs(b[1] - a[1]).toFixed(1)} м`,
                 Math.max(sx1, sx2) + 8, Math.min(sy1, sy2) - 6);
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
  drawSnapMarker();
}

// ---------- вид ----------
function fitView() {
  const pts = [];
  for (const f of state.features) for (const p of featurePts(f)) pts.push(p);
  if (!pts.length) return;
  const w = cv.clientWidth, h = cv.clientHeight;
  if (w < 2 || h < 2) return;
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const dx = Math.max(Math.max(...xs) - Math.min(...xs), 10);
  const dy = Math.max(Math.max(...ys) - Math.min(...ys), 10);
  state.view.k = Math.max(0.05, Math.min(40, Math.min(w / dx, h / dy) * 0.82));
  state.view.tx = w / 2 - (Math.min(...xs) + dx / 2) * state.view.k;
  state.view.ty = h / 2 + (Math.min(...ys) + dy / 2) * state.view.k;
  draw();
}

// ---------- история и сохранение ----------
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
function persist() {
  try {
    localStorage.setItem("grado_studio_v1", JSON.stringify({
      features: state.features, nextId: state.nextId,
      name: document.getElementById("project-name").value,
      density: document.getElementById("p-density").value,
      ratio: document.getElementById("p-ratio").value,
      hidden: state.hidden,
    }));
  } catch (e) { /* приватный режим — работаем без сохранения */ }
}
function afterChange() {
  state._ix = null;
  draw(); renderProps(); renderLayers(); refreshTep(); persist();
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
  const f = selectedFeature();
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
    <div class="metric" style="margin-top:6px">двойной клик по ребру — вершина,<br>Alt+клик по вершине — удалить,<br>R — поворот, ⌘D — дубликат</div>
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
function renderLayers() {
  const el = document.getElementById("layers-body");
  if (!el) return;
  el.innerHTML = "";
  for (const kind of Z_ORDER) {
    const count = state.features.filter(f => f.kind === kind).length;
    const st = STYLES[kind];
    const row = document.createElement("label");
    row.className = "layer-row";
    row.innerHTML = `<input type="checkbox" ${state.hidden[kind] ? "" : "checked"}>
      <span class="sw" style="background:${st.fill || "transparent"};border-color:${st.stroke || "#999"}"></span>
      <span class="nm">${KIND_NAMES[kind]}</span><span class="cnt">${count || ""}</span>`;
    row.querySelector("input").addEventListener("change", ev => {
      state.hidden[kind] = !ev.target.checked;
      const sel = selectedFeature();
      if (state.hidden[kind] && sel && sel.kind === kind) {
        state.selected = null;
        renderProps();
      }
      state._ix = null;
      persist();
      draw();
    });
    el.appendChild(row);
  }
}

function deleteSelected() {
  if (state.selected == null) return;
  snapshot();
  state.features = state.features.filter(f => f.id !== state.selected);
  state.selected = null; afterChange();
}

// ---------- добавление и правка фигур ----------
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
  return f;
}
function finishDrawing() {
  const d = state.drawing;
  if (!d) return;
  const isPoly = state.tool !== "redline";
  if (isPoly && d.pts.length >= 3) addFeature(state.tool, { ring: d.pts });
  else if (!isPoly && d.pts.length >= 2) addFeature("redline", { line: d.pts });
  state.drawing = null; state.typed = "";
  draw();
}
function rotateSelected() {
  const f = selectedFeature();
  if (!f || f.point) return;
  snapshot();
  const pts = featurePts(f);
  const cx = pts.reduce((a, p) => a + p[0], 0) / pts.length;
  const cy = pts.reduce((a, p) => a + p[1], 0) / pts.length;
  for (const p of pts) {
    const dx = p[0] - cx, dy = p[1] - cy;
    p[0] = cx - dy; p[1] = cy + dx;   // 90° против часовой
  }
  afterChange();
}
function duplicateSelected() {
  const f = selectedFeature();
  if (!f) return;
  const g = gridStep();
  const copy = JSON.parse(JSON.stringify(f));
  copy.id = state.nextId++;
  for (const p of featurePts(copy)) { p[0] += g; p[1] -= g; }
  snapshot();
  state.features.push(copy);
  state.selected = copy.id;
  afterChange();
}
function nudgeSelected(dx, dy) {
  const f = selectedFeature();
  if (!f) return;
  snapshot();
  for (const p of featurePts(f)) { p[0] += dx; p[1] += dy; }
  afterChange();
}
function placeTypedPoint() {
  const base = lastDrawingPt();
  const dist = parseFloat(state.typed.replace(",", "."));
  if (!base || !state.mouse || !isFinite(dist) || dist <= 0) { state.typed = ""; return; }
  const a = Math.atan2(state.mouse[1] - base[1], state.mouse[0] - base[0]);
  state.drawing.pts.push([base[0] + dist * Math.cos(a), base[1] + dist * Math.sin(a)]);
  state.typed = "";
  draw();
}

// ---------- хит-тест ----------
function hitTest(wx, wy) {
  const tolW = 7 / state.view.k;
  for (const kind of [...Z_ORDER].reverse()) {
    if (state.hidden[kind]) continue;
    for (let i = state.features.length - 1; i >= 0; i--) {
      const f = state.features[i];
      if (f.kind !== kind) continue;
      if (f.point && Math.hypot(f.point[0] - wx, f.point[1] - wy) < tolW + 4 / state.view.k) return f;
      if (f.line && nearChain(wx, wy, f.line, tolW) !== null) return f;
      if (f.ring && (kind === "boundary" ? nearChain(wx, wy, [...f.ring, f.ring[0]], tolW) !== null
                                         : pointInRing(wx, wy, f.ring))) return f;
    }
  }
  return null;
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
  const s = cursorPoint(wxr, wyr);
  if (state.tool === "select") {
    const cur = selectedFeature();
    if (cur) {
      const vi = vertexAt(cur, wxr, wyr);
      if (vi != null) {
        if (e.altKey) {   // Alt+клик — удалить вершину
          const pts = featurePts(cur);
          const min = cur.ring ? 3 : 2;
          if (!cur.point && pts.length > min) {
            snapshot(); pts.splice(vi, 1); afterChange();
          }
          return;
        }
        state.edit = { f: cur, vi, moved: false };
        return;
      }
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
  } else if (state.tool === "building" && !state.drawing) {
    // протягивание — прямоугольник; одиночный клик — контур по точкам
    state.drag = { a: s.p, b: s.p, rect: true, moved: false };
  } else {
    if (!state.drawing) { state.drawing = { pts: [] }; state.typed = ""; }
    const first = state.drawing.pts[0];
    if (first && state.tool !== "redline" && state.drawing.pts.length > 2 &&
        Math.hypot(first[0] - s.p[0], first[1] - s.p[1]) < 12 / state.view.k) {
      finishDrawing();
    } else {
      state.drawing.pts.push(s.p);
      state.typed = "";
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
      const s = snapPoint(wx, wy, ed.f.id);
      state.snapHit = s;
      const pts = featurePts(ed.f);
      pts[ed.vi][0] = s.p[0]; pts[ed.vi][1] = s.p[1];
    }
    state._ix = null;
    draw(); return;
  }
  const s = cursorPoint(wx, wy);
  state.snapHit = s;
  state.mouse = s.p;
  document.getElementById("st-snap").textContent = s.kind ? `привязка: ${s.kind}` : "";
  if (state.drag && state.drag.rect) {
    state.drag.b = s.p;
    if (Math.hypot(s.p[0] - state.drag.a[0], s.p[1] - state.drag.a[1]) * state.view.k > 4)
      state.drag.moved = true;
    draw(); return;
  }
  if (state.tool === "select") {
    const cur = selectedFeature();
    cv.style.cursor = (cur && vertexAt(cur, wx, wy) != null) ? "move"
      : hitTest(wx, wy) ? "pointer" : "default";
    if (state.guides.length) draw();
  }
  if (state.drawing || state.tool !== "select") draw();
});
// Слушаем на window, а не на #cv: если отпустить кнопку за пределами
// холста (над панелью/тулбаром), локальный слушатель #cv это событие
// не увидит — pan/edit/drag «залипнут», и вид будет произвольно
// скакать при следующем движении мыши, создавая впечатление, что
// холст не реагирует на клики.
window.addEventListener("mouseup", e => {
  if (state.pan) { state.pan = null; return; }
  if (state.edit) {
    const moved = state.edit.moved;
    state.edit = null;
    if (moved) afterChange();
    return;
  }
  if (state.drag && state.drag.rect) {
    const { a, b, moved } = state.drag;
    state.drag = null;
    if (moved && Math.abs(a[0] - b[0]) > 1 && Math.abs(a[1] - b[1]) > 1) {
      addFeature("building", { ring: [[a[0], a[1]], [b[0], a[1]], [b[0], b[1]], [a[0], b[1]]] });
    } else if (!moved) {
      // клик без протягивания — рисуем произвольный контур здания
      state.drawing = { pts: [a] };
      state.typed = "";
      draw();
    } else draw();
  }
});
// потеря фокуса окна (alt-tab, системный диалог) посреди жеста —
// та же защита, чтобы состояние не осталось залипшим
window.addEventListener("blur", () => {
  state.pan = null;
  if (state.edit) { state.edit = null; }
  if (state.drag) { state.drag = null; draw(); }
});
cv.addEventListener("dblclick", e => {
  e.preventDefault();
  if (state.drawing) { finishDrawing(); return; }
  // двойной клик по ребру выбранной фигуры — вставка вершины
  if (state.tool === "select") {
    const f = selectedFeature();
    if (!f || f.point) return;
    const [wx, wy] = s2w(e.offsetX, e.offsetY);
    const chain = f.ring ? [...f.ring, f.ring[0]] : f.line;
    const i = nearChain(wx, wy, chain, 7 / state.view.k);
    if (i !== null) {
      snapshot();
      const q = nearestOnSeg([wx, wy], chain[i], chain[i + 1]);
      featurePts(f).splice(i + 1, 0, q);
      afterChange();
    }
  }
});
cv.addEventListener("wheel", e => {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
  const [wx, wy] = s2w(e.offsetX, e.offsetY);
  state.view.k = Math.min(40, Math.max(0.05, state.view.k * factor));
  state.view.tx = e.offsetX - wx * state.view.k;
  state.view.ty = e.offsetY + wy * state.view.k;
  draw();
}, { passive: false });

// ---------- клавиатура (по кодам клавиш — не зависит от раскладки) ----------
const TOOL_CODES = { KeyV: "select", KeyG: "boundary", KeyZ: "zone", KeyO: "restrict",
                     KeyB: "building", KeyP: "public", KeyL: "redline", KeyS: "social",
                     KeyM: "measure" };
document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  if (e.key === "Shift") { shiftDown = true; if (state.drawing) draw(); return; }
  if (e.code === "Space") { spaceDown = true; e.preventDefault(); return; }
  if ((e.metaKey || e.ctrlKey) && e.code === "KeyZ") {
    e.preventDefault(); e.shiftKey ? redo() : undo(); return;
  }
  if ((e.metaKey || e.ctrlKey) && e.code === "KeyD") {
    e.preventDefault(); duplicateSelected(); return;
  }
  // набор длины цифрами при рисовании
  if (state.drawing && /^[0-9.,]$/.test(e.key)) { state.typed += e.key; draw(); return; }
  if (state.drawing && e.key === "Backspace") {
    state.typed = state.typed.slice(0, -1); draw(); return;
  }
  if (e.key === "Enter") {
    if (state.drawing && state.typed) placeTypedPoint();
    else finishDrawing();
    return;
  }
  if (e.key === "Escape") {
    if (state.typed) { state.typed = ""; draw(); return; }
    if (state.drawing) { state.drawing = null; draw(); return; }
    if (state.measure) { state.measure = null; draw(); return; }
    state.selected = null; draw(); renderProps(); return;
  }
  if (e.key === "Delete" || e.key === "Backspace") { deleteSelected(); return; }
  if (e.key.startsWith("Arrow")) {
    const step = e.shiftKey ? 1 : gridStep();
    const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0],
                ArrowUp: [0, step], ArrowDown: [0, -step] }[e.key];
    if (d && state.selected != null) { e.preventDefault(); nudgeSelected(...d); }
    return;
  }
  if (e.code === "KeyX") { setOsnap(!state.osnap); return; }
  if (e.code === "KeyC" && !e.metaKey && !e.ctrlKey) { setGridSnap(!state.gridSnap); return; }
  if (e.code === "KeyF") { fitView(); return; }
  if (e.code === "KeyR") { rotateSelected(); return; }
  const tool = TOOL_CODES[e.code];
  if (tool) setTool(tool);
});
document.addEventListener("keyup", e => {
  if (e.key === "Shift") { shiftDown = false; if (state.drawing) draw(); }
  if (e.code === "Space") spaceDown = false;
});

// ---------- инструменты, сетка, кнопки ----------
function setTool(tool) {
  state.tool = tool; state.drawing = null; state.drag = null;
  state.edit = null; state.typed = "";
  if (tool !== "measure") state.measure = null;
  document.querySelectorAll("#toolbar button[data-tool]").forEach(
    b => b.classList.toggle("active", b.dataset.tool === tool));
  cv.style.cursor = tool === "select" ? "default" : "crosshair";
  draw();
}
document.querySelectorAll("#toolbar button[data-tool]").forEach(
  b => b.addEventListener("click", () => setTool(b.dataset.tool)));

function setOsnap(v) {
  state.osnap = v;
  document.getElementById("btn-snap").classList.toggle("active", v);
  const chk = document.getElementById("obj-snap");
  if (chk) chk.checked = v;
}
function setGridSnap(v) {
  state.gridSnap = v;
  const chk = document.getElementById("grid-snap");
  if (chk) chk.checked = v;
  draw();
}
on("basemap-show", "change", e => {
  basemap.on = e.target.checked;
  if (basemap.on && basemap.originLon == null) initBasemap().then(draw);
  draw();
});
on("basemap-opacity", "input", e => {
  basemap.opacity = +e.target.value / 100;
  draw();
});
on("btn-snap", "click", () => setOsnap(!state.osnap));
on("obj-snap", "change", e => setOsnap(e.target.checked));
on("grid-snap", "change", e => setGridSnap(e.target.checked));
on("grid-show", "change", e => { state.gridShow = e.target.checked; draw(); });
on("grid-step", "change", e => { state.gridMode = e.target.value; draw(); });
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

// открытие проекта .grado (round-trip с QGIS)
on("btn-open", "click", () => document.getElementById("grado-file").click());
on("grado-file", "change", async e => {
  const file = e.target.files[0];
  if (!file) return;
  e.target.value = "";
  try {
    const r = await fetch("/api/open-grado", { method: "POST",
      headers: { "Content-Type": "application/octet-stream" }, body: file });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    snapshot();
    state.features = data.features.map(f => ({ id: state.nextId++, ...f }));
    if (data.name) document.getElementById("project-name").value = data.name;
    state.selected = null;
    afterChange();
    fitView();
    toast(`Открыт проект: ${data.features.length} объектов`);
  } catch (err) {
    alert("Не удалось открыть проект: " + String(err).slice(0, 200));
  }
});

// мост браузерного расширения: опрос входящих выгрузок
let toastTimer = null;
function toast(msg) {
  const el = document.getElementById("st-toast");
  el.textContent = msg;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.textContent = ""; }, 5000);
}
async function pollInbox() {
  try {
    const r = await fetch("/api/inbox");
    const data = await r.json();
    document.getElementById("st-bridge").textContent =
      data.bridge ? "мост 8081: вкл" : "мост 8081: занят (QGIS)";
    let added = 0;
    for (const item of data.items) {
      if (!item.features.length) continue;
      if (!added) snapshot();
      for (const f of item.features)
        state.features.push({ id: state.nextId++, ...f });
      added += item.features.length;
    }
    if (added) {
      afterChange();
      fitView();
      const src = data.items[0].source === "fgis_tp" ? "ФГИС ТП" : "НСПД";
      toast(`Мост: +${added} объектов (${src})`);
    }
  } catch (e) { /* сервер перезапускается — молча */ }
}
setInterval(pollInbox, 2500);
pollInbox();

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
  add("redline", { line: [[-30, 190], [400, 190], [400, 590]] }, { radius: 60 });
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
    state.hidden = d.hidden || {};
    if (d.name) document.getElementById("project-name").value = d.name;
    if (d.density) document.getElementById("p-density").value = d.density;
    if (d.ratio) document.getElementById("p-ratio").value = d.ratio;
  } catch (e) { /* повреждённое сохранение игнорируем */ }
})();
on("project-name", "change", persist);
window.studio = { state, addFeature, refreshTep, fitView, snapPoint, gridStep };
setTool("select");
renderLayers();
requestAnimationFrame(resize);
refreshTep();
