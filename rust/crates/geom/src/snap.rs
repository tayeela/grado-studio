//! Движок привязок: конец / пересечение / середина / ближайшая точка.
//!
//! Приоритет как в CAD: точная характеристическая точка бьёт «ближайшую».
//! Кандидаты в допуске сортируются по (приоритет, дистанция). Поиск отрезков
//! рядом с курсором — пространственный индекс (R-дерево rstar вместо STRtree
//! shapely 2); пересечения и ближайшая точка — своя аналитика вместо GEOS.
//! Пересечение в допуске лежит на двух отрезках, каждый из которых сам в
//! допуске, поэтому пары перебираются только среди найденных рядом.
//! Порт `grado_geom/snap.py`.

use rstar::{RTree, AABB};

use crate::Pt;

pub const PRIORITY_ENDPOINT: u8 = 0;
pub const PRIORITY_INTERSECTION: u8 = 1;
pub const PRIORITY_MIDPOINT: u8 = 2;
pub const PRIORITY_NEAREST: u8 = 3;

/// Вид характеристической точки (Python: строковые метки).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SnapKind {
    Endpoint,
    Intersection,
    Midpoint,
    Nearest,
}

impl SnapKind {
    pub fn priority(self) -> u8 {
        match self {
            SnapKind::Endpoint => PRIORITY_ENDPOINT,
            SnapKind::Intersection => PRIORITY_INTERSECTION,
            SnapKind::Midpoint => PRIORITY_MIDPOINT,
            SnapKind::Nearest => PRIORITY_NEAREST,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            SnapKind::Endpoint => "endpoint",
            SnapKind::Intersection => "intersection",
            SnapKind::Midpoint => "midpoint",
            SnapKind::Nearest => "nearest",
        }
    }
}

/// Результат привязки: точка, вид, дистанция до курсора.
#[derive(Debug, Clone, PartialEq)]
pub struct SnapResult {
    pub point: Pt,
    pub kind: SnapKind,
    pub dist: f64,
}

/// Элемент R-дерева: bbox отрезка + его индекс.
struct SegItem {
    idx: usize,
    env: AABB<[f64; 2]>,
}

impl rstar::RTreeObject for SegItem {
    type Envelope = AABB<[f64; 2]>;

    fn envelope(&self) -> Self::Envelope {
        self.env
    }
}

/// Точка пересечения отрезков, если она одна (как GEOS, возвращающий Point:
/// собственное пересечение или касание в одной точке; перекрытие —
/// LineString — точки не даёт).
fn seg_seg_point(a: (Pt, Pt), b: (Pt, Pt)) -> Option<Pt> {
    let (a1, a2) = a;
    let (b1, b2) = b;
    let d0 = (a2.0 - a1.0, a2.1 - a1.1);
    let d1 = (b2.0 - b1.0, b2.1 - b1.1);
    let det = d0.0 * d1.1 - d0.1 * d1.0;
    let eps = 1e-12;
    if det.abs() >= eps {
        let t = ((b1.0 - a1.0) * d1.1 - (b1.1 - a1.1) * d1.0) / det;
        let u = ((b1.0 - a1.0) * d0.1 - (b1.1 - a1.1) * d0.0) / det;
        if t >= -eps && t <= 1.0 + eps && u >= -eps && u <= 1.0 + eps {
            let tc = t.clamp(0.0, 1.0);
            return Some((a1.0 + d0.0 * tc, a1.1 + d0.1 * tc));
        }
        return None;
    }
    // параллельны; коллинеарны ли?
    let cross = (b1.0 - a1.0) * d0.1 - (b1.1 - a1.1) * d0.0;
    if cross.abs() > eps {
        return None;
    }
    // коллинеарны: касание в одной точке или перекрытие
    let len2 = d0.0 * d0.0 + d0.1 * d0.1;
    if len2 == 0.0 {
        return None;
    }
    let sr = ((b1.0 - a1.0) * d0.0 + (b1.1 - a1.1) * d0.1) / len2;
    let ss = ((b2.0 - a1.0) * d0.0 + (b2.1 - a1.1) * d0.1) / len2;
    let lo = sr.min(ss).max(0.0);
    let hi = sr.max(ss).min(1.0);
    if hi < lo {
        return None;
    }
    if hi - lo <= eps {
        let t = (lo + hi) / 2.0;
        return Some((a1.0 + d0.0 * t, a1.1 + d0.1 * t));
    }
    None // перекрытие: у GEOS это LineString, точки пересечения нет
}

