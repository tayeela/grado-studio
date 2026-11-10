//! Сверка с Python бит-в-бит: rust/parity/crs/reference.json пишет rust/parity/crs/dump_reference.py
//! (тот же core/connectors/grado_connectors/crs.py) на Linux. На Linux (CI, сайт) числа сравниваются по битам: синус,
//! степень и прочее у Rust и Python там из одной системной библиотеки. На Mac и Windows своя библиотека math —
//! там допуск 1e-9 (метры: нанометры, градусы: десятые доли миллиметра и меньше).

use grado_crs as crs;
use serde_json::Value;

fn f(v: &Value) -> f64 {
    v.as_f64().expect("число")
}

#[test]
fn same_bits_as_python() {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../parity/crs/reference.json"
    );
    let text = std::fs::read_to_string(path)
        .expect("reference.json: запустите rust/parity/crs/dump_reference.py");
    let cases: Value = serde_json::from_str(&text).unwrap();
    let mut n = 0usize;
    let mut bad = Vec::new();
    for c in cases.as_array().unwrap() {
        let fname = c["fn"].as_str().unwrap();
        let (a, b) = (f(&c["in"][0]), f(&c["in"][1]));
        let got = match fname {
            "merc_to_wgs84" => crs::merc_to_wgs84(a, b),
            "wgs84_to_merc" => crs::wgs84_to_merc(a, b),
            "wgs84_to_utm37n" => crs::wgs84_to_utm37n(a, b),
            "utm37n_to_wgs84" => crs::utm37n_to_wgs84(a, b),
            "merc_to_utm37n" => crs::merc_to_utm37n(a, b),
            "msk50_to_wgs84" => crs::msk50_to_wgs84(a, b),
            "wgs84_to_msk50" => crs::wgs84_to_msk50(a, b),
            "msk_to_wgs84" => crs::msk_to_wgs84(a, b),
            "wgs84_to_msk" => crs::wgs84_to_msk(a, b),
            "ogd_to_msk" => crs::ogd_to_msk(a, b),
            "hypot" => (crs::py_hypot(a, b), 0.0),
            other => panic!("неизвестная функция {other}"),
        };
        let want = (f(&c["out"][0]), f(&c["out"][1]));
        n += 1;
        let same = if cfg!(target_os = "linux") {
            got.0.to_bits() == want.0.to_bits() && got.1.to_bits() == want.1.to_bits()
        } else {
            (got.0 - want.0).abs() <= 1e-9 * want.0.abs().max(1.0)
                && (got.1 - want.1).abs() <= 1e-9 * want.1.abs().max(1.0)
        };
        if !same {
            bad.push(format!(
                "{fname}({a}, {b}): rust {:?} python {:?}",
                got, want
            ));
        }
    }
    assert!(n > 1000, "мало случаев: {n}");
    assert!(
        bad.is_empty(),
        "{} из {n} не совпали бит-в-бит:\n{}",
        bad.len(),
        bad[..bad.len().min(20)].join("\n")
    );
}
