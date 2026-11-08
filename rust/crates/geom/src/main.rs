//! CLI крейта grado_geom_rs: дампы результатов для сверки с Python-эталоном
//! (parity/geom) и быстрая прикидка в руках.
//!
//! Команды: overlay, snap, coverage, path, arc — JSON на входе (--input)
//! и JSON-дамп на выходе (--out).

use std::path::PathBuf;

use serde_json::{json, Map, Value};

use grado_geom_rs::curves::{tessellate_curve, Arc};
use grado_geom_rs::{coverage, overlay, path, snap, Pt};

fn load(p: &PathBuf) -> Value {
    let text = std::fs::read_to_string(p).expect("файл сценария");
    serde_json::from_str(&text).expect("JSON сценария")
}

fn pt_of(v: &Value) -> Pt {
    let arr = v.as_array().expect("точка — пара координат");
    (
        arr[0].as_f64().expect("число"),
        arr[1].as_f64().expect("число"),
    )
}

fn pts_of(v: &Value) -> Vec<Pt> {
    v.as_array().expect("кольцо").iter().map(pt_of).collect()
}

fn json_pt(p: Pt) -> Value {
    json!([p.0, p.1])
}

fn write_out(out: &PathBuf, value: Value) {
    std::fs::write(out, serde_json::to_string_pretty(&value).unwrap()).expect("запись дампа");
}

fn cmd_overlay(input: &Value) -> Value {
    let regions: Vec<Vec<Vec<Pt>>> = input["regions"]
        .as_array()
        .expect("regions")
        .iter()
        .map(|poly| poly.as_array().unwrap().iter().map(pts_of).collect())
        .collect();
    let clips: Vec<Vec<Vec<Pt>>> = input["clips"]
        .as_array()
        .expect("clips")
        .iter()
        .map(|poly| poly.as_array().unwrap().iter().map(pts_of).collect())
        .collect();
    json!({ "area": overlay::union_intersection_area(&regions, &clips) })
}

fn cmd_snap(input: &Value) -> Value {
    let mut s = snap::Snapper::new(
        input["tolerance"].as_f64().unwrap_or(0.5),
    );
    for seg in input["segments"].as_array().expect("segments") {
        let pts = pts_of(seg);
        s.add_segment(pts[0], pts[1]);
    }
    let mut results = Vec::new();
    for q in input["queries"].as_array().expect("queries") {
        let (x, y) = pt_of(q);
        results.push(match s.snap(x, y) {
            None => Value::Null,
            Some(r) => json!({
                "kind": r.kind.as_str(),
                "point": json_pt(r.point),
                "dist": r.dist,
            }),
        });
    }
    json!({ "results": results })
}

