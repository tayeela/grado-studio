//! Типы линий ЛГР (REDLN97: сложные типы линий AutoCAD из LIN + SHX) вдоль ломаной — один код для печати и экрана
//! (план 08.11.2026, шаг 3). Библиотека — core/render/grado_render/styles/redln97.json (tools/gen_redln97.py).
//! Python-двойник и эталон сверки — apps/grado2/print_io.py `linetype_ops_py` (tests/test_symparts.py), прежний
//! экранный рисовальщик — web/linetype.js (остаётся запасным путём без WebAssembly).
//!
//! k — единиц вывода на единицу шаблона (печать: мм листа на метр шаблона, LT_MM; экран: пиксели на метр местности);
//! shape_k — свой масштаб знаков (засечки, треугольники), иначе k. Ось y вниз, «слева по ходу» = (uy, −ux).
//! Знаки рисуются своей толщиной min(width, 0,12 · масштаб знака) со скруглёнными изломами — иначе на мелком знаке
//! толстая линия превращает его в пятно (владелец 05.10.2026: «условные ЛГР битые»). Нулевой штрих (d = 0) — точка.

use std::collections::HashMap;

use serde_json::{json, Value};

pub type Pt = (f64, f64);

enum Elem {
    Dash(f64),
    Shape { name: String, s: f64, r: f64, x: f64, y: f64, abs: bool },
}

struct Lt {
    length: f64,
    pattern: Vec<Elem>,
}

pub struct LineLib {
    lts: HashMap<String, Lt>,
    shapes: HashMap<String, Vec<Vec<Pt>>>,
}

fn f(v: &Value, d: f64) -> f64 {
    v.as_f64().unwrap_or(d)
}

/// Цвет: '#rrggbb' или [r, g, b] 0..1 (как у Python-вызова)
fn color(c: &Value) -> Value {
    if c.is_array() { c.clone() } else { crate::rgb(c) }
}

fn rj(r: &[Pt]) -> Value {
    Value::Array(r.iter().map(|p| json!([p.0, p.1])).collect())
}

impl LineLib {
    pub fn from_json(s: &str) -> Result<Self, String> {
        let v: Value = serde_json::from_str(s).map_err(|e| format!("библиотека типов линий: {e}"))?;
        let mut shapes = HashMap::new();
        for (n, sh) in v["shapes"].as_object().into_iter().flatten() {
            let paths = sh["paths"].as_array().into_iter().flatten()
                .map(|p| p.as_array().into_iter().flatten().filter_map(|q| Some((q.get(0)?.as_f64()?, q.get(1)?.as_f64()?))).collect())
                .collect();
            shapes.insert(n.to_uppercase(), paths);
        }
        let mut lts = HashMap::new();
        for (n, lt) in v["linetypes"].as_object().into_iter().flatten() {
            let pattern = lt["pattern"].as_array().into_iter().flatten().filter_map(|e| {
                if let Some(d) = e.get("d").and_then(Value::as_f64) {
                    Some(Elem::Dash(d))
                } else {
                    let name = e.get("shape")?.as_str().filter(|s| !s.is_empty())?.to_uppercase();
                    Some(Elem::Shape { name, s: f(&e["s"], 1.0), r: f(&e["r"], 0.0), x: f(&e["x"], 0.0), y: f(&e["y"], 0.0), abs: e["abs"].as_bool().unwrap_or(false) })
                }
            }).collect();
            lts.insert(n.clone(), Lt { length: f(&lt["length"], 0.0), pattern });
        }
        Ok(LineLib { lts, shapes })
    }

    pub fn has(&self, name: &str) -> bool {
        self.lts.contains_key(name)
    }

