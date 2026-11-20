/* ГРАДО · рисование слоёв карты через ядро Rust (план 09.11.2026, шаг И2): единый знак, категории, диапазоны, правила,
   штриховка, подписи, слои знака (parts: линия, полоса внутрь, штриховка, значки вдоль со стороной) и знаки ЛГР REDLN97
   (lgrLine и режим lgr). Операции частей знака и типов линий REDLN97 строит ядро Rust в WebAssembly (core.ts →
   partsOps, linetypeOps) — экран и печать рисуют одним кодом. */
import { Circle, Fill, Stroke, Style, Text } from "ol/style";
import type Feature from "ol/Feature";
import type { StyleFunction } from "ol/style/Style";
import { hasLinetype, linetypeOps, loadLinetypes, partsOps, type RenderOp, type XY } from "./core";
import type { Layer } from "./types/project";

export const OTHER = "#9aa1a8";
export const RAMPS: Record<string, string[]> = {
  blue: ["#dcebfa", "#a8cbf1", "#6fa6e6", "#2a78d6", "#1a4f94", "#0f3363"],
  brick: ["#fbe4d8", "#f5b698", "#ec875b", "#cf5a2c", "#933717", "#5e200c"],
  green: ["#e1f2e3", "#b2dcb7", "#7ec188", "#3f9a4f", "#1f6e31", "#10461e"],
  grey: ["#f2f2f2", "#d4d4d4", "#aaaaaa", "#7a7a7a", "#4d4d4d", "#262626"],
};

export interface SymbolPart {
  k: "line" | "band" | "hatch" | "marks";
  c?: string;
  a?: number;
  w?: number;
  b?: number;
  dash?: number[];
  hp?: string;
  hs?: number;
  shape?: string;
  step?: number;
  size?: number;
  side?: number;
}

export interface RuleSpec {
  field: string;
  op: string;
  val: string | number;
  fill: string;
  hatch?: boolean;
  opacity?: number;
  stroke?: string;
  width?: number;
  dash?: number[];
  parts?: SymbolPart[];
  label?: string;
  labelSize?: number;
  labelColor?: string;
}

export interface LayerStyle {
  mode?: "single" | "cat" | "grad" | "rules" | "lgr";
  fill?: string;
  stroke?: string;
  strokeOwn?: boolean;
  width?: number;
  opacity?: number;
  dash?: number[];
  hatch?: boolean;
  hatchPat?: string;
  hatchStep?: number;
  hatchColor?: string;
  label?: string;
  labelSize?: number;
  labelColor?: string;
  labelAngle?: boolean;
  floorsDen?: number;
  marker?: boolean;
  lgrLine?: number;
  parts?: SymbolPart[];
  cat?: { field?: string; colors?: Record<string, string>; off?: string[]; sym?: Record<string, Partial<LayerStyle>> };
  grad?: { field?: string; n?: number; ramp?: string; method?: string };
  rules?: { list?: RuleSpec[]; elseFill?: string; elseHide?: boolean };
}

type LgrFamily = { s?: string; b?: string; t?: string };
const LGRC: Record<number, string> = {};
const LGRD: Record<number, number[]> = {};
let lgrMap: Record<string, Record<string, LgrFamily>> = {};
let libsPromise: Promise<void> | null = null;

/** Загружает библиотеки типов линий REDLN97 и цветов Эталона ЛГР один раз; передаёт REDLN97 в ядро Rust. */
export function loadSymbologyLibs(): Promise<void> {
  if (!libsPromise && typeof fetch !== "undefined") {
    libsPromise = (async () => {
      try {
        const [redText, lgrRes] = await Promise.all([
          fetch("/styles/redln97.json").then(r => (r.ok ? r.text() : "")),
          fetch("/styles/moscow_lgr.json").then(r => (r.ok ? r.json() : null)),
        ]);
        if (redText) {
          loadLinetypes(redText);
          const parsed = JSON.parse(redText);
          lgrMap = parsed.lgr || {};
        }
        if (lgrRes?.styles) {
          for (const s of Object.values(lgrRes.styles) as { lgr_code?: number; stroke?: string; dash_mm?: number[] }[]) {
            if (s.lgr_code != null) {
              if (s.stroke) LGRC[+s.lgr_code] = s.stroke;
              if (s.dash_mm) LGRD[+s.lgr_code] = s.dash_mm.map(v => v * 2);
            }
          }
        }
      } catch { /* без сети и стилей линии рисуются сплошными */ }
    })();
  }
  return libsPromise || Promise.resolve();
}

