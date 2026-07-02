"""grado_layout — альбом «ГРАДО Студии» (эталонная реализация).

Документ → листы → фреймы (рамка ГОСТ, карта, легенда, таблица, текст,
основная надпись). Карто-фреймы и таблицы ТЭП собираются из модели —
альбом обновляется вместе с проектом.
"""

from .compose import (document_pages_ops, render_document_pdf,
                      render_page_svg)
from .frames import (LegendFrame, MapFrame, PageBorder, StampFrame,
                     TableFrame, TextFrame)
from .model import (A3_LANDSCAPE, A3_PORTRAIT, A4_PORTRAIT, Document,
                    Frame, Page)

__all__ = ["Document", "Page", "Frame", "A3_LANDSCAPE", "A3_PORTRAIT",
           "A4_PORTRAIT", "PageBorder", "MapFrame", "LegendFrame",
           "TableFrame", "TextFrame", "StampFrame", "document_pages_ops",
           "render_document_pdf", "render_page_svg"]
__version__ = "0.1.0"
