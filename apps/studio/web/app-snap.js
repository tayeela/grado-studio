// ============================================================================
//  app-snap.js — движок объектных привязок (osnap) и курсор-точка.
//  Вынесено из монолита app.js (P0-разрез). Классический скрипт, общий
//  global-scope. Грузится ПЕРЕД app.js (draw() зовёт drawSnapMarker на init).
//  Внешние зависимости — runtime-глобали app.js: state, cv, w2s, cvColor,
//  featurePts, layerOf, isHidden, isLocked, LAYERS_V2, gridStep, lastDrawingPt,
//  и гео-примитивы (pointInRing/nearChain/nearestOnSeg/circleCircleIntersections/
//  segCircleIntersections/isAngleInSweep — пока остаются в app.js как общие).
//  SNAP_PRIORITY и все snap-функции здесь.
// ============================================================================

function featureChains(f) {
  if (f.ring) return [[...f.ring, f.ring[0]]];
  if (f.line) return [f.line];
  if (f.arc) {
    // approx for hit/snap: sample arc
    const a = f.arc; const n=12; const pts=[];
    for(let i=0;i<=n;i++){ const ang=a.a0 + a.sweep*i/n; pts.push([a.cx + a.r*Math.cos(ang), a.cy + a.r*Math.sin(ang)]); }
    return [pts];
  }
  if (f.circle) {
    const c = f.circle; const n=24; const pts=[];
    for(let i=0;i<=n;i++){ const ang = i/n * 2*Math.PI; pts.push([c.cx + c.r*Math.cos(ang), c.cy + c.r*Math.sin(ang)]); }
    return [pts];
  }
  return [];
}

// ---------- привязки (уровень CAD) ----------
const SNAP_PRIORITY = { "вершина": 0, "пересечение": 1, "квадрант": 1, "середина": 2,
                        "перпендикуляр": 2, "касательная": 2, "центр": 3, "ближайшая": 4 };

function _excludeSet(exclude) {
  if (exclude == null) return null;
  return exclude instanceof Set ? exclude : new Set([].concat(exclude));
}

function collectSnapPts(exclude) {
  const ex = _excludeSet(exclude);
  const out = [];
  for (const f of state.features) {
    if ((ex && ex.has(f.id)) || isHidden(f)) continue;
    if (f.point) { out.push({ p: f.point, kind: "вершина" }); continue; }
    if (f.circle) {
      const c = f.circle;
      out.push({ p: [c.cx, c.cy], kind: "центр" });
      // квадранты — привязки CAD (север/восток/юг/запад окружности)
      out.push({ p: [c.cx + c.r, c.cy], kind: "квадрант" });
      out.push({ p: [c.cx - c.r, c.cy], kind: "квадрант" });
      out.push({ p: [c.cx, c.cy + c.r], kind: "квадрант" });
      out.push({ p: [c.cx, c.cy - c.r], kind: "квадрант" });
    }
    for (const chain of featureChains(f)) {
      for (let i = 0; i + 1 < chain.length; i++) {
        out.push({ p: chain[i], kind: "вершина" });
        out.push({ p: [(chain[i][0] + chain[i + 1][0]) / 2,
                       (chain[i][1] + chain[i + 1][1]) / 2], kind: "середина" });
      }
    }
    if (f.ring) {
      const xs = f.ring.map(p => p[0]), ys = f.ring.map(p => p[1]);
      out.push({ p: [(Math.min(...xs) + Math.max(...xs)) / 2,
                     (Math.min(...ys) + Math.max(...ys)) / 2], kind: "центр" });
    }
    if (f.arc) {
      const a = f.arc;
      out.push({ p: [a.cx, a.cy], kind: "центр" });
      // точные концы (вершины) и середина дуги — вместо грубых 5 сэмплов
      out.push({ p: [a.cx + a.r * Math.cos(a.a0), a.cy + a.r * Math.sin(a.a0)], kind: "вершина" });
      out.push({ p: [a.cx + a.r * Math.cos(a.a0 + a.sweep), a.cy + a.r * Math.sin(a.a0 + a.sweep)], kind: "вершина" });
      out.push({ p: [a.cx + a.r * Math.cos(a.a0 + a.sweep / 2), a.cy + a.r * Math.sin(a.a0 + a.sweep / 2)], kind: "середина" });
    }
  }
  return out;
}

