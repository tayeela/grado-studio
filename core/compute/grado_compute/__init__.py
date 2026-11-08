"""grado_compute — эталонная реализация ТЭП-движка «ГРАДО Студии».

Метрики описываются данными (JSON-пресет), движок строит граф зависимостей
и пересчитывает инкрементально. Python-версия — спецификация поведения и движок
по умолчанию; Rust-порт (rust/crates/compute, модуль grado_rs) включается
переменной окружения GRADO_COMPUTE=rust, если модуль установлен.
"""

import logging
import os

from .engine import Engine as PyEngine
from .engine import PresetError
from .expressions import ExpressionError

BACKEND = "python"
Engine = PyEngine
if os.environ.get("GRADO_COMPUTE", "").strip().lower() == "rust":
    try:
        from .rust_backend import RustEngine as Engine  # noqa: F811
        BACKEND = "rust"
    except ImportError:   # колесо grado_rs не установлено — работаем на эталоне
        logging.getLogger("grado.compute").warning("GRADO_COMPUTE=rust, но модуль grado_rs не установлен — ТЭП считает Python-версия")

__all__ = ["Engine", "PyEngine", "PresetError", "ExpressionError", "BACKEND"]
__version__ = "0.1.0"
