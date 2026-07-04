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

    def _role_layers(self):
        """[(layer_id, code, роль)] по слоям проекта с ролью-входом ТЭП."""
        out = []
        for info in self.project.layers():
            cls = self.project.classifier.get(info["code"])
            if cls.tep_role and cls.tep_role in self.engine.inputs:
                out.append((info["layer_id"], info["code"], cls.tep_role))
        return out

    def _on_change(self, layer_codes):
        # изменение слоя роли пересобирает входы (layer_codes несёт коды/id)
        role_codes = {code for _, code, _ in self._role_layers()}
        role_ids = {lid for lid, _, _ in self._role_layers()}
        if layer_codes & (role_codes | role_ids):
            self.sync()

    def sync(self):
        # суммируем площади по слоям (layer_id): несколько слоёв одной роли
        # складываются, а не берётся один
        values = {}
        for layer_id, _code, role in self._role_layers():
            values[role] = values.get(role, 0.0) \
                + self.project.layer_by_id(layer_id).area_ha()
        if values:
            self.engine.set_inputs(**values)
        return values
