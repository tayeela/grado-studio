"""Сверка дампов Python-эталона и Rust-порта (parity/geom).

Запуск: python3 -I compare.py <папка py> <папка rs> [rel_tol] [abs_tol]
Плавающие сравниваются с допуском (по умолчанию 1e-9 относительный,
1e-12 абсолютный): hypot у CPython свой, GEOS-операции заменены
собственным планарным движком — бит-в-бит, в отличие от крейта compute,
здесь не ожидается. Структура должна совпадать точно.
"""

import json
import sys
from pathlib import Path

pydir = Path(sys.argv[1]).resolve()
rsdir = Path(sys.argv[2]).resolve()
rel_tol = float(sys.argv[3]) if len(sys.argv) > 3 else 1e-9
abs_tol = float(sys.argv[4]) if len(sys.argv) > 4 else 1e-12


class Mismatch(Exception):
    pass


worst = {"path": "", "rel": 0.0}


def walk(a, b, path):
    if isinstance(a, bool) or isinstance(b, bool):
        if a is not b:
            raise Mismatch(f"{path}: {a!r} != {b!r}")
        return
    if a is None or b is None:
        if a is not b:
            raise Mismatch(f"{path}: {a!r} != {b!r}")
        return
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        af, bf = float(a), float(b)
        if af == bf:
            return
        diff = abs(af - bf)
        rel = diff / max(abs(af), abs(bf), 1e-300)
        if diff > abs_tol and rel > rel_tol:
            raise Mismatch(f"{path}: {af!r} != {bf!r} (rel {rel:.3e})")
        if rel > worst["rel"] and rel < 1.0:
            worst["rel"] = rel
            worst["path"] = path
        return
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            raise Mismatch(f"{path}: ключи {sorted(set(a) ^ set(b))}")
        for k in a:
            walk(a[k], b[k], f"{path}.{k}")
        return
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            raise Mismatch(f"{path}: длины {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]")
        return
    if a != b:
        raise Mismatch(f"{path}: {a!r} != {b!r}")


py_files = sorted(pydir.glob("py_*.json"))
rs_files = sorted(rsdir.glob("py_*.json"))
if [f.name for f in py_files] != [f.name for f in rs_files]:
    sys.exit("наборы дампов не совпадают")

failed = 0
for pf, rf in zip(py_files, rs_files):
    a = json.loads(pf.read_text("utf-8"))
    b = json.loads(rf.read_text("utf-8"))
    try:
        walk(a, b, pf.name)
        print(f"  {pf.name}: сходится")
    except Mismatch as e:
        failed += 1
        print(f"  {pf.name}: РАСХОЖДЕНИЕ — {e}")

if failed:
    print(f"\nСВЕРКА НЕ СХОДИТСЯ: {failed} из {len(py_files)}")
    sys.exit(1)
print(
    f"\nСВЕРКА СХОДИТСЯ: {len(py_files)} сценариев, "
    f"допуск rel {rel_tol:g} / abs {abs_tol:g}, "
    f"максимальное относительное расхождение {worst['rel']:.3e} ({worst['path']})"
)
