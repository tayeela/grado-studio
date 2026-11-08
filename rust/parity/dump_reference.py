"""Эталонные дампы Python-движка grado_compute для сверки с Rust-портом.

Запуск: ~/.grado2/venv/bin/python dump_reference.py <репозиторий> <папка вывода>
PYTHONPATH на core/compute ставится скриптом. Дампы: results + values (repr + json) + eval_counts.
"""

import json
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
outdir = Path(sys.argv[2]).resolve()
outdir.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(repo / "core" / "compute"))

from grado_compute import Engine  # noqa: E402

PRESETS = repo / "core" / "compute" / "grado_compute" / "presets"

# Сценарии: имя, пресет, --set (значения как в CLI — всегда float), --const
YAK = [("terr_area", 15), ("restrict_area", 0), ("spp_in", 357), ("ratio_zh", 100),
       ("nonres_part", 6), ("education_zone", 1), ("k1", 0.75), ("k2", 0.2),
       ("tinao", 0), ("territory_mode", 1), ("unbuilt_share", 25)]
SCENARIOS = [
    ("calc2_defaults", "moscow_calc2.json", [], []),
    ("calc2_yakimanka", "moscow_calc2.json", YAK, []),
    ("calc2_zone2", "moscow_calc2.json", YAK[:-1] + [("education_zone", 2)], []),
    ("calc2_lowrise", "moscow_calc2.json",
     [("spp_in", 100), ("ratio_zh", 100), ("spp_low_in", 100), ("nonres_part", 6)], []),
    ("calc2_people_100", "moscow_calc2.json",
     [("spp_in", 3.3 / 0.65 / 0.94), ("ratio_zh", 100), ("nonres_part", 6)], []),
    ("calc2_people_101", "moscow_calc2.json",
     [("spp_in", 3.30033 / 0.65 / 0.94), ("ratio_zh", 100), ("nonres_part", 6)], []),
    ("calc2_const_doo50", "moscow_calc2.json", YAK, [("doo_z1", 50)]),
    ("calc2_const_plots", "moscow_calc2.json", YAK,
     [("doo_plot_m2_2", 30), ("clinic_plot_norm_ha", 0.5)]),
    ("calc2_zero", "moscow_calc2.json", [("spp_in", 0), ("education_zone", 1)], []),
    ("krt_defaults", "moscow_krt.json", [], []),
]


def dump(name, preset, sets, consts):
    e = Engine.from_file(PRESETS / preset)
    if sets:
        e.set_inputs(**{k: float(v) for k, v in sets})
    if consts:
        e.set_constants(**{k: float(v) for k, v in consts})
    values = {k: {"repr": repr(v), "json": v} for k, v in sorted(e._values.items())}
    counts = dict(sorted(e.eval_counts.items()))
    doc = {
        "title": e.title,
        "results": e.results(),
        "values": values,
        "eval_counts": counts,
    }
    (outdir / f"py_{name}.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


for name, preset, sets, consts in SCENARIOS:
    dump(name, preset, sets, consts)
(outdir / "scenarios.json").write_text(json.dumps(
    [{"name": n, "preset": p, "set": s, "const": c} for n, p, s, c in SCENARIOS],
    ensure_ascii=False, indent=1), encoding="utf-8")
print(f"ok: {len(SCENARIOS)} эталонных дампов в {outdir}")