/// Ближайшая точка отрезка к p (как line.interpolate(line.project(p))).
fn nearest_on_segment(p: Pt, a: Pt, b: Pt) -> Pt {
    let d = (b.0 - a.0, b.1 - a.1);
    let len2 = d.0 * d.0 + d.1 * d.1;
    if len2 == 0.0 {
        return a;
    }
    let t = (((p.0 - a.0) * d.0 + (p.1 - a.1) * d.1) / len2).clamp(0.0, 1.0);
    (a.0 + d.0 * t, a.1 + d.1 * t)
}

/// Движок привязок.
pub struct Snapper {
    pub tolerance: f64,
    /// Шаг прежней сетки-индекса; оставлен для совместимости вызовов,
    /// индекс теперь R-дерево.
    pub cell: Option<f64>,
    segments: Vec<(Pt, Pt)>,
    tree: Option<RTree<SegItem>>,
}

impl Snapper {
    pub fn new(tolerance: f64) -> Self {
        Snapper {
            tolerance,
            cell: None,
            segments: Vec::new(),
            tree: None,
        }
    }

    pub fn add_segment(&mut self, a: Pt, b: Pt) {
        let env = AABB::from_corners(
            [a.0.min(b.0), a.1.min(b.1)],
            [a.0.max(b.0), a.1.max(b.1)],
        );
        self.segments.push((a, b));
        self.tree
            .get_or_insert_with(RTree::new)
            .insert(SegItem {
                idx: self.segments.len() - 1,
                env,
            });
    }

    pub fn add_polyline(&mut self, pts: &[Pt]) {
        for w in pts.windows(2) {
            self.add_segment(w[0], w[1]);
        }
    }

    /// Индексы отрезков рядом с точкой (по bbox в допуске — надмножество
    /// точного dwithin; лишние отсеются финальным фильтром дистанции),
    /// по возрастанию индекса, как в Python.
    fn near(&self, p: Pt) -> Vec<usize> {
        if self.segments.is_empty() {
            return Vec::new();
        }
        let t = self.tolerance;
        let env = AABB::from_corners([p.0 - t, p.1 - t], [p.0 + t, p.1 + t]);
        let mut idx: Vec<usize> = self
            .tree
            .as_ref()
            .expect("дерево построено при добавлении")
            .locate_in_envelope_intersecting(env)
            .map(|item| item.idx)
            .collect();
        idx.sort_unstable();
        idx
    }

    /// Привязка курсора: лучшая характеристическая точка в допуске.
    pub fn snap(&self, x: f64, y: f64) -> Option<SnapResult> {
        let near = self.near((x, y));
        let mut candidates: Vec<(Pt, SnapKind)> = Vec::new();
        for &idx in &near {
            let (a, b) = self.segments[idx];
            candidates.push((a, SnapKind::Endpoint));
            candidates.push((b, SnapKind::Endpoint));
            candidates.push((((a.0 + b.0) / 2.0, (a.1 + b.1) / 2.0), SnapKind::Midpoint));
            let q = if a != b { nearest_on_segment((x, y), a, b) } else { a };
            candidates.push((q, SnapKind::Nearest));
        }
        for i in 0..near.len() {
            for j in i + 1..near.len() {
                // совпадающие (коллинеарные) отрезки точки пересечения не дают
                if let Some(hit) = seg_seg_point(self.segments[near[i]], self.segments[near[j]]) {
                    candidates.push((hit, SnapKind::Intersection));
                }
            }
        }

        let mut best: Option<SnapResult> = None;
        for (pt, kind) in candidates {
            let dist = (x - pt.0).hypot(y - pt.1);
            if dist > self.tolerance {
                continue;
            }
            let better = match &best {
                None => true,
                // кортеж (приоритет, дистанция), строго меньше — первый в ties
                Some(b) => (kind.priority(), dist) < (b.kind.priority(), b.dist),
            };
            if better {
                best = Some(SnapResult { point: pt, kind, dist });
            }
        }
        best
    }
}
