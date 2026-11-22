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
export const CAT = [
  "#2a78d6", "#d95f02", "#1b9e77", "#7570b3", "#e7298a", "#66a61e",
  "#e6ab02", "#a6761d", "#008080", "#8c564b", "#c0392b", "#4e79a7",
];
export const RAMPS: Record<string, string[]> = {
  blue: ["#dcebfa", "#a8cbf1", "#6fa6e6", "#2a78d6", "#1a4f94", "#0f3363"],
  brick: ["#fbe4d8", "#f5b698", "#ec875b", "#cf5a2c", "#933717", "#5e200c"],
  green: ["#e1f2e3", "#b2dcb7", "#7ec188", "#3f9a4f", "#1f6e31", "#10461e"],
  grey: ["#f2f2f2", "#d4d4d4", "#aaaaaa", "#7a7a7a", "#4d4d4d", "#262626"],
};
export const RAMP_TITLES: Record<string, string> = {
  blue: "синяя",
  brick: "терракотовая",
  green: "зелёная",
  grey: "серая",
};
export const HATCHES: Record<string, string> = {
  "45": "косая 45°",
  "135": "косая 135°",
  "0": "горизонтальная",
  "90": "вертикальная",
  x45: "крест 45°",
  x0: "клетка",
  dots: "точки",
};
export const DASHES: Record<string, string> = {
  solid: "сплошная",
  "6,4": "пунктир",
  "1.5,3": "точки",
  "8,3,1.5,3": "штрих-пунктир",
  "10,4": "длинный пунктир",
};
export const MARKS: Record<string, string> = {
  tick: "засечки",
  tri: "треугольники",
  dot: "кружки",
  cross: "крестики",
};
export const OPS = ["=", "≠", ">", "<", "≥", "≤", "содержит"] as const;
export const PARTS: Record<SymbolPart["k"], string> = {
  line: "Линия по контуру",
  band: "Полоса внутрь вдоль границы",
  hatch: "Штриховка",
  marks: "Значки вдоль линии",
};
export const PART_DEF: Record<SymbolPart["k"], Omit<SymbolPart, "k">> = {
  line: { c: "#1d1d1f", w: 1.2, a: 1 },
  band: { c: "#e07010", b: 8, a: 0.35 },
  hatch: { c: "#4a3aa7", hp: "45", hs: 8, w: 1 },
  marks: { c: "#1f6e31", shape: "tick", step: 16, size: 5, side: 1, w: 1.2 },
};

/** Цвета штриховки ЗОУИТ по Эталону ЛГР (общие для ГИС ОГД и ЕГРН). */
export const ZOUIT_HATCH: Record<string, string> = {
  "Водоохранная зона": "#0669b2",
  "Прибрежная защитная полоса": "#3a86d4",
  "Береговая полоса": "#0018b8",
  "Зона затопления": "#5b8fd9",
  "Зона сильного подтопления": "#8f63a8",
  "Зона умеренного подтопления": "#6fa4e0",
  "Зона слабого подтопления": "#5fb89c",
  "Санитарно-защитная зона (ПЗЗ)": "#62a51b",
  "Зона охраняемого объекта": "#694720",
  "Зона военного объекта": "#e3007b",
  "Охранная зона радиотехнического объекта": "#eb880e",
  "Охранная зона ООПТ": "#b8a800",
  "Охранная зона объектов электроэнергетики": "#eb880e",
  "Охранная зона линий и сооружений связи": "#b8a800",
  "Охранная зона пунктов наблюдений": "#694720",
  "Охранная зона геодезических пунктов": "#694720",
  "Особо охраняемая зелёная территория": "#009f3c",
};

