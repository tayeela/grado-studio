"""Подмена сети для тестов коннекторов: ответы портала по очереди через httpx.MockTransport, паузы повторов — в список.

Используют test_netutil.py, test_osm.py, test_gisogd_api.py, test_nspd_*.py, test_yandex_vmap.py.
"""

import httpx

from grado_connectors import netutil


class FakeNet:
    """with FakeNet(ответ, ответ, …) as net: … — каждый запрос берёт следующий ответ.

    Ответ — httpx.Response, число (код без тела), bytes (200 с телом) или исключение (бросается при запросе).
    net.requests — пришедшие запросы, net.sleeps — паузы между попытками.
    """

    def __init__(self, *answers, repeat_last=False):
        self.answers, self.repeat_last = list(answers), repeat_last
        self.requests, self.sleeps = [], []

    def _handle(self, request):
        self.requests.append(request)
        a = self.answers[0] if len(self.answers) == 1 and self.repeat_last else self.answers.pop(0)
        if isinstance(a, BaseException):
            raise a
        if isinstance(a, int):
            return httpx.Response(a)
        if isinstance(a, (bytes, str)):
            return httpx.Response(200, content=a)
        return a

    def __enter__(self):
        self._saved = netutil.TRANSPORT, netutil.sleep
        netutil.TRANSPORT = httpx.MockTransport(self._handle)
        netutil.sleep = self.sleeps.append
        return self

    def __exit__(self, *exc):
        netutil.TRANSPORT, netutil.sleep = self._saved
