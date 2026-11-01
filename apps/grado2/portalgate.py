"""ГРАДО 2 · очередь к порталам: к одному порталу ходит одно место программы за раз (владелец 10.10.2026, #51).

Выгрузка слоёв (server.fetch), «Всё из ГИС ОГД» (ogd_all.Job), поиск по кадастровому номеру и слой КРТ берут портал
через GATE.use({"gisogd", "nspd", …}). Внутри одной выгрузки её задания идут параллельно (один владелец — token);
вторая выгрузка к тем же порталам ждёт первую, к другим порталам идёт сразу. Аудит 12.10.2026, находка 7.
"""

import contextlib
import json
import math
import os
import uuid
from email.utils import parsedate_to_datetime
from pathlib import Path
import threading
import time

# вид источника server.SOURCES → портал; None — локальный файл, очередь не нужна
PORTAL_OF = {"gisogd": "gisogd", "gisogd_admin": None, "yandex_sit": "yandex"}


class Busy(Exception):
    """Портал занят другой выгрузкой дольше, чем готов ждать запрос."""


class Cooling(Busy):
    """Источник запросил паузу; следующая вкладка её также соблюдает."""
    def __init__(self, portal, until):
        super().__init__("Источник временно ограничил обращения")
        self.portal, self.until = portal, until


class Gate:
    def __init__(self):
        self._cv = threading.Condition()
        self._cooldown = {}
        self._cooldown_path = None
        self._own = {}                      # портал → [token, сколько раз взят]
        self._wait = {}                     # портал → {token: сколько ждут} — для fair
        self._last = {}                     # портал → token, державший его последним

    def _free(self, portals, token, fair=False):
        # fair: свой же token не берёт портал снова, пока его ждёт чужая выгрузка (иначе потоки одной выгрузки
        # передают портал друг другу и чужая не дожидается никогда, 26.10.2026)
        def others(p):
            return fair and any(t is not token for t in self._wait.get(p, {}))
        return all((self._own[p][0] is token and not others(p)) if p in self._own
                   else not (self._last.get(p) is token and others(p)) for p in portals)

    def acquire(self, portals, token, timeout=None, fair=False, cancel=None):
        """Взять все порталы разом (без взаимной блокировки двух выгрузок). timeout истёк — Busy.
        fair=True — только для захвата не изнутри своего же захвата (одна загрузка с сети), иначе взаимная блокировка."""
        portals = {p for p in portals if p}
        end = None if timeout is None else time.monotonic() + timeout
        with self._cv:
            self.check_cooldown(portals)
            for p in portals:
                w = self._wait.setdefault(p, {})
                w[token] = w.get(token, 0) + 1
            try:
                while not self._free(portals, token, fair):
                    self.check_cooldown(portals)
                    if cancel is not None and cancel.is_set():
                        raise Busy("Получение отменено")
                    left = None if end is None else end - time.monotonic()
                    if left is not None and left <= 0:
                        raise Busy(", ".join(sorted(portals)))
                    self._cv.wait(min(left, .2) if left is not None else .2 if cancel is not None else None)
            finally:
                for p in portals:
                    w = self._wait[p]
                    w[token] -= 1
                    if w[token] <= 0:
                        del w[token]
                    if not w:
                        del self._wait[p]
                self._cv.notify_all()
            self.check_cooldown(portals)
            if cancel is not None and cancel.is_set():
                raise Busy("Получение отменено")
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
                        self._last[p] = token
            self._cv.notify_all()

    @contextlib.contextmanager
    def use(self, portals, token=None, timeout=None, fair=False, cancel=None):
        token = token if token is not None else object()
        got = self.acquire(portals, token, timeout, fair, cancel)
        try:
            yield token
        finally:
            self.release(got, token)

    def configure_cooldown(self, path):
        """Служебный файл отдельного пространства кэша, без токенов и ответов источника."""
        with self._cv:
            self._cooldown_path = Path(path)
            if self._cooldown_path.exists():
                try:
                    values = json.loads(self._cooldown_path.read_text())
                    self._cooldown = {k: float(v) for k, v in values.items() if isinstance(v, (int, float))}
                except (OSError, ValueError, TypeError):
                    self._cooldown = {}

    def check_cooldown(self, portals):
        with self._cv:
            for portal in portals:
                until = self._cooldown.get(portal, 0)
                if until > time.time():
                    raise Cooling(portal, until)

    def defer(self, portal, retry_after=None, now=None):
        now = time.time() if now is None else now
        try:
            seconds = float(retry_after)
            if not math.isfinite(seconds):
                raise ValueError()
            until = now + max(1., seconds)
        except (ValueError, TypeError):
            try:
                date = parsedate_to_datetime(str(retry_after))
                if date.tzinfo is None:
                    from datetime import timezone
                    date = date.replace(tzinfo=timezone.utc)
                until = max(now + 1., date.timestamp())
            except (ValueError, TypeError, OverflowError):
                until = now + 60.
        with self._cv:
            self._cooldown[portal] = max(until, self._cooldown.get(portal, 0))
            if self._cooldown_path:
                path = self._cooldown_path
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_name("." + path.name + "." + uuid.uuid4().hex)
                try:
                    with tmp.open("w") as f:
                        json.dump(self._cooldown, f)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp, path)
                finally:
                    tmp.unlink(missing_ok=True)
            self._cv.notify_all()
            return self._cooldown[portal]

    def busy(self):
        with self._cv:
            return sorted(self._own)


GATE = Gate()


def portals_of(kinds):
    """Виды источников SOURCES → множество порталов."""
    return {PORTAL_OF.get(k, k) for k in kinds} - {None}


def install_network_policy(cache):
    """Связывает общий netutil с Gate при запуске сервера, а не при импорте в тестах."""
    from grado_connectors import netutil
    GATE.configure_cooldown(Path(cache) / "portal-cooldown.json")

    def policy(event, portal, code, headers):
        if event == "response" and (code == 429 or code == 503 and (headers or {}).get("Retry-After")):
            after = (headers or {}).get("Retry-After")
            until = GATE.defer(portal, after)
            raise netutil.RateLimited(code, headers={"Retry-After": str(max(1., until - time.time()))})
        if event == "before":
            try:
                GATE.check_cooldown({portal})
            except Cooling as e:
                raise netutil.RateLimited(429, headers={"Retry-After": str(max(1., e.until - time.time()))}) from None

    netutil.PORTAL_POLICY = policy
