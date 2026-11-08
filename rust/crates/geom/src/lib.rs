//! Геометрическое ядро «ГРАДО Студии» на Rust — порт `core/geom` (эталонная
//! реализация на Python). Модули соответствуют один к одному:
//!
//! - [`affine`] — поворот, масштаб, зеркало;
//! - [`curves`] — дуги окружностей, линеаризация по допуску, схемы кривых;
//! - [`path`] — составные пути: пикетаж, сопряжения, офсеты;
//! - [`overlay`] — площадь (∪ regions) ∩ (∪ clips) (аналог shapely/GEOS);
//! - [`snap`] — движок привязок (аналог STRtree-поиска);
//! - [`coverage`] — топологическое покрытие зон с общими рёбрами.
//!
//! Отличия от Python-эталона задокументированы в README крейта и в каждом
//! модуле: `hypot` у CPython собственный (расхождение ≤ пары ulp с libm),
//! GEOS-операции заменены на `geo`/собственный нодинг — сверка с Python
//! идёт по допуску, а не бит-в-бит (в отличие от крейта `grado_compute_rs`).

pub mod affine;
pub mod coverage;
pub mod curves;
pub mod overlay;
pub mod path;
pub mod snap;

/// Точка — пара координат, как кортеж в Python-эталоне.
pub type Pt = (f64, f64);

/// 2π теми же битами, что `2 * math.pi` в Python (умножение на 2 точно).
pub const TAU: f64 = 6.283185307179586;

/// Python float `%`: fmod с подгонкой знака к делителю (семантика CPython
/// `float_rem`), а не наивное `a - b*floor(a/b)` — биты отличаются.
pub fn py_mod(a: f64, b: f64) -> f64 {
    let m = a % b;
    if m != 0.0 && (m < 0.0) != (b < 0.0) {
        m + b
    } else {
        m
    }
}

/// Python `round(x, 9)`: корректное десятичное округление точного бинарного
/// значения (CPython — Gay's dtoa, режим 3; Rust — формат с точностью).
/// Сверено с CPython 3.12 бит-в-бит на 150 тыс. значений, включая границы
/// ties. -0.0 нормализуется в 0.0 — как в Python, где -0.0 и 0.0 — один
/// ключ словаря.
pub fn py_round9(x: f64) -> f64 {
    let r: f64 = format!("{x:.9}").parse().unwrap_or(x);
    if r == 0.0 {
        0.0
    } else {
        r
    }
}

/// f64 с полным порядком для ключей карт (координаты всегда конечны —
/// не конечные отсекаются на входе).
#[derive(Clone, Copy, PartialEq, Debug)]
pub struct OrdF64(pub f64);

impl Eq for OrdF64 {}

impl Ord for OrdF64 {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.0.total_cmp(&other.0)
    }
}

impl PartialOrd for OrdF64 {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl From<f64> for OrdF64 {
    fn from(x: f64) -> Self {
        OrdF64(x)
    }
}

/// Ключ точки для карт: лексикографический порядок, как сравнение кортежей
/// в Python (`min(a, b)`, `a < b`).
pub type OrdPt = (OrdF64, OrdF64);

pub fn ord_pt(p: Pt) -> OrdPt {
    (OrdF64(p.0), OrdF64(p.1))
}

pub fn unord_pt(p: OrdPt) -> Pt {
    (p.0 .0, p.1 .0)
}

/// Площадь (со знаком) замкнутого контура по формуле шнурков — тот же
/// порядок суммирования, что у поэлементного цикла Python-эталона.
pub fn shoelace(ring: &[Pt]) -> f64 {
    if ring.is_empty() {
        return 0.0;
    }
    let mut s = 0.0;
    for i in 0..ring.len() {
        let (x1, y1) = ring[i];
        let (x2, y2) = ring[(i + 1) % ring.len()];
        s += x1 * y2 - x2 * y1;
    }
    s / 2.0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn py_mod_matches_python_semantics() {
        // (-0.5) % (2π) в Python = 2π - 0.5, не -0.5
        assert!((py_mod(-0.5, TAU) - (TAU - 0.5)).abs() < 1e-15);
        assert!((py_mod(7.0, TAU) - (7.0 - TAU)).abs() < 1e-15);
        assert_eq!(py_mod(0.5, TAU), 0.5);
    }

    #[test]
    fn round9_agrees_with_python() {
        // эталоны сняты с CPython 3.12: round(x, 9)
        assert_eq!(py_round9(0.12345678949999999), 0.123456789);
        assert_eq!(py_round9(1.0000000005), 1.000000001);
        assert_eq!(py_round9(-0.0), 0.0);
    }
}
