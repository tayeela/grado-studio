//! Сборка `.gstore` из существующих форматов кэша ГРАДО:
//! - ГИС ОГД (`<code>.shp.lines2.gz`) — потоковое чтение gzip в Rust;
//! - ЕГКО (`base2.<code>.shp.grid/*.lines.gz`) — чтение всех клеток сетки в единый R-дерево файл.
//!
//! Строка формата `.lines2.gz` / `.lines.gz`: `w,s,e,n\tkey\t{"geometry":...,"properties":...}\n`.

use std::fs::{self, File};
use std::io::{self, BufRead, BufReader};
use std::path::Path;

use flate2::read::MultiGzDecoder;

use crate::format::{write_layer, LayerMeta, StoredFeature};

fn parse_line(line: &str) -> Option<StoredFeature> {
    let trimmed = line.trim_end_matches(&['\r', '\n'][..]);
    if trimmed.is_empty() {
        return None;
    }
    let mut parts = trimmed.splitn(3, '\t');
    let bb_s = parts.next()?;
    let key = parts.next()?;
    let payload = parts.next()?;

    let mut nums = bb_s.split(',');
    let w: f64 = nums.next()?.parse().ok()?;
    let s: f64 = nums.next()?.parse().ok()?;
    let e: f64 = nums.next()?.parse().ok()?;
    let n: f64 = nums.next()?.parse().ok()?;
    if !(w.is_finite() && s.is_finite() && e.is_finite() && n.is_finite()) {
        return None;
    }
    Some(StoredFeature {
        bbox: [w, s, e, n],
        key: key.to_string(),
        payload_json: payload.to_string(),
    })
}

fn read_lines_gz_into(path: &Path, out: &mut Vec<StoredFeature>) -> io::Result<()> {
    let f = File::open(path)?;
    // MultiGzDecoder важен для ЕГКО: flush() дописывает в клетку несколько склеенных gzip-членов.
    let dec = MultiGzDecoder::new(BufReader::with_capacity(1 << 16, f));
    let mut reader = BufReader::with_capacity(1 << 16, dec);
    let mut line = String::new();
    loop {
        line.clear();
        let n = reader.read_line(&mut line)?;
        if n == 0 {
            break;
        }
        if let Some(rec) = parse_line(&line) {
            out.push(rec);
        }
    }
    Ok(())
}

/// Собрать `.gstore` из одного файла `<code>.shp.lines2.gz`.
pub fn build_from_lines_gz(
    lines_gz: &Path,
    out_path: &Path,
    code: &str,
    map_name: &str,
    source_mtime: f64,
) -> io::Result<LayerMeta> {
    let mut records = Vec::new();
    read_lines_gz_into(lines_gz, &mut records)?;
    write_layer(out_path, code, map_name, source_mtime, records)
}

/// Собрать `.gstore` из папки клеток сетки ЕГКО (`base2.<code>.shp.grid`).
pub fn build_from_grid_dir(
    grid_dir: &Path,
    out_path: &Path,
    code: &str,
    map_name: &str,
    source_mtime: f64,
) -> io::Result<LayerMeta> {
    let mut files = Vec::new();
    for ent in fs::read_dir(grid_dir)? {
        let ent = ent?;
        let p = ent.path();
        if p.file_name()
            .and_then(|s| s.to_str())
            .map_or(false, |n| n.ends_with(".lines.gz"))
        {
            files.push(p);
        }
    }
    files.sort();
    let mut records = Vec::new();
    for p in files {
        read_lines_gz_into(&p, &mut records)?;
    }
    write_layer(out_path, code, map_name, source_mtime, records)
}
