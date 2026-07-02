"""Подключение соседних модулей ядра (до монорепо-тулинга)."""

import sys
from pathlib import Path

CORE = Path(__file__).parents[2]
for mod in ("model", "compute", "reactive"):
    p = str(CORE / mod)
    if p not in sys.path:
        sys.path.insert(0, p)

PRESET = CORE / "compute" / "grado_compute" / "presets" / "moscow_krt.json"
