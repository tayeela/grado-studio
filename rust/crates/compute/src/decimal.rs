//! Значения выражений и «математическое» округление round_half_up.
//!
//! Порт семантики Python из core/compute/grado_compute/expressions.py:
//! целые — произвольной точности (bigint, как int в Python), bool — подтип int,
//! round_half_up идёт по десятичной записи кратчайшего repr числа
//! (Decimal(repr(x)) в Python): 2.5 → 3, 2.675 → 2.68, 0.145 → 0.15 на двух знаках.

use num_bigint::BigInt;
use num_traits::{Pow, ToPrimitive, Zero};
use serde_json::Number;

#[derive(Clone, Debug)]
pub enum Value {
    Int(BigInt),
    Float(f64),
    Bool(bool),
    Str(String),
}

impl Value {
    /// Python-правда: 0, 0.0, False, "" — ложь, остальное — истина.
    pub fn truthy(&self) -> bool {
        match self {
            Value::Int(i) => !i.is_zero(),
            Value::Float(f) => *f != 0.0,
            Value::Bool(b) => *b,
            Value::Str(s) => !s.is_empty(),
        }
    }

    /// Числовое прочтение: bool → 0/1, Int → f64 (может потерять точность свыше 2^53,
    /// как float(x) в Python), Str — ошибка.
    pub fn as_f64(&self) -> Result<f64, String> {
        match self {
            Value::Int(i) => i
                .to_f64()
                .ok_or_else(|| "целое слишком велико для float".to_string()),
            Value::Float(f) => Ok(*f),
            Value::Bool(b) => Ok(if *b { 1.0 } else { 0.0 }),
            Value::Str(_) => Err("строка не участвует в арифметике".to_string()),
        }
    }

    /// JSON-сериализация в стиле Python json.dump: int без точки, float — кратчайший repr.
    pub fn to_json(&self) -> serde_json::Value {
        match self {
            Value::Int(i) => match i.to_i64() {
                Some(v) => serde_json::Value::Number(Number::from(v)),
                None => serde_json::Value::String(i.to_string()), // за пределами i64 — строка (в ТЭП не встречается)
            },
            Value::Float(f) => serde_json::Number::from_f64(*f)
                .map(serde_json::Value::Number)
                .unwrap_or(serde_json::Value::Null),
            Value::Bool(b) => serde_json::Value::Bool(*b),
            Value::Str(s) => serde_json::Value::String(s.clone()),
        }
    }

    /// Печать как repr в Python (для сверочных дампов: 2.0 → "2.0").
    pub fn py_repr(&self) -> String {
        match self {
            Value::Int(i) => i.to_string(),
            Value::Float(f) => py_float_repr(*f),
            Value::Bool(b) => if *b { "True" } else { "False" }.to_string(),
            Value::Str(s) => format!("{s:?}"),
        }
    }
}

/// Кратчайший repr float как в Python: экспонента при |x| >= 1e16 или |x| < 1e-4.
pub fn py_float_repr(f: f64) -> String {
    if f.is_nan() {
        return "nan".into();
    }
    if f.is_infinite() {
        return if f > 0.0 { "inf".into() } else { "-inf".into() };
    }
    let shortest = format!("{f}"); // Rust Display: кратчайшая запись с полным round-trip, без экспоненты
    let a = f.abs();
    if a != 0.0 && (a >= 1e16 || a < 1e-4) {
        let (mantissa, exp) = scientific_parts(&shortest);
        let sign = if exp < 0 { "-" } else { "+" };
        format!("{mantissa}e{sign}{:02}", exp.abs())
    } else {
        // Python у целочисленных float печатает ".0"
        if !shortest.contains('.') {
            format!("{shortest}.0")
        } else {
            shortest
        }
    }
}

fn scientific_parts(plain: &str) -> (String, i32) {
    let neg = plain.starts_with('-');
    let body = plain.trim_start_matches('-');
    let (int_part, frac_part) = body.split_once('.').unwrap_or((body, ""));
    let digits: String = format!("{int_part}{frac_part}");
    let first = digits.bytes().position(|b| b != b'0').unwrap_or(0);
    let exp = int_part.len() as i32 - 1 - first as i32;
    let mantissa_digits = &digits[first..];
    let mut m = String::new();
    if mantissa_digits.is_empty() {
        m.push('0');
    } else {
        m.push_str(&mantissa_digits[..1]);
        let rest = mantissa_digits[1..].trim_end_matches('0');
        if !rest.is_empty() {
            m.push('.');
            m.push_str(rest);
        }
    }
    if neg {
        m.insert(0, '-');
    }
    (m, exp)
}

