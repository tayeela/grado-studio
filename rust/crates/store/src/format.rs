//! Бинарный формат слоя `.gstore` с пространственным индексом `rstar`:
//!
//! Устройство файла:
//!   [0..8]   магия `GRST0001`
//!   [8..16]  число объектов `u64` (LE)
//!   [16..24] смещение индекса блоков `u64` (LE)
//!   [24..32] смещение JSON-метаданных `u64` (LE)
//!   [32..index_offset]  сжатые (zlib/deflate) пространственные блоки по 64 (мелкие) / 16 (крупные) объекта:
//!                       внутри блока подряд записи `[f64;4 bbox][u32 key_len][key][u32 json_len][json]`
//!   [index_offset..meta_offset]  массив записей блоков: `[u32 block_count]` затем `block_count` раз
//!                       `[f64;4 bbox][u64 offset][u32 comp_len][u32 count]`
//!   [meta_offset..EOF]  JSON `LayerMeta` (код, карта, число объектов, общий габарит, mtime источника, время сборки).
//!
//! Почему не FlatGeobuf: проверка показала, что FlatGeobuf требует фиксированной типизированной схемы колонок
//! на весь слой (риск потери/приведения разнотипных атрибутов ГИС ОГД и `grado_key`) и тянет `geozero`/`flatbuffers`.
//! `.gstore` хранит сырой GeoJSON + `grado_key` без потерь (100 % совпадение с Python), использует только `rstar` + `flate2`,
//! занимает столько же места на диске, как `.lines2.gz`, и отдаёт вырезку за O(log B + K) миллисекунд.

use std::fs::{self, File};
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use flate2::read::DeflateDecoder;
use flate2::write::DeflateEncoder;
use flate2::Compression;
use rstar::{RTree, RTreeObject, AABB};
use serde::{Deserialize, Serialize};

pub const MAGIC: &[u8; 8] = b"GRST0001";
const HEADER_LEN: usize = 32;
const SMALL_BLOCK: usize = 64;
const LARGE_BLOCK: usize = 16;
const LARGE_SPAN_DEG: f64 = 0.05;

/// Одна запись объекта при сборке или выборке из хранилища.
#[derive(Debug, Clone, PartialEq)]
pub struct StoredFeature {
    pub bbox: [f64; 4],
    pub key: String,
    /// JSON вида `{"geometry":...,"properties":...}` — совместим со строками `.shp.lines2.gz`.
    pub payload_json: String,
}

/// Метаданные слоя в хвосте файла `.gstore`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LayerMeta {
    pub code: String,
    pub map_name: String,
    pub feature_count: u64,
    pub bbox: Option<[f64; 4]>,
    pub source_mtime: f64,
    pub built_at: f64,
    pub format: String,
}

#[derive(Debug, Clone, Copy)]
pub struct BlockMeta {
    pub bbox: [f64; 4],
    pub offset: u64,
    pub comp_len: u32,
    pub count: u32,
}

impl RTreeObject for BlockMeta {
    type Envelope = AABB<[f64; 2]>;

    fn envelope(&self) -> Self::Envelope {
        AABB::from_corners([self.bbox[0], self.bbox[1]], [self.bbox[2], self.bbox[3]])
    }
}

/// Проверка перекрытия двух прямоугольников (совпадает с `gisogd_api._overlaps`).
#[inline]
pub fn overlaps(a: [f64; 4], b: [f64; 4]) -> bool {
    !(a[2] < b[0] || a[0] > b[2] || a[3] < b[1] || a[1] > b[3])
}

#[inline]
pub fn contains_box(outer: [f64; 4], inner: [f64; 4]) -> bool {
    inner[0] >= outer[0] && inner[2] <= outer[2] && inner[1] >= outer[1] && inner[3] <= outer[3]
}

fn expand_bbox(acc: &mut Option<[f64; 4]>, b: [f64; 4]) {
    match acc {
        Some(a) => {
            if b[0] < a[0] { a[0] = b[0]; }
            if b[1] < a[1] { a[1] = b[1]; }
            if b[2] > a[2] { a[2] = b[2]; }
            if b[3] > a[3] { a[3] = b[3]; }
        }
        None => *acc = Some(b),
    }
}

fn spread_bits(mut v: u32) -> u32 {
    v &= 0x0000_ffff;
    v = (v | (v << 8)) & 0x00ff_00ff;
    v = (v | (v << 4)) & 0x0f0f_0f0f;
    v = (v | (v << 2)) & 0x3333_3333;
    v = (v | (v << 1)) & 0x5555_5555;
    v
}

