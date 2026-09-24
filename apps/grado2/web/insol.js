/* ГРАДО 2 · инсоляция: положение солнца, инсоляционный фронт существующих окон, солнечный потолок участка.
   Предпроектная оценка по методам ГОСТ Р 57795-2017 и нормам СанПиН 1.2.3685-21 (табл. 5.58, центральная зона):
   расчётные даты 22 апреля и 22 августа, время солнечное, первый час после восхода и последний перед заходом
   не учитываются (на 55–56° с. ш. — как на инсографике МАрхИ: 6:00–18:00); норма — 2 ч непрерывно или 2,5 ч
   прерывисто при одном периоде не короче 1 ч. Это НЕ сертифицированный расчёт для экспертизы.
   Упрощения: рельеф плоский, высота этажа задаётся одна, теневые углы окон — одним углом на все окна.
   Все координаты — метры в местной рамке (x — восток, y — север). Модуль без DOM: его же гоняет тест в node. */
(function (root) {
  const RAD = Math.PI / 180;

  // склонение солнца (формула Спенсера), день года 1…365
  function declination(day) {
    const g = 2 * Math.PI * (day - 1) / 365;
    return 0.006918 - 0.399912 * Math.cos(g) + 0.070257 * Math.sin(g) - 0.006758 * Math.cos(2 * g)
      + 0.000907 * Math.sin(2 * g) - 0.002697 * Math.cos(3 * g) + 0.00148 * Math.sin(3 * g);
  }
  const DATES = [{ name: "22 апреля", day: 112 }, { name: "22 августа", day: 234 }];

  // солнце в солнечное время t (часы): высота и азимут (от севера по часовой), горизонтальный вектор на солнце
  function sunAt(latDeg, decl, t) {
    const phi = latDeg * RAD, H = 15 * (t - 12) * RAD;
    const sinA = Math.sin(phi) * Math.sin(decl) + Math.cos(phi) * Math.cos(decl) * Math.cos(H);
    const alt = Math.asin(sinA);
    const az = Math.atan2(Math.sin(H), Math.cos(H) * Math.sin(phi) - Math.tan(decl) * Math.cos(phi)) + Math.PI;
    return { t, alt, az, vx: Math.sin(az), vy: Math.cos(az), tan: Math.tan(alt) };
  }

  /* расчётное окно: восход + 1 ч … заход − 1 ч, округлено до получаса (на 55,75° с. ш. — 6:00…18:00,
     как у инсоляционной линейки МАрхИ для 55°); шаг — минуты */
  function sunPath(latDeg, day, stepMin) {
    const d = declination(day), phi = latDeg * RAD;
    const h0 = Math.acos(Math.max(-1, Math.min(1, -Math.tan(phi) * Math.tan(d)))) / RAD / 15;   // полудуга дня, ч
    const start = Math.round((12 - h0 + 1) * 2) / 2, end = 24 - start, out = [];
    for (let m = Math.round(start * 60); m <= Math.round(end * 60) + 1e-9; m += stepMin) out.push(sunAt(latDeg, d, m / 60));
    return { decl: d, start, end, sun: out, step: stepMin };
  }

  /* препятствия: призмы {ring:[[x,y]…] без повтора первой точки, holes — внутренние дворы, h — отметка верха над землёй}.
     Индекс — сетка 40 м: луч проверяет только здания в клетках, через которые проходит. */
  function obstacleIndex(prisms, cell = 40) {
    const idx = new Map(), key = (i, j) => i + "," + j;
    let hmax = 0;
    prisms.forEach((p, n) => {
      const xs = p.ring.map(q => q[0]), ys = p.ring.map(q => q[1]);
      p.bb = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]; hmax = Math.max(hmax, p.h);
      for (let i = Math.floor(p.bb[0] / cell); i <= Math.floor(p.bb[2] / cell); i++)
        for (let j = Math.floor(p.bb[1] / cell); j <= Math.floor(p.bb[3] / cell); j++) { const k = key(i, j); (idx.get(k) || idx.set(k, []).get(k)).push(n); }
    });
    return { prisms, idx, cell, hmax, key };
  }
  // расстояние по лучу (x,y)+(vx,vy)·d до первого пересечения с контуром; Infinity — мимо
  function rayHit(ring, x, y, vx, vy) {
    let best = Infinity;
    for (let i = 0, n = ring.length; i < n; i++) {
      const a = ring[i], b = ring[(i + 1) % n], ex = b[0] - a[0], ey = b[1] - a[1];
      const den = vx * ey - vy * ex; if (Math.abs(den) < 1e-12) continue;
      const wx = a[0] - x, wy = a[1] - y, d = (wx * ey - wy * ex) / den, u = (wx * vy - wy * vx) / den;
      if (d > 1e-6 && u >= 0 && u <= 1 && d < best) best = d;
    }
    return best;
  }
  // освещена ли точка (x,y,z) солнцем s: луч к солнцу не должен пройти под верхом ни одного здания
  function lit(ob, x, y, z, s, skip) {
    if (s.alt <= 0) return false;
    const dmax = (ob.hmax - z) / s.tan; if (dmax <= 0) return true;
    const cell = ob.cell, seen = new Set();
    // шаг по клеткам сетки вдоль луча (полклетки — чтобы не проскочить угол)
    for (let d = 0; d <= dmax + cell; d += cell / 2) {
      const cx = Math.floor((x + s.vx * d) / cell), cy = Math.floor((y + s.vy * d) / cell);
      for (let di = -1; di <= 1; di++) for (let dj = -1; dj <= 1; dj++) {
        const list = ob.idx.get(ob.key(cx + di, cy + dj)); if (!list) continue;
        for (const n of list) {
          if (seen.has(n) || n === skip) continue; seen.add(n);
          const p = ob.prisms[n]; if (p.h <= z) continue;
          let dh = rayHit(p.ring, x, y, s.vx, s.vy);
          if (p.holes) for (const h of p.holes) dh = Math.min(dh, rayHit(h, x, y, s.vx, s.vy));   // из двора луч упирается во внутреннюю стену
          if (dh < Infinity && p.h > z + dh * s.tan) return false;
        }
      }
    }
    return true;
  }

  // периоды освещённости по ряду отсчётов: [{from, to, min}] (минуты)
  function periods(flags, path) {
    const out = []; let st = -1;
    flags.forEach((f, i) => { if (f && st < 0) st = i; if ((!f || i === flags.length - 1) && st >= 0) { const e = f ? i : i - 1; out.push({ from: path.sun[st].t, to: path.sun[e].t, min: (e - st) * path.step, i0: st, i1: e }); st = -1; } });
    return out;
  }
  // оценка по норме: непрерывно ≥ N или прерывисто ≥ N + 30 мин при периоде ≥ 60 мин
  function verdict(pers, normMin) {
    const cont = Math.max(0, ...pers.map(p => p.min)), total = pers.reduce((s, p) => s + p.min, 0);
    const ok = cont >= normMin ? "непрерывная" : total >= normMin + 30 && cont >= 60 ? "прерывистая" : "";
    return { cont, total, ok };
  }

  /* точки фронта: вдоль каждого фасада через step м, в 0,2 м наружу от стены, на высоте z.
     Фасад — ребро контура; нормаль наружу считается по обходу контура. */
  function frontPoints(buildings, step, z) {
    const out = [];
    // точка у стены, примыкающей к соседнему дому (секции урбан-блока, блокированные дома, брандмауэры), — не окно:
    // она внутри соседа. Такие точки отбрасываются, иначе общая стена считается затенённым фасадом
    const G = 40, grid = new Map(), inRing = (x, y, r) => { let c = false; for (let i = 0, j = r.length - 1; i < r.length; j = i++) { const a = r[i], b = r[j]; if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) c = !c; } return c; };
    buildings.forEach((b, bi) => { if (!(b.h - (b.g || 0) > z)) return; let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity; b.ring.forEach(([x, y]) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); });
      for (let gx = Math.floor(x0 / G); gx <= Math.floor(x1 / G); gx++) for (let gy = Math.floor(y0 / G); gy <= Math.floor(y1 / G); gy++) { const k = gx + ":" + gy; (grid.get(k) || grid.set(k, []).get(k)).push(bi); } });
    const covered = (x, y, own) => (grid.get(Math.floor(x / G) + ":" + Math.floor(y / G)) || []).some(bi => bi !== own && inRing(x, y, buildings[bi].ring) && !(buildings[bi].holes || []).some(h => inRing(x, y, h)));
    const signed = r => r.reduce((s, p, i) => { const q = r[(i + 1) % r.length]; return s + p[0] * q[1] - q[0] * p[1]; }, 0);
    // окна выше крыши не бывает: дом ниже расчётной высоты точек не получает
    // h и g — отметки верха и земли дома от общей базы рельефа (без рельефа g = 0); окно — на z над своей землёй
    buildings.forEach((b, bi) => b.h - (b.g || 0) > z && [b.ring, ...(b.holes || [])].forEach((r0, ri) => {
      const zb = (b.g || 0) + z;
      // наружный контур — против часовой, двор — по часовой: тогда справа от ребра всегда воздух, а не здание
      const ring = (signed(r0) < 0) === (ri === 0) ? r0.slice().reverse() : r0;
      for (let i = 0; i < ring.length; i++) {
        const a = ring[i], c = ring[(i + 1) % ring.length], L = Math.hypot(c[0] - a[0], c[1] - a[1]); if (L < 3) continue;
        const ux = (c[0] - a[0]) / L, uy = (c[1] - a[1]) / L, nx = uy, ny = -ux, n = Math.max(1, Math.round(L / step));
        for (let k = 0; k < n; k++) { const f = (k + .5) / n, x = a[0] + ux * L * f + nx * .2, y = a[1] + uy * L * f + ny * .2; if (!covered(x, y, bi)) out.push({ x, y, z: zb, nx, ny, b: bi, yard: ri > 0 }); }
      }
    }));
    return out;
  }

  /* фронт: для каждой точки — освещённость по отсчётам обеих дат, периоды и оценка.
     reveal — теневой угол окна, °: солнце под более острым углом к фасаду окно не освещает. */
  function evalFront(pts, ob, paths, opt) {
    const sinR = Math.sin((opt.reveal || 0) * RAD);
    pts.forEach(p => {
      // окно, которое и без застройки не набирает нормы (фасад на север), нормой не защищается: квартира
      // получает солнце через другие комнаты — так и считает норма (северный сектор 310–50° не нормируется)
      const face = paths.map(path => path.sun.map(s => p.nx * s.vx + p.ny * s.vy > sinR));
      p.orient = face.some((fl, k) => !verdict(periods(fl, paths[k]), opt.norm).ok);
      p.flags = face.map((fl, k) => fl.map((f, i) => f && lit(ob, p.x, p.y, p.z, paths[k].sun[i])));
      const res = p.flags.map((fl, k) => verdict(periods(fl, paths[k]), opt.norm));
      p.worst = res.slice().sort((a, b) => (a.ok ? 1 : 0) - (b.ok ? 1 : 0) || a.cont - b.cont)[0];   // худшая из двух дат
    });
    return pts;
  }

  /* Солнечный потолок: сетка участка, в каждой клетке — наибольшая отметка верха, при которой сохраняются
     защищённые лучи фронта. Защищается у каждой точки:
       · выполняет норму непрерывно — одно окно длиной в норму внутри её освещённого периода, выбранное так,
         чтобы лучи меньше всего шли над участком (солнце «со стороны от участка»);
       · выполняет прерывисто или не выполняет вовсе — всё её нынешнее солнце («не ухудшать»).
     Любой объём ниже потолка не перекрывает ни один защищённый луч, поэтому норма у соседей сохраняется
     независимо от порядка и числа новых корпусов (в отличие от поштучного «выращивания»). */
  function envelope(pts, paths, grid, opt) {
    const { x0, y0, cell, nx, ny, inside } = grid, cap = opt.cap, env = new Float64Array(nx * ny).fill(cap);
    const X1 = x0 + nx * cell, Y1 = y0 + ny * cell;
    const march = (p, s, fn) => {                        // клетки вдоль луча до высоты cap: fn(индекс клетки, отметка луча)
      let a = 0, b = (cap - p.z) / s.tan; if (b <= 0) return;
      for (const [o, v, lo, hi] of [[p.x, s.vx, x0, X1], [p.y, s.vy, y0, Y1]]) {           // отрезок луча внутри сетки
        if (Math.abs(v) < 1e-12) { if (o < lo || o > hi) return; continue; }
        const t1 = (lo - o) / v, t2 = (hi - o) / v; a = Math.max(a, Math.min(t1, t2)); b = Math.min(b, Math.max(t1, t2));
      }
      if (a > b) return;
      // точный обход клеток, которые пересекает луч (Amanatides–Woo); отметка луча — на входе в клетку, там она ниже всего
      let i = Math.min(nx - 1, Math.max(0, Math.floor((p.x + s.vx * a - x0) / cell))), j = Math.min(ny - 1, Math.max(0, Math.floor((p.y + s.vy * a - y0) / cell)));
      const si = s.vx > 0 ? 1 : -1, sj = s.vy > 0 ? 1 : -1;
      const next = (o, v, k, lo) => Math.abs(v) < 1e-12 ? Infinity : ((lo + (k + (v > 0 ? 1 : 0)) * cell) - o) / v;
      let tx = next(p.x, s.vx, i, x0), ty = next(p.y, s.vy, j, y0), d = a;
      const dx = Math.abs(v2(s.vx)), dy = Math.abs(v2(s.vy));
      while (d <= b && i >= 0 && j >= 0 && i < nx && j < ny) {
        fn(j * nx + i, p.z + d * s.tan - 0.01);   // 1 см запаса на округление
        if (tx < ty) { d = tx; tx += dx; i += si; } else { d = ty; ty += dy; j += sj; }
      }
    };
    const v2 = v => Math.abs(v) < 1e-12 ? Infinity : cell / v;
    const normSteps = k => Math.ceil(opt.norm / paths[k].step);
    let protectedRays = 0;
    pts.forEach(p => {
      if (p.orient) return;                                   // северный фасад: защищать нечего
      p.flags.forEach((fl, k) => {
        const path = paths[k], pers = periods(fl, path), v = verdict(pers, opt.norm);
        let keep = [];
        if (v.ok === "непрерывная") {
          const cost = path.sun.map((s, i) => { if (!fl[i]) return 0; let c = 0; march(p, s, n => { if (inside[n]) c++; }); return c; });
          let best = null; const w = normSteps(k);
          pers.filter(r => r.i1 - r.i0 >= w).forEach(r => { for (let a = r.i0; a + w <= r.i1; a++) { let c = 0; for (let i = a; i <= a + w; i++) c += cost[i]; if (!best || c < best.c) best = { a, c }; } });
          if (best) for (let i = best.a; i <= best.a + w; i++) keep.push(i);
        } else fl.forEach((f, i) => { if (f) keep.push(i); });
        keep.forEach(i => { protectedRays++; march(p, path.sun[i], (n, zr) => { if (zr < env[n]) env[n] = zr; }); });
      });
    });
    return { env, protectedRays };
  }

  const INSOL = { declination, sunAt, sunPath, obstacleIndex, lit, rayHit, periods, verdict, frontPoints, evalFront, envelope, DATES };
  if (typeof module !== "undefined" && module.exports) module.exports = INSOL; else root.INSOL = INSOL;
})(typeof window !== "undefined" ? window : globalThis);
