//! Топологическое покрытие (coverage): зоны с общими границами.
//!
//! Смежные функциональные зоны и участки межевания хранят общее ребро один
//! раз: правка ребра двигает обе зоны, дырки и нахлёсты невозможны
//! конструктивно. Сборка — из полигонов с точно совпадающими общими цепочками
//! вершин (так рисуют с привязками). Хранение рёбер — своё (у shapely такой
//! модели нет); площади — своя формула шнурков (как у GEOS); проверка
//! целостности `validate`: парные пересечения граней (вместо
//! `shapely.coverage_is_valid`) и баланс площадей с внешней границей.
//! Порт `grado_geom/coverage.py`.

use std::collections::{BTreeMap, BTreeSet};

use geo::{Area, BooleanOps, Intersects, LineString, MultiPolygon, Polygon};

use crate::{OrdF64, Pt};

/// Ошибка покрытия (Python: CoverageError, подкласс ValueError).
#[derive(Debug, Clone)]
pub struct CoverageError(pub String);

impl std::fmt::Display for CoverageError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for CoverageError {}

/// Ребро: цепочка точек + смежные грани слева/справа.
#[derive(Debug, Clone)]
pub struct EdgeData {
    pub pts: Vec<Pt>,
    pub left: Option<String>,
    pub right: Option<String>,
}

/// Топологическое покрытие. Грани хранятся в порядке вставки полигонов
/// (Python — dict), рёбра — по номерам (BTreeMap = порядок вставки Python).
#[derive(Debug, Clone, Default)]
pub struct Coverage {
    pub edges: BTreeMap<u64, EdgeData>,
    pub faces: Vec<(String, Vec<(u64, bool)>)>,
    next_eid: u64,
}

impl Coverage {
    /// Номера рёбер начинаются с 1, как в Python-эталоне.
    fn new() -> Self {
        Coverage {
            edges: BTreeMap::new(),
            faces: Vec::new(),
            next_eid: 1,
        }
    }
}

fn norm(pt: Pt) -> Pt {
    (crate::py_round9(pt.0), crate::py_round9(pt.1))
}

/// Python `_ccw`: кольцо против часовой (площадь со знаком > 0).
fn ccw(ring: &[Pt]) -> Vec<Pt> {
    if crate::shoelace(ring) > 0.0 {
        ring.to_vec()
    } else {
        ring.iter().rev().copied().collect()
    }
}

/// Замкнутое кольцо сегментов (сегменты по кругу, включая замыкающий).
fn ring_segments(ring: &[Pt]) -> Vec<(Pt, Pt)> {
    let mut segs: Vec<(Pt, Pt)> = ring.windows(2).map(|w| (w[0], w[1])).collect();
    if !ring.is_empty() {
        segs.push((ring[ring.len() - 1], ring[0]));
    }
    segs
}

fn ring_polygon(ring: &[Pt]) -> Polygon<f64> {
    let mut closed = ring.to_vec();
    if !ring.is_empty() && closed[0] != closed[closed.len() - 1] {
        closed.push(closed[0]);
    }
    Polygon::new(LineString::from(closed), Vec::new())
}

/// Ключ неориентированного сегмента (min/max концов, лексикографически).
fn seg_key(a: Pt, b: Pt) -> (OrdF64, OrdF64, OrdF64, OrdF64) {
    let (x1, y1, x2, y2) = if a < b {
        (a.0, a.1, b.0, b.1)
    } else {
        (b.0, b.1, a.0, a.1)
    };
    (OrdF64(x1), OrdF64(y1), OrdF64(x2), OrdF64(y2))
}

