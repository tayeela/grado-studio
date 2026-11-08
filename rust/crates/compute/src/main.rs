//! ТЭП-движок ГРАДО на Rust — CLI как у python -m grado_compute.
//!
//! Команды:
//!   grado_compute_rs --preset P [--set ID=ЗНАЧ]... [--json]   — расчёт ТЭП
//!   grado_compute_rs dump --preset P --set ... --out F        — дамп для сверки с Python-эталоном

use grado_compute_rs::decimal::Value;
use grado_compute_rs::engine::Engine;
use std::collections::BTreeMap;
use std::path::PathBuf;

fn value_from_str(raw: &str) -> Value {
    // как float(raw) в __main__.py: всегда float
    match raw.parse::<f64>() {
        Ok(f) => Value::Float(f),
        Err(_) => Value::Str(raw.to_string()),
    }
}

fn parse_set(items: &[String]) -> Vec<(String, Value)> {
    let mut out = Vec::new();
    for item in items {
        if let Some((k, v)) = item.split_once('=') {
            out.push((k.trim().to_string(), value_from_str(v)));
        }
    }
    out
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mode = args.first().map(String::as_str).unwrap_or("");
    if mode == "dump" {
        dump(&args[1..]);
    } else if mode == "bench" {
        bench(&args[1..]);
    } else {
        compute(&args);
    }
}

fn build_engine(args: &[String]) -> Option<Engine> {
    let mut preset_path: Option<PathBuf> = None;
    let mut sets: Vec<String> = Vec::new();
    let mut consts: Vec<String> = Vec::new();
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--preset" => {
                i += 1;
                preset_path = Some(PathBuf::from(&args[i]));
            }
            "--set" => {
                i += 1;
                sets.push(args[i].clone());
            }
            "--const" => {
                i += 1;
                consts.push(args[i].clone());
            }
            "--out" => {
                i += 1; // путь дампа — не параметр движка
            }
            "--iters" => {
                i += 1; // счётчик bench — не параметр движка
            }
            other => {
                eprintln!("неизвестный аргумент {other:?}");
                return None;
            }
        }
        i += 1;
    }
    let path = preset_path?;
    let text = match std::fs::read_to_string(&path) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("пресет не читается {}: {e}", path.display());
            return None;
        }
    };
    let mut eng = match Engine::from_preset_str(&text) {
        Ok(e) => e,
        Err(e) => {
            eprintln!("{}", e.msg);
            return None;
        }
    };
    let pairs = parse_set(&sets);
    if !pairs.is_empty() {
        if let Err(e) = eng.set_inputs(&pairs) {
            eprintln!("{}", e.msg);
            return None;
        }
    }
    let cpairs = parse_set(&consts);
    if !cpairs.is_empty() {
        if let Err(e) = eng.set_constants(&cpairs) {
            eprintln!("{}", e.msg);
            return None;
        }
    }
    Some(eng)
}

fn compute(args: &[String]) {
    let json = args.iter().any(|a| a == "--json");
    let Some(eng) = build_engine(args) else {
        std::process::exit(2);
    };
    if json {
        let rows: Vec<serde_json::Value> = eng.results().iter().map(|r| r.to_json()).collect();
        println!("{}", serde_json::to_string_pretty(&rows).unwrap());
        return;
    }
    println!("{}", eng.title);
    println!();
    println!("Входные параметры:");
    for id in eng.input_ids() {
        let v = eng.input_value(&id);
        let unit = eng.input_unit_of(&id);
        let tail = if unit.is_empty() { String::new() } else { format!(" {unit}") };
        println!("  {}: {}{}", id, v.py_repr(), tail);
    }
    let mut group = String::new();
    for row in eng.results() {
        if row.group != group {
            group = row.group.clone();
            println!("\n{group}:");
        }
        let tail = if row.unit.is_empty() { String::new() } else { format!(" {}", row.unit) };
        println!("  {}: {}{}", row.title, row.value.py_repr(), tail);
    }
}

fn bench(args: &[String]) {
    // bench --preset P --iters N: цикл set_inputs по двум входам, меряем только пересчёт
    let mut iters = 10000usize;
    let mut i = 0;
    while i < args.len() {
        if args[i] == "--iters" {
            i += 1;
            iters = args[i].parse().unwrap();
        }
        i += 1;
    }
    let Some(mut eng) = build_engine(args) else {
        std::process::exit(2);
    };
    let inputs = eng.input_ids();
    if inputs.len() < 2 {
        eprintln!("нужны хотя бы два входа для bench");
        std::process::exit(2);
    }
    let t0 = std::time::Instant::now();
    for k in 0..iters {
        let a = (k % 100) as f64 / 10.0 + 1.0;
        let b = ((k / 7) % 100) as f64 / 10.0;
        eng.set_inputs(&[
            (inputs[0].clone(), Value::Float(a)),
            (inputs[1].clone(), Value::Float(b)),
        ]).unwrap();
    }
    let dt = t0.elapsed();
    eprintln!("{} итераций set_inputs за {:?} ({:.0} оп/с)", iters, dt, iters as f64 / dt.as_secs_f64());
}

fn dump(args: &[String]) {
    let mut out = PathBuf::new();
    let mut i = 0;
    while i < args.len() {
        if args[i] == "--out" {
            i += 1;
            out = PathBuf::from(&args[i]);
        }
        i += 1;
    }
    let Some(eng) = build_engine(args) else {
        std::process::exit(2);
    };
    let mut doc = serde_json::Map::new();
    doc.insert("title".into(), serde_json::Value::String(eng.title.clone()));
    let rows: Vec<serde_json::Value> = eng.results().iter().map(|r| r.to_json()).collect();
    doc.insert("results".into(), serde_json::Value::Array(rows));
    let mut values = serde_json::Map::new();
    let raw: BTreeMap<String, Value> = eng.raw_values();
    for (k, v) in &raw {
        let mut entry = serde_json::Map::new();
        entry.insert("repr".into(), serde_json::Value::String(v.py_repr()));
        entry.insert("json".into(), v.to_json());
        values.insert(k.clone(), serde_json::Value::Object(entry));
    }
    doc.insert("values".into(), serde_json::Value::Object(values));
    let mut counts = serde_json::Map::new();
    for (k, v) in eng.eval_counts.iter() {
        counts.insert(k.clone(), serde_json::Value::Number((*v).into()));
    }
    doc.insert("eval_counts".into(), serde_json::Value::Object(counts));
    let text = serde_json::to_string_pretty(&serde_json::Value::Object(doc)).unwrap();
    if out.as_os_str().is_empty() {
        println!("{text}");
    } else {
        std::fs::write(&out, text).expect("дамп не записался");
    }
}
