"""grado_geom — геометрическое ядро «ГРАДО Студии» (эталонная реализация).

Дуги (параметрически, линеаризация по допуску), составные пути с пикетажем,
сопряжениями и офсетами, движок привязок, топологическое покрытие зон.
"""

from .affine import mirror, rotate, scale
from .coverage import Coverage, CoverageError
from .curves import Arc, CurveError, curve_spec, tessellate_curve
from .overlay import union_intersection_area
from .path import Path, PathError
from .snap import Snapper, SnapResult

__all__ = ["union_intersection_area", "Arc", "Path", "Snapper", "SnapResult", "Coverage",
           "CurveError", "PathError", "CoverageError",
           "curve_spec", "tessellate_curve", "rotate", "scale", "mirror"]
__version__ = "0.1.0"
