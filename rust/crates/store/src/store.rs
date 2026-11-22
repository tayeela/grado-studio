//! Хранилище слоёв на диске (`LayerStore`):
//! - автоматическая сборка и проверка свежести `.gstore` рядом с `.shp.lines2.gz` (ГИС ОГД) и `.shp.grid` (ЕГКО);
//! - вырезка по прямоугольнику WGS84 (`query`) и подсчёт объектов по каталогу (`scan`);
//! - плитки карты XYZ (`tile_bbox`, `query_tile_geojson`) для быстрого показа тяжёлых слоёв.

use std::collections::HashMap;
use std::f64::consts::PI;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

use crate::format::{read_meta, LayerIndex, LayerMeta, StoredFeature};
use crate::freshness::now_unix;
use crate::ingest::{build_from_grid_dir, build_from_lines_gz};

/// Проверка кода слоя (совпадает с `gisogd_api._check_code`).
pub fn check_code(code: &str) -> io::Result<()> {
    if code.is_empty()
        || code.starts_with('.')
        || code.contains("..")
        || !code
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'.' || b == b'-')
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "ГИС ОГД: недопустимый код слоя",
        ));
    }
    Ok(())
}

pub fn file_mtime(path: &Path) -> Option<f64> {
    fs::metadata(path)
        .ok()?
        .modified()
        .ok()?
        .duration_since(UNIX_EPOCH)
        .ok()
        .map(|d| d.as_secs_f64())
}

pub fn shp_gz_path(cache_dir: &Path, code: &str) -> PathBuf {
    cache_dir.join(format!("{code}.shp.gz"))
}

pub fn lines_path(cache_dir: &Path, code: &str) -> PathBuf {
    cache_dir.join(format!("{code}.shp.lines2.gz"))
}

pub fn grid_dir_path(cache_dir: &Path, map_name: &str, code: &str) -> PathBuf {
    cache_dir.join(format!("{map_name}.{code}.shp.grid"))
}

pub fn gstore_path(cache_dir: &Path, map_name: &str, code: &str) -> PathBuf {
    if map_name == "isogd" {
        cache_dir.join(format!("{code}.gstore"))
    } else {
        cache_dir.join(format!("{map_name}.{code}.gstore"))
    }
}

/// Преобразовать координаты XYZ-плитки (Web Mercator) в прямоугольник WGS84 `[w, s, e, n]` с запасом `buffer_frac`.
pub fn tile_bbox(z: u32, x: u32, y: u32, buffer_frac: f64) -> [f64; 4] {
    let n = (1u64 << z.min(28)) as f64;
    let lon_of = |tx: f64| tx / n * 360.0 - 180.0;
    let lat_of = |ty: f64| {
        let rad = (PI * (1.0 - 2.0 * ty / n)).sinh().atan();
        rad.to_degrees()
    };
    let fx = x as f64;
    let fy = y as f64;
    let w = lon_of(fx - buffer_frac);
    let e = lon_of(fx + 1.0 + buffer_frac);
    let north = lat_of((fy - buffer_frac).max(0.0));
    let south = lat_of((fy + 1.0 + buffer_frac).min(n));
    [w, south, e, north]
}

/// Управляющее хранилище слоёв в одной папке кэша (`~/.grado2/cache/gisogd` или `~/.grado2/cache/egko`).
#[derive(Debug, Clone)]
pub struct LayerStore {
    pub cache_dir: PathBuf,
    pub map_name: String,
}

impl LayerStore {
    pub fn new(cache_dir: impl Into<PathBuf>, map_name: impl Into<String>) -> Self {
        Self {
            cache_dir: cache_dir.into(),
            map_name: map_name.into(),
        }
    }

