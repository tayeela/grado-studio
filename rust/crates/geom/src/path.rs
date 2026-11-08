//! Составной путь: отрезки и дуги. Пикетаж, офсеты, сопряжения.
//!
//! Это геометрия красных линий: полилиния с тангенциальными дугами в углах
//! (fillet), точка на заданном пикете, офсет всей линии. G1-непрерывная цепь
//! (стыки по касательной) офсетится поэлементно и остаётся непрерывной —
//! свойство, на котором держится офсет красных линий с кривыми.
//! Прямой порт `grado_geom/path.py`.

use std::collections::BTreeMap;

use crate::curves::{Arc, CurveError};
use crate::{Pt, TAU};

/// Ошибка пути (Python: PathError, подкласс ValueError).
#[derive(Debug, Clone)]
pub struct PathError(pub String);

impl std::fmt::Display for PathError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for PathError {}

/// Элемент пути: отрезок или дуга.
#[derive(Debug, Clone)]
pub enum PathElement {
    Seg { a: Pt, b: Pt },
    Arc(Arc),
}

/// Составной путь.
#[derive(Debug, Clone)]
pub struct Path {
    pub elements: Vec<PathElement>,
    pub closed: bool,
}

/// Пересечение прямых точка+направление; None для параллельных.
fn line_intersect(p0: Pt, d0: Pt, p1: Pt, d1: Pt) -> Option<Pt> {
    let det = d0.0 * d1.1 - d0.1 * d1.0;
    if det.abs() < 1e-12 {
        return None;
    }
    let t = ((p1.0 - p0.0) * d1.1 - (p1.1 - p0.1) * d1.0) / det;
    Some((p0.0 + d0.0 * t, p0.1 + d0.1 * t))
}

impl Path {
    pub fn new(elements: Vec<PathElement>, closed: bool) -> Result<Self, PathError> {
        if elements.is_empty() {
            return Err(PathError("пустой путь".into()));
        }
        Ok(Path { elements, closed })
    }

    // --- конструкторы ----------------------------------------------------

    pub fn polyline(pts: &[Pt], closed: bool) -> Result<Self, PathError> {
        if pts.len() < 2 {
            return Err(PathError("нужно >= 2 точек".into()));
        }
        let mut elems: Vec<PathElement> = pts
            .windows(2)
            .map(|w| PathElement::Seg { a: w[0], b: w[1] })
            .collect();
        if closed && pts[0] != pts[pts.len() - 1] {
            elems.push(PathElement::Seg {
                a: pts[pts.len() - 1],
                b: pts[0],
            });
        }
        Self::new(elems, closed)
    }

    /// Полилиния с тангенциальными дугами в углах (сопряжение).
    ///
    /// Классика красных линий: прямые участки + скругления радиусом R.
    pub fn fillet_polyline(pts: &[Pt], radius: f64) -> Result<Self, PathError> {
        if pts.len() < 3 {
            return Self::polyline(pts, false);
        }
        let mut elems = Vec::new();
        let mut cur = pts[0];
        for w in pts.windows(3) {
            let (prev, v, nxt) = (w[0], w[1], w[2]);
            let v1 = (v.0 - prev.0, v.1 - prev.1);
            let v2 = (nxt.0 - v.0, nxt.1 - v.1);
            // Python: деление на ноль здесь даёт ZeroDivisionError; здесь —
            // PathError (задокументированное отличие).
            if v1.0.hypot(v1.1) == 0.0 || v2.0.hypot(v2.1) == 0.0 {
                return Err(PathError(format!("нулевая длина отрезка в вершине {v:?}")));
            }
            let l1 = v1.0.hypot(v1.1);
            let l2 = v2.0.hypot(v2.1);
            let u1 = (v1.0 / l1, v1.1 / l1);
            let u2 = (v2.0 / l2, v2.1 / l2);
            let cross = u1.0 * u2.1 - u1.1 * u2.0;
            let dot = u1.0 * u2.0 + u1.1 * u2.1;
            let theta = std::f64::consts::PI - cross.abs().atan2(dot); // внутренний угол
            if cross.abs() < 1e-9 {
                continue; // прямой участок без излома
            }
            let t = radius / (theta / 2.0).tan();
            if t > l1 - 1e-9 || t > l2 - 1e-9 {
                return Err(PathError(format!(
                    "радиус {radius} не помещается в вершине ({}, {})",
                    v.0, v.1
                )));
            }
            let tp1 = (v.0 - u1.0 * t, v.1 - u1.1 * t); // точка схода с первой прямой
            let tp2 = (v.0 + u2.0 * t, v.1 + u2.1 * t); // точка входа на вторую
            // центр — на биссектрисе, на расстоянии r от обеих прямых
            let n1 = if cross > 0.0 { (-u1.1, u1.0) } else { (u1.1, -u1.0) };
            let cx = tp1.0 + n1.0 * radius;
            let cy = tp1.1 + n1.1 * radius;
            let a0 = (tp1.1 - cy).atan2(tp1.0 - cx);
            let a1 = (tp2.1 - cy).atan2(tp2.0 - cx);
            let sweep = if cross > 0.0 {
                crate::py_mod(a1 - a0, TAU)
            } else {
                crate::py_mod(a1 - a0, TAU) - TAU
            };
            elems.push(PathElement::Seg { a: cur, b: tp1 });
            elems.push(PathElement::Arc(Arc::new(cx, cy, radius, a0, sweep).map_err(
                |CurveError(m)| PathError(m),
            )?));
            cur = tp2;
        }
        elems.push(PathElement::Seg {
            a: cur,
            b: pts[pts.len() - 1],
        });
        Self::new(elems, false)
    }

