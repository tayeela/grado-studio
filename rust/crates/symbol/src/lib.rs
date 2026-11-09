//! Слои знака ГРАДО (план 08.11.2026, шаг 3: «один рисовальщик знака для экрана и печати»).
//!
//! Вход — стопка частей `parts` стиля слоя или класса (apps/grado2/ui/src/symbology.js `cleanParts`):
//! `line` (линия по контуру: цвет `c`, толщина `w`, штрих `dash`), `band` (полоса шириной `b` внутрь вдоль границы,
//! прозрачность `a`), `hatch` (штриховка: узор `hp`, шаг `hs`), `marks` (значки вдоль линии: `shape` tick/tri/dot/cross,
//! шаг `step`, размер `size`, сторона `side` — внутрь/наружу у полигона, справа/слева по ходу у линии).
//! Размеры частей — пиксели экрана; здесь они переводятся в мм листа множителем `px_mm` (печать — 0,26, как
//! print_io.PX_MM; экран — мм на пиксель карты = 1, тогда координаты — пиксели).
//!
//! Выход — операции рендера (как core/render/grado_render): `path` (кольца, заливка или контур), `clip` / `unclip`.
//! Их рисует пластина (crates/plate) для PDF и PPTX и canvas экрана (ui/src/symbology.js через WebAssembly).
//! Координаты — ось y вниз. Полоса внутрь — контур двойной ширины, обрезанный по полигону (как карта на экране),
//! без построения буфера. Python-двойник — apps/grado2/symparts.py (сверка — tests/test_symparts.py).

use serde_json::{json, Value};

pub const PX_MM: f64 = 0.26;

type Pt = (f64, f64);

fn num(v: &Value, d: f64) -> f64 {
    v.as_f64().filter(|x| x.is_finite() && *x != 0.0).unwrap_or(d)
}

/// '#rrggbb' → [r, g, b] 0..1. Прозрачность части не смешивается здесь: у операций части поле `alpha` — экран рисует
/// её прозрачной, печать (symparts.py) смешивает цвет с белым листом, как прежде.
pub fn rgb(c: &Value) -> Value {
    let s = c.as_str().unwrap_or("#333333").trim_start_matches('#');
    let h = |i: usize| s.get(i..i + 2).and_then(|x| u8::from_str_radix(x, 16).ok()).unwrap_or(0x33) as f64 / 255.0;
    json!([h(0), h(2), h(4)])
}

fn pts(v: &Value) -> Vec<Pt> {
    v.as_array()
        .map(|a| a.iter().filter_map(|p| Some((p.get(0)?.as_f64()?, p.get(1)?.as_f64()?))).collect())
        .unwrap_or_default()
}

fn area(r: &[Pt]) -> f64 {
    (0..r.len()).map(|i| { let p = r[(i + r.len() - 1) % r.len()]; p.0 * r[i].1 - r[i].0 * p.1 }).sum::<f64>() / 2.0
}

/// Кольца полигона так, чтобы внутренность была справа по ходу (y вниз: наружное по часовой на листе, дыры — наоборот)
fn right_inside(rings: &[Vec<Pt>]) -> Vec<Vec<Pt>> {
    rings
        .iter()
        .enumerate()
        .map(|(i, r)| {
            let want = i == 0;
            if (area(r) > 0.0) == want { r.clone() } else { r.iter().rev().cloned().collect() }
        })
        .collect()
}

/// Точки через step вдоль ломаной (первая — на step/2): (x, y, ux, uy) с единичным направлением хода
pub fn stations(line: &[Pt], step: f64, closed: bool) -> Vec<(f64, f64, f64, f64)> {
    let mut seq = line.to_vec();
    if closed && !line.is_empty() && line[0] != line[line.len() - 1] {
        seq.push(line[0]);
    }
    let (mut out, mut need) = (Vec::new(), step / 2.0);
    for w in seq.windows(2) {
        let ((x0, y0), (x1, y1)) = (w[0], w[1]);
        let d = (x1 - x0).hypot(y1 - y0);
        if d <= 1e-9 {
            continue;
        }
        let (ux, uy) = ((x1 - x0) / d, (y1 - y0) / d);
        let mut t = 0.0;
        while t + need <= d {
            t += need;
            out.push((x0 + ux * t, y0 + uy * t, ux, uy));
            need = step;
        }
        need -= d - t;
    }
    out
}

