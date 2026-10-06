/* Привязка и умные направляющие для редактора макета листа (layout.js), как в InDesign. Перенос прохода выравнивания
   из DesignCraft (crates/tools/src/snap.rs: pass_align, offer_box, offer, push_alignment_guide; MIT, лицензия —
   vendor/LICENSE-designcraft). Владелец 06.10.2026: «используй код этой программы для нашего редактора листов — вёрстка».
   Надпись при перетаскивании встаёт краем к краю или серединой к середине другой надписи или листа, если до них не
   дальше зоны привязки (4 пикселя экрана); по каждой оси — ближайшее совпадение, и рисуется одна направляющая.
   Чистые функции, рамки в мм листа {x0, y0, x1, y1}; проверки — tests/snap_test.js. */
(function (root) {
  const ZONE_PX = 4, GUIDE_OVER = 6;                      // зона привязки (px) и выпуск направляющей за рамки (мм), как в DesignCraft
  const fin = r => r && [r.x0, r.y0, r.x1, r.y1].every(Number.isFinite);
  // низ, середина, верх рамки по оси (x: левый край, середина, правый; y: верх, середина, низ)
  const triple = (r, ax) => ax === "x" ? [r.x0, (r.x0 + r.x1) / 2, r.x1] : [r.y0, (r.y0 + r.y1) / 2, r.y1];
  function offer(best, moving, target, tol, span) {
    const delta = target - moving, dist = Math.abs(delta);
    if (dist <= tol && (!best.hit || dist < best.hit.dist)) best.hit = { dist, delta, at: target, span };
  }
  // края — к краям цели (оба), середина — к середине
  function offerBox(best, moving, target, ax, tol) {
    const [m0, mm, m1] = triple(moving, ax), [t0, tm, t1] = triple(target, ax);
    offer(best, m0, t0, tol, target); offer(best, m0, t1, tol, target);
    offer(best, m1, t0, tol, target); offer(best, m1, t1, tol, target);
    offer(best, mm, tm, tol, target);
  }
  // направляющая на линии совпадения: от общей крайней точки обеих рамок с выпуском GUIDE_OVER
  function guide(ax, hit, moving) {
    const t = hit.span;
    if (ax === "x") return { a: [hit.at, Math.min(moving.y0, moving.y1, t.y0, t.y1) - GUIDE_OVER], b: [hit.at, Math.max(moving.y0, moving.y1, t.y0, t.y1) + GUIDE_OVER] };
    return { a: [Math.min(moving.x0, moving.x1, t.x0, t.x1) - GUIDE_OVER, hit.at], b: [Math.max(moving.x0, moving.x1, t.x0, t.x1) + GUIDE_OVER, hit.at] };
  }
  /* rect — рамка надписи на новом месте; targets — рамки, к которым можно встать (другие надписи, лист);
     tol — зона привязки в мм (ZONE_PX / пикселей в мм). → { dx, dy, guides: [{ a: [x, y], b: [x, y] }] } */
  function snap(rect, targets, tol) {
    const out = { dx: 0, dy: 0, guides: [] };
    if (!fin(rect) || !(tol > 0) || !Number.isFinite(tol)) return out;
    const hits = {};
    for (const ax of ["x", "y"]) {
      const best = {};
      for (const t of targets || []) if (fin(t)) offerBox(best, rect, t, ax, tol);
      hits[ax] = best.hit;
    }
    if (hits.x) out.dx = hits.x.delta;
    if (hits.y) out.dy = hits.y.delta;
    const placed = { x0: rect.x0 + out.dx, y0: rect.y0 + out.dy, x1: rect.x1 + out.dx, y1: rect.y1 + out.dy };
    for (const ax of ["x", "y"]) if (hits[ax]) out.guides.push(guide(ax, hits[ax], placed));
    return out;
  }
  const api = { ZONE_PX, snap };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.Snap = api;
})(typeof window !== "undefined" ? window : globalThis);
