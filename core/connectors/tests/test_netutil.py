"""Проверяет общее правило запросов к порталам (netutil на httpx и tenacity): повторы, паузы, потолок размера, редиректы.

Без сети: ответы подменены httpx.MockTransport (_fakenet.FakeNet), паузы пишутся в список.
Запуск: python -m unittest discover -s core/connectors/tests (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import ssl
import threading
import unittest

import httpx

import _paths  # noqa: F401
from _fakenet import FakeNet
from grado_connectors import netutil
from grado_connectors.contract import ConnectorError


class Retry(unittest.TestCase):
    def test_overload_twice_then_answer_waits_1_then_2_seconds(self):
        with FakeNet(503, 429, b"ok") as net:
            r = netutil.request("https://x/a")
        self.assertEqual(r.content, b"ok")
        self.assertEqual(len(net.requests), 3)
        self.assertEqual(net.sleeps, [1.0, 2.0])

    def test_three_attempts_at_most_then_the_last_error(self):
        with FakeNet(504, repeat_last=True) as net:
            with self.assertRaises(netutil.HttpError) as c:
                netutil.request("https://x/a")
        self.assertEqual(c.exception.code, 504)
        self.assertEqual(len(net.requests), netutil.ATTEMPTS)
        self.assertEqual(net.sleeps, [1.0, 2.0])                    # после последней попытки паузы нет

    def test_retry_after_is_honoured_and_capped(self):
        with FakeNet(httpx.Response(429, headers={"Retry-After": "7"}),
                     httpx.Response(429, headers={"Retry-After": "600"}), b"ok") as net:
            netutil.request("https://x/a")
        self.assertEqual(net.sleeps, [7.0, netutil.MAX_WAIT])

    def test_other_4xx_is_not_retried_and_keeps_body(self):
        with FakeNet(httpx.Response(400, content=b'{"message": "bad"}')) as net:
            with self.assertRaises(netutil.HttpError) as c:
                netutil.request("https://x/a")
        self.assertEqual(len(net.requests), 1)
        self.assertEqual(c.exception.body, b'{"message": "bad"}')

    def test_network_failure_and_timeout_are_retried(self):
        with FakeNet(httpx.ConnectError("reset"), httpx.ReadTimeout("slow"), b"ok") as net:
            self.assertEqual(netutil.request("https://x/a").content, b"ok")
        self.assertEqual(len(net.requests), 3)

    def test_certificate_failure_is_not_retried(self):
        err = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        with FakeNet(err) as net:
            with self.assertRaises(netutil.NetError) as c:
                netutil.request("https://x/a")
        self.assertTrue(c.exception.cert)
        self.assertEqual(len(net.requests), 1)
        wrapped = httpx.ConnectError("handshake")
        wrapped.__cause__ = ssl.SSLCertVerificationError("unable to get local issuer certificate")
        self.assertTrue(netutil.is_cert_error(wrapped))

    def test_bad_body_is_retried_then_reported(self):
        def check(data):
            if data != b"tile":
                raise ValueError("captcha")
        with FakeNet(b"<html>captcha</html>", b"tile") as net:
            self.assertEqual(netutil.request("https://x/a", check=check).content, b"tile")
        with FakeNet(b"<html>", repeat_last=True) as net:
            with self.assertRaises(netutil.BadBody):
                netutil.request("https://x/a", check=check)
        self.assertEqual(len(net.requests), 3)

    def test_cancelled_request_is_not_sent(self):
        stop = threading.Event()
        stop.set()
        with FakeNet(b"ok") as net:
            with self.assertRaises(ConnectorError):
                netutil.request("https://x/a", cancel=stop)
        self.assertEqual(net.requests, [])


class Limits(unittest.TestCase):
    def test_body_over_limit_is_refused_without_retry(self):
        with FakeNet(b"x" * 2000) as net:
            with self.assertRaises(ConnectorError):
                netutil.request("https://x/a", limit=1000)
        self.assertEqual(len(net.requests), 1)

    def test_redirect_to_plain_http_is_refused(self):
        with FakeNet(httpx.Response(302, headers={"Location": "http://evil/"})):
            with self.assertRaises(ConnectorError) as c:
                netutil.request("https://x/a")
        self.assertIn("https", str(c.exception))

    def test_redirect_to_https_is_followed(self):
        with FakeNet(httpx.Response(302, headers={"Location": "https://y/b"}), b"ok") as net:
            self.assertEqual(netutil.request("https://x/a").content, b"ok")
        self.assertEqual(str(net.requests[1].url), "https://y/b")

    def test_stream_gives_raw_bytes_and_retries_only_opening(self):
        with FakeNet(503, httpx.Response(200, stream=httpx.ByteStream(b"abc"))) as net:
            with netutil.stream("https://x/a") as r:
                self.assertEqual(b"".join(r.iter_raw(1)), b"abc")
        self.assertEqual(len(net.requests), 2)


if __name__ == "__main__":
    unittest.main()
