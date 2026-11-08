"""Сверка Rust-дампов с Python-эталонами бит-в-бит.

Сравнение: results (порядок и все поля, значения — по repr-строке), values (repr),
eval_counts. Числа сравниваются по repr, чтобы отличить 3 от 3.0, как в Python.
"""

import json
import sys
from pathlib import Path

pydir, rsdir = Path(sys.argv[1]), Path(sys.argv[2])


def rows_equal(a, b, path):
    if len(a) != len(b):
        return [f"{path}: строк {len(a)} против {len(b)}"]
    bad = []
    for i, (x, y) in enumerate(zip(a, b)):
        for key in ("id", "title", "unit", "group", "value", "precision", "note"):
            xv, yv = x.get(key), y.get(key)
            if key == "value":
                # значение сравниваем по repr: int 3 и float 3.0 — разные результаты
                xs, ys = py_repr_of(xv), py_repr_of(yv)
                if xs != ys:
                    bad.append(f"{path}[{i}].value: {xs} против {ys}")
            elif xv != yv:
                bad.append(f"{path}[{i}].{key}: {xv!r} против {yv!r}")
    return bad


def py_repr_of(v):
    # repr в том же виде, что писали дампы: у Rust value уже строка repr в values,
    # но в results — json-значение; для сравнения приводим оба к паре (тип, текст)
    if isinstance(v, bool):
        return ("bool", repr(v))
    if isinstance(v, int):
        return ("int", str(v))
    if isinstance(v, float):
        return ("float", repr(v))
    return ("other", repr(v))


bad = []
py_files = sorted(pydir.glob("py_*.json"))
for pf in py_files:
    name = pf.stem[len("py_"):]
    rf = rsdir / f"rs_{name}.json"
    if not rf.exists():
        bad.append(f"{name}: нет Rust-дампа")
        continue
    p = json.loads(pf.read_text("utf-8"))
    r = json.loads(rf.read_text("utf-8"))
    if p["title"] != r["title"]:
        bad.append(f"{name}: заголовок пресета разный")
    bad += rows_equal(p["results"], r["results"], f"{name}.results")
    if set(p["values"]) != set(r["values"]):
        only_py = set(p["values"]) - set(r["values"])
        only_rs = set(r["values"]) - set(p["values"])
        bad.append(f"{name}: имена значений расходятся: только py {sorted(only_py)}, только rs {sorted(only_rs)}")
    for k in sorted(set(p["values"]) & set(r["values"])):
        pv, rv = p["values"][k], r["values"][k]
        if pv["repr"] != rv["repr"]:
            bad.append(f"{name}.values.{k}: {pv['repr']} против {rv['repr']}")
    if p["eval_counts"] != r["eval_counts"]:
        diff = {k: (p["eval_counts"].get(k), r["eval_counts"].get(k))
                for k in set(p["eval_counts"]) | set(r["eval_counts"])
                if p["eval_counts"].get(k) != r["eval_counts"].get(k)}
        bad.append(f"{name}: eval_counts расходятся: {diff}")

print(f"сценариев: {len(py_files)}")
if bad:
    print(f"РАСХОЖДЕНИЙ: {len(bad)}")
    for line in bad[:40]:
        print(" ", line)
    sys.exit(1)
print("СВЕРКА СХОДИТСЯ: результаты, все сырые значения (repr) и счётчики пересчётов идентичны Python-версии")
