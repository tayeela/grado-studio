// @ts-check
/* ГРАДО 2 · геометрия черчения в метрах МСК (X на восток, Y на север). Без DOM и OpenLayers — проверяется под node
   (tests/cadcore_test.js). Цепочка — массив точек [x, y]; у замкнутой первая точка повторена в конце.
   Здесь всё, что считают команды AutoCAD: пересечения, перпендикуляр, касательные, дуги по трём точкам,
   правильные многоугольники, подобие (offset), обрезка, удлинение, разрыв, сопряжение, соединение. */
(function (root) {
  const EPS = 1e-9;
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1]], add = (a, b) => [a[0] + b[0], a[1] + b[1]], mul = (a, k) => [a[0] * k, a[1] * k];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1], cross = (a, b) => a[0] * b[1] - a[1] * b[0];
  const len = a => Math.hypot(a[0], a[1]), dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const ang = (a, b) => Math.atan2(b[1] - a[1], b[0] - a[0]);
  const unit = a => { const l = len(a) || 1; return [a[0] / l, a[1] / l]; };
  const polar = (p, a, d) => [p[0] + d * Math.cos(a), p[1] + d * Math.sin(a)];
  const same = (a, b, tol = 1e-6) => Math.abs(a[0] - b[0]) <= tol && Math.abs(a[1] - b[1]) <= tol;
  const closed = pts => pts.length > 2 && same(pts[0], pts[pts.length - 1]);
  const norm2pi = a => ((a % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);

  // пересечение прямых/отрезков a-b и c-d: {p, t, u} (t, u — доли вдоль отрезков); inf — прямые без ограничения
  function inter(a, b, c, d, inf) {
    const r = sub(b, a), s = sub(d, c), den = cross(r, s);
    if (Math.abs(den) < EPS * Math.max(1, len(r) * len(s))) return null;
    const t = cross(sub(c, a), s) / den, u = cross(sub(c, a), r) / den;
    if (!inf && (t < -1e-9 || t > 1 + 1e-9 || u < -1e-9 || u > 1 + 1e-9)) return null;
    return { p: add(a, mul(r, t)), t, u };
  }
  // основание перпендикуляра из p на отрезок (clamp) или прямую a-b
  function foot(p, a, b, clamp) {
    const r = sub(b, a), l2 = dot(r, r); if (l2 < EPS) return a.slice();
    let t = dot(sub(p, a), r) / l2; if (clamp) t = Math.max(0, Math.min(1, t));
    return add(a, mul(r, t));
  }
  // пересечения отрезка (или прямой) с окружностью
  function segCircle(a, b, c, r, inf) {
    const d = sub(b, a), f = sub(a, c), A = dot(d, d), B = 2 * dot(f, d), C = dot(f, f) - r * r, disc = B * B - 4 * A * C;
    if (A < EPS || disc < 0) return [];
    const q = Math.sqrt(disc), out = [];
    for (const t of disc === 0 ? [-B / (2 * A)] : [(-B - q) / (2 * A), (-B + q) / (2 * A)]) if (inf || (t >= -1e-9 && t <= 1 + 1e-9)) out.push(add(a, mul(d, t)));
    return out;
  }
  function circleCircle(c1, r1, c2, r2) {
    const d = dist(c1, c2); if (d < EPS || d > r1 + r2 || d < Math.abs(r1 - r2)) return [];
    const a = (r1 * r1 - r2 * r2 + d * d) / (2 * d), h = Math.sqrt(Math.max(0, r1 * r1 - a * a)), m = add(c1, mul(sub(c2, c1), a / d));
    const o = mul([-(c2[1] - c1[1]) / d, (c2[0] - c1[0]) / d], h);
    return h < EPS ? [m] : [add(m, o), sub(m, o)];
  }
  // касательные из точки p к окружности: точки касания
  function tangents(p, c, r) {
    const d = dist(p, c); if (d <= r) return [];
    const a = ang(c, p), b = Math.acos(r / d);
    return [polar(c, a + b, r), polar(c, a - b, r)];
  }
  // окружность через три точки
  function circle3(p1, p2, p3) {
    const bx = p2[0] - p1[0], by = p2[1] - p1[1], cx = p3[0] - p1[0], cy = p3[1] - p1[1], d = 2 * (bx * cy - by * cx);
    if (Math.abs(d) < EPS) return null;
    const ux = (cy * (bx * bx + by * by) - by * (cx * cx + cy * cy)) / d, uy = (bx * (cx * cx + cy * cy) - cx * (bx * bx + by * by)) / d;
    const c = [p1[0] + ux, p1[1] + uy]; return { c, r: dist(c, p1) };
  }
  // дуга по трём точкам: центр, радиус, начальный угол, угловой размах со знаком (плюс — против часовой)
  function arc3(p1, p2, p3) {
    const k = circle3(p1, p2, p3); if (!k) return null;
    const a0 = ang(k.c, p1), a1 = ang(k.c, p2), a2 = ang(k.c, p3);
    const ccw = cross(sub(p2, p1), sub(p3, p2)) > 0;
    let sw = ccw ? norm2pi(a2 - a0) : -norm2pi(a0 - a2);
    return { c: k.c, r: k.r, a0, sw, mid: a1 };
  }
  const segsFor = (r, sw, tol = 0.01) => Math.min(720, Math.max(8, Math.ceil(Math.abs(sw) / (2 * Math.acos(Math.max(-1, 1 - tol / Math.max(r, tol)))))));
  function arcPts(a, tol) { const n = segsFor(a.r, a.sw, tol), out = []; for (let i = 0; i <= n; i++) out.push(polar(a.c, a.a0 + a.sw * i / n, a.r)); return out; }
  function circlePts(c, r, tol) { const n = Math.max(24, segsFor(r, 2 * Math.PI, tol)), out = []; for (let i = 0; i < n; i++) out.push(polar(c, 2 * Math.PI * i / n, r)); out.push(out[0].slice()); return out; }
  // эллипс: центр, конец большой полуоси (вектор ax от центра) и малая полуось b; точки с прогибом хорды не больше tol
  function ellipsePts(c, ax, b, tol = 0.01) {
    const a = len(ax), u = a ? mul(ax, 1 / a) : [1, 0], v = [-u[1], u[0]], n = Math.max(32, segsFor(Math.max(a, b), 2 * Math.PI, tol)), out = [];
    for (let i = 0; i < n; i++) { const t = 2 * Math.PI * i / n; out.push(add(c, add(mul(u, a * Math.cos(t)), mul(v, b * Math.sin(t))))); }
    out.push(out[0].slice()); return out;
  }
  // правильный многоугольник: вписанный (вершины на окружности) или описанный (середины сторон на окружности)
  function regPoly(c, n, r, a0, inscribed = true) {
    const R = inscribed ? r : r / Math.cos(Math.PI / n), start = inscribed ? a0 : a0 + Math.PI / n, out = [];
    for (let i = 0; i < n; i++) out.push(polar(c, start + 2 * Math.PI * i / n, R));
    out.push(out[0].slice()); return out;
  }
  const chainLen = pts => pts.slice(1).reduce((s, p, i) => s + dist(pts[i], p), 0);
  function area(ring) { let s = 0; for (let i = 0; i + 1 < ring.length; i++) s += cross(ring[i], ring[i + 1]); if (!closed(ring) && ring.length > 2) s += cross(ring[ring.length - 1], ring[0]); return s / 2; }

  // ближайшая точка цепочки к p: номер отрезка, доля, расстояние вдоль цепочки, сама точка
  function nearest(pts, p) {
    let best = null, s = 0;
    for (let i = 0; i + 1 < pts.length; i++) {
      const a = pts[i], b = pts[i + 1], q = foot(p, a, b, true), d = dist(p, q), L = dist(a, b);
      if (!best || d < best.d) best = { i, t: L ? dist(a, q) / L : 0, s: s + dist(a, q), p: q, d };
      s += L;
    }
    return best;
  }
  // подобие: цепочка на расстоянии d (плюс — слева по ходу), углы — продолжением сторон до пересечения
  function offset(pts, d) {
    const cl = closed(pts), P = cl ? pts.slice(0, -1) : pts.slice(), n = P.length; if (n < 2) return null;
    const segs = [];
    for (let i = 0; i < (cl ? n : n - 1); i++) {
      const a = P[i], b = P[(i + 1) % n], u = unit(sub(b, a)), nrm = [-u[1] * d, u[0] * d];
      if (dist(a, b) > EPS) segs.push([add(a, nrm), add(b, nrm)]);
    }
    if (!segs.length) return null;
    const out = [];
    const join = (s1, s2) => { const x = inter(s1[0], s1[1], s2[0], s2[1], true); return x ? x.p : s1[1]; };
    if (cl) { for (let i = 0; i < segs.length; i++) out.push(join(segs[(i - 1 + segs.length) % segs.length], segs[i])); out.push(out[0].slice()); }
    else { out.push(segs[0][0]); for (let i = 1; i < segs.length; i++) out.push(join(segs[i - 1], segs[i])); out.push(segs[segs.length - 1][1]); }
    return out;
  }
  // с какой стороны цепочки лежит p: +1 слева, -1 справа (по ближайшему отрезку)
  function side(pts, p) { const q = nearest(pts, p); const a = pts[q.i], b = pts[q.i + 1]; return cross(sub(b, a), sub(p, a)) >= 0 ? 1 : -1; }

  // точки пересечения цепочки с другими цепочками (и с самой собой) — расстояния вдоль цепочки, по возрастанию
  function cutsAlong(pts, others, withSelf = true) {
    const cuts = []; let s = 0;
    for (let i = 0; i + 1 < pts.length; i++) {
      const a = pts[i], b = pts[i + 1], L = dist(a, b);
      for (const o of others) for (let j = 0; j + 1 < o.length; j++) { const x = inter(a, b, o[j], o[j + 1]); if (x) cuts.push(s + x.t * L); }
      if (withSelf) for (let j = 0; j + 1 < pts.length; j++) { if (Math.abs(j - i) <= 1 || (closed(pts) && ((i === 0 && j === pts.length - 2) || (j === 0 && i === pts.length - 2)))) continue; const x = inter(a, b, pts[j], pts[j + 1]); if (x) cuts.push(s + x.t * L); }
      s += L;
    }
    return [...new Set(cuts.map(c => Math.round(c * 1e6) / 1e6))].sort((x, y) => x - y);
  }
  // кусок цепочки между расстояниями s0 и s1 вдоль неё
  function sliceChain(pts, s0, s1) {
    const out = []; let s = 0;
    const at = (i, t) => add(pts[i], mul(sub(pts[i + 1], pts[i]), t));
    for (let i = 0; i + 1 < pts.length; i++) {
      const L = dist(pts[i], pts[i + 1]), e = s + L;
      if (e >= s0 - 1e-9 && s <= s1 + 1e-9) {
        if (!out.length) out.push(at(i, L ? Math.max(0, (s0 - s) / L) : 0));
        if (e <= s1 + 1e-9) out.push(pts[i + 1].slice()); else { out.push(at(i, L ? (s1 - s) / L : 0)); break; }
      }
      s = e;
    }
    return out.filter((p, i) => !i || !same(p, out[i - 1], 1e-7));
  }
  // обрезка: убрать кусок цепочки вокруг точки щелчка s между соседними пересечениями; вернуть оставшиеся куски
  function trim(pts, sClick, cuts) {
    const L = chainLen(pts), inner = cuts.filter(c => c > 1e-7 && c < L - 1e-7);
    const lo = Math.max(0, ...inner.filter(c => c < sClick)), hi = Math.min(L, ...inner.filter(c => c > sClick));
    if (closed(pts)) {
      if (inner.length < 2) return null;                             // замкнутый контур режется только двумя пересечениями
      const below = inner.filter(c => c < sClick), above = inner.filter(c => c > sClick);
      const a = below.length ? below[below.length - 1] : inner[inner.length - 1], b = above.length ? above[0] : inner[0];
      // оставляем дугу от b до a, идущую через начало цепочки при необходимости
      if (a < b) return [sliceChain(pts, b, L).concat(sliceChain(pts, 0, a).slice(1))];
      return [sliceChain(pts, b, a)];
    }
    if (lo <= 1e-7 && hi >= L - 1e-7) return null;                    // пересечений нет: обрезать нечего
    const out = [];
    if (lo > 1e-7) out.push(sliceChain(pts, 0, lo));
    if (hi < L - 1e-7) out.push(sliceChain(pts, hi, L));
    return out.filter(c => c.length >= 2 && chainLen(c) > 1e-6);
  }
  // разрыв между двумя точками цепочки
  function breakChain(pts, s0, s1) { if (s0 > s1) [s0, s1] = [s1, s0]; const L = chainLen(pts); return [sliceChain(pts, 0, s0), sliceChain(pts, s1, L)].filter(c => c.length >= 2 && chainLen(c) > 1e-6); }
  // удлинение конца до ближайшей границы по направлению последнего отрезка
  function extend(pts, atStart, others) {
    const P = atStart ? pts.slice().reverse() : pts.slice(), a = P[P.length - 2], b = P[P.length - 1], dir = unit(sub(b, a));
    let best = null;
    for (const o of others) for (let j = 0; j + 1 < o.length; j++) {
      const x = inter(b, add(b, dir), o[j], o[j + 1], true);
      if (!x || x.t <= 1e-6 || x.u < -1e-9 || x.u > 1 + 1e-9) continue;
      if (!best || x.t < best.t) best = x;
    }
    if (!best) return null;
    P[P.length - 1] = best.p; return atStart ? P.reverse() : P;
  }
  // сопряжение угла v (соседи p0, p2) радиусом r: точки касания и дуга (от p0 к p2)
  function filletCorner(p0, v, p2, r) {
    const u1 = unit(sub(p0, v)), u2 = unit(sub(p2, v)), th = Math.acos(Math.max(-1, Math.min(1, dot(u1, u2))));
    if (th < 1e-6 || Math.PI - th < 1e-6) return null;
    const t = r / Math.tan(th / 2); if (t > dist(p0, v) + 1e-9 || t > dist(p2, v) + 1e-9) return null;
    const t1 = add(v, mul(u1, t)), t2 = add(v, mul(u2, t)), bis = unit(add(u1, u2)), c = add(v, mul(bis, r / Math.sin(th / 2)));
    const a0 = ang(c, t1), a1 = ang(c, t2); let sw = norm2pi(a1 - a0); if (sw > Math.PI) sw -= 2 * Math.PI;
    return { t1, t2, arc: { c, r, a0, sw } };
  }
  // сопряжение всех углов цепочки
  function filletAll(pts, r, tol) {
    const cl = closed(pts), P = cl ? pts.slice(0, -1) : pts, n = P.length, out = [];
    let done = 0;
    for (let i = 0; i < n; i++) {
      if (!cl && (i === 0 || i === n - 1)) { out.push(P[i]); continue; }
      const f = filletCorner(P[(i - 1 + n) % n], P[i], P[(i + 1) % n], r);
      if (!f) { out.push(P[i]); continue; }
      out.push(...arcPts(f.arc, tol)); done++;
    }
    if (cl) out.push(out[0].slice());
    return { pts: out, done };
  }
  // фаска угла v: отрезать d1 по стороне к p0 и d2 по стороне к p2
  function chamferCorner(p0, v, p2, d1, d2) {
    if (d1 > dist(p0, v) + 1e-9 || d2 > dist(p2, v) + 1e-9) return null;
    return { t1: add(v, mul(unit(sub(p0, v)), d1)), t2: add(v, mul(unit(sub(p2, v)), d2)) };
  }
  function chamferAll(pts, d1, d2) {
    const cl = closed(pts), P = cl ? pts.slice(0, -1) : pts, n = P.length, out = []; let done = 0;
    for (let i = 0; i < n; i++) {
      if (!cl && (i === 0 || i === n - 1)) { out.push(P[i]); continue; }
      const c = chamferCorner(P[(i - 1 + n) % n], P[i], P[(i + 1) % n], d1, d2);
      if (!c) { out.push(P[i]); continue; } out.push(c.t1, c.t2); done++;
    }
    if (cl) out.push(out[0].slice());
    return { pts: out, done };
  }
  // дуга, касательная к направлению t в точке p0 и приходящая в p1 (дуговой участок полилинии AutoCAD)
  function tangentArc(p0, t, p1) {
    const d = sub(p1, p0), n = [-t[1], t[0]], s = dot(d, n);
    if (Math.abs(s) < 1e-9 * Math.max(1, len(d))) return null;               // по касательной — это прямая
    const r = dot(d, d) / (2 * s), c = add(p0, mul(n, r)), a0 = ang(c, p0), a1 = ang(c, p1);
    const sw = r > 0 ? norm2pi(a1 - a0) : -norm2pi(a0 - a1);
    return { c, r: Math.abs(r), a0, sw };
  }
  // направление касательной в конце дуги
  const arcEndDir = a => { const e = a.a0 + a.sw; return a.sw >= 0 ? [-Math.sin(e), Math.cos(e)] : [Math.sin(e), -Math.cos(e)]; };
  // удлинить или укоротить конец цепочки на delta по направлению последнего отрезка
  function lengthen(pts, atStart, delta) {
    const P = atStart ? pts.slice().reverse() : pts.slice(), L = chainLen(P);
    if (delta < 0) { if (-delta >= L - 1e-9) return null; const out = sliceChain(P, 0, L + delta); return atStart ? out.reverse() : out; }
    const a = P[P.length - 2], b = P[P.length - 1]; P[P.length - 1] = add(b, mul(unit(sub(b, a)), delta));
    return atStart ? P.reverse() : P;
  }
  // соединение цепочек, у которых совпадают концы (допуск tol), в наименьшее число цепочек
  function join(chains, tol = 0.001) {
    const left = chains.map(c => c.slice()), out = [];
    while (left.length) {
      let cur = left.shift(), grew = true;
      while (grew) {
        grew = false;
        for (let i = 0; i < left.length; i++) {
          const c = left[i], s = cur[0], e = cur[cur.length - 1];
          if (same(e, c[0], tol)) cur = cur.concat(c.slice(1));
          else if (same(e, c[c.length - 1], tol)) cur = cur.concat(c.slice(0, -1).reverse());
          else if (same(s, c[c.length - 1], tol)) cur = c.slice(0, -1).concat(cur);
          else if (same(s, c[0], tol)) cur = c.slice(1).reverse().concat(cur);
          else continue;
          left.splice(i, 1); grew = true; break;
        }
      }
      out.push(cur);
    }
    return out;
  }
  // аффинные преобразования точки: перенос, поворот, масштаб, зеркало
  const T = {
    move: d => p => add(p, d),
    rotate: (c, a) => p => { const x = p[0] - c[0], y = p[1] - c[1], cs = Math.cos(a), sn = Math.sin(a); return [c[0] + x * cs - y * sn, c[1] + x * sn + y * cs]; },
    scale: (c, k) => p => add(c, mul(sub(p, c), k)),
    mirror: (a, b) => p => { const f = foot(p, a, b, false); return sub(mul(f, 2), p); } };

  const api = { EPS, sub, add, mul, dot, cross, len, dist, ang, unit, polar, same, closed, norm2pi, inter, foot, segCircle, circleCircle, tangents,
    circle3, arc3, arcPts, circlePts, regPoly, chainLen, area, nearest, offset, side, cutsAlong, sliceChain, trim, breakChain, extend,
    ellipsePts, filletCorner, filletAll, chamferCorner, chamferAll, tangentArc, arcEndDir, lengthen, join, T };
  if (typeof module === "object" && module.exports) module.exports = api; else root.CG = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
