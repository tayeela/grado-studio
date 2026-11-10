//! Чтение и запись без потерь, проверка и перевод старых файлов.
//! Образцы: проект нового интерфейса из тестов ГРАДО 2, полный образец со всеми разделами,
//! перевод «потолок» → «предельная высота» против эталона `apps/grado2/web/migrate.js` (tests/data/migrate_*.json
//! записаны тем же migrate.js под node).

use grado_model::{check, check_text, migrate, Level, Maybe, Project};
use serde_json::Value;

fn read(path: &str) -> String {
    std::fs::read_to_string(path).unwrap_or_else(|e| panic!("{path}: {e}"))
}

fn same_after_write(text: &str) {
    let want: Value = serde_json::from_str(text).unwrap();
    let p = Project::parse(text).unwrap();
    let got: Value = serde_json::from_str(&p.to_json()).unwrap();
    assert_eq!(got, want, "файл изменился после чтения и записи");
    // и второй круг тот же
    assert_eq!(Project::parse(&p.to_json()).unwrap(), p);
}

const NEXT_UI: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../../apps/grado2/tests/fixtures/next_ui_project.grado2"
);
const FULL: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/data/full.grado2");

#[test]
fn next_ui_fixture_round_trip() {
    let t = read(NEXT_UI);
    same_after_write(&t);
    let r = check_text(&t);
    assert!(r.ok, "{:?}", r.issues);
    assert_eq!(r.layers, 7);
}

#[test]
fn full_sample_round_trip() {
    let t = read(FULL);
    same_after_write(&t);
    let p = Project::parse(&t).unwrap();
    assert_eq!(
        p.file,
        Maybe::Null,
        "file: null держится как null, не пропадает"
    );
    assert_eq!(
        p.layer("user:territory")
            .unwrap()
            .role
            .get()
            .map(|s| s.as_str()),
        Some("territory")
    );
    assert_eq!(
        p.extra.get("saved_at").and_then(|v| v.as_str()),
        Some("2026-11-09T20:00:00.000Z")
    );
    // числа как в файле: 0.1… с 34 цифрами читается в ближайшее f64 и пишется кратчайшей записью — значение то же
    let s = p.data.get().unwrap()["ogd.11.02.04.03"]["fc"]["features"][0]["properties"]["S"]
        .as_f64()
        .unwrap();
    assert_eq!(s.to_bits(), 0.1f64.to_bits());
    let r = check(&p);
    assert!(r.ok, "{:?}", r.issues);
    assert_eq!((r.layers, r.features, r.views, r.sheets), (2, 2, 1, 1));
}

#[test]
fn key_order_kept_and_layouts_last() {
    let p = Project::parse(&read(FULL)).unwrap();
    let out = p.to_json();
    let keys: Vec<String> = serde_json::from_str::<serde_json::Map<String, Value>>(&out)
        .unwrap()
        .keys()
        .cloned()
        .collect();
    assert_eq!(
        keys.last().map(|s| s.as_str()),
        Some("layouts"),
        "листы — последним ключом (server.py with_layouts)"
    );
    assert!(out.starts_with("{\"format\":\"grado2\""));
}

#[test]
fn check_finds_problems() {
    let bad = r#"{"format":"grado2","version":3,"groups":[{"id":"g"},{"id":"g"}],
      "layers":[{"key":"a","group":"нет","geom":"poly3"},{"key":"a"},{"key":""},{"key":"t1","role":"territory"},{"key":"t2","role":"territory"}],
      "current":"x","data":{"a":{"fc":{"type":"Feature"}},"сирота":{"fc":{"type":"FeatureCollection","features":[]}}},
      "views":[{"id":"v"},{"id":"v"},{}],"layouts":[{"title":"без элементов"}],
      "territory":{"type":"Feature","geometry":{"type":"Point","coordinates":[0,0]}}}"#;
    let r = check_text(bad);
    assert!(!r.ok);
    let texts: Vec<String> = r
        .issues
        .iter()
        .map(|i| format!("{:?} {} {}", i.level, i.path, i.text))
        .collect();
    let has = |s: &str| texts.iter().any(|t| t.contains(s));
    for s in [
        "более новой программой",
        "группа «g» повторяется",
        "в группе «нет»",
        "poly3",
        "слой «a» повторяется",
        "у слоя нет ключа",
        "у нескольких слоёв: t1, t2",
        "текущий слой «x»",
        "не FeatureCollection",
        "«сирота» без слоя",
        "вид «v» повторяется",
        "у вида нет id",
        "нет списка элементов",
        "не полигон",
    ] {
        assert!(has(s), "нет замечания «{s}»: {texts:#?}");
    }
    assert!(r.issues.iter().any(|i| i.level == Level::Warning));
}

#[test]
fn parse_errors_are_russian() {
    assert!(check_text("не json").issues[0]
        .text
        .starts_with("файл проекта повреждён"));
    assert!(check_text("[1,2]").issues[0]
        .text
        .contains("нужен объект JSON"));
    assert!(!check_text(r#"{"version":2}"#).ok, "без format — не проект");
}

#[test]
fn migrate_same_as_js() {
    let dir = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/data/");
    let mut p: Value = serde_json::from_str(&read(&format!("{dir}migrate_in.json"))).unwrap();
    let want: Value = serde_json::from_str(&read(&format!("{dir}migrate_out.json"))).unwrap();
    migrate(&mut p);
    assert_eq!(p, want, "перевод отличается от web/migrate.js");
    // порядок полей объекта сохранён
    let keys: Vec<&String> = p["data"]["cons:ceiling"]["fc"]["features"][0]["properties"]
        .as_object()
        .unwrap()
        .keys()
        .collect();
    assert_eq!(
        keys,
        [
            "_uid",
            "Предельная высота, м",
            "Предельная высота, эт.",
            "По ПЗЗ, м",
            "Почему"
        ]
    );
    // второй прогон ничего не меняет
    let once = p.clone();
    migrate(&mut p);
    assert_eq!(p, once);
    let mut small: Value = serde_json::json!({"format": "grado2", "version": 2});
    migrate(&mut small);
    assert_eq!(small, serde_json::json!({"format": "grado2", "version": 2}));
}
