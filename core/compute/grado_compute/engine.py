"""ТЭП-движок: декларативные метрики над входными параметрами.

Метрика = данные (id, выражение, единица), а не код. Движок строит граф
зависимостей из выражений, вычисляет метрики в топологическом порядке и
при изменении входа пересчитывает только затронутую часть графа —
эталон реактивной модели ядра (см. docs/architecture.md, п. 5 и 8).
"""

import json
from pathlib import Path

from . import expressions


class PresetError(ValueError):
    pass


class Metric:
    def __init__(self, spec):
        self.id = spec["id"]
        self.title = spec.get("title", self.id)
        self.unit = spec.get("unit", "")
        self.expr = spec["expr"]
        self.precision = spec.get("precision")
        self.group = spec.get("group", "")
        self.hidden = spec.get("hidden", False)
        self.tree = expressions.parse(self.expr)
        self.deps = expressions.names(self.tree)


class Engine:
    def __init__(self, preset):
        self.preset = preset
        self.title = preset.get("title", "")
        self.inputs = {i["id"]: i for i in preset.get("inputs", [])}
        self.constants = dict(preset.get("constants", {}))
        self.metrics = {}
        for spec in preset.get("metrics", []):
            m = Metric(spec)
            if m.id in self.metrics or m.id in self.inputs or m.id in self.constants:
                raise PresetError(f"дублирующийся идентификатор {m.id!r}")
            self.metrics[m.id] = m

        known = set(self.inputs) | set(self.constants) | set(self.metrics)
        for m in self.metrics.values():
            unknown = m.deps - known
            if unknown:
                raise PresetError(f"метрика {m.id!r} ссылается на неизвестные имена {sorted(unknown)}")

        self._order = self._topo_sort()
        self._downstream = self._build_downstream()
        self.eval_counts = {mid: 0 for mid in self.metrics}

        self._values = dict(self.constants)
        for i in self.inputs.values():
            self._values[i["id"]] = i.get("default", 0)
        self._recompute(self._order)

    @classmethod
    def from_file(cls, path):
        preset = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(preset)

    def _topo_sort(self):
        indeg = {}
        dependents = {mid: [] for mid in self.metrics}
        for m in self.metrics.values():
            metric_deps = [d for d in m.deps if d in self.metrics]
            indeg[m.id] = len(metric_deps)
            for d in metric_deps:
                dependents[d].append(m.id)
        queue = sorted(mid for mid, d in indeg.items() if d == 0)
        order = []
        while queue:
            mid = queue.pop(0)
            order.append(mid)
            for dep in dependents[mid]:
                indeg[dep] -= 1
                if indeg[dep] == 0:
                    queue.append(dep)
        if len(order) != len(self.metrics):
            cycle = sorted(set(self.metrics) - set(order))
            raise PresetError(f"цикл в зависимостях метрик: {cycle}")
        return order

    def _build_downstream(self):
        down = {name: set() for name in
                set(self.inputs) | set(self.constants) | set(self.metrics)}
        for m in self.metrics.values():
            for d in m.deps:
                down[d].add(m.id)
        return down

    def _dirty_set(self, source):
        dirty, queue = set(), [source]
        while queue:
            for mid in self._downstream[queue.pop()]:
                if mid not in dirty:
                    dirty.add(mid)
                    queue.append(mid)
        return dirty

    def _recompute(self, metric_ids):
        for mid in self._order:
            if mid in metric_ids:
                m = self.metrics[mid]
                self._values[mid] = expressions.evaluate(m.tree, self._values)
                self.eval_counts[mid] += 1

    def set_input(self, input_id, value):
        if input_id not in self.inputs:
            raise KeyError(f"нет входного параметра {input_id!r}")
        self._values[input_id] = value
        self._recompute(self._dirty_set(input_id))

    def set_inputs(self, **kwargs):
        unknown = [k for k in kwargs if k not in self.inputs]
        if unknown:   # проверяем до записи: ошибка не оставляет полуизменённое состояние
            raise KeyError(f"нет входного параметра {unknown[0]!r}")
        dirty = set()
        for input_id, value in kwargs.items():
            self._values[input_id] = value
            dirty |= self._dirty_set(input_id)
        self._recompute(dirty)

    def value(self, name):
        return self._values[name]

    def display(self, name):
        v = self._values[name]
        m = self.metrics.get(name)
        if m is not None and m.precision is not None:
            v = expressions.round_half_up(v, m.precision)
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return v

    def results(self):
        out = []
        for mid in self._order:
            m = self.metrics[mid]
            if m.hidden:
                continue
            out.append({"id": m.id, "title": m.title, "unit": m.unit,
                        "group": m.group, "value": self.display(mid), "precision": m.precision})
        return out