    // --- базовые свойства -------------------------------------------------

    fn elem_len(e: &PathElement) -> f64 {
        match e {
            PathElement::Seg { a, b } => (b.0 - a.0).hypot(b.1 - a.1),
            PathElement::Arc(arc) => arc.length(),
        }
    }

    pub fn length(&self) -> f64 {
        self.elements.iter().map(Self::elem_len).sum()
    }

    pub fn linearize(&self, tol: f64) -> Vec<Pt> {
        let mut pts: Vec<Pt> = Vec::new();
        for e in &self.elements {
            let mut chunk: Vec<Pt> = match e {
                PathElement::Seg { a, b } => vec![*a, *b],
                PathElement::Arc(arc) => arc.linearize(tol),
            };
            if let Some(&last) = pts.last() {
                if last == chunk[0] {
                    chunk.remove(0);
                }
            }
            pts.extend(chunk);
        }
        pts
    }

    pub fn area(&self, tol: f64) -> f64 {
        let pts = self.linearize(tol);
        let mut s = 0.0;
        for i in 0..pts.len() {
            let (x1, y1) = pts[i];
            let (x2, y2) = pts[(i + 1) % pts.len()];
            s += x1 * y2 - x2 * y1;
        }
        s.abs() / 2.0
    }

    // --- пикетаж ----------------------------------------------------------

    /// Точка и касательная (рад) на пикете s от начала пути.
    pub fn point_at_station(&self, s: f64) -> Result<(Pt, f64), PathError> {
        let mut s = s.max(0.0);
        let last = self.elements.len() - 1;
        for (i, e) in self.elements.iter().enumerate() {
            let el = Self::elem_len(e);
            if s <= el || i == last {
                if el == 0.0 {
                    // Python здесь падает с ZeroDivisionError; здесь — ошибка пути
                    return Err(PathError("нулевой элемент пути".into()));
                }
                let t = (s / el).min(1.0);
                return match e {
                    PathElement::Seg { a, b } => {
                        let (x0, y0) = *a;
                        let (x1, y1) = *b;
                        Ok((
                            (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t),
                            (y1 - y0).atan2(x1 - x0),
                        ))
                    }
                    PathElement::Arc(arc) => Ok((arc.point_at(t), arc.tangent_at(t))),
                };
            }
            s -= el;
        }
        Err(PathError("пустой путь".into()))
    }

    /// Точки пикетажа через step метров: [(ПК, точка)].
    pub fn stations(&self, step: f64) -> Result<Vec<(f64, Pt)>, PathError> {
        if step <= 0.0 || !step.is_finite() {
            // Python зациклился бы; здесь — ошибка пути
            return Err(PathError("шаг пикетажа должен быть > 0".into()));
        }
        let total = self.length();
        let mut out = Vec::new();
        let mut s = 0.0;
        while s < total - 1e-9 {
            out.push((s, self.point_at_station(s)?.0));
            s += step;
        }
        out.push((total, self.point_at_station(total)?.0));
        Ok(out)
    }

