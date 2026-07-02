"""Импорт снимка в проект: снимок → слой .grado через журнал.

Конвейер архитектуры: снимок (WGS84) → трансформация в СК проекта →
загрузка с провенансом. Импорт идёт через Session.bulk — одна запись
журнала, один undo на весь снимок; каждый объект получает source,
source_date (дата выгрузки) и source_doc (реквизиты) из манифеста.
"""

from . import crs


def _coerce(value, expected):
    if value is None:
        return None
    if expected == "string":
        return value if isinstance(value, str) else str(value)
    if expected == "integer":
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if expected == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def import_snapshot(store, sid, project, session, layer_code,
                    attr_map=None, transform=crs.wgs84_to_utm37n):
    """Импортирует снимок в слой проекта. Возвращает число объектов."""
    manifest, features = store.load(sid)
    store.verify(sid)

    codes = [info["code"] for info in project.layers()]
    layer = project.layer(layer_code) if layer_code in codes \
        else project.add_layer(layer_code)
    cls = project.classifier.get(layer_code)
    attr_types = {a["id"]: a["type"] for a in cls.attrs}
    # по умолчанию — свойства с именами атрибутов классификатора
    attr_map = attr_map or {aid: aid for aid in attr_types}

    count = 0
    with session.bulk(f"импорт {manifest['connector']}: {sid} "
                      f"({manifest['count']} объектов)"):
        for f in features:
            if not f.get("geometry"):
                continue
            geom = crs.transform_geom(f["geometry"], transform)
            props = f.get("properties") or {}
            attrs = {}
            for aid, prop in attr_map.items():
                if aid in attr_types and prop in props:
                    v = _coerce(props[prop], attr_types[aid])
                    if v is not None:
                        attrs[aid] = v
            session.insert_feature(
                layer_code, geom, attrs=attrs,
                source=manifest["source"],
                source_date=manifest["fetched_at"][:10],
                source_doc=manifest.get("source_doc") or sid,
                title=f"импорт {f.get('grado_key')}")
            count += 1
    return count