impl Coverage {
    /// polygons: пары (fid, кольцо [(x,y), …]) в порядке вставки — без
    /// дырок, общие границы совпадают повершинно.
    pub fn from_polygons(polygons: &[(String, Vec<Pt>)]) -> Result<Self, CoverageError> {
        let mut cov = Coverage::new();
        let mut walks: Vec<(String, Vec<Pt>)> = Vec::new();
        // неориентированный сегмент -> [(грань, направление обхода a<b)]
        let mut seg_usage: BTreeMap<(OrdF64, OrdF64, OrdF64, OrdF64), Vec<(usize, bool)>> =
            BTreeMap::new();

        for (fid, raw) in polygons {
            for p in raw {
                if !p.0.is_finite() || !p.1.is_finite() {
                    return Err(CoverageError(format!("{fid}: координата не конечна")));
                }
            }
            let mut ring: Vec<Pt> = raw.iter().map(|&p| norm(p)).collect();
            if ring.len() >= 2 && ring[0] == ring[ring.len() - 1] {
                ring.pop();
            }
            if ring.len() < 3 {
                return Err(CoverageError(format!("{fid}: вырожденное кольцо")));
            }
            let ring = ccw(&ring);
            for (a, b) in ring_segments(&ring) {
                if a == b {
                    return Err(CoverageError(format!(
                        "{fid}: нулевой сегмент ({}, {})",
                        a.0, a.1
                    )));
                }
                seg_usage
                    .entry(seg_key(a, b))
                    .or_default()
                    .push((walks.len(), a < b));
            }
            walks.push((fid.clone(), ring));
        }

        for (key, users) in &seg_usage {
            if users.len() > 2 {
                return Err(CoverageError(format!(
                    "сегмент {key:?} принадлежит {} зонам — нахлёст",
                    users.len()
                )));
            }
            if users.len() == 2 && users[0].1 == users[1].1 {
                return Err(CoverageError(format!(
                    "сегмент {key:?} обходится дважды в одном направлении — зоны перекрываются"
                )));
            }
        }

        let other_face = |face: usize, a: Pt, b: Pt| -> Option<usize> {
            for (uf, _) in &seg_usage[&seg_key(a, b)] {
                if *uf != face {
                    return Some(*uf);
                }
            }
            None
        };

        // разбиваем обход каждой грани на цепочки с одинаковым соседом
        let mut seg_edge: BTreeMap<(OrdF64, OrdF64, OrdF64, OrdF64), (u64, bool)> =
            BTreeMap::new();
        for (face, (fid, ring)) in walks.iter().enumerate() {
            let segs = ring_segments(ring);
            let pairs: Vec<Option<usize>> =
                segs.iter().map(|&(a, b)| other_face(face, a, b)).collect();

            // начинаем цепочку с границы смены соседа (иначе кольцо — одна цепь)
            let mut start = 0;
            for i in 0..segs.len() {
                if pairs[i] != pairs[(i + segs.len() - 1) % segs.len()] {
                    start = i;
                    break;
                }
            }
            let order: Vec<usize> = (start..segs.len()).chain(0..start).collect();
            let mut boundary: Vec<(Vec<(Pt, Pt)>, Option<Option<usize>>)> = Vec::new();
            let mut chain: Vec<(Pt, Pt)> = Vec::new();
            // внешнее None — «цепь ещё не начата», внутреннее None — сосед
            // None (внешняя граница); как sentinel object() в Python
            let mut chain_pair: Option<Option<usize>> = None;
            for &i in &order {
                if chain_pair != Some(pairs[i]) && !chain.is_empty() {
                    boundary.push((std::mem::take(&mut chain), chain_pair));
                }
                chain_pair = Some(pairs[i]);
                chain.push(segs[i]);
            }
            boundary.push((chain, chain_pair));

            let mut face_edges: Vec<(u64, bool)> = Vec::new();
            for (chain, neighbor) in boundary {
                let _ = neighbor;
                // цепь уже создана соседом — идём по ней в обратную сторону;
                // первый развёрнутый сегмент — последний сегмент цепи (сосед
                // шёл в противоположную сторону)
                let rev_first = match chain.last() {
                    Some(&(a, b)) => seg_key(b, a),
                    None => unreachable!("пустая цепь"),
                };
                if let Some(&(eid, _)) = seg_edge.get(&rev_first) {
                    face_edges.push((eid, false));
                    cov.edges.get_mut(&eid).expect("ребро создано").right =
                        Some(fid.clone());
                } else {
                    let mut pts: Vec<Pt> = vec![chain[0].0];
                    pts.extend(chain.iter().map(|s| s.1));
                    let eid = cov.next_eid;
                    cov.next_eid += 1;
                    cov.edges.insert(
                        eid,
                        EdgeData { pts, left: Some(fid.clone()), right: None },
                    );
                    for seg in &chain {
                        seg_edge.insert(seg_key(seg.0, seg.1), (eid, true));
                    }
                    face_edges.push((eid, true));
                }
            }
            cov.faces.push((fid.clone(), face_edges));
        }
        Ok(cov)
    }

    // --- доступ -------------------------------------------------------------

    fn face_index(&self, fid: &str) -> Option<usize> {
        self.faces.iter().position(|(f, _)| f == fid)
    }

    /// Кольцо грани.
    pub fn polygon(&self, fid: &str) -> Vec<Pt> {
        let idx = self
            .face_index(fid)
            .unwrap_or_else(|| panic!("нет грани {fid}"));
        let mut ring: Vec<Pt> = Vec::new();
        for &(eid, forward) in &self.faces[idx].1 {
            let mut pts = self.edges[&eid].pts.clone();
            if !forward {
                pts.reverse();
            }
            if let Some(&last) = ring.last() {
                if last == pts[0] {
                    pts.remove(0);
                }
            }
            ring.extend(pts);
        }
        if ring.len() >= 2 && ring[0] == ring[ring.len() - 1] {
            ring.pop();
        }
        ring
    }

