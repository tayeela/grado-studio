"""Запросы к порталам одним правилом: httpx (клиент) и tenacity (повторы), потолок размера, редиректы только на https.

Вызывают все коннекторы (nspd, osm, gisogd_api, fgistp, geocode, terrain, yandex_vmap) и выгрузки сервера
(apps/grado2/sat_io.py, server.esri_tile). Правило повторов одно на все порталы: не больше трёх попыток,
повтор — на 429, 5xx, обрыв сети и таймаут; пауза 1 с, 2 с или сколько просит Retry-After (не больше 30 с);
ошибка сертификата и прочие 4xx не повторяются. Тесты подменяют сеть через TRANSPORT (httpx.MockTransport):
core/connectors/tests/test_netutil.py и тесты коннекторов.
"""
import asyncio
import contextlib
import ssl
import time

import httpx
import tenacity

from .contract import ConnectorError

MAX_RESPONSE = 256 * 2**20
ATTEMPTS = 3                                   # «не больше трёх повторов» (CLAUDE.md): три попытки на запрос
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_WAIT = 30.0

TRANSPORT = None                               # тесты: httpx.MockTransport(handler) вместо сети
PORTAL_POLICY = None                           # сервер: before/response для общей паузы портала

sleep = time.sleep                             # тесты подменяют паузы между попытками


class HttpError(ConnectorError):
    """Портал ответил кодом ≥ 400 (после всех попыток для 429 и 5xx)."""

    def __init__(self, code, body=b"", headers=None):
        super().__init__(f"HTTP {code}")
        self.code, self.body, self.headers = code, body, headers or {}


class NetError(ConnectorError):
    """Сеть: нет соединения, таймаут, обрыв; cert=True — сертификат не прошёл проверку."""

    def __init__(self, cause):
        super().__init__(" ".join(str(cause).split())[:300] or type(cause).__name__)
        self.cause = cause
        self.cert = is_cert_error(cause)


class BadBody(ConnectorError):
    """Ответ пришёл, но не тот (капча вместо тайла, обрезанный файл): повтор, а не кэш."""