    /// Штрихи и знаки типа линии name вдоль pts: [(толщина, скруглять изломы, кольца)]. Короче двух длин шаблона —
    /// сплошная линия (правило AutoCAD). Без serde — мост Python строит из них объекты сам (так в разы быстрее JSON).
    pub fn runs(&self, pts: &[Pt], name: &str, k: f64, shape_k: Option<f64>, width: f64) -> Vec<Run> {
        let (mut seg, mut cum) = (Vec::new(), vec![0.0]);
        for w in pts.windows(2) {
            let d = (w[1].0 - w[0].0).hypot(w[1].1 - w[0].1);
            seg.push(d);
            cum.push(cum[cum.len() - 1] + d);
        }
        let total = cum[cum.len() - 1];
        let lt = match self.lts.get(name) {
            Some(lt) if !seg.is_empty() && total >= 2.0 * lt.length * k && lt.length > 0.0 => lt,
            _ => return vec![Run { width, round: false, rings: vec![pts.to_vec()] }],
        };
        let mut pos = 0usize;                                // t растёт монотонно — указатель по отрезкам
        let at = |t: f64, pos: &mut usize| {
            let mut i = *pos;
            while i < seg.len() - 1 && cum[i + 1] < t {
                i += 1;
            }
            *pos = i;
            let fr = if seg[i] > 0.0 { (t - cum[i]) / seg[i] } else { 0.0 };
            let (a, b) = (pts[i], pts[i + 1]);
            let (ux, uy) = if seg[i] > 0.0 { ((b.0 - a.0) / seg[i], (b.1 - a.1) / seg[i]) } else { (1.0, 0.0) };
            (a.0 + (b.0 - a.0) * fr, a.1 + (b.1 - a.1) * fr, ux, uy)
        };
        let kk = shape_k.unwrap_or(k);
        let (mut rings, mut marks): (Vec<Vec<Pt>>, Vec<Run>) = (Vec::new(), Vec::new());
        let (mut t, mut guard) = (0.0, 0);
        while t < total && guard < 20000 {
            guard += 1;
            for e in &lt.pattern {
                if t >= total {
                    break;
                }
                match e {
                    Elem::Dash(d) => {
                        let d = d * k;
                        if d > 0.0 {
                            let t1 = (t + d).min(total);
                            let (sx, sy, _, _) = at(t, &mut pos);
                            let i0 = pos;
                            let (ex, ey, _, _) = at(t1, &mut pos);
                            let mut r = vec![(sx, sy)];
                            r.extend((i0 + 1..=pos).filter(|&i| t < cum[i] && cum[i] < t1).map(|i| pts[i]));
                            r.push((ex, ey));
                            rings.push(r);
                        } else if d == 0.0 {                 // точка: квадратик толщиной линии
                            let (x, y, ux, uy) = at(t, &mut pos);
                            let h = width / 2.0;
                            rings.push(vec![(x - ux * h, y - uy * h), (x + ux * h, y + uy * h)]);
                        }
                        t += d.abs();
                    }
                    Elem::Shape { name, s, r, x, y, abs } => {
                        let Some(paths) = self.shapes.get(name) else { continue };
                        let (px, py, ux, uy) = at(t, &mut pos);
                        let (vx, vy) = (uy, -ux);
                        let rr = r.to_radians();
                        let (cr, sr, sc) = (rr.cos(), rr.sin(), s * kk);
                        let (ax, ay, bx, by) = if *abs { (1.0, 0.0, 0.0, -1.0) } else { (ux, uy, vx, vy) };
                        let ox = px + x * k * ux + y * kk * vx;
                        let oy = py + x * k * uy + y * kk * vy;
                        let sw = (width.min(0.12 * sc) * 1e4).round() / 1e4;
                        let i = match marks.iter().position(|m| m.width == sw) {
                            Some(i) => i,
                            None => { marks.push(Run { width: sw, round: true, rings: Vec::new() }); marks.len() - 1 }
                        };
                        for p in paths {
                            let ring: Vec<Pt> = p.iter().map(|&(qx, qy)| {
                                let (lx, ly) = ((qx * cr - qy * sr) * sc, (qx * sr + qy * cr) * sc);
                                (ox + lx * ax + ly * bx, oy + lx * ay + ly * by)
                            }).collect();
                            if ring.len() > 1 {
                                marks[i].rings.push(ring);
                            }
                        }
                    }
                }
            }
        }
        let mut out = Vec::new();
        if !rings.is_empty() {
            out.push(Run { width, round: false, rings });
        }
        out.extend(marks);
        out
    }

