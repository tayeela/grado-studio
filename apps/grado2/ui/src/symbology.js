/* ГРАДО 2 · оформление слоёв в новом интерфейсе: единое, категории, диапазоны, правила, знаки ЛГР, штриховка, подписи,
   видимость по масштабу. Перенос web/layers.js (cleanStyle, symbolOf, breaks, testRule, styleFor) и web/app.js (hatch,
   redLineStyle) на модули: значения по умолчанию и цвета те же, чтобы файл проекта рисовался одинаково в обеих страницах.
   Знаки REDLN97 рисует тот же web/linetype.js. Окно «Свойства» правит стиль, MapPanel строит из него стиль OpenLayers. */
import { Circle, Fill, Stroke, Style, Text } from "ol/style.js";
import MultiLineString from "ol/geom/MultiLineString.js";
import { fromLonLat } from "ol/proj.js";
import "../../web/linetype.js";

export const CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"], OTHER = "#9aa1a8";
export const RAMPS = {
  blue: ["#dcebfa", "#a8cbf1", "#6fa6e6", "#2a78d6", "#1a4f94", "#0f3363"], brick: ["#fbe4d8", "#f5b698", "#ec875b", "#cf5a2c", "#933717", "#5e200c"],
  green: ["#e1f2e3", "#b2dcb7", "#7ec188", "#3f9a4f", "#1f6e31", "#10461e"], grey: ["#f2f2f2", "#d4d4d4", "#aaaaaa", "#7a7a7a", "#4d4d4d", "#262626"],
};
export const RAMP_TITLES = { blue: "синяя", brick: "кирпичная", green: "зелёная", grey: "серая" };
export const HATCHES = { "45": "косая ／", "135": "косая ＼", "0": "горизонтальная", "90": "вертикальная", "x45": "косая сетка", "x0": "прямая сетка", "dots": "точки" };
export const OPS = ["=", "≠", ">", "<", "≥", "≤", "содержит"];
export const DENS = [0, 1000, 2000, 2500, 5000, 10000, 25000];
export const ramp = (n, k) => k === 1 ? [RAMPS[n][3]] : Array.from({ length: k }, (_, i) => RAMPS[n][Math.round(i * (RAMPS[n].length - 1) / Math.max(1, k - 1))]);

const HEX = /^#[0-9a-f]{3,8}$/i, okc = (c, d) => typeof c === "string" && HEX.test(c) ? c : d;
export const okn = (v, d) => { const n = typeof v === "number" || (typeof v === "string" && v.trim() !== "") ? Number(v) : NaN; return Number.isFinite(n) ? n : d; };
export const isNum = v => typeof v === "number" || (v !== "" && v != null && !isNaN(+v));
const numOf = v => v == null || v === "" ? NaN : +v;

/* Стиль слоя со всеми полями (как web/layers.js ST = cleanStyle(stDefaults)): чужие значения из файла заменяются умолчаниями. */
export function fullStyle(o = {}) {
  const st = {
    mode: "single", fill: "#9aa1a8", stroke: "#5f6368", width: 1, opacity: .7, hatch: false, label: "", labelSize: 11, ...o,
    cat: { field: "", colors: {}, off: [], ...(o.cat || {}) },
    grad: { field: "", n: 5, ramp: "blue", method: "quantile", ...(o.grad || {}) },
    rules: { list: [], elseFill: "#dddddd", elseHide: false, ...(o.rules || {}) },
  };
  st.width = okn(st.width, 1); st.opacity = okn(st.opacity, .7); st.labelSize = okn(st.labelSize, 11);
  if (st.floorsDen != null && ![0, 2000, 5000].includes(Number(st.floorsDen))) delete st.floorsDen; else if (st.floorsDen != null) st.floorsDen = Number(st.floorsDen);
  ["hatchStep", "maxDen", "minDen"].forEach(k => { if (st[k] != null) { const n = okn(st[k], 0); if (n) st[k] = n; else delete st[k]; } });
  st.fill = okc(st.fill, "#9aa1a8"); st.stroke = okc(st.stroke, "#5f6368");
  if (!Object.hasOwn(RAMPS, st.grad.ramp)) st.grad.ramp = "blue";
  st.rules.elseFill = okc(st.rules.elseFill, "#dddddd");
  st.rules.list = (st.rules.list || []).map(r => ({ field: "", op: "=", val: "", ...r, fill: okc(r?.fill, "#9aa1a8") }));
  st.cat.colors = Object.fromEntries(Object.entries(st.cat.colors || {}).map(([k, c]) => [k, okc(c, "#9aa1a8")]));
  st.cat.off = Array.isArray(st.cat.off) ? st.cat.off : [];
  return st;
}

