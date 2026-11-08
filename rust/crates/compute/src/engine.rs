//! ТЭП-движок — порт core/compute/grado_compute/engine.py.
//!
//! Метрика = данные (id, выражение, единица), не код. Граф зависимостей строится
//! из выражений, вычисление идёт в топологическом порядке, при изменении входа
//! пересчитывается только затронутая часть графа. Порядок топосортировки
//! воспроизводит Python-версию ровно: стартовая очередь отсортирована по id,
//! очередность добавления — по порядку метрик в пресете.

use crate::decimal::{round_half_up, Value};
use crate::expr::{self, Node};
use num_bigint::BigInt;
use serde_json::Value as J;
use std::collections::{BTreeMap, BTreeSet, HashMap, VecDeque};

/// Вид ошибки — какое исключение бросила бы Python-версия (мост PyO3 переводит вид в класс исключения).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorKind {
    /// Пресет не годится (PresetError в Python).
    Preset,
    /// Нет такого входа, константы или значения (KeyError в Python).
    UnknownName,
    /// Выражение не вычисляется (ExpressionError в Python).
    Eval,
    /// Деление на ноль при вычислении (ZeroDivisionError в Python).
    ZeroDivision,
}

#[derive(Debug)]
pub struct PresetError {
    pub kind: ErrorKind,
    pub msg: String,
}

#[allow(non_snake_case)]
pub fn PresetError(m: impl Into<String>) -> PresetError {
    PresetError { kind: ErrorKind::Preset, msg: m.into() }
}

fn unknown(m: impl Into<String>) -> PresetError {
    PresetError { kind: ErrorKind::UnknownName, msg: m.into() }
}

fn eval_err(m: String) -> PresetError {
    let kind = if m == "деление на ноль" { ErrorKind::ZeroDivision } else { ErrorKind::Eval };
    PresetError { kind, msg: m }
}

impl std::fmt::Display for PresetError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.msg)
    }
}

impl std::error::Error for PresetError {}

fn pe(m: impl Into<String>) -> PresetError {
    PresetError(m)
}

struct Metric {
    id: String,
    title: String,
    unit: String,
    precision: Option<i32>,
    group: String,
    hidden: bool,
    note: String,
    tree: Node,
    deps: BTreeSet<String>,
}

struct InputSpec {
    id: String,
    title: String,
    unit: String,
    default: Value,
}

pub struct Engine {
    pub title: String,
    inputs: Vec<InputSpec>,
    input_idx: HashMap<String, usize>,
    constant_ids: BTreeSet<String>,
    metrics: Vec<Metric>,
    metric_idx: HashMap<String, usize>,
    order: Vec<usize>,
    downstream: HashMap<String, Vec<usize>>, // имя → метрики, которые от него зависят напрямую
    values: HashMap<String, Value>,
    pub eval_counts: HashMap<String, u64>,
}

fn json_to_value(v: &J) -> Value {
    match v {
        J::Number(n) => {
            if let Some(i) = n.as_i64() {
                Value::Int(BigInt::from(i))
            } else if let Some(u) = n.as_u64() {
                // выше i64 — как long в Python (в пресетах не встречается)
                Value::Int(BigInt::from(u))
            } else {
                Value::Float(n.as_f64().unwrap_or(0.0))
            }
        }
        J::Bool(b) => Value::Bool(*b),
        J::String(s) => Value::Str(s.clone()),
        _ => Value::Int(BigInt::from(0)),
    }
}

fn spec_str(spec: &J, key: &str, default: &str) -> String {
    spec.get(key)
        .and_then(|v| v.as_str())
        .unwrap_or(default)
        .to_string()
}