fn cmd_coverage(input: &Value) -> Value {
    let polygons: Vec<(String, Vec<Pt>)> = input["polygons"]
        .as_array()
        .expect("polygons")
        .iter()
        .map(|pair| {
            (
                pair[0].as_str().expect("fid").to_string(),
                pts_of(&pair[1]),
            )
        })
        .collect();
    let cov = match coverage::Coverage::from_polygons(&polygons) {
        Err(_) => return json!({ "error": "CoverageError" }),
        Ok(c) => c,
    };
    let mut cov = cov;
    let mut edit_error = false;
    if input["edit_ends_mismatch"].as_bool().unwrap_or(false) {
        // правка с несовпадающими концами — как в тесте edit_edge_nodes_fixed
        let eid = cov.shared_edges()[0];
        let pts = [(10.0, 1.0), (10.0, 9.0)];
        if cov.edit_edge(eid, &pts).is_err() {
            edit_error = true;
        }
    }
    if let Some(bump_x) = input["bump_shared_edge"].as_f64() {
        // выгиб первого общего ребра: узлы неподвижны, середина сдвигается
        let eid = cov.shared_edges()[0];
        let pts = &cov.edges[&eid].pts;
        let (p0, p1) = (pts[0], pts[pts.len() - 1]);
        let my = (p0.1 + p1.1) / 2.0;
        cov.edit_edge(eid, &[p0, (bump_x, my), p1])
            .expect("выгиб общего ребра");
    }
    for edit in input["edits"].as_array().unwrap_or(&Vec::new()) {
        let eid = edit[0].as_u64().expect("eid");
        let pts = pts_of(&edit[1]);
        if cov.edit_edge(eid, &pts).is_err() {
            edit_error = true;
        }
    }
    let mut edges = Map::new();
    for (eid, e) in &cov.edges {
        edges.insert(
            eid.to_string(),
            json!({
                "pts": e.pts.iter().map(|&p| json_pt(p)).collect::<Vec<_>>(),
                "left": e.left,
                "right": e.right,
            }),
        );
    }
    let mut faces = Map::new();
    let mut areas = Map::new();
    for (fid, face_edges) in &cov.faces {
        faces.insert(
            fid.clone(),
            json!(face_edges
                .iter()
                .map(|(eid, fwd)| json!([eid, fwd]))
                .collect::<Vec<_>>()),
        );
    }
    for (fid, a) in cov.areas() {
        areas.insert(fid, json!(a));
    }
    let validate = match cov.validate(input["tol"].as_f64().unwrap_or(1e-6)) {
        Ok(true) => json!({ "ok": true }),
        Ok(false) => json!({ "ok": false }),
        Err(_) => json!({ "error": "CoverageError" }),
    };
    let outer = match cov.outer_ring() {
        Ok(ring) => json!(ring.iter().map(|&p| json_pt(p)).collect::<Vec<_>>()),
        Err(_) => Value::Null,
    };
    json!({
        "edges": edges,
        "faces": faces,
        "areas": areas,
        "shared": cov.shared_edges(),
        "validate": validate,
        "outer": outer,
        "edit_error": edit_error,
    })
}

fn cmd_path(input: &Value) -> Value {
    let vertices = pts_of(&input["vertices"]);
    let radius = input["radius"].as_f64().unwrap_or(0.0);
    let closed = input["closed"].as_bool().unwrap_or(false);
    let tol = input["tol"].as_f64().unwrap_or(0.01);
    let built = if input["fillet"].as_bool().unwrap_or(false) {
        path::Path::fillet_polyline(&vertices, radius)
    } else {
        path::Path::polyline(&vertices, closed)
    };
    let p = match built {
        Err(_) => return json!({ "error": "PathError" }),
        Ok(p) => p,
    };
    let mut dump = Map::new();
    dump.insert("length".into(), json!(p.length()));
    dump.insert("area".into(), json!(p.area(tol)));
    dump.insert("g1".into(), json!(p.is_g1(1e-6)));
    let lin = p.linearize(tol);
    dump.insert("linearize_n".into(), json!(lin.len()));
    dump.insert("linearize_first".into(), json_pt(lin[0]));
    dump.insert("linearize_last".into(), json_pt(lin[lin.len() - 1]));
    match input["stations"].as_f64() {
        Some(step) => match p.stations(step) {
            Ok(sts) => {
                dump.insert(
                    "stations".into(),
                    json!(sts
                        .iter()
                        .map(|(s, pt)| json!([s, json_pt(*pt)]))
                        .collect::<Vec<_>>()),
                );
            }
            Err(_) => {
                dump.insert("stations".into(), json!({ "error": "PathError" }));
            }
        },
        None => {}
    }
    match input["offset"].as_f64() {
        Some(d) => match p.offset(d) {
            Ok(off) => {
                dump.insert("offset_length".into(), json!(off.length()));
                dump.insert("offset_area".into(), json!(off.area(tol)));
                dump.insert("offset_g1".into(), json!(off.is_g1(1e-6)));
            }
            Err(_) => {
                dump.insert("offset".into(), json!({ "error": "PathError" }));
            }
        },
        None => {}
    }
    Value::Object(dump)
}