/// round_half_up(x, n): математическое округление по цифрам кратчайшего repr |x|,
/// половина — от нуля (ROUND_HALF_UP в Python). n <= 0 даёт целое (int), n > 0 — float.
pub fn round_half_up(x: f64, n: i32) -> Result<Value, String> {
    if !x.is_finite() {
        return Err(format!("round от нечислового значения {}", py_float_repr(x)));
    }
    let neg = x.is_sign_negative() && x != 0.0;
    let s = format!("{}", x.abs()); // десятичная запись без экспоненты, кратчайшая
    let (int_part, frac_part) = match s.split_once('.') {
        Some((a, b)) => (a, b),
        None => (s.as_str(), ""),
    };
    let point = int_part.len() as i64; // позиции цифр: 0 — старшая цифра целой части
    let digits: Vec<u8> = int_part
        .bytes()
        .chain(frac_part.bytes())
        .filter(|b| b.is_ascii_digit())
        .collect();
    // Позиция первой отбрасываемой цифры: округляем на |n| знаках после точки.
    let len = digits.len() as i64;
    let pos = point + n as i64;
    let kept_len = pos.clamp(0, len) as usize;
    let mut kept: BigInt = if kept_len == 0 {
        BigInt::zero()
    } else {
        let txt: String = String::from_utf8(digits[..kept_len].to_vec()).unwrap();
        txt.parse().map_err(|e| format!("разбор числа {s}: {e}"))?
    };
    let decide = if pos >= 0 && pos < len {
        digits[pos as usize]
    } else {
        b'0'
    };
    if decide >= b'5' {
        kept = kept + BigInt::from(1); // половина и больше — от нуля; перенос 9.99 → 10 включён
    }
    // Последняя сохранённая цифра стоит в позиции min(pos, len) − 1, её разряд — 10^(point − min(pos, len)).
    let scale = point - pos.min(len);
    if n <= 0 {
        // pos = point + n ≤ point ≤ len, поэтому scale = −n ≥ 0 — результат целый
        let result = kept * BigInt::from(10u32).pow(scale as u32);
        return Ok(Value::Int(if neg { -result } else { result }));
    }
    let f = if scale >= 0 {
        (kept * BigInt::from(10u32).pow(scale as u32))
            .to_f64()
            .ok_or_else(|| format!("переполнение при округлении {s}"))?
    } else {
        kept.to_f64()
            .ok_or_else(|| format!("переполнение при округлении {s}"))?
            / 10f64.powi((-scale) as i32)
    };
    Ok(Value::Float(if neg { -f } else { f }))
}

/// Округление f64 на n знаках — float-результат (для round(x, n>0) внутри выражений).
pub fn round_half_up_f64(x: f64, n: i32) -> Result<f64, String> {
    match round_half_up(x, n)? {
        Value::Float(f) => Ok(f),
        Value::Int(i) => Ok(i.to_f64().unwrap_or(f64::NAN)),
        _ => unreachable!(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn f(v: Value) -> f64 {
        v.as_f64().unwrap()
    }

    #[test]
    fn half_up_matches_python() {
        assert_eq!(f(round_half_up(2.5, 0).unwrap()), 3.0);
        assert_eq!(f(round_half_up(0.0005, 3).unwrap()), 0.001);
        assert_eq!(f(round_half_up(2.675, 2).unwrap()), 2.68);
        assert_eq!(f(round_half_up(0.145, 2).unwrap()), 0.15); // ловушка двоичного представления
        assert_eq!(f(round_half_up(-2.5, 0).unwrap()), -3.0); // ROUND_HALF_UP — от нуля
        assert_eq!(f(round_half_up(2.567, 1).unwrap()), 2.6);
        assert_eq!(f(round_half_up(9.99, 1).unwrap()), 10.0);
        assert_eq!(f(round_half_up(6.0, -1).unwrap()), 10.0); // отрицательный n — до десятков
        assert_eq!(f(round_half_up(4.0, -1).unwrap()), 0.0);
        assert_eq!(f(round_half_up(500.0, -3).unwrap()), 1000.0);
        assert!(matches!(round_half_up(2.5, 0).unwrap(), Value::Int(_)));
        assert!(matches!(round_half_up(2.5, 1).unwrap(), Value::Float(_)));
    }

    #[test]
    fn repr_matches_python() {
        assert_eq!(py_float_repr(357.0), "357.0");
        assert_eq!(py_float_repr(21.42), "21.42");
        assert_eq!(py_float_repr(1e16), "1e+16");
        assert_eq!(py_float_repr(1.5e16), "1.5e+16");
        assert_eq!(py_float_repr(1e-5), "1e-05");
        assert_eq!(py_float_repr(1e-100), "1e-100");
        assert_eq!(py_float_repr(0.0001), "0.0001");
        assert_eq!(py_float_repr(-2.5), "-2.5");
    }
}