export function lgrForCode(code: number, sign: number, family = "00"): string | null {
  const fams = lgrMap[String(Math.abs(code))];
  if (!fams) return null;
  const f = fams[family] || Object.values(fams)[0];
  if (!f) return null;
  const name = f.s || f[sign > 0 ? "b" : "t"] || f[sign > 0 ? "t" : "b"] || null;
  return name && hasLinetype(name) ? name : null;
}

const lgrColor = (code: number): string => LGRC[Math.abs(code)] || "#d7191c";
const ltCode = (n: string): number | null => {
  const m = /^L(\d\d)s(\d\d)/i.exec(n) || /^L(\d\d)[bt](\d\d)/i.exec(n);
  return m ? (/^L\d\ds/i.test(n) ? +m[2] : +m[1]) : null;
};

const ramp = (name: string, k: number): string[] => {
  const arr = RAMPS[name] || RAMPS.blue;
  return k <= 1 ? [arr[3]] : Array.from({ length: k }, (_, i) => arr[Math.round((i * (arr.length - 1)) / Math.max(1, k - 1))]);
};

export function rgba(hex: string | undefined, a: number): string {
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.exec(hex || "");
  if (!m) return `rgba(80,90,110,${a})`;
  const h = m[1].length === 3 ? m[1].split("").map(x => x + x).join("") : m[1].slice(0, 6);
  return `rgba(${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)},${a})`;
}

const cssRgb = (c: [number, number, number]): string =>
  `rgb(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)})`;

const PAT = new Map<string, CanvasPattern | string>();
function hatchPattern(color: string, pat = "45", step = 8): CanvasPattern | string {
  if (typeof document === "undefined") return rgba(color, 0.35);
  const k = `${color}|${pat}|${step}`;
  const hit = PAT.get(k);
  if (hit) return hit;
  const n = Math.max(4, Math.min(40, Math.round(step)));
  const c = document.createElement("canvas");
  c.width = c.height = n;
  const x = c.getContext("2d");
  if (!x) return rgba(color, 0.35);
  x.fillStyle = rgba(color, 0.1);
  x.fillRect(0, 0, n, n);
  x.strokeStyle = x.fillStyle = color;
  x.lineWidth = 1.1;
  x.beginPath();
  const d45 = () => { x.moveTo(0, n); x.lineTo(n, 0); x.moveTo(-n / 2, n / 2); x.lineTo(n / 2, -n / 2); x.moveTo(n / 2, n * 1.5); x.lineTo(n * 1.5, n / 2); };
  const d135 = () => { x.moveTo(0, 0); x.lineTo(n, n); x.moveTo(-n / 2, n / 2); x.lineTo(n / 2, n * 1.5); x.moveTo(n / 2, -n / 2); x.lineTo(n * 1.5, n / 2); };
  const h = () => { x.moveTo(0, n / 2); x.lineTo(n, n / 2); };
  const v = () => { x.moveTo(n / 2, 0); x.lineTo(n / 2, n); };
  if (pat === "dots") { x.arc(n / 2, n / 2, 1.2, 0, 2 * Math.PI); x.fill(); }
  else { ({ "45": [d45], "135": [d135], "0": [h], "90": [v], x45: [d45, d135], x0: [h, v] }[pat] || [d45]).forEach(fn => fn()); x.stroke(); }
  const p = x.createPattern(c, "repeat") || rgba(color, 0.35);
  PAT.set(k, p);
  return p;
}

function tracePath(ctx: CanvasRenderingContext2D, rings: XY[][], close?: boolean) {
  ctx.beginPath();
  for (const r of rings) {
    r.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
    if (close) ctx.closePath();
  }
}

/** Отрисовка операций рендера ядра Rust (path, clip, unclip) на canvas слоя OpenLayers. */
export function drawOps(ctx: CanvasRenderingContext2D, ops: RenderOp[]) {
  let depth = 0;
  for (const o of ops) {
    if (o.op === "clip") { ctx.save(); depth++; tracePath(ctx, o.rings, true); ctx.clip("evenodd"); continue; }
    if (o.op === "unclip") { if (depth) { ctx.restore(); depth--; } continue; }
    if (o.op !== "path") continue;
    tracePath(ctx, o.rings, o.closed);
    ctx.globalAlpha = o.alpha ?? 1;
    if (o.fill) { ctx.fillStyle = cssRgb(o.fill); ctx.fill("evenodd"); }
    if (o.stroke && (o.width ?? 0) > 0) {
      ctx.strokeStyle = cssRgb(o.stroke);
      ctx.lineWidth = o.width!;
      ctx.setLineDash(o.dash || []);
      ctx.lineJoin = "round";
      ctx.lineCap = o.cap || (o.dash ? "butt" : "round");
      ctx.stroke();
    }
  }
  while (depth--) ctx.restore();
}

