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

#[pymodule]
fn grado_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<ComputeEngine>()?;
    m.add("ExpressionError", m.py().get_type::<ExpressionError>())?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
