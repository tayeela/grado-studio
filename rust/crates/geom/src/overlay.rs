//! Площадь объединения полигонов внутри объединения других полигонов.
//!
//! Нужна ТЭП и доле районов: сколько площади ограничений лежит внутри границы
//! территории. Ограничения перекрываются (зоны охраны ОКН вложены друг в
//! друга), бывают дублями и выходят за границу — простая сумма площадей даёт
//! неверный ответ.
//!
//! Python-эталон считает shapely 2 (GEOS): `make_valid` чинит кольца,
//! `union_all`/`intersection` — площади. Здесь тот же результат даёт теорема
//! Грина по нодированным рёбрам: все кольца вместе делятся во всех
//! пересечениях (подребро не пересекает границ, статус «внутри» вдоль него
//! постоянен), для каждого подребра статус вычисляется слева и справа
//! (чётность точки по каждому кольцу — PNPOLY; внутренность полигона —
//! внешнее кольцо нечётно, дыры чётны, «правило чётности», как у GEOS
//! make_valid; объединение группы — ИЛИ по её полигонам, дубли не гасятся).
//! Подребро — кусок границы области, когда статусы сторон разные: внутри
//! слева — вклад +½(x₁y₂−x₂y₁), внутри справа — минус. Сумма вкладов и есть
//! площадь. Порядок обхода и совпадающие границы на результат не влияют.
//!
//! Точность — f64 без квантования: точка пересечения считается один раз на
//! пару рёбер и попадает в оба.

use std::collections::BTreeMap;

use crate::{ord_pt, OrdPt, Pt};

/// Полигон — список колец (первое внешнее, остальные дыры; порядок обхода
/// не важен).
pub type Poly = Vec<Vec<Pt>>;

/// Кольцо годно: >= 3 точек, все конечны (кольцо с NaN/∞ пропускается —
/// GEOS на нём падает, прежний метод давал ему нулевую площадь).
fn ring_is_usable(ring: &[Pt]) -> bool {
    ring.len() >= 3 && ring.iter().all(|p| p.0.is_finite() && p.1.is_finite())
}

/// Рёбра одного кольца (по кругу, без нулевых).
fn ring_edges(ring: &[Pt]) -> Vec<(Pt, Pt)> {
    let mut edges = Vec::new();
    for i in 0..ring.len() {
        let a = ring[i];
        let b = ring[(i + 1) % ring.len()];
        if a != b {
            edges.push((a, b));
        }
    }
    edges
}

/// Точки деления на каждом рёбре от парных пересечений; концы рёбер — тоже
/// узлы. Точка считается один раз на пару рёбер и вставляется в оба.
fn noded_splits(edges: &[(Pt, Pt)]) -> Vec<Vec<(f64, Pt)>> {
    let n = edges.len();
    let mut splits: Vec<Vec<(f64, Pt)>> = vec![Vec::new(); n];
    let eps = 1e-12;

    for i in 0..n {
        for j in i + 1..n {
            let (p, q) = edges[i];
            let (r, s) = edges[j];
            let d0 = (q.0 - p.0, q.1 - p.1);
            let d1 = (s.0 - r.0, s.1 - r.1);
            let det = d0.0 * d1.1 - d0.1 * d1.0;
            if det.abs() >= eps {
                // собственное пересечение прямых
                let t = ((r.0 - p.0) * d1.1 - (r.1 - p.1) * d1.0) / det;
                let u = ((r.0 - p.0) * d0.1 - (r.1 - p.1) * d0.0) / det;
                if t >= -eps && t <= 1.0 + eps && u >= -eps && u <= 1.0 + eps {
                    let tc = t.clamp(0.0, 1.0);
                    let uc = u.clamp(0.0, 1.0);
                    let pt = (p.0 + d0.0 * tc, p.1 + d0.1 * tc);
                    splits[i].push((tc, pt));
                    splits[j].push((uc, pt));
                }
                continue;
            }
            // параллельны; коллинеарны ли?
            let cross = (r.0 - p.0) * d0.1 - (r.1 - p.1) * d0.0;
            if cross.abs() > eps {
                continue;
            }
            // коллинеарны: перекрытие в параметрах ребра i
            let len2 = d0.0 * d0.0 + d0.1 * d0.1;
            if len2 == 0.0 {
                continue;
            }
            let sr = ((r.0 - p.0) * d0.0 + (r.1 - p.1) * d0.1) / len2;
            let ss = ((s.0 - p.0) * d0.0 + (s.1 - p.1) * d0.1) / len2;
            let (lo, hi) = (sr.min(ss).max(0.0), sr.max(ss).min(1.0));
            if hi < lo {
                continue;
            }
            let len1 = d1.0 * d1.0 + d1.1 * d1.1;
            if len1 == 0.0 {
                continue;
            }
            let params: Vec<f64> = if hi - lo <= eps {
                vec![(lo + hi) / 2.0] // касание в одной точке
            } else {
                vec![lo, hi] // перекрытие отрезком: делим оба ребра в обоих концах
            };
            for tc in params {
                let pt = (p.0 + d0.0 * tc, p.1 + d0.1 * tc);
                let u = ((pt.0 - r.0) * d1.0 + (pt.1 - r.1) * d1.1) / len1;
                let uc = u.clamp(0.0, 1.0);
                splits[i].push((tc, pt));
                splits[j].push((uc, pt));
            }
        }
    }

    // концы рёбер — тоже узлы; сортировка по t; близкие параметры (щель
    // ~1e-12 длины) склеиваются, чтобы не плодить вырожденные подребра
    for (i, list) in splits.iter_mut().enumerate() {
        let (a, b) = edges[i];
        list.push((0.0, a));
        list.push((1.0, b));
        list.sort_by(|a, b| a.0.total_cmp(&b.0));
        let mut merged: Vec<(f64, Pt)> = Vec::with_capacity(list.len());
        for &(t, pt) in list.iter() {
            match merged.last() {
                Some(&(t0, _)) if t - t0 < 1e-12 => {}
                _ => merged.push((t, pt)),
            }
        }
        *list = merged;
    }
    splits
}

