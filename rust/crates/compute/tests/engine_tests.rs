//! Портированные тесты core/compute/tests (engine, пресет «Калькулятора 2.0»).
//!
//! Эталон — Python-версия; значения фикстуры Якиманки сняты с genplan.tech 23.09.2026.
//! Путь к репозиторию берётся из GRADO_REPO или по умолчанию — соседняя папка repos/grado-studio.

use grado_compute_rs::decimal::Value;
use grado_compute_rs::engine::Engine;
use num_bigint::BigInt;
use std::path::PathBuf;
use std::sync::OnceLock;

fn repo() -> PathBuf {
    if let Ok(p) = std::env::var("GRADO_REPO") {
        return PathBuf::from(p);
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..")
}

fn preset_path(name: &str) -> PathBuf {
    repo().join("core/compute/grado_compute/presets").join(name)
}

fn calc2() -> &'static str {
    static T: OnceLock<String> = OnceLock::new();
    T.get_or_init(|| std::fs::read_to_string(preset_path("moscow_calc2.json")).unwrap())
}

fn load(name: &str) -> Engine {
    let text = std::fs::read_to_string(preset_path(name)).unwrap();
    Engine::from_preset_str(&text).unwrap()
}

fn i(v: i64) -> Value {
    Value::Int(BigInt::from(v))
}
fn f(v: f64) -> Value {
    Value::Float(v)
}

fn make_engine() -> Engine {
    // как в test_engine.py:make_engine
    let preset = serde_json::json!({
        "title": "test",
        "inputs": [ {"id": "a", "default": 10}, {"id": "b", "default": 2} ],
        "constants": {"k": 3},
        "metrics": [
            {"id": "m3", "expr": "m1 + m2"},
            {"id": "m1", "expr": "a * k"},
            {"id": "m2", "expr": "b + 1"},
        ],
    });
    Engine::from_preset(&preset).unwrap()
}

fn results_map(e: &Engine) -> std::collections::HashMap<String, Value> {
    e.results()
        .into_iter()
        .map(|r| (r.id, r.value))
        .collect()
}

fn num(v: &Value) -> f64 {
    v.as_f64().unwrap()
}

// ---------- test_engine.py ----------

#[test]
fn topo_evaluation() {
    let e = make_engine();
    assert_eq!(e.value("m1").unwrap().py_repr(), "30");
    assert_eq!(e.value("m2").unwrap().py_repr(), "3");
    assert_eq!(e.value("m3").unwrap().py_repr(), "33");
}

#[test]
fn incremental_recompute() {
    let mut e = make_engine();
    let counts: Vec<u64> = ["m1", "m2", "m3"].iter().map(|k| e.eval_counts[*k]).collect();
    e.set_input("b", i(5)).unwrap();
    assert_eq!(e.value("m2").unwrap().py_repr(), "6");
    assert_eq!(e.value("m3").unwrap().py_repr(), "36");
    assert_eq!(e.eval_counts["m1"], counts[0], "m1 не зависит от b");
    assert_eq!(e.eval_counts["m2"], counts[1] + 1);
    assert_eq!(e.eval_counts["m3"], counts[2] + 1);
}

#[test]
fn unknown_input() {
    let mut e = make_engine();
    assert!(e.set_input("zzz", i(1)).is_err());
}

#[test]
fn cycle_detection() {
    let preset = serde_json::json!({
        "inputs": [{"id": "a", "default": 1}],
        "metrics": [
            {"id": "x", "expr": "y + 1"},
            {"id": "y", "expr": "x + a"},
        ],
    });
    assert!(Engine::from_preset(&preset).is_err());
}

#[test]
fn unknown_reference() {
    let preset = serde_json::json!({"metrics": [{"id": "x", "expr": "nope + 1"}]});
    assert!(Engine::from_preset(&preset).is_err());
}

#[test]
fn duplicate_id() {
    let preset = serde_json::json!({
        "inputs": [{"id": "a", "default": 1}],
        "metrics": [{"id": "a", "expr": "1 + 1"}],
    });
    assert!(Engine::from_preset(&preset).is_err());
}

#[test]
fn set_inputs_atomic() {
    let mut e = make_engine();
    assert!(e.set_inputs(&[("a".into(), i(99)), ("bogus".into(), i(1))]).is_err());
    assert_eq!(e.value("a").unwrap().py_repr(), "10");
}

// ---------- test_calc2_preset.py ----------

fn yakimanka() -> Engine {
    let mut e = Engine::from_preset_str(calc2()).unwrap();
    e.set_inputs(&[
        ("terr_area".into(), f(15.0)),
        ("restrict_area".into(), f(0.0)),
        ("spp_in".into(), f(357.0)),
        ("ratio_zh".into(), f(100.0)),
        ("nonres_part".into(), f(6.0)),
        ("education_zone".into(), f(1.0)),
        ("k1".into(), f(0.75)),
        ("k2".into(), f(0.2)),
        ("tinao".into(), f(0.0)),
        ("territory_mode".into(), f(1.0)),
        ("unbuilt_share".into(), f(25.0)),
    ])
    .unwrap();
    e
}

