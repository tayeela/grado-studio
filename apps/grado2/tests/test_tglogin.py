"""Тесты входа через Telegram (apps/grado2/tglogin.py, Hub.tg_login, маршруты /api/hub/tg/* в server.py).
Telegram подменён: свой ключ RSA подписывает id_token, обмен кода на токен — заглушка; сеть не нужна."""

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if not os.environ.get("GRADO2_PROJECTS"):         # папка владельца неприкосновенна: проекты тестов — во временной
    os.environ["GRADO2_PROJECTS"] = tempfile.mkdtemp(prefix="grado2-tg-")
import hub as hubmod  # noqa: E402
import server as S  # noqa: E402
import tglogin as T  # noqa: E402

hubmod.SCRYPT_N = 2 ** 4
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ENV = {"GRADO2_TG_CLIENT_ID": "7000001", "GRADO2_TG_CLIENT_SECRET": "secret-x", "GRADO2_TG_ADMINS": "@Boss_TG, 42"}
CFG = T.config(ENV)


def id_token(tid=555, username="anna_tg", name="Анна Петрова", aud="7000001", iss=T.ISSUER, exp=600, key=KEY):
    now = int(time.time())
    return jwt.encode({"iss": iss, "aud": aud, "sub": str(tid), "id": tid, "iat": now, "exp": now + exp,
                       "preferred_username": username, "name": name}, key, algorithm="RS256")


class TgProtocol(unittest.TestCase):
    def test_config_needs_id_and_secret(self):
        self.assertIsNone(T.config({}))
        self.assertIsNone(T.config({"GRADO2_TG_CLIENT_ID": "1"}))
        self.assertEqual(CFG[2], {"boss_tg", "42"})

    def test_start_url_and_state_roundtrip(self):
        url, cookie = T.start(CFG, "grado.example", invite="INV1")
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        self.assertTrue(url.startswith(T.AUTH_URL + "?"))
        self.assertEqual(q["redirect_uri"], "https://grado.example/api/hub/tg/callback")
        self.assertEqual(q["code_challenge_method"], "S256")
        st = T.check_state(CFG, cookie, q["state"])
        self.assertEqual(st["i"], "INV1")
        self.assertTrue(cookie.isascii() and ";" not in cookie and " " not in cookie)   # годится в Set-Cookie как есть

    def test_state_forged_expired_or_other(self):
        url, cookie = T.start(CFG, "h")
        state = parse_qs(urlparse(url).query)["state"][0]
        data, _, sig = cookie.partition(".")
        for bad in ("", data + ".x" + sig, "abc"):
            with self.assertRaises(T.TgError):
                T.check_state(CFG, bad, state)
        with self.assertRaises(T.TgError):
            T.check_state(CFG, cookie, state + "x")
        with self.assertRaises(T.TgError) as e:
            T.check_state(CFG, cookie, state, now=time.time() + T.STATE_TTL + 5)
        self.assertEqual(e.exception.code, "expired")
        with self.assertRaises(T.TgError):                   # чужой секрет
            T.check_state((CFG[0], "other", set()), cookie, state)

    def test_verify_checks_signature_audience_issuer_expiry(self):
        pub = KEY.public_key()
        p = T.verify(CFG, id_token(), key=pub)
        self.assertEqual(p, {"id": "555", "username": "anna_tg", "name": "Анна Петрова"})
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        for tok in (id_token(key=other), id_token(aud="999"), id_token(iss="https://evil.example"), id_token(exp=-3600)):
            with self.assertRaises(T.TgError):
                T.verify(CFG, tok, key=pub)

    def test_exchange_sends_verifier_and_secret(self):
        seen = {}

        def post(url, data, auth):
            seen.update(url=url, data=data, auth=auth)
            return 200, {"id_token": "TOK"}
        self.assertEqual(T.exchange(CFG, "h", "CODE", "VER", post=post), "TOK")
        self.assertEqual(seen["auth"], ("7000001", "secret-x"))
        self.assertEqual(seen["data"]["code_verifier"], "VER")
        with self.assertRaises(T.TgError):
            T.exchange(CFG, "h", "CODE", "VER", post=lambda *a: (400, {"error": "invalid_grant"}))

    def test_admin_by_id_or_username(self):
        self.assertTrue(T.is_admin(CFG, {"id": "42", "username": ""}))
        self.assertTrue(T.is_admin(CFG, {"id": "1", "username": "boss_tg"}))
        self.assertFalse(T.is_admin(CFG, {"id": "1", "username": ""}))


