"""Дельта — атомарное изменение одного объекта модели.

Формат (JSON-сериализуемый):
    {"op": "insert"|"update"|"delete", "layer": код, "fid": id,
     "before": снимок | None, "after": снимок | None}

Снимок объекта: {"geom", "attrs", "source", "source_date", "source_doc",
"style_id", "grado_key", "curve"}. Дельта обратима: invert() меняет местами
before/after — этого достаточно для undo, переключения веток и синхронизации.
"""

_INVERT_OP = {"insert": "delete", "delete": "insert", "update": "update"}


def snapshot(feature):
    """Снимок объекта из формата Layer.features()."""
    return {
        "geom": feature["geom"],
        "attrs": dict(feature["attrs"]),
        "source": feature["source"],
        "source_date": feature["source_date"],
        "source_doc": feature["source_doc"],
        "style_id": feature.get("style_id"),  # per-object стиль переживает undo/redo
        "grado_key": feature.get("grado_key"),
        "curve": feature.get("curve"),
    }


def invert(delta):
    return {
        "op": _INVERT_OP[delta["op"]],
        "layer": delta["layer"],
        "fid": delta["fid"],
        "before": delta["after"],
        "after": delta["before"],
    }


def apply(project, delta):
    """Применяет дельту к модели (реплей: undo/redo/переключение веток)."""
    layer = project.layer(delta["layer"])
    fid = delta["fid"]
    if delta["op"] == "delete":
        layer.delete_feature(fid)
    else:
        layer.set_feature(fid, delta["after"])


def affected_layers(deltas):
    return {d["layer"] for d in deltas}
