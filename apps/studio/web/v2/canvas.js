import { post } from "./api.js";
import {
  SNAP_LABEL, addFeature, emit, featurePoints, layerById, replaceFeature,
  selectedFeature, snapPolylines, state, subscribe, togglePick, undoEdit,
} from "./store.js";

const COLORS = {
  boundary: "#1c1b19",
  restrict: "#8a4b2f",
  zone: "#2f6f4e",
  building: "#3d4c66",
  public: "#6a5a2f",
  redline: "#9c2f2f",
  social: "#1f4d7a",
};

let ctx;
let rect = { width: 1, height: 1 };
let draft = [];
let cursor = null;
let panning = null;
let drag = null;
// Последняя расстановка точки: привязка идёт через сервер, двойной щелчок
// обязан дождаться её, иначе контур закроется без последней вершины.
let placing = Promise.resolve();
const tileCache = new Map();

export function worldFromEvent(event) {
  const box = event.currentTarget.getBoundingClientRect();
  return screenToWorld(event.clientX - box.left, event.clientY - box.top);
}

export function screenToWorld(px, py) {
  return {
    x: state.origin.x + (px - rect.width / 2) / state.ppm,
    y: state.origin.y - (py - rect.height / 2) / state.ppm,
  };
}

function worldToScreen(x, y) {
  return [
    rect.width / 2 + (x - state.origin.x) * state.ppm,
    rect.height / 2 - (y - state.origin.y) * state.ppm,
  ];
}

function snapTolerance() {
  return Math.max(state.snap, 10 / state.ppm);
}

async function placePoint(point) {
  if (state.gridOn) {
    try {
      const g = await post("/api/geom", { op: "grid", x: point.x, y: point.y, step: state.gridStep });
      point = { ...point, x: g.x, y: g.y };
    } catch { /* шаг сетки не применился */ }
  }
  point = applyOrtho(point);
  if (state.snapOn) point = await snapPoint(point);
  return point;
}

function chainsOf(feature) {
  if (feature.line && feature.line.length >= 2) return [feature.line];
  if (feature.ring && feature.ring.length >= 2) return [[...feature.ring, feature.ring[0]]];
  if (feature.preview && feature.preview.length >= 2) return [feature.preview];
  return [];
}

function applyOrtho(point) {
  if (!state.ortho || !draft.length) return point;
  const last = draft[draft.length - 1];
  if (Math.abs(point.x - last.x) >= Math.abs(point.y - last.y)) {
    return { x: point.x, y: last.y };
  }
  return { x: last.x, y: point.y };
}

async function snapPoint(point) {
  const lines = snapPolylines();
  if (!lines.length) return { ...point, hint: "" };
  try {
    const out = await post("/api/geom", {
      op: "snap", x: point.x, y: point.y, tolerance: snapTolerance(), polylines: lines,
    });
    if (!out.hit) return { ...point, hint: "" };
    return { x: out.hit.x, y: out.hit.y, hint: SNAP_LABEL[out.hit.kind] || "" };
  } catch {
    return { ...point, hint: "" };
  }
}