class HubTgLogin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = hubmod.Hub(Path(self.tmp.name) / "hub")
        self.hub.create_user("boss", "password-boss", "Начальник", admin=True)

    def tearDown(self):
        self.tmp.cleanup()

    P = {"id": "555", "username": "anna_tg", "name": "Анна"}

    def test_stranger_is_refused(self):
        with self.assertRaises(hubmod.HubError) as e:
            self.hub.tg_login(self.P, "1.1.1.1")
        self.assertEqual((e.exception.status, e.exception.code), (403, "unknown"))
        self.assertNotIn("anna_tg", self.hub.users)

    def test_invite_creates_account_once(self):
        code = self.hub.create_invite({"login": "boss"})
        token, user = self.hub.tg_login(self.P, "1.1.1.1", invite=code)
        self.assertEqual(user, {"login": "anna_tg", "name": "Анна", "admin": False, "tg": True})
        self.assertEqual(self.hub.session_user(token)["login"], "anna_tg")
        _, again = self.hub.tg_login(self.P, "1.1.1.1")              # второй вход — без приглашения
        self.assertEqual(again["login"], "anna_tg")
        with self.assertRaises(hubmod.HubError) as e:                # код уже использован
            self.hub.tg_login({"id": "777", "username": "x_y", "name": ""}, "1.1.1.1", invite=code)
        self.assertEqual(e.exception.code, "invite")

    def test_taken_username_gets_tg_login(self):
        self.hub.create_user("anna_tg", "password-anna", "Другая Анна")
        code = self.hub.create_invite({"login": "boss"})
        _, user = self.hub.tg_login(self.P, "1.1.1.1", invite=code)
        self.assertEqual(user["login"], "tg555")
        self.assertNotIn("tg", self.hub.users["anna_tg"])            # чужая учётная запись не тронута

    def test_admin_binds_to_same_login_or_is_created(self):
        _, user = self.hub.tg_login({"id": "42", "username": "boss", "name": "B"}, "ip", admin=True)
        self.assertEqual((user["login"], user["admin"]), ("boss", True))
        _, user = self.hub.tg_login({"id": "43", "username": "", "name": "Новый"}, "ip", admin=True)
        self.assertEqual((user["login"], user["admin"]), ("tg43", True))

    def test_bind_to_own_account_and_conflicts(self):
        _, user = self.hub.tg_login(self.P, "ip", bind="boss")
        self.assertEqual(user["login"], "boss")
        _, user = self.hub.tg_login(self.P, "ip")                    # дальше Telegram пускает в boss
        self.assertEqual(user["login"], "boss")
        self.hub.create_user("vic", "password-vic")
        with self.assertRaises(hubmod.HubError) as e:
            self.hub.tg_login(self.P, "ip", bind="vic")
        self.assertEqual(e.exception.code, "taken")

    def test_disabled_account_not_let_in(self):
        self.hub.tg_login(self.P, "ip", bind="boss")
        self.hub.create_user("adm2", "password-adm2", admin=True)
        self.hub.update_user({"login": "adm2"}, "boss", disabled=True)
        with self.assertRaises(hubmod.HubError) as e:
            self.hub.tg_login(self.P, "ip")
        self.assertEqual(e.exception.code, "disabled")


