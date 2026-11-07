"""ГРАДО 2 · мини-журнал сервера (аудит 06.11, этап 4 п. 4.2): один формат вместо трёх стилей записи.

Было: print в stdout, sys.stderr.write с разными префиксами, stdlib logging только в fonts.py — причины сбоев
искали по-разному. Теперь всё через stdlib logging с двумя потоками: RotatingFileHandler
(~/.grado2/server.log, 1 МБ, 3 запасных) и stderr — сайт msk продолжает собирать журнал journald'ом,
локальная копия получает ещё и файл. ~/.grado2 не пишется (права, диск) — молча остаётся один stderr:
журнал не роняет сервер. Компоненты: save, print, ogd, auth, portal, http.

Путь берётся из GRADO2_LOG при первой записи (не при импорте): тесты подменяют переменной, не трогая
настоящий журнал владельца.
"""

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_PATH = Path.home() / ".grado2" / "server.log"
FORMAT = "%(asctime)s [%(levelname)s] [%(comp)s] %(message)s"      # ГГГГ-ММ-ДД ЧЧ:ММ:СС [LEVEL] [компонент] сообщение
DATE = "%Y-%m-%d %H:%M:%S"
MAX_BYTES, BACKUPS = 2**20, 3
_lock = threading.Lock()
_root = None


class _StderrHandler(logging.StreamHandler):
    """stderr берётся при каждой записи, а не при создании: тесты подменяют sys.stderr и читают журнал оттуда —
    прежние sys.stderr.write видели подмену, и поток не должен отставать от неё."""

    def emit(self, record):
        self.stream = sys.stderr
        super().emit(record)


def _comp(record):
    """Имя компонента без префикса: grado2.save → [save]."""
    record.comp = record.name.removeprefix("grado2.")
    return True


def _handler(h):
    h.setFormatter(logging.Formatter(FORMAT, DATE))
    h.addFilter(_comp)
    return h


def _setup():
    """Обвязка логгеров grado2.* — один раз (лениво: путь из GRADO2_LOG читается при первом сообщении)."""
    global _root
    with _lock:
        if _root is not None:
            return _root
        root = logging.getLogger("grado2")
        root.setLevel(logging.INFO)
        root.propagate = False                      # второй проход через корень дублировал бы строку в stderr
        root.addHandler(_handler(_StderrHandler()))
        try:
            path = Path(os.environ.get("GRADO2_LOG") or LOG_PATH)
            path.parent.mkdir(parents=True, exist_ok=True)
            root.addHandler(_handler(RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")))
        except OSError:
            pass                                    # ~/.grado2 не пишется — остаётся stderr, сервер работает
        _root = root
        return root


def get(component):
    """Логгер компонента: gravlog.get("save").info(…) / .error(…)."""
    _setup()
    return logging.getLogger(f"grado2.{component}")


def human(n):
    """Размер для журнала: «12.3 МБ», «456 КБ», «891 Б»."""
    return f"{n / 1e6:.1f} МБ" if n >= 1e6 else (f"{n / 1e3:.0f} КБ" if n >= 1e3 else f"{n} Б")


def _reset():
    """Тесты: убрать обвязку — следующий get() соберёт её заново (с другим путём/потоками)."""
    global _root
    with _lock:
        if _root is not None:
            for h in _root.handlers[:]:
                _root.removeHandler(h)
                h.close()
            _root = None
