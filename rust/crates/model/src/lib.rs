//! Формат проекта ГРАДО `.grado2` на Rust (план 09.11.2026, шаг С1).
//!
//! Один источник правды о файле проекта для сервера (дальше — axum), браузера (WebAssembly, `crates/wasm`) и
//! интерфейса (типы TypeScript строит ts-rs: `cargo test -p grado_model export_bindings`). Сейчас файл пишут
//! `apps/grado2/ui/src/project.js` и `apps/grado2/web/project.js`; поля — как у них.
//!
//! - [`Project::parse`] / [`Project::to_json`] — чтение и запись **без потерь**: известные поля разобраны по типам,
//!   незнакомые лежат в `extra` и уходят обратно как были; «нет поля», `null` и значение различаются ([`Maybe`]).
//!   Сверка — `tests/roundtrip.rs`: файл после чтения и записи равен исходному по значению.
//! - [`check`] — проверка файла: ошибки (файл нельзя открыть как проект) и замечания (открыть можно, но что-то не так),
//!   тексты по-русски для окна программы.
//! - [`migrate`] — перевод старых файлов, перенос `apps/grado2/web/migrate.js` (без смены номера формата).

pub mod maybe;
mod migrate;

pub use maybe::Maybe;
pub use migrate::migrate;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use ts_rs::TS;

/// Формат файла, который пишет программа.
pub const FORMAT: &str = "grado2";
/// Номер формата: файл с большим номером записан более новой программой.
pub const VERSION: u64 = 2;

/// Проект целиком: так он лежит в файле `.grado2`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, TS)]
#[ts(export, export_to = "project.ts")]
pub struct Project {
    pub format: String,
    #[ts(type = "number")]
    pub version: Value,
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<String>", optional = nullable)]
    pub app: Maybe<String>,
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<String>", optional = nullable)]
    pub name: Maybe<String>,
    /// имя файла в папке проектов (без .grado2)
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<String>", optional = nullable)]
    pub file: Maybe<String>,
    /// вид карты при открытии
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<MapView>", optional = nullable)]
    pub view: Maybe<MapView>,
    /// текущий слой (ключ)
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<String>", optional = nullable)]
    pub current: Maybe<String>,
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<Vec<Group>>", optional = nullable)]
    pub groups: Maybe<Vec<Group>>,
    /// слои сверху вниз
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<Vec<Layer>>", optional = nullable)]
    pub layers: Maybe<Vec<Layer>>,
    /// данные слоёв по ключу слоя
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<std::collections::HashMap<String, LayerData>>", optional = nullable)]
    pub data: Maybe<Map<String, Value>>,
    /// виды: слои с оформлением и рамка на карте (#119)
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<Vec<View>>", optional = nullable)]
    pub views: Maybe<Vec<Value>>,
    /// граница территории: GeoJSON Feature (роль `territory` у слоя — главный путь, это поле — для старых файлов)
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<GeoJson>", optional = nullable)]
    pub territory: Maybe<Value>,
    /// альбом ППТ КРТ (движок альбома, пока на прежней странице)
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<GeoJson>", optional = nullable)]
    pub album: Maybe<Value>,
    /// схема расчёта (граф узлов)
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<GeoJson>", optional = nullable)]
    pub graph: Maybe<Value>,
    /// остальные поля файла, как были (saved_at, dirty, источники…); незнакомое не теряется
    #[serde(flatten)]
    #[ts(skip)]
    pub extra: Map<String, Value>,
    /// листы «Макета листа»; в файле последним ключом (server.py with_layouts)
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<Vec<Sheet>>", optional = nullable)]
    pub layouts: Maybe<Vec<Value>>,
}

/// Любое значение JSON (GeoJSON, стиль, лист): тип TypeScript `unknown`, разбирает интерфейс.
#[derive(TS)]
#[ts(export, export_to = "project.ts", type = "unknown")]
pub struct GeoJson;

