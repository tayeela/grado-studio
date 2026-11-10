//! Ядро ГРАДО в браузере: те же координаты и тот же формат проекта, что на сервере, одним кодом.
//!
//! Интерфейс (`apps/grado3/ui/src/core.ts`) зовёт эти функции; точки — массивы [x, y], проект — текст JSON.
//! Функции ниже обычные Rust: их же проверяют `cargo test`, а `wasm_bindgen` нужен только при сборке в WebAssembly.

#[cfg(target_arch = "wasm32")]
use wasm_bindgen::prelude::*;

/// МСК (X восток, Y север, м) → [долгота, широта] WGS84.
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub fn msk_to_wgs84(x: f64, y: f64) -> Vec<f64> {
    let (a, b) = grado_crs::msk_to_wgs84(x, y);
    vec![a, b]
}

/// [долгота, широта] WGS84 → МСК.
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub fn wgs84_to_msk(lon: f64, lat: f64) -> Vec<f64> {
    let (a, b) = grado_crs::wgs84_to_msk(lon, lat);
    vec![a, b]
}

/// Родные координаты ГИС ОГД → МСК (сдвиг).
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub fn ogd_to_msk(x: f64, y: f64) -> Vec<f64> {
    let (a, b) = grado_crs::ogd_to_msk(x, y);
    vec![a, b]
}

/// Много точек за один вызов: [x0, y0, x1, y1, …] МСК → то же в WGS84 (быстрее, чем по точке).
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub fn msk_to_wgs84_many(xy: &[f64]) -> Vec<f64> {
    xy.chunks_exact(2)
        .flat_map(|p| msk_to_wgs84(p[0], p[1]))
        .collect()
}

/// Много точек: WGS84 → МСК.
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub fn wgs84_to_msk_many(ll: &[f64]) -> Vec<f64> {
    ll.chunks_exact(2)
        .flat_map(|p| wgs84_to_msk(p[0], p[1]))
        .collect()
}

/// Проверка файла проекта → отчёт (JSON, тип `Report` из `types/check.ts`).
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub fn check_project(text: &str) -> String {
    serde_json::to_string(&grado_model::check_text(text)).unwrap()
}

/// Перевод старого файла на нынешние имена (как web/migrate.js) → текст JSON; не JSON — как был.
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub fn migrate_project(text: &str) -> String {
    match serde_json::from_str::<serde_json::Value>(text) {
        Ok(mut v) => {
            grado_model::migrate(&mut v);
            serde_json::to_string(&v).unwrap()
        }
        Err(_) => text.to_string(),
    }
}

/// Номер формата проекта, который знает ядро.
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub fn project_format_version() -> u32 {
    grado_model::VERSION as u32
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn many_equals_one() {
        let one = msk_to_wgs84(1234.5, -6789.0);
        assert_eq!(
            msk_to_wgs84_many(&[1234.5, -6789.0, 0.0, 0.0])[..2],
            one[..]
        );
        let back = wgs84_to_msk_many(&one);
        assert!((back[0] - 1234.5).abs() < 1e-3 && (back[1] + 6789.0).abs() < 1e-3);
    }

    #[test]
    fn check_reports_json() {
        let r: serde_json::Value =
            serde_json::from_str(&check_project(r#"{"format":"grado2","version":2}"#)).unwrap();
        assert_eq!(r["ok"], true);
        assert_eq!(migrate_project("не json"), "не json");
    }
}