    pub fn area(&self, fid: &str) -> f64 {
        crate::shoelace(&self.polygon(fid)).abs()
    }

    /// Площади граней в порядке вставки полигонов.
    pub fn areas(&self) -> Vec<(String, f64)> {
        self.faces
            .iter()
            .map(|(fid, _)| (fid.clone(), self.area(fid)))
            .collect()
    }

    /// Номера рёбер с двумя смежными гранями, по возрастанию.
    pub fn shared_edges(&self) -> Vec<u64> {
        self.edges
            .iter()
            .filter(|(_, e)| e.left.is_some() && e.right.is_some())
            .map(|(eid, _)| *eid)
            .collect()
    }

    // --- редактирование -------------------------------------------------------

    /// Заменить геометрию ребра (узлы на концах неподвижны).
    ///
    /// Обе смежные зоны меняются одновременно — общая граница одна.
    pub fn edit_edge(&mut self, eid: u64, new_pts: &[Pt]) -> Result<(), CoverageError> {
        let e = self
            .edges
            .get(&eid)
            .ok_or_else(|| CoverageError(format!("нет ребра {eid}")))?;
        if new_pts.is_empty() {
            return Err(CoverageError("концы ребра должны совпадать с узлами".into()));
        }
        let new_pts: Vec<Pt> = new_pts.iter().map(|&p| norm(p)).collect();
        if new_pts[0] != e.pts[0]
            || new_pts[new_pts.len() - 1] != e.pts[e.pts.len() - 1]
        {
            return Err(CoverageError("концы ребра должны совпадать с узлами".into()));
        }
        self.edges.get_mut(&eid).expect("ребро есть").pts = new_pts;
        Ok(())
    }

    // --- контроль целостности ---------------------------------------------------

    /// Внешняя граница покрытия.
    pub fn outer_ring(&self) -> Result<Vec<Pt>, CoverageError> {
        let boundary: BTreeMap<u64, &EdgeData> = self
            .edges
            .iter()
            .filter(|(_, e)| e.right.is_none())
            .map(|(eid, e)| (*eid, e))
            .collect();
        if boundary.is_empty() {
            return Err(CoverageError("нет внешней границы".into()));
        }
        let start_eid = *boundary.keys().next().expect("не пусто");
        let mut ring = boundary[&start_eid].pts.clone();
        let mut used: BTreeSet<u64> = BTreeSet::from([start_eid]);
        while ring[0] != ring[ring.len() - 1] {
            let mut found = false;
            for (eid, e) in boundary.iter() {
                if used.contains(eid) {
                    continue;
                }
                let cand = if e.pts[0] == ring[ring.len() - 1] {
                    Some(e.pts[1..].to_vec())
                } else if e.pts[e.pts.len() - 1] == ring[ring.len() - 1] {
                    let mut rev = e.pts.clone();
                    rev.reverse();
                    Some(rev[1..].to_vec())
                } else {
                    None
                };
                if let Some(v) = cand {
                    used.insert(*eid);
                    ring.extend(v);
                    found = true;
                    break;
                }
            }
            if !found {
                return Err(CoverageError("внешняя граница не замыкается".into()));
            }
        }
        ring.pop();
        Ok(ring)
    }

    /// Зоны образуют правильное покрытие и сумма их площадей == площадь
    /// внешней границы (нет дырок/нахлёстов).
    ///
    /// Вместо shapely.coverage_is_valid: парные пересечения граней пусты
    /// (порог — 1e-9 от максимальной площади) и баланс сходится.
    pub fn validate(&self, tol: f64) -> Result<bool, CoverageError> {
        let polys: Vec<Polygon<f64>> = self
            .faces
            .iter()
            .map(|(fid, _)| ring_polygon(&self.polygon(fid)))
            .collect();
        let max_area = polys
            .iter()
            .map(|p| p.unsigned_area())
            .fold(0.0f64, f64::max);
        for i in 0..polys.len() {
            for j in i + 1..polys.len() {
                let a = MultiPolygon::new(vec![polys[i].clone()]);
                let b = MultiPolygon::new(vec![polys[j].clone()]);
                if a.intersects(&b) {
                    let overlap = a.intersection(&b).unsigned_area();
                    if overlap > max_area * 1e-9 {
                        return Err(CoverageError(
                            "зоны перекрываются или между ними щель".into(),
                        ));
                    }
                }
            }
        }
        let total: f64 = polys.iter().map(|p| p.unsigned_area()).sum();
        let outer = crate::shoelace(&self.outer_ring()?).abs();
        // math.isclose(total, outer, rel_tol=tol)
        if !((total - outer).abs() <= tol * total.abs().max(outer.abs())) {
            return Err(CoverageError(format!(
                "баланс не сходится: зоны {:.6} ≠ контур {:.6}",
                total, outer
            )));
        }
        Ok(true)
    }
}