class TgHttp(unittest.TestCase):
    """Настоящий сервер в совместном режиме: /api/hub/tg/start → (Telegram подменён) → /api/hub/tg/callback."""

    @classmethod
    def setUpClass(cls):
        cls.srv = S.Server(("127.0.0.1", 0))
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.port = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = hubmod.Hub(Path(self.tmp.name) / "hub")
        self.hub.create_user("boss", "password-boss", admin=True)
        self.patches = [mock.patch.object(S, "HUB", self.hub), mock.patch.dict(os.environ, ENV),
                        mock.patch.object(T, "_post", lambda url, data, auth: (200, {"id_token": self.tok})),
                        mock.patch.object(T, "_jwks_client", lambda: mock.Mock(get_signing_key_from_jwt=lambda t: mock.Mock(key=KEY.public_key())))]
        for p in self.patches:
            p.start()
        self.tok = id_token(tid=42, username="boss_tg", name="Босс")

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def get(self, path, cookie=None):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", path, headers={"Cookie": cookie} if cookie else {})
        r = c.getresponse()
        r.read()
        c.close()
        return r

    def cookies(self, r):
        return {v.split("=", 1)[0]: v.split(";")[0].split("=", 1)[1] for v in r.headers.get_all("Set-Cookie") or []}

    def start(self, q=""):
        r = self.get("/api/hub/tg/start" + q)
        self.assertEqual(r.status, 302)
        loc = r.getheader("Location")
        self.assertTrue(loc.startswith(T.AUTH_URL))
        return parse_qs(urlparse(loc).query)["state"][0], self.cookies(r)[T.STATE_COOKIE]

    def test_me_tells_page_that_telegram_is_on(self):
        import http.client
        import json
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", "/api/hub/me")
        r = c.getresponse()
        self.assertEqual((r.status, json.loads(r.read()).get("tg")), (401, True))

    def test_full_login_sets_session(self):
        state, st = self.start()
        r = self.get(f"/api/hub/tg/callback?code=C&state={state}", f"{T.STATE_COOKIE}={st}")
        self.assertEqual((r.status, r.getheader("Location")), (302, "/next/"))
        ck = self.cookies(r)
        self.assertEqual(ck[T.STATE_COOKIE], "")                        # кука состояния погашена
        self.assertEqual(self.hub.session_user(ck[S.SESSION_COOKIE])["login"], "boss_tg")
        self.assertTrue(all(v.isascii() for v in r.headers.get_all("Set-Cookie")))

    def test_callback_without_state_cookie_refused(self):
        state, _ = self.start()
        r = self.get(f"/api/hub/tg/callback?code=C&state={state}")
        self.assertEqual(r.getheader("Location"), "/next/#tg=state")
        self.assertNotIn(S.SESSION_COOKIE, self.cookies(r))

    def test_stranger_and_cancel(self):
        self.tok = id_token(tid=9, username="nobody")
        state, st = self.start()
        r = self.get(f"/api/hub/tg/callback?code=C&state={state}", f"{T.STATE_COOKIE}={st}")
        self.assertEqual(r.getheader("Location"), "/next/#tg=unknown")
        r = self.get("/api/hub/tg/callback?error=access_denied")
        self.assertEqual(r.getheader("Location"), "/next/#tg=denied")

    def test_bind_from_logged_in_session(self):
        import http.client
        import json
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("POST", "/api/hub/login", body=json.dumps({"login": "boss", "password": "password-boss"}),
                  headers={"Content-Type": "application/json"})
        r = c.getresponse()
        r.read()
        sess = r.getheader("Set-Cookie").split(";")[0]
        self.tok = id_token(tid=777, username="someone")                # не админ, без приглашения — но привязка
        r = self.get("/api/hub/tg/start?bind=1", sess)
        state = parse_qs(urlparse(r.getheader("Location")).query)["state"][0]
        st = self.cookies(r)[T.STATE_COOKIE]
        r = self.get(f"/api/hub/tg/callback?code=C&state={state}", f"{sess}; {T.STATE_COOKIE}={st}")
        self.assertEqual(r.getheader("Location"), "/next/#tg=bound")
        self.assertEqual(self.hub.users["boss"]["tg"], "777")

    def test_off_without_config(self):
        with mock.patch.dict(os.environ, {"GRADO2_TG_CLIENT_ID": ""}):
            self.assertEqual(self.get("/api/hub/tg/start").getheader("Location"), "/next/#tg=off")


