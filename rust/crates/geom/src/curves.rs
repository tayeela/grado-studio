//! Дуги окружностей — параметрическое хранение, линеаризация по допуску.
//!
//! Инвариант ядра: кривая хранится параметрами (центр, радиус, углы), а не
//! ломаной; линеаризация — только на границах (GEOS-операции, экспорт).
//! Клотоиды (переходные кривые УДС) — в C++ ядре; эталон ограничен дугами.
//! Прямой порт `grado_geom/curves.py`.

use serde_json::Value;

use crate::{Pt, TAU};

/// Ошибка кривой (Python: CurveError, подкласс ValueError).
#[derive(Debug, Clone)]
pub struct CurveError(pub String);

impl std::fmt::Display for CurveError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for CurveError {}

/// Дуга: центр, радиус, начальный угол a0, знаковая развёртка sweep.
///
/// sweep > 0 — против часовой (центр слева по ходу), sweep < 0 — по часовой.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Arc {
    pub cx: f64,
    pub cy: f64,
    pub r: f64,
    pub a0: f64,
    pub sweep: f64,
}

impl Arc {
    pub fn new(cx: f64, cy: f64, r: f64, a0: f64, sweep: f64) -> Result<Self, CurveError> {
        if r <= 0.0 {
            return Err(CurveError("радиус должен быть > 0".into()));
        }
        if sweep == 0.0 {
            return Err(CurveError("нулевая развёртка".into()));
        }
        Ok(Arc { cx, cy, r, a0, sweep })
    }

    /// Дуга по трём точкам (начало, промежуточная, конец).
    pub fn from_3pts(p0: Pt, pm: Pt, p1: Pt) -> Result<Self, CurveError> {
        let (x0, y0) = p0;
        let (xm, ym) = pm;
        let (x1, y1) = p1;
        let d = 2.0 * (x0 * (ym - y1) + xm * (y1 - y0) + x1 * (y0 - ym));
        if d.abs() < 1e-12 {
            return Err(CurveError("точки коллинеарны — дуга не определена".into()));
        }
        let s0 = x0 * x0 + y0 * y0;
        let sm = xm * xm + ym * ym;
        let s1 = x1 * x1 + y1 * y1;
        let cx = (s0 * (ym - y1) + sm * (y1 - y0) + s1 * (y0 - ym)) / d;
        let cy = (s0 * (x1 - xm) + sm * (x0 - x1) + s1 * (xm - x0)) / d;
        let r = (x0 - cx).hypot(y0 - cy);
        let a0 = (y0 - cy).atan2(x0 - cx);
        let a1 = (y1 - cy).atan2(x1 - cx);
        let am = (ym - cy).atan2(xm - cx);
        let ccw_sweep = crate::py_mod(a1 - a0, TAU);
        let ccw_mid = crate::py_mod(am - a0, TAU);
        let sweep = if ccw_mid <= ccw_sweep {
            ccw_sweep
        } else {
            ccw_sweep - TAU
        };
        Self::new(cx, cy, r, a0, sweep)
    }

    pub fn start(&self) -> Pt {
        self.point_at(0.0)
    }

    pub fn end(&self) -> Pt {
        self.point_at(1.0)
    }

    pub fn length(&self) -> f64 {
        self.r * self.sweep.abs()
    }

    pub fn point_at(&self, t: f64) -> Pt {
        let a = self.a0 + self.sweep * t;
        (self.cx + self.r * a.cos(), self.cy + self.r * a.sin())
    }

    pub fn point_at_length(&self, s: f64) -> Pt {
        self.point_at((s / self.length()).clamp(0.0, 1.0))
    }

    /// Направление движения по дуге, радианы.
    pub fn tangent_at(&self, t: f64) -> f64 {
        let a = self.a0 + self.sweep * t;
        a + if self.sweep > 0.0 {
            std::f64::consts::FRAC_PI_2
        } else {
            -std::f64::consts::FRAC_PI_2
        }
    }

    /// Ломаная с прогибом (сагиттой) не более tol.
    pub fn linearize(&self, tol: f64) -> Vec<Pt> {
        let dphi = if tol >= self.r {
            std::f64::consts::FRAC_PI_2
        } else {
            2.0 * (1.0 - tol / self.r).acos()
        };
        let n = 2.0f64.max((self.sweep.abs() / dphi).ceil()) as usize;
        (0..=n).map(|i| self.point_at(i as f64 / n as f64)).collect()
    }

    /// Офсет влево по ходу на d (d < 0 — вправо).
    ///
    /// Для дуги против часовой центр слева — радиус уменьшается.
    pub fn offset(&self, d: f64) -> Result<Self, CurveError> {
        let r_new = if self.sweep > 0.0 { self.r - d } else { self.r + d };
        if r_new <= 0.0 {
            return Err(CurveError(format!(
                "офсет {d} схлопывает дугу радиуса {}",
                self.r
            )));
        }
        Arc::new(self.cx, self.cy, r_new, self.a0, self.sweep)
    }
}

/// Каноническая схема кривой (запись в колонку curve).
///
/// Ломаная в geom — только тесселяция для QGIS.
#[derive(Debug, Clone, PartialEq)]
pub enum CurveSpec {
    Circle { cx: f64, cy: f64, r: f64 },
    Arc { cx: f64, cy: f64, r: f64, a0: f64, sweep: f64 },
    Path { radius: f64, vertices: Vec<Pt> },
}

