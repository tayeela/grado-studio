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
  const api = { memoByGeometry, cornerPoints };
  if (typeof module === "object" && module.exports) module.exports = api; else root.AlbumGeo = api;
})(typeof window !== "undefined" ? window : globalThis);
