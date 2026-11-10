//! Сверка с Python. Эталон пишет rust/parity/crs/dump_reference.py (тот же core/connectors/grado_connectors/crs.py).
//! Бит-в-бит — только с эталоном, снятым на этой же машине: путь в GRADO_CRS_REF (так делает CI). Синус, tan, asinh
//! у Rust и Python тогда из одной системной libm. С закоммиченным rust/parity/crs/reference.json — допуск 1e-9:
//! другая версия glibc, Mac, Windows дают другой последний бит (метры: нанометры, градусы: доли миллиметра).

use grado_crs as crs;
use serde_json::Value;

fn f(v: &Value) -> f64 {
    v.as_f64().expect("число")
}

#[test]
fn same_bits_as_python() {
    let fresh = std::env::var("GRADO_CRS_REF").ok();
    let path = fresh.clone().unwrap_or_else(|| {
        concat!(env!("CARGO_MANIFEST_DIR"), "/../../parity/crs/reference.json").to_string()
    });
    let exact = fresh.is_some();
    let text = std::fs::read_to_string(&path)
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
        let same = if exact {
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
        "{} из {n} не совпали ({}):\n{}",
        bad.len(),
        if exact { "бит-в-бит" } else { "допуск 1e-9" },
        bad[..bad.len().min(20)].join("\n")
    );
}
