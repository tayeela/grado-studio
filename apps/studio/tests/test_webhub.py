"""Веб-хаб: аккаунты по инвайтам, сессии, проекты, ревизии/409."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from webhub import Hub, HubError  # noqa: E402


class HubBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.hub = Hub(Path(self._tmp.name) / "hub", quiet=True)
        # стартовый инвайт создан автоматически (хаб пуст)
        self.invite0 = next(iter(self.hub.invites))

    def tearDown(self):
        self._tmp.cleanup()

    def _user(self, login="anna", invite=None):
        if invite is None:
            invite = next(c for c, v in self.hub.invites.items()
                          if v["used_by"] is None)
        return self.hub.register(invite, login, "секрет123")


class TestAuth(HubBase):
    def test_register_by_invite_and_login(self):
        token = self._user("anna")
        self.assertEqual(self.hub.session_user(token), "anna")
        # инвайт одноразовый
        with self.assertRaises(HubError):
            self.hub.register(self.invite0, "boris", "пароль99")
        # вход по паролю
        t2 = self.hub.login("anna", "секрет123")
        self.assertEqual(self.hub.session_user(t2), "anna")
        with self.assertRaises(HubError):
            self.hub.login("anna", "не тот пароль")

    def test_first_user_is_admin_and_can_invite(self):
        self._user("anna")
        self.assertTrue(self.hub.user_info("anna")["admin"])
        code = self.hub.create_invite("anna")
        t = self.hub.register(code, "boris", "пароль99")
        self.assertEqual(self.hub.session_user(t), "boris")
        self.assertFalse(self.hub.user_info("boris")["admin"])
        with self.assertRaises(HubError):     # не-админ приглашать не может
            self.hub.create_invite("boris")

    def test_bad_login_and_short_password(self):
        with self.assertRaises(HubError):
            self.hub.register(self.invite0, "а б", "пароль99")   # кириллица/пробел
        with self.assertRaises(HubError):
            self.hub.register(self.invite0, "anna", "123")       # короткий

    def test_logout_kills_session(self):
        token = self._user("anna")
        self.hub.logout(token)
        self.assertIsNone(self.hub.session_user(token))

    def test_sessions_survive_restart(self):
        token = self._user("anna")
        hub2 = Hub(self.hub.root, quiet=True)             # «перезапуск сервера»
        self.assertEqual(hub2.session_user(token), "anna")


class TestProjects(HubBase):
    def setUp(self):
        super().setUp()
        self._user("anna")
        code = self.hub.create_invite("anna")
        self.hub.register(code, "boris", "пароль99")

    def test_create_list_share(self):
        pid = self.hub.create_project("anna", "Квартал 12")["id"]
        self.assertEqual([p["id"] for p in self.hub.list_projects("anna")],
                         [pid])
        self.assertEqual(self.hub.list_projects("boris"), [],
                         "чужой проект не виден")
        self.hub.share_project(pid, "anna", "boris")
        self.assertEqual([p["id"] for p in self.hub.list_projects("boris")],
                         [pid])
        with self.assertRaises(HubError):     # делится только владелец
            self.hub.share_project(pid, "boris", "anna")
        with self.assertRaises(HubError):     # несуществующий пользователь
            self.hub.share_project(pid, "anna", "нет-такого")

    def test_access_control_on_state(self):
        pid = self.hub.create_project("anna", "Секретный")["id"]
        with self.assertRaises(HubError):
            self.hub.get_state(pid, "boris")
        with self.assertRaises(HubError):
            self.hub.put_state(pid, "boris", 0, {"features": []})

    def test_delete_only_owner(self):
        pid = self.hub.create_project("anna", "Врем")["id"]
        self.hub.share_project(pid, "anna", "boris")
        with self.assertRaises(HubError):
            self.hub.delete_project(pid, "boris")
        self.hub.delete_project(pid, "anna")
        with self.assertRaises(HubError):
            self.hub.get_state(pid, "anna")


class TestSync(HubBase):
    def setUp(self):
        super().setUp()
        self._user("anna")
        code = self.hub.create_invite("anna")
        self.hub.register(code, "boris", "пароль99")
        self.pid = self.hub.create_project("anna", "Совместный")["id"]
        self.hub.share_project(self.pid, "anna", "boris")

    def test_rev_increments_and_since_204(self):
        r1 = self.hub.put_state(self.pid, "anna", 0,
                                {"features": [{"id": 1}], "nextId": 2})
        self.assertEqual(r1["rev"], 1)
        # не менялось → unchanged (HTTP 204)
        out = self.hub.get_state(self.pid, "boris", since=1)
        self.assertTrue(out.get("unchanged"))
        # менялось → полный state
        out = self.hub.get_state(self.pid, "boris", since=0)
        self.assertEqual(out["rev"], 1)
        self.assertEqual(out["state"]["features"], [{"id": 1}])

    def test_conflict_409_serializes_writers(self):
        self.hub.put_state(self.pid, "anna", 0, {"features": [{"id": 1}]})
        # boris пишет со старым base_rev → conflict + актуальный state
        out = self.hub.put_state(self.pid, "boris", 0,
                                 {"features": [{"id": 2}]})
        self.assertTrue(out.get("conflict"))
        self.assertEqual(out["rev"], 1)
        self.assertEqual(out["state"]["features"], [{"id": 1}])
        # после «слияния» повторяет с новым base_rev — принято
        out2 = self.hub.put_state(self.pid, "boris", 1,
                                  {"features": [{"id": 1}, {"id": 2}]})
        self.assertEqual(out2["rev"], 2)

    def test_personal_keys_stripped(self):
        # личное (вид, undo, активный слой) на сервер не попадает
        self.hub.put_state(self.pid, "anna", 0, {
            "features": [], "undo": ["..."], "redo": ["..."],
            "activeLayerId": "user.x", "basemapSource": "sat",
            "exportStyle": "canvas"})
        st = self.hub.get_state(self.pid, "anna")["state"]
        for key in ("undo", "redo", "activeLayerId", "basemapSource",
                    "exportStyle"):
            self.assertNotIn(key, st)
        self.assertIn("features", st)

    def test_presence_online(self):
        self.hub.get_state(self.pid, "anna")
        out = self.hub.get_state(self.pid, "boris")
        self.assertEqual(out["online"], ["anna", "boris"])

    def test_state_survives_restart(self):
        self.hub.put_state(self.pid, "anna", 0, {"features": [{"id": 7}]})
        hub2 = Hub(self.hub.root, quiet=True)
        out = hub2.get_state(self.pid, "anna")
        self.assertEqual(out["rev"], 1)
        self.assertEqual(out["state"]["features"], [{"id": 7}])


if __name__ == "__main__":
    unittest.main()
