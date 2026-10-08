/* ГРАДО 2 · геометрия нового интерфейса — те же приёмы, что web/app.js: местная рамка в метрах вокруг границы
   (x — восток, y — север; для инсоляции и сеток), контуры полигона, буфер, пересечение, вычитание и объединение на Turf
   с повтором при сбое (округление до ~1 см, затем «раздутое» на 1 см вычитаемое), площадь в МСК. */
import * as turf from "@turf/turf";
import { sizeOf } from "./features.js";

let LON0 = 37.6, LAT0 = 55.75, KX = 111320 * Math.cos(LAT0 * Math.PI / 180);
const KY = 110540;
export function setFrame([lon, lat]) { LON0 = lon; LAT0 = lat; KX = 111320 * Math.cos(lat * Math.PI / 180); }
export const toLL = ([x, y]) => [LON0 + x / KX, LAT0 + y / KY];
export const toXY = ([lo, la]) => [(lo - LON0) * KX, (la - LAT0) * KY];
export const bboxOf = r => { const xs = r.map(p => p[0]), ys = r.map(p => p[1]); return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]; };
export const polys = f => { const g = f?.geometry; return !g ? [] : g.type === "Polygon" ? [g.coordinates] : g.type === "MultiPolygon" ? g.coordinates : []; };
export const ringsXY = f => polys(f).map(p => p[0].map(toXY));
export const m2 = f => { if (!f) return 0; const [k, v] = sizeOf({ geometry: f.geometry || f }); return k === "area" ? v : 0; };   // м² в МСК
export const safe = fn => { try { return fn(); } catch (e) { console.warn(e); return null; } };
const quiet = fn => { try { return { ok: true, v: fn() }; } catch { return { ok: false }; } };
const snap6 = f => turf.truncate(f, { precision: 7, coordinates: 2 });
export function robust(op, a, b) {
  const tries = [() => op(a, b), () => op(snap6(a), snap6(b)), () => op(snap6(a), snap6(turf.buffer(b, 0.01, { units: "meters" }) || b))];
  const sane = g => { const ps = g?.geometry?.type === "Polygon" ? [g.geometry.coordinates] : g?.geometry?.type === "MultiPolygon" ? g.geometry.coordinates : null;
    return g == null || (ps != null && ps.every(p => p.every(r => r.length >= 4))); };
  for (const t of tries) { const r = quiet(t); if (r.ok && sane(r.v)) return r.v; }
  console.warn("геометрия: операция не удалась и после повторов"); return null;
}
export function unionAll(fs) {
  fs = fs.filter(f => f && polys(f).length); if (!fs.length) return null; if (fs.length === 1) return fs[0];
  const all = quiet(() => turf.union(turf.featureCollection(fs))); if (all.ok) return all.v;
  const snapped = quiet(() => turf.union(turf.featureCollection(fs.map(snap6)))); if (snapped.ok) return snapped.v;
  return fs.reduce((a, b) => robust((x, y) => turf.union(turf.featureCollection([x, y])), a, b) || a);
}
export const diff = (a, b) => !a ? null : !b ? a : robust((x, y) => turf.difference(turf.featureCollection([x, y])), a, b);
export const inter = (a, b) => (a && b) ? robust((x, y) => turf.intersect(turf.featureCollection([x, y])), a, b) : null;
export const buf = (a, d) => { if (!a) return null; if (!d) return a; const r = safe(() => turf.buffer(a, d, { units: "meters" })); return r?.geometry ? r : null; };
export const floorsOf = f => { const v = +(f.properties?.["Этажность"]); return v > 0 ? v : 1; };
export function plural(n, [one, few, many]) {
  const a = Math.abs(n) % 100, b = a % 10;
  return `${Number(n).toLocaleString("ru-RU")} ${a > 10 && a < 20 ? many : b === 1 ? one : b >= 2 && b <= 4 ? few : many}`;
}