/* ---------- поля и значения слоя (по GeoJSON из файла проекта) ---------- */
const hidden = k => k.startsWith("_") || k === "gradosym" || k === "geometry";
export function fieldsOf(fc) {
  const s = new Set();
  for (const f of fc?.features || []) for (const k in f.properties || {}) s.add(k);
  return [...s].filter(k => !hidden(k)).sort((a, b) => /[а-яё]/i.test(b) - /[а-яё]/i.test(a));
}
export function numFields(fc) {
  const fs = (fc?.features || []).slice(0, 300);
  return fieldsOf(fc).filter(k => fs.length && fs.every(f => f.properties?.[k] == null || isNum(f.properties[k])));
}
export function catValues(fc, field) {
  const m = new Map();
  for (const f of fc?.features || []) { const v = String(f.properties?.[field] ?? ""); m.set(v, (m.get(v) || 0) + 1); }
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}
/* «Классифицировать»: поле по умолчанию — текстовое с 2–30 значениями; цвета по порядку, остальное серым. */
export function assignCats(st, fc, keep) {
  if (!st.cat.field) {
    const fs = fieldsOf(fc), nf = numFields(fc), txt = fs.filter(k => !nf.includes(k)), feats = (fc?.features || []).slice(0, 5000);
    const nv = k => new Set(feats.map(f => String(f.properties?.[k] ?? ""))).size;
    st.cat.field = txt.find(k => { const n = nv(k); return n >= 2 && n <= 30; }) || txt[0] || fs[0] || "";
  }
  const c = keep ? { ...st.cat.colors } : {}; let k = Object.keys(c).length;
  catValues(fc, st.cat.field).forEach(([v]) => { if (!c[v]) c[v] = k < CAT.length ? CAT[k++] : OTHER; });
  st.cat.colors = c; if (!keep) st.cat.off = [];
}
export function breaks(st, fc) {
  const g = st.grad, v = (fc?.features || []).map(f => numOf(f.properties?.[g.field])).filter(x => !isNaN(x)).sort((a, b) => a - b);
  if (!v.length) return [0, 0];
  const b = [v[0]];
  for (let i = 1; i < g.n; i++) b.push(+(g.method === "equal" ? v[0] + (v[v.length - 1] - v[0]) * i / g.n : v[Math.floor(i * v.length / g.n)]).toFixed(2));
  b.push(v[v.length - 1]);
  const u = [...new Set(b)]; return u.length > 1 ? u : [u[0], u[0]];
}
export function testRule(r, get) {
  const v = get(r.field), t = r.val; if (v == null) return false;
  if (r.op === "содержит") return String(v).toLowerCase().includes(String(t).toLowerCase());
  const n = isNum(v) && isNum(t), a = n ? +v : String(v), b = n ? +t : String(t);
  return { "=": a == b, "≠": a != b, ">": a > b, "<": a < b, "≥": a >= b, "≤": a <= b }[r.op];
}
export const ruleCount = (r, fc) => (fc?.features || []).filter(f => testRule(r, k => f.properties?.[k])).length;

