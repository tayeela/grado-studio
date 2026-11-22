//! Журнал свежести слоёв и планировщик ночной выгрузки (`ogd_warm.py` → Rust, план 09.11.2026 шаг С3):
//!
//! Правила те же, что в `apps/grado2/ogd_warm.py`:
//! - слои старше `REFRESH_SECS` (20 часов) — устарели и идут на обновление, самые старые и отсутствующие первыми;
//! - с `UNTIL_UTC_HOUR` (04:00 UTC = 07:00 МСК) до 12:00 UTC новые слои ночного прогона не начинаются;
//! - итоговый отчёт `warm_status.json` имеет ту же структуру полей (`started`, `gisogd`, `egko`, `seconds`).

use std::fs;
use std::io;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

use crate::store::{check_code, file_mtime, gstore_path, lines_path, shp_gz_path, grid_dir_path};

pub const REFRESH_SECS: f64 = 20.0 * 3600.0;
pub const UNTIL_UTC_HOUR: u32 = 4;

/// Статистика ночного прогона по одному порталу (совпадает с `warm_status.json`).
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct PortalWarmStats {
    pub layers: usize,
    pub fresh: usize,
    pub got: usize,
    pub err: usize,
    pub left: usize,
}

/// Итоговый отчёт ночной выгрузки `<кэш>/warm_status.json`.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct WarmStatus {
    pub started: String,
    pub gisogd: PortalWarmStats,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub egko: Option<PortalWarmStats>,
    pub seconds: u64,
}

/// Информация о свежести одного слоя на диске.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LayerFreshness {
    pub code: String,
    pub map_name: String,
    pub age_secs: Option<f64>,
    pub fresh: bool,
    pub has_gstore: bool,
    pub has_source: bool,
}

/// Утро (07:00–15:00 МСК = 04:00–12:00 UTC): ночной прогон новых слоёв не начинает.
pub fn is_late(utc_hour: u32) -> bool {
    (UNTIL_UTC_HOUR..12).contains(&utc_hour)
}

pub fn now_unix() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

/// Возраст слоя в секундах (как `ogd_warm.ogd_age` / `egko_age`).
/// `None` — слоя нет или он недособран (эквивалент `float("inf")`).
pub fn layer_age_secs(cache_dir: &Path, map_name: &str, code: &str, now: f64) -> Option<f64> {
    check_code(code).ok()?;
    if map_name == "isogd" {
        let gz = shp_gz_path(cache_dir, code);
        let lp = lines_path(cache_dir, code);
        let gs = gstore_path(cache_dir, map_name, code);
        if let (Some(gz_t), Some(lp_t)) = (file_mtime(&gz), file_mtime(&lp)) {
            if lp_t >= gz_t {
                return Some((now - gz_t).max(0.0));
            }
        }
        if let Some(gs_t) = file_mtime(&gs) {
            return Some((now - gs_t).max(0.0));
        }
        None
    } else {
        let meta = grid_dir_path(cache_dir, map_name, code).join("_meta.json");
        if let Some(mt) = file_mtime(&meta) {
            return Some((now - mt).max(0.0));
        }
        let gs = gstore_path(cache_dir, map_name, code);
        file_mtime(&gs).map(|t| (now - t).max(0.0))
    }
}

/// Отобрать коды слоёв старше `refresh_secs`, самые старые (и отсутствующие) первыми.
pub fn stale_codes(
    cache_dir: &Path,
    map_name: &str,
    codes: &[String],
    refresh_secs: f64,
    now: f64,
) -> Vec<String> {
    let mut ranked: Vec<(f64, usize, &String)> = codes
        .iter()
        .enumerate()
        .filter_map(|(idx, c)| {
            let age = layer_age_secs(cache_dir, map_name, c, now).unwrap_or(f64::INFINITY);
            if age >= refresh_secs {
                Some((age, idx, c))
            } else {
                None
            }
        })
        .collect();
    // Сначала бесконечность (не скачанные), затем по убыванию возраста; при равенстве — исходный порядок каталога.
    ranked.sort_by(|a, b| {
        b.0.total_cmp(&a.0).then_with(|| a.1.cmp(&b.1))
    });
    ranked.into_iter().map(|(_, _, c)| c.clone()).collect()
}

/// Полный отчёт свежести по списку кодов слоя.
pub fn freshness_report(
    cache_dir: &Path,
    map_name: &str,
    codes: &[String],
    refresh_secs: f64,
    now: f64,
) -> Vec<LayerFreshness> {
    codes
        .iter()
        .map(|code| {
            let age = layer_age_secs(cache_dir, map_name, code, now);
            let gs = gstore_path(cache_dir, map_name, code);
            let src = if map_name == "isogd" {
                lines_path(cache_dir, code).exists()
            } else {
                grid_dir_path(cache_dir, map_name, code).join("_meta.json").exists()
            };
            LayerFreshness {
                code: code.clone(),
                map_name: map_name.to_string(),
                age_secs: age,
                fresh: age.map_or(false, |a| a < refresh_secs),
                has_gstore: gs.exists(),
                has_source: src,
            }
        })
        .collect()
}

/// Прочитать `warm_status.json` из папки кэша (если есть).
pub fn read_warm_status(cache_dir: &Path) -> io::Result<Option<WarmStatus>> {
    let p = cache_dir.join("warm_status.json");
    if !p.exists() {
        return Ok(None);
    }
    let text = fs::read_to_string(p)?;
    let st: WarmStatus = serde_json::from_str(&text)
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
    Ok(Some(st))
}

/// Атомарно записать `warm_status.json`.
pub fn write_warm_status(cache_dir: &Path, status: &WarmStatus) -> io::Result<()> {
    fs::create_dir_all(cache_dir)?;
    let p = cache_dir.join("warm_status.json");
    let tmp = cache_dir.join(format!("warm_status.{}.part", std::process::id()));
    let text = serde_json::to_string_pretty(status)
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
    fs::write(&tmp, text)?;
    fs::rename(&tmp, &p)?;
    Ok(())
}
