"""ГРАДО 2 · очередь к порталам: к одному порталу ходит одно место программы за раз (владелец 10.10.2026, #51).

Выгрузка слоёв (server.fetch), «Всё из ГИС ОГД» (ogd_all.Job), поиск по кадастровому номеру и слой КРТ берут портал
через GATE.use({"gisogd", "nspd", …}). Внутри одной выгрузки её задания идут параллельно (один владелец — token);
вторая выгрузка к тем же порталам ждёт первую, к другим порталам идёт сразу. Аудит 12.10.2026, находка 7.
"""

import contextlib
import threading
import time

# вид источника server.SOURCES → портал; None — локальный файл, очередь не нужна
PORTAL_OF = {"gisogd": "gisogd", "gisogd_admin": None, "yandex_sit": "yandex"}


class Busy(Exception):
    """Портал занят другой выгрузкой дольше, чем готов ждать запрос."""


class Gate:
    def __init__(self):
        self._cv = threading.Condition()
        self._own = {}                      # портал → [token, сколько раз взят]

    def _free(self, portals, token):
        return all(p not in self._own or self._own[p][0] is token for p in portals)

    def acquire(self, portals, token, timeout=None):
        """Взять все порталы разом (без взаимной блокировки двух выгрузок). timeout истёк — Busy."""
        portals = {p for p in portals if p}
        end = None if timeout is None else time.monotonic() + timeout
        with self._cv:
            while not self._free(portals, token):
                left = None if end is None else end - time.monotonic()
                if left is not None and left <= 0:
                    raise Busy(", ".join(sorted(portals)))
                self._cv.wait(left)
            for p in portals:
                self._own.setdefault(p, [token, 0])[1] += 1
        return portals

    def release(self, portals, token):
        with self._cv:
            for p in portals:
                own = self._own.get(p)
                if own and own[0] is token:
                    own[1] -= 1
                    if own[1] <= 0:
                        del self._own[p]
            self._cv.notify_all()

    @contextlib.contextmanager
    def use(self, portals, token=None, timeout=None):
        token = token if token is not None else object()
        got = self.acquire(portals, token, timeout)
        try:
            yield token
        finally:
            self.release(got, token)

    def busy(self):
        with self._cv:
            return sorted(self._own)


GATE = Gate()


def portals_of(kinds):
    """Виды источников SOURCES → множество порталов."""
    return {PORTAL_OF.get(k, k) for k in kinds} - {None}
