"""grado_geom — геометрическое ядро «ГРАДО Студии» (эталонная реализация).

Дуги (параметрически, линеаризация по допуску), составные пути с пикетажем,
сопряжениями и офсетами, движок привязок, топологическое покрытие зон.
"""

from .coverage import Coverage, CoverageError
from .curves import Arc, CurveError
from .path import Path, PathError
from .snap import Snapper, SnapResult

__all__ = ["Arc", "Path", "Snapper", "SnapResult", "Coverage",
           "CurveError", "PathError", "CoverageError"]
__version__ = "0.1.0"
