"""Документная модель альбома: документ → листы → фреймы.

Фрейм отдаёт операции отрисовки (общий байткод render), собранные из
контекста: проекта, стилей, ТЭП-движка, метаданных документа. Правка
модели инвалидирует листы через граф зависимостей ядра; в эталоне листы
собираются заново при каждом рендере.
"""

A3_LANDSCAPE = (420, 297)
A3_PORTRAIT = (297, 420)
A4_PORTRAIT = (210, 297)

# поля рамки по ГОСТ Р 21.101: слева 20 мм (подшивка), остальные 5 мм
MARGIN_LEFT, MARGIN = 20, 5


class Frame:
    def __init__(self, rect):
        self.rect = tuple(rect)

    def ops(self, ctx):
        raise NotImplementedError


class Page:
    def __init__(self, size=A3_LANDSCAPE, frames=None):
        self.size = size
        self.frames = list(frames or [])

    def inner_rect(self):
        w, h = self.size
        return (MARGIN_LEFT, MARGIN, w - MARGIN_LEFT - MARGIN, h - 2 * MARGIN)

    def ops(self, ctx):
        out = []
        for frame in self.frames:
            out.extend(frame.ops(ctx))
        return out


class Document:
    def __init__(self, title, meta=None, pages=None):
        self.title = title
        self.meta = dict(meta or {})
        self.pages = list(pages or [])