/// Чётность точки относительно кольца (PNPOLY, полураскрытый интервал по y —
/// вершины обрабатываются единообразно).
fn point_in_ring(p: Pt, ring: &[Pt]) -> bool {
    let (px, py) = p;
    let mut inside = false;
    let n = ring.len();
    for i in 0..n {
        let (xi, yi) = ring[i];
        let (xj, yj) = ring[(i + 1) % n];
        if (yi > py) != (yj > py) && px < (xj - xi) * (py - yi) / (yj - yi) + xi {
            inside = !inside;
        }
    }
    inside
}

/// Внутренность полигона: внешнее кольцо нечётно и дыры чётны.
fn point_in_poly(p: Pt, shell: &[Pt], holes: &[&[Pt]]) -> bool {
    if !point_in_ring(p, shell) {
        return false;
    }
    holes.iter().all(|h| !point_in_ring(p, h))
}

/// Площадь (∪ regions) ∩ (∪ clips) в единицах координат².
///
/// max_rows, min_step прежнего приближённого метода не переносятся —
/// в Python-эталоне они не используются.
pub fn union_intersection_area(regions: &[Poly], clips: &[Poly]) -> f64 {
    // выжившие полигоны: (внешнее кольцо, дыры); пустые и вырожденные отпадают
    let mut group_polys: [Vec<(Vec<Pt>, Vec<Vec<Pt>>)>; 2] = [Vec::new(), Vec::new()];
    for (group, group_polygons) in [(0usize, regions), (1usize, clips)] {
        for poly in group_polygons {
            let usable: Vec<&Vec<Pt>> = poly.iter().filter(|r| ring_is_usable(r)).collect();
            if usable.is_empty() {
                continue;
            }
            let shell = usable[0].clone();
            let holes: Vec<Vec<Pt>> = usable[1..].iter().map(|r| (*r).clone()).collect();
            group_polys[group].push((shell, holes));
        }
    }
    if group_polys[0].is_empty() || group_polys[1].is_empty() {
        return 0.0;
    }

    // все рёбра всех колец; нодинг делит их во всех пересечениях
    let mut edges: Vec<(Pt, Pt)> = Vec::new();
    for polys in &group_polys {
        for (shell, holes) in polys {
            for e in ring_edges(shell) {
                edges.push(e);
            }
            for hole in holes {
                for e in ring_edges(hole) {
                    edges.push(e);
                }
            }
        }
    }
    if edges.is_empty() {
        return 0.0;
    }
    let splits = noded_splits(&edges);

    // масштаб сцены для отступа статус-точек от ребра
    let mut min = (f64::INFINITY, f64::INFINITY);
    let mut max = (f64::NEG_INFINITY, f64::NEG_INFINITY);
    for &(a, b) in &edges {
        for p in [a, b] {
            min.0 = min.0.min(p.0);
            min.1 = min.1.min(p.1);
            max.0 = max.0.max(p.0);
            max.1 = max.1.max(p.1);
        }
    }
    let diag = (max.0 - min.0).hypot(max.1 - min.1);
    let eps = 1e-7 * diag.max(1.0);

    let inside_group = |group: usize, p: Pt| -> bool {
        group_polys[group].iter().any(|(shell, holes)| {
            let hole_refs: Vec<&[Pt]> = holes.iter().map(|h| h.as_slice()).collect();
            point_in_poly(p, shell, &hole_refs)
        })
    };

    // уникальные подребра: совпадающие (общие границы, дубли) схлопываются —
    // статус точки от копии не зависит, вклад границы считается один раз
    let mut unique: BTreeMap<(OrdPt, OrdPt), (Pt, Pt)> = BTreeMap::new();
    for list in &splits {
        for w in list.windows(2) {
            let (a, b) = (w[0].1, w[1].1);
            if a == b {
                continue;
            }
            let (p1, p2) = if a < b { (a, b) } else { (b, a) };
            unique.entry((ord_pt(p1), ord_pt(p2))).or_insert((p1, p2));
        }
    }

    // теорема Грина: вклад подребра — когда статус «внутри области» на его
    // сторонах разный; ориентация границы — внутренность слева
    let mut total = 0.0;
    for (_, (p1, p2)) in &unique {
        let d = (p2.0 - p1.0, p2.1 - p1.1);
        let len = d.0.hypot(d.1);
        if len == 0.0 {
            continue;
        }
        let mid = ((p1.0 + p2.0) / 2.0, (p1.1 + p2.1) / 2.0);
        let n = (-d.1 / len, d.0 / len); // левая нормаль по ходу p1 -> p2
        let left = (mid.0 + n.0 * eps, mid.1 + n.1 * eps);
        let right = (mid.0 - n.0 * eps, mid.1 - n.1 * eps);
        let sl = inside_group(0, left) && inside_group(1, left);
        let sr = inside_group(0, right) && inside_group(1, right);
        if sl == sr {
            continue; // не граница области
        }
        let cross = 0.5 * (p1.0 * p2.1 - p2.0 * p1.1);
        total += if sl { cross } else { -cross };
    }
    total
}