    /// Убедиться, что для слоя `code` есть актуальный `.gstore` (в пределах `ttl_secs`).
    /// Если исходник (`.shp.lines2.gz` или `.shp.grid`) есть и свеж, но `.gstore` отсутствует или устарел,
    /// пересобирает `.gstore` на месте. Возвращает путь к `.gstore` или `None`, если слоя нет/истёк TTL.
    pub fn ensure_index(&self, code: &str, ttl_secs: Option<f64>) -> io::Result<Option<PathBuf>> {
        check_code(code)?;
        let now = now_unix();
        let gs = gstore_path(&self.cache_dir, &self.map_name, code);

        if self.map_name == "isogd" {
            let gz = shp_gz_path(&self.cache_dir, code);
            let lp = lines_path(&self.cache_dir, code);
            let gz_m = file_mtime(&gz);
            let lp_m = file_mtime(&lp);

            // Если есть исходные файлы .shp.gz и .shp.lines2.gz — ориентируемся на них (совместимость с Python-кэшем)
            if let (Some(gz_t), Some(lp_t)) = (gz_m, lp_m) {
                if lp_t < gz_t {
                    return Ok(None);
                }
                if let Some(ttl) = ttl_secs {
                    if (now - gz_t) >= ttl {
                        return Ok(None);
                    }
                }
                let need_build = match read_meta(&gs) {
                    Ok(meta) => (meta.source_mtime - lp_t).abs() > 1e-3 && meta.source_mtime < lp_t,
                    Err(_) => true,
                };
                if need_build {
                    build_from_lines_gz(&lp, &gs, code, &self.map_name, lp_t)?;
                }
                return Ok(Some(gs));
            }
            // Автономный .gstore без .shp.lines2.gz (например, собранный напрямую или в тестах)
            if let Some(gs_t) = file_mtime(&gs) {
                if let Some(ttl) = ttl_secs {
                    if (now - gs_t) >= ttl {
                        return Ok(None);
                    }
                }
                if read_meta(&gs).is_ok() {
                    return Ok(Some(gs));
                }
            }
            Ok(None)
        } else {
            let gdir = grid_dir_path(&self.cache_dir, &self.map_name, code);
            let meta_p = gdir.join("_meta.json");
            if let Some(mt) = file_mtime(&meta_p) {
                if let Some(ttl) = ttl_secs {
                    if (now - mt) >= ttl {
                        return Ok(None);
                    }
                }
                let need_build = match read_meta(&gs) {
                    Ok(meta) => (meta.source_mtime - mt).abs() > 1e-3 && meta.source_mtime < mt,
                    Err(_) => true,
                };
                if need_build {
                    build_from_grid_dir(&gdir, &gs, code, &self.map_name, mt)?;
                }
                return Ok(Some(gs));
            }
            if let Some(gs_t) = file_mtime(&gs) {
                if let Some(ttl) = ttl_secs {
                    if (now - gs_t) >= ttl {
                        return Ok(None);
                    }
                }
                if read_meta(&gs).is_ok() {
                    return Ok(Some(gs));
                }
            }
            Ok(None)
        }
    }

    /// Принудительно построить или обновить индекс `.gstore` для слоя (вызывается из `ogd_warm.py` / после скачивания).
    pub fn sync_layer(&self, code: &str) -> io::Result<Option<LayerMeta>> {
        match self.ensure_index(code, None)? {
            Some(p) => Ok(Some(read_meta(&p)?)),
            None => Ok(None),
        }
    }

    /// Выборка объектов слоя по прямоугольнику WGS84 `[w, s, e, n]`.
    pub fn query(
        &self,
        code: &str,
        bbox: [f64; 4],
        ttl_secs: Option<f64>,
    ) -> io::Result<Option<Vec<StoredFeature>>> {
        let Some(p) = self.ensure_index(code, ttl_secs)? else {
            return Ok(None);
        };
        let mut idx = match LayerIndex::open(&p) {
            Ok(i) => i,
            Err(_) => {
                let _ = fs::remove_file(&p);
                let Some(p2) = self.ensure_index(code, ttl_secs)? else {
                    return Ok(None);
                };
                LayerIndex::open(&p2)?
            }
        };
        idx.query_bbox(bbox).map(Some)
    }

    /// Подсчёт объектов по списку слоёв в области (замена медленного `ogd_all.scan`).
    /// Для отсутствующих/устаревших слоёв в словаре лежит `None`.
    pub fn scan(
        &self,
        codes: &[String],
        bbox: [f64; 4],
        ttl_secs: Option<f64>,
        exact_geom: bool,
    ) -> HashMap<String, Option<usize>> {
        let mut out = HashMap::with_capacity(codes.len());
        for code in codes {
            let val = match self.ensure_index(code, ttl_secs) {
                Ok(Some(p)) => LayerIndex::open(&p)
                    .and_then(|mut idx| idx.count_bbox(bbox, exact_geom))
                    .ok(),
                _ => None,
            };
            out.insert(code.clone(), val);
        }
        out
    }

    /// Вырезка плитки карты XYZ в формате GeoJSON FeatureCollection.
    pub fn tile_geojson(
        &self,
        code: &str,
        z: u32,
        x: u32,
        y: u32,
        ttl_secs: Option<f64>,
        buffer_frac: f64,
    ) -> io::Result<Option<String>> {
        let bbox = tile_bbox(z, x, y, buffer_frac);
        let Some(feats) = self.query(code, bbox, ttl_secs)? else {
            return Ok(None);
        };
        let mut out = String::with_capacity(feats.len() * 192 + 64);
        out.push_str("{\"type\":\"FeatureCollection\",\"features\":[");
        for (i, f) in feats.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            // payload_json имеет вид {"geometry":...,"properties":...} — превращаем в Feature с grado_key
            let body = f.payload_json.trim();
            if body.starts_with('{') && body.ends_with('}') {
                out.push_str("{\"type\":\"Feature\",\"grado_key\":");
                out.push_str(&serde_json::to_string(&f.key).unwrap_or_else(|_| "\"\"".to_string()));
                out.push(',');
                out.push_str(&body[1..]);
            }
        }
        out.push_str("]}");
        Ok(Some(out))
    }
}
