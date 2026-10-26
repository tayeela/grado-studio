"""ГРАДО 2 · вход на общий сайт через Telegram (OpenID Connect, код + PKCE; владелец 26.10.2026).

Сайт уводит человека на oauth.telegram.org, Telegram возвращает его на /api/hub/tg/callback с кодом; сервер меняет код
на id_token (секрет бота), проверяет подпись по ключам Telegram (JWKS) и пускает в хаб по привязке Telegram → учётная запись.
Состояние входа (state, verifier PKCE, код приглашения) — в короткой подписанной куке, а не в памяти: перезапуск сервера
посреди входа его не рвёт. Настройка — переменные окружения (на msk — в службе grado):
  GRADO2_TG_CLIENT_ID      — Client ID из @BotFather → бот → Login Widget (это числовой id бота)
  GRADO2_TG_CLIENT_SECRET  — Client Secret оттуда же
  GRADO2_TG_ADMINS         — через запятую: id Telegram или @имя; такой человек входит без приглашения администратором
Allowed URL в BotFather: https://<GRADO2_PUBLIC_HOST>/api/hub/tg/callback. Тесты: tests/test_tglogin.py.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode

ISSUER = "https://oauth.telegram.org"
AUTH_URL = ISSUER + "/auth"
TOKEN_URL = ISSUER + "/token"
JWKS_URL = ISSUER + "/.well-known/jwks.json"
ALGS = ["RS256", "ES256", "EdDSA", "ES256K"]
STATE_COOKIE = "grado_tg"
STATE_TTL = 600                     # секунд на вход в Telegram
CALLBACK = "/api/hub/tg/callback"


class TgError(Exception):
    """Вход не удался; code — короткий ASCII-код для адреса страницы (#tg=код), текст — страница показывает по коду."""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


def config(env=None):
    """(client_id, secret, admins) или None, если вход через Telegram не настроен."""
    env = os.environ if env is None else env
    cid, sec = (env.get("GRADO2_TG_CLIENT_ID") or "").strip(), (env.get("GRADO2_TG_CLIENT_SECRET") or "").strip()
    if not cid or not sec:
        return None
    admins = {a.strip().lstrip("@").lower() for a in (env.get("GRADO2_TG_ADMINS") or "").split(",") if a.strip()}
    return cid, sec, admins


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(secret, data):
    return _b64(hmac.new(("grado-tg:" + secret).encode(), data.encode(), hashlib.sha256).digest())


def start(cfg, host, invite=None, bind=None, now=None):
    """Начало входа: (адрес Telegram для перехода, значение подписанной куки состояния).
    invite — код приглашения (новый человек); bind — логин вошедшего, который привязывает свой Telegram."""
    cid, sec, _ = cfg
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    payload = {"s": state, "v": verifier, "t": int(now or time.time())}
    if isinstance(invite, str) and invite.strip():
        payload["i"] = invite.strip()[:64]
    if bind:
        payload["b"] = bind
    data = _b64(json.dumps(payload, separators=(",", ":")).encode())
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    url = AUTH_URL + "?" + urlencode({
        "client_id": cid, "redirect_uri": redirect_uri(host), "response_type": "code", "scope": "openid profile",
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
    return url, data + "." + _sign(sec, data)


def redirect_uri(host):
    return f"https://{host}{CALLBACK}"


def check_state(cfg, cookie, state, now=None):
    """Кука состояния подлинная, свежая и того же входа (state из адреса) → её содержимое, иначе TgError."""
    data, _, sig = (cookie or "").partition(".")
    if not data or not hmac.compare_digest(sig, _sign(cfg[1], data)):
        raise TgError("state", "нет или поддельная кука состояния")
    try:
        p = json.loads(_unb64(data))
    except ValueError:
        raise TgError("state", "кука состояния не читается") from None
    if not isinstance(p, dict) or (now or time.time()) - p.get("t", 0) > STATE_TTL:
        raise TgError("expired")
    if not isinstance(state, str) or not hmac.compare_digest(str(p.get("s", "")), state):
        raise TgError("state", "state не совпал")
    return p


def exchange(cfg, host, code, verifier, post=None):
    """Код из адреса → id_token. post(url, data, auth) → (статус, dict) — подменяется в тестах."""
    cid, sec, _ = cfg
    post = post or _post
    status, j = post(TOKEN_URL, {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(host),
                                 "client_id": cid, "code_verifier": verifier}, (cid, sec))
    tok = j.get("id_token") if isinstance(j, dict) else None
    if status != 200 or not tok:
        raise TgError("token", f"Telegram ответил {status}: {str(j)[:200]}")
    return tok


def _ssl():
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())       # правило 4: корни certifi, проверка не отключается
    except ImportError:
        return ssl.create_default_context()


def _post(url, data, auth):
    import httpx
    with httpx.Client(timeout=20, verify=_ssl()) as cl:
        r = cl.post(url, data=data, auth=auth, headers={"Accept": "application/json"})
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {"raw": r.text[:200]}


_JWKS = {}


def _jwks_client():
    import jwt
    if "c" not in _JWKS:
        _JWKS["c"] = jwt.PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600, ssl_context=_ssl())
    return _JWKS["c"]


def verify(cfg, id_token, key=None):
    """Подпись Telegram, издатель, получатель (наш бот) и срок id_token → данные человека
    {"id": str, "username": str, "name": str}. key — открытый ключ вместо JWKS (тесты)."""
    import jwt
    try:
        k = key if key is not None else _jwks_client().get_signing_key_from_jwt(id_token).key
        c = jwt.decode(id_token, k, algorithms=ALGS, audience=cfg[0], issuer=ISSUER, leeway=60,
                       options={"require": ["exp", "iat", "iss", "aud", "sub"]})
    except jwt.PyJWTError as e:
        raise TgError("token", f"id_token не прошёл проверку: {e}") from None
    tid = str(c.get("id") or c.get("sub") or "")
    if not tid.isdecimal():
        raise TgError("token", "в id_token нет id Telegram")
    name = c.get("name") or " ".join(x for x in (c.get("given_name"), c.get("family_name")) if x) or ""
    return {"id": tid, "username": str(c.get("preferred_username") or "").lstrip("@"), "name": str(name)}


def is_admin(cfg, person):
    return person["id"] in cfg[2] or (person["username"] or "\0").lower() in cfg[2]
