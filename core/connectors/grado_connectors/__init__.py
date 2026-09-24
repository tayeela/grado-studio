"""grado_connectors — сервис данных «ГРАДО Студии» (эталонная реализация).

Контракт коннектора: discover → fetch → снимок в SnapshotStore → diff →
импорт в проект через журнал. Форматы НСПД/ФГИС ТП/ГИС ОГД сняты с
работающего GRADO-моста (QGIS-плагин + браузерное расширение v2).
"""

from .contract import Connector, ConnectorError
from .diff import diff, has_changes
from .fgistp import FgistpConnector
from .gisogd import GisogdZip
from .gisogd_api import GISOGD_API_LAYERS, GisogdApi
from .importer import import_snapshot
from .nspd import NSPD_CATEGORIES, NspdCapture, NspdDirect
from .osm import OSM_SETS, OsmOverpass
from .store import SnapshotStore, StoreError, Subscriptions
from .terrain import TerrainContours
from .yandex_vmap import YandexVmap

__all__ = ["Connector", "ConnectorError", "FgistpConnector", "GisogdZip",
           "GISOGD_API_LAYERS", "GisogdApi",
           "NSPD_CATEGORIES", "NspdCapture", "NspdDirect",
           "OSM_SETS", "OsmOverpass", "TerrainContours", "YandexVmap",
           "SnapshotStore", "StoreError", "Subscriptions",
           "diff", "has_changes", "import_snapshot"]
__version__ = "0.1.0"