/* Цвет, штриховка и «скрыт» одного объекта; br — границы диапазонов (считаются один раз на слой). */
export function symbolOf(st, get, br) {
  let fill = st.fill, hatch = st.hatch, hide = false;
  if (st.mode === "cat") { const v = String(get(st.cat.field) ?? ""); fill = st.cat.colors[v] || OTHER; hide = st.cat.off.includes(v); }
  else if (st.mode === "grad") {
    const cols = ramp(st.grad.ramp, br.length - 1), v = numOf(get(st.grad.field)), i = br.findIndex((x, k) => k > 0 && v <= x);
    fill = isNaN(v) ? OTHER : cols[Math.max(0, i - 1)] ?? cols[cols.length - 1];
  } else if (st.mode === "rules") {
    const r = st.rules.list.find(r => r.field && testRule(r, get));
    if (r) { fill = r.fill; hatch = r.hatch; } else { fill = st.rules.elseFill; hatch = false; hide = st.rules.elseHide; }
  }
  return { fill, hatch, hide };
}

/* Пункты легенды для окна «Свойства» и списка слоёв. */
export function legendItems(st, fc) {
  if (st.mode === "cat") return catValues(fc, st.cat.field).map(([v, n]) => ({ v, n, c: st.cat.colors[v] || OTHER, off: st.cat.off.includes(v) }));
  if (st.mode === "grad") {
    const b = breaks(st, fc), none = (fc?.features || []).filter(f => isNaN(numOf(f.properties?.[st.grad.field]))).length;
    const fmt = x => Number(x).toLocaleString("ru-RU", { maximumFractionDigits: 1 });
    return ramp(st.grad.ramp, b.length - 1).map((c, i) => ({ v: `${fmt(b[i])} – ${fmt(b[i + 1])}`, c })).concat(none ? [{ v: "нет значения", c: OTHER, n: none }] : []);
  }
  if (st.mode === "rules") return st.rules.list.map(r => ({ v: `${r.field} ${r.op} ${r.val}`, c: r.fill })).concat(st.rules.elseHide ? [] : [{ v: "остальные", c: st.rules.elseFill }]);
  return [];
}

/* Образец слоя в списке: цвет единого стиля, первой категории, середины шкалы или первого правила. */
export function swatchColor(st) {
  if (st.mode === "lgr") return "#d7191c";
  return st.mode === "single" ? st.fill : st.mode === "cat" ? (Object.values(st.cat.colors)[0] || OTHER) : st.mode === "grad" ? ramp(st.grad.ramp, 3)[1] : (st.rules.list[0]?.fill || st.rules.elseFill);
}

/* ---------- штриховка и знаки ЛГР ---------- */
const PAT = new Map();
export function hatch(color, pat = "45", step = 8) {
  const k = color + "|" + pat + "|" + step; if (PAT.has(k)) return PAT.get(k);
  const n = Math.max(4, Math.min(40, Math.round(step))), c = document.createElement("canvas"); c.width = c.height = n; const x = c.getContext("2d");
  x.fillStyle = color + "18"; x.fillRect(0, 0, n, n); x.strokeStyle = x.fillStyle = color; x.lineWidth = 1.1; x.beginPath();
  const d45 = () => { x.moveTo(0, n); x.lineTo(n, 0); x.moveTo(-n / 2, n / 2); x.lineTo(n / 2, -n / 2); x.moveTo(n / 2, n * 1.5); x.lineTo(n * 1.5, n / 2); };
  const d135 = () => { x.moveTo(0, 0); x.lineTo(n, n); x.moveTo(-n / 2, n / 2); x.lineTo(n / 2, n * 1.5); x.moveTo(n / 2, -n / 2); x.lineTo(n * 1.5, n / 2); };
  const h = () => { x.moveTo(0, n / 2); x.lineTo(n, n / 2); }, v = () => { x.moveTo(n / 2, 0); x.lineTo(n / 2, n); };
  if (pat === "dots") { x.arc(n / 2, n / 2, 1.2, 0, 2 * Math.PI); x.fill(); }
  else { ({ "45": [d45], "135": [d135], "0": [h], "90": [v], x45: [d45, d135], x0: [h, v] }[pat] || [d45]).forEach(f => f()); x.stroke(); }
  const p = x.createPattern(c, "repeat"); PAT.set(k, p); return p;
}

