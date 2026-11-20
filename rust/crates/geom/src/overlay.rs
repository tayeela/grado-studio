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

use crate::Pt;

/// Полигон — список колец (первое внешнее, остальные дыры; порядок обхода
/// не важен).
pub type Poly = Vec<Vec<Pt>>;

/// Кольцо годно: >= 3 точек, все конечны (кольцо с NaN/∞ пропускается —
/// GEOS на нём падает, прежний метод давал ему нулевую площадь).
fn ring_is_usable(ring: &[Pt]) -> bool {
    ring.len() >= 3 && ring.iter().all(|p| p.0.is_finite() && p.1.is_finite())
}

/// Габарит кольца или набора точек: (min_x, min_y, max_x, max_y).
type BBox = (f64, f64, f64, f64);

fn ring_bbox(ring: &[Pt]) -> BBox {
    let mut b = (f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY);
    for &(x, y) in ring {
        b.0 = b.0.min(x);
        b.1 = b.1.min(y);
        b.2 = b.2.max(x);
        b.3 = b.3.max(y);
    }
    b
}

fn bbox_union(a: BBox, b: BBox) -> BBox {
    (a.0.min(b.0), a.1.min(b.1), a.2.max(b.2), a.3.max(b.3))
}

fn bbox_inter(a: BBox, b: BBox) -> Option<BBox> {
    let r = (a.0.max(b.0), a.1.max(b.1), a.2.min(b.2), a.3.min(b.3));
    if r.0 <= r.2 && r.1 <= r.3 {
        Some(r)
    } else {
        None
    }
}

fn bbox_overlaps(a: BBox, b: BBox, pad: f64) -> bool {
    a.2 + pad >= b.0 && a.0 - pad <= b.2 && a.3 + pad >= b.1 && a.1 - pad <= b.3
}

/// Рёбра одного кольца (по кругу, без нулевых), пересекающие габарит области `clip` с запасом `pad`.
fn ring_edges_in(ring: &[Pt], clip: BBox, pad: f64) -> Vec<(Pt, Pt)> {
    let mut edges = Vec::new();
    for i in 0..ring.len() {
        let a = ring[i];
        let b = ring[(i + 1) % ring.len()];
        if a != b {
            let eb = (a.0.min(b.0), a.1.min(b.1), a.0.max(b.0), a.1.max(b.1));
            if bbox_overlaps(eb, clip, pad) {
                edges.push((a, b));
            }
        }
    }
    edges
}

