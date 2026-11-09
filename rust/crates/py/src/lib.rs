//! Модуль grado_rs для Python: ТЭП-движок на Rust (crates/compute) с API как у grado_compute.Engine.
//!
//! Обёртка на стороне Python — core/compute/grado_compute/rust_backend.py: держит пресет-словарь,
//! переводит виды ошибок в PresetError / KeyError / ExpressionError / ZeroDivisionError.
//! Значения: int Python ↔ BigInt (произвольная точность), bool, float, str — как в эталоне.

use grado_compute_rs::decimal::Value;
use grado_compute_rs::engine::{Engine, ErrorKind, PresetError};
use num_bigint::BigInt;
use pyo3::exceptions::{PyKeyError, PyTypeError, PyValueError, PyZeroDivisionError};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString};

pyo3::create_exception!(grado_rs, ExpressionError, PyValueError);

fn to_py_err(e: PresetError) -> PyErr {
    match e.kind {
        ErrorKind::Preset => PyValueError::new_err(e.msg),
        ErrorKind::UnknownName => PyKeyError::new_err(e.msg),
        ErrorKind::Eval => ExpressionError::new_err(e.msg),
        ErrorKind::ZeroDivision => PyZeroDivisionError::new_err(e.msg),
    }
}

fn from_py(v: &Bound<'_, PyAny>) -> PyResult<Value> {
    if v.is_instance_of::<PyBool>() {
        return Ok(Value::Bool(v.extract::<bool>()?));
    }
    if v.is_instance_of::<PyInt>() {
        return Ok(Value::Int(v.extract::<BigInt>()?));
    }
    if v.is_instance_of::<PyFloat>() {
        return Ok(Value::Float(v.extract::<f64>()?));
    }
    if v.is_instance_of::<PyString>() {
        return Ok(Value::Str(v.extract::<String>()?));
    }
    Err(PyTypeError::new_err(format!(
        "значение должно быть числом или строкой, получено {}",
        v.get_type().name()?
    )))
}

fn to_py<'py>(py: Python<'py>, v: &Value) -> PyResult<Bound<'py, PyAny>> {
    Ok(match v {
        Value::Int(i) => i.clone().into_pyobject(py)?.into_any(),
        Value::Float(f) => PyFloat::new(py, *f).into_any(),
        Value::Bool(b) => PyBool::new(py, *b).to_owned().into_any(),
        Value::Str(s) => PyString::new(py, s).into_any(),
    })
}

fn pairs(kwargs: Option<&Bound<'_, PyDict>>) -> PyResult<Vec<(String, Value)>> {
    let mut out = Vec::new();
    if let Some(d) = kwargs {
        for (k, v) in d.iter() {
            out.push((k.extract::<String>()?, from_py(&v)?));
        }
    }
    Ok(out)
}

/// Движок ТЭП: тот же граф, порядок, округление и счётчики пересчётов, что у Python-версии.
#[pyclass(module = "grado_rs", name = "ComputeEngine", unsendable)]
struct ComputeEngine {
    inner: Engine,
}

#[pymethods]
impl ComputeEngine {
    /// Пресет — JSON-текст (json.dumps словаря пресета).
    #[new]
    fn new(preset_json: &str) -> PyResult<Self> {
        Engine::from_preset_str(preset_json)
            .map(|inner| ComputeEngine { inner })
            .map_err(to_py_err)
    }

    fn set_input(&mut self, input_id: &str, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let v = from_py(value)?;
        self.inner.set_input(input_id, v).map_err(to_py_err)
    }

    #[pyo3(signature = (**kwargs))]
    fn set_inputs(&mut self, kwargs: Option<&Bound<'_, PyDict>>) -> PyResult<()> {
        let p = pairs(kwargs)?;
        self.inner.set_inputs(&p).map_err(to_py_err)
    }

    #[pyo3(signature = (**kwargs))]
    fn set_constants(&mut self, kwargs: Option<&Bound<'_, PyDict>>) -> PyResult<()> {
        let p = pairs(kwargs)?;
        self.inner.set_constants(&p).map_err(to_py_err)
    }

