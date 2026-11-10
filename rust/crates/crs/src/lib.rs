//! Системы координат ГРАДО: перенос `core/connectors/grado_connectors/crs.py` один в один.
//!
//! Москва: МСК (как в QGIS) — в ней пользователь видит и вводит координаты, в ней DXF и листы; система ГИС ОГД —
//! родные координаты выгрузок портала. Датум один (Бессель + towgs84), МСК = ОГД − [`OGD_SHIFT`] (железное правило 3:
//! схему не менять и не «калибровать»).
//!
//! Порядок действий и степени (`powf`, как `**` в Python) повторены точно, поэтому результат совпадает с Python
//! бит-в-бит на той же платформе (сверка — `tests/parity.rs` по `rust/parity/crs/reference.json`).
//! Единственное место, где Python считает по-своему, — `math.hypot`: здесь [`py_hypot`] повторяет его алгоритм.

use std::f64::consts::PI;

/// Система ГИС ОГД − МСК, метры (false easting/northing OGD_PROJ4).
pub const OGD_SHIFT: (f64, f64) = (16.098, 14.512);

const R: f64 = 6378137.0; // сфера Web Mercator
const A: f64 = 6378137.0; // WGS84
const F: f64 = 1.0 / 298.257223563;
const K0: f64 = 0.9996;
const FE: f64 = 500000.0;

const B_A: f64 = 6377397.155; // Бессель 1841
const B_F: f64 = 1.0 / 299.1528128;
const MSK_K0: f64 = 1.0;
const TW_D: (f64, f64, f64) = (316.151, 78.924, 589.650);
const TW_S: f64 = 8.4507e-6;

fn e2() -> f64 {
    F * (2.0 - F)
}
fn ep2() -> f64 {
    e2() / (1.0 - e2())
}
fn b_e2() -> f64 {
    B_F * (2.0 - B_F)
}
fn b_ep2() -> f64 {
    b_e2() / (1.0 - b_e2())
}
/// `math.radians` Python: x * (pi / 180).
fn radians(x: f64) -> f64 {
    x * (PI / 180.0)
}
/// `math.degrees` Python: x * (180 / pi).
fn degrees(x: f64) -> f64 {
    x * (180.0 / PI)
}
fn lon0() -> f64 {
    radians(39.0) // осевой меридиан зоны 37
}
fn msk_lat0() -> f64 {
    radians(55.66666666667)
}
fn msk_lon0() -> f64 {
    radians(37.5)
}
fn tw_r() -> (f64, f64, f64) {
    (
        radians(-1.57273 / 3600.0),
        radians(2.69209 / 3600.0),
        radians(2.34693 / 3600.0),
    )
}
fn p(x: f64, n: f64) -> f64 {
    x.powf(n)
}

/// `math.hypot(x, y)` Python 3.10+ (vector_norm для двух чисел): масштаб по степени двойки, сумма квадратов
/// с поправкой и одна итерация Ньютона — повторено, чтобы совпасть с Python бит-в-бит.
pub fn py_hypot(x: f64, y: f64) -> f64 {
    let (x, y) = (x.abs(), y.abs());
    let max = x.max(y);
    if max.is_infinite() {
        return f64::INFINITY;
    }
    if max.is_nan() {
        return f64::NAN;
    }
    if max == 0.0 || x.min(y) == 0.0 {
        return max;
    }
    // frexp(max): max = m * 2^e, m в [0.5, 1)
    let (_, max_e) = frexp(max);
    if max_e < -1023 {
        // очень малые числа: Python масштабирует и считает заново
        return py_hypot(x / f64::MIN_POSITIVE, y / f64::MIN_POSITIVE) * f64::MIN_POSITIVE;
    }
    let scale = ldexp(1.0, -max_e);
    let mut csum = 1.0f64;
    let mut frac1 = 0.0f64;
    let mut frac2 = 0.0f64;
    for v in [x, y] {
        let v = v * scale;
        // dl_mul(v, v): точное произведение как сумма hi + lo (FMA)
        let hi = v * v;
        let lo = v.mul_add(v, -hi);
        let oldcsum = csum;
        csum += hi;
        frac1 += (oldcsum - csum) + hi;
        frac2 += lo;
    }
    let mut h = (csum - 1.0 + (frac1 + frac2)).sqrt();
    // поправка Ньютона: точное h*h
    let pr_hi = -h * h;
    let pr_lo = (-h).mul_add(h, -pr_hi);
    let oldcsum = csum;
    csum += pr_hi;
    frac1 += (oldcsum - csum) + pr_hi;
    frac2 += pr_lo;
    let x2 = csum - 1.0 + (frac1 + frac2);
    h += x2 / (2.0 * h);
    h / scale
}

