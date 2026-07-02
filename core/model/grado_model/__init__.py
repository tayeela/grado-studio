"""grado_model — проектная БД «ГРАДО Студии» (эталонная реализация).

Файл проекта .grado = GeoPackage (открывается QGIS/GDAL) + расширенные
таблицы grado_*: метаданные, реестр слоёв с привязкой к классификатору.
Провенанс обязателен на каждом объекте.
"""

from .classifier import Classifier, ClassifierError
from .geometry import GeometryError
from .project import Layer, Project, ProjectError

__all__ = ["Project", "Layer", "Classifier",
           "ProjectError", "ClassifierError", "GeometryError"]
__version__ = "0.1.0"
