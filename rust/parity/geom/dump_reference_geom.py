"""Эталонные дампы Python-эталона grado_geom для сверки с Rust-портом.

Запуск: ~/.grado2/venv/bin/python dump_reference_geom.py <репозиторий> <папка вывода>
PYTHONPATH на core/geom ставится скриптом. Сценарии — parity/geom/scenarios.json.
Структура дампов совпадает с CLI крейта grado_geom_rs (crates/geom/src/main.rs).
"""

import json
import math
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
outdir = Path(sys.argv[2]).resolve()
outdir.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(repo / "core" / "geom"))

from grado_geom import (  # noqa: E402
    Arc,
    Coverage,
    Path as GPath,
    Snapper,
    curve_spec,
    tessellate_curve,
    union_intersection_area,
)

scenarios = json.loads((Path(__file__).resolve().parent / "scenarios.json").read_text("utf-8"))


def dump_overlay(sc):
    regions = [[[(p[0], p[1]) for p in ring] for ring in poly] for poly in sc["regions"]]
    clips = [[[(p[0], p[1]) for p in ring] for ring in poly] for poly in sc["clips"]]
    return {"area": union_intersection_area(regions, clips)}


def dump_snap(sc):
    s = Snapper(tolerance=sc["tolerance"])
    for seg in sc["segments"]:
        s.add_segment(tuple(seg[0]), tuple(seg[1]))
    results = []
    for q in sc["queries"]:
        r = s.snap(q[0], q[1])
        results.append(None if r is None else {"kind": r.kind, "point": list(r.point), "dist": r.dist})
    return {"results": results}


def dump_coverage(sc):
    polygons = {fid: [(p[0], p[1]) for p in ring] for fid, ring in sc["polygons"]}
    try:
        cov = Coverage.from_polygons(polygons)
    except Exception:
        return {"error": "CoverageError"}
    edit_error = False
    if sc.get("edit_ends_mismatch"):
        eid = cov.shared_edges()[0]
        try:
            cov.edit_edge(eid, [(10, 1), (10, 9)])
        except Exception:
            edit_error = True  # как CLI Rust: ошибка правки помечается, дамп продолжается
    if sc.get("bump_shared_edge") is not None:
        eid = cov.shared_edges()[0]
        e = cov.edges[eid]
        p0, p1 = e["pts"][0], e["pts"][-1]
        my = (p0[1] + p1[1]) / 2
        cov.edit_edge(eid, [p0, (sc["bump_shared_edge"], my), p1])
    edges = {
        str(eid): {"pts": [list(p) for p in e["pts"]], "left": e["left"], "right": e["right"]}
        for eid, e in cov.edges.items()
    }
    faces = {fid: [[eid, fwd] for eid, fwd in fe] for fid, fe in cov.faces.items()}
    areas = {fid: a for fid, a in cov.areas().items()}
    try:
        cov.validate(sc["tol"])
        validate = {"ok": True}
    except Exception:
        validate = {"error": "CoverageError"}
    try:
        outer = [list(p) for p in cov.outer_ring()]
    except Exception:
        outer = None
    return {
        "edges": edges,
        "faces": faces,
        "areas": areas,
        "shared": cov.shared_edges(),
        "validate": validate,
        "outer": outer,
        "edit_error": edit_error,
    }


def dump_path(sc):
    vertices = [tuple(p) for p in sc["vertices"]]
    try:
        if sc["fillet"]:
            p = GPath.fillet_polyline(vertices, sc["radius"])
        else:
            p = GPath.polyline(vertices, closed=sc["closed"])
    except Exception:
        return {"error": "PathError"}
    tol = sc["tol"]
    lin = p.linearize(tol)
    dump = {"length": p.length(), "area": p.area(tol), "g1": p.is_g1(),
            "linearize_n": len(lin), "linearize_first": list(lin[0]), "linearize_last": list(lin[-1])}
    if sc["stations"] is not None:
        try:
            dump["stations"] = [[s, list(pt)] for s, pt in p.stations(sc["stations"])]
        except Exception:
            dump["stations"] = {"error": "PathError"}
    if sc["offset"] is not None:
        try:
            off = p.offset(sc["offset"])
            dump["offset_length"] = off.length()
            dump["offset_area"] = off.area(tol)
            dump["offset_g1"] = off.is_g1()
        except Exception:
            dump["offset"] = {"error": "PathError"}
    return dump


def dump_arc(sc):
    try:
        if "p0" in sc:
            arc = Arc.from_3pts(tuple(sc["p0"]), tuple(sc["pm"]), tuple(sc["p1"]))
        else:
            arc = Arc(sc["cx"], sc["cy"], sc["r"], sc["a0"], sc["sweep"])
    except Exception:
        return {"error": "CurveError"}
    tol = sc["tol"]
    lin = arc.linearize(tol)
    dump = {
        "cx": arc.cx, "cy": arc.cy, "r": arc.r, "a0": arc.a0, "sweep": arc.sweep,
        "length": arc.length(), "start": list(arc.start), "end": list(arc.end),
        "linearize_n": len(lin), "linearize_first": list(lin[0]), "linearize_last": list(lin[-1]),
    }
    if "t_samples" in sc:
        dump["points_at_t"] = [list(arc.point_at(t)) for t in sc["t_samples"]]
        dump["tangents_at_t"] = [arc.tangent_at(t) for t in sc["t_samples"]]
    if "s_samples" in sc:
        dump["points_at_s"] = [list(arc.point_at_length(s)) for s in sc["s_samples"]]
    if sc.get("offset") is not None:
        try:
            dump["offset_r"] = arc.offset(sc["offset"]).r
        except Exception:
            dump["offset"] = {"error": "CurveError"}
    return dump


def dump_tessellate(sc):
    try:
        spec = curve_spec(sc["spec"])
        pts = tessellate_curve(spec, sc["tol"])
    except Exception:
        return {"error": "CurveError"}
    return {"n": len(pts), "first": list(pts[0]), "last": list(pts[-1]), "closed": pts[0] == pts[-1]}


DUMPERS = {
    "overlay": dump_overlay,
    "snap": dump_snap,
    "coverage": dump_coverage,
    "path": dump_path,
    "arc": dump_arc,
    "tessellate": dump_tessellate,
}

count = 0
for kind, items in scenarios.items():
    for sc in items:
        dump = DUMPERS[kind](sc)
        (outdir / f"py_{sc['name']}.json").write_text(json.dumps(dump, ensure_ascii=False, indent=1), "utf-8")
        count += 1
print(f"ok: {count} дампов Python-эталона в {outdir}")