class SiteCookie(unittest.TestCase):
    P = {"id": "555", "username": "anna_tg", "name": "Анна"}

    def test_roles(self):
        self.assertEqual(T.site_role(CFG, {"id": "42", "username": ""}, {}), "o")
        with self.assertRaises(T.TgError):
            T.site_role(CFG, self.P, {})
        self.assertEqual(T.site_role(CFG, self.P, {"GRADO2_TG_GUESTS": "*"}), "g")
        self.assertEqual(T.site_role(CFG, self.P, {"GRADO2_TG_GUESTS": "@Anna_TG"}), "g")

    def test_cookie_signed_role_bound_and_expires(self):
        v = T.site_cookie(CFG, self.P, "g")
        self.assertTrue(v.startswith("g.") and v.isascii() and ";" not in v)
        self.assertEqual(T.site_check(CFG, v, ("o", "g"))["u"], "555")
        self.assertIsNone(T.site_check(CFG, v, ("o",)))                 # гость в копию владельца не входит
        self.assertIsNone(T.site_check(CFG, "o" + v[1:], ("o", "g")))   # роль в куке не подменить
        self.assertIsNone(T.site_check((CFG[0], "other", set()), v, ("o", "g")))
        self.assertIsNone(T.site_check(CFG, v, ("o", "g"), now=time.time() + T.SITE_TTL + 5))
        for bad in ("", "o", "o..", "g.x.y"):
            self.assertIsNone(T.site_check(CFG, bad, ("o", "g")))


class SiteHttp(TgHttp):
    """Сайт без хаба (как grado.tailink.tech): вход через Telegram закрывает всю программу, кука grado_site."""

    def setUp(self):
        self.patches = [mock.patch.object(S, "HUB", None), mock.patch.object(S, "SITE_ACCEPT", ("o",)),
                        mock.patch.dict(os.environ, {**ENV, "GRADO2_TG_GUESTS": "*"}),
                        mock.patch.object(T, "_post", lambda url, data, auth: (200, {"id_token": self.tok})),
                        mock.patch.object(T, "_jwks_client", lambda: mock.Mock(get_signing_key_from_jwt=lambda t: mock.Mock(key=KEY.public_key())))]
        for p in self.patches:
            p.start()
        self.tok = id_token(tid=42, username="boss_tg", name="Босс")

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def login(self):
        state, st = self.start()
        r = self.get(f"/api/hub/tg/callback?code=C&state={state}", f"{T.STATE_COOKIE}={st}")
        return r, self.cookies(r)

    def test_closed_without_cookie(self):
        self.assertEqual(self.get("/next/").getheader("Location"), "/login.html")
        self.assertEqual(self.get("/").getheader("Location"), "/login.html")
        self.assertEqual(self.get("/api/projects").status, 401)
        self.assertEqual(self.get("/login.html").status, 200)
        self.assertEqual(self.get("/api/health").status, 200)
        self.assertEqual(self.get("/api/site").status, 200)

    def test_owner_gets_in(self):
        r, ck = self.login()
        self.assertEqual((r.status, r.getheader("Location")), (302, "/next/"))
        v = ck[T.SITE_COOKIE]
        self.assertTrue(v.startswith("o."))
        self.assertEqual(self.get("/api/projects", f"{T.SITE_COOKIE}={v}").status, 200)
        self.assertEqual(self.get("/next/", f"{T.SITE_COOKIE}={v}").status, 200)

    def test_guest_gets_guest_cookie_not_owner_copy(self):
        self.tok = id_token(tid=9, username="nobody")
        r, ck = self.login()
        v = ck[T.SITE_COOKIE]
        self.assertTrue(v.startswith("g."))
        self.assertEqual(self.get("/api/projects", f"{T.SITE_COOKIE}={v}").status, 401)
        with mock.patch.object(S, "SITE_ACCEPT", ("o", "g")):           # гостевая копия его пускает
            self.assertEqual(self.get("/api/projects", f"{T.SITE_COOKIE}={v}").status, 200)

    def test_stranger_refused_when_no_guests(self):
        self.tok = id_token(tid=9, username="nobody")
        with mock.patch.dict(os.environ, {"GRADO2_TG_GUESTS": ""}):
            r, ck = self.login()
        self.assertEqual(r.getheader("Location"), "/login.html#tg=unknown")
        self.assertNotIn(T.SITE_COOKIE, ck)

    def test_cancel(self):
        self.assertEqual(self.get("/api/hub/tg/callback?error=access_denied").getheader("Location"), "/login.html#tg=denied")

    test_me_tells_page_that_telegram_is_on = test_full_login_sets_session = None
    test_callback_without_state_cookie_refused = test_stranger_and_cancel = None
    test_bind_from_logged_in_session = test_off_without_config = None


if __name__ == "__main__":
    unittest.main()
