/* Draws AutoCAD complex linetypes (LIN + SHX) on a canvas.
   Data: styles/redln97.json, generated from REDLN97.LIN + RED_LNS.SHX by tools/gen_redln97.py.
   Pattern units are drawing units (metres); k = pixels per metre. */
(function () {
  let LIB = null, SHAPES = {};
  const Linetypes = {
    async load(url = "/styles/redln97.json") {
      LIB = await (await fetch(url)).json();
      SHAPES = Object.fromEntries(Object.entries(LIB.shapes).map(([n, s]) => [n.toUpperCase(), s]));
      return LIB;
    },
    get lib() { return LIB; },
    /* LineCode ±code → linetype name ("+" = object to the right of the line → variant b) */
    forCode(code, sign, family = "00") {
      const fams = LIB?.lgr[String(code)]; if (!fams) return null;
      const f = fams[family] || Object.values(fams)[0];
      return f.s || f[sign > 0 ? "b" : "t"] || f[sign > 0 ? "t" : "b"];
    },
    draw,
  };

  function draw(ctx, pts, name, k, { color = "#d7191c", width = 1.2, plain = false } = {}) {
    const lt = LIB?.linetypes[name];
    ctx.save(); ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = width; ctx.lineCap = "butt"; ctx.lineJoin = "round";
    const seg = [], cum = [0];
    for (let i = 1; i < pts.length; i++) { const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); seg.push(d); cum.push(cum[i - 1] + d); }
    const L = cum[cum.length - 1];
    const patLen = lt ? lt.length * k : 0;
    // AutoCAD rule from REDLN97: a line shorter than two pattern lengths is drawn solid
    if (!lt || plain || !patLen || L < 2 * patLen) { ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.stroke(); ctx.restore(); return; }
    let si = 0;
    const at = t => { while (si < seg.length - 1 && cum[si + 1] < t) si++; while (si > 0 && cum[si] > t) si--; const f = seg[si] ? (t - cum[si]) / seg[si] : 0, a = pts[si], b = pts[si + 1]; const ux = seg[si] ? (b[0] - a[0]) / seg[si] : 1, uy = seg[si] ? (b[1] - a[1]) / seg[si] : 0; return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, ux, uy]; };
    const dash = (t0, t1) => { t1 = Math.min(t1, L); if (t1 <= t0) return; si = 0; const p = at(t0); ctx.moveTo(p[0], p[1]); for (let i = 1; i < pts.length; i++) if (cum[i] > t0 && cum[i] < t1) ctx.lineTo(pts[i][0], pts[i][1]); const q = at(t1); ctx.lineTo(q[0], q[1]); };
    ctx.beginPath();
    let t = 0, guard = 0;
    while (t < L && guard++ < 20000) {
      for (const e of lt.pattern) {
        if (t >= L) break;
        if (e.d !== undefined) {
          if (e.d > 0) dash(t, t + e.d * k);
          else if (e.d === 0) { si = 0; const p = at(t); ctx.moveTo(p[0] - width / 2, p[1]); ctx.lineTo(p[0] + width / 2, p[1]); }
          t += Math.abs(e.d) * k;
        } else if (e.shape) {
          const s = SHAPES[e.shape.toUpperCase()]; if (!s) continue; si = 0;
          const [px, py, ux0, uy0] = at(t);
          // canvas y points down: "left of travel" in drawing space = (uy, -ux) in canvas
          const vx = uy0, vy = -ux0, r = (e.r || 0) * Math.PI / 180, cr = Math.cos(r), sr = Math.sin(r), sc = (e.s || 1) * k;
          const ax = e.abs ? 1 : ux0, ay = e.abs ? 0 : uy0, bx = e.abs ? 0 : vx, by = e.abs ? -1 : vy;
          const ox = px + (e.x || 0) * k * ux0 + (e.y || 0) * k * vx, oy = py + (e.x || 0) * k * uy0 + (e.y || 0) * k * vy;
          for (const path of s.paths) path.forEach(([sx, sy], i) => {
            const lx = (sx * cr - sy * sr) * sc, ly = (sx * sr + sy * cr) * sc;
            const X = ox + lx * ax + ly * bx, Y = oy + lx * ay + ly * by;
            i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y);
          });
        }
      }
    }
    ctx.stroke(); ctx.restore();
  }
  window.Linetypes = Linetypes;
})();
