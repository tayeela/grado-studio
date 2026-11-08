//! Пластина карты ГРАДО: тот же список операций, что исполняют PDF-, SVG- и PPTX-бэкенды
//! (core/render/grado_render), растеризуется в картинку заданного dpi.
//!
//! Операции в миллиметрах листа, y вниз:
//! - `path` — кольца `rings`, `closed`, заливка `fill` (r,g,b 0..1) с `alpha`, контур `stroke` толщины `width` (мм),
//!   штрих `dash` (мм), `evenodd` (или несколько колец — по чётности, как SVG-бэкенд), `join: "round"`;
//! - `circle` — `x`, `y`, `r`, `fill`, `stroke`, `width`;
//! - `clip` — прямоугольник `rect` [x, y, w, h] или кольца `rings` (по чётности), `unclip` — снять последний;
//! - `image` — JPEG `data_b64` в прямоугольник `x, y, w, h` или параллелограмм `quad` [[tl], [tr], [bl]];
//! - `text`, `layer` и прочие — пропускаются: подписи остаются векторными поверх пластины (PDF, PPTX).
//!
//! Цель — одна картинка карты для экрана, PDF и PPTX: что видно на листе, то и в выдаче.

use base64::Engine as _;
use serde_json::Value;
use tiny_skia::{
    FillRule, LineCap, LineJoin, Mask, Paint, PathBuilder, Pixmap, PixmapPaint, Rect, Stroke, StrokeDash, Transform,
};

#[derive(Debug)]
pub struct PlateError(pub String);

impl std::fmt::Display for PlateError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

/// Итог: картинка и счётчики (сколько операций нарисовано и пропущено) — для проверки «карта не пустая».
pub struct Plate {
    pub pixmap: Pixmap,
    pub drawn: usize,
    pub skipped: usize,
}

impl Plate {
    pub fn png(&self) -> Result<Vec<u8>, PlateError> {
        self.pixmap.encode_png().map_err(|e| PlateError(format!("PNG: {e}")))
    }
    /// Доля закрашенных (не белых) пикселей: пустая или потерянная карта — около нуля.
    pub fn ink(&self) -> f64 {
        let px = self.pixmap.pixels();
        let n = px.iter().filter(|p| p.red() < 250 || p.green() < 250 || p.blue() < 250).count();
        n as f64 / px.len().max(1) as f64
    }
}

fn num(v: &Value) -> Option<f32> {
    v.as_f64().map(|x| x as f32).filter(|x| x.is_finite())
}

fn color(v: &Value, alpha: f32) -> Option<tiny_skia::Color> {
    let a = v.as_array()?;
    if a.len() < 3 {
        return None;
    }
    let c = |i: usize| num(&a[i]).unwrap_or(0.0).clamp(0.0, 1.0);
    tiny_skia::Color::from_rgba(c(0), c(1), c(2), alpha.clamp(0.0, 1.0))
}

fn point(v: &Value) -> Option<(f32, f32)> {
    let a = v.as_array()?;
    Some((num(a.first()?)?, num(a.get(1)?)?))
}

fn rings_path(rings: &Value, closed: bool) -> Option<tiny_skia::Path> {
    let mut pb = PathBuilder::new();
    for ring in rings.as_array()? {
        let pts: Vec<(f32, f32)> = ring.as_array()?.iter().filter_map(point).collect();
        if pts.is_empty() {
            continue;
        }
        pb.move_to(pts[0].0, pts[0].1);
        for p in &pts[1..] {
            pb.line_to(p.0, p.1);
        }
        if closed {
            pb.close();
        }
    }
    pb.finish()
}

fn paint(c: tiny_skia::Color) -> Paint<'static> {
    let mut p = Paint::default();
    p.set_color(c);
    p.anti_alias = true;
    p
}

fn stroke_of(o: &Value) -> Stroke {
    let mut s = Stroke { width: num(&o["width"]).unwrap_or(0.3).max(0.0), ..Stroke::default() };
    if o["join"].as_str() == Some("round") {
        s.line_join = LineJoin::Round;
        s.line_cap = LineCap::Round;
    }
    if let Some(d) = o["dash"].as_array() {
        let mut v: Vec<f32> = d.iter().filter_map(num).map(|x| x.max(0.01)).collect();
        if v.len() % 2 == 1 {
            v.extend(v.clone());
        }
        if v.len() >= 2 {
            s.dash = StrokeDash::new(v, 0.0);
        }
    }
    s
}