/** Опорный порядок слоёв в проекте (сверху вниз). */
export const PREFERRED_ORDER = [
  "gisogd.red_lines", "gisogd.demolition", "egko.addresses", "egko.fences", "relief.contours",
  "egko.buildings", "nspd.buildings", "yandex.buildings", "osm.buildings",
  "yandex.transport", "yandex.parking", "osm.social", "yandex.roads", "osm.roads", "egko.paths",
  "gisogd.okn", "nspd.zouit", "gisogd.zouit", "gisogd.airfield", "gisogd.szz", "gisogd.vodookhr",
  "gisogd.ppt", "gisogd.pmt", "gisogd.agr", "gisogd.gpzu", "gisogd.krt",
  "nspd.parcels", "yandex.hd_roads", "egko.roads", "egko.water_labels", "egko.place_labels",
  "egko.water", "osm.water", "yandex.water", "egko.green", "yandex.green",
  "gisogd.admin", "gisogd.pzz_zones", "gisogd.pzz_sub", "gisogd.func_zones", "gisogd.func_zones_tinao",
  "osm.landuse", "yandex.landuse",
];

export interface SymbolPreset {
  id: string;
  title: string;
  geom: "poly" | "line" | "point" | "any";
  style: LayerStyle;
}

/** Библиотека градостроительных знаков (план 09.11.2026, шаг И3). */
export const SYMBOL_LIBRARY: SymbolPreset[] = [
  {
    id: "zouit_band", title: "ЗОУИТ (полоса внутрь)", geom: "poly",
    style: { mode: "single", fill: "#eb880e", opacity: 0, stroke: "#c45b00", strokeOwn: true, width: 1.4,
      parts: [{ k: "band", c: "#eb880e", b: 10, a: 0.35 }] },
  },
  {
    id: "szz_hatch", title: "СЗЗ (штриховка 45°)", geom: "poly",
    style: { mode: "single", fill: "#4a3aa7", opacity: 0, stroke: "#4a3aa7", strokeOwn: true, width: 1.2, hatch: true, hatchPat: "45", hatchStep: 8 },
  },
  {
    id: "water_zone", title: "Водоохранная зона", geom: "poly",
    style: { mode: "single", fill: "#0669b2", opacity: 0.08, stroke: "#0669b2", strokeOwn: true, width: 1.4,
      parts: [{ k: "marks", c: "#0669b2", shape: "tick", step: 16, size: 5, side: 1, w: 1.1 }] },
  },
  {
    id: "lgr_18_green", title: "Природный комплекс (ЛГР 18)", geom: "poly",
    style: { mode: "single", fill: "#009f3c", opacity: 0.14, stroke: "#009f3c", width: 1.3, lgrLine: 18 },
  },
  {
    id: "lgr_1_red", title: "Красная линия (ЛГР 1)", geom: "line",
    style: { mode: "single", fill: "#d7191c", stroke: "#d7191c", width: 1.5, lgrLine: 1 },
  },
  {
    id: "territory_dash", title: "Граница территории", geom: "poly",
    style: { mode: "single", fill: "#2446d8", opacity: 0.05, stroke: "#2446d8", strokeOwn: true, width: 2.5, dash: [8, 5] },
  },
  {
    id: "parcel_contour", title: "Участки ЕГРН (контур)", geom: "poly",
    style: { mode: "single", fill: "#ffffff", opacity: 0, stroke: "#7d8288", strokeOwn: true, width: 0.9 },
  },
  {
    id: "buildings_egko", title: "Здания (опорный план)", geom: "poly",
    style: { mode: "single", fill: "#d6d1c7", opacity: 1, stroke: "#6f6a62", strokeOwn: true, width: 0.7 },
  },
  {
    id: "pzz_contour", title: "Зоны ПЗЗ (контур)", geom: "poly",
    style: { mode: "single", fill: "#ffffff", opacity: 0, stroke: "#6a3d9a", strokeOwn: true, width: 1.5 },
  },
];

