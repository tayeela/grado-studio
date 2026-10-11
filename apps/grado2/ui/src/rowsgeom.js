/* ГРАДО 2 · геометрия рядов «по границе» для генератора посадки (sketchgen.js edgeRows): контур участка → хорды
   (спрямление с допуском), расстояние между корпусами-четырёхугольниками. Чистые функции в метрах местной рамки, без
   библиотек — проверяются node --test src/rowsgeom.test.js (tests/test_rowsgeom_js.py). */

/* контур → хорды: начало — в самом остром изломе, хорда тянется, пока все точки между её концами не дальше tol м от неё */
export function chords(ring, tol) {
  const N = ring.length; if (N < 3) return [];
  const turn = i => { const a = ring[(i + N - 1) % N], o = ring[i], b = ring[(i + 1) % N];
    const t = Math.atan2(b[1] - o[1], b[0] - o[0]) - Math.atan2(o[1] - a[1], o[0] - a[0]); return Math.abs(Math.atan2(Math.sin(t), Math.cos(t))); };
  let s0 = 0; for (let i = 1; i < N; i++) if (turn(i) > turn(s0)) s0 = i;
  const P = Array.from({ length: N + 1 }, (_, i) => ring[(s0 + i) % N]), out = [];
  const off = (a, b, q) => { const L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1; return Math.abs((b[0] - a[0]) * (a[1] - q[1]) - (a[0] - q[0]) * (b[1] - a[1])) / L; };
  let i = 0;
  while (i < N) {
    let j = i + 1;
    while (j + 1 <= N && P.slice(i + 1, j + 1).every(q => off(P[i], P[j + 1], q) <= tol)) j++;
    out.push([P[i], P[j]]); i = j;
  }
  return out;
}
/* расстояние между выпуклыми четырёхугольниками в метрах (0 — пересекаются) */
export function gapXY(a, b) {
  const axes = q => q.map((p, i) => { const r = q[(i + 1) % q.length]; return [-(r[1] - p[1]), r[0] - p[0]]; });
  const sep = [...axes(a), ...axes(b)].some(([x, y]) => { const pa = a.map(p => p[0] * x + p[1] * y), pb = b.map(p => p[0] * x + p[1] * y);
    return Math.max(...pa) < Math.min(...pb) || Math.max(...pb) < Math.min(...pa); });
  if (!sep) return 0;
  const seg = (q, a, b) => { const dx = b[0] - a[0], dy = b[1] - a[1], t = Math.max(0, Math.min(1, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
    return Math.hypot(q[0] - a[0] - t * dx, q[1] - a[1] - t * dy); };
  let m = Infinity;
  for (const [P, Q] of [[a, b], [b, a]]) for (const q of P) Q.forEach((r, i) => { m = Math.min(m, seg(q, r, Q[(i + 1) % Q.length])); });
  return m;
}