function intersections() {
  if (state._ix) return state._ix;
  const segs = [];
  for (const f of state.features) {
    if (isHidden(f)) continue;
    for (const chain of featureChains(f))
      for (let i = 0; i + 1 < chain.length; i++)
        segs.push([chain[i], chain[i + 1]]);
  }
  const out = [];
  for (let i = 0; i < segs.length && i < 400; i++)
    for (let j = i + 1; j < segs.length && j < 400; j++) {
      const p = segIntersect(segs[i][0], segs[i][1], segs[j][0], segs[j][1]);
      if (p) out.push(p);
    }
  // точные пересечения с окружностями/дугами (по параметрам, не по сэмплам):
  // линия×окружность, окружность×окружность; для дуг — фильтр по развёртке
  const curves = [];
  const realSegs = [];   // настоящие прямые сегменты (без сэмплов дуг)
  for (const f of state.features) {
    if (isHidden(f)) continue;
    if (f.circle) curves.push({ cx: f.circle.cx, cy: f.circle.cy, r: f.circle.r, full: true });
    else if (f.arc) curves.push({ cx: f.arc.cx, cy: f.arc.cy, r: f.arc.r, a0: f.arc.a0, sweep: f.arc.sweep, full: false });
    else for (const ch of (f.ring ? [[...f.ring, f.ring[0]]] : f.line ? [f.line] : []))
      for (let i = 0; i + 1 < ch.length; i++) realSegs.push([ch[i], ch[i + 1]]);
  }
  const onCurve = (p, cv) => cv.full || isAngleInSweep(Math.atan2(p[1] - cv.cy, p[0] - cv.cx), cv.a0, cv.sweep);
  if (curves.length) {
    for (let s = 0; s < realSegs.length && s < 600; s++)
      for (const cv of curves)
        for (const p of segCircleIntersections(realSegs[s][0], realSegs[s][1], cv.cx, cv.cy, cv.r))
          if (onCurve(p, cv)) out.push(p);
    for (let i = 0; i < curves.length; i++)
      for (let j = i + 1; j < curves.length; j++)
        for (const p of circleCircleIntersections(curves[i].cx, curves[i].cy, curves[i].r, curves[j].cx, curves[j].cy, curves[j].r))
          if (onCurve(p, curves[i]) && onCurve(p, curves[j])) out.push(p);
  }
  state._ix = out;
  return out;
}

// сегменты всех видимых объектов (кроме исключённых) — для привязок
// «ближайшая точка на ребре» и «перпендикуляр»
function segmentsOf(exclude) {
  const ex = _excludeSet(exclude);
  const segs = [];
  for (const f of state.features) {
    if ((ex && ex.has(f.id)) || isHidden(f) || f.point) continue;
    for (const chain of featureChains(f))
      for (let i = 0; i + 1 < chain.length; i++) segs.push([chain[i], chain[i + 1]]);
  }
  return segs;
}
function footOnLine(p, a, b, clamp) {
  const dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy || 1e-9;
  let t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2;
  if (clamp) t = Math.max(0, Math.min(1, t));
  return [a[0] + t * dx, a[1] + t * dy];
}

function tangentPointsToArc(from, arc) {
  const dx = arc.cx - from[0], dy = arc.cy - from[1];
  const dist = Math.hypot(dx, dy);
  if (dist < arc.r + 1e-9) return [];
  const leg = Math.sqrt(dist * dist - arc.r * arc.r);
  const ang = Math.atan2(dy, dx);
  const delta = Math.asin(arc.r / dist);
  const pts = [];
  for (const sign of [1, -1]) {
    const tAng = ang + sign * delta;
    pts.push([arc.cx + arc.r * Math.cos(tAng), arc.cy + arc.r * Math.sin(tAng)]);
  }
  return pts;
}