export const LGR_LINES: { code: number; title: string }[] = [];

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
          const seen = new Set<number>();
          LGR_LINES.length = 0;
          for (const s of Object.values(lgrRes.styles) as { lgr_code?: number; title?: string; name?: string; stroke?: string; dash_mm?: number[] }[]) {
            if (s.lgr_code != null) {
              const code = +s.lgr_code;
              if (s.stroke) LGRC[code] = s.stroke;
              if (s.dash_mm) LGRD[code] = s.dash_mm.map(v => v * 2);
              if (!seen.has(code)) {
                seen.add(code);
                LGR_LINES.push({ code, title: s.title || s.name || `Линия ${code}` });
              }
            }
          }
          LGR_LINES.sort((a, b) => a.code - b.code);
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

/** Поля атрибутов слоя (без служебных полей `_...`). */
export function fieldsOf(fc: { features?: { properties?: Record<string, unknown> }[] } | null | undefined): string[] {
  const seen = new Set<string>();
  for (const f of (fc?.features || []).slice(0, 500)) {
    for (const k of Object.keys(f.properties || {})) if (!k.startsWith("_")) seen.add(k);
  }
  return [...seen];
}

/** Числовые поля слоя (для диапазонов). */
export function numFields(fc: { features?: { properties?: Record<string, unknown> }[] } | null | undefined): string[] {
  const fs = (fc?.features || []).slice(0, 300);
  return fieldsOf(fc).filter(k => {
    let ok = 0, seen = 0;
    for (const f of fs) {
      const v = f.properties?.[k];
      if (v == null || v === "") continue;
      seen++;
      if (isNum(v)) ok++;
    }
    return seen > 0 && ok / seen >= 0.7;
  });
}

/** Значения категорий поля с числом объектов, по убыванию частоты. */
export function catValues(fc: { features?: { properties?: Record<string, unknown> }[] } | null | undefined, field: string | undefined): [string, number][] {
  if (!field) return [];
  const cnt = new Map<string, number>();
  for (const f of fc?.features || []) {
    const v = String(f.properties?.[field] ?? "");
    cnt.set(v, (cnt.get(v) || 0) + 1);
  }
  return [...cnt.entries()].sort((a, b) => b[1] - a[1]);
}

/** Заполнить цвета категорий стиля по значениям выбранного поля (keep — сохранить уже заданные цвета). */
export function assignCats(st: LayerStyle, fc: { features?: { properties?: Record<string, unknown> }[] } | null | undefined, keep = false): LayerStyle {
  const fs = fieldsOf(fc);
  st.cat ||= { field: "", colors: {}, off: [], sym: {} };
  if (!st.cat.field || (fs.length && !fs.includes(st.cat.field))) st.cat.field = fs[0] || st.cat.field || "";
  const prev = keep ? { ...(st.cat.colors || {}) } : {};
  const colors: Record<string, string> = { ...prev };
  const vals = catValues(fc, st.cat.field);
  vals.forEach(([v], i) => {
    if (!colors[v]) colors[v] = ZOUIT_HATCH[v] || CAT[i % CAT.length];
  });
  st.cat.colors = colors;
  st.cat.off ||= [];
  st.cat.sym ||= {};
  return st;
}

/** Сколько объектов слоя подходит под правило. */
export function ruleCount(r: RuleSpec, fc: { features?: { properties?: Record<string, unknown> }[] } | null | undefined): number {
  if (!r.field) return 0;
  let n = 0;
  for (const f of fc?.features || []) if (testRule(r, k => f.properties?.[k])) n++;
  return n;
}