/// Вид карты при открытии проекта.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, TS)]
#[ts(export, export_to = "project.ts")]
pub struct MapView {
    /// долгота и широта WGS84
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<[f64; 2]>", optional = nullable)]
    pub center: Maybe<Vec<f64>>,
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<f64>", optional = nullable)]
    pub zoom: Maybe<Value>,
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<String>", optional = nullable)]
    pub basemap: Maybe<String>,
    #[serde(flatten)]
    #[ts(skip)]
    pub extra: Map<String, Value>,
}

/// Группа слоёв.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, TS)]
#[ts(export, export_to = "project.ts")]
pub struct Group {
    pub id: String,
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<String>", optional = nullable)]
    pub title: Maybe<String>,
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<bool>", optional = nullable)]
    pub visible: Maybe<bool>,
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<bool>", optional = nullable)]
    pub open: Maybe<bool>,
    #[serde(flatten)]
    #[ts(skip)]
    pub extra: Map<String, Value>,
}

/// Слой проекта: что показывать и как (данные — в `Project::data` по тому же ключу).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, TS)]
#[ts(export, export_to = "project.ts")]
pub struct Layer {
    /// ключ слоя: `ogd.<код>`, `egko.buildings`, `user:territory`…; по нему и только по нему ищут слой (железное правило 5)
    pub key: String,
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<String>", optional = nullable)]
    pub title: Maybe<String>,
    /// poly, line, point
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<String>", optional = nullable)]
    pub geom: Maybe<String>,
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<bool>", optional = nullable)]
    pub visible: Maybe<bool>,
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<String>", optional = nullable)]
    pub group: Maybe<String>,
    /// роль слоя: `territory` — граница территории
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<String>", optional = nullable)]
    pub role: Maybe<String>,
    /// оформление (знак, классы по атрибутам, подпись) — разбирает symbology
    #[serde(default, skip_serializing_if = "Maybe::is_absent")]
    #[ts(as = "Option<GeoJson>", optional = nullable)]
    pub style: Maybe<Value>,
    #[serde(flatten)]
    #[ts(skip)]
    pub extra: Map<String, Value>,
}

/// Данные слоя (значение `Project::data[ключ]`).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, TS)]
#[ts(export, export_to = "project.ts")]
pub struct LayerData {
    #[ts(optional = nullable)]
    pub title: Option<String>,
    #[ts(optional = nullable)]
    pub source: Option<String>,
    #[ts(optional = nullable)]
    pub fetched_at: Option<String>,
    /// объекты: GeoJSON FeatureCollection в WGS84
    #[ts(as = "Option<GeoJson>", optional = nullable)]
    pub fc: Option<Value>,
    /// исходная выгрузка до правок, или "=fc" — не правилась
    #[ts(as = "Option<GeoJson>", optional = nullable)]
    pub original: Option<Value>,
}

/// Вид (рамка вида на карте): разбирается интерфейсом, здесь важен только id.
#[derive(TS)]
#[ts(export, export_to = "project.ts")]
pub struct View {
    pub id: String,
}

/// Лист «Макета листа»: формат, рамка, штамп, элементы.
#[derive(TS)]
#[ts(export, export_to = "project.ts")]
pub struct Sheet {
    #[ts(optional)]
    pub id: Option<String>,
    #[ts(optional)]
    pub title: Option<String>,
    #[ts(as = "Vec<GeoJson>")]
    pub blocks: Vec<Value>,
}

/// Ошибка чтения: файл не JSON или не объект проекта.
#[derive(Debug, Clone, PartialEq)]
pub struct ParseError(pub String);

impl std::fmt::Display for ParseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl Project {
    /// Читает файл проекта. Ошибка — по-русски, для окна программы.
    pub fn parse(text: &str) -> Result<Project, ParseError> {
        let v: Value = serde_json::from_str(text)
            .map_err(|e| ParseError(format!("файл проекта повреждён: {e}")))?;
        Project::from_value(v)
    }

    pub fn from_value(v: Value) -> Result<Project, ParseError> {
        if !v.is_object() {
            return Err(ParseError(
                "в файле не проект ГРАДО: нужен объект JSON".into(),
            ));
        }
        serde_json::from_value(v).map_err(|e| ParseError(format!("в файле не проект ГРАДО: {e}")))
    }

