"""Пишет эталон координат для сверки Rust (rust/crates/crs/tests/parity.rs) с Python бит-в-бит.

Берёт core/connectors/grado_connectors/crs.py как есть; точки — по Москве и Новой Москве с запасом, случайные
с постоянным зерном, плюс краевые. Вызов: python3 rust/parity/crs/dump_reference.py [выход.json]
(по умолчанию rust/parity/crs/reference.json). CI пересобирает файл и сверяет с репозиторием (rust.yml).
"""

import importlib.util
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# crs.py без пакета: пакет тянет сетевые зависимости, а координатам нужна только math
_spec = importlib.util.spec_from_file_location("crs", ROOT / "core/connectors/grado_connectors/crs.py")
crs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(crs)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("reference.json")
    rnd = random.Random(20261109)
    cases = []

    def add(name, a, b):
        fn = math.hypot if name == "hypot" else getattr(crs, name)
        r = fn(a, b)
        r = (r, 0.0) if name == "hypot" else r
        cases.append({"fn": name, "in": [a, b], "out": [r[0], r[1]]})

    lonlat = [(37.6176, 55.7558), (37.5, 55.66666666667), (36.8, 55.1), (37.97, 56.02)]
    lonlat += [(rnd.uniform(36.8, 38.0), rnd.uniform(55.1, 56.05)) for _ in range(300)]
    for lon, lat in lonlat:
        for name in ("wgs84_to_merc", "wgs84_to_utm37n", "wgs84_to_msk50", "wgs84_to_msk"):
            add(name, lon, lat)
    msk = [(0.0, 0.0), (-30000.0, -60000.0), (40000.0, 45000.0)]
    msk += [(rnd.uniform(-45000, 45000), rnd.uniform(-65000, 45000)) for _ in range(300)]
    for x, y in msk:
        for name in ("msk_to_wgs84", "msk50_to_wgs84", "ogd_to_msk"):
            add(name, x, y)
    for lon, lat in lonlat[:150]:
        mx, my = crs.wgs84_to_merc(lon, lat)
        add("merc_to_wgs84", mx, my)
        add("merc_to_utm37n", mx, my)
        ux, uy = crs.wgs84_to_utm37n(lon, lat)
        add("utm37n_to_wgs84", ux, uy)
    for _ in range(300):
        add("hypot", rnd.uniform(-1e7, 1e7), rnd.uniform(-1e7, 1e7))
    for a, b in ((3.0, 4.0), (1e-300, 1e-300), (5e-324, 0.0), (1e308, 1e308), (2.0, 2.0 ** -40)):
        add("hypot", a, b)
    out.write_text(json.dumps(cases, indent=0) + "\n", "utf-8")
    print(f"crs: {len(cases)} случаев → {out}")


if __name__ == "__main__":
    main()
