/* Картографическая чистка полигонов дорог листа альбома (albums.js, roadSource). Владелец 06.10.2026 (T84): «сделай на всех
   векторных схемах дороги ЕГКО, чтобы остались только полигональные, сделай красиво по лучшим правилам оформления
   градостроительных схем». Куски проезжей части (особенно ЕГКО) лежат внахлёст и с волосяными щелями — на листе видны швы.
   Порядок: рамка с запасом 5 % → слияние в одну фигуру (сначала по плиткам: работа ограничена) → закрытие щелей (буфер +0.4 м, затем −0.4 м) →
   без обрывков < 10 м² и дыр-«островов» < 25 м² → упрощение ~0.3 м. Решение (фильтры, плитки) — чистые функции без turf;
   turf передаётся параметром и касается только слияния и буфера. Проверки — tests/roadclean_test.js. */
(function (root) {
  const OPT = { margin: .05, close: .4, minPart: 10, minHole: 25, simplify: .3, tiles: 4, maxLoss: .5 };
  const planar = (ring, f) => { let s = 0; for (let i = 0, n = ring.length - 1; i < n; i++) s += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]; return Math.abs(s) / 2 * f; };
  // площадь кольца (м²) по градусам: плоское приближение с широтой кольца; для тестов и как запасной вариант
  function ringArea(ring) {
    const lat = ring.reduce((s, p) => s + p[1], 0) / (ring.length || 1);
    return planar(ring, 111320 * 111320 * Math.cos(lat * Math.PI / 180)); }
  // убрать обрывки и дыры: Polygon/MultiPolygon → геометрия без них (null, если ничего не осталось)
  function filterParts(g, minPart = OPT.minPart, minHole = OPT.minHole, area = ringArea) {
    const polys = g?.type === "Polygon" ? [g.coordinates] : g?.type === "MultiPolygon" ? g.coordinates : [];
    const out = [];
    polys.forEach(p => { if (!p.length || p[0].length < 4 || area(p[0]) < minPart) return;
      out.push([p[0], ...p.slice(1).filter(r => r.length >= 4 && area(r) >= minHole)]); });
    return !out.length ? null : out.length === 1 ? { type: "Polygon", coordinates: out[0] } : { type: "MultiPolygon", coordinates: out }; }
  // плитки n×n по рамке: индексы кусков по центру их bbox (рамка bb = [w, s, e, n]); пустые плитки не возвращаются
  function tiles(boxes, bb, n = OPT.tiles) {
    const m = new Map(), dx = (bb[2] - bb[0]) / n || 1, dy = (bb[3] - bb[1]) / n || 1;
    boxes.forEach((b, i) => { const cx = Math.min(n - 1, Math.max(0, Math.floor(((b[0] + b[2]) / 2 - bb[0]) / dx))),
      cy = Math.min(n - 1, Math.max(0, Math.floor(((b[1] + b[3]) / 2 - bb[1]) / dy))), k = cy * n + cx; (m.get(k) || m.set(k, []).get(k)).push(i); });
    return [...m.values()]; }
  const polysOf = g => g?.type === "Polygon" ? [g.coordinates] : g?.type === "MultiPolygon" ? g.coordinates : [];
  const bboxOf = g => { let w = 1e9, s = 1e9, e = -1e9, n = -1e9; polysOf(g).forEach(p => p[0].forEach(([x, y]) => { if (x < w) w = x; if (x > e) e = x; if (y < s) s = y; if (y > n) n = y; })); return [w, s, e, n]; };
  const feat = g => ({ type: "Feature", geometry: g, properties: {} });
  // geoms — геометрии дорог; возвращает одну очищенную геометрию или null. При сбое turf — исходные куски без чистки
  function clean(turf, geoms, bb, o = {}) {
    const op = { ...OPT, ...o }, dx = (bb[2] - bb[0]) * op.margin, dy = (bb[3] - bb[1]) * op.margin, fr = [bb[0] - dx, bb[1] - dy, bb[2] + dx, bb[3] + dy];
    const items = geoms.filter(g => polysOf(g).length).map(g => ({ g, b: bboxOf(g) }))
      .filter(x => !(x.b[2] < fr[0] || x.b[0] > fr[2] || x.b[3] < fr[1] || x.b[1] > fr[3]));
    if (!items.length) return null;
    // слияние: целиком; при сбое polygon-clipping (почти совпадающие рёбра) — попарно, а пара, которая не слилась, просто
    // складывается в одну мультигеометрию (куски не теряются; шов закроет буфер)
    const union = fs => { if (fs.length === 1) return fs[0];
      try { return turf.union(turf.featureCollection(fs)); } catch { /* ниже — попарно */ }
      return fs.reduce((a, b) => { try { return turf.union(turf.featureCollection([a, b])); } catch { return feat({ type: "MultiPolygon", coordinates: [...polysOf(a.geometry), ...polysOf(b.geometry)] }); } }); };
    const snap = f => turf.truncate(f, { precision: 7, coordinates: 2, mutate: false });   // ~1 см: убирает «почти совпадающие» рёбра
    try {
      const clipped = items.map(x => { const inside = x.b[0] >= fr[0] && x.b[1] >= fr[1] && x.b[2] <= fr[2] && x.b[3] <= fr[3];
        if (inside) return x.g; const c = turf.bboxClip(feat(x.g), fr); return c?.geometry?.coordinates?.length ? c.geometry : null; }).filter(Boolean);
      const parts = tiles(clipped.map(bboxOf), fr, op.tiles).map(ix => {
        return union(ix.map(i => snap(feat(clipped[i])))); });
      let all = union(parts);
      // нормализация: у ЕГКО бывает дыра, лежащая на краю внешнего кольца (обрезка рамкой запроса) — для JSTS это невалидный
      // полигон, буфер +0.4 м «съедал» 7988 м² до 326 м², а −0.4 м — до 0.035 м² (лист 4 КРТ 3229, T86g). Объединение фигуры с самой
      // собой (polygon-clipping) раскладывает такую дыру на края; страховка — закрытие не должно терять > 50 % площади
      if (op.close > 0) { const area0 = turf.area(all), norm = f => { try { const u = turf.union(turf.featureCollection([f, f])); return u?.geometry ? u : f; } catch { return f; } },
          src = norm(all), b = turf.buffer(src, op.close, { units: "meters" }), e = b?.geometry && turf.buffer(b, -op.close, { units: "meters" });
        if (e?.geometry && turf.area(e) >= area0 * (1 - op.maxLoss)) all = e; else if (o.debug) console.warn("roadclean: закрытие щелей потеряло площадь, взята фигура без буфера"); }
      let g = filterParts(all.geometry, op.minPart, op.minHole);
      if (g && op.simplify > 0) { const s = turf.simplify(feat(g), { tolerance: op.simplify / 111320, highQuality: false, mutate: false }); g = filterParts(s.geometry, op.minPart, op.minHole) || g; }
      if (!g) return null;
      if (g && turf.area(feat(g)) < turf.area(all) * (1 - op.maxLoss)) g = all.geometry;   // страховка: чистка не должна терять > 50 % площади
      const c = turf.bboxClip(feat(g), fr); return c?.geometry?.coordinates?.length ? c.geometry : null;
    } catch (e) { if (o.debug) console.warn(e); return { type: "MultiPolygon", coordinates: items.flatMap(x => polysOf(x.g)) }; }
  }
  // Дороги Яндекса там, где у ЕГКО их нет (F4, 06.10.2026: на листах 7–8 пропала дорога южнее НИКИЭТ — у ЕГКО её полигона нет,
  // а площади хватало на правило «ЕГКО первым»). Яндекс минус ЕГКО с запасом near (край у двух источников не совпадает на
  // 2–4 м) → без полос уже open (обводка у края ЕГКО) и без кусков меньше minGap м² → каждый кусок возвращается назад на near
  // внутри Яндекса, чтобы с ЕГКО не было шва. Возвращает геометрии для clean() вместе с ЕГКО; пусто — ЕГКО полная
  const GAP = { near: 4, open: 2, minGap: 150 };
  function gapFill(turf, egko, yandex, bb, o = {}) {
    const op = { ...GAP, ...o }, E = clean(turf, egko, bb, o), Y = clean(turf, yandex, bb, o);
    if (!Y) return [];
    if (!E) return [Y];
    try {
      const d = turf.difference(turf.featureCollection([feat(Y), turf.buffer(feat(E), op.near, { units: "meters" })]));
      if (!d?.geometry) return [];
      const opened = turf.buffer(turf.buffer(d, -op.open, { units: "meters" }), op.open, { units: "meters" });
      const parts = polysOf(opened?.geometry).map(p => ({ type: "Polygon", coordinates: p })).filter(g => ringArea(g.coordinates[0]) >= op.minGap);
      return parts.map(g => { const back = turf.intersect(turf.featureCollection([turf.buffer(feat(g), op.near + .5, { units: "meters" }), feat(Y)])); return back?.geometry || g; });
    } catch (e) { if (o.debug) console.warn(e); return []; }
  }
  const api = { OPT, GAP, ringArea, filterParts, tiles, clean, gapFill };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.RoadClean = api;
})(typeof window !== "undefined" ? window : globalThis);