fn ring_json(r: &[Pt]) -> Value {
    Value::Array(r.iter().map(|p| json!([p.0, p.1])).collect())
}

fn path(rings: Vec<Value>, closed: bool, fill: Value, stroke: Value, width: f64, dash: Value) -> Value {
    json!({"op": "path", "rings": rings, "closed": closed, "fill": fill, "stroke": stroke, "width": width, "dash": dash})
}

/// Значок в точке: нормаль — в сторону side (справа по ходу при side > 0; y вниз: справа = (−uy, ux))
#[allow(clippy::too_many_arguments)]
fn mark(shape: &str, x: f64, y: f64, ux: f64, uy: f64, side: f64, s: f64, col: &Value, w: f64) -> Value {
    let (nx, ny) = (-uy * side, ux * side);
    match shape {
        "dot" => {
            let (cx, cy) = (x + nx * s / 2.0, y + ny * s / 2.0);
            let ring: Vec<Pt> = (0..12).map(|a| { let t = a as f64 * std::f64::consts::PI / 6.0; (cx + s / 2.0 * t.cos(), cy + s / 2.0 * t.sin()) }).collect();
            path(vec![ring_json(&ring)], true, col.clone(), Value::Null, 0.0, Value::Null)
        }
        "tri" => {
            let ring = [(x - ux * s / 2.0, y - uy * s / 2.0), (x + ux * s / 2.0, y + uy * s / 2.0), (x + nx * s, y + ny * s)];
            path(vec![ring_json(&ring)], true, col.clone(), Value::Null, 0.0, Value::Null)
        }
        "cross" => {
            let h = s / 2.0;
            path(vec![ring_json(&[(x - h, y - h), (x + h, y + h)]), ring_json(&[(x - h, y + h), (x + h, y - h)])], false, Value::Null, col.clone(), w, Value::Null)
        }
        _ => path(vec![ring_json(&[(x, y), (x + nx * s, y + ny * s)])], false, Value::Null, col.clone(), w, Value::Null),
    }
}

/// Штриховка внутри полигона (как grado_render.scene.hatch_ops): прямые семейства пересекаются с рёбрами колец,
/// пары точек по чётности — отрезки (дыры учтены). Угол 0/45/90/135.
pub fn hatch(rings: &[Vec<Pt>], spacing: f64, stroke: &Value, width: f64, angle: i32) -> Option<Value> {
    let all: Vec<Pt> = rings.iter().flatten().cloned().collect();
    if all.is_empty() {
        return None;
    }
    let (n_of, t_of, step): (fn(f64, f64) -> f64, fn(f64, f64) -> f64, f64) = match angle {
        0 => (|_, y| y, |x, _| x, spacing),
        90 => (|x, _| x, |_, y| y, spacing),
        135 => (|x, y| x - y, |x, y| x + y, spacing * 1.41421),
        _ => (|x, y| x + y, |x, y| x - y, spacing * 1.41421),
    };
    let vals: Vec<f64> = all.iter().map(|p| n_of(p.0, p.1)).collect();
    let lo = vals.iter().cloned().fold(f64::INFINITY, f64::min);
    let hi = vals.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let mut c = lo - lo.rem_euclid(step);
    let mut segs = Vec::new();
    while c <= hi {
        let mut hits: Vec<(f64, Pt)> = Vec::new();
        for r in rings {
            for i in 0..r.len() {
                let (p1, p2) = (r[i], r[(i + 1) % r.len()]);
                let (s1, s2) = (n_of(p1.0, p1.1) - c, n_of(p2.0, p2.1) - c);
                if (s1 > 0.0) == (s2 > 0.0) {
                    continue;
                }
                let t = s1 / (s1 - s2);
                let p = (p1.0 + (p2.0 - p1.0) * t, p1.1 + (p2.1 - p1.1) * t);
                hits.push((t_of(p.0, p.1), p));
            }
        }
        hits.sort_by(|a, b| a.0.total_cmp(&b.0));
        for pair in hits.chunks_exact(2) {
            segs.push(ring_json(&[pair[0].1, pair[1].1]));
        }
        c += step;
    }
    (!segs.is_empty()).then(|| path(segs, false, Value::Null, stroke.clone(), width, Value::Null))
}

