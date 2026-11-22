//! Крейт `grado_store` (план 09.11.2026, шаг С3): дисковое хранилище слоёв с пространственным индексом `rstar`,
//! вырезкой по рамке, плитками карты XYZ и журналом свежести ночной выгрузки (`ogd_warm.py`).

pub mod format;
pub mod freshness;
pub mod ingest;
pub mod store;

pub use format::{overlaps, read_meta, write_layer, LayerIndex, LayerMeta, StoredFeature};
pub use freshness::{
    freshness_report, is_late, layer_age_secs, read_warm_status, stale_codes, write_warm_status,
    LayerFreshness, PortalWarmStats, WarmStatus, REFRESH_SECS, UNTIL_UTC_HOUR,
};
pub use ingest::{build_from_grid_dir, build_from_lines_gz};
pub use store::{check_code, tile_bbox, LayerStore};

#[cfg(test)]
mod tests {
    use super::*;
    use flate2::write::GzEncoder;
    use flate2::Compression;
    use std::fs::{self, File};
    use std::io::Write;
    use std::path::PathBuf;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static SEQ: AtomicUsize = AtomicUsize::new(0);

    fn tmp_dir(tag: &str) -> PathBuf {
        let id = SEQ.fetch_add(1, Ordering::Relaxed);
        let p = std::env::temp_dir().join(format!("grado_store_test_{tag}_{}_{id}", std::process::id()));
        let _ = fs::remove_dir_all(&p);
        fs::create_dir_all(&p).unwrap();
        p
    }

    fn make_poly_record(i: usize, x: f64, y: f64, size: f64) -> StoredFeature {
        let x2 = x + size;
        let y2 = y + size;
        let payload = format!(
            r#"{{"geometry":{{"type":"Polygon","coordinates":[[[{x},{y}],[{x2},{y}],[{x2},{y2}],[{x},{y2}],[{x},{y}]]]}},"properties":{{"id":{i},"name":"объект {i}"}}}}"#
        );
        StoredFeature {
            bbox: [x, y, x2, y2],
            key: format!("l1:{i}"),
            payload_json: payload,
        }
    }