fn decode_jpeg(b64: &str) -> Option<Pixmap> {
    let bytes = base64::engine::general_purpose::STANDARD.decode(b64).ok()?;
    let mut dec = jpeg_decoder::Decoder::new(&bytes[..]);
    let data = dec.decode().ok()?;
    let info = dec.info()?;
    let (w, h) = (info.width as u32, info.height as u32);
    let mut pm = Pixmap::new(w, h)?;
    let px = pm.pixels_mut();
    match info.pixel_format {
        jpeg_decoder::PixelFormat::RGB24 => {
            for (i, c) in data.chunks_exact(3).enumerate().take(px.len()) {
                px[i] = tiny_skia::PremultipliedColorU8::from_rgba(c[0], c[1], c[2], 255)?;
            }
        }
        jpeg_decoder::PixelFormat::L8 => {
            for (i, &g) in data.iter().enumerate().take(px.len()) {
                px[i] = tiny_skia::PremultipliedColorU8::from_rgba(g, g, g, 255)?;
            }
        }
        _ => return None,
    }
    Some(pm)
}

/// Операции `ops` (JSON-массив) на лист `w_mm × h_mm` при `dpi` → пластина на белом фоне.
pub fn render(ops: &Value, w_mm: f32, h_mm: f32, dpi: f32) -> Result<Plate, PlateError> {
    let k = dpi / 25.4;
    let (pw, ph) = ((w_mm * k).ceil().max(1.0) as u32, (h_mm * k).ceil().max(1.0) as u32);
    if (pw as u64) * (ph as u64) > 400_000_000 {
        return Err(PlateError(format!("пластина {pw}×{ph} слишком велика")));
    }
    let mut pm = Pixmap::new(pw, ph).ok_or_else(|| PlateError("пустой размер пластины".into()))?;
    pm.fill(tiny_skia::Color::WHITE);
    let tf = Transform::from_scale(k, k);
    let mut clips: Vec<Option<Mask>> = Vec::new();
    let (mut drawn, mut skipped) = (0usize, 0usize);
    let list = ops.as_array().ok_or_else(|| PlateError("ops — не список".into()))?;
    for o in list {
        let mask = clips.iter().rev().flatten().next();
        match o["op"].as_str().unwrap_or("") {
            "clip" => {
                let path = if o["rings"].as_array().is_some_and(|r| !r.is_empty()) {
                    rings_path(&o["rings"], true)
                } else {
                    let r = o["rect"].as_array();
                    r.and_then(|r| {
                        Rect::from_xywh(num(r.first()?)?, num(r.get(1)?)?, num(r.get(2)?)?, num(r.get(3)?)?)
                    })
                    .map(PathBuilder::from_rect)
                };
                let m = path.and_then(|p| {
                    let mut m = match mask {
                        Some(prev) => prev.clone(),
                        None => {
                            let mut m = Mask::new(pw, ph)?;
                            m.data_mut().fill(255);
                            m
                        }
                    };
                    m.intersect_path(&p, FillRule::EvenOdd, true, tf);
                    Some(m)
                });
                clips.push(m);
            }
            "unclip" => {
                clips.pop();
            }
            "path" => {
                let closed = o["closed"].as_bool().unwrap_or(false);
                let Some(path) = rings_path(&o["rings"], closed) else {
                    skipped += 1;
                    continue;
                };
                let multi = o["rings"].as_array().map_or(0, |r| r.len()) > 1;
                let rule = if o["evenodd"].as_bool().unwrap_or(false) || multi { FillRule::EvenOdd } else { FillRule::Winding };
                let alpha = num(&o["alpha"]).unwrap_or(1.0);
                if let Some(c) = color(&o["fill"], alpha) {
                    pm.fill_path(&path, &paint(c), rule, tf, mask);
                }
                let st = stroke_of(o);
                if st.width > 0.0 {
                    if let Some(c) = color(&o["stroke"], 1.0) {
                        pm.stroke_path(&path, &paint(c), &st, tf, mask);
                    }
                }
                drawn += 1;
            }
            "circle" => {
                let (Some(x), Some(y), Some(r)) = (num(&o["x"]), num(&o["y"]), num(&o["r"])) else {
                    skipped += 1;
                    continue;
                };
                let Some(path) = PathBuilder::from_circle(x, y, r.max(0.001)) else {
                    skipped += 1;
                    continue;
                };
                if let Some(c) = color(&o["fill"], 1.0) {
                    pm.fill_path(&path, &paint(c), FillRule::Winding, tf, mask);
                }
                let st = stroke_of(o);
                if st.width > 0.0 {
                    if let Some(c) = color(&o["stroke"], 1.0) {
                        pm.stroke_path(&path, &paint(c), &st, tf, mask);
                    }
                }
                drawn += 1;
            }
            "image" => {
                let Some(img) = o["data_b64"].as_str().and_then(decode_jpeg) else {
                    skipped += 1;
                    continue;
                };
                let (iw, ih) = (img.width() as f32, img.height() as f32);
                // единичный квадрат картинки → прямоугольник или параллелограмм листа, как matrix() SVG-бэкенда
                let m = if let Some(q) = o["quad"].as_array() {
                    let (Some(tl), Some(tr), Some(bl)) =
                        (q.first().and_then(point), q.get(1).and_then(point), q.get(2).and_then(point))
                    else {
                        skipped += 1;
                        continue;
                    };
                    Transform::from_row(tr.0 - tl.0, tr.1 - tl.1, bl.0 - tl.0, bl.1 - tl.1, tl.0, tl.1)
                } else {
                    let (Some(x), Some(y), Some(w), Some(h)) = (num(&o["x"]), num(&o["y"]), num(&o["w"]), num(&o["h"])) else {
                        skipped += 1;
                        continue;
                    };
                    Transform::from_row(w, 0.0, 0.0, h, x, y)
                };
                let full = tf.pre_concat(m).pre_scale(1.0 / iw, 1.0 / ih);
                let pp = PixmapPaint { quality: tiny_skia::FilterQuality::Bilinear, ..PixmapPaint::default() };
                pm.draw_pixmap(0, 0, img.as_ref(), &pp, full, mask);
                drawn += 1;
            }
            _ => skipped += 1,
        }
    }
    Ok(Plate { pixmap: pm, drawn, skipped })
}

