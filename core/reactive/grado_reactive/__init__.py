"""grado_reactive — реактивное ядро «ГРАДО Студии» (эталонная реализация).

Единый путь изменений: команда → дельта → журнал → подписчики.
Журнал дельт закрывает undo/redo, ветки вариантов и (позже) синхронизацию.
"""

from .journal import MAIN, Journal, JournalError
from .session import Session
from .tep_link import TepLink

__all__ = ["Session", "Journal", "JournalError", "TepLink", "MAIN"]
__version__ = "0.1.0"