    pub fn to_value(&self) -> Value {
        serde_json::to_value(self).expect("проект всегда сериализуется")
    }

    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("проект всегда сериализуется")
    }

    pub fn layers(&self) -> &[Layer] {
        self.layers.get().map(|v| v.as_slice()).unwrap_or(&[])
    }

    pub fn groups(&self) -> &[Group] {
        self.groups.get().map(|v| v.as_slice()).unwrap_or(&[])
    }

    /// Слой по ключу (железное правило 5: по ключу, не «первый слой такого вида»).
    pub fn layer(&self, key: &str) -> Option<&Layer> {
        self.layers().iter().find(|l| l.key == key)
    }
}

/// Насколько серьёзно замечание проверки.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, TS)]
#[serde(rename_all = "lowercase")]
#[ts(export, export_to = "check.ts")]
pub enum Level {
    /// файл нельзя открыть как проект
    Error,
    /// открыть можно, но что-то не так
    Warning,
}

/// Одно замечание проверки: где и что.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "check.ts")]
pub struct Issue {
    pub level: Level,
    /// где: `layers[3]`, `data.ogd.123`, `views[0]`…
    pub path: String,
    /// что не так, по-русски
    pub text: String,
}

/// Итог проверки файла.
#[derive(Debug, Clone, PartialEq, Serialize, TS)]
#[ts(export, export_to = "check.ts")]
pub struct Report {
    /// можно открывать (ошибок нет)
    pub ok: bool,
    pub issues: Vec<Issue>,
    pub layers: usize,
    pub features: usize,
    pub views: usize,
    pub sheets: usize,
}

/// Проверяет текст файла проекта: ошибки чтения — тоже замечания, без паники.
pub fn check_text(text: &str) -> Report {
    match Project::parse(text) {
        Ok(p) => check(&p),
        Err(e) => Report {
            ok: false,
            issues: vec![issue(Level::Error, "", e.0)],
            layers: 0,
            features: 0,
            views: 0,
            sheets: 0,
        },
    }
}

fn issue(level: Level, path: impl Into<String>, text: impl Into<String>) -> Issue {
    Issue {
        level,
        path: path.into(),
        text: text.into(),
    }
}

const GEOMS: [&str; 3] = ["poly", "line", "point"];