    // --- офсет -------------------------------------------------------------

    fn tangents(e: &PathElement) -> (f64, f64) {
        match e {
            PathElement::Seg { a, b } => {
                let ang = (b.1 - a.1).atan2(b.0 - a.0);
                (ang, ang)
            }
            PathElement::Arc(arc) => (arc.tangent_at(0.0), arc.tangent_at(1.0)),
        }
    }

    fn ends(e: &PathElement) -> (Pt, Pt) {
        match e {
            PathElement::Seg { a, b } => (*a, *b),
            PathElement::Arc(arc) => (arc.start(), arc.end()),
        }
    }

    pub fn is_g1(&self, tol: f64) -> bool {
        for w in self.elements.windows(2) {
            let (a, b) = (Self::ends(&w[0]).1, Self::ends(&w[1]).0);
            if (b.0 - a.0).hypot(b.1 - a.1) > tol {
                return false;
            }
            let da = crate::py_mod(Self::tangents(&w[1]).0 - Self::tangents(&w[0]).1, TAU);
            if da.min(TAU - da) > tol {
                return false;
            }
        }
        true
    }

    fn offset_seg(e: &PathElement, d: f64) -> Result<PathElement, PathError> {
        let (a, b) = match e {
            PathElement::Seg { a, b } => (*a, *b),
            PathElement::Arc(_) => return Err(PathError("не отрезок".into())),
        };
        let length = (b.0 - a.0).hypot(b.1 - a.1);
        if length == 0.0 {
            // Python: ZeroDivisionError; здесь — ошибка пути
            return Err(PathError("нулевой отрезок".into()));
        }
        let (nx, ny) = (-(b.1 - a.1) / length * d, (b.0 - a.0) / length * d);
        Ok(PathElement::Seg {
            a: (a.0 + nx, a.1 + ny),
            b: (b.0 + nx, b.1 + ny),
        })
    }

    /// Офсет влево по ходу на d. G1-цепь — поэлементно; ломаная — со
    /// стыковкой соседних офсетов по пересечению (miter).
    pub fn offset(&self, d: f64) -> Result<Self, PathError> {
        let all_segs = self
            .elements
            .iter()
            .all(|e| matches!(e, PathElement::Seg { .. }));
        let g1 = self.is_g1(1e-6);
        if all_segs && !g1 {
            return self.offset_miter(d);
        }
        if !g1 {
            return Err(PathError("офсет цепи с дугами требует G1-непрерывности".into()));
        }
        let mut out = Vec::with_capacity(self.elements.len());
        for e in &self.elements {
            match e {
                PathElement::Seg { .. } => out.push(Self::offset_seg(e, d)?),
                PathElement::Arc(arc) => {
                    out.push(PathElement::Arc(arc.offset(d).map_err(|CurveError(m)| PathError(m))?))
                }
            }
        }
        Self::new(out, self.closed)
    }

    fn offset_miter(&self, d: f64) -> Result<Self, PathError> {
        let mut segs = Vec::with_capacity(self.elements.len());
        for e in &self.elements {
            segs.push(match Self::offset_seg(e, d)? {
                PathElement::Seg { a, b } => (a, b),
                PathElement::Arc(_) => unreachable!(),
            });
        }
        let n = segs.len();
        let mut joints: BTreeMap<usize, Pt> = BTreeMap::new();
        let pairs: Vec<usize> = (0..n - 1).chain(if self.closed { vec![n - 1] } else { vec![] }).collect();
        for i in pairs {
            let a = segs[i];
            let b = segs[(i + 1) % n];
            let da = (a.1 .0 - a.0 .0, a.1 .1 - a.0 .1);
            let db = (b.1 .0 - b.0 .0, b.1 .1 - b.0 .1);
            let p = line_intersect(a.0, da, b.0, db);
            joints.insert(i, p.unwrap_or(a.1));
        }
        let mut out = Vec::with_capacity(n);
        for (i, s) in segs.iter().enumerate() {
            let prev = (i + n - 1) % n;
            let start = if (i > 0 || self.closed) && joints.contains_key(&prev) {
                joints[&prev]
            } else {
                s.0
            };
            let end = match joints.get(&i) {
                Some(p) => *p,
                None => s.1,
            };
            out.push(PathElement::Seg { a: start, b: end });
        }
        Self::new(out, self.closed)
    }
}
