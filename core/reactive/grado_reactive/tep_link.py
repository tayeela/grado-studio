"""Связка сессии с ТЭП-движком: прообраз графа зависимостей ядра.

Подписывается на изменения модели; если затронут слой с ролью ТЭП —
пересобирает входы из геометрии и отдаёт движку, который инкрементально
пересчитывает метрики. Удаление всех объектов роли даёт 0, а не «прежнее
значение» — вход всегда функция от текущей модели.
"""


class TepLink:
    def __init__(self, session, engine):
        self.project = session.project
        self.engine = engine
        session.subscribe(self._on_change)
        self.sync()

    def _roles(self):
        """{код слоя: роль} по слоям, существующим в проекте."""
        out = {}
        for info in self.project.layers():
            cls = self.project.classifier.get(info["code"])
            if cls.tep_role and cls.tep_role in self.engine.inputs:
                out[info["code"]] = cls.tep_role
        return out

    def _on_change(self, layer_codes):
        if layer_codes & set(self._roles()):
            self.sync()

    def sync(self):
        roles = self._roles()
        values = {role: 0.0 for role in roles.values()}
        for code, role in roles.items():
            values[role] += self.project.layer(code).area_ha()
        if values:
            self.engine.set_inputs(**values)
        return values