def is_cert_error(e):
    """Ошибка проверки сертификата где-то в цепочке причин (httpx заворачивает ssl-ошибку в ConnectError)."""
    seen = 0
    while e is not None and seen < 8:
        if isinstance(e, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(e):
            return True
        e, seen = e.__cause__ or e.__context__, seen + 1
    return False


def ssl_context(extra_pem=()):
    """Проверяющий контекст на корнях certifi (сборки Python.org на macOS не видят системные CA, правило 4)
    плюс дополнительные корни в PEM (НСПД: НУЦ Минцифры). Проверка не отключается."""
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    for pem in extra_pem:
        ctx.load_verify_locations(cadata=pem)
    return ctx


def _https_only(response):
    if response.is_redirect and response.url.join(response.headers.get("location", "")).scheme != "https":
        raise ConnectorError("Редирект не на https отклонён")


def _client(timeout, context):
    kw = {"timeout": timeout, "follow_redirects": True, "event_hooks": {"response": [_https_only]}}
    if TRANSPORT is not None:
        kw["transport"] = TRANSPORT
    else:
        kw["verify"] = context if context is not None else ssl_context()
    return httpx.Client(**kw)


class RateLimited(HttpError):
    """Первая 429/503 с паузой: не повторять, ждать общий cooldown источника."""


def _retryable(e):
    if isinstance(e, RateLimited):
        return False
    if isinstance(e, HttpError):
        return e.code in RETRY_STATUS
    if isinstance(e, BadBody):
        return True
    return isinstance(e, NetError) and not e.cert


def _wait(state):
    e = state.outcome.exception()
    after = getattr(e, "headers", {}).get("Retry-After", "") if isinstance(e, HttpError) else ""
    if after.strip().isdigit():
        return min(float(after), MAX_WAIT)
    return float(state.attempt_number)          # 1 с, затем 2 с


def _retrying(attempts, cancel=None):
    """cancel — threading.Event: запрос, ставший ненужным (зеркало проиграло гонку), больше не повторяется."""
    def pause(seconds):
        if cancel is not None:
            cancel.wait(seconds)
        else:
            sleep(seconds)
    return tenacity.Retrying(stop=tenacity.stop_after_attempt(attempts), wait=_wait,
                             retry=tenacity.retry_if_exception(_retryable), sleep=pause, reraise=True)


def _check(r, limit):
    """Код ≥ 400 → HttpError с телом (не больше 64 КБ)."""
    if r.status_code >= 400:
        body = b""
        with contextlib.suppress(httpx.HTTPError):
            for c in r.iter_bytes():
                body += c
                if len(body) > 65536:
                    break
        raise HttpError(r.status_code, body[:65536], r.headers)


class Response:
    __slots__ = ("status", "headers", "content", "url")

    def __init__(self, status, headers, content, url):
        self.status, self.headers, self.content, self.url = status, headers, content, url

    def json(self):
        import json
        return json.loads(self.content.decode("utf-8"))


def request(url, *, method="GET", headers=None, content=None, timeout=30, context=None,
            limit=MAX_RESPONSE, attempts=ATTEMPTS, cancel=None, check=None, portal=None):
    """Запрос с повторами → Response (тело целиком, не больше limit байт, Content-Encoding уже снят).

    check(тело) — проверка содержимого: ValueError/IndexError в ней — повтор (BadBody после всех попыток).
    HttpError — код ≥ 400; NetError — сеть или сертификат; ConnectorError — ответ больше limit, редирект не на https.
    """
    def once():
        if portal and PORTAL_POLICY:
            PORTAL_POLICY("before", portal, None, None)
        if cancel is not None and cancel.is_set():
            raise ConnectorError("запрос отменён")
        try:
            with _client(timeout, context) as c, c.stream(method, url, headers=headers, content=content) as r:
                try:
                    _check(r, limit)
                except HttpError as e:
                    if portal and PORTAL_POLICY:
                        PORTAL_POLICY("response", portal, e.code, e.headers)
                    raise
                data = bytearray()
                for chunk in r.iter_bytes():
                    data += chunk
                    if len(data) > limit:
                        raise ConnectorError(f"Ответ больше {limit // 2**20} МБ")
                resp = Response(r.status_code, r.headers, bytes(data), str(r.url))
        except httpx.HTTPError as e:
            raise NetError(e) from None
        if check is not None:
            try:
                check(resp.content)
            except (ValueError, IndexError) as e:
                raise BadBody(f"ответ не прочитан: {e}") from None
        return resp
    return _retrying(attempts, cancel)(once)


@contextlib.contextmanager
def stream(url, *, headers=None, timeout=300, context=None, attempts=ATTEMPTS):
    """Открыть ответ без чтения тела (большие выгрузки): повторы — только на открытии соединения.

    Отдаёт httpx.Response: headers, iter_raw(n) — байты как пришли по сети (gzip распаковывает вызывающий,
    со своей защитой от бомбы), iter_bytes(n). Обрыв посреди тела — NetError, без молчаливой докачки.
    """
    def open_once():
        client = _client(timeout, context)
        try:
            r = client.send(client.build_request("GET", url, headers=headers), stream=True)
            _check(r, 0)
            return client, r
        except httpx.HTTPError as e:
            client.close()
            raise NetError(e) from None
        except BaseException:
            client.close()
            raise
    client, r = _retrying(attempts)(open_once)
    try:
        yield r
    except httpx.HTTPError as e:
        raise NetError(e) from None
    finally:
        r.close()
        client.close()


async def arequest(url, *, headers=None, timeout=30, context=None, limit=MAX_RESPONSE,
                   attempts=ATTEMPTS, cancel=None, deadline=None, check=None, portal=None):
    """Общее асинхронное правило сети с суммарным deadline и закрытием соединения при отмене.

    Панорамы используют этот метод вместо дополнительного цикла повторов. 429 прекращает
    операцию сразу; паузу сохраняет серверная PORTAL_POLICY. Остальные вызовы request прежние.
    """
    async def redirect(response):
        _https_only(response)

    async def once():
        if cancel is not None and cancel.is_set():
            raise ConnectorError("запрос отменён")
        if portal and PORTAL_POLICY:
            PORTAL_POLICY("before", portal, None, None)
        remaining = timeout if deadline is None else min(timeout, deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("общий срок запроса истёк")
        kw = {"timeout": remaining, "follow_redirects": True,
              "event_hooks": {"response": [redirect]}}
        if TRANSPORT is not None:
            kw["transport"] = TRANSPORT
        else:
            kw["verify"] = context if context is not None else ssl_context()
        try:
            async with httpx.AsyncClient(**kw) as client:
                async with client.stream("GET", url, headers=headers) as r:
                    if r.status_code >= 400:
                        body = bytearray()
                        async for chunk in r.aiter_bytes():
                            body.extend(chunk[:max(0, 65536-len(body))])
                            if len(body) >= 65536:
                                break
                        if portal and PORTAL_POLICY:
                            PORTAL_POLICY("response", portal, r.status_code, r.headers)
                        error = RateLimited if r.status_code == 429 else HttpError
                        raise error(r.status_code, bytes(body), r.headers)
                    body = bytearray()
                    async for chunk in r.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > limit:
                            raise ConnectorError("Ответ источника превышает допустимый размер")
                    result = Response(r.status_code, r.headers, bytes(body), str(r.url))
        except httpx.HTTPError as e:
            raise NetError(e) from None
        if check is not None:
            try:
                check(result.content)
            except (ValueError, IndexError) as e:
                raise BadBody(f"ответ не прочитан: {e}") from None
        return result

    async def run():
        retry = tenacity.AsyncRetrying(stop=tenacity.stop_after_attempt(min(ATTEMPTS, attempts)),
                                     wait=_wait, retry=tenacity.retry_if_exception(_retryable), reraise=True)
        async for attempt in retry:
            with attempt:
                return await once()

    async def wait_cancel():
        while True:
            if cancel is not None and cancel.is_set():
                return
            await asyncio.sleep(.1)

    task = asyncio.create_task(run())
    watcher = asyncio.create_task(wait_cancel()) if cancel is not None else None
    try:
        seconds = max(0., deadline - time.monotonic()) if deadline is not None else None
        async with asyncio.timeout(seconds):
            if watcher:
                done, _ = await asyncio.wait((task, watcher), return_when=asyncio.FIRST_COMPLETED)
                if watcher in done:
                    raise ConnectorError("запрос отменён")
            return await task
    finally:
        task.cancel()
        if watcher:
            watcher.cancel()
        await asyncio.gather(task, *([watcher] if watcher else []), return_exceptions=True)