fn frexp(x: f64) -> (f64, i32) {
    if x == 0.0 || !x.is_finite() {
        return (x, 0);
    }
    let bits = x.to_bits();
    let exp = ((bits >> 52) & 0x7ff) as i32;
    if exp == 0 {
        let (m, e) = frexp(x * 2f64.powi(54));
        return (m, e - 54);
    }
    let m = f64::from_bits((bits & !(0x7ffu64 << 52)) | (1022u64 << 52));
    (m, exp - 1022)
}

fn ldexp(x: f64, e: i32) -> f64 {
    let h = e / 2; // два шага: 2^±1024 не помещается в f64, а 2^±512 — да
    x * 2f64.powi(h) * 2f64.powi(e - h)
}

/// Web Mercator (EPSG:3857) → WGS84 (долгота, широта), градусы.
pub fn merc_to_wgs84(x: f64, y: f64) -> (f64, f64) {
    (degrees(x / R), degrees((y / R).sinh().atan()))
}

/// asinh из системной libm, как math.asinh в Python: f64::asinh в Rust
/// считается своей формулой и в разных версиях Rust расходится в последнем бите.
#[cfg(not(target_arch = "wasm32"))]
fn c_asinh(x: f64) -> f64 {
    extern "C" {
        fn asinh(x: f64) -> f64;
    }
    // SAFETY: чистая функция libm без побочных действий.
    unsafe { asinh(x) }
}

#[cfg(target_arch = "wasm32")]
fn c_asinh(x: f64) -> f64 {
    x.asinh()
}

/// WGS84 → Web Mercator (EPSG:3857), метры.
pub fn wgs84_to_merc(lon: f64, lat: f64) -> (f64, f64) {
    (radians(lon) * R, c_asinh(radians(lat).tan()) * R)
}

/// WGS84 → UTM 37N (ряды Снайдера, точность около миллиметра).
pub fn wgs84_to_utm37n(lon: f64, lat: f64) -> (f64, f64) {
    let (e2, ep2) = (e2(), ep2());
    let phi = radians(lat);
    let lam = radians(lon);
    let (sin_phi, cos_phi, tan_phi) = (phi.sin(), phi.cos(), phi.tan());
    let n = A / (1.0 - e2 * p(sin_phi, 2.0)).sqrt();
    let t = p(tan_phi, 2.0);
    let c = ep2 * p(cos_phi, 2.0);
    let a = (lam - lon0()) * cos_phi;
    let m = A
        * ((1.0 - e2 / 4.0 - 3.0 * p(e2, 2.0) / 64.0 - 5.0 * p(e2, 3.0) / 256.0) * phi
            - (3.0 * e2 / 8.0 + 3.0 * p(e2, 2.0) / 32.0 + 45.0 * p(e2, 3.0) / 1024.0)
                * (2.0 * phi).sin()
            + (15.0 * p(e2, 2.0) / 256.0 + 45.0 * p(e2, 3.0) / 1024.0) * (4.0 * phi).sin()
            - (35.0 * p(e2, 3.0) / 3072.0) * (6.0 * phi).sin());
    let x = K0
        * n
        * (a + (1.0 - t + c) * p(a, 3.0) / 6.0
            + (5.0 - 18.0 * t + p(t, 2.0) + 72.0 * c - 58.0 * ep2) * p(a, 5.0) / 120.0)
        + FE;
    let y = K0
        * (m + n
            * tan_phi
            * (p(a, 2.0) / 2.0
                + (5.0 - t + 9.0 * c + 4.0 * p(c, 2.0)) * p(a, 4.0) / 24.0
                + (61.0 - 58.0 * t + p(t, 2.0) + 600.0 * c - 330.0 * ep2) * p(a, 6.0) / 720.0));
    (x, y)
}