impl Engine {
    pub fn from_preset(preset: &J) -> Result<Engine, PresetError> {
        let title = spec_str(preset, "title", "");

        let mut inputs: Vec<InputSpec> = Vec::new();
        let mut input_idx = HashMap::new();
        for (_i, spec) in preset
            .get("inputs")
            .and_then(|v| v.as_array())
            .map(|a| a.as_slice())
            .unwrap_or(&[])
            .iter()
            .enumerate()
        {
            let id = spec
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| pe("у входа нет id"))?
                .to_string();
            let default = spec.get("default").map(json_to_value).unwrap_or(Value::Int(BigInt::from(0)));
            input_idx.insert(id.clone(), inputs.len());
            inputs.push(InputSpec {
                id,
                title: spec_str(spec, "title", ""),
                unit: spec_str(spec, "unit", ""),
                default,
            });
        }

        let mut constants: HashMap<String, Value> = HashMap::new();
        let mut constant_ids: BTreeSet<String> = BTreeSet::new();
        if let Some(J::Object(map)) = preset.get("constants") {
            for (k, v) in map {
                constants.insert(k.clone(), json_to_value(v));
                constant_ids.insert(k.clone());
            }
        }

        let mut metrics: Vec<Metric> = Vec::new();
        let mut metric_idx: HashMap<String, usize> = HashMap::new();
        for spec in preset
            .get("metrics")
            .and_then(|v| v.as_array())
            .map(|a| a.as_slice())
            .unwrap_or(&[])
        {
            let id = spec
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| pe("у метрики нет id"))?
                .to_string();
            if metrics.iter().any(|m| m.id == id)
                || input_idx.contains_key(&id)
                || constants.contains_key(&id)
            {
                return Err(pe(format!("дублирующийся идентификатор {id:?}")));
            }
            let expr_src = spec
                .get("expr")
                .and_then(|v| v.as_str())
                .ok_or_else(|| pe(format!("у метрики {id:?} нет выражения")))?;
            let tree =
                expr::parse(expr_src).map_err(|e| eval_err(e.to_string()))?;
            let deps = expr::names(&tree);
            metric_idx.insert(id.clone(), metrics.len());
            metrics.push(Metric {
                id,
                title: spec_str(spec, "title", ""),
                unit: spec_str(spec, "unit", ""),
                precision: spec.get("precision").and_then(|v| v.as_i64()).map(|v| v as i32),
                group: spec_str(spec, "group", ""),
                hidden: spec.get("hidden").and_then(|v| v.as_bool()).unwrap_or(false),
                note: spec_str(spec, "note", ""),
                tree,
                deps,
            });
        }

        // неизвестные имена
        let known: BTreeSet<String> = inputs
            .iter()
            .map(|i| i.id.clone())
            .chain(constants.keys().cloned())
            .chain(metrics.iter().map(|m| m.id.clone()))
            .collect();
        for m in &metrics {
            let unknown: Vec<&String> = m.deps.iter().filter(|d| !known.contains(*d)).collect();
            if !unknown.is_empty() {
                let list: Vec<String> = unknown.into_iter().map(|s| s.to_string()).collect();
                return Err(pe(format!(
                    "метрика {:?} ссылается на неизвестные имена {:?}",
                    m.id, list
                )));
            }
        }

        // топосортировка: стартовая очередь отсортирована, добавление — по порядку метрик пресета
        let n = metrics.len();
        let mut indeg = vec![0usize; n];
        let mut dependents: Vec<Vec<usize>> = vec![Vec::new(); n];
        for (mi, m) in metrics.iter().enumerate() {
            for d in &m.deps {
                if let Some(di) = metric_idx.get(d) {
                    indeg[mi] += 1;
                    dependents[*di].push(mi);
                }
            }
        }
        let mut init_queue: Vec<usize> = (0..n).filter(|mi| indeg[*mi] == 0).collect();
        init_queue.sort_by(|a, b| metrics[*a].id.cmp(&metrics[*b].id));
        let mut queue: VecDeque<usize> = init_queue.into();
        let mut order = Vec::with_capacity(n);
        while let Some(mid) = queue.pop_front() {
            order.push(mid);
            for dep in &dependents[mid] {
                indeg[*dep] -= 1;
                if indeg[*dep] == 0 {
                    queue.push_back(*dep);
                }
            }
        }
        if order.len() != n {
            let mut cycle: Vec<String> =
                (0..n).filter(|mi| !order.contains(mi)).map(|mi| metrics[mi].id.clone()).collect();
            cycle.sort();
            return Err(pe(format!("цикл в зависимостях метрик: {cycle:?}")));
        }

        // downstream: имя → метрики, напрямую от него зависящие (порядок метрик пресета)
        let mut downstream: HashMap<String, Vec<usize>> = HashMap::new();
        for name in known.iter() {
            downstream.insert(name.clone(), Vec::new());
        }
        for (mi, m) in metrics.iter().enumerate() {
            for d in &m.deps {
                downstream.entry(d.clone()).or_default().push(mi);
            }
        }

        let mut values: HashMap<String, Value> = constants;
        for i in &inputs {
            values.insert(i.id.clone(), i.default.clone());
        }
        let eval_counts: HashMap<String, u64> =
            metrics.iter().map(|m| (m.id.clone(), 0)).collect();

        let mut eng = Engine {
            title,
            inputs,
            input_idx,
            constant_ids,
            metrics,
            metric_idx,
            order,
            downstream,
            values,
            eval_counts,
        };
        let all: BTreeSet<usize> = (0..n).collect();
        eng.recompute(&all)?;
        Ok(eng)
    }

    pub fn from_preset_str(text: &str) -> Result<Engine, PresetError> {
        let preset: J = serde_json::from_str(text)
            .map_err(|e| PresetError(format!("пресет не читается: {e}")))?;
        Self::from_preset(&preset)
    }

    pub fn input_ids(&self) -> Vec<String> {
        self.inputs.iter().map(|i| i.id.clone()).collect()
    }

    pub fn input_unit_of(&self, id: &str) -> String {
        self.inputs
            .iter()
            .find(|i| i.id == id)
            .map(|i| i.unit.clone())
            .unwrap_or_default()
    }

    pub fn input_value(&self, id: &str) -> Value {
        self.values.get(id).cloned().unwrap_or(Value::Int(BigInt::from(0)))
    }

    /// Пересчёт грязных метрик по порядку; ошибка выражения прерывает пересчёт,
    /// уже вычисленное остаётся (как исключение посреди цикла в Python-версии).
    fn recompute(&mut self, dirty: &BTreeSet<usize>) -> Result<(), PresetError> {
        for mi in &self.order {
            if dirty.contains(mi) {
                let m = &self.metrics[*mi];
                let v = expr::evaluate(&m.tree, &|n| self.values.get(n).cloned())
                    .map_err(|e| eval_err(e.to_string()))?;
                self.values.insert(m.id.clone(), v);
                *self.eval_counts.get_mut(&m.id).unwrap() += 1;
            }
        }
        Ok(())
    }

    fn dirty_set(&self, source: &str) -> BTreeSet<usize> {
        let mut dirty = BTreeSet::new();
        let mut queue = vec![source.to_string()];
        while let Some(name) = queue.pop() {
            for mi in self.downstream.get(&name).into_iter().flatten() {
                if dirty.insert(*mi) {
                    queue.push(self.metrics[*mi].id.clone());
                }
            }
        }
        dirty
    }

    pub fn set_input(&mut self, input_id: &str, value: Value) -> Result<(), PresetError> {
        if !self.input_idx.contains_key(input_id) {
            return Err(unknown(format!("нет входного параметра {input_id:?}")));
        }
        self.values.insert(input_id.to_string(), value);
        let dirty = self.dirty_set(input_id);
        self.recompute(&dirty)
    }

    /// set_inputs: атомарно — неизвестный ключ отменяет всё (как в Python-версии).
    pub fn set_inputs(&mut self, pairs: &[(String, Value)]) -> Result<(), PresetError> {
        for (k, _) in pairs {
            if !self.input_idx.contains_key(k) {
                return Err(unknown(format!("нет входного параметра {k:?}")));
            }
        }
        let mut dirty = BTreeSet::new();
        for (k, v) in pairs {
            self.values.insert(k.clone(), v.clone());
            dirty.extend(self.dirty_set(k));
        }
        self.recompute(&dirty)
    }

    /// Подмена норм (констант пресета) перед расчётом; неизвестное имя — ошибка до записи.
    pub fn set_constants(&mut self, pairs: &[(String, Value)]) -> Result<(), PresetError> {
        for (k, _) in pairs {
            if !self.constant_ids.contains(k) {
                return Err(unknown(format!("нет константы {k:?}")));
            }
        }
        let mut dirty = BTreeSet::new();
        for (k, v) in pairs {
            self.values.insert(k.clone(), v.clone());
            dirty.extend(self.dirty_set(k));
        }
        self.recompute(&dirty)
    }

    pub fn value(&self, name: &str) -> Result<Value, PresetError> {
        self.values
            .get(name)
            .cloned()
            .ok_or_else(|| unknown(format!("нет значения {name:?}")))
    }

    /// Значение для показа: округление по precision, целый float → int (как в Python-версии).
    pub fn display(&self, name: &str) -> Result<Value, PresetError> {
        let mut v = self.value(name)?;
        if let Some(mi) = self.metric_idx.get(name) {
            let m = &self.metrics[*mi];
            if let Some(p) = m.precision {
                if let Ok(x) = v.as_f64() {
                    v = round_half_up(x, p).map_err(|e| PresetError(e))?;
                }
            }
        }
        if let Value::Float(f) = v {
            if f.is_finite() && f.fract() == 0.0 && f.abs() < 9.0e15 {
                v = Value::Int(BigInt::from(f as i128));
            }
        }
        Ok(v)
    }

    /// Строки результатов в топологическом порядке, скрытые пропускаются.
    pub fn results(&self) -> Vec<Row> {
        let mut out = Vec::new();
        for mi in &self.order {
            let m = &self.metrics[*mi];
            if m.hidden {
                continue;
            }
            let value = self.display(&m.id).unwrap_or(Value::Int(BigInt::from(0)));
            out.push(Row {
                id: m.id.clone(),
                title: m.title.clone(),
                unit: m.unit.clone(),
                group: m.group.clone(),
                value,
                precision: m.precision,
                note: if m.note.is_empty() { None } else { Some(m.note.clone()) },
            });
        }
        out
    }

    /// Все сырые значения (для сверки с Python-эталоном), имена отсортированы.
    pub fn raw_values(&self) -> BTreeMap<String, Value> {
        self.values.iter().map(|(k, v)| (k.clone(), v.clone())).collect()
    }
}

/// Строка results() с порядком ключей как в Python-версии (id, title, unit, group, value, precision, note).
pub struct Row {
    pub id: String,
    pub title: String,
    pub unit: String,
    pub group: String,
    pub value: Value,
    pub precision: Option<i32>,
    pub note: Option<String>,
}

impl Row {
    pub fn to_json(&self) -> serde_json::Value {
        let mut map = serde_json::Map::new();
        map.insert("id".into(), serde_json::Value::String(self.id.clone()));
        map.insert("title".into(), serde_json::Value::String(self.title.clone()));
        map.insert("unit".into(), serde_json::Value::String(self.unit.clone()));
        map.insert("group".into(), serde_json::Value::String(self.group.clone()));
        map.insert("value".into(), self.value.to_json());
        map.insert(
            "precision".into(),
            match self.precision {
                Some(p) => serde_json::Value::Number(serde_json::Number::from(p)),
                None => serde_json::Value::Null,
            },
        );
        if let Some(note) = &self.note {
            map.insert("note".into(), serde_json::Value::String(note.clone()));
        }
        serde_json::Value::Object(map)
    }
}
