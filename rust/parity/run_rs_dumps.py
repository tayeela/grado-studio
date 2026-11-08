"""Прогон всех сценариев через Rust-движок: parity/rs_<имя>.json (та же структура дампа)."""

import json
import subprocess
import sys
from pathlib import Path

rsdir = Path(sys.argv[1]).resolve()
repo = Path(sys.argv[2]).resolve()
scenarios = json.loads((Path(sys.argv[3]).resolve() / "scenarios.json").read_text("utf-8"))
bin_ = Path(__file__).resolve().parent.parent / "target" / "release" / "grado_compute_rs"
rsdir.mkdir(parents=True, exist_ok=True)

for sc in scenarios:
    args = [str(bin_), "dump", "--preset", str(repo / "core" / "compute" / "grado_compute" / "presets" / sc["preset"]), "--out", str(rsdir / f"rs_{sc['name']}.json")]
    for k, v in sc["set"]:
        args += ["--set", f"{k}={v}"]
    for k, v in sc["const"]:
        args += ["--const", f"{k}={v}"]
    subprocess.run(args, check=True)
print(f"ok: {len(scenarios)} дампов Rust в {rsdir}")