fn morton_key(bbox: [f64; 4], global: [f64; 4]) -> u32 {
    let cx = 0.5 * (bbox[0] + bbox[2]);
    let cy = 0.5 * (bbox[1] + bbox[3]);
    let dx = (global[2] - global[0]).max(1e-9);
    let dy = (global[3] - global[1]).max(1e-9);
    let nx = (((cx - global[0]) / dx).clamp(0.0, 1.0) * 65535.0) as u32;
    let ny = (((cy - global[1]) / dy).clamp(0.0, 1.0) * 65535.0) as u32;
    spread_bits(nx) | (spread_bits(ny) << 1)
}

fn now_unix() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

fn write_block(
    out: &mut File,
    items: &[StoredFeature],
) -> io::Result<BlockMeta> {
    let offset = out.stream_position()?;
    let mut bbox: Option<[f64; 4]> = None;
    let mut raw = Vec::with_capacity(items.len() * 256);
    for it in items {
        expand_bbox(&mut bbox, it.bbox);
        for v in it.bbox {
            raw.extend_from_slice(&v.to_le_bytes());
        }
        let kb = it.key.as_bytes();
        let pb = it.payload_json.as_bytes();
        raw.extend_from_slice(&(kb.len() as u32).to_le_bytes());
        raw.extend_from_slice(kb);
        raw.extend_from_slice(&(pb.len() as u32).to_le_bytes());
        raw.extend_from_slice(pb);
    }
    let mut enc = DeflateEncoder::new(Vec::with_capacity(raw.len() / 3), Compression::fast());
    enc.write_all(&raw)?;
    let comp = enc.finish()?;
    out.write_all(&comp)?;
    Ok(BlockMeta {
        bbox: bbox.unwrap_or([0.0; 4]),
        offset,
        comp_len: comp.len() as u32,
        count: items.len() as u32,
    })
}

/// Атомарная запись слоя в `.gstore` с пространственной сортировкой (Z-порядок) и сжатием блоков.
pub fn write_layer(
    path: &Path,
    code: &str,
    map_name: &str,
    source_mtime: f64,
    mut records: Vec<StoredFeature>,
) -> io::Result<LayerMeta> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut global: Option<[f64; 4]> = None;
    for r in &records {
        expand_bbox(&mut global, r.bbox);
    }
    let gbox = global.unwrap_or([0.0; 4]);

    let mut small = Vec::new();
    let mut large = Vec::new();
    for r in records.drain(..) {
        if (r.bbox[2] - r.bbox[0]) <= LARGE_SPAN_DEG && (r.bbox[3] - r.bbox[1]) <= LARGE_SPAN_DEG {
            small.push(r);
        } else {
            large.push(r);
        }
    }
    small.sort_unstable_by_key(|r| morton_key(r.bbox, gbox));
    large.sort_unstable_by_key(|r| morton_key(r.bbox, gbox));

    let total_count = (small.len() + large.len()) as u64;
    let tmp_name = format!(
        "{}.{}.{:?}.part",
        path.file_name().and_then(|s| s.to_str()).unwrap_or("layer"),
        std::process::id(),
        std::thread::current().id()
    );
    let tmp = path.with_file_name(tmp_name);

    let res = (|| -> io::Result<LayerMeta> {
        let mut f = File::create(&tmp)?;
        f.write_all(&[0u8; HEADER_LEN])?;

        let mut blocks = Vec::new();
        for chunk in small.chunks(SMALL_BLOCK) {
            blocks.push(write_block(&mut f, chunk)?);
        }
        for chunk in large.chunks(LARGE_BLOCK) {
            blocks.push(write_block(&mut f, chunk)?);
        }

        let index_offset = f.stream_position()?;
        f.write_all(&(blocks.len() as u32).to_le_bytes())?;
        for b in &blocks {
            for v in b.bbox {
                f.write_all(&v.to_le_bytes())?;
            }
            f.write_all(&b.offset.to_le_bytes())?;
            f.write_all(&b.comp_len.to_le_bytes())?;
            f.write_all(&b.count.to_le_bytes())?;
        }

        let meta_offset = f.stream_position()?;
        let meta = LayerMeta {
            code: code.to_string(),
            map_name: map_name.to_string(),
            feature_count: total_count,
            bbox: global,
            source_mtime,
            built_at: now_unix(),
            format: "gstore-v1".to_string(),
        };
        let meta_bytes = serde_json::to_vec(&meta)
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
        f.write_all(&meta_bytes)?;

        f.seek(SeekFrom::Start(0))?;
        f.write_all(MAGIC)?;
        f.write_all(&total_count.to_le_bytes())?;
        f.write_all(&index_offset.to_le_bytes())?;
        f.write_all(&meta_offset.to_le_bytes())?;
        f.flush()?;
        Ok(meta)
    })();

    match res {
        Ok(meta) => {
            fs::rename(&tmp, path)?;
            Ok(meta)
        }
        Err(e) => {
            let _ = fs::remove_file(&tmp);
            Err(e)
        }
    }
}

