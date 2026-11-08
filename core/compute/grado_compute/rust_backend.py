"""ТЭП-движок на Rust (модуль grado_rs, rust/crates/py) с API как у engine.Engine.

Стратегия «удушающей змеи»: Python-версия (engine.py) остаётся эталоном и движком по умолчанию;
Rust включается переменной GRADO_COMPUTE=rust, если модуль grado_rs установлен
(сборка: maturin build --release -m rust/crates/py/Cargo.toml). Сверка обоих движков —
core/compute/tests/test_rust_backend.py и rust/parity/.
"""

import json
from pathlib import Path

import grado_rs

from .engine import Metric, PresetError
from .expressions import ExpressionError


def _call(fn, *args, **kwargs):
    """Ошибки Rust → те же классы, что бросает Python-версия."""
    try:
        return fn(*args, **kwargs)
    except grado_rs.ExpressionError as e:
        raise ExpressionError(str(e)) from None


class RustEngine:
    def __init__(self, preset):
        self.preset = preset
        self.title = preset.get("title", "")
        self.inputs = {i["id"]: i for i in preset.get("inputs", [])}
        self.constants = dict(preset.get("constants", {}))
        self._metrics = None
        try:
            self._rs = grado_rs.ComputeEngine(json.dumps(preset, ensure_ascii=False))
        except grado_rs.ExpressionError as e:
            raise ExpressionError(str(e)) from None
        except ValueError as e:
            raise PresetError(str(e)) from None

    @classmethod
    def from_file(cls, path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @property
    def metrics(self):
        if self._metrics is None:   # описания метрик нужны редко — разбираем по требованию
            self._metrics = {s["id"]: Metric(s) for s in self.preset.get("metrics", [])}
        return self._metrics

    @property
    def eval_counts(self):
        return self._rs.eval_counts()

    @property
    def _values(self):
        return self._rs.raw_values()

    def set_input(self, input_id, value):
        _call(self._rs.set_input, input_id, value)

    def set_inputs(self, **kwargs):
        _call(self._rs.set_inputs, **kwargs)

    def set_constants(self, **kwargs):
        _call(self._rs.set_constants, **kwargs)

    def value(self, name):
        return self._rs.value(name)

    def display(self, name):
        return _call(self._rs.display, name)

    def results(self):
        return self._rs.results()