const LGRC = {}, LGRD = {};
let libs = null;
/* Библиотеки знаков ЛГР: цвета и штрихи кодов, типы линий REDLN97 (те же файлы /styles/, что у рабочей страницы). */
export function loadLibs() {
  return libs ||= (async () => {
    try {
      await window.Linetypes.load();
      const lgr = await (await fetch("/styles/moscow_lgr.json")).json();
      Object.values(lgr.styles).forEach(s => { if (s.lgr_code != null) { LGRC[+s.lgr_code] = s.stroke; if (s.dash_mm) LGRD[+s.lgr_code] = s.dash_mm.map(v => v * 2); } });
    } catch { /* без библиотек линии ЛГР рисуются сплошными */ }
  })();
}
const ltCode = n => { const m = /^L(\d\d)s(\d\d)/i.exec(n) || /^L(\d\d)[bt](\d\d)/i.exec(n); return m ? (/^L\d\ds/i.test(n) ? +m[2] : +m[1]) : null; };
const redLineStyle = (f, lat) => new Style({ renderer(coords, st) {
  const ctx = st.context, pr = st.pixelRatio, mpp = st.resolution * Math.cos(lat * Math.PI / 180), k = pr / mpp, plain = mpp / 0.000264583 > 10000;
  const lines = typeof coords[0][0] === "number" ? [coords] : coords, lt = f.get("_lt") || [], miss = f.get("_miss") || [];
  for (const pts of lines) {
    lt.forEach(n => window.Linetypes.draw(ctx, pts, n, k, { color: LGRC[ltCode(n)] || "#d7191c", width: 1.3 * pr, plain }));
    miss.forEach(([c]) => { ctx.save(); ctx.strokeStyle = LGRC[c] || "#888"; ctx.lineWidth = 1.3 * pr; if (LGRD[c] && !plain) ctx.setLineDash(LGRD[c].map(v => v * k)); ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(...p) : ctx.moveTo(...p)); ctx.stroke(); ctx.restore(); });
    if (!lt.length && !miss.length) { ctx.save(); ctx.strokeStyle = "#999"; ctx.lineWidth = pr; ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(...p) : ctx.moveTo(...p)); ctx.stroke(); ctx.restore(); }
  }
} });

/* Полигон, обрезанный по области выгрузки (ЕГКО): рёбра на рамке не обводятся (web/layers.js frameless). */
function frameless(ft) {
  const g = ft.getGeometry(), b = ft.get("_clip"); if (!b || !g) return g;
  const rev = g.getRevision(); if (ft._fl?.rev === rev) return ft._fl.g;
  const [x0, y0] = fromLonLat([b[0], b[1]]), [x1, y1] = fromLonLat([b[2], b[3]]);
  const onFrame = (a, c) => a[0] === c[0] && (a[0] === x0 || a[0] === x1) || a[1] === c[1] && (a[1] === y0 || a[1] === y1);
  const lines = [], polys = g.getType() === "MultiPolygon" ? g.getCoordinates() : [g.getCoordinates()];
  for (const p of polys) for (const r of p) {
    let cur = [];
    for (let i = 1; i < r.length; i++) {
      if (onFrame(r[i - 1], r[i])) { if (cur.length > 1) lines.push(cur); cur = []; }
      else { if (!cur.length) cur.push(r[i - 1]); cur.push(r[i]); }
    }
    if (cur.length > 1) lines.push(cur);
  }
  ft._fl = { rev, g: new MultiLineString(lines) }; return ft._fl.g;
}

