"""Диф снимков: что изменилось в источнике между выгрузками.

Сравнение по стабильному ключу объекта (grado_key) и сигнатуре
содержимого (геометрия + свойства).
"""

import hashlib
import json


def _sig(feature):
    payload = json.dumps(
        {"g": feature.get("geometry"), "p": feature.get("properties")},
        sort_keys=True, ensure_ascii=False, default=float)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def diff(features_a, features_b):
    a = {f["grado_key"]: f for f in features_a}
    b = {f["grado_key"]: f for f in features_b}
    return {
        "added": sorted(set(b) - set(a)),
        "removed": sorted(set(a) - set(b)),
        "changed": sorted(k for k in set(a) & set(b) if _sig(a[k]) != _sig(b[k])),
    }


def has_changes(d):
    return bool(d["added"] or d["removed"] or d["changed"])
