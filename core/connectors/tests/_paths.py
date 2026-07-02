"""Подключение соседних модулей ядра (до монорепо-тулинга)."""

import sys
from pathlib import Path

CORE = Path(__file__).parents[2]
for mod in ("model", "compute", "reactive", "connectors"):
    p = str(CORE / mod)
    if p not in sys.path:
        sys.path.insert(0, p)
