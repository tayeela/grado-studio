"""Общие сетевые помощники коннекторов: потолок размера ответа и редиректы только на https."""
import urllib.request

from .contract import ConnectorError

MAX_RESPONSE = 256 * 2**20


class _HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise ConnectorError("Редирект не на https отклонён")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(req, timeout, context=None):
    """urlopen, который не следует редиректам на http/ftp."""
    opener = urllib.request.build_opener(
        _HttpsOnlyRedirect, urllib.request.HTTPSHandler(context=context))
    return opener.open(req, timeout=timeout)


def read_capped(resp, limit=MAX_RESPONSE):
    """Читает ответ целиком, но не больше limit байт."""
    data = resp.read(limit + 1)
    if len(data) > limit:
        raise ConnectorError(f"Ответ больше {limit // 2**20} МБ")
    return data