// exclude — id объектов, исключаемых из привязок (свой при правке);
// from — опорная точка для «перпендикуляр» (последняя точка построения)
function snapPoint(wx, wy, exclude, from) {
  state.guides = [];
  const tolW = 10 / state.view.k;
  const ex = _excludeSet(exclude);
  // 1. объектные привязки по приоритету
  if (state.osnap) {
    let best = null;
    for (const c of collectSnapPts(exclude)) {
      const d = Math.hypot(c.p[0] - wx, c.p[1] - wy);
      if (d > tolW) continue;
      const key = [SNAP_PRIORITY[c.kind], d];
      if (!best || key[0] < best.key[0] || (key[0] === best.key[0] && key[1] < best.key[1]))
        best = { p: [...c.p], kind: c.kind, key };
    }
    for (const p of intersections()) {
      const d = Math.hypot(p[0] - wx, p[1] - wy);
      if (d <= tolW && (!best || best.key[0] > 1 || (best.key[0] === 1 && d < best.key[1])))
        best = { p: [...p], kind: "пересечение", key: [1, d] };
    }
    // перпендикуляр: основание перпендикуляра из опорной точки на прямую ребра
    if (from) {
      for (const [a, b] of segmentsOf(exclude)) {
        const foot = footOnLine(from, a, b, false);
        const d = Math.hypot(foot[0] - wx, foot[1] - wy);
        if (d > tolW) continue;
        const key = [SNAP_PRIORITY["перпендикуляр"], d];
        if (!best || key[0] < best.key[0] || (key[0] === best.key[0] && key[1] < best.key[1]))
          best = { p: foot, kind: "перпендикуляр", key };
      }
      // касательные к дугам и окружностям от опорной точки
      for (const f of state.features) {
        if ((ex && ex.has(f.id)) || isHidden(f)) continue;
        const carc = f.arc || f.circle;
        if (!carc) continue;
        for (const tp of tangentPointsToArc(from, carc)) {
          const d = Math.hypot(tp[0] - wx, tp[1] - wy);
          if (d > tolW) continue;
          const key = [SNAP_PRIORITY["касательная"], d];
          if (!best || key[0] < best.key[0] || (key[0] === best.key[0] && key[1] < best.key[1]))
            best = { p: tp, kind: "касательная", key };
        }
      }
    }
    if (best) return { p: best.p, kind: best.kind };
    // 2. направляющие выравнивания по вершинам
    let gx = null, gy = null;
    for (const c of collectSnapPts(exclude)) {
      if (c.kind !== "вершина") continue;
      if (Math.abs(c.p[0] - wx) < tolW && (!gx || Math.abs(c.p[0] - wx) < Math.abs(gx.p[0] - wx))) gx = c;
      if (Math.abs(c.p[1] - wy) < tolW && (!gy || Math.abs(c.p[1] - wy) < Math.abs(gy.p[1] - wy))) gy = c;
    }
    if (gx || gy) {
      const p = [gx ? gx.p[0] : wx, gy ? gy.p[1] : wy];
      if (gx) state.guides.push([gx.p, p]);
      if (gy) state.guides.push([gy.p, p]);
      return { p, kind: "выравнивание" };
    }
    // 2b. ближайшая точка на ребре — низший приоритет объектной привязки
    let near = null;
    for (const [a, b] of segmentsOf(exclude)) {
      const foot = footOnLine([wx, wy], a, b, true);
      const d = Math.hypot(foot[0] - wx, foot[1] - wy);
      if (d <= tolW && (!near || d < near.d)) near = { p: foot, d };
    }
    // ближайшая точка на окружности/дуге (проекция курсора на кривую)
    for (const f of state.features) {
      if ((ex && ex.has(f.id)) || isHidden(f)) continue;
      if (f.circle) {
        const c = f.circle, dx = wx - c.cx, dy = wy - c.cy, dl = Math.hypot(dx, dy) || 1e-9;
        const p = [c.cx + c.r * dx / dl, c.cy + c.r * dy / dl];
        const d = Math.hypot(p[0] - wx, p[1] - wy);
        if (d <= tolW && (!near || d < near.d)) near = { p, d };
      } else if (f.arc) {
        const a = f.arc, dx = wx - a.cx, dy = wy - a.cy;
        let ang = Math.atan2(dy, dx);
        if (!isAngleInSweep(ang, a.a0, a.sweep)) {   // вне дуги — прижать к ближнему концу
          const e0 = a.a0, e1 = a.a0 + a.sweep;
          const dst = t => Math.abs(((ang - t + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI);
          ang = dst(e0) < dst(e1) ? e0 : e1;
        }
        const p = [a.cx + a.r * Math.cos(ang), a.cy + a.r * Math.sin(ang)];
        const d = Math.hypot(p[0] - wx, p[1] - wy);
        if (d <= tolW && (!near || d < near.d)) near = { p, d };
      }
    }
    if (near) return { p: near.p, kind: "ближайшая" };
  }
  // (направляющие уже используют тот же exclude через collectSnapPts выше)
  // 3. сетка
  if (state.gridSnap) {
    const g = gridStep();
    return { p: [Math.round(wx / g) * g, Math.round(wy / g) * g], kind: "сетка" };
  }
  return { p: [wx, wy], kind: null };
}

function orthoProject(base, wx, wy) {
  // фиксация направления на 0/45/90° (Shift)
  const dx = wx - base[0], dy = wy - base[1];
  const dist = Math.hypot(dx, dy);
  if (dist < 1e-9) return [wx, wy];
  const a = Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4);
  return [base[0] + dist * Math.cos(a), base[1] + dist * Math.sin(a)];
}

function cursorPoint(wx, wy) {
  const base = lastDrawingPt();
  if (shiftDown && base) {
    const [ox, oy] = orthoProject(base, wx, wy);
    if (state.gridSnap) {
      // выравниваем длину по шагу сетки вдоль зафиксированного направления
      const g = gridStep();
      const d = Math.round(Math.hypot(ox - base[0], oy - base[1]) / g) * g;
      const a = Math.atan2(oy - base[1], ox - base[0]);
      return { p: [base[0] + d * Math.cos(a), base[1] + d * Math.sin(a)], kind: "орто" };
    }
    return { p: [ox, oy], kind: "орто" };
  }
  // from=base: во время построения доступна привязка «перпендикуляр»
  let exclude = state.edit && state.edit.f ? state.edit.f.id : undefined;
  // инструменты преобразования в фазе «act»: выделение движется вместе с превью,
  // поэтому реф/ось/масштаб привязываем к ФИКСИРОВАННЫМ объектам, исключая само
  // выделение (иначе привязка цепляется за ползущую геометрию). Опорная точка
  // (фаза «base») привязывается ко всему — в т.ч. к вершинам самого объекта.
  if (state.xf && state.xf.phase === "act") exclude = new Set(selectionIds());
  return snapPoint(wx, wy, exclude, base);
}

function drawSnapMarker() {
  const s = state.snapHit;
  // в «Выборе» маркер нужен при переносе/правке (state.edit), иначе скрыт
  if (!s || !s.kind || (state.tool === "select" && !state.edit)) return;
  const [sx, sy] = w2s(...s.p);
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = cvColor("shared", "#12a150");
  if (s.kind === "вершина") ctx.strokeRect(sx - 5, sy - 5, 10, 10);
  else if (s.kind === "середина") {
    ctx.beginPath(); ctx.moveTo(sx, sy - 6); ctx.lineTo(sx + 6, sy + 5); ctx.lineTo(sx - 6, sy + 5);
    ctx.closePath(); ctx.stroke();
  } else if (s.kind === "пересечение") {
    ctx.beginPath();
    ctx.moveTo(sx - 5, sy - 5); ctx.lineTo(sx + 5, sy + 5);
    ctx.moveTo(sx - 5, sy + 5); ctx.lineTo(sx + 5, sy - 5); ctx.stroke();
  } else if (s.kind === "центр") {
    ctx.beginPath(); ctx.arc(sx, sy, 5.5, 0, 7); ctx.stroke();
  } else if (s.kind === "перпендикуляр") {
    ctx.beginPath();                          // ⊥ — прямой угол
    ctx.moveTo(sx - 6, sy - 6); ctx.lineTo(sx - 6, sy + 6); ctx.lineTo(sx + 6, sy + 6);
    ctx.moveTo(sx - 6, sy); ctx.lineTo(sx, sy); ctx.lineTo(sx, sy + 6); ctx.stroke();
  } else if (s.kind === "ближайшая") {
    ctx.beginPath();                          // ◇ — ромб на ребре
    ctx.moveTo(sx, sy - 5); ctx.lineTo(sx + 5, sy);
    ctx.lineTo(sx, sy + 5); ctx.lineTo(sx - 5, sy); ctx.closePath(); ctx.stroke();
  } else if (s.kind === "выравнивание" || s.kind === "орто") {
    ctx.beginPath(); ctx.arc(sx, sy, 3, 0, 7); ctx.stroke();
  } else if (s.kind === "сетка") {
    ctx.strokeStyle = cvColor("label", "#9a978f");
    ctx.beginPath();
    ctx.moveTo(sx - 4, sy); ctx.lineTo(sx + 4, sy);
    ctx.moveTo(sx, sy - 4); ctx.lineTo(sx, sy + 4); ctx.stroke();
  }
}
