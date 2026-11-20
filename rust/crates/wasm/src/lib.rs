//! Ядро ГРАДО в браузере: координаты, формат проекта, геометрия в МСК и рисование знаков одним кодом с сервером
//! (план 09.11.2026, шаги С1, С2, И1, И2).
//!
//! Интерфейс (`apps/grado3/ui/src/core.ts`) зовёт эти функции; точки — массивы [x, y], проект и геометрия — текст JSON.
//! Функции ниже обычные Rust: их же проверяют `cargo test`, а `wasm_bindgen` нужен только при сборке в WebAssembly.

use std::cell::RefCell;

use serde_json::Value;

#[cfg(target_arch = "wasm32")]
use wasm_bindgen::prelude::*;

thread_local! {
    static LINE_LIB: RefCell<Option<grado_symbol::LineLib>> = const { RefCell::new(None) };
}

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

fn ring_msk(v: &Value) -> Vec<(f64, f64)> {
    v.as_array()
        .map(|pts| {
            pts.iter()
                .filter_map(|p| {
                    let lon = p.get(0)?.as_f64()?;
                    let lat = p.get(1)?.as_f64()?;
                    if lon.is_finite() && lat.is_finite() {
                        Some(grado_crs::wgs84_to_msk(lon, lat))
                    } else {
                        None
                    }
                })
                .collect()
        })
        .unwrap_or_default()
}

fn collect_polys_msk(v: &Value, out: &mut Vec<Vec<Vec<(f64, f64)>>>) {
    if let Some(arr) = v.as_array() {
        for x in arr {
            collect_polys_msk(x, out);
        }
        return;
    }
    match v.get("type").and_then(Value::as_str) {
        Some("FeatureCollection") => {
            if let Some(fs) = v.get("features").and_then(Value::as_array) {
                for f in fs {
                    collect_polys_msk(f, out);
                }
            }
        }
        Some("Feature") => {
            if let Some(g) = v.get("geometry") {
                collect_polys_msk(g, out);
            }
        }
        Some("Polygon") => {
            if let Some(rings) = v.get("coordinates").and_then(Value::as_array) {
                let rs: Vec<Vec<(f64, f64)>> = rings
                    .iter()
                    .map(ring_msk)
                    .filter(|r| r.len() >= 3)
                    .collect();
                if !rs.is_empty() {
                    out.push(rs);
                }
            }
        }
        Some("MultiPolygon") => {
            if let Some(polys) = v.get("coordinates").and_then(Value::as_array) {
                for poly in polys {
                    if let Some(rings) = poly.as_array() {
                        let rs: Vec<Vec<(f64, f64)>> = rings
                            .iter()
                            .map(ring_msk)
                            .filter(|r| r.len() >= 3)
                            .collect();
                        if !rs.is_empty() {
                            out.push(rs);
                        }
                    }
                }
            }
        }
        _ => {}
    }
}

fn collect_lines_msk(v: &Value, out: &mut Vec<Vec<(f64, f64)>>) {
    if let Some(arr) = v.as_array() {
        for x in arr {
            collect_lines_msk(x, out);
        }
        return;
    }
    match v.get("type").and_then(Value::as_str) {
        Some("FeatureCollection") => {
            if let Some(fs) = v.get("features").and_then(Value::as_array) {
                for f in fs {
                    collect_lines_msk(f, out);
                }
            }
        }
        Some("Feature") => {
            if let Some(g) = v.get("geometry") {
                collect_lines_msk(g, out);
            }
        }
        Some("LineString") => {
            if let Some(c) = v.get("coordinates") {
                let ln = ring_msk(c);
                if ln.len() >= 2 {
                    out.push(ln);
                }
            }
        }
        Some("MultiLineString") => {
            if let Some(lines) = v.get("coordinates").and_then(Value::as_array) {
                for c in lines {
                    let ln = ring_msk(c);
                    if ln.len() >= 2 {
                        out.push(ln);
                    }
                }
            }
        }
        _ => {}
    }
}

/// Плановая площадь полигонов GeoJSON (Feature, FeatureCollection, Geometry в WGS84) в м² в МСК:
/// сумма площадей каждого полигона (внешнее кольцо минус дыры), как features.js sizeOf.
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub fn geojson_area_msk(text: &str) -> f64 {
    let Ok(v) = serde_json::from_str::<Value>(text) else {
        return 0.0;
    };
    let mut polys = Vec::new();
    collect_polys_msk(&v, &mut polys);
    polys
        .iter()
        .map(|rings| {
            let outer = grado_geom_rs::shoelace(&rings[0]).abs();
            let holes: f64 = rings[1..]
                .iter()
                .map(|r| grado_geom_rs::shoelace(r).abs())
                .sum();
            (outer - holes).max(0.0)
        })
        .sum()
}

/// Плановая длина линий GeoJSON (LineString, MultiLineString, Feature, FeatureCollection в WGS84) в м в МСК.
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub fn geojson_length_msk(text: &str) -> f64 {
    let Ok(v) = serde_json::from_str::<Value>(text) else {
        return 0.0;
    };
    let mut lines = Vec::new();
    collect_lines_msk(&v, &mut lines);
    lines
        .iter()
        .map(|ln| {
            ln.windows(2)
                .map(|w| (w[1].0 - w[0].0).hypot(w[1].1 - w[0].1))
                .sum::<f64>()
        })
        .sum()
}

