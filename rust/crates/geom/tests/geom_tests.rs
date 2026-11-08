//! Портированные тесты core/geom/tests (overlay, snap+coverage, curves+path).
//!
//! Эталон — Python-версия; проверяемые числа и допуски сняты с unittest.
//! Путь к репозиторию берётся из GRADO_REPO или по умолчанию — соседняя
//! папка repos/grado-studio.

use std::path::PathBuf;
use std::sync::OnceLock;

use grado_geom_rs::coverage::{Coverage, CoverageError};
use grado_geom_rs::curves::{tessellate_curve, Arc, CurveError};
use grado_geom_rs::overlay::union_intersection_area;
use grado_geom_rs::path::{Path, PathError};
use grado_geom_rs::{affine, snap, Pt};

fn repo() -> PathBuf {
    if let Ok(p) = std::env::var("GRADO_REPO") {
        return PathBuf::from(p);
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
}

/// Число портированных тестов (для отчёта о переносе покрытия).
#[test]
fn port_inventory() {
    static REPO: OnceLock<PathBuf> = OnceLock::new();
    let dir = REPO.get_or_init(repo).join("core/geom/tests");
    assert!(dir.exists(), "репозиторий с тестами не найден: {}", dir.display());
}

// --- хелперы почти-равенства (unittest.assertAlmostEqual) -------------------

fn close_delta(a: f64, b: f64, delta: f64, msg: &str) {
    assert!(
        (a - b).abs() <= delta,
        "{msg}: {a} != {b} (допуск {delta})"
    );
}

fn close_places(a: f64, b: f64, places: i32, msg: &str) {
    let delta = 0.5 * 10f64.powi(-places);
    close_delta(a, b, delta, msg);
}

// --- test_overlay.py --------------------------------------------------------

fn square(x: f64, y: f64, s: f64) -> Vec<Vec<Pt>> {
    vec![vec![(x, y), (x + s, y), (x + s, y + s), (x, y + s)]]
}

#[test]
fn overlay_partial_overlap_with_clip() {
    let area = union_intersection_area(&[square(50.0, 50.0, 100.0)], &[square(0.0, 0.0, 100.0)]);
    close_delta(area, 2500.0, 0.5, "половинное перекрытие");
}

#[test]
fn overlay_duplicates_and_nested_are_not_double_counted() {
    let regions = vec![
        square(0.0, 0.0, 100.0),
        square(0.0, 0.0, 100.0),
        square(20.0, 20.0, 30.0),
    ];
    let area = union_intersection_area(&regions, &[square(0.0, 0.0, 100.0)]);
    close_delta(area, 10000.0, 0.5, "дубли и вложенность");
}

#[test]
fn overlay_adjacent_regions_share_edge() {
    let regions = vec![
        square(0.0, 0.0, 50.0),
        vec![vec![(50.0, 0.0), (100.0, 0.0), (100.0, 50.0), (50.0, 50.0)]],
    ];
    let area = union_intersection_area(&regions, &[square(0.0, 0.0, 100.0)]);
    close_delta(area, 5000.0, 0.5, "смежные зоны");
}

#[test]
fn overlay_hole_and_orientation() {
    let ring = vec![(0.0, 0.0), (0.0, 100.0), (100.0, 100.0), (100.0, 0.0)]; // по часовой
    let hole = vec![(40.0, 40.0), (60.0, 40.0), (60.0, 60.0), (40.0, 60.0)];
    let area = union_intersection_area(&[vec![ring, hole]], &[square(-10.0, -10.0, 200.0)]);
    close_delta(area, 9600.0, 0.5, "дыра и ориентация");
}

#[test]
fn overlay_triangle_exact_and_disjoint() {
    let tri = vec![vec![(0.0, 0.0), (100.0, 0.0), (0.0, 100.0)]];
    let area = union_intersection_area(&[tri], &[square(0.0, 0.0, 100.0)]);
    close_delta(area, 5000.0, 0.5, "треугольник");
    let disjoint = union_intersection_area(&[square(500.0, 500.0, 10.0)], &[square(0.0, 0.0, 100.0)]);
    assert_eq!(0.0, disjoint, "не пересекаются — ноль");
}

#[test]
fn overlay_small_coordinates_are_exact() {
    // граница в градусах (как у district_shares), треугольник 0,01° на стыке
    // двух районов: точно 3/4 на западе; прежний шаг 0,05 давал одну строку
    // сканирования и 100 % западу
    let terr = vec![vec![(37.70, 55.80), (37.71, 55.80), (37.70, 55.81)]];
    let west = vec![vec![(37.60, 55.70), (37.705, 55.70), (37.705, 55.90), (37.60, 55.90)]];
    let east = vec![vec![(37.705, 55.70), (37.80, 55.70), (37.80, 55.90), (37.705, 55.90)]];
    let a = union_intersection_area(&[terr.clone()], &[west]);
    let b = union_intersection_area(&[terr], &[east]);
    close_places(a / (a + b), 0.75, 9, "граница в градусах, 3/4 западу");
}

#[test]
fn overlay_degenerate_rings_give_zero() {
    let cases: Vec<Vec<Pt>> = vec![
        vec![(1.0, 1.0), (1.0, 1.0), (1.0, 1.0)],
        vec![(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)],
        vec![(0.0, 0.0), (f64::NAN, 1.0), (2.0, 2.0)],
    ];
    for ring in cases {
        let area = union_intersection_area(&[vec![ring.clone()]], &[square(0.0, 0.0, 10.0)]);
        assert_eq!(0.0, area, "вырожденное кольцо {ring:?}");
    }
}

#[test]
fn overlay_self_intersecting_ring_is_repaired() {
    // «бабочка»: два треугольника по 2500
    let bow = vec![vec![(0.0, 0.0), (100.0, 100.0), (100.0, 0.0), (0.0, 100.0)]];
    let area = union_intersection_area(&[bow], &[square(0.0, 0.0, 100.0)]);
    close_delta(area, 5000.0, 0.5, "самопересечение чинится");
}

// --- test_snap_coverage.py: Snapper ----------------------------------------

fn demo_snapper() -> snap::Snapper {
    let mut s = snap::Snapper::new(0.5);
    s.add_segment((0.0, 0.0), (10.0, 10.0));
    s.add_segment((0.0, 10.0), (10.0, 0.0));
    s
}

#[test]
fn snap_endpoint_beats_nearest() {
    let s = demo_snapper();
    let r = s.snap(0.1, 0.05).expect("привязка есть");
    assert_eq!(r.kind, snap::SnapKind::Endpoint);
    assert_eq!(r.point, (0.0, 0.0));
}

#[test]
fn snap_intersection() {
    let s = demo_snapper();
    let r = s.snap(5.2, 5.1).expect("привязка есть");
    assert_eq!(r.kind, snap::SnapKind::Intersection);
    close_delta(r.point.0, 5.0, 1e-9, "x пересечения");
    close_delta(r.point.1, 5.0, 1e-9, "y пересечения");
}

#[test]
fn snap_priority_over_distance() {
    // ближайшая точка на отрезке в нуле от курсора, но пересечение в допуске
    let s = demo_snapper();
    let r = s.snap(5.3, 5.3).expect("привязка есть");
    assert_eq!(
        r.kind,
        snap::SnapKind::Intersection,
        "характеристическая точка бьёт «ближайшую»"
    );
}

#[test]
fn snap_nothing_beyond_tolerance() {
    let s = demo_snapper();
    assert!(s.snap(50.0, 50.0).is_none());
}

#[test]
fn snap_grid_keeps_distant_endpoint() {
    let mut s = demo_snapper();
    s.add_segment((1000.0, 1000.0), (1010.0, 1000.0));
    let near = s.snap(0.1, 0.05).expect("привязка есть");
    assert_eq!(near.point, (0.0, 0.0));
    let far = s.snap(1000.1, 1000.1).expect("привязка есть");
    assert_eq!(far.kind, snap::SnapKind::Endpoint);
    assert_eq!(far.point, (1000.0, 1000.0));
}

#[test]
fn snap_midpoint() {
    let mut s = snap::Snapper::new(0.5);
    s.add_segment((0.0, 0.0), (10.0, 0.0));
    let r = s.snap(5.1, 0.2).expect("привязка есть");
    assert_eq!(r.kind, snap::SnapKind::Midpoint);
    assert_eq!(r.point, (5.0, 0.0));
}

// --- test_snap_coverage.py: Coverage ----------------------------------------

fn sq(x0: f64, y0: f64, w: f64, h: f64) -> Vec<Pt> {
    vec![(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
}

fn pair(name_a: &str, name_b: &str) -> Vec<(String, Vec<Pt>)> {
    vec![
        (name_a.to_string(), sq(0.0, 0.0, 10.0, 10.0)),
        (name_b.to_string(), sq(10.0, 0.0, 10.0, 10.0)),
    ]
}

#[test]
fn coverage_shared_edge_detected() {
    let cov = Coverage::from_polygons(&pair("A", "B")).expect("покрытие строится");
    assert_eq!(cov.shared_edges().len(), 1);
    close_delta(cov.area("A"), 100.0, 1e-9, "площадь A");
    close_delta(cov.area("B"), 100.0, 1e-9, "площадь B");
    cov.validate(1e-6).expect("покрытие правильно");
}

#[test]
fn coverage_edit_shared_edge_moves_both() {
    let mut cov = Coverage::from_polygons(&pair("A", "B")).expect("покрытие строится");
    let eid = cov.shared_edges()[0];
    let e = &cov.edges[&eid];
    let (p0, p1) = (e.pts[0], e.pts[e.pts.len() - 1]);
    let my = (p0.1 + p1.1) / 2.0;
    cov.edit_edge(eid, &[p0, (13.0, my), p1])
        .expect("выгиб в сторону B");

    let areas = cov.areas();
    let total: f64 = areas.iter().map(|(_, a)| *a).sum();
    close_delta(total, 200.0, 1e-9, "баланс территории сохраняется");
    let max_a = areas.iter().map(|(_, a)| *a).fold(f64::MIN, f64::max);
    let min_a = areas.iter().map(|(_, a)| *a).fold(f64::MAX, f64::min);
    close_delta(max_a, 115.0, 1e-9, "максимальная площадь");
    close_delta(min_a, 85.0, 1e-9, "минимальная площадь");
    cov.validate(1e-6).expect("покрытие правильно");
}

#[test]
fn coverage_edit_edge_nodes_fixed() {
    let mut cov = Coverage::from_polygons(&pair("A", "B")).expect("покрытие строится");
    let eid = cov.shared_edges()[0];
    let err = cov
        .edit_edge(eid, &[(10.0, 1.0), (10.0, 9.0)])
        .expect_err("концы обязаны совпадать с узлами");
    assert!(matches!(err, CoverageError(_)));
}

#[test]
fn coverage_three_faces() {
    // у C промежуточная вершина (10,10): общие границы совпадают повершинно
    let polygons = vec![
        ("A".to_string(), sq(0.0, 0.0, 10.0, 10.0)),
        ("B".to_string(), sq(10.0, 0.0, 10.0, 10.0)),
        (
            "C".to_string(),
            vec![(0.0, 10.0), (10.0, 10.0), (20.0, 10.0), (20.0, 16.0), (0.0, 16.0)],
        ),
    ];
    let cov = Coverage::from_polygons(&polygons).expect("покрытие строится");
    assert_eq!(cov.shared_edges().len(), 3);
    let total: f64 = cov.areas().iter().map(|(_, a)| *a).sum();
    close_delta(total, 320.0, 1e-9, "сумма площадей");
    cov.validate(1e-6).expect("покрытие правильно");
}

#[test]
fn coverage_overlap_rejected() {
    let polygons = vec![
        ("A".to_string(), sq(0.0, 0.0, 10.0, 10.0)),
        ("B".to_string(), sq(0.0, 0.0, 10.0, 10.0)),
    ];
    let err = Coverage::from_polygons(&polygons).expect_err("нахлёст отвергнут");
    assert!(matches!(err, CoverageError(_)));
}

#[test]
fn coverage_triple_use_rejected() {
    let polygons = vec![
        ("A".to_string(), sq(0.0, 0.0, 10.0, 10.0)),
        ("B".to_string(), sq(10.0, 0.0, 10.0, 10.0)),
        ("C".to_string(), sq(0.0, 0.0, 10.0, 10.0)),
    ];
    let err = Coverage::from_polygons(&polygons).expect_err("тройное использование отвергнуто");
    assert!(matches!(err, CoverageError(_)));
}

#[test]
fn coverage_disconnected_fails_validation() {
    let polygons = vec![
        ("A".to_string(), sq(0.0, 0.0, 10.0, 10.0)),
        ("B".to_string(), sq(30.0, 0.0, 10.0, 10.0)),
    ];
    let cov = Coverage::from_polygons(&polygons).expect("покрытие строится");
    let err = cov.validate(1e-6).expect_err("разрыв пойман");
    assert!(matches!(err, CoverageError(_)));
}

// --- test_curves_path.py -----------------------------------------------------

#[test]
fn arc_from_3pts_semicircle() {
    let arc = Arc::from_3pts((0.0, 0.0), (1.0, 1.0), (2.0, 0.0)).expect("дуга строится");
    close_delta(arc.cx, 1.0, 1e-9, "cx");
    close_delta(arc.cy, 0.0, 1e-9, "cy");
    close_delta(arc.r, 1.0, 1e-9, "r");
    close_delta(arc.length(), std::f64::consts::PI, 1e-9, "длина");
    let (x, y) = arc.point_at(0.5);
    close_delta(x, 1.0, 1e-9, "x середины");
    close_delta(y, 1.0, 1e-9, "y середины");
    let (sx, sy) = arc.start();
    close_delta((sx - 0.0).hypot(sy - 0.0), 0.0, 1e-9, "начало");
    let (ex, ey) = arc.end();
    close_delta((ex - 2.0).hypot(ey - 0.0), 0.0, 1e-9, "конец");
}

#[test]
fn arc_collinear_rejected() {
    let err = Arc::from_3pts((0.0, 0.0), (1.0, 0.0), (2.0, 0.0)).expect_err("коллинеарность");
    assert!(matches!(err, CurveError(_)));
}

#[test]
fn arc_linearize_sagitta() {
    let arc = Arc::new(0.0, 0.0, 100.0, 0.0, std::f64::consts::FRAC_PI_2).expect("дуга");
    let tol = 0.01;
    let pts = arc.linearize(tol);
    for w in pts.windows(2) {
        let (mx, my) = ((w[0].0 + w[1].0) / 2.0, (w[0].1 + w[1].1) / 2.0);
        let sagitta = 100.0 - mx.hypot(my);
        assert!(sagitta <= tol * 1.001, "сагитта {sagitta} > допуска");
    }
}

#[test]
fn arc_offset_left() {
    let ccw = Arc::new(0.0, 0.0, 10.0, 0.0, std::f64::consts::FRAC_PI_2).expect("дуга");
    close_delta(ccw.offset(2.0).expect("офсет").r, 8.0, 1e-9, "центр слева — радиус меньше");
    let cw = Arc::new(0.0, 0.0, 10.0, std::f64::consts::FRAC_PI_2, -std::f64::consts::FRAC_PI_2)
        .expect("дуга");
    close_delta(cw.offset(2.0).expect("офсет").r, 12.0, 1e-9, "центр справа — радиус больше");
    let err = ccw.offset(10.5).expect_err("офсет схлопывает");
    assert!(matches!(err, CurveError(_)));
}

#[test]
fn arc_tangent() {
    let arc = Arc::new(0.0, 0.0, 5.0, 0.0, std::f64::consts::FRAC_PI_2).expect("дуга");
    close_delta(arc.tangent_at(0.0), std::f64::consts::FRAC_PI_2, 1e-9, "касательная");
}

#[test]
fn path_station_on_polyline() {
    let p = Path::polyline(&[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], false).expect("путь");
    close_delta(p.length(), 20.0, 1e-9, "длина");
    let ((x, y), tangent) = p.point_at_station(15.0).expect("пикет");
    close_delta(x, 10.0, 1e-9, "x на пикете");
    close_delta(y, 5.0, 1e-9, "y на пикете");
    close_delta(tangent, std::f64::consts::FRAC_PI_2, 1e-9, "касательная");
}

#[test]
fn path_fillet_length() {
    let p = Path::fillet_polyline(&[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], 2.0).expect("путь");
    close_places(p.length(), 16.0 + std::f64::consts::PI, 9, "длина с сопряжением");
    assert!(p.is_g1(1e-6), "сопряжение тангенциально");
}

#[test]
fn path_fillet_radius_too_big() {
    let err = Path::fillet_polyline(&[(0.0, 0.0), (3.0, 0.0), (3.0, 3.0)], 5.0).expect_err("радиус велик");
    assert!(matches!(err, PathError(_)));
}

#[test]
fn path_stations() {
    let p = Path::fillet_polyline(&[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], 2.0).expect("путь");
    let sts = p.stations(5.0).expect("пикетаж");
    assert_eq!(sts.len(), 5);
    close_places(sts[sts.len() - 1].0, 16.0 + std::f64::consts::PI, 9, "последний ПК");
    let (x, y) = sts[sts.len() - 1].1;
    close_places((x - 10.0).hypot(y - 10.0), 0.0, 9, "конец пути");
}

#[test]
fn path_offset_g1_chain() {
    let p = Path::fillet_polyline(&[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], 2.0).expect("путь");
    let off = p.offset(1.0).expect("офсет"); // левый офсет; поворот налево — офсет внутри
    close_places(off.length(), 16.0 + std::f64::consts::FRAC_PI_2, 9, "длина офсета");
    assert!(off.is_g1(1e-6), "офсет G1-цепи остаётся G1");
}

#[test]
fn path_offset_miter_rectangle() {
    let rect = Path::polyline(
        &[(0.0, 0.0), (10.0, 0.0), (10.0, 6.0), (0.0, 6.0)],
        true,
    )
    .expect("путь");
    let inner = rect.offset(1.0).expect("офсет"); // ccw-обход: слева — внутренность
    close_places(inner.area(0.01), 8.0 * 4.0, 6, "внутренний офсет");
    let outer = rect.offset(-1.0).expect("офсет");
    close_places(outer.area(0.01), 12.0 * 8.0, 6, "внешний офсет");
}

#[test]
fn curve_spec_round_and_tessellation() {
    let spec = serde_json::json!({
        "type": "arc", "cx": 0, "cy": 0, "r": 10, "a0": 0, "sweep": std::f64::consts::FRAC_PI_2
    });
    let pts = tessellate_curve(&spec, 0.05).expect("тесселяция");
    assert!(pts.len() > 2);
    close_delta(pts[0].0, 10.0, 1e-9, "первая точка дуги");
    let circle = tessellate_curve(
        &serde_json::json!({"type": "circle", "cx": 0, "cy": 0, "r": 5}),
        0.05,
    )
    .expect("тесселяция");
    assert_eq!(circle[0], circle[circle.len() - 1], "окружность замкнута");
}

#[test]
fn affine_rotate_scale_mirror() {
    let turned = affine::rotate(&[(1.0, 0.0)], (0.0, 0.0), 90.0).expect("поворот");
    close_places(turned[0].0, 0.0, 6, "x повёрнутый");
    close_places(turned[0].1, 1.0, 6, "y повёрнутый");
    let scaled = affine::scale(&[(2.0, 0.0)], (0.0, 0.0), 3.0).expect("масштаб");
    assert_eq!(scaled, vec![(6.0, 0.0)]);
    let mirrored = affine::mirror(&[(1.0, 2.0)], (0.0, 0.0), (1.0, 0.0)).expect("зеркало");
    assert_eq!(mirrored, vec![(1.0, -2.0)]);
}

#[test]
fn path_offset_mixed_non_g1_rejected() {
    let arc = Arc::new(0.0, 0.0, 5.0, 0.0, std::f64::consts::FRAC_PI_2).expect("дуга");
    let p = Path::new(
        vec![
            grado_geom_rs::path::PathElement::Seg { a: (0.0, 0.0), b: (5.0, 0.0) },
            grado_geom_rs::path::PathElement::Arc(arc),
        ],
        false,
    )
    .expect("путь");
    assert!(!p.is_g1(1e-6));
    let err = p.offset(1.0).expect_err("не G1 — офсет отвергнут");
    assert!(matches!(err, PathError(_)));
}