/// Точки деления на каждом рёбре от парных пересечений; концы рёбер — тоже
/// узлы. Точка считается один раз на пару рёбер и вставляется в оба.
fn noded_splits(edges: &[(Pt, Pt)], tol: f64) -> Vec<Vec<(f64, Pt)>> {
    let n = edges.len();
    let mut splits: Vec<Vec<(f64, Pt)>> = vec![Vec::new(); n];
    let eps = 1e-12;
    let boxes: Vec<BBox> = edges
        .iter()
        .map(|&(a, b)| (a.0.min(b.0), a.1.min(b.1), a.0.max(b.0), a.1.max(b.1)))
        .collect();

    for i in 0..n {
        let bi = boxes[i];
        for j in i + 1..n {
            if !bbox_overlaps(bi, boxes[j], tol) {
                continue;
            }
            let (p, q) = edges[i];
            let (r, s) = edges[j];
            let d0 = (q.0 - p.0, q.1 - p.1);
            let d1 = (s.0 - r.0, s.1 - r.1);
            let len2 = d0.0 * d0.0 + d0.1 * d0.1;
            let len1 = d1.0 * d1.0 + d1.1 * d1.1;
            if len2 == 0.0 || len1 == 0.0 {
                continue;
            }
            let l0 = len2.sqrt();
            let l1 = len1.sqrt();
            let det = d0.0 * d1.1 - d0.1 * d1.0;
            // почти параллельные рёбра (угол < 1e-7 рад) проверяем на коллинеарное перекрытие в допуске tol
            if det.abs() >= 1e-7 * l0 * l1 {
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
            // параллельны; коллинеарны ли в пределах допуска tol?
            let cross = (r.0 - p.0) * d0.1 - (r.1 - p.1) * d0.0;
            if cross.abs() > tol * l0 {
                continue;
            }
            // коллинеарны: перекрытие в параметрах ребра i
            let sr = ((r.0 - p.0) * d0.0 + (r.1 - p.1) * d0.1) / len2;
            let ss = ((s.0 - p.0) * d0.0 + (s.1 - p.1) * d0.1) / len2;
            let (lo, hi) = (sr.min(ss).max(0.0), sr.max(ss).min(1.0));
            if hi < lo - eps {
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

/// Площадь (∪ regions) ∩ (∪ clips) в единицах координат².
///
/// max_rows, min_step прежнего приближённого метода не переносятся —
/// в Python-эталоне они не используются.
pub fn union_intersection_area(regions: &[Poly], clips: &[Poly]) -> f64 {
    // выжившие полигоны: (габарит внешнего кольца, внешнее кольцо, дыры); пустые и вырожденные отпадают
    let mut raw_polys: [Vec<(BBox, Vec<Pt>, Vec<(BBox, Vec<Pt>)>)>; 2] = [Vec::new(), Vec::new()];
    let mut group_box = [
        (f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY),
        (f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY),
    ];
    for (group, group_polygons) in [(0usize, regions), (1usize, clips)] {
        for poly in group_polygons {
            let usable: Vec<&Vec<Pt>> = poly.iter().filter(|r| ring_is_usable(r)).collect();
            if usable.is_empty() {
                continue;
            }
            let shell = usable[0].clone();
            let sb = ring_bbox(&shell);
            group_box[group] = bbox_union(group_box[group], sb);
            let holes: Vec<(BBox, Vec<Pt>)> = usable[1..]
                .iter()
                .map(|r| {
                    let h = (*r).clone();
                    (ring_bbox(&h), h)
                })
                .collect();
            raw_polys[group].push((sb, shell, holes));
        }
    }
    if raw_polys[0].is_empty() || raw_polys[1].is_empty() {
        return 0.0;
    }
    let Some(clip_box) = bbox_inter(group_box[0], group_box[1]) else {
        return 0.0;
    };

    // масштаб области пересечения для отступа статус-точек от ребра
    let diag = (clip_box.2 - clip_box.0).hypot(clip_box.3 - clip_box.1);
    let eps = 1e-7 * diag.max(1e-6);
    let tol = 0.5 * eps;
    let pad = 4.0 * eps;

    // полигоны, чей габарит не пересекает общий габарит, не могут ни содержать точек пересечения, ни давать рёбер границы
    let [raw0, raw1] = raw_polys;
    let group_polys: [Vec<(BBox, Vec<Pt>, Vec<(BBox, Vec<Pt>)>)>; 2] = [
        raw0.into_iter()
            .filter(|(b, _, _)| bbox_overlaps(*b, clip_box, pad))
            .collect(),
        raw1.into_iter()
            .filter(|(b, _, _)| bbox_overlaps(*b, clip_box, pad))
            .collect(),
    ];
    if group_polys[0].is_empty() || group_polys[1].is_empty() {
        return 0.0;
    }

    // рёбра колец внутри области пересечения; нодинг делит их во всех пересечениях
    let mut edges: Vec<(Pt, Pt)> = Vec::new();
    for polys in &group_polys {
        for (_, shell, holes) in polys {
            for e in ring_edges_in(shell, clip_box, pad) {
                edges.push(e);
            }
            for (_, hole) in holes {
                for e in ring_edges_in(hole, clip_box, pad) {
                    edges.push(e);
                }
            }
        }
    }
    let splits = noded_splits(&edges, tol);

    let inside_group = |group: usize, p: Pt| -> bool {
        group_polys[group].iter().any(|(sb, shell, holes)| {
            if p.0 < sb.0 || p.0 > sb.2 || p.1 < sb.1 || p.1 > sb.3 {
                return false;
            }
            if !point_in_ring(p, shell) {
                return false;
            }
            holes.iter().all(|(hb, h)| {
                p.0 < hb.0 || p.0 > hb.2 || p.1 < hb.1 || p.1 > hb.3 || !point_in_ring(p, h)
            })
        })
    };

    // уникальные подребра: совпадающие в пределах tol (общие границы, дубли после перевода координат)
    // схлопываются — статус точки на расстоянии eps от копии не зависит, вклад границы считается один раз
    let q_pt = |p: Pt| -> (i64, i64) { ((p.0 / tol).round() as i64, (p.1 / tol).round() as i64) };
    let mut unique: BTreeMap<((i64, i64), (i64, i64)), (Pt, Pt)> = BTreeMap::new();
    for list in &splits {
        for w in list.windows(2) {
            let (a, b) = (w[0].1, w[1].1);
            let (qa, qb) = (q_pt(a), q_pt(b));
            if qa == qb {
                continue;
            }
            let (key, pair) = if qa < qb { ((qa, qb), (a, b)) } else { ((qb, qa), (b, a)) };
            unique.entry(key).or_insert(pair);
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
        let step = eps.min(0.25 * len);
        let n = (-d.1 / len, d.0 / len); // левая нормаль по ходу p1 -> p2
        let left = (mid.0 + n.0 * step, mid.1 + n.1 * step);
        let right = (mid.0 - n.0 * step, mid.1 - n.1 * step);
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