/// То же из строки JSON.
pub fn render_json(ops_json: &str, w_mm: f32, h_mm: f32, dpi: f32) -> Result<Plate, PlateError> {
    let v: Value = serde_json::from_str(ops_json).map_err(|e| PlateError(format!("JSON: {e}")))?;
    render(&v, w_mm, h_mm, dpi)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn px(p: &Plate, x_mm: f32, y_mm: f32, dpi: f32) -> (u8, u8, u8) {
        let k = dpi / 25.4;
        let c = p.pixmap.pixel((x_mm * k) as u32, (y_mm * k) as u32).unwrap().demultiply();
        (c.red(), c.green(), c.blue())
    }

    #[test]
    fn fill_stroke_and_white_background() {
        let ops = json!([{"op": "path", "closed": true, "rings": [[[10, 10], [30, 10], [30, 30], [10, 30]]],
                          "fill": [1, 0, 0], "stroke": [0, 0, 1], "width": 1.0}]);
        let p = render(&ops, 40.0, 40.0, 100.0).unwrap();
        assert_eq!(px(&p, 20.0, 20.0, 100.0), (255, 0, 0));
        assert_eq!(px(&p, 10.0, 20.0, 100.0), (0, 0, 255));
        assert_eq!(px(&p, 35.0, 35.0, 100.0), (255, 255, 255));
        assert_eq!((p.drawn, p.skipped), (1, 0));
    }

    #[test]
    fn alpha_holes_and_clip() {
        let ops = json!([
            {"op": "clip", "rect": [0, 0, 20, 40]},
            {"op": "path", "closed": true, "fill": [0, 0, 0], "alpha": 0.5,
             "rings": [[[2, 2], [38, 2], [38, 38], [2, 38]], [[8, 8], [14, 8], [14, 14], [8, 14]]]},
            {"op": "unclip"},
            {"op": "text", "x": 1, "y": 1, "text": "подпись", "size": 3}
        ]);
        let p = render(&ops, 40.0, 40.0, 100.0).unwrap();
        let (r, _, _) = px(&p, 5.0, 5.0, 100.0);
        assert!((120..=135).contains(&r), "полупрозрачный серый: {r}");
        assert_eq!(px(&p, 11.0, 11.0, 100.0), (255, 255, 255), "дыра по чётности");
        assert_eq!(px(&p, 30.0, 5.0, 100.0), (255, 255, 255), "за обрезкой пусто");
        assert_eq!(p.skipped, 1, "текст не растрируется");
    }

    #[test]
    fn dash_leaves_gaps() {
        let ops = json!([{"op": "path", "closed": false, "rings": [[[0, 5], [40, 5]]], "stroke": [0, 0, 0], "width": 1.0, "dash": [4, 4]}]);
        let p = render(&ops, 40.0, 10.0, 100.0).unwrap();
        assert_eq!(px(&p, 2.0, 5.0, 100.0), (0, 0, 0));
        assert_eq!(px(&p, 6.0, 5.0, 100.0), (255, 255, 255));
    }

    #[test]
    fn ink_detects_empty_plate() {
        let p = render(&json!([]), 50.0, 50.0, 72.0).unwrap();
        assert_eq!(p.ink(), 0.0);
        assert!(render(&json!({"op": 1}), 10.0, 10.0, 72.0).is_err());
    }
}
