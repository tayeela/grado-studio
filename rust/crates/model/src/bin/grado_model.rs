//! grado_model — проверка файла проекта из командной строки (для сверки на копиях проектов).
//!   grado_model check <файл.grado2>       → отчёт проверки (JSON), код выхода 1 при ошибках
//!   grado_model roundtrip <файл.grado2>   → «без потерь» или первое отличие, код выхода 1 при отличии

use grado_model::{check_text, Project};
use serde_json::Value;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let (Some(cmd), Some(path)) = (args.get(1), args.get(2)) else {
        eprintln!("вызов: grado_model check|roundtrip <файл.grado2>");
        std::process::exit(2);
    };
    let text = std::fs::read_to_string(path).unwrap_or_else(|e| {
        eprintln!("{path}: {e}");
        std::process::exit(2)
    });
    match cmd.as_str() {
        "check" => {
            let r = check_text(&text);
            println!("{}", serde_json::to_string_pretty(&r).unwrap());
            std::process::exit(if r.ok { 0 } else { 1 });
        }
        "roundtrip" => {
            let want: Value = match serde_json::from_str(&text) {
                Ok(v) => v,
                Err(e) => {
                    eprintln!("не JSON: {e}");
                    std::process::exit(1)
                }
            };
            let p = Project::parse(&text).unwrap_or_else(|e| {
                eprintln!("{e}");
                std::process::exit(1)
            });
            let got: Value = serde_json::from_str(&p.to_json()).unwrap();
            if got == want {
                println!("{path}: без потерь ({} байт)", text.len());
            } else {
                println!("{path}: ОТЛИЧИЕ после записи");
                std::process::exit(1);
            }
        }
        _ => {
            eprintln!("неизвестная команда {cmd}");
            std::process::exit(2);
        }
    }
}
