"""Контракт коннектора (архитектура, п. «Сервис данных»).

Коннектор возвращает нормализованный результат:
    {"features": [Feature + "grado_key"], "params": {...},
     "source_doc": реквизиты | None, "crs": "EPSG:4326", "notes": [...]}

Инварианты: геометрия всегда WGS84 (проекция в СК проекта — на импорте);
grado_key — стабильный ключ объекта в источнике (для diff между снимками);
fetch не пишет ничего, кроме результата, — снимки сохраняет SnapshotStore.
"""


class ConnectorError(RuntimeError):
    pass


class Connector:
    name = None    # идентификатор коннектора (nspd/fgistp/gisogd)
    source = None  # код источника для провенанса модели

    def discover(self, **params):
        """Каталог доступного (файлы в папке захвата, документы реестра...)."""
        return []

    def fetch(self, **params):
        raise NotImplementedError


def make_result(features, params, source_doc=None, notes=None):
    return {"features": features, "params": params,
            "source_doc": source_doc, "crs": "EPSG:4326", "notes": notes or []}