    #[test]
    fn roundtrip_and_bbox_query_match_linear() {
        let dir = tmp_dir("rt");
        let path = dir.join("l1.gstore");
        let mut recs = Vec::new();
        for ix in 0..25 {
            for iy in 0..25 {
                let x = 37.3 + ix as f64 * 0.02;
                let y = 55.5 + iy as f64 * 0.02;
                recs.push(make_poly_record(ix * 25 + iy, x, y, 0.01));
            }
        }
        // Добавим крупный полигон (больше LARGE_SPAN_DEG), перекрывающий половину карты
        recs.push(make_poly_record(9999, 37.35, 55.55, 0.25));

        let meta = write_layer(&path, "l1", "isogd", 1700000000.0, recs.clone()).unwrap();
        assert_eq!(meta.feature_count, 626);
        assert!(meta.bbox.is_some());

        let query = [37.45, 55.65, 37.50, 55.70];
        let mut expected: Vec<String> = recs
            .iter()
            .filter(|r| overlaps(r.bbox, query))
            .map(|r| r.key.clone())
            .collect();
        expected.sort();

        let mut idx = LayerIndex::open(&path).unwrap();
        let got = idx.query_bbox(query).unwrap();
        let mut got_keys: Vec<String> = got.iter().map(|r| r.key.clone()).collect();
        got_keys.sort();
        assert_eq!(got_keys, expected);

        let exact_cnt = idx.count_bbox(query, true).unwrap();
        assert_eq!(exact_cnt, expected.len());

        // Запрос вне области слоя — 0 объектов
        assert_eq!(idx.query_bbox([10.0, 10.0, 11.0, 11.0]).unwrap().len(), 0);
        assert_eq!(idx.count_bbox([10.0, 10.0, 11.0, 11.0], true).unwrap(), 0);

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn ingest_lines2_gz_and_scan_and_tile() {
        let dir = tmp_dir("lines2");
        let gz = dir.join("zouit.shp.gz");
        let lp = dir.join("zouit.shp.lines2.gz");
        fs::write(&gz, b"dummy").unwrap();
        {
            let f = File::create(&lp).unwrap();
            let mut enc = GzEncoder::new(f, Compression::fast());
            let r1 = make_poly_record(1, 37.52, 55.79, 0.005);
            let r2 = make_poly_record(2, 37.80, 55.90, 0.005);
            for r in [&r1, &r2] {
                writeln!(
                    enc,
                    "{},{},{},{}\t{}\t{}",
                    r.bbox[0], r.bbox[1], r.bbox[2], r.bbox[3], r.key, r.payload_json
                )
                .unwrap();
            }
            enc.finish().unwrap();
        }

        let store = LayerStore::new(&dir, "isogd");
        let got = store.query("zouit", [37.51, 55.78, 37.54, 55.80], Some(3600.0)).unwrap().unwrap();
        assert_eq!(got.len(), 1);
        assert_eq!(got[0].key, "l1:1");
        assert!(dir.join("zouit.gstore").exists());

        let counts = store.scan(
            &["zouit".to_string(), "missing_layer".to_string()],
            [37.51, 55.78, 37.54, 55.80],
            Some(3600.0),
            true,
        );
        assert_eq!(counts.get("zouit"), Some(&Some(1)));
        assert_eq!(counts.get("missing_layer"), Some(&None));

        // Плитка XYZ над Ходынским полем (z=12: x=2475, y=1281 — проверим через tile_bbox)
        let tb = tile_bbox(12, 2475, 1281, 0.0);
        assert!(tb[0] < tb[2] && tb[1] < tb[3]);
        let fc_json = store.tile_geojson("zouit", 0, 0, 0, Some(3600.0), 0.0).unwrap().unwrap();
        let v: serde_json::Value = serde_json::from_str(&fc_json).unwrap();
        assert_eq!(v["type"], "FeatureCollection");
        assert_eq!(v["features"].as_array().unwrap().len(), 2);

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn ingest_egko_grid_dir() {
        let dir = tmp_dir("egko");
        let gdir = dir.join("base2.buildings.shp.grid");
        fs::create_dir_all(&gdir).unwrap();
        fs::write(gdir.join("_meta.json"), r#"{"code":"buildings","map":"base2","count":2}"#).unwrap();
        // Проверим склеенные gzip-члены, как в _stream_build ЕГКО
        {
            let mut f = File::create(gdir.join("3752_5579.lines.gz")).unwrap();
            for i in 1..=2 {
                let r = make_poly_record(i, 37.52 + i as f64 * 0.001, 55.79, 0.0005);
                let mut enc = GzEncoder::new(Vec::new(), Compression::fast());
                writeln!(
                    enc,
                    "{},{},{},{}\t{}\t{}",
                    r.bbox[0], r.bbox[1], r.bbox[2], r.bbox[3], r.key, r.payload_json
                )
                .unwrap();
                let bytes = enc.finish().unwrap();
                f.write_all(&bytes).unwrap();
            }
        }
        let store = LayerStore::new(&dir, "base2");
        let got = store.query("buildings", [37.51, 55.78, 37.54, 55.80], Some(3600.0)).unwrap().unwrap();
        assert_eq!(got.len(), 2);
        assert!(dir.join("base2.buildings.gstore").exists());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn freshness_stale_order_and_late_hours() {
        let dir = tmp_dir("fresh");
        fs::write(dir.join("fresh1.shp.gz"), b"x").unwrap();
        fs::write(dir.join("fresh1.shp.lines2.gz"), b"x").unwrap();
        let now = freshness::now_unix();
        let codes = vec!["fresh1".to_string(), "missing1".to_string(), "missing2".to_string()];
        let todo = stale_codes(&dir, "isogd", &codes, REFRESH_SECS, now);
        assert_eq!(todo, vec!["missing1".to_string(), "missing2".to_string()]);

        assert!(!is_late(3));
        assert!(is_late(4));
        assert!(is_late(11));
        assert!(!is_late(12));

        let st = WarmStatus {
            started: "2026-11-20T00:30:00+00:00".to_string(),
            gisogd: PortalWarmStats { layers: 10, fresh: 7, got: 2, err: 1, left: 0 },
            egko: Some(PortalWarmStats { layers: 5, fresh: 5, got: 0, err: 0, left: 0 }),
            seconds: 42,
        };
        write_warm_status(&dir, &st).unwrap();
        assert_eq!(read_warm_status(&dir).unwrap(), Some(st));
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn check_code_rejects_traversal() {
        assert!(check_code("virtual1742").is_ok());
        assert!(check_code("l18").is_ok());
        assert!(check_code("../etc").is_err());
        assert!(check_code(".hidden").is_err());
        assert!(check_code("a/b").is_err());
        assert!(check_code("").is_err());
    }
}
