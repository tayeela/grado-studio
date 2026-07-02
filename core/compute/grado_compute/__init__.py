"""grado_compute — эталонная реализация ТЭП-движка «ГРАДО Студии».

Метрики описываются данными (JSON-пресет), движок строит граф зависимостей
и пересчитывает инкрементально. Позже переносится в C++ ядро (core/compute),
эта реализация остаётся спецификацией поведения и основой Python SDK.
"""

from .engine import Engine, PresetError
from .expressions import ExpressionError

__all__ = ["Engine", "PresetError", "ExpressionError"]
__version__ = "0.1.0"