/** Дополнить неполный стиль значениями по умолчанию. */
export function fullStyle(raw: Partial<LayerStyle> | undefined | null): LayerStyle {
  const s = (raw || {}) as LayerStyle;
  return {
    mode: s.mode || "single",
    fill: s.fill || "#9aa1a8",
    stroke: s.stroke || "#3d3d3d",
    strokeOwn: !!s.strokeOwn,
    width: s.width ?? 1.2,
    opacity: s.opacity ?? 0.35,
    hatch: !!s.hatch,
    hatchPat: s.hatchPat || "45",
    hatchStep: s.hatchStep || 8,
    ...(s.hatchColor ? { hatchColor: s.hatchColor } : {}),
    ...(s.dash?.length ? { dash: [...s.dash] } : {}),
    ...(s.lgrLine ? { lgrLine: s.lgrLine } : {}),
    ...(s.parts?.length ? { parts: s.parts.map(p => ({ ...p })) } : {}),
    ...(s.marker !== undefined ? { marker: s.marker } : {}),
    label: s.label || "",
    labelSize: s.labelSize || 11,
    labelColor: s.labelColor || "#1d1d1f",
    cat: { field: s.cat?.field || "", colors: { ...(s.cat?.colors || {}) }, off: [...(s.cat?.off || [])], sym: { ...(s.cat?.sym || {}) } },
    grad: { field: s.grad?.field || "", n: s.grad?.n || 5, ramp: s.grad?.ramp || "blue", method: s.grad?.method || "quantile" },
    rules: { list: (s.rules?.list || []).map(r => ({ ...r })), elseFill: s.rules?.elseFill || "#dddddd", elseHide: !!s.rules?.elseHide },
  };
}

/** Определить тип геометрии слоя по его FeatureCollection. */
export function geomOfFc(fc: { features?: { geometry?: { type?: string } | null }[] } | null | undefined): "point" | "line" | "poly" {
  const t = fc?.features?.find(f => f.geometry)?.geometry?.type || "";
  return /Point/.test(t) ? "point" : /Line/.test(t) ? "line" : "poly";
}

