//! CLI `grado_store`: индексация, вырезка, подсчёт, плитки и проверка свежести слоёв на диске.
//!
//! Использование:
//!   grado_store index  <cache_dir> <map_name> <code>
//!   grado_store query  <cache_dir> <map_name> <code> <w,s,e,n>
//!   grado_store scan   <cache_dir> <map_name> <w,s,e,n> <code1> [code2 ...]
//!   grado_store tile   <cache_dir> <map_name> <code> <z> <x> <y>
//!   grado_store status <cache_dir> <map_name> <code1> [code2 ...]

use std::env;
use std::path::PathBuf;
use std::process::ExitCode;
use std::time::Instant;

use grado_store::{freshness_report, LayerStore, REFRESH_SECS};

fn parse_bbox(s: &str) -> Result<[f64; 4], String> {
    let v: Result<Vec<f64>, _> = s.split(',').map(|x| x.trim().parse::<f64>()).collect();
    let v = v.map_err(|_| format!("неверный bbox: {s}"))?;
    if v.len() != 4 {
        return Err(format!("нужны 4 числа w,s,e,n: {s}"));
    }
    Ok([v[0], v[1], v[2], v[3]])
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.len() < 4 {
        eprintln!("Использование: grado_store <index|query|scan|tile|status> <cache_dir> <map_name> ...");
        return ExitCode::from(2);
    }
    let cmd = args[0].as_str();
    let dir = PathBuf::from(&args[1]);
    let map = args[2].as_str();
    let store = LayerStore::new(&dir, map);

    match cmd {
        "index" => {
            let code = &args[3];
            let t0 = Instant::now();
            match store.sync_layer(code) {
                Ok(Some(meta)) => {
                    println!(
                        "{}",
                        serde_json::json!({
                            "code": meta.code,
                            "features": meta.feature_count,
                            "bbox": meta.bbox,
                            "ms": t0.elapsed().as_secs_f64() * 1000.0
                        })
                    );
                    ExitCode::SUCCESS
                }
                Ok(None) => {
                    eprintln!("слой {code} не найден в {}", dir.display());
                    ExitCode::FAILURE
                }
                Err(e) => {
                    eprintln!("ошибка: {e}");
                    ExitCode::FAILURE
                }
            }
        }
        "query" if args.len() >= 5 => {
            let code = &args[3];
            let bbox = match parse_bbox(&args[4]) {
                Ok(b) => b,
                Err(e) => { eprintln!("{e}"); return ExitCode::from(2); }
            };
            let t0 = Instant::now();
            match store.query(code, bbox, None) {
                Ok(Some(feats)) => {
                    println!(
                        "{}",
                        serde_json::json!({
                            "code": code,
                            "count": feats.len(),
                            "ms": t0.elapsed().as_secs_f64() * 1000.0
                        })
                    );
                    ExitCode::SUCCESS
                }
                Ok(None) => {
                    eprintln!("слой {code} отсутствует");
                    ExitCode::FAILURE
                }
                Err(e) => { eprintln!("ошибка: {e}"); ExitCode::FAILURE }
            }
        }
        "scan" if args.len() >= 5 => {
            let bbox = match parse_bbox(&args[3]) {
                Ok(b) => b,
                Err(e) => { eprintln!("{e}"); return ExitCode::from(2); }
            };
            let codes: Vec<String> = args[4..].to_vec();
            let t0 = Instant::now();
            let counts = store.scan(&codes, bbox, None, true);
            println!(
                "{}",
                serde_json::json!({
                    "counts": counts,
                    "ms": t0.elapsed().as_secs_f64() * 1000.0
                })
            );
            ExitCode::SUCCESS
        }
        "tile" if args.len() >= 7 => {
            let code = &args[3];
            let z: u32 = args[4].parse().unwrap_or(0);
            let x: u32 = args[5].parse().unwrap_or(0);
            let y: u32 = args[6].parse().unwrap_or(0);
            match store.tile_geojson(code, z, x, y, None, 0.05) {
                Ok(Some(js)) => { println!("{js}"); ExitCode::SUCCESS }
                Ok(None) => { eprintln!("слой {code} отсутствует"); ExitCode::FAILURE }
                Err(e) => { eprintln!("ошибка: {e}"); ExitCode::FAILURE }
            }
        }
        "status" => {
            let codes: Vec<String> = args[3..].to_vec();
            let now = grado_store::freshness::now_unix();
            let rep = freshness_report(&dir, map, &codes, REFRESH_SECS, now);
            println!("{}", serde_json::to_string_pretty(&rep).unwrap());
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("неизвестная команда или мало аргументов: {cmd}");
            ExitCode::from(2)
        }
    }
}
