// Мини-движок метрик: тот же язык выражений, что в grado_compute (Python).
// Парсер — рекурсивный спуск; никакого eval.

const FUNCS = {
  min: Math.min,
  max: Math.max,
  abs: Math.abs,
  round: (x, n = 0) => { const k = 10 ** n; return Math.round(x * k) / k; },
  floor: Math.floor,
  ceil: Math.ceil,
  sqrt: Math.sqrt,
  clamp: (x, lo, hi) => Math.max(lo, Math.min(hi, x)),
  where: (cond, a, b) => (cond ? a : b),
};

function tokenize(src) {
  const tokens = [];
  const re = /\s*(\d+\.?\d*|[A-Za-z_][A-Za-z0-9_]*|\*\*|\/\/|>=|<=|==|!=|[-+*/%(),<>])/y;
  let pos = 0;
  while (pos < src.length) {
    re.lastIndex = pos;
    const m = re.exec(src);
    if (!m) throw new Error(`недопустимый символ в выражении: ${src.slice(pos)}`);
    tokens.push(m[1]);
    pos = re.lastIndex;
  }
  return tokens;
}

function parseExpr(src) {
  const tokens = tokenize(src);
  const names = new Set();
  let i = 0;
  const peek = () => tokens[i];
  const next = () => tokens[i++];
  const expect = (t) => { if (next() !== t) throw new Error(`ожидалось "${t}" в: ${src}`); };

  function primary() {
    const t = next();
    if (t === undefined) throw new Error(`неожиданный конец выражения: ${src}`);
    if (t === "(") { const e = comparison(); expect(")"); return e; }
    if (/^\d/.test(t)) { const v = parseFloat(t); return () => v; }
    if (/^[A-Za-z_]/.test(t)) {
      if (peek() === "(") {
        next();
        const fn = FUNCS[t];
        if (!fn) throw new Error(`неизвестная функция ${t}`);
        const args = [];
        if (peek() !== ")") {
          args.push(comparison());
          while (peek() === ",") { next(); args.push(comparison()); }
        }
        expect(")");
        return (v) => fn(...args.map((a) => a(v)));
      }
      names.add(t);
      return (v) => {
        if (!(t in v)) throw new Error(`неизвестное имя ${t}`);
        return v[t];
      };
    }
    throw new Error(`неожиданный токен "${t}" в: ${src}`);
  }

  function unary() {
    if (peek() === "-") { next(); const e = unary(); return (v) => -e(v); }
    if (peek() === "+") { next(); return unary(); }
    return power();
  }

  function power() {
    const base = primary();
    if (peek() === "**") { next(); const exp = unary(); return (v) => base(v) ** exp(v); }
    return base;
  }

  function multiplicative() {
    let e = unary();
    while (["*", "/", "//", "%"].includes(peek())) {
      const op = next(); const r = unary(); const l = e;
      if (op === "*") e = (v) => l(v) * r(v);
      else if (op === "/") e = (v) => l(v) / r(v);
      else if (op === "//") e = (v) => Math.floor(l(v) / r(v));
      else e = (v) => l(v) % r(v);
    }
    return e;
  }

  function additive() {
    let e = multiplicative();
    while (peek() === "+" || peek() === "-") {
      const op = next(); const r = multiplicative(); const l = e;
      e = op === "+" ? (v) => l(v) + r(v) : (v) => l(v) - r(v);
    }
    return e;
  }

  function comparison() {
    const l = additive();
    const op = peek();
    if ([">=", "<=", ">", "<", "==", "!="].includes(op)) {
      next();
      const r = additive();
      const cmp = { ">=": (a, b) => a >= b, "<=": (a, b) => a <= b, ">": (a, b) => a > b,
                    "<": (a, b) => a < b, "==": (a, b) => a === b, "!=": (a, b) => a !== b }[op];
      return (v) => cmp(l(v), r(v));
    }
    return l;
  }

  const fn = comparison();
  if (i !== tokens.length) throw new Error(`лишние токены после выражения: ${src}`);
  return { eval: fn, names };
}

class MetricEngine {
  constructor(preset) {
    this.preset = preset;
    this.inputs = Object.fromEntries(preset.inputs.map((s) => [s.id, s]));
    this.values = { ...(preset.constants || {}) };
    for (const s of preset.inputs) this.values[s.id] = s.default ?? 0;
    this.metrics = preset.metrics.map((s) => ({ ...s, compiled: parseExpr(s.expr) }));
    this.order = this.toposort();
    this.recompute();
  }

  toposort() {
    const byId = new Map(this.metrics.map((m) => [m.id, m]));
    const state = new Map();
    const order = [];
    const visit = (m) => {
      if (state.get(m.id) === 2) return;
      if (state.get(m.id) === 1) throw new Error(`цикл в метриках: ${m.id}`);
      state.set(m.id, 1);
      for (const d of m.compiled.names) if (byId.has(d)) visit(byId.get(d));
      state.set(m.id, 2);
      order.push(m);
    };
    this.metrics.forEach(visit);
    return order;
  }

  setInput(id, value) {
    if (!(id in this.inputs)) throw new Error(`нет входного параметра ${id}`);
    this.values[id] = value;
    this.recompute();
  }

  recompute() {
    for (const m of this.order) this.values[m.id] = m.compiled.eval(this.values);
  }

  display(m) {
    let v = this.values[m.id];
    if (m.precision !== undefined) v = FUNCS.round(v, m.precision);
    return Number.isInteger(v) ? v.toLocaleString("ru-RU") : v.toLocaleString("ru-RU");
  }

  groups() {
    const out = new Map();
    for (const m of this.order) {
      if (m.hidden) continue;
      if (!out.has(m.group)) out.set(m.group, []);
      out.get(m.group).push(m);
    }
    return out;
  }
}

window.GradoCompute = { MetricEngine, parseExpr };