/// UTM 37N → WGS84, обратный ряд Снайдера.
pub fn utm37n_to_wgs84(x: f64, y: f64) -> (f64, f64) {
    let (e2, ep2) = (e2(), ep2());
    let e1 = (1.0 - (1.0 - e2).sqrt()) / (1.0 + (1.0 - e2).sqrt());
    let m = y / K0;
    let mu = m / (A * (1.0 - e2 / 4.0 - 3.0 * p(e2, 2.0) / 64.0 - 5.0 * p(e2, 3.0) / 256.0));
    let phi1 = mu
        + (3.0 * e1 / 2.0 - 27.0 * p(e1, 3.0) / 32.0) * (2.0 * mu).sin()
        + (21.0 * p(e1, 2.0) / 16.0 - 55.0 * p(e1, 4.0) / 32.0) * (4.0 * mu).sin()
        + (151.0 * p(e1, 3.0) / 96.0) * (6.0 * mu).sin()
        + (1097.0 * p(e1, 4.0) / 512.0) * (8.0 * mu).sin();
    let (sin_phi1, cos_phi1, tan_phi1) = (phi1.sin(), phi1.cos(), phi1.tan());
    let c1 = ep2 * p(cos_phi1, 2.0);
    let t1 = p(tan_phi1, 2.0);
    let n1 = A / (1.0 - e2 * p(sin_phi1, 2.0)).sqrt();
    let r1 = A * (1.0 - e2) / p(1.0 - e2 * p(sin_phi1, 2.0), 1.5);
    let d = (x - FE) / (n1 * K0);
    let phi = phi1
        - (n1 * tan_phi1 / r1)
            * (p(d, 2.0) / 2.0
                - (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * p(c1, 2.0) - 9.0 * ep2) * p(d, 4.0) / 24.0
                + (61.0 + 90.0 * t1 + 298.0 * c1 + 45.0 * p(t1, 2.0)
                    - 252.0 * ep2
                    - 3.0 * p(c1, 2.0))
                    * p(d, 6.0)
                    / 720.0);
    let lam = lon0()
        + (d - (1.0 + 2.0 * t1 + c1) * p(d, 3.0) / 6.0
            + (5.0 - 2.0 * c1 + 28.0 * t1 - 3.0 * p(c1, 2.0) + 8.0 * ep2 + 24.0 * p(t1, 2.0))
                * p(d, 5.0)
                / 120.0)
            / cos_phi1;
    (degrees(lam), degrees(phi))
}

/// Web Mercator → UTM 37N.
pub fn merc_to_utm37n(x: f64, y: f64) -> (f64, f64) {
    let (lon, lat) = merc_to_wgs84(x, y);
    wgs84_to_utm37n(lon, lat)
}

fn meridian_arc(phi: f64, a: f64, e2: f64) -> f64 {
    a * ((1.0 - e2 / 4.0 - 3.0 * p(e2, 2.0) / 64.0 - 5.0 * p(e2, 3.0) / 256.0) * phi
        - (3.0 * e2 / 8.0 + 3.0 * p(e2, 2.0) / 32.0 + 45.0 * p(e2, 3.0) / 1024.0)
            * (2.0 * phi).sin()
        + (15.0 * p(e2, 2.0) / 256.0 + 45.0 * p(e2, 3.0) / 1024.0) * (4.0 * phi).sin()
        - (35.0 * p(e2, 3.0) / 3072.0) * (6.0 * phi).sin())
}

/// Система ГИС ОГД (Бессель со смещением, OGD_PROJ4) → WGS84 (долгота, широта), градусы.
/// Имя историческое, как в Python: это НЕ рабочая МСК пользователя — для неё [`msk_to_wgs84`].
pub fn msk50_to_wgs84(east: f64, north: f64) -> (f64, f64) {
    let (a, e2, ep2) = (B_A, b_e2(), b_ep2());
    let (x0, y0) = OGD_SHIFT;
    let m0 = meridian_arc(msk_lat0(), a, e2);
    let m = m0 + (north - y0) / MSK_K0;
    let mu = m / (a * (1.0 - e2 / 4.0 - 3.0 * p(e2, 2.0) / 64.0 - 5.0 * p(e2, 3.0) / 256.0));
    let e1 = (1.0 - (1.0 - e2).sqrt()) / (1.0 + (1.0 - e2).sqrt());
    let phi1 = mu
        + (3.0 * e1 / 2.0 - 27.0 * p(e1, 3.0) / 32.0) * (2.0 * mu).sin()
        + (21.0 * p(e1, 2.0) / 16.0 - 55.0 * p(e1, 4.0) / 32.0) * (4.0 * mu).sin()
        + (151.0 * p(e1, 3.0) / 96.0) * (6.0 * mu).sin()
        + (1097.0 * p(e1, 4.0) / 512.0) * (8.0 * mu).sin();
    let (sp, cp, tp) = (phi1.sin(), phi1.cos(), phi1.tan());
    let c1 = ep2 * p(cp, 2.0);
    let t1 = p(tp, 2.0);
    let n1 = a / (1.0 - e2 * p(sp, 2.0)).sqrt();
    let r1 = a * (1.0 - e2) / p(1.0 - e2 * p(sp, 2.0), 1.5);
    let d = (east - x0) / (n1 * MSK_K0);
    let phi = phi1
        - (n1 * tp / r1)
            * (p(d, 2.0) / 2.0
                - (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * p(c1, 2.0) - 9.0 * ep2) * p(d, 4.0) / 24.0
                + (61.0 + 90.0 * t1 + 298.0 * c1 + 45.0 * p(t1, 2.0)
                    - 252.0 * ep2
                    - 3.0 * p(c1, 2.0))
                    * p(d, 6.0)
                    / 720.0);
    let lam = msk_lon0()
        + (d - (1.0 + 2.0 * t1 + c1) * p(d, 3.0) / 6.0
            + (5.0 - 2.0 * c1 + 28.0 * t1 - 3.0 * p(c1, 2.0) + 8.0 * ep2 + 24.0 * p(t1, 2.0))
                * p(d, 5.0)
                / 120.0)
            / cp;
    // геодезические (Бессель) → геоцентрика → Хельмерт (Position Vector, как towgs84 в PROJ) → WGS84
    let (sinp, cosp, sinl, cosl) = (phi.sin(), phi.cos(), lam.sin(), lam.cos());
    let nn = a / (1.0 - e2 * p(sinp, 2.0)).sqrt();
    let x = nn * cosp * cosl;
    let y = nn * cosp * sinl;
    let z = nn * (1.0 - e2) * sinp;
    let (dx, dy, dz) = TW_D;
    let (rx, ry, rz) = tw_r();
    let ms = 1.0 + TW_S;
    let xo = ms * (x - rz * y + ry * z) + dx;
    let yo = ms * (rz * x + y - rx * z) + dy;
    let zo = ms * (-ry * x + rx * y + z) + dz;
    // геоцентрика WGS84 → геодезические (Боуринг)
    let (aw, e2w) = (A, F * (2.0 - F));
    let bw = aw * (1.0 - e2w).sqrt();
    let ep2w = e2w / (1.0 - e2w);
    let pp = py_hypot(xo, yo);
    let th = (zo * aw).atan2(pp * bw);
    let lat = (zo + ep2w * bw * p(th.sin(), 3.0)).atan2(pp - e2w * aw * p(th.cos(), 3.0));
    let lon = yo.atan2(xo);
    (degrees(lon), degrees(lat))
}

