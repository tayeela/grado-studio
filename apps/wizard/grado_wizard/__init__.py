"""grado_wizard — мастер территории: граница → проект → ТЭП → альбом АГК."""

from .wizard import TerritoryWizard  # noqa: F401  (первым: настраивает пути ядра)
from .territory import build_project, demo_boundary, ring_area_ha  # noqa: F401,E402

__all__ = ["TerritoryWizard", "build_project", "demo_boundary", "ring_area_ha"]
__version__ = "0.1.0"