/// Открытый индекс слоя `.gstore` с R-деревом блоков (`rstar::RTree`).
pub struct LayerIndex {
    file: File,
    pub meta: LayerMeta,
    tree: RTree<BlockMeta>,
}

fn read_u32(slice: &[u8], off: &mut usize) -> io::Result<u32> {
    if *off + 4 > slice.len() {
        return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "truncated u32"));
    }
    let v = u32::from_le_bytes(slice[*off..*off + 4].try_into().unwrap());
    *off += 4;
    Ok(v)
}

fn read_u64(slice: &[u8], off: &mut usize) -> io::Result<u64> {
    if *off + 8 > slice.len() {
        return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "truncated u64"));
    }
    let v = u64::from_le_bytes(slice[*off..*off + 8].try_into().unwrap());
    *off += 8;
    Ok(v)
}

fn read_f64(slice: &[u8], off: &mut usize) -> io::Result<f64> {
    if *off + 8 > slice.len() {
        return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "truncated f64"));
    }
    let v = f64::from_le_bytes(slice[*off..*off + 8].try_into().unwrap());
    *off += 8;
    Ok(v)
}

/// Прочитать только метаданные `.gstore` без построения R-дерева (быстрая проверка свежести).
pub fn read_meta(path: &Path) -> io::Result<LayerMeta> {
    let mut f = File::open(path)?;
    let mut hdr = [0u8; HEADER_LEN];
    f.read_exact(&mut hdr)?;
    if &hdr[0..8] != MAGIC {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "bad gstore magic"));
    }
    let meta_offset = u64::from_le_bytes(hdr[24..32].try_into().unwrap());
    f.seek(SeekFrom::Start(meta_offset))?;
    let mut mb = Vec::new();
    f.read_to_end(&mut mb)?;
    serde_json::from_slice(&mb).map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))
}

