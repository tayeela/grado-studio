"""Веб-хаб: аккаунты по инвайтам, сессии, проекты, ревизии/409."""

import sys
import stat
import json
import tempfile
import threading
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import webhub  # noqa: E402
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
        with self.assertRaises(HubError):
            self.hub.register(self.invite0, "anna", "1234567")   # всё ещё короткий

    def test_unknown_login_still_runs_password_hash(self):
        with mock.patch.object(webhub, "_scrypt", return_value="not-a-match") as hasher:
            with self.assertRaises(HubError):
                self.hub.login("missing-user", "password")
        hasher.assert_called_once()

    def test_invalid_invite_is_rejected_before_password_hashing(self):
        with mock.patch.object(webhub, "_scrypt") as hasher:
            with self.assertRaises(HubError) as caught:
                self.hub.register("missing", "anna", "секрет123")
        self.assertEqual(403, caught.exception.status)
        hasher.assert_not_called()

    def test_login_throttles_repeated_failures_before_more_password_hashing(self):
        self._user("anna")
        with mock.patch.object(webhub, "_scrypt", return_value="not-a-match") as hasher:
            for _ in range(webhub.LOGIN_FAILURE_LIMIT):
                with self.assertRaises(HubError) as caught:
                    self.hub.login("anna", "wrong", client_key="192.0.2.10")
                self.assertEqual(401, caught.exception.status)
            with self.assertRaises(HubError) as caught:
                self.hub.login("anna", "wrong", client_key="192.0.2.10")
        self.assertEqual(429, caught.exception.status)
        self.assertEqual(webhub.LOGIN_FAILURE_LIMIT, hasher.call_count)

    def test_login_throttle_isolated_by_client(self):
        self._user("anna")
        with mock.patch.object(webhub, "_scrypt", return_value="not-a-match"):
            for _ in range(webhub.LOGIN_FAILURE_LIMIT):
                with self.assertRaises(HubError):
                    self.hub.login("anna", "wrong", client_key="192.0.2.10")
            with self.assertRaises(HubError) as caught:
                self.hub.login("anna", "wrong", client_key="192.0.2.11")
        self.assertEqual(401, caught.exception.status)

    def test_slow_login_does_not_block_project_operations(self):
        self._user("anna")
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        def slow_hash(_password, _salt):
            started.set()
            release.wait(2)
            return "not-a-match"

        def attempt_login():
            try:
                self.hub.login("anna", "wrong", client_key="192.0.2.44")
            except HubError:
                pass
            finally:
                finished.set()

        with mock.patch.object(webhub, "_scrypt", side_effect=slow_hash):
            worker = threading.Thread(target=attempt_login, daemon=True)
            worker.start()
            self.assertTrue(started.wait(1), "login hash did not start")
            # This needs the project lock. It must still complete while the
            # password hash is deliberately blocked on a separate lock.
            created = self.hub.create_project("anna", "Параллельный")
            self.assertRegex(created["id"], r"^[a-z0-9]{12}$")
            self.assertFalse(finished.is_set())
            release.set()
            worker.join(1)
        self.assertTrue(finished.is_set())

    @unittest.skipIf(sys.platform == "win32", "POSIX permissions are not portable to Windows")
    def test_hub_secrets_and_projects_are_private_to_current_os_user(self):
        self._user("anna")
        pid = self.hub.create_project("anna", "Закрытый")['id']

        self.assertEqual(0o700, stat.S_IMODE(self.hub.root.stat().st_mode))
        self.assertEqual(0o700, stat.S_IMODE(self.hub.projects_dir.stat().st_mode))
        for name in ("users.json", "invites.json", "sessions.json"):
            self.assertEqual(0o600, stat.S_IMODE((self.hub.root / name).stat().st_mode))
        self.assertEqual(
            0o600,
            stat.S_IMODE((self.hub.projects_dir / f"{pid}.json").stat().st_mode),
        )

    def test_logout_kills_session(self):
        token = self._user("anna")
        self.hub.logout(token)
        self.assertIsNone(self.hub.session_user(token))

    def test_sessions_survive_restart(self):
        token = self._user("anna")
        hub2 = Hub(self.hub.root, quiet=True)             # «перезапуск сервера»
        self.assertEqual(hub2.session_user(token), "anna")

    def test_expired_session_is_removed_from_memory_and_disk(self):
        token = self._user("anna")
        self.hub.sessions[token]["created"] = 0
        self.hub._save("sessions.json", self.hub.sessions)

        self.assertIsNone(self.hub.session_user(token))
        saved = json.loads((self.hub.root / "sessions.json").read_text(
            encoding="utf-8"))
        self.assertNotIn(token, saved)

    def test_malformed_sessions_are_pruned_on_restart(self):
        token = self._user("anna")
        sessions_path = self.hub.root / "sessions.json"
        sessions_path.write_text(json.dumps({
            token: self.hub.sessions[token],
            "broken-value": "not-an-object",
            "missing-login": {"created": 1e20},
            "bad-created": {"login": "anna", "created": "never"},
            "unknown-user": {"login": "ghost", "created": 1e20},
        }), encoding="utf-8")

        restarted = Hub(self.hub.root, quiet=True)
        self.assertEqual("anna", restarted.session_user(token))
        self.assertEqual({token}, set(restarted.sessions))
        saved = json.loads(sessions_path.read_text(encoding="utf-8"))
        self.assertEqual({token}, set(saved))

    def test_corrupted_account_store_fails_closed(self):
        (self.hub.root / "users.json").write_text("{broken", encoding="utf-8")
        with self.assertRaises(HubError) as caught:
            Hub(self.hub.root, quiet=True)
        self.assertEqual(500, caught.exception.status)
        self.assertIn("users.json", str(caught.exception))


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

    def test_create_project_retries_random_id_collision(self):
        first = self.hub.create_project("anna", "Первый")["id"]
        second_id = "b" * 12 if first != "b" * 12 else "c" * 12
        with mock.patch.object(webhub.secrets, "token_hex",
                               side_effect=[first, second_id]) as generator:
            created = self.hub.create_project("anna", "Второй")
        self.assertEqual(second_id, created["id"])
        self.assertEqual(2, generator.call_count)
        self.assertEqual(
            {"Первый", "Второй"},
            {project["name"] for project in self.hub.list_projects("anna")},
        )

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

    def test_corrupted_project_returns_controlled_server_error(self):
        pid = self.hub.create_project("anna", "Повреждённый")["id"]
        (self.hub.projects_dir / f"{pid}.json").write_text("{broken",
                                                            encoding="utf-8")

        with self.assertRaises(HubError) as caught:
            self.hub.get_state(pid, "anna")
        self.assertEqual(500, caught.exception.status)
        self.assertIn("повреждён", str(caught.exception))


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

    def test_rejects_malformed_shared_state(self):
        bad_payloads = (
            {"features": "not-a-list"},
            {"features": ["not-an-object"]},
            {"features": [], "layerOrder": [1, 2]},
            {"features": [], "layersVisible": []},
            {"features": [], "nextId": 0},
            {"features": [], "density": "not-a-number"},
        )
        for payload in bad_payloads:
            with self.subTest(payload=payload), self.assertRaises(HubError) as caught:
                self.hub.put_state(self.pid, "anna", 0, payload)
            self.assertEqual(caught.exception.status, 400)
        self.assertEqual(self.hub.get_state(self.pid, "anna")["rev"], 0)

    def test_accepts_empty_project_state(self):
        out = self.hub.put_state(self.pid, "anna", 0, {
            "features": [], "nextId": 1, "layerOrder": [],
            "layersVisible": {}, "projectStyles": {}, "density": "25",
            "educationZone": "2", "territoryMode": "1",
        })
        self.assertEqual(out["rev"], 1)
        state = self.hub.get_state(self.pid, "anna")["state"]
        self.assertEqual(state["features"], [])
        self.assertEqual(state["educationZone"], "2")

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