function drawChain(points, color, width, close, dash) {
  if (!points.length) return;
  ctx.beginPath();
  points.forEach((p, i) => {
    const [x, y] = worldToScreen(p[0], p[1]);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  if (close) ctx.closePath();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.setLineDash(Array.isArray(dash) && dash.length ? dash : []);
  ctx.stroke();
  ctx.setLineDash([]);
}

function curveSamples(curve) {
  const steps = Math.max(12, Math.ceil(Math.abs(curve.sweep || Math.PI * 2) / (Math.PI / 24)));
  const pts = [];
  for (let i = 0; i <= steps; i++) {
    const angle = curve.a0 + curve.sweep * (i / steps);
    pts.push([curve.cx + curve.r * Math.cos(angle), curve.cy + curve.r * Math.sin(angle)]);
  }
  return pts;
}

function paintOf(feature) {
  const id = feature.style_id;
  const custom = (id && state.projectStyles && state.projectStyles[id]) || {};
  const library = (id && state.library && state.library[id]) || {};
  const style = { ...library, ...custom };
  return {
    stroke: style.stroke || COLORS[feature.kind] || "#444",
    fill: style.fill || null,
    width: style.width || 1.4,
    dash: style.dash || null,
    hatch: style.hatch || null,
    dots: style.dots || null,
  };
}

function clipShape(points, holes) {
  ctx.beginPath();
  const add = (ring) => {
    ring.forEach((p, i) => {
      const [x, y] = worldToScreen(p[0], p[1]);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
  };
  add(points);
  for (const hole of holes || []) if (hole.length >= 3) add(hole);
  ctx.clip(holes && holes.length ? "evenodd" : "nonzero");
}

function screenBox(points) {
  let x0 = Infinity;
  let x1 = -Infinity;
  let y0 = Infinity;
  let y1 = -Infinity;
  for (const p of points) {
    const [x, y] = worldToScreen(p[0], p[1]);
    if (x < x0) x0 = x;
    if (x > x1) x1 = x;
    if (y < y0) y0 = y;
    if (y > y1) y1 = y;
  }
  return { x0, y0, x1, y1 };
}

function drawHatch(points, hatch, strokeColor, holes) {
  if (!hatch || points.length < 3) return;
  const spec = hatch === true ? { angle: 45, spacing_px: 9, color: strokeColor } : hatch;
  ctx.save();
  clipShape(points, holes);
  const box = screenBox(points);
  const margin = (spec.spacing_px || 9) * 2;
  const x0 = Math.max(box.x0, -margin);
  const x1 = Math.min(box.x1, rect.width + margin);
  const y0 = Math.max(box.y0, -margin);
  const y1 = Math.min(box.y1, rect.height + margin);
  if (x1 <= x0 || y1 <= y0) {
    ctx.restore();
    return;
  }
  ctx.strokeStyle = spec.color || strokeColor;
  ctx.lineWidth = 1;
  ctx.setLineDash([]);
  const step = Math.max(3, spec.spacing_px || 9);
  const angles = spec.cross ? [45, 135] : [spec.angle ?? 45];
  for (const angle of angles) {
    ctx.beginPath();
    if (angle === 0) {
      for (let y = y0; y <= y1; y += step) {
        ctx.moveTo(x0, y);
        ctx.lineTo(x1, y);
      }
    } else if (angle === 90) {
      for (let x = x0; x <= x1; x += step) {
        ctx.moveTo(x, y0);
        ctx.lineTo(x, y1);
      }
    } else if (angle === 45) {
      const span = step * Math.SQRT2;
      for (let c = x0 - (y1 - y0); c < x1; c += span) {
        ctx.moveTo(c, y1);
        ctx.lineTo(c + (y1 - y0), y0);
      }
    } else {
      const span = step * Math.SQRT2;
      for (let c = x0 - (y1 - y0); c < x1; c += span) {
        ctx.moveTo(c + (y1 - y0), y1);
        ctx.lineTo(c, y0);
      }
    }
    ctx.stroke();
  }
  ctx.restore();
}

function drawDots(points, dots, holes) {
  if (!dots || !dots.color || points.length < 3) return;
  ctx.save();
  clipShape(points, holes);
  const box = screenBox(points);
  const step = Math.max(4, dots.spacing_px || 8);
  const radius = Math.max(0.6, (dots.size_px || 2) / 2);
  const x0 = Math.max(box.x0, -step);
  const x1 = Math.min(box.x1, rect.width + step);
  const y0 = Math.max(box.y0, -step);
  const y1 = Math.min(box.y1, rect.height + step);
  if (x1 <= x0 || y1 <= y0) {
    ctx.restore();
    return;
  }
  ctx.fillStyle = dots.color;
  const sx = Math.floor(x0 / step) * step;
  const sy = Math.floor(y0 / step) * step;
  ctx.beginPath();
  for (let y = sy; y <= y1; y += step) {
    for (let x = sx; x <= x1; x += step) {
      ctx.moveTo(x + radius, y);
      ctx.arc(x, y, radius, 0, Math.PI * 2);
    }
  }
  ctx.fill();
  ctx.restore();
}

const filletWait = new Set();

function queueFillet(feature) {
  if (!feature.id || filletWait.has(feature.id) || feature.preview) return;
  if (!feature.line || !(feature.props && feature.props.radius > 0)) return;
  filletWait.add(feature.id);
  post("/api/geom", { op: "fillet", line: feature.line, radius: feature.props.radius })
    .then((out) => {
      feature.preview = out.preview;
      filletWait.delete(feature.id);
      redraw();
    })
    .catch(() => filletWait.delete(feature.id));
}

function drawFeature(feature) {
  const ink = paintOf(feature);
  const color = ink.stroke;
  const selected = feature.id === state.selection || state.picked.includes(feature.id);
  const width = selected ? Math.max(ink.width, 2.2) : ink.width;
  ctx.save();
  if (feature.circle) {
    const samples = curveSamples({ ...feature.circle, a0: 0, sweep: Math.PI * 2 });
    if (ink.hatch) drawHatch(samples, ink.hatch, color);
    if (ink.dots) drawDots(samples, ink.dots);
    drawChain(samples, color, width, true, ink.dash);
  } else if (feature.arc) {
    drawChain(curveSamples(feature.arc), color, width, false, ink.dash);
  } else if (feature.props && feature.props.radius > 0 && feature.line) {
    queueFillet(feature);
    if (feature.preview && feature.preview.length) drawChain(feature.preview, color, width, false, ink.dash);
  } else if (feature.preview && feature.preview.length && !feature.ring) {
    drawChain(feature.preview, color, width, false, ink.dash);
  } else if (feature.ring) {
    ctx.beginPath();
    feature.ring.forEach((p, i) => {
      const [x, y] = worldToScreen(p[0], p[1]);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fillStyle = ink.fill || (color + "22");
    ctx.fill();
    if (ink.hatch) drawHatch(feature.ring, ink.hatch, color, feature.holes);
    if (ink.dots) drawDots(feature.ring, ink.dots, feature.holes);
    ctx.beginPath();
    feature.ring.forEach((p, i) => {
      const [x, y] = worldToScreen(p[0], p[1]);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.setLineDash(Array.isArray(ink.dash) && ink.dash.length ? ink.dash : []);
    ctx.stroke();
    ctx.setLineDash([]);
  } else if (feature.line) {
    drawChain(feature.line, color, width, false, ink.dash);
  } else if (feature.point) {
    const [x, y] = worldToScreen(feature.point[0], feature.point[1]);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, selected ? 5 : 3.5, 0, Math.PI * 2);
    ctx.fill();
  }
  if (feature.kind === "dim" && feature.line && feature.line.length >= 2) {
    const a = feature.line[0], b = feature.line[1];
    const [x, y] = worldToScreen((a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
    ctx.fillStyle = "#1c1b19";
    ctx.font = "12px sans-serif";
    ctx.fillText(feature.props.label || "", x + 6, y - 6);
  }
  ctx.restore();
}

function drawBasemap() {
  if (!state.basemap || state.view === "draw" && state.basemap === "off") return;
  if (!state.basemap || state.basemap === "off") return;
  const crs = window.GRADO_CRS;
  if (!crs) return;
  const z = Math.max(12, Math.min(18, Math.round(Math.log2(state.ppm * 800))));
  const corners = [[0, 0], [rect.width, 0], [rect.width, rect.height], [0, rect.height]];
  const wgs = corners.map(([x, y]) => crs.localToWgs84([screenToWorld(x, y).x, screenToWorld(x, y).y]));
  const lons = wgs.map((p) => p[0]), lats = wgs.map((p) => p[1]);
  const tile = (lon, lat) => {
    const n = 2 ** z;
    const x = Math.floor((lon + 180) / 360 * n);
    const r = lat * Math.PI / 180;
    const y = Math.floor((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * n);
    return [x, y];
  };
  const [x0, y0] = tile(Math.min(...lons), Math.max(...lats));
  const [x1, y1] = tile(Math.max(...lons), Math.min(...lats));
  for (let x = x0; x <= x1; x++) {
    for (let y = y0; y <= y1; y++) {
      const key = `${state.basemap}/${z}/${x}/${y}`;
      let img = tileCache.get(key);
      if (!img) {
        img = new Image();
        img.src = `/api/tiles/${z}/${x}/${y}.png?source=${state.basemap}`;
        img.onload = () => redraw();
        tileCache.set(key, img);
      }
      if (!img.complete || !img.naturalWidth) continue;
      const nw = crs.wgs84ToLocal([(x / (2 ** z)) * 360 - 180, Math.atan(Math.sinh(Math.PI * (1 - 2 * y / (2 ** z)))) * 180 / Math.PI]);
      const se = crs.wgs84ToLocal([((x + 1) / (2 ** z)) * 360 - 180, Math.atan(Math.sinh(Math.PI * (1 - 2 * (y + 1) / (2 ** z)))) * 180 / Math.PI]);
      const [sx, sy] = worldToScreen(nw[0], nw[1]);
      const [ex, ey] = worldToScreen(se[0], se[1]);
      ctx.drawImage(img, sx, sy, ex - sx, ey - sy);
    }
  }
}

function redraw() {
  const canvas = ctx.canvas;
  const dpr = window.devicePixelRatio || 1;
  rect = { width: canvas.clientWidth, height: canvas.clientHeight };
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);
  ctx.fillStyle = state.view === "map" ? "#e4ebe3" : "#f6f3ec";
  ctx.fillRect(0, 0, rect.width, rect.height);
  if (state.view === "map") drawBasemap();
  for (const feature of state.features) {
    if (state.visible[feature.layer_id] === false) continue;
    drawFeature(feature);
  }
  if (draft.length) {
    const pts = draft.map((p) => [p.x, p.y]);
    if (cursor) pts.push([cursor.x, cursor.y]);
    drawChain(pts, "#1f4d7a", 1.2, false);
  }
}

async function commitDraft() {
  const layer = layerById(state.activeLayer);
  if (!layer) return;
  const points = draft.map((p) => [p.x, p.y]);
  draft = [];
  try {
    if (state.tool === "rect" && points.length >= 2) {
      const rect = await post("/api/geom", { op: "rectangle", a: points[0], b: points[1] });
      addFeature({ kind: layer.kind, layer_id: layer.id, ring: rect.ring, props: {} });
      return;
    }
    if (state.tool === "point" && points.length >= 1) {
      addFeature({ kind: "social", layer_id: "project.social.objects", point: points[0], props: {} });
      return;
    }
    if (state.tool === "segment" && points.length >= 2) {
      addFeature({ kind: "redline", layer_id: "project.apo.red_lines", line: points.slice(0, 2), props: {} });
      return;
    }
    if (state.tool === "polyline" && points.length >= 2) {
      addFeature({ kind: "redline", layer_id: "project.apo.red_lines", line: points, props: {} });
      return;
    }
    if ((state.tool === "polygon" || state.tool === "rect") && points.length >= 3) {
      addFeature({ kind: layer.kind, layer_id: layer.id, ring: points, props: {} });
      return;
    }
    if (state.tool === "polygon") {
      state.message = "Контур не закрыт: нужно минимум три точки";
      emit();
      return;
    }
    if (state.tool === "dim" && points.length >= 2) {
      const measured = await post("/api/geom", { op: "measure", points: points.slice(0, 2) });
      addFeature({
        kind: "dim", layer_id: "annotation.dimensions", line: points.slice(0, 2),
        props: { label: measured.length_m + " м" },
      });
      return;
    }
    if (state.tool === "measure" && points.length >= 2) {
      const measured = await post("/api/geom", { op: "measure", points: points.slice(0, 2) });
      state.message = `Длина ${measured.length_m} м`;
      emit();
    }
    if (state.tool === "arc" && points.length >= 3) {
      const arc = await post("/api/geom", { op: "arc3", points: points.slice(0, 3) });
      addFeature({
        kind: "redline", layer_id: "project.apo.red_lines",
        line: [points[0], points[2]], arc, preview: arc.preview, props: {},
      });
      return;
    }
    if (state.tool === "circle" && points.length >= 2) {
      const circle = await post("/api/geom", { op: "circle", center: points[0], edge: points[1] });
      addFeature({
        kind: "redline", layer_id: "project.apo.red_lines",
        circle, preview: circle.preview, props: {},
      });
    }
  } catch (error) {
    state.message = error.message || "Команда не выполнена";
    emit();
  }
}

function needed() {
  if (state.tool === "point") return 1;
  if (state.tool === "segment" || state.tool === "circle" || state.tool === "rect"
      || state.tool === "dim" || state.tool === "measure") return 2;
  if (state.tool === "arc") return 3;
  return Infinity;
}

export async function transformSelection(op, extra) {
  const feature = selectedFeature();
  let points = featurePoints(feature);
  if (feature && feature.arc) {
    const arc = feature.arc;
    const at = (t) => {
      const angle = arc.a0 + arc.sweep * t;
      return [arc.cx + arc.r * Math.cos(angle), arc.cy + arc.r * Math.sin(angle)];
    };
    points = [at(0), at(0.5), at(1)];
  }
  if (!feature || points.length === 0) {
    state.message = "Сначала выберите объект";
    emit();
    return;
  }
  const origin = points.reduce((acc, p) => [acc[0] + p[0], acc[1] + p[1]], [0, 0])
    .map((v) => v / points.length);
  try {
    const out = await post("/api/geom", { op, points, origin, ...extra });
    const moved = out.points;
    if (feature.circle) {
      const next = { ...feature.circle, cx: moved[0][0], cy: moved[0][1] };
      if (op === "scale") next.r = feature.circle.r * Number(extra.factor);
      replaceFeature(feature.id, { circle: next, preview: undefined });
    } else if (feature.arc) {
      const rebuilt = await post("/api/geom", { op: "arc3", points: moved });
      replaceFeature(feature.id, {
        arc: { cx: rebuilt.cx, cy: rebuilt.cy, r: rebuilt.r, a0: rebuilt.a0, sweep: rebuilt.sweep },
        preview: undefined,
      });
    } else if (feature.ring) replaceFeature(feature.id, { ring: moved, preview: undefined });
    else if (feature.line) replaceFeature(feature.id, { line: moved, preview: undefined });
    else if (feature.point) replaceFeature(feature.id, { point: moved[0], preview: undefined });
    else state.message = "Для этой геометрии команда не задана";
  } catch (error) {
    state.message = error.message || "Команда не выполнена";
  }
  emit();
}

export async function filletSelection(radius) {
  const feature = selectedFeature();
  if (!feature || !feature.line || feature.line.length < 3) {
    state.message = "Сопряжение ждёт полилинию из трёх точек";
    emit();
    return;
  }
  try {
    const out = await post("/api/geom", { op: "fillet", line: feature.line, radius });
    replaceFeature(feature.id, {
      line: out.vertices, preview: out.preview, props: { ...feature.props, radius: out.radius },
    });
  } catch {
    state.message = "Радиус не помещается";
    emit();
  }
}

export function mount(canvas) {
  ctx = canvas.getContext("2d");
  const resize = () => redraw();
  new ResizeObserver(resize).observe(canvas);
  subscribe(redraw);

  canvas.addEventListener("pointermove", async (event) => {
    if (panning) {
      state.origin.x -= (event.clientX - panning.x) / state.ppm;
      state.origin.y += (event.clientY - panning.y) / state.ppm;
      panning = { x: event.clientX, y: event.clientY };
      redraw();
      return;
    }
    const raw = screenToWorld(
      event.clientX - canvas.getBoundingClientRect().left,
      event.clientY - canvas.getBoundingClientRect().top,
    );
    const point = await placePoint(raw);
    cursor = point;
    if (state.snapHint !== point.hint) {
      state.snapHint = point.hint;
      emit();
    } else redraw();
  });

  canvas.addEventListener("pointerdown", async (event) => {
    if (event.button === 1 || event.altKey) {
      panning = { x: event.clientX, y: event.clientY };
      return;
    }
    if (state.tool === "select") {
      const vertex = nearVertex(event);
      if (vertex) { drag = vertex; return; }
      pick(event);
      return;
    }
    if (state.tool === "trim" || state.tool === "extend") {
      await trimClick(event);
      return;
    }
    if (event.detail > 1) return;
    canvas.setPointerCapture(event.pointerId);
    const job = placePoint(worldFromEvent(event)).then(async (point) => {
      state.snapHint = point.hint;
      draft.push(point);
      if (draft.length >= needed()) await commitDraft();
      else emit();
    });
    placing = job.catch(() => {});
    await job;
  });

  canvas.addEventListener("pointerup", async (event) => {
    panning = null;
    if (!drag) return;
    const point = await placePoint(worldFromEvent(event));
    const feature = state.features.find((item) => item.id === drag.id);
    const moved = drag;
    drag = null;
    if (!feature || state.locked[feature.layer_id]) return;
    const source = feature[moved.key];
    const points = moved.key === "point" ? [source] : source;
    try {
      const out = await post("/api/geom", {
        op: "vertex", points, index: moved.index, point: [point.x, point.y],
      });
      const patch = moved.key === "point" ? { point: out.points[0] } : { [moved.key]: out.points };
      replaceFeature(feature.id, patch);
    } catch (error) {
      state.message = error.message || "Вершина не сдвинулась";
      emit();
    }
  });
  canvas.addEventListener("dblclick", async (event) => {
    event.preventDefault();
    await placing;
    if (draft.length >= 2 && (state.tool === "polyline" || state.tool === "polygon")) {
      await commitDraft();
    }
  });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const next = state.ppm * (event.deltaY > 0 ? 0.9 : 1.1);
    state.ppm = Math.min(80, Math.max(0.05, next));
    redraw();
    emit();
  }, { passive: false });

  window.addEventListener("keydown", async (event) => {
    if (event.target.id === "command") return;
    if (event.key === "Escape") {
      draft = [];
      state.tool = "select";
      state.trimReady = false;
      state.snapHint = "";
      emit();
    } else if (event.key === "Enter" && (state.tool === "trim" || state.tool === "extend")) {
      state.trimReady = true;
      state.message = state.tool === "trim" ? "Клик по лишнему куску" : "Клик у открытого конца";
      emit();
    } else if (event.key === "Enter" && draft.length >= 2) {
      await placing;
      await commitDraft();
    } else if ((event.metaKey || event.ctrlKey) && event.key === "z") {
      event.preventDefault();
      undoEdit();
    }
  });
}

function curveDistance(feature, here) {
  if (feature.circle) {
    const c = feature.circle;
    return Math.abs(Math.hypot(c.cx - here.x, c.cy - here.y) - c.r);
  }
  if (!feature.arc) return Infinity;
  const arc = feature.arc;
  let best = Infinity;
  for (let i = 0; i <= 8; i++) {
    const angle = arc.a0 + arc.sweep * (i / 8);
    best = Math.min(best, Math.hypot(
      arc.cx + arc.r * Math.cos(angle) - here.x,
      arc.cy + arc.r * Math.sin(angle) - here.y,
    ));
  }
  return best;
}

function hitFeature(event) {
  const here = worldFromEvent(event);
  let best = null;
  let bestDist = 12 / state.ppm;
  for (const feature of state.features) {
    if (state.visible[feature.layer_id] === false) continue;
    const along = curveDistance(feature, here);
    if (along < bestDist) {
      best = feature;
      bestDist = along;
    }
    for (const p of featurePoints(feature)) {
      const dist = Math.hypot(p[0] - here.x, p[1] - here.y);
      if (dist < bestDist) {
        best = feature;
        bestDist = dist;
      }
    }
  }
  return best;
}

function nearVertex(event) {
  const here = worldFromEvent(event);
  let best = null;
  let bestDist = 8 / state.ppm;
  for (const feature of state.features) {
    if (state.visible[feature.layer_id] === false || state.locked[feature.layer_id]) continue;
    for (const key of ["ring", "line"]) {
      const pts = feature[key];
      if (!pts) continue;
      pts.forEach((p, index) => {
        const dist = Math.hypot(p[0] - here.x, p[1] - here.y);
        if (dist < bestDist) {
          best = { id: feature.id, key, index };
          bestDist = dist;
        }
      });
    }
    if (feature.point) {
      const dist = Math.hypot(feature.point[0] - here.x, feature.point[1] - here.y);
      if (dist < bestDist) best = { id: feature.id, key: "point", index: 0 };
    }
  }
  return best;
}

function pick(event) {
  const feature = hitFeature(event);
  togglePick(feature && feature.id, event.shiftKey);
}

async function trimClick(event) {
  const feature = hitFeature(event);
  if (!feature) return;
  if (!state.trimReady) {
    state.bounds = state.bounds.includes(feature.id)
      ? state.bounds.filter((id) => id !== feature.id)
      : state.bounds.concat(feature.id);
    state.message = `Границы: ${state.bounds.length}. Enter — резать или продлевать`;
    emit();
    return;
  }
  if (state.bounds.includes(feature.id) || !feature.line) {
    state.message = "Нужна линия, которая не выбрана границей";
    emit();
    return;
  }
  const boundaries = state.features.filter((item) => state.bounds.includes(item.id)).flatMap(chainsOf);
  const point = await placePoint(worldFromEvent(event));
  try {
    const out = await post("/api/geom", {
      op: state.tool, line: feature.line, click: [point.x, point.y],
      boundaries, tolerance: Math.max(snapTolerance(), 2),
    });
    replaceFeature(feature.id, { line: out.line, arc: undefined, preview: undefined });
  } catch {
    state.message = "Нет пересечения рядом с этой точкой";
    emit();
  }
}

export function fitView() {
  const pts = state.features.flatMap(featurePoints);
  if (!pts.length) return;
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  state.origin = {
    x: (Math.min(...xs) + Math.max(...xs)) / 2,
    y: (Math.min(...ys) + Math.max(...ys)) / 2,
  };
  const canvas = ctx && ctx.canvas;
  const spanX = Math.max(1, Math.max(...xs) - Math.min(...xs));
  const spanY = Math.max(1, Math.max(...ys) - Math.min(...ys));
  if (canvas) {
    state.ppm = Math.max(0.05, Math.min(
      canvas.clientWidth / (spanX * 1.3),
      canvas.clientHeight / (spanY * 1.3),
    ));
  }
  emit();
}

export function viewBbox() {
  const crs = window.GRADO_CRS;
  if (!crs) return null;
  const corners = [[0, 0], [rect.width, 0], [rect.width, rect.height], [0, rect.height]]
    .map(([x, y]) => screenToWorld(x, y));
  const wgs = corners.map((p) => crs.localToWgs84([p.x, p.y]));
  const lons = wgs.map((p) => p[0]), lats = wgs.map((p) => p[1]);
  return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
}

export function cancelDraft() {
  draft = [];
}