/// Площадь объединения полигонов GeoJSON (WGS84) в м² в МСК без двойного счёта наложений (grado_geom_rs::overlay).
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub fn union_area_msk(text: &str) -> f64 {
    let Ok(v) = serde_json::from_str::<Value>(text) else {
        return 0.0;
    };
    let mut polys = Vec::new();
    collect_polys_msk(&v, &mut polys);
    if polys.is_empty() {
        return 0.0;
    }
    if polys.len() == 1 && polys[0].len() == 1 {
        // один полигон: нодинг чинит и самопересечения («бабочки»)
        return grado_geom_rs::overlay::union_intersection_area(&polys, &polys);
    }
    grado_geom_rs::overlay::union_intersection_area(&polys, &polys)
}

/// Площадь пересечения (∪ regions) ∩ (∪ clips) двух GeoJSON (WGS84) в м² в МСК (шаг С2).
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub fn overlay_area_msk(regions_text: &str, clips_text: &str) -> f64 {
    let (Ok(rv), Ok(cv)) = (
        serde_json::from_str::<Value>(regions_text),
        serde_json::from_str::<Value>(clips_text),
    ) else {
        return 0.0;
    };
    let (mut regions, mut clips) = (Vec::new(), Vec::new());
    collect_polys_msk(&rv, &mut regions);
    collect_polys_msk(&cv, &mut clips);
    if regions.is_empty() || clips.is_empty() {
        return 0.0;
    }
    grado_geom_rs::overlay::union_intersection_area(&regions, &clips)
}

/// Операции рендера слоёв знака (parts: line, band, hatch, marks) на Rust (crates/symbol, шаг И2):
/// в WebAssembly экспортируются `parts_ops` и `LineLib` самого крейта `grado_symbol`, а эта обёртка — для cargo test.
pub fn parts_ops(kind: &str, shapes_json: &str, parts_json: &str, px_mm: f64) -> String {
    grado_symbol::parts_ops_json(kind, shapes_json, parts_json, px_mm)
        .unwrap_or_else(|_| "[]".into())
}

/// Загружает библиотеку типов линий ЛГР (redln97.json) один раз в память ядра.
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub fn load_linetypes(lib_json: &str) -> bool {
    match grado_symbol::LineLib::from_json(lib_json) {
        Ok(lib) => {
            LINE_LIB.with(|cell| *cell.borrow_mut() = Some(lib));
            true
        }
        Err(_) => false,
    }
}

/// Есть ли тип линии `name` в загруженной библиотеке REDLN97.
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub fn has_linetype(name: &str) -> bool {
    LINE_LIB.with(|cell| cell.borrow().as_ref().map(|l| l.has(name)).unwrap_or(false))
}

/// Операции рендера типа линии ЛГР (REDLN97) вдоль ломаной `pts_json` ([[x, y], …] в пикселях экрана).
#[cfg_attr(target_arch = "wasm32", wasm_bindgen)]
pub fn linetype_ops(
    pts_json: &str,
    name: &str,
    k: f64,
    shape_k: f64,
    color: &str,
    width: f64,
) -> String {
    LINE_LIB.with(|cell| {
        let borrow = cell.borrow();
        let Some(lib) = borrow.as_ref() else {
            return "[]".into();
        };
        lib.ops_json(
            pts_json,
            name,
            k,
            (shape_k > 0.0).then_some(shape_k),
            color,
            width,
        )
        .unwrap_or_else(|_| "[]".into())
    })
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

    #[test]
    fn area_and_overlay_msk_work_on_geojson() {
        // квадрат 100×100 м в МСК → переводим углы в WGS84 и проверяем площадь обратно
        let c0 = msk_to_wgs84(1000.0, 2000.0);
        let c1 = msk_to_wgs84(1100.0, 2000.0);
        let c2 = msk_to_wgs84(1100.0, 2100.0);
        let c3 = msk_to_wgs84(1000.0, 2100.0);
        let sq = serde_json::json!({
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[c0[0], c0[1]], [c1[0], c1[1]], [c2[0], c2[1]], [c3[0], c3[1]], [c0[0], c0[1]]]]
            }
        })
        .to_string();
        assert!((geojson_area_msk(&sq) - 10_000.0).abs() < 0.01);
        // две копии того же квадрата: простая сумма 20 000 м², объединение — 10 000 м²
        let dup = format!("[{sq},{sq}]");
        assert!((geojson_area_msk(&dup) - 20_000.0).abs() < 0.02);
        assert!((union_area_msk(&dup) - 10_000.0).abs() < 0.01);
        assert!((overlay_area_msk(&sq, &sq) - 10_000.0).abs() < 0.01);
    }

    #[test]
    fn parts_and_linetypes_ops_run_in_core() {
        let ops: Value = serde_json::from_str(&parts_ops(
            "poly",
            "[[[[0,0],[100,0],[100,100],[0,100]]]]",
            r##"[{"k":"band","b":4,"c":"#2446d8","a":0.3}]"##,
            1.0,
        ))
        .unwrap();
        assert_eq!(ops.as_array().unwrap().len(), 3);
        let lib = r##"{"shapes":{},"linetypes":{"DASH":{"length":10,"pattern":[{"d":6},{"d":-4}]}}}"##;
        assert!(load_linetypes(lib));
        assert!(has_linetype("DASH"));
        let lops: Value = serde_json::from_str(&linetype_ops(
            "[[0,0],[100,0]]",
            "DASH",
            1.0,
            0.0,
            "#e01b24",
            2.0,
        ))
        .unwrap();
        assert!(!lops.as_array().unwrap().is_empty());
    }
}