const OWN_STYLES: Record<string, Partial<LayerStyle>> = {
  "nspd.parcels": { fill: "#ffffff", stroke: "#7d8288", strokeOwn: true, width: 0.8, opacity: 0 },
  "nspd.buildings": { fill: "#cbc6be", stroke: "#4d4d4d", strokeOwn: true, width: 0.8, opacity: 1 },
  "nspd.zouit": { mode: "cat", hatch: true, width: 1.2, cat: { field: "Вид зоны", off: [], colors: { ...ZOUIT_HATCH } } },
  "gisogd.zouit": { mode: "cat", hatch: true, width: 1.2, cat: { field: "Вид зоны", off: [], colors: { ...ZOUIT_HATCH } } },
  "gisogd.szz": { fill: "#4a3aa7", stroke: "#4a3aa7", hatch: true, width: 1.2 },
  "gisogd.vodookhr": { fill: "#2a78d6", stroke: "#2a78d6", hatch: true, width: 1.2 },
  "gisogd.red_lines": { mode: "lgr", fill: "#d7191c", width: 1.3 },
  "gisogd.airfield": { mode: "cat", opacity: 0, width: 1, cat: { field: "Вид зоны", colors: {}, off: [] } },
  "gisogd.okn": { mode: "cat", hatch: true, width: 1.2, cat: { field: "Вид зоны", colors: {}, off: [] } },
  "gisogd.demolition": { fill: "#b3261e", stroke: "#b3261e", hatch: true, width: 1.4 },
  "gisogd.pzz_zones": { fill: "#ffffff", opacity: 0, stroke: "#6a3d9a", strokeOwn: true, width: 1.4 },
  "gisogd.pzz_sub": { mode: "grad", opacity: 0.45, stroke: "#8a5a00", width: 0.6, grad: { field: "Плотность, тыс. м²/га", n: 5, ramp: "brick", method: "quantile" } },
  "gisogd.func_zones": { mode: "cat", opacity: 0.75, stroke: "#3c3c3c", width: 0.5, cat: { field: "naimfunkzony", colors: {}, off: [] } },
  "gisogd.func_zones_tinao": { mode: "cat", opacity: 0.75, stroke: "#3c3c3c", width: 0.5, cat: { field: "Вид зоны", colors: {}, off: [] } },
  "gisogd.ppt": { mode: "cat", hatch: true, width: 1.2, hatchPat: "135", cat: { field: "Вид зоны", colors: {}, off: [] } },
  "gisogd.pmt": { fill: "#2f9e44", stroke: "#2f9e44", width: 1.6, opacity: 0 },
  "gisogd.gpzu": { fill: "#35c2d6", stroke: "#1b8a99", width: 0.8, opacity: 0.35 },
  "gisogd.agr": { fill: "#d6336c", stroke: "#b3261e", hatch: true, hatchPat: "45", width: 1 },
  "gisogd.krt": { fill: "#e0892f", stroke: "#b35d00", hatch: true, hatchPat: "45", width: 1.2 },
  "gisogd.admin": { mode: "cat", opacity: 0, fill: "#ffffff", stroke: "#3c3c3c", width: 1, label: "Наименование", labelSize: 11, cat: { field: "Уровень", colors: { "округ": "#3c3c3c", "район": "#8a8a8a" }, off: [] } },
  "egko.buildings": { fill: "#d6d1c7", stroke: "#6f6a62", strokeOwn: true, width: 0.7, opacity: 1 },
  "egko.water": { fill: "#b9d6ec", stroke: "#6fa6e6", width: 0.8, opacity: 1 },
  "egko.green": { fill: "#cfe3b4", stroke: "#8fb573", width: 0.4, opacity: 0.7 },
  "egko.roads": { fill: "#e4e1da", stroke: "#b7b2a8", width: 0.5, opacity: 0.9 },
  "egko.water_labels": { fill: "#1f8fe0", width: 1, label: "Подпись", labelSize: 11, marker: false, labelColor: "#1f8fe0" },
  "egko.place_labels": { fill: "#141414", width: 1, label: "Подпись", labelSize: 11, marker: false, labelColor: "#141414" },
  "osm.buildings": { fill: "#dcd7ce", stroke: "#8a857c", width: 0.7, opacity: 1 },
  "osm.roads": { mode: "cat", width: 1.6, cat: { field: "Тип дороги", colors: {}, off: [] } },
  "osm.water": { fill: "#b9d6ec", stroke: "#6fa6e6", width: 0.8, opacity: 1 },
  "osm.landuse": { mode: "cat", opacity: 0.35, stroke: "#b8b2a3", width: 0.5, cat: { field: "Землепользование", colors: {}, off: [] } },
  "yandex.buildings": { fill: "#d8d3c9", stroke: "#8f897f", width: 0.6, opacity: 1 },
  "yandex.hd_roads": { fill: "#d5dae0", stroke: "#9ea7b1", width: 0.6, opacity: 1 },
  "yandex.roads": { fill: "#8f887c", width: 0.9 },
  "yandex.green": { fill: "#cfe4b3", stroke: "#9cbf80", width: 0, opacity: 0.7 },
  "yandex.water": { fill: "#bcd8ee", stroke: "#78aee6", width: 0, opacity: 1 },
};

/** Автостиль слоя при загрузке из каталога (Эталон ЛГР, ЗОУИТ, стиль портала или палитра). */
export function defaultStyleFor(
  key: string,
  fc: { features?: { properties?: Record<string, unknown> }[] } | null | undefined,
  layerIndex = 0,
  portalStyle?: Partial<LayerStyle> | null,
): LayerStyle {
  const hasLt = (fc?.features || []).some(f => f.properties?._lt || f.properties?._miss);
  let base: Partial<LayerStyle>;
  if (portalStyle && Object.keys(portalStyle).length) {
    base = { ...portalStyle, ...(hasLt && geomOfFc(fc as never) === "line" ? { mode: "lgr" as const } : {}) };
  } else if (OWN_STYLES[key]) {
    base = JSON.parse(JSON.stringify(OWN_STYLES[key]));
  } else if (hasLt) {
    base = { mode: "lgr", fill: "#d7191c", width: 1.3 };
  } else {
    base = { fill: CAT[layerIndex % CAT.length], stroke: "#3d3d3d", opacity: 0.35, width: 1.2 };
  }
  const st = fullStyle(base);
  if (st.mode === "cat") assignCats(st, fc, true);
  return st;
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
