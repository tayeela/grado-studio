/* ГРАДО 2 · мелкая геометрия листов альбома без карты (T10/T11, 06.10.2026): кэш по объекту и углы рамки листа в МСК.
   Чистые функции; tests/test_albumgeo_js.py. */
(function (root) {
  // Кэш вычисления над объектом слоя: result = calc(f, ...args), пересчёт только когда меняется объект (по ссылке на его
  // геометрию), параметры или «ревизия» (rev — строка-признак внешнего состояния, у округа центр территории: от него зависит, какие части остаются)
  function memoByGeometry(calc) {
    const cache = new WeakMap();
    const fn = (f, rev, ...args) => {
      const g = f?.geometry; if (!g || typeof g !== "object") return calc(f, ...args);
      let m = cache.get(g); if (!m) cache.set(g, m = new Map());
      const k = rev + "|" + args.join(",");
      if (!m.has(k)) { fn.misses++; m.set(k, calc(f, ...args)); }
      return m.get(k);
    };
    fn.misses = 0;
    return fn;
  }
  // Точки на рамке листа на отступе frac от левого верхнего и правого нижнего углов — в МСК, затем в [lon, lat].
  // Рамка листа — прямоугольник в МСК (как рисуют и печатают), её центр и размер: center [lon, lat], rectMM [x, y, w, h] в мм
  // листа, scale — знаменатель масштаба. Рамка в градусах (extent прямоугольника в проекции карты) по углам смещена: МСК
  // повёрнута относительно меридианов, поэтому угол листа в градусах не равен углу рамки.
  function cornerPoints(center, rectMM, scale, msk, frac = .03) {
    const [cx, cy] = msk.fromWgs(center), w = rectMM[2] * scale / 1000, h = rectMM[3] * scale / 1000;
    const at = (sx, sy) => msk.toWgs([cx + sx * w * (.5 - frac), cy + sy * h * (.5 - frac)]);
    return { tl: at(-1, 1), br: at(1, -1) };
  }
  // Точка в глубине многоугольника (полюс недоступности, приближённо): сетка n × n по охвату, лучшая ячейка — центр
  // следующей, мельче, сетки. rings — внешнее кольцо и дыры в [lon, lat]; долгота сжата cos(широты), чтобы расстояния
  // были честными. Подписи зон (КРТ на листе ПЗЗ) — там, где больше всего места, а не у края (владелец 21.10.2026, #144)
  function poleOf(rings, n = 16, iters = 5) {
    const k = Math.cos((rings[0].reduce((a, p) => a + p[1], 0) / rings[0].length) * Math.PI / 180);
    const R = rings.map(r => r.map(([x, y]) => [x * k, y]));
    const inside = (x, y) => R.reduce((c, r) => { for (let i = 0, j = r.length - 1; i < r.length; j = i++)
      if ((r[i][1] > y) !== (r[j][1] > y) && x < (r[j][0] - r[i][0]) * (y - r[i][1]) / (r[j][1] - r[i][1]) + r[i][0]) c = !c; return c; }, false);
    const dist = (x, y) => { let m = Infinity; R.forEach(r => { for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
      const [ax, ay] = r[j], [bx, by] = r[i], dx = bx - ax, dy = by - ay, l = dx * dx + dy * dy;
      const t = l ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / l)) : 0;
      m = Math.min(m, Math.hypot(x - ax - t * dx, y - ay - t * dy)); } }); return m; };
    let x0 = Math.min(...R[0].map(p => p[0])), x1 = Math.max(...R[0].map(p => p[0])), y0 = Math.min(...R[0].map(p => p[1])), y1 = Math.max(...R[0].map(p => p[1]));
    let best = null;
    for (let it = 0; it < iters; it++) {
      const sx = (x1 - x0) / n, sy = (y1 - y0) / n;
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
        const x = x0 + (i + .5) * sx, y = y0 + (j + .5) * sy;
        if (!inside(x, y)) continue;
        const d = dist(x, y); if (!best || d > best[2]) best = [x, y, d];
      }
      if (!best) return null;
      [x0, x1, y0, y1] = [best[0] - sx, best[0] + sx, best[1] - sy, best[1] + sy];
    }
    return [best[0] / k, best[1]];
  }
  const api = { memoByGeometry, cornerPoints, poleOf };
  if (typeof module === "object" && module.exports) module.exports = api; else root.AlbumGeo = api;
})(typeof window !== "undefined" ? window : globalThis);