    /// Операции рендера (как print_io.linetype_ops): path без заливки цвета col, у знаков join round
    pub fn ops(&self, pts: &[Pt], name: &str, k: f64, shape_k: Option<f64>, col: &Value, width: f64) -> Vec<Value> {
        let col = color(col);
        self.runs(pts, name, k, shape_k, width).into_iter().map(|r| {
            let mut o = json!({"op": "path", "closed": false, "fill": null, "stroke": col, "width": r.width, "dash": null,
                               "rings": r.rings.iter().map(|x| rj(x)).collect::<Vec<_>>()});
            if r.round {
                o["join"] = json!("round");
            }
            o
        }).collect()
    }

    /// Строковый вход-выход для WebAssembly: pts — JSON ломаной [[x, y], …], цвет — '#rrggbb' или JSON [r, g, b]
    pub fn ops_json(&self, pts_json: &str, name: &str, k: f64, shape_k: Option<f64>, col: &str, width: f64) -> Result<String, String> {
        let p: Value = serde_json::from_str(pts_json).map_err(|e| format!("линия: {e}"))?;
        let pts: Vec<Pt> = p.as_array().into_iter().flatten().filter_map(|q| Some((q.get(0)?.as_f64()?, q.get(1)?.as_f64()?))).collect();
        if pts.len() < 2 {
            return Ok("[]".into());
        }
        let c = serde_json::from_str::<Value>(col).unwrap_or_else(|_| Value::String(col.into()));
        Ok(Value::Array(self.ops(&pts, name, k, shape_k, &c, width)).to_string())
    }
}

/// Один проход пера: толщина, скругление изломов (знаки), кольца-ломаные
pub struct Run {
    pub width: f64,
    pub round: bool,
    pub rings: Vec<Vec<Pt>>,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lib() -> LineLib {
        LineLib::from_json(r#"{"shapes": {"tri": {"paths": [[[0, 0], [0.5, 1], [1, 0]]]}},
            "linetypes": {"T": {"length": 4, "pattern": [{"d": 2}, {"d": -1}, {"shape": "TRI", "s": 1, "x": 0, "y": 0}, {"d": -1}]},
                          "D": {"length": 2, "pattern": [{"d": 0}, {"d": -2}]}}}"#).unwrap()
    }

    #[test]
    fn short_line_is_solid() {
        let ops = lib().ops(&[(0.0, 0.0), (5.0, 0.0)], "T", 1.0, None, &json!("#ff0000"), 0.5);
        assert_eq!(ops.len(), 1);
        assert_eq!(ops[0]["rings"][0].as_array().unwrap().len(), 2);
        assert_eq!(ops[0]["stroke"], json!([1.0, 0.0, 0.0]));
    }

    #[test]
    fn dashes_and_marks() {
        let ops = lib().ops(&[(0.0, 0.0), (20.0, 0.0)], "T", 1.0, None, &json!([0, 0, 0]), 0.5);
        assert_eq!(ops.len(), 2, "штрихи и знаки");
        assert_eq!(ops[0]["rings"].as_array().unwrap().len(), 5);
        assert_eq!(ops[1]["rings"].as_array().unwrap().len(), 5);
        assert_eq!(ops[1]["width"], json!(0.12));
        assert_eq!(ops[1]["join"], json!("round"));
        // знак слева по ходу (y вниз): вершина треугольника над линией
        assert!(ops[1]["rings"][0][1][1].as_f64().unwrap() < 0.0);
    }

    #[test]
    fn zero_dash_is_dot_and_bends_kept() {
        let ops = lib().ops(&[(0.0, 0.0), (10.0, 0.0)], "D", 1.0, None, &json!("#000000"), 0.4);
        assert_eq!(ops[0]["rings"].as_array().unwrap().len(), 5);
        let t = lib().ops(&[(0.0, 0.0), (9.0, 0.0), (9.0, 10.0)], "T", 1.0, None, &json!("#000000"), 0.5);
        let bent = t[0]["rings"].as_array().unwrap().iter().any(|r| r.as_array().unwrap().len() == 3);
        assert!(bent, "штрих через излом идёт по вершине");
    }
}