fn cmd_arc(input: &Value) -> Value {
    let arc = match input.get("p0") {
        // по трём точкам
        Some(_) => Arc::from_3pts(
            pt_of(&input["p0"]),
            pt_of(&input["pm"]),
            pt_of(&input["p1"]),
        ),
        None => Arc::new(
            input["cx"].as_f64().expect("cx"),
            input["cy"].as_f64().expect("cy"),
            input["r"].as_f64().expect("r"),
            input["a0"].as_f64().expect("a0"),
            input["sweep"].as_f64().expect("sweep"),
        ),
    };
    let arc = match arc {
        Err(_) => return json!({ "error": "CurveError" }),
        Ok(a) => a,
    };
    let tol = input["tol"].as_f64().unwrap_or(0.01);
    let mut dump = Map::new();
    dump.insert("cx".into(), json!(arc.cx));
    dump.insert("cy".into(), json!(arc.cy));
    dump.insert("r".into(), json!(arc.r));
    dump.insert("a0".into(), json!(arc.a0));
    dump.insert("sweep".into(), json!(arc.sweep));
    dump.insert("length".into(), json!(arc.length()));
    dump.insert("start".into(), json_pt(arc.start()));
    dump.insert("end".into(), json_pt(arc.end()));
    let lin = arc.linearize(tol);
    dump.insert("linearize_n".into(), json!(lin.len()));
    dump.insert("linearize_first".into(), json_pt(lin[0]));
    dump.insert("linearize_last".into(), json_pt(lin[lin.len() - 1]));
    if let Some(ts) = input["t_samples"].as_array() {
        let mut pts = Vec::new();
        let mut tang = Vec::new();
        for t in ts {
            let t = t.as_f64().expect("t");
            pts.push(json_pt(arc.point_at(t)));
            tang.push(json!(arc.tangent_at(t)));
        }
        dump.insert("points_at_t".into(), json!(pts));
        dump.insert("tangents_at_t".into(), json!(tang));
    }
    if let Some(ss) = input["s_samples"].as_array() {
        let mut pts = Vec::new();
        for s in ss {
            pts.push(json_pt(arc.point_at_length(s.as_f64().expect("s"))));
        }
        dump.insert("points_at_s".into(), json!(pts));
    }
    if let Some(d) = input["offset"].as_f64() {
        match arc.offset(d) {
            Ok(off) => dump.insert("offset_r".into(), json!(off.r)),
            Err(_) => dump.insert("offset".into(), json!({ "error": "CurveError" })),
        };
    }
    Value::Object(dump)
}

fn cmd_tessellate(input: &Value) -> Value {
    match tessellate_curve(&input["spec"], input["tol"].as_f64().unwrap_or(0.05)) {
        Err(_) => json!({ "error": "CurveError" }),
        Ok(pts) => json!({
            "n": pts.len(),
            "first": json_pt(pts[0]),
            "last": json_pt(pts[pts.len() - 1]),
            "closed": pts[0] == pts[pts.len() - 1],
        }),
    }
}

fn main() {
    let mut args = std::env::args().skip(1);
    let cmd = args.next().expect("команда: overlay|snap|coverage|path|arc|tessellate");
    let mut input_path = PathBuf::new();
    let mut out_path = PathBuf::new();
    while let Some(a) = args.next() {
        match a.as_str() {
            "--input" => input_path = PathBuf::from(args.next().expect("путь")),
            "--out" => out_path = PathBuf::from(args.next().expect("путь")),
            other => panic!("неизвестный аргумент {other}"),
        }
    }
    if out_path.as_os_str().is_empty() {
        panic!("нужен --out <файл>");
    }
    let input = load(&input_path);
    let dump = match cmd.as_str() {
        "overlay" => cmd_overlay(&input),
        "snap" => cmd_snap(&input),
        "coverage" => cmd_coverage(&input),
        "path" => cmd_path(&input),
        "arc" => cmd_arc(&input),
        "tessellate" => cmd_tessellate(&input),
        other => panic!("неизвестная команда {other}"),
    };
    write_out(&out_path, dump);
}