const ringArea = (r: XY[]): number => {
  let a = 0;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) a += r[j][0] * r[i][1] - r[i][0] * r[j][1];
  return a;
};

function drawLgrLine(ctx: CanvasRenderingContext2D, pts: XY[], name: string | null, k: number, color: string, width: number, plain: boolean, dashFallback?: number[]) {
  if (name && !plain) {
    const ops = linetypeOps(pts, name, k, 0, color, width);
    if (ops.length) {
      for (const o of ops) o.cap = o.join === "round" ? "round" : "butt";
      ctx.save();
      drawOps(ctx, ops);
      ctx.restore();
      return;
    }
  }
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  if (dashFallback && !plain) ctx.setLineDash(dashFallback.map(v => v * k));
  ctx.beginPath();
  pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
  ctx.stroke();
  ctx.restore();
}

function ownLgrStyle(code: number, width: number, lat: () => number): Style {
  const c = Math.abs(code), sign = code < 0 ? -1 : 1;
  return new Style({
    renderer(coords, st) {
      const ctx = st.context, pr = st.pixelRatio;
      const mpp = st.resolution * Math.cos((lat() * Math.PI) / 180), k = pr / mpp, plain = mpp / 0.000264583 > 10000;
      const name = lgrForCode(c, sign), w = Math.max(1, width) * 1.3 * pr, col = lgrColor(c);
      const t = st.geometry.getType(), lines: XY[][] = [];
      if (t === "Polygon" || t === "MultiPolygon") {
        const polys = (t === "Polygon" ? [coords] : coords) as XY[][][];
        for (const poly of polys) {
          poly.forEach((r, i) => {
            const want = (i ? -1 : 1) * sign;
            lines.push(Math.sign(ringArea(r)) === want ? r : r.slice().reverse());
          });
        }
      } else {
        const raw = coords as unknown;
        lines.push(...(typeof (raw as number[][])[0]?.[0] === "number" ? [raw as XY[]] : (raw as XY[][])));
      }
      for (const pts of lines) drawLgrLine(ctx, pts, name, k, col, w, plain, LGRD[c]);
    },
  });
}

function redLineStyle(f: Feature, lat: () => number): Style {
  return new Style({
    renderer(coords, st) {
      const ctx = st.context, pr = st.pixelRatio;
      const mpp = st.resolution * Math.cos((lat() * Math.PI) / 180), k = pr / mpp, plain = mpp / 0.000264583 > 10000;
      const raw = coords as unknown;
      const lines: XY[][] = typeof (raw as number[][])[0]?.[0] === "number" ? [raw as XY[]] : (raw as XY[][]);
      const lt = (f.get("_lt") as string[] | undefined) || [];
      const miss = (f.get("_miss") as [number, number][] | undefined) || [];
      for (const pts of lines) {
        for (const n of lt) drawLgrLine(ctx, pts, hasLinetype(n) ? n : null, k, LGRC[ltCode(n) || 0] || "#d7191c", 1.3 * pr, plain);
        for (const [c] of miss) drawLgrLine(ctx, pts, null, k, LGRC[c] || "#888888", 1.3 * pr, plain, LGRD[c]);
        if (!lt.length && !miss.length) drawLgrLine(ctx, pts, null, k, "#999999", pr, true);
      }
    },
  });
}

function partStyles(parts: SymbolPart[] | undefined, g: string): Style[] {
  const poly = g === "poly";
  return (parts || [])
    .filter(p => poly || p.k === "line" || p.k === "marks")
    .map(p => new Style({
      renderer(coords, st) {
        const ctx = st.context, closed = poly && /Polygon/.test(st.geometry.getType());
        const t = st.geometry.getType();
        const shapes = closed ? (t === "Polygon" ? [coords] : coords) : (typeof (coords as number[][])[0]?.[0] === "number" ? [coords] : coords);
        const ops = partsOps(closed ? "poly" : "line", shapes, [p], st.pixelRatio);
        if (ops.length) {
          ctx.save();
          drawOps(ctx, ops);
          ctx.restore();
        }
      },
    }));
}

