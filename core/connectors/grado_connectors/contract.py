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


def with_acquisition(result, bbox, sublayers, *, provenance="network", data_date=None, fields_complete=True):
    """Подтверждение фактически проверенной области; не по габариту найденных объектов.

    Вызывать только после полного успешного чтения подслоя/ответа. Исходная дата
    неизвестна, если источник её не сообщил; дата кэша не выдаётся за дату данных.
    """
    import hashlib
    import json
    from datetime import datetime, timezone
    w, s, e, n = map(float, bbox)
    area = {"type":"Polygon","coordinates":[[[w,s],[e,s],[e,n],[w,n],[w,s]]]}
    checked = datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    outcome = "received" if result.get("features") else "empty"
    parts = [{"partId":str(sub)+":"+hashlib.sha256(json.dumps(bbox).encode()).hexdigest()[:16],
              "sublayer":str(sub),"area":area,"outcome":outcome,"checkedAt":checked,
              "dataDate":data_date,"provenance":provenance} for sub in sublayers]
    return {**result,"acquisition":{"checkedParts":parts,"state":outcome if fields_complete else "partial",
            "reasonCode":None if fields_complete else "partial_attributes","dataDate":data_date}}
