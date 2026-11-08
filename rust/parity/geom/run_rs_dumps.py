"""Прогон всех геометрических сценариев через Rust CLI: parity/geom/rs/py_<имя>.json.

Запуск: python3 -I run_rs_dumps.py <папка вывода> <репозиторий>
Бинарь — target/release/grado_geom_rs от корня крейта. Сценарии —
scenarios.json рядом. Структура дампов — как у CLI (crates/geom/src/main.rs).
"""

import json
import subprocess
import sys
from pathlib import Path

rsdir = Path(sys.argv[1]).resolve()
repo = Path(sys.argv[2]).resolve()
here = Path(__file__).resolve().parent
scenarios = json.loads((here / "scenarios.json").read_text("utf-8"))
bin_ = here.parent.parent / "target" / "release" / "grado_geom_rs"
if not bin_.exists():
    sys.exit(f"нет бинаря {bin_} — сначала cargo build --release -p grado_geom_rs")
rsdir.mkdir(parents=True, exist_ok=True)

count = 0
for kind, items in scenarios.items():
    for sc in items:
        # сценарий в формате CLI: имя входного файла совпадает с именем сценария
        infile = rsdir / f"in_{sc['name']}.json"
        infile.write_text(json.dumps(sc, ensure_ascii=False), "utf-8")
        out = rsdir / f"py_{sc['name']}.json"
        subprocess.run(
            [str(bin_), kind, "--input", str(infile), "--out", str(out)],
            check=True,
        )
        infile.unlink()
        count += 1
print(f"ok: {count} дампов Rust в {rsdir}")
