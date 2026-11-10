//! Перевод старых файлов без смены номера формата — перенос `apps/grado2/web/migrate.js` один в один.
//!
//! «Потолок» → «предельная высота» (решение владельца 01.10.2026). Идемпотентно. Трогает только служебный слой
//! `cons:ceiling` (поля стиля, свойства объектов) и гнёзда узлов графа «Данные/Ограничения» и
//! «Эскиз/Посадка застройки»; одноимённые поля в слоях пользователя остаются как есть.

use serde_json::{Map, Value};

const CEIL_KEY: &str = "cons:ceiling";
const FIELDS: [(&str, &str); 2] = [
    ("Потолок, м", "Предельная высота, м"),
    ("Потолок, эт.", "Предельная высота, эт."),
];
const SOCKET_OLD: &str = "потолок";
const SOCKET_NEW: &str = "предельная высота";

fn ren(v: &mut Value) {
    if let Value::String(s) = v {
        if let Some((_, to)) = FIELDS.iter().find(|(from, _)| from == s) {
            *s = to.to_string();
        }
    }
}

fn ren_field(o: Option<&mut Value>, key: &str) {
    if let Some(Value::Object(m)) = o {
        if let Some(f) = m.get_mut(key) {
            ren(f);
        }
    }
}

fn rename_props(fc: &mut Value) {
    let Some(list) = fc.get_mut("features").and_then(|f| f.as_array_mut()) else {
        return;
    };
    for f in list {
        let Some(Value::Object(pr)) = f.get_mut("properties") else {
            continue;
        };
        if !FIELDS.iter().any(|(k, _)| pr.contains_key(*k)) {
            continue;
        }
        // порядок полей сохраняется
        let old = std::mem::take(pr);
        let mut neu = Map::new();
        for (k, v) in old {
            let k = FIELDS
                .iter()
                .find(|(from, _)| *from == k)
                .map(|(_, to)| to.to_string())
                .unwrap_or(k);
            neu.insert(k, v);
        }
        *pr = neu;
    }
}

/// Переводит проект (JSON-значение) на нынешние имена. Не объект — без изменений.
pub fn migrate(p: &mut Value) {
    let Some(root) = p.as_object_mut() else {
        return;
    };
    // стиль служебного слоя: поле подписи, раскраски, градации, правил
    if let Some(Value::Array(layers)) = root.get_mut("layers") {
        if let Some(l) = layers
            .iter_mut()
            .find(|l| l.get("key").and_then(|k| k.as_str()) == Some(CEIL_KEY))
        {
            if let Some(Value::Object(st)) = l.get_mut("style") {
                if let Some(v) = st.get_mut("label") {
                    ren(v);
                }
                ren_field(st.get_mut("cat"), "field");
                ren_field(st.get_mut("grad"), "field");
                if let Some(Value::Array(list)) =
                    st.get_mut("rules").and_then(|r| r.get_mut("list"))
                {
                    for r in list {
                        ren_field(Some(r), "field");
                    }
                }
            }
        }
    }
    // данные служебного слоя: объекты и исходная выгрузка, если она отдельный объект
    if let Some(Value::Object(d)) = root.get_mut("data").and_then(|d| d.get_mut(CEIL_KEY)) {
        if let Some(fc) = d.get_mut("fc") {
            rename_props(fc);
        }
        if let Some(orig) = d.get_mut("original") {
            if orig.is_object() {
                rename_props(orig);
            }
        }
    }
    // граф: гнёзда по имени, только в узлах программы
    if let Some(Value::Array(nodes)) = root.get_mut("graph").and_then(|g| g.get_mut("nodes")) {
        for n in nodes {
            let side = match n.get("type").and_then(|t| t.as_str()) {
                Some("Данные/Ограничения") => "outputs",
                Some("Эскиз/Посадка застройки") => "inputs",
                _ => continue,
            };
            let Some(Value::Array(socks)) = n.get_mut(side) else {
                continue;
            };
            for s in socks {
                for f in ["name", "label"] {
                    if let Some(v) = s.get_mut(f) {
                        if v == SOCKET_OLD {
                            *v = Value::String(SOCKET_NEW.into());
                        }
                    }
                }
            }
        }
    }
}