impl LayerIndex {
    pub fn open(path: &Path) -> io::Result<Self> {
        let mut f = File::open(path)?;
        let mut hdr = [0u8; HEADER_LEN];
        f.read_exact(&mut hdr)?;
        if &hdr[0..8] != MAGIC {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "bad gstore magic"));
        }
        let index_offset = u64::from_le_bytes(hdr[16..24].try_into().unwrap());
        let meta_offset = u64::from_le_bytes(hdr[24..32].try_into().unwrap());
        if meta_offset < index_offset {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "invalid offsets"));
        }

        f.seek(SeekFrom::Start(index_offset))?;
        let mut idx_buf = vec![0u8; (meta_offset - index_offset) as usize];
        f.read_exact(&mut idx_buf)?;
        let mut off = 0usize;
        let n_blocks = read_u32(&idx_buf, &mut off)? as usize;
        let mut blocks = Vec::with_capacity(n_blocks);
        for _ in 0..n_blocks {
            let b0 = read_f64(&idx_buf, &mut off)?;
            let b1 = read_f64(&idx_buf, &mut off)?;
            let b2 = read_f64(&idx_buf, &mut off)?;
            let b3 = read_f64(&idx_buf, &mut off)?;
            let offset = read_u64(&idx_buf, &mut off)?;
            let comp_len = read_u32(&idx_buf, &mut off)?;
            let count = read_u32(&idx_buf, &mut off)?;
            blocks.push(BlockMeta { bbox: [b0, b1, b2, b3], offset, comp_len, count });
        }

        let mut meta_buf = Vec::new();
        f.read_to_end(&mut meta_buf)?;
        let meta: LayerMeta = serde_json::from_slice(&meta_buf)
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
        let tree = RTree::bulk_load(blocks);
        Ok(Self { file: f, meta, tree })
    }

    fn read_block_raw(&mut self, b: &BlockMeta) -> io::Result<Vec<u8>> {
        self.file.seek(SeekFrom::Start(b.offset))?;
        let mut comp = vec![0u8; b.comp_len as usize];
        self.file.read_exact(&mut comp)?;
        let mut dec = DeflateDecoder::new(&comp[..]);
        let mut raw = Vec::with_capacity(b.comp_len as usize * 3);
        dec.read_to_end(&mut raw)?;
        Ok(raw)
    }

    /// Быстрая выборка всех объектов, чей габарит пересекается с `query = [w, s, e, n]`.
    pub fn query_bbox(&mut self, query: [f64; 4]) -> io::Result<Vec<StoredFeature>> {
        if let Some(gb) = self.meta.bbox {
            if !overlaps(gb, query) {
                return Ok(Vec::new());
            }
        } else {
            return Ok(Vec::new());
        }
        let env = AABB::from_corners([query[0], query[1]], [query[2], query[3]]);
        let mut hits: Vec<BlockMeta> = self.tree.locate_in_envelope_intersecting(&env).copied().collect();
        hits.sort_unstable_by_key(|b| b.offset);

        let mut out = Vec::new();
        for b in hits {
            let raw = self.read_block_raw(&b)?;
            let mut off = 0usize;
            for _ in 0..b.count {
                let fb = [
                    read_f64(&raw, &mut off)?,
                    read_f64(&raw, &mut off)?,
                    read_f64(&raw, &mut off)?,
                    read_f64(&raw, &mut off)?,
                ];
                let klen = read_u32(&raw, &mut off)? as usize;
                if off + klen > raw.len() {
                    return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "truncated key"));
                }
                let k_start = off;
                off += klen;
                let plen = read_u32(&raw, &mut off)? as usize;
                if off + plen > raw.len() {
                    return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "truncated payload"));
                }
                let p_start = off;
                off += plen;

                if overlaps(fb, query) {
                    let key = String::from_utf8(raw[k_start..k_start + klen].to_vec())
                        .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
                    let payload_json = String::from_utf8(raw[p_start..p_start + plen].to_vec())
                        .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
                    out.push(StoredFeature { bbox: fb, key, payload_json });
                }
            }
        }
        Ok(out)
    }

    /// Подсчёт объектов в прямоугольнике `query` (для `ogd_all.scan`).
    /// При `exact_geom == true` проверяется реальное пересечение геометрии с прямоугольником (как `clip_geometry`).
    pub fn count_bbox(&mut self, query: [f64; 4], exact_geom: bool) -> io::Result<usize> {
        if let Some(gb) = self.meta.bbox {
            if !overlaps(gb, query) {
                return Ok(0);
            }
        } else {
            return Ok(0);
        }
        let env = AABB::from_corners([query[0], query[1]], [query[2], query[3]]);
        let mut hits: Vec<BlockMeta> = self.tree.locate_in_envelope_intersecting(&env).copied().collect();
        hits.sort_unstable_by_key(|b| b.offset);

        let mut total = 0usize;
        for b in hits {
            // Быстрый путь: весь блок целиком внутри рамки запроса — можно не распаковывать.
            if contains_box(query, b.bbox) {
                total += b.count as usize;
                continue;
            }
            let raw = self.read_block_raw(&b)?;
            let mut off = 0usize;
            for _ in 0..b.count {
                let fb = [
                    read_f64(&raw, &mut off)?,
                    read_f64(&raw, &mut off)?,
                    read_f64(&raw, &mut off)?,
                    read_f64(&raw, &mut off)?,
                ];
                let klen = read_u32(&raw, &mut off)? as usize;
                off += klen;
                let plen = read_u32(&raw, &mut off)? as usize;
                let p_start = off;
                off += plen;
                if off > raw.len() {
                    return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "truncated record"));
                }
                if !overlaps(fb, query) {
                    continue;
                }
                if !exact_geom || contains_box(query, fb) {
                    total += 1;
                    continue;
                }
                if let Ok(v) = serde_json::from_slice::<serde_json::Value>(&raw[p_start..p_start + plen]) {
                    if let Some(g) = v.get("geometry") {
                        if geom_intersects_rect(g, query) {
                            total += 1;
                        }
                    }
                }
            }
        }
        Ok(total)
    }
}