/// WGS84 → система ГИС ОГД: обратная задача итерациями Ньютона по прямой цепочке, как в Python.
pub fn wgs84_to_msk50(lon: f64, lat: f64) -> (f64, f64) {
    let (x0, y0) = OGD_SHIFT;
    let kx = 111320.0 * radians(lat).cos();
    let mut e = (lon - degrees(msk_lon0())) * kx + x0;
    let mut n = (lat - degrees(msk_lat0())) * 110540.0 + y0;
    for _ in 0..6 {
        let (lo, la) = msk50_to_wgs84(e, n);
        e -= (lo - lon) * kx;
        n -= (la - lat) * 110540.0;
        if (lo - lon).abs() < 1e-11 && (la - lat).abs() < 1e-11 {
            break;
        }
    }
    (e, n)
}

/// МСК (как в QGIS): X восток, Y север, метры → WGS84. Через систему ГИС ОГД и сдвиг.
pub fn msk_to_wgs84(x: f64, y: f64) -> (f64, f64) {
    msk50_to_wgs84(x + OGD_SHIFT.0, y + OGD_SHIFT.1)
}

/// WGS84 → МСК (как в QGIS).
pub fn wgs84_to_msk(lon: f64, lat: f64) -> (f64, f64) {
    let (e, n) = wgs84_to_msk50(lon, lat);
    (e - OGD_SHIFT.0, n - OGD_SHIFT.1)
}

/// Родные координаты ГИС ОГД → МСК: сдвиг, без пересчёта через градусы.
pub fn ogd_to_msk(x: f64, y: f64) -> (f64, f64) {
    (x - OGD_SHIFT.0, y - OGD_SHIFT.1)
}

/// МСК → родные координаты ГИС ОГД.
pub fn msk_to_ogd(x: f64, y: f64) -> (f64, f64) {
    (x + OGD_SHIFT.0, y + OGD_SHIFT.1)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shift_is_exact() {
        let (x, y) = ogd_to_msk(1000.0, 2000.0);
        assert_eq!(msk_to_ogd(x, y), (1000.0, 2000.0));
    }

    #[test]
    fn round_trip_mm() {
        for (lon, lat) in [
            (37.6176, 55.7558),
            (37.2, 55.5),
            (37.9, 55.95),
            (36.8, 55.15),
        ] {
            let (x, y) = wgs84_to_msk(lon, lat);
            let (lo, la) = msk_to_wgs84(x, y);
            assert!(
                (lo - lon).abs() < 1e-8 && (la - lat).abs() < 1e-8,
                "{lon} {lat}"
            );
        }
    }

    #[test]
    fn hypot_like_python() {
        assert_eq!(py_hypot(3.0, 4.0), 5.0);
        assert_eq!(py_hypot(0.0, -2.5), 2.5);
    }
}
