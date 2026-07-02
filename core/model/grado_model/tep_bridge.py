"""Мост модель → ТЭП-движок.

Классификатор помечает слои ролями (tep_role). Мост собирает по проекту
значения входных параметров ТЭП из геометрии: площадь слоёв роли в га.
Прообраз графа зависимостей ядра: ТЭП — функция от модели, не ручной ввод.
"""


def collect_inputs(project):
    """Возвращает {tep_role: площадь в га} по слоям проекта с ролями."""
    inputs = {}
    for info in project.layers():
        cls = project.classifier.get(info["code"])
        if not cls.tep_role:
            continue
        layer = project.layer(info["code"])
        inputs[cls.tep_role] = inputs.get(cls.tep_role, 0.0) + layer.area_ha()
    return inputs


def apply_to_engine(project, engine):
    """Подставляет собранные из геометрии входы в движок; возвращает их."""
    inputs = {k: v for k, v in collect_inputs(project).items() if k in engine.inputs}
    if inputs:
        engine.set_inputs(**inputs)
    return inputs