/// Проверка пересечения геометрии GeoJSON с прямоугольником `[w, s, e, n]` (для быстрого `scan`).
pub fn geom_intersects_rect(geom: &serde_json::Value, rect: [f64; 4]) -> bool {
    let gtype = match geom.get("type").and_then(|v| v.as_str()) {
        Some(t) => t,
        None => return false,
    };
    let coords = match geom.get("coordinates") {
        Some(c) => c,
        None => return false,
    };
    match gtype {
        "Point" => point_xy(coords).map_or(false, |p| point_in_rect(p, rect)),
        "MultiPoint" => coords.as_array().map_or(false, |arr| {
            arr.iter().filter_map(point_xy).any(|p| point_in_rect(p, rect))
        }),
        "LineString" => line_intersects_rect(coords, rect),
        "MultiLineString" => coords.as_array().map_or(false, |arr| {
            arr.iter().any(|ln| line_intersects_rect(ln, rect))
        }),
        "Polygon" => poly_intersects_rect(coords, rect),
        "MultiPolygon" => coords.as_array().map_or(false, |arr| {
            arr.iter().any(|poly| poly_intersects_rect(poly, rect))
        }),
        _ => true,
    }
}

#[inline]
fn point_xy(v: &serde_json::Value) -> Option<(f64, f64)> {
    let a = v.as_array()?;
    if a.len() < 2 { return None; }
    Some((a[0].as_f64()?, a[1].as_f64()?))
}

#[inline]
fn point_in_rect(p: (f64, f64), r: [f64; 4]) -> bool {
    p.0 >= r[0] && p.0 <= r[2] && p.1 >= r[1] && p.1 <= r[3]
}

/// Liang-Barsky пересечение отрезка с прямоугольником.
fn seg_intersects_rect(p0: (f64, f64), p1: (f64, f64), r: [f64; 4]) -> bool {
    if point_in_rect(p0, r) || point_in_rect(p1, r) {
        return true;
    }
    let dx = p1.0 - p0.0;
    let dy = p1.1 - p0.1;
    let mut t0 = 0.0_f64;
    let mut t1 = 1.0_f64;
    for (p, q) in [
        (-dx, p0.0 - r[0]),
        (dx, r[2] - p0.0),
        (-dy, p0.1 - r[1]),
        (dy, r[3] - p0.1),
    ] {
        if p == 0.0 {
            if q < 0.0 { return false; }
        } else {
            let t = q / p;
            if p < 0.0 {
                if t > t1 { return false; }
                if t > t0 { t0 = t; }
            } else {
                if t < t0 { return false; }
                if t < t1 { t1 = t; }
            }
        }
    }
    t0 <= t1
}

fn ring_pts(v: &serde_json::Value) -> Vec<(f64, f64)> {
    v.as_array()
        .map(|a| a.iter().filter_map(point_xy).collect())
        .unwrap_or_default()
}

fn line_intersects_rect(coords: &serde_json::Value, rect: [f64; 4]) -> bool {
    let pts = ring_pts(coords);
    if pts.len() == 1 {
        return point_in_rect(pts[0], rect);
    }
    pts.windows(2).any(|w| seg_intersects_rect(w[0], w[1], rect))
}

fn point_in_ring(p: (f64, f64), ring: &[(f64, f64)]) -> bool {
    if ring.len() < 3 {
        return false;
    }
    let mut inside = false;
    let mut j = ring.len() - 1;
    for i in 0..ring.len() {
        let (xi, yi) = ring[i];
        let (xj, yj) = ring[j];
        let crosses = (yi > p.1) != (yj > p.1);
        if crosses {
            let x_int = (xj - xi) * (p.1 - yi) / (yj - yi) + xi;
            if p.0 < x_int {
                inside = !inside;
            }
        }
        j = i;
    }
    inside
}

fn poly_intersects_rect(coords: &serde_json::Value, rect: [f64; 4]) -> bool {
    let rings = match coords.as_array() {
        Some(a) if !a.is_empty() => a,
        _ => return false,
    };
    let ext = ring_pts(&rings[0]);
    if ext.len() < 3 {
        return false;
    }
    // 1. Любое ребро внешнего кольца пересекает рамку (или вершина внутри рамки)
    if ext.windows(2).any(|w| seg_intersects_rect(w[0], w[1], rect)) {
        return true;
    }
    if seg_intersects_rect(ext[ext.len() - 1], ext[0], rect) {
        return true;
    }
    // 2. Рамка целиком внутри внешнего кольца: проверяем центр и углы рамки против дыр
    let probe = (0.5 * (rect[0] + rect[2]), 0.5 * (rect[1] + rect[3]));
    if !point_in_ring(probe, &ext) {
        return false;
    }
    for hole_val in &rings[1..] {
        let hole = ring_pts(hole_val);
        if hole.len() >= 3 {
            // Если ребро дыры пересекает рамку, часть полигона всё равно попадает в рамку
            if hole.windows(2).any(|w| seg_intersects_rect(w[0], w[1], rect)) {
                return true;
            }
            if point_in_ring(probe, &hole) {
                return false;
            }
        }
    }
    true
}