#[test]
fn calc2_yakimanka_areas() {
    let e = yakimanka();
    let r = results_map(&e);
    // эталон фикстуры: spp_total 357.000, np_total 321.300 и т.д. (сравнение с точностью метода)
    assert!((num(&r["spp"]) - 357.0).abs() < 1e-9, "spp = {}", r["spp"].py_repr());
    assert!((num(&r["np"]) - 321.3).abs() < 1e-9, "np = {}", r["np"].py_repr());
    assert!((num(&r["spp_res_living"]) - 335.58).abs() < 1e-9);
    assert!((num(&r["spp_res_nonres"]) - 21.42).abs() < 1e-9);
    assert!((num(&r["np_res_living"]) - 302.022).abs() < 1e-9);
    assert!((num(&r["np_res_nonres"]) - 19.278).abs() < 1e-9);
    assert!((num(&r["flats_area"]) - 218.127).abs() < 1e-9);
    assert!((num(&r["nnp"]) - 19.278).abs() < 1e-9);
    assert!((num(&r["density_spp"]) - 23.8).abs() < 1e-9);
    assert!((num(&r["density_np"]) - 21.42).abs() < 1e-9);
}

#[test]
fn calc2_yakimanka_population_and_social() {
    let e = yakimanka();
    let r = results_map(&e);
    assert_eq!(r["population"].py_repr(), "6610");
    assert_eq!(r["flats"].py_repr(), "3148");
    assert_eq!(r["doo_places"].py_repr(), "291");
    assert_eq!(r["school_places"].py_repr(), "595");
    assert_eq!(r["clinic_mixed_visits"].py_repr(), "126");
    // участки социальных объектов (ручной расчёт в docstring теста)
    let d = e.display("doo_plot_ha").unwrap();
    assert!((num(&d) - 0.931).abs() < 1e-9, "doo_plot_ha = {}", d.py_repr());
    let s = e.display("school_plot_ha").unwrap();
    assert!((num(&s) - 1.131).abs() < 1e-9, "school_plot_ha = {}", s.py_repr());
    assert_eq!(e.display("clinic_plot_ha").unwrap().py_repr(), "0.35");
    // точное значение без округления, как assertEqual(e.value("doo_plot_ha"), 291 * 32 / 10000)
    let exact = e.value("doo_plot_ha").unwrap();
    assert_eq!(exact.py_repr(), "0.9312");
}

#[test]
fn calc2_people_and_places_round_up() {
    // 33 м² ровно на человека — без лишнего округления вверх; 33,001 — уже ещё один человек
    let mut e = Engine::from_preset_str(calc2()).unwrap();
    e.set_inputs(&[
        ("spp_in".into(), f(3.3 / 0.65 / 0.94)),
        ("ratio_zh".into(), f(100.0)),
        ("nonres_part".into(), f(6.0)),
    ])
    .unwrap();
    assert_eq!(results_map(&e)["population"].py_repr(), "100");

    let mut e = Engine::from_preset_str(calc2()).unwrap();
    e.set_inputs(&[
        ("spp_in".into(), f(3.30033 / 0.65 / 0.94)),
        ("ratio_zh".into(), f(100.0)),
        ("nonres_part".into(), f(6.0)),
    ])
    .unwrap();
    assert_eq!(results_map(&e)["population"].py_repr(), "101");
}

#[test]
fn calc2_lowrise_50_sqm_per_person() {
    let mut e = Engine::from_preset_str(calc2()).unwrap();
    e.set_inputs(&[
        ("spp_in".into(), f(100.0)),
        ("ratio_zh".into(), f(100.0)),
        ("spp_low_in".into(), f(100.0)),
        ("nonres_part".into(), f(6.0)),
    ])
    .unwrap();
    let r = results_map(&e);
    assert_eq!(r["population"].py_repr(), "1300"); // 100 000 × 0,65 / 50
    assert_eq!(r["parking_perm"].py_repr(), "496"); // 65 000 / (50 × 2,1) × 0,8 = 495,2 → вверх
}

#[test]
fn calc2_zone_2_norms() {
    let mut e = Engine::from_preset_str(calc2()).unwrap();
    e.set_inputs(&[
        ("spp_in".into(), f(357.0)),
        ("ratio_zh".into(), f(100.0)),
        ("nonres_part".into(), f(6.0)),
        ("education_zone".into(), f(2.0)),
    ])
    .unwrap();
    let r = results_map(&e);
    assert_eq!(r["doo_places"].py_repr(), "417"); // 6610 × 63 / 1000 = 416,4 → вверх
    assert_eq!(r["school_places"].py_repr(), "820"); // × 124 = 819,6 → вверх
}

#[test]
fn calc2_constants_editable_and_recompute() {
    // как test_set_constants_recomputes_and_rejects_unknown
    let mut e = yakimanka();
    let school = e.value("school_places").unwrap().py_repr();
    e.set_constants(&[("doo_z1".into(), f(50.0))]).unwrap();
    let pop = e.value("population").unwrap();
    assert_eq!(e.value("school_places").unwrap().py_repr(), school);
    // doo_places = ceil(round(50 * pop / 1000, 6)) — пересчитался
    let doo = e.value("doo_places").unwrap();
    assert!(num(&doo) > 0.0);
    assert!(e.set_constants(&[("nope".into(), i(1))]).is_err());
}