fn angles(hp: &str) -> &'static [i32] {
    match hp {
        "0" => &[0],
        "90" => &[90],
        "135" => &[135],
        "x45" => &[45, 135],
        "x0" => &[0, 90],
        _ => &[45],
    }
}

/// Операции частей знака. kind — "poly" (shapes — полигоны, у каждого кольца) или "line" (shapes — ломаные);
/// px_mm — мм листа на пиксель размера части (печать 0,26; экран в пикселях — 1).
pub fn parts_ops(kind: &str, shapes: &Value, parts: &Value, px_mm: f64) -> Vec<Value> {
    let poly = kind == "poly";
    let polys: Vec<Vec<Vec<Pt>>> = shapes
        .as_array()
        .map(|a| a.iter().map(|s| if poly { s.as_array().map(|r| r.iter().map(pts).collect()).unwrap_or_default() } else { vec![pts(s)] }).collect())
        .unwrap_or_default();
    let mut out = Vec::new();
    for p in parts.as_array().map(|v| v.as_slice()).unwrap_or(&[]) {
        let k = p["k"].as_str().unwrap_or("");
        let w = (num(&p["w"], 1.0) * px_mm).max(0.05 * px_mm / PX_MM);
        let col = rgb(&p["c"]);
        let alpha = p["a"].as_f64().unwrap_or(1.0).clamp(0.0, 1.0);
        let from = out.len();
        let dash = p["dash"].as_array().filter(|d| !d.is_empty()).map(|d| Value::Array(d.iter().map(|x| json!((x.as_f64().unwrap_or(1.0) * px_mm).max(0.1 * px_mm / PX_MM))).collect())).unwrap_or(Value::Null);
        match k {
            "line" => {
                for rings in &polys {
                    out.push(path(rings.iter().map(|r| ring_json(r)).collect(), poly, Value::Null, col.clone(), w, dash.clone()));
                }
            }
            "band" if poly => {
                let b = (num(&p["b"], 6.0) * px_mm).max(0.1 * px_mm / PX_MM);
                for rings in &polys {
                    let rj: Vec<Value> = rings.iter().map(|r| ring_json(r)).collect();
                    out.push(json!({"op": "clip", "rings": rj.clone()}));
                    let mut s = path(rj, true, Value::Null, col.clone(), 2.0 * b, Value::Null);
                    s["join"] = json!("round");
                    out.push(s);
                    out.push(json!({"op": "unclip"}));
                }
            }
            "hatch" if poly => {
                let step = (num(&p["hs"], 8.0) * px_mm).max(0.8 * px_mm / PX_MM);
                for rings in &polys {
                    for &a in angles(p["hp"].as_str().unwrap_or("45")) {
                        out.extend(hatch(rings, step, &col, (w / 2.0).max(0.08 * px_mm / PX_MM), a));
                    }
                }
            }
            "marks" => {
                let step = (num(&p["step"], 16.0) * px_mm).max(0.5 * px_mm / PX_MM);
                let size = (num(&p["size"], 5.0) * px_mm).max(0.3 * px_mm / PX_MM);
                let side = if p["side"].as_f64().unwrap_or(1.0) < 0.0 { -1.0 } else { 1.0 };
                let shape = p["shape"].as_str().unwrap_or("tick");
                let lines: Vec<Vec<Pt>> = if poly { polys.iter().flat_map(|r| right_inside(r)).collect() } else { polys.iter().flatten().cloned().collect() };
                for ln in lines.iter().filter(|l| l.len() >= 2) {
                    for (x, y, ux, uy) in stations(ln, step, poly) {
                        out.push(mark(shape, x, y, ux, uy, side, size, &col, w));
                    }
                }
            }
            _ => {}
        }
        if alpha < 1.0 {
            for o in out[from..].iter_mut().filter(|o| o["op"] == "path") {
                o["alpha"] = json!(alpha);
            }
        }
    }
    out
}