const isNum = (v: unknown): boolean => typeof v === "number" || (v !== "" && v != null && !isNaN(Number(v)));
const numOf = (v: unknown): number => (v == null || v === "" ? NaN : Number(v));

function testRule(r: RuleSpec, get: (k: string) => unknown): boolean {
  const v = get(r.field), t = r.val;
  if (v == null) return false;
  if (r.op === "содержит") return String(v).toLowerCase().includes(String(t).toLowerCase());
  const n = isNum(v) && isNum(t), a = n ? Number(v) : String(v), b = n ? Number(t) : String(t);
  return ({ "=": a == b, "≠": a != b, ">": a > b, "<": a < b, "≥": a >= b, "≤": a <= b } as Record<string, boolean>)[r.op] || false;
}

function breaksOf(st: LayerStyle, fc: { features?: { properties?: Record<string, unknown> }[] } | null): number[] {
  const g = st.grad || {}, n = g.n || 5, field = g.field || "";
  const v = (fc?.features || []).map(f => numOf(f.properties?.[field])).filter(x => !isNaN(x)).sort((a, b) => a - b);
  if (!v.length) return [0, 0];
  const b = [v[0]];
  for (let i = 1; i < n; i++) b.push(+(g.method === "equal" ? v[0] + ((v[v.length - 1] - v[0]) * i) / n : v[Math.floor((i * v.length) / n)]).toFixed(2));
  b.push(v[v.length - 1]);
  const u = [...new Set(b)];
  return u.length > 1 ? u : [u[0], u[0]];
}

/** Образец слоя для списка слоёв: цвет заливки, контура и признак пунктира. */
export function swatchOf(l: Layer): { fill: string; stroke: string; dash: boolean } {
  if (l.role === "territory") return { fill: "rgba(36,70,216,0.08)", stroke: "#2446d8", dash: true };
  const st = (l.style || {}) as LayerStyle;
  if (st.mode === "lgr" || st.lgrLine) {
    const c = st.lgrLine ? lgrColor(st.lgrLine) : "#d7191c";
    return { fill: rgba(st.fill || c, st.opacity ?? 0.2), stroke: c, dash: false };
  }
  const fillHex =
    st.mode === "cat" ? Object.values(st.cat?.colors || {})[0] || st.fill || OTHER
    : st.mode === "grad" ? ramp(st.grad?.ramp || "blue", 3)[1]
    : st.mode === "rules" ? st.rules?.list?.[0]?.fill || st.rules?.elseFill || OTHER
    : st.fill || OTHER;
  return {
    fill: l.geom === "line" ? "transparent" : rgba(fillHex, st.opacity ?? 0.35),
    stroke: st.stroke || fillHex,
    dash: !!st.dash?.length,
  };
}

