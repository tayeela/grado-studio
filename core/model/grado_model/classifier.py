"""Классификатор: реестр видов объектов.

Каждый слой проекта привязан к коду классификатора, который определяет тип
геометрии, схему атрибутов и роль в ТЭП. Классификатор — данные (JSON),
а не код; базовый пресет — presets/classifier_base.json.
"""

import json
from pathlib import Path

from .geometry import WKB_TYPES

DEFAULT_PRESET = Path(__file__).parent / "presets" / "classifier_base.json"

ATTR_TYPES = {"string", "integer", "number"}


class ClassifierError(ValueError):
    pass


class ClassifierClass:
    def __init__(self, spec):
        self.code = spec["code"]
        self.title = spec.get("title", self.code)
        self.group = spec.get("group", "")
        self.geom_type = spec["geom_type"]
        self.tep_role = spec.get("tep_role")
        self.topology = spec.get("topology")  # "coverage" — слой-покрытие
        self.stage = spec.get("stage")        # "existing" | "project" | "base"
        self.code_433pr = spec.get("code_433pr")
        self.attrs = spec.get("attrs", [])
        if self.geom_type not in WKB_TYPES:
            raise ClassifierError(f"{self.code}: неподдерживаемый тип геометрии {self.geom_type!r}")
        for a in self.attrs:
            if a.get("type") not in ATTR_TYPES:
                raise ClassifierError(f"{self.code}: недопустимый тип атрибута {a.get('type')!r}")

    def validate_attrs(self, attrs):
        known = {a["id"]: a["type"] for a in self.attrs}
        for key, value in attrs.items():
            if key not in known:
                raise ClassifierError(f"{self.code}: неизвестный атрибут {key!r}")
            if value is None:
                continue
            expected = known[key]
            ok = (expected == "string" and isinstance(value, str)) or \
                 (expected == "integer" and isinstance(value, int) and not isinstance(value, bool)) or \
                 (expected == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
            if not ok:
                raise ClassifierError(
                    f"{self.code}: атрибут {key!r} должен быть типа {expected}, получено {value!r}")


class Classifier:
    def __init__(self, preset):
        self.id = preset.get("id", "")
        self.title = preset.get("title", "")
        self.classes = {}
        for spec in preset.get("classes", []):
            c = ClassifierClass(spec)
            if c.code in self.classes:
                raise ClassifierError(f"дублирующийся код {c.code!r}")
            self.classes[c.code] = c

    @classmethod
    def load(cls, path=DEFAULT_PRESET):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def get(self, code):
        if code not in self.classes:
            raise ClassifierError(f"нет кода {code!r} в классификаторе")
        return self.classes[code]

    def codes(self):
        return list(self.classes)