/// Python `_finite`: число из JSON-значения (число или строка-число).
fn finite(spec: &Value, key: &str, default: Option<f64>) -> Result<f64, CurveError> {
    let raw = match spec.get(key) {
        Some(v) => v.clone(),
        None => match default {
            Some(d) => return Ok(d),
            None => return Err(CurveError(format!("{key} не число"))),
        },
    };
    value_finite(&raw, key)
}

/// Python `_finite` для отдельного значения.
fn value_finite(raw: &Value, name: &str) -> Result<f64, CurveError> {
    let number = match raw {
        Value::Number(n) => n
            .as_f64()
            .ok_or_else(|| CurveError(format!("{name} не число")))?,
        Value::String(s) => s
            .trim()
            .parse::<f64>()
            .map_err(|_| CurveError(format!("{name} не число")))?,
        _ => return Err(CurveError(format!("{name} не число"))),
    };
    if !number.is_finite() {
        return Err(CurveError(format!("{name} не конечное число")));
    }
    Ok(number)
}

/// Python repr для сообщения о неизвестном типе кривой.
fn py_repr(v: &Value) -> String {
    match v {
        Value::Null => "None".into(),
        Value::Bool(b) => format!("{b}"),
        Value::Number(n) => n.to_string(),
        Value::String(s) => format!("'{s}'"),
        Value::Array(_) => "[…]".into(),
        Value::Object(_) => "{…}".into(),
    }
}

/// Каноническая схема кривой: arc, circle или path.
pub fn curve_spec(spec: &Value) -> Result<CurveSpec, CurveError> {
    let obj = match spec {
        Value::Object(o) => o,
        _ => return Err(CurveError("схема кривой — словарь".into())),
    };
    let kind = obj.get("type");
    if kind.and_then(Value::as_str) == Some("circle") {
        let (cx, cy, r) = (
            finite(spec, "cx", None)?,
            finite(spec, "cy", None)?,
            finite(spec, "r", None)?,
        );
        if r <= 0.0 {
            return Err(CurveError("радиус должен быть > 0".into()));
        }
        return Ok(CurveSpec::Circle { cx, cy, r });
    }
    if kind.and_then(Value::as_str) == Some("arc") {
        let (cx, cy) = (finite(spec, "cx", None)?, finite(spec, "cy", None)?);
        let r = finite(spec, "r", None)?;
        let (a0, sweep) = (finite(spec, "a0", None)?, finite(spec, "sweep", None)?);
        Arc::new(cx, cy, r, a0, sweep)?;
        return Ok(CurveSpec::Arc { cx, cy, r, a0, sweep });
    }
    if kind.and_then(Value::as_str) == Some("path") {
        let radius = finite(spec, "radius", Some(0.0))?;
        if radius < 0.0 {
            return Err(CurveError("радиус пути < 0".into()));
        }
        let raw = match spec.get("vertices").and_then(Value::as_array) {
            Some(a) => a,
            None => return Err(CurveError("у пути меньше двух вершин".into())),
        };
        if raw.len() < 2 {
            return Err(CurveError("у пути меньше двух вершин".into()));
        }
        let mut vertices = Vec::with_capacity(raw.len());
        for pt in raw {
            let arr = match pt.as_array() {
                Some(a) if a.len() >= 2 => a,
                _ => return Err(CurveError("вершина пути — пара координат".into())),
            };
            let x = value_finite(&arr[0], "x")?;
            let y = value_finite(&arr[1], "y")?;
            vertices.push((x, y));
        }
        return Ok(CurveSpec::Path { radius, vertices });
    }
    Err(CurveError(format!(
        "неизвестный тип кривой {}",
        py_repr(kind.unwrap_or(&Value::Null))
    )))
}

/// Ломаная по схеме. Допуск — максимальная сагитта, метры.
pub fn tessellate_curve(spec: &Value, tol: f64) -> Result<Vec<Pt>, CurveError> {
    let spec = curve_spec(spec)?;
    if tol <= 0.0 || !tol.is_finite() {
        return Err(CurveError("допуск тесселяции должен быть > 0".into()));
    }
    match spec {
        CurveSpec::Circle { cx, cy, r } => {
            let mut pts = Arc::new(cx, cy, r, 0.0, TAU)?.linearize(tol);
            if pts[0] != pts[pts.len() - 1] {
                pts.push(pts[0]);
            }
            Ok(pts)
        }
        CurveSpec::Arc { cx, cy, r, a0, sweep } => {
            Ok(Arc::new(cx, cy, r, a0, sweep)?.linearize(tol))
        }
        CurveSpec::Path { radius, vertices } => {
            if radius > 0.0 && vertices.len() >= 3 {
                // как в Python: сопряжение, а при PathError — сырые вершины
                match crate::path::Path::fillet_polyline(&vertices, radius) {
                    Ok(p) => return Ok(p.linearize(tol)),
                    Err(crate::path::PathError(_)) => return Ok(vertices),
                }
            }
            Ok(vertices)
        }
    }
}
