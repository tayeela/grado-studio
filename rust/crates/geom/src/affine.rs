//! Аффинные преобразования точек: поворот, масштаб, зеркало.
//!
//! Ось и начало задаёт вызывающий. Функции не пишут проект и не режут
//! топологию. Прямой порт `grado_geom/affine.py` — порядок операций сохранён.

use crate::Pt;

/// Ошибка валидации входа (Python: ValueError).
#[derive(Debug, Clone)]
pub struct GeomValueError(pub String);

impl std::fmt::Display for GeomValueError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for GeomValueError {}

/// Python `_pairs`: проверка конечности координат входных точек.
fn validate(points: &[Pt]) -> Result<(), GeomValueError> {
    for &(x, y) in points {
        if !x.is_finite() || !y.is_finite() {
            return Err(GeomValueError("координата не конечна".into()));
        }
    }
    Ok(())
}

/// Поворот вокруг origin на degrees против часовой, градусы.
pub fn rotate(points: &[Pt], origin: Pt, degrees: f64) -> Result<Vec<Pt>, GeomValueError> {
    validate(points)?;
    let (ox, oy) = origin;
    let rad = degrees.to_radians();
    let (c, s) = (rad.cos(), rad.sin());
    Ok(points
        .iter()
        .map(|&(x, y)| {
            let (dx, dy) = (x - ox, y - oy);
            (ox + dx * c - dy * s, oy + dx * s + dy * c)
        })
        .collect())
}

/// Масштаб относительно origin. factor > 0.
pub fn scale(points: &[Pt], origin: Pt, factor: f64) -> Result<Vec<Pt>, GeomValueError> {
    validate(points)?;
    if !factor.is_finite() || factor <= 0.0 {
        return Err(GeomValueError("масштаб должен быть > 0".into()));
    }
    let (ox, oy) = origin;
    Ok(points
        .iter()
        .map(|&(x, y)| (ox + (x - ox) * factor, oy + (y - oy) * factor))
        .collect())
}

/// Отражение относительно прямой через точки a и b.
pub fn mirror(points: &[Pt], a: Pt, b: Pt) -> Result<Vec<Pt>, GeomValueError> {
    validate(points)?;
    let (ax, ay) = a;
    let (bx, by) = b;
    let (dx, dy) = (bx - ax, by - ay);
    let length2 = dx * dx + dy * dy;
    if length2 == 0.0 || !length2.is_finite() {
        return Err(GeomValueError("ось зеркала — не прямая".into()));
    }
    Ok(points
        .iter()
        .map(|&(x, y)| {
            let t = ((x - ax) * dx + (y - ay) * dy) / length2;
            let (px, py) = (ax + t * dx, ay + t * dy);
            (2.0 * px - x, 2.0 * py - y)
        })
        .collect())
}