/// Проверяет проект: формат, ключи слоёв, группы, данные, виды, листы, граница.
pub fn check(p: &Project) -> Report {
    use Level::*;
    let mut out = Vec::new();
    if p.format != FORMAT {
        out.push(issue(
            Error,
            "format",
            format!("формат «{}», а нужен «{FORMAT}»", p.format),
        ));
    }
    match p.version.as_u64() {
        Some(v) if v > VERSION => out.push(issue(
            Error,
            "version",
            format!("файл записан более новой программой (формат {v}, эта программа знает до {VERSION}): обновите ГРАДО"),
        )),
        Some(_) => {}
        None => out.push(issue(Error, "version", "номер формата должен быть целым числом")),
    }

    let groups: Vec<&str> = p.groups().iter().map(|g| g.id.as_str()).collect();
    for (i, g) in p.groups().iter().enumerate() {
        if g.id.is_empty() {
            out.push(issue(Error, format!("groups[{i}]"), "у группы нет id"));
        } else if groups[..i].contains(&g.id.as_str()) {
            out.push(issue(
                Error,
                format!("groups[{i}]"),
                format!("группа «{}» повторяется", g.id),
            ));
        }
    }

    let mut keys: Vec<&str> = Vec::new();
    let mut territory = Vec::new();
    for (i, l) in p.layers().iter().enumerate() {
        let at = format!("layers[{i}]");
        if l.key.is_empty() {
            out.push(issue(Error, &at, "у слоя нет ключа"));
            continue;
        }
        if keys.contains(&l.key.as_str()) {
            out.push(issue(
                Error,
                &at,
                format!("слой «{}» повторяется: ключ слоя должен быть один", l.key),
            ));
        }
        keys.push(&l.key);
        if let Maybe::Some(g) = &l.group {
            if !groups.contains(&g.as_str()) {
                out.push(issue(
                    Warning,
                    &at,
                    format!(
                        "слой «{}» в группе «{g}», которой нет: покажется вне групп",
                        l.key
                    ),
                ));
            }
        }
        if let Maybe::Some(g) = &l.geom {
            if !GEOMS.contains(&g.as_str()) {
                out.push(issue(
                    Warning,
                    &at,
                    format!(
                        "у слоя «{}» вид геометрии «{g}», а бывает poly, line, point",
                        l.key
                    ),
                ));
            }
        }
        if l.role.get().map(|r| r == "territory").unwrap_or(false) {
            territory.push(l.key.clone());
        }
        if let Maybe::Some(s) = &l.style {
            if !s.is_object() {
                out.push(issue(
                    Warning,
                    &at,
                    format!(
                        "оформление слоя «{}» не объект: слой покажется оформлением по умолчанию",
                        l.key
                    ),
                ));
            }
        }
    }
    if territory.len() > 1 {
        out.push(issue(
            Error,
            "layers",
            format!(
                "роль «граница территории» у нескольких слоёв: {}",
                territory.join(", ")
            ),
        ));
    }
    if let Maybe::Some(c) = &p.current {
        if !keys.is_empty() && !keys.contains(&c.as_str()) {
            out.push(issue(
                Warning,
                "current",
                format!("текущий слой «{c}» не найден: станет текущим первый"),
            ));
        }
    }

    let mut features = 0usize;
    if let Maybe::Some(data) = &p.data {
        for (k, d) in data {
            let at = format!("data.{k}");
            let Some(obj) = d.as_object() else {
                out.push(issue(Error, &at, "данные слоя не объект"));
                continue;
            };
            if !keys.contains(&k.as_str()) {
                out.push(issue(
                    Warning,
                    &at,
                    format!("данные «{k}» без слоя: в «Слоях» их не видно"),
                ));
            }
            for f in ["fc", "original"] {
                match obj.get(f) {
                    None | Some(Value::Null) => {}
                    Some(Value::String(s)) if f == "original" && s == "=fc" => {}
                    Some(fc) => match fc.get("features").and_then(|x| x.as_array()) {
                        Some(list)
                            if fc.get("type").and_then(|t| t.as_str())
                                == Some("FeatureCollection") =>
                        {
                            if f == "fc" {
                                features += list.len();
                            }
                        }
                        _ => out.push(issue(
                            Error,
                            format!("{at}.{f}"),
                            "объекты слоя не FeatureCollection",
                        )),
                    },
                }
            }
        }
    }

    let mut views = 0usize;
    if let Maybe::Some(list) = &p.views {
        let mut ids: Vec<String> = Vec::new();
        for (i, v) in list.iter().enumerate() {
            views += 1;
            match v.get("id").and_then(|x| x.as_str()) {
                None | Some("") => out.push(issue(Error, format!("views[{i}]"), "у вида нет id")),
                Some(id) if ids.iter().any(|x| x == id) => out.push(issue(
                    Error,
                    format!("views[{i}]"),
                    format!("вид «{id}» повторяется"),
                )),
                Some(id) => ids.push(id.to_string()),
            }
        }
    }

    let mut sheets = 0usize;
    if let Maybe::Some(list) = &p.layouts {
        for (i, s) in list.iter().enumerate() {
            sheets += 1;
            if s.get("blocks").and_then(|b| b.as_array()).is_none() {
                out.push(issue(
                    Error,
                    format!("layouts[{i}]"),
                    "у листа нет списка элементов",
                ));
            }
        }
    }

    if let Maybe::Some(t) = &p.territory {
        let ty = t.pointer("/geometry/type").and_then(|x| x.as_str());
        if !matches!(ty, Some("Polygon") | Some("MultiPolygon")) {
            out.push(issue(
                Warning,
                "territory",
                "граница территории не полигон: её не будет на карте",
            ));
        }
    }

    Report {
        ok: !out.iter().any(|i| i.level == Error),
        issues: out,
        layers: keys.len(),
        features,
        views,
        sheets,
    }
}