const rgba = (hex, a) => {
  let h = hex.slice(1); if (h.length <= 4) h = [...h].map(c => c + c).join("");
  const n = parseInt(h.slice(0, 6), 16);
  return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`;
};
const upright = a => { a = ((a % 360) + 360) % 360; return a > 90 && a <= 270 ? a - 180 : a > 270 ? a - 360 : a; };
const labelDeg = f => f.get("_angle") != null ? +f.get("_angle") : -(+f.get("textangle") || 0);
export const floorsDenOf = l => l.style?.floorsDen != null ? l.style.floorsDen : /^user:/.test(l.key) && /^Эскиз/.test(l.title || "") ? 2000 : 0;
/* знаменатель масштаба по разрешению и широте (web/layers.js scaleDen) */
export const scaleDen = (res, lat) => Math.round(res * Math.cos(lat * Math.PI / 180) / 0.000264583 / 10) * 10;
export const denToRes = (den, lat) => den * 0.000264583 / Math.cos(lat * Math.PI / 180);

/* Функция стиля OpenLayers для слоя l (поля как в файле: key, title, geom, style); fc — его данные, lat() — широта вида. */
export function styleFunction(l, fc, lat) {
  const st = fullStyle(l.style), cache = new Map(), br = st.mode === "grad" ? breaks(st, fc) : null;
  return (f, res) => {
    const out = [];
    if (st.mode === "lgr") out.push(redLineStyle(f, lat()));
    else {
      const s = symbolOf(st, k => f.get(k), br); if (s.hide) return null;
      const ft = f.getGeometry()?.getType() || "", g = /Point/.test(ft) ? "point" : /Line/.test(ft) && l.geom !== "line" ? (l.geom === "poly" ? "pline" : "line") : l.geom;
      const clip = g === "poly" && st.width > 0 && !!f.get("_clip");
      const key = `${s.fill}|${s.hatch}|${g}|${clip}`; let base = cache.get(key);
      const edge = s.hatch && !st.strokeOwn ? s.fill : st.stroke, dash = st.dash?.length ? st.dash : undefined;
      if (!base) {
        const fillOf = () => new Fill({ color: s.hatch ? hatch(s.fill, st.hatchPat, st.hatchStep) : rgba(s.fill, st.opacity) });
        if (g === "line") base = new Style({ stroke: new Stroke({ color: s.fill, width: st.width, lineCap: dash ? "butt" : "round", lineJoin: "round", lineDash: dash }) });
        else if (g === "pline") base = new Style({ stroke: new Stroke({ color: edge, width: Math.max(st.width, 1), lineCap: "round", lineJoin: "round", lineDash: dash }) });
        else if (g === "point" && st.marker === false) base = [];
        else if (g === "point") base = new Style({ image: new Circle({ declutterMode: "obstacle", radius: 2 + st.width * 2, fill: new Fill({ color: s.fill }), stroke: new Stroke({ color: st.stroke, width: 1 }) }) });
        else if (clip) base = [new Style({ fill: fillOf() }), new Style({ geometry: frameless, stroke: new Stroke({ color: edge, width: st.width, lineDash: dash }) })];
        else base = new Style({ fill: fillOf(), stroke: st.width > 0 ? new Stroke({ color: edge, width: st.width, lineDash: dash }) : undefined });
        cache.set(key, base);
      }
      Array.isArray(base) ? out.push(...base) : out.push(base);
    }
    if (st.label && res < 4) {
      let t = f.get(st.label);
      if (t != null && t !== "") {
        if (st.label === "Этажность" && String(l.key).startsWith("user:")) t = t + " эт.";
        const fd = st.label === "Этажность" ? floorsDenOf(l) : 0;
        if (!fd || scaleDen(res, lat()) <= fd) {
          const ang = st.labelAngle ? -upright(labelDeg(f)) * Math.PI / 180 : 0, bare = st.marker === false;
          out.push(new Style({ text: new Text({
            text: String(t), font: `${st.labelSize}px Onest, system-ui, sans-serif`, fill: new Fill({ color: st.labelColor || "#1d1d1f" }), stroke: new Stroke({ color: "#fff", width: 3 }),
            placement: l.geom === "line" ? "line" : "point", rotation: ang, rotateWithView: !!st.labelAngle,
            offsetY: l.geom === "point" && !bare ? -(2 + st.width * 2 + 1 + st.labelSize * 0.6 + 5) : 0, overflow: false,
          }) }));
        }
      }
    }
    return out;
  };
}