    fn value<'py>(&self, py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
        to_py(py, &self.inner.value(name).map_err(to_py_err)?)
    }

    fn display<'py>(&self, py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
        to_py(py, &self.inner.display(name).map_err(to_py_err)?)
    }

    /// Строки результатов: ключи и порядок как у Python-версии (note — только где есть).
    fn results<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let out = PyList::empty(py);
        for r in self.inner.results() {
            let d = PyDict::new(py);
            d.set_item("id", &r.id)?;
            d.set_item("title", &r.title)?;
            d.set_item("unit", &r.unit)?;
            d.set_item("group", &r.group)?;
            d.set_item("value", to_py(py, &r.value)?)?;
            d.set_item("precision", r.precision)?;
            if let Some(n) = &r.note {
                d.set_item("note", n)?;
            }
            out.append(d)?;
        }
        Ok(out)
    }

    /// Счётчики пересчётов по метрикам (для сверки инкрементальности с эталоном).
    fn eval_counts<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let d = PyDict::new(py);
        for (k, v) in &self.inner.eval_counts {
            d.set_item(k, *v)?;
        }
        Ok(d)
    }

    /// Все сырые значения (входы, константы, метрики).
    fn raw_values<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let d = PyDict::new(py);
        for (k, v) in self.inner.raw_values() {
            d.set_item(k, to_py(py, &v)?)?;
        }
        Ok(d)
    }
}

/// Пластина карты (crates/plate): операции рендера в JSON (мм листа) → (PNG, нарисовано, пропущено, доля закраски).
/// Тексты пропускаются — подписи остаются векторными поверх пластины. transparent — фон прозрачный (слайд PPTX).
#[pyfunction]
#[pyo3(signature = (ops_json, w_mm, h_mm, dpi=300.0, transparent=false))]
fn render_plate(py: Python<'_>, ops_json: &str, w_mm: f32, h_mm: f32, dpi: f32, transparent: bool) -> PyResult<(Py<pyo3::types::PyBytes>, usize, usize, f64)> {
    let plate = py
        .detach(|| grado_plate::render_json_on(ops_json, w_mm, h_mm, dpi, transparent))
        .map_err(|e| PyValueError::new_err(e.0))?;
    let png = plate.png().map_err(|e| PyValueError::new_err(e.0))?;
    Ok((pyo3::types::PyBytes::new(py, &png).unbind(), plate.drawn, plate.skipped, plate.ink()))
}

/// Слои знака (crates/symbol, план 08.11 шаг 3): kind "poly"/"line", фигуры и части в JSON → операции рендера в JSON.
/// Тот же код собирается в WebAssembly для карты на экране (ui/src/symbology.js).
#[pyfunction]
#[pyo3(signature = (kind, shapes_json, parts_json, px_mm=0.26))]
fn parts_ops(kind: &str, shapes_json: &str, parts_json: &str, px_mm: f64) -> PyResult<String> {
    grado_symbol::parts_ops_json(kind, shapes_json, parts_json, px_mm).map_err(PyValueError::new_err)
}

/// Типы линий ЛГР (REDLN97) вдоль ломаной в мм листа (crates/symbol linetype.rs) — print_io.linetype_ops.
/// Библиотека разбирается один раз; тот же код рисует ЛГР на экране (WebAssembly).
#[pyclass(frozen)]
struct LineLib(grado_symbol::LineLib);

#[pymethods]
impl LineLib {
    #[new]
    fn new(lib_json: &str) -> PyResult<Self> {
        grado_symbol::LineLib::from_json(lib_json).map(LineLib).map_err(PyValueError::new_err)
    }
    fn has(&self, name: &str) -> bool {
        self.0.has(name)
    }
    /// Операции print_io.linetype_ops: [{"op": "path", …, "stroke": color, "rings": [[(x, y), …], …]}] —
    /// объекты Python строятся здесь же, без JSON (длинная граница — десятки тысяч точек)
    #[pyo3(signature = (pts, name, k, color, width, shape_k=None))]
    fn ops<'py>(&self, py: Python<'py>, pts: Vec<(f64, f64)>, name: &str, k: f64, color: Bound<'py, PyAny>, width: f64, shape_k: Option<f64>) -> PyResult<Bound<'py, PyList>> {
        let out = PyList::empty(py);
        if pts.len() < 2 {
            return Ok(out);
        }
        for r in self.0.runs(&pts, name, k, shape_k, width) {
            let d = PyDict::new(py);
            d.set_item("op", "path")?;
            d.set_item("closed", false)?;
            d.set_item("fill", py.None())?;
            d.set_item("stroke", &color)?;
            d.set_item("width", r.width)?;
            d.set_item("dash", py.None())?;
            d.set_item("rings", r.rings)?;
            if r.round {
                d.set_item("join", "round")?;
            }
            out.append(d)?;
        }
        Ok(out)
    }
}

#[pymodule]
fn grado_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<ComputeEngine>()?;
    m.add_function(wrap_pyfunction!(render_plate, m)?)?;
    m.add_function(wrap_pyfunction!(parts_ops, m)?)?;
    m.add_class::<LineLib>()?;
    m.add("ExpressionError", m.py().get_type::<ExpressionError>())?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