/// Строковый вход-выход (мост Python и WebAssembly): JSON частей и фигур → JSON операций
pub fn parts_ops_json(kind: &str, shapes_json: &str, parts_json: &str, px_mm: f64) -> Result<String, String> {
    let shapes: Value = serde_json::from_str(shapes_json).map_err(|e| format!("фигуры: {e}"))?;
    let parts: Value = serde_json::from_str(parts_json).map_err(|e| format!("слои знака: {e}"))?;
    Ok(Value::Array(parts_ops(kind, &shapes, &parts, px_mm)).to_string())
}

#[cfg(target_arch = "wasm32")]
mod wasm {
    use wasm_bindgen::prelude::*;
    /// Экран: операции частей знака в пикселях карты (px_mm = 1) — их рисует canvas слоя (symbology.js)
    #[wasm_bindgen]
    pub fn parts_ops(kind: &str, shapes_json: &str, parts_json: &str, px_mm: f64) -> Result<String, JsValue> {
        super::parts_ops_json(kind, shapes_json, parts_json, px_mm).map_err(|e| JsValue::from_str(&e))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sq() -> Value { json!([[[[0, 0], [100, 0], [100, 100], [0, 100]]]]) }

    #[test]
    fn marks_inside_any_direction() {
        for ring in [json!([[[0, 0], [100, 0], [100, 100], [0, 100]]]), json!([[[0, 0], [0, 100], [100, 100], [100, 0]]])] {
            let ops = parts_ops("poly", &json!([ring]), &json!([{"k": "marks", "shape": "tick", "step": 20, "size": 5, "side": 1}]), 1.0);
            assert_eq!(ops.len(), 20);
            for o in &ops {
                let r = &o["rings"][0];
                let (x, y) = (r[1][0].as_f64().unwrap(), r[1][1].as_f64().unwrap());
                assert!((0.0..=100.0).contains(&x) && (0.0..=100.0).contains(&y), "конец штриха внутри: {x} {y}");
            }
        }
    }

    #[test]
    fn band_is_clipped_double_stroke() {
        let ops = parts_ops("poly", &sq(), &json!([{"k": "band", "b": 6, "c": "#ff0000", "a": 0.5}]), PX_MM);
        assert_eq!(ops[0]["op"], "clip");
        assert!((ops[1]["width"].as_f64().unwrap() - 2.0 * 6.0 * PX_MM).abs() < 1e-9);
        assert_eq!(ops[2]["op"], "unclip");
        assert_eq!((ops[1]["stroke"].clone(), ops[1]["alpha"].clone()), (json!([1.0, 0.0, 0.0]), json!(0.5)));
    }

    #[test]
    fn hatch_cross_two_ops() {
        let ops = parts_ops("poly", &sq(), &json!([{"k": "hatch", "hp": "x45", "hs": 10}]), 1.0);
        assert_eq!(ops.len(), 2);
        assert!(ops[0]["rings"].as_array().unwrap().len() > 10);
    }

    #[test]
    fn line_stations_step() {
        let st = stations(&[(0.0, 0.0), (100.0, 0.0)], 20.0, false);
        assert_eq!(st.len(), 5);
        assert!((st[0].0 - 10.0).abs() < 1e-9 && (st[4].0 - 90.0).abs() < 1e-9);
    }
}