/** Функция стиля OpenLayers для слоя проекта l: использует ядро Rust для частей знака и линий ЛГР. */
export function layerStyleFunction(l: Layer, fc: unknown, lat: () => number): StyleFunction {
  const baseSt: LayerStyle = {
    mode: "single", fill: "#9aa1a8", stroke: "#5f6368", width: 1.5, opacity: 0.35, hatch: false, label: "", labelSize: 11,
    ...((l.style || {}) as LayerStyle),
  };
  if (l.role === "territory" && !l.style) {
    return () => new Style({
      stroke: new Stroke({ color: "#2446d8", width: 3, lineDash: [8, 5] }),
      fill: new Fill({ color: "rgba(36,70,216,0.04)" }),
    });
  }
  const br = baseSt.mode === "grad" ? breaksOf(baseSt, fc as { features?: { properties?: Record<string, unknown> }[] }) : [0, 0];
  const cache = new Map<string, Style[]>();

  return (feature, res) => {
    const f = feature as Feature;
    if (baseSt.mode === "lgr") return [redLineStyle(f, lat)];

    let fill = baseSt.fill || OTHER, hatch = !!baseSt.hatch, hide = false, id = "s";
    let over: Partial<LayerStyle> | null = null;
    if (baseSt.mode === "cat") {
      const v = String(f.get(baseSt.cat?.field || "") ?? "");
      fill = baseSt.cat?.colors?.[v] || OTHER;
      hide = (baseSt.cat?.off || []).includes(v);
      over = baseSt.cat?.sym?.[v] || null;
      if (over?.hatch != null) hatch = !!over.hatch;
      id = "c:" + v;
    } else if (baseSt.mode === "grad") {
      const cols = ramp(baseSt.grad?.ramp || "blue", br.length - 1);
      const v = numOf(f.get(baseSt.grad?.field || ""));
      const i = br.findIndex((x, k) => k > 0 && v <= x);
      fill = isNaN(v) ? OTHER : cols[Math.max(0, i - 1)] ?? cols[cols.length - 1];
      id = "g:" + fill;
    } else if (baseSt.mode === "rules") {
      const list = baseSt.rules?.list || [];
      const i = list.findIndex(r => r.field && testRule(r, k => f.get(k)));
      const r = list[i];
      if (r) { fill = r.fill; hatch = !!r.hatch; over = r; id = "r:" + i; }
      else { fill = baseSt.rules?.elseFill || "#dddddd"; hatch = false; hide = !!baseSt.rules?.elseHide; id = "e"; }
    }
    if (hide) return [];

    const eff: LayerStyle = over ? { ...baseSt, ...over, strokeOwn: baseSt.strokeOwn || over.stroke != null } : baseSt;
    const ft = f.getGeometry()?.getType() || "";
    const g = /Point/.test(ft) ? "point" : /Line/.test(ft) && l.geom !== "line" ? (l.geom === "poly" ? "pline" : "line") : (l.geom || "poly");
    const key = `${id}|${fill}|${hatch}|${g}|${l.role === "territory"}`;
    let styles = cache.get(key);
    if (!styles) {
      const w = l.role === "territory" ? Math.max(eff.width ?? 2, 2.5) : (eff.width ?? 1.5);
      const edge = l.role === "territory" && !l.style ? "#2446d8" : (hatch && !eff.strokeOwn ? (eff.hatchColor || fill) : (eff.stroke || fill));
      const dash = eff.dash?.length ? eff.dash : (l.role === "territory" && !eff.lgrLine ? [8, 5] : undefined);
      const fillObj = new Fill({
        color: hatch ? hatchPattern(eff.hatchColor || fill, eff.hatchPat, eff.hatchStep) : rgba(fill, l.role === "territory" ? Math.min(eff.opacity ?? 0, 0.12) : (eff.opacity ?? 0.35)),
      });
      const base: Style[] = [];
      if (eff.lgrLine && g !== "point") {
        if (g === "poly") base.push(new Style({ fill: fillObj }));
        base.push(ownLgrStyle(eff.lgrLine, w, lat));
      } else if (g === "line" || g === "pline") {
        base.push(new Style({ stroke: new Stroke({ color: g === "line" ? fill : edge, width: Math.max(w, 1), lineCap: dash ? "butt" : "round", lineJoin: "round", lineDash: dash }) }));
      } else if (g === "point") {
        if (eff.marker !== false) {
          base.push(new Style({ image: new Circle({ radius: 2 + w * 2, fill: new Fill({ color: fill }), stroke: new Stroke({ color: eff.stroke || "#333", width: 1 }) }) }));
        }
      } else {
        if (hatch && eff.hatchColor && (eff.opacity ?? 0) > 0) {
          base.push(new Style({ fill: new Fill({ color: rgba(fill, eff.opacity ?? 0.35) }) }));
        }
        base.push(new Style({
          fill: fillObj,
          stroke: w > 0 ? new Stroke({ color: edge, width: w, lineDash: dash }) : undefined,
        }));
      }
      if (eff.parts?.length) base.push(...partStyles(eff.parts, g));
      cache.set(key, (styles = base));
    }

    const out = [...styles];
    if (eff.label && res < 4) {
      let t = f.get(eff.label);
      if (t != null && t !== "") {
        if (eff.label === "Этажность" && l.key.startsWith("user:")) t = `${t} эт.`;
        out.push(new Style({
          text: new Text({
            text: String(t),
            font: `${eff.labelSize || 11}px Onest, system-ui, sans-serif`,
            fill: new Fill({ color: eff.labelColor || "#1d1d1f" }),
            stroke: new Stroke({ color: "#ffffff", width: 3 }),
            placement: g === "line" ? "line" : "point",
            overflow: false,
          }),
        }));
      }
    }
    return out;
  };
}
