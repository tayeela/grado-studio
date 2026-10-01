"""Тесты хаба совместной работы ГРАДО 2 (apps/grado2/hub.py): аккаунты, роли, ревизии разделов, история,
комментарии, присутствие и события. Каждому тесту — свой временный каталог; scrypt удешевлён."""

import copy
import gzip
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hub  # noqa: E402
from hub import Conflict, Hub, HubError  # noqa: E402

hub.SCRYPT_N = 2 ** 4          # быстрый scrypt: проверяется логика, не стойкость
PW = "correct horse"


def feature(uid, **props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [37.6, 55.7]},
            "properties": {"_uid": uid, **props}}


def layer_section(key, *uids, title=None):
    return {"spec": {"key": key, "title": title or key, "geom": "Point", "visible": True, "layerOpacity": 1,
                     "open": False, "group": None, "style": {}},
            "data": {"title": title or key, "source": "t", "fetched_at": None, "notes": "", "history": [],
                     "shp": None, "fc": {"type": "FeatureCollection", "features": [feature(u) for u in uids]},
                     "original": "=fc"}}


def sample_project(name="Образец"):
    """Проект в формате collectProject(): два слоя, личное состояние (view, current) — не для общего хранилища."""
    a, b = layer_section("a", "u1", "u2"), layer_section("b", "u3")
    return {"format": "grado2", "version": 2, "app": "ГРАДО 2 test", "name": name, "file": name,
            "saved_at": "2026-09-30T00:00:00.000Z", "dirty": True,
            "view": {"center": [37.6, 55.7], "zoom": 12, "basemap": "osm"},
            "territory": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                          "properties": {}},
            "imports": {"import:x": {"title": "x", "kind": "import"}}, "checked": ["a"], "current": "b",
            "groups": [{"id": "g1", "title": "Группа", "visible": True, "open": True}],
            "views": [{"id": "v1"}], "album": {"meta": {"object": "О"}, "sheets": []},
            "layers": [b["spec"], a["spec"]],          # порядок прорисовки: b раньше a
            "data": {"a": a["data"], "b": b["data"]},
            "graph": {"nodes": [], "links": []}}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.clock = [1_800_000_000.0]
        orig = hub._now
        hub._now = lambda: self.clock[0]
        self.addCleanup(setattr, hub, "_now", orig)
        self.hub = Hub(Path(self._tmp.name) / ".hub")
        self.admin = self.hub.create_user("admin", PW, "Админ", admin=True)
        self.owner = self.hub.create_user("owner", PW, "Владелец")
        self.editor = self.hub.create_user("editor", PW, "Редактор")
        self.viewer = self.hub.create_user("viewer", PW, "Зритель")
        self.stranger = self.hub.create_user("stranger", PW, "Чужой")

    def tick(self, seconds):
        self.clock[0] += seconds

    def new_project(self, project=None):
        pid = self.hub.create_project(self.owner, "Проект", project)["id"]
        self.hub.set_member(self.owner, pid, "editor", "editor")
        self.hub.set_member(self.owner, pid, "viewer", "viewer")
        return pid


class Accounts(Base):
    def test_create_and_login(self):
        token, user = self.hub.login("Owner", PW, "1.1.1.1")
        self.assertEqual(user, {"login": "owner", "name": "Владелец", "admin": False})
        self.assertEqual(self.hub.session_user(token), user)
        with self.assertRaises(HubError) as cm:
            self.hub.create_user("owner", PW)
        self.assertEqual(cm.exception.status, 409)

    def test_validation(self):
        for bad in ("ab", "Bad Login", "x" * 33, "ю" * 4, None):
            with self.assertRaises(HubError):
                self.hub.create_user(bad, PW)
        with self.assertRaises(HubError):
            self.hub.create_user("shorty", "1234567")

    def test_tokens_not_stored_raw(self):
        token, _ = self.hub.login("owner", PW, "1.1.1.1")
        raw = (Path(self._tmp.name) / ".hub" / "sessions.json").read_text(encoding="utf-8")
        self.assertNotIn(token, raw)
        self.assertEqual(len(json.loads(raw)), 1)

    def test_wrong_password_401_and_unknown_login_same_answer(self):
        for login in ("owner", "nobody"):
            with self.assertRaises(HubError) as cm:
                self.hub.login(login, "wrong-password", "1.1.1.1")
            self.assertEqual((cm.exception.status, cm.exception.message), (401, "неверный логин или пароль"))

    def test_login_throttle(self):
        for _ in range(hub.LOGIN_FAILS):
            with self.assertRaises(HubError) as cm:
                self.hub.login("owner", "wrong-password", "9.9.9.9")
            self.assertEqual(cm.exception.status, 401)
        with self.assertRaises(HubError) as cm:               # даже верный пароль заперт
            self.hub.login("owner", PW, "9.9.9.9")
        self.assertEqual(cm.exception.status, 429)
        self.tick(hub.FAIL_WINDOW + 1)
        self.assertTrue(self.hub.login("owner", PW, "9.9.9.9")[0])

    def test_login_throttle_survives_ip_change(self):
        for i in range(hub.LOGIN_FAILS):
            with self.assertRaises(HubError):
                self.hub.login("owner", "wrong-password", f"10.0.0.{i}")
        with self.assertRaises(HubError) as cm:
            self.hub.login("owner", PW, "10.0.1.1")
        self.assertEqual(cm.exception.status, 429)

    def test_ip_throttle(self):
        for i in range(hub.IP_FAILS):
            with self.assertRaises(HubError) as cm:
                self.hub.login(f"user{i:03d}", "wrong-password", "8.8.8.8")
            self.assertEqual(cm.exception.status, 401)
        with self.assertRaises(HubError) as cm:
            self.hub.login("owner", PW, "8.8.8.8")
        self.assertEqual(cm.exception.status, 429)
        self.assertTrue(self.hub.login("owner", PW, "7.7.7.7")[0])      # другой адрес не задет

    def test_success_clears_login_counter(self):
        for _ in range(hub.LOGIN_FAILS - 1):
            with self.assertRaises(HubError):
                self.hub.login("owner", "wrong-password", "1.1.1.1")
        self.hub.login("owner", PW, "1.1.1.1")
        with self.assertRaises(HubError) as cm:
            self.hub.login("owner", "wrong-password", "1.1.1.1")
        self.assertEqual(cm.exception.status, 401)

    def test_invites_single_use_and_expiry(self):
        code = self.hub.create_invite(self.admin)
        token, user = self.hub.register(code, "Newbie", "  Новичок  ", PW, "2.2.2.2")
        self.assertEqual(user, {"login": "newbie", "name": "Новичок", "admin": False})
        self.assertEqual(self.hub.session_user(token)["login"], "newbie")
        with self.assertRaises(HubError) as cm:                      # второй раз тот же код
            self.hub.register(code, "second", "", PW, "2.2.2.2")
        self.assertEqual(cm.exception.status, 403)
        code2 = self.hub.create_invite(self.admin)
        with self.assertRaises(HubError) as cm:                      # занятый логин
            self.hub.register(code2, "newbie", "", PW, "2.2.2.2")
        self.assertEqual(cm.exception.status, 409)
        self.tick(hub.INVITE_TTL + 1)
        with self.assertRaises(HubError) as cm:
            self.hub.register(code2, "late", "", PW, "2.2.2.2")
        self.assertEqual(cm.exception.status, 403)
        used = [i for i in self.hub.list_invites(self.admin) if i["code"] == code][0]
        self.assertEqual(used["used_by"], "newbie")

    def test_invite_guessing_is_throttled(self):
        for _ in range(hub.IP_FAILS):
            with self.assertRaises(HubError) as cm:
                self.hub.register("guess-guess-guess", "someone", "", PW, "6.6.6.6")
            self.assertEqual(cm.exception.status, 403)
        with self.assertRaises(HubError) as cm:
            self.hub.register("guess-guess-guess", "someone", "", PW, "6.6.6.6")
        self.assertEqual(cm.exception.status, 429)

    def test_admin_only_operations(self):
        for fn in (lambda: self.hub.create_invite(self.owner), lambda: self.hub.list_invites(self.owner),
                   lambda: self.hub.list_users(self.owner), lambda: self.hub.update_user(self.owner, "viewer", name="x")):
            with self.assertRaises(HubError) as cm:
                fn()
            self.assertEqual(cm.exception.status, 403)
        self.assertEqual(len(self.hub.list_users(self.admin)), 5)

    def test_update_user_disable_closes_sessions(self):
        token, _ = self.hub.login("viewer", PW, "1.1.1.1")
        row = self.hub.update_user(self.admin, "viewer", disabled=True, name="Зритель 2")
        self.assertTrue(row["disabled"])
        self.assertEqual(row["name"], "Зритель 2")
        self.assertIsNone(self.hub.session_user(token))
        with self.assertRaises(HubError) as cm:
            self.hub.login("viewer", PW, "1.1.1.1")
        self.assertEqual(cm.exception.status, 403)
        with self.assertRaises(HubError):
            self.hub.update_user(self.admin, "viewer", bogus=1)
        with self.assertRaises(HubError):
            self.hub.update_user(self.admin, "admin", disabled=True)    # себя и последнего админа нельзя
        with self.assertRaises(HubError):
            self.hub.update_user(self.admin, "admin", admin=False)

    def test_sessions_ttl_is_sliding_and_logout(self):
        token, _ = self.hub.login("owner", PW, "1.1.1.1")
        self.tick(hub.SESSION_TTL - 3600)
        self.assertIsNotNone(self.hub.session_user(token))           # продлилась
        self.tick(hub.SESSION_TTL - 3600)
        self.assertIsNotNone(self.hub.session_user(token))           # ещё раз: от последнего обращения
        self.tick(hub.SESSION_TTL + 1)
        self.assertIsNone(self.hub.session_user(token))
        token2, _ = self.hub.login("owner", PW, "1.1.1.1")
        self.hub.logout(token2)
        self.assertIsNone(self.hub.session_user(token2))
        self.assertIsNone(self.hub.session_user("x" * 40))
        self.assertIsNone(self.hub.session_user(None))

    def test_sessions_persist_between_instances(self):
        token, _ = self.hub.login("owner", PW, "1.1.1.1")
        again = Hub(Path(self._tmp.name) / ".hub")
        self.assertEqual(again.session_user(token)["login"], "owner")

    def test_passwords(self):
        u = self.hub.session_user(self.hub.login("owner", PW, "1.1.1.1")[0])
        with self.assertRaises(HubError) as cm:
            self.hub.change_password(u, "not-the-password", "new-password-1")
        self.assertEqual(cm.exception.status, 401)
        self.hub.change_password(u, PW, "new-password-1")
        self.hub.login("owner", "new-password-1", "1.1.1.1")
        with self.assertRaises(HubError):
            self.hub.login("owner", PW, "1.1.1.1")
        token = self.hub.login("owner", "new-password-1", "1.1.1.1")[0]
        self.hub.set_password("owner", "admin-reset-1")
        self.assertIsNone(self.hub.session_user(token))              # сброс админом гасит входы
        self.hub.login("owner", "admin-reset-1", "1.1.1.1")

    def test_storage_permissions(self):
        root = Path(self._tmp.name) / ".hub"
        self.assertEqual(root.stat().st_mode & 0o777, 0o700)
        self.assertEqual((root / "users.json").stat().st_mode & 0o777, 0o600)


class SplitJoin(unittest.TestCase):
    def test_split_shape(self):
        s = hub.split_project(sample_project())
        self.assertEqual(set(s), {"meta", "layer:a", "layer:b"})
        self.assertEqual(s["meta"]["current_order"], ["b", "a"])
        self.assertEqual(set(s["meta"]), set(hub.META_KEYS))
        self.assertEqual(set(s["layer:a"]), {"spec", "data"})
        self.assertNotIn("view", s["meta"])
        self.assertNotIn("current", s["meta"])

    def test_join_file_shape(self):
        s = hub.split_project(sample_project())
        p = hub.join_sections(s, "Имя")
        self.assertEqual((p["format"], p["version"], p["name"]), ("grado2", 2, "Имя"))
        self.assertEqual([l["key"] for l in p["layers"]], ["b", "a"])
        self.assertEqual(set(p["data"]), {"a", "b"})
        self.assertEqual(p["groups"][0]["id"], "g1")
        self.assertEqual(p["album"]["meta"]["object"], "О")
        json.dumps(p, allow_nan=False)

    def test_round_trip(self):
        s = hub.split_project(sample_project())
        self.assertEqual(hub.split_project(hub.join_sections(copy.deepcopy(s), "Образец")), s)
        self.assertEqual(hub.split_project(hub.join_sections(s)), s)

    def test_round_trip_with_deleted_layer(self):
        s = hub.split_project(sample_project())
        s["layer:a"] = None                                 # раздел удалён: join его пропускает
        p = hub.join_sections(s, "x")
        self.assertEqual([l["key"] for l in p["layers"]], ["b"])
        again = hub.split_project(p)
        self.assertNotIn("layer:a", again)
        self.assertEqual(again["meta"]["current_order"], ["b"])
        self.assertEqual(hub.split_project(hub.join_sections(again, "x")), again)

    def test_empty_and_odd_input(self):
        s = hub.split_project({"format": "grado2"})
        self.assertEqual(set(s), {"meta"})
        self.assertEqual(hub.split_project(hub.join_sections(s)), s)
        p = sample_project()
        p["layers"].append({"key": "no data"})                # слой без данных и ключ с пробелом — пропуск
        p["layers"].append({"key": "__proto__"})
        p["data"]["__proto__"] = {}
        self.assertEqual(set(hub.split_project(p)), {"meta", "layer:a", "layer:b"})
        with self.assertRaises(ValueError):
            hub.split_project([])

    def test_layer_not_in_order_goes_last(self):
        s = hub.split_project(sample_project())
        s["layer:z"] = layer_section("z", "u9")
        self.assertEqual([l["key"] for l in hub.join_sections(s)["layers"]], ["b", "a", "z"])


class Projects(Base):
    def test_create_get_and_list(self):
        pid = self.new_project(sample_project())
        self.assertRegex(pid, r"^[0-9a-f]{16}$")
        p = self.hub.get_project(self.owner, pid)
        self.assertEqual((p["name"], p["role"], p["rev"]), ("Проект", "owner", 1))
        self.assertEqual(set(p["sections"]), {"meta", "layer:a", "layer:b"})
        self.assertEqual(p["sec_rev"], {"meta": 1, "layer:a": 1, "layer:b": 1})
        self.assertEqual(p["sections"]["meta"]["name"], "Проект")
        rows = self.hub.list_projects(self.owner)
        self.assertEqual(len(rows), 1)
        self.assertEqual({m["login"]: m["role"] for m in rows[0]["members"]},
                         {"owner": "owner", "editor": "editor", "viewer": "viewer"})
        self.assertEqual(self.hub.list_projects(self.stranger), [])
        self.assertEqual(self.hub.list_projects(self.admin)[0]["role"], "admin")

    def test_create_rejects_foreign_files(self):
        for bad in ({"format": "other"}, [], {"format": "grado2", "version": 3}):
            with self.assertRaises(HubError):
                self.hub.create_project(self.owner, "x", bad)

    def test_project_file_is_openable(self):
        pid = self.new_project(sample_project())
        name, data = self.hub.project_file(self.viewer, pid)
        self.assertEqual(name, "Проект.grado2")
        p = json.loads(data)
        self.assertEqual((p["format"], p["version"], [l["key"] for l in p["layers"]]), ("grado2", 2, ["b", "a"]))
        self.assertEqual(p["name"], "Проект")

    def test_storage_layout(self):
        pid = self.new_project(sample_project())
        d = Path(self._tmp.name) / ".hub" / "projects" / pid
        self.assertTrue((d / "meta.json").is_file() and (d / "project.grado2").is_file())
        self.assertEqual(d.stat().st_mode & 0o777, 0o700)
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["members"]["owner"], "owner")

    def test_pid_path_safety(self):
        evil = ["../x", "..", "", "0123456789abcdeF", "0123456789abcde", "0123456789abcdef0", "0123456789abcdeg",
                "0123456789abcde/", "%2e%2e", "a" * 16 + "\n", None, 12]
        for pid in evil:
            for call in (lambda p: self.hub.get_project(self.owner, p), lambda p: self.hub.history(self.owner, p),
                         lambda p: self.hub.delete_project(self.owner, p), lambda p: self.hub.comments(self.owner, p),
                         lambda p: self.hub.push(self.owner, p, 0, {}, "c1"), lambda p: self.hub.subscribe(self.owner, p),
                         lambda p: self.hub.project_file(self.owner, p)):
                with self.assertRaises(HubError) as cm:
                    call(pid)
                self.assertEqual(cm.exception.status, 400, repr(pid))
            self.assertIsNone(self.hub.role_of(self.owner, pid))
        with self.assertRaises(HubError) as cm:                       # правильный формат, но нет такого
            self.hub.get_project(self.owner, "0" * 16)
        self.assertEqual(cm.exception.status, 404)

    def test_rename(self):
        pid = self.new_project()
        self.assertEqual(self.hub.rename_project(self.owner, pid, "  Новое   имя "), "Новое имя")
        p = self.hub.get_project(self.editor, pid)
        self.assertEqual((p["name"], p["rev"], p["sections"]["meta"]["name"]), ("Новое имя", 2, "Новое имя"))
        self.assertEqual(p["sec_rev"]["meta"], 2)
        for bad in ("", "   ", None):
            with self.assertRaises(HubError):
                self.hub.rename_project(self.owner, pid, bad)
        self.assertEqual(len(self.hub.rename_project(self.owner, pid, "я" * 100)), 60)

    def test_delete_project_removes_files(self):
        pid = self.new_project()
        self.hub.delete_project(self.owner, pid)
        self.assertFalse((Path(self._tmp.name) / ".hub" / "projects" / pid).exists())
        with self.assertRaises(HubError) as cm:
            self.hub.get_project(self.admin, pid)
        self.assertEqual(cm.exception.status, 404)


class Roles(Base):
    def setUp(self):
        super().setUp()
        self.pid = self.new_project(sample_project())
        self.stamp = 0

    def sec(self, rev, uid="n"):
        return {"layer:a": layer_section("a", "u1", "u2", uid)}

    def attempt(self, user, fn):
        try:
            fn()
            return True
        except HubError as e:
            self.assertIn(e.status, (403,), e.message)
            return False

    def test_matrix(self):
        h, pid = self.hub, self.pid
        for u, want in ((self.owner, "owner"), (self.editor, "editor"), (self.viewer, "viewer"),
                        (self.admin, "admin"), (self.stranger, None)):
            self.assertEqual(h.role_of(u, pid), want)
        rev = [1]

        def push(u):
            r = h.push(u, pid, h.get_project(self.owner, pid)["rev"], {"layer:a": layer_section("a", "p%d" % rev[0])}, "c")
            rev[0] += 1
            return r

        def project_ops(u):
            return [
                ("open", lambda: h.get_project(u, pid)), ("history", lambda: h.history(u, pid)),
                ("comments", lambda: h.comments(u, pid)), ("activity", lambda: h.activity(u, pid)),
                ("subscribe", lambda: h.subscribe(u, pid).close()),
                ("presence", lambda: h.presence(u, pid, "cl1", [1.0, 2.0], None, [])),
                ("file", lambda: h.project_file(u, pid)),
                ("comment", lambda: h.add_comment(u, pid, "привет", {"lonlat": [1, 2]})),
                ("push", lambda: push(u)),
            ]
        expect = {
            "owner": dict.fromkeys(["open", "history", "comments", "activity", "subscribe", "presence", "file", "comment", "push"], True),
            "editor": dict.fromkeys(["open", "history", "comments", "activity", "subscribe", "presence", "file", "comment", "push"], True),
            "viewer": {**dict.fromkeys(["open", "history", "comments", "activity", "subscribe", "presence", "file", "comment"], True), "push": False},
            "admin": dict.fromkeys(["open", "history", "comments", "activity", "subscribe", "presence", "file", "comment", "push"], True),
            "stranger": dict.fromkeys(["open", "history", "comments", "activity", "subscribe", "presence", "file", "comment", "push"], False),
        }
        users = {"owner": self.owner, "editor": self.editor, "viewer": self.viewer, "admin": self.admin, "stranger": self.stranger}
        for name, u in users.items():
            for op, fn in project_ops(u):
                self.assertEqual(self.attempt(u, fn), expect[name][op], f"{name}: {op}")

    def test_restore_rename_share_delete(self):
        h, pid = self.hub, self.pid
        h.push(self.owner, pid, 1, {"layer:a": layer_section("a", "x")}, "c")
        self.tick(hub.HISTORY_INTERVAL + 1)
        h.push(self.owner, pid, 2, {"layer:a": layer_section("a", "y")}, "c")
        snaps = h.history(self.owner, pid)
        self.assertTrue(snaps)
        results = {}
        for name, u in (("viewer", self.viewer), ("editor", self.editor), ("stranger", self.stranger)):
            results[name] = {
                "restore": self.attempt(u, lambda: h.restore(u, pid, snaps[-1]["rev"])),
                "rename": self.attempt(u, lambda: h.rename_project(u, pid, "чужое")),
                "share": self.attempt(u, lambda: h.set_member(u, pid, "stranger", "editor")),
                "delete": self.attempt(u, lambda: h.delete_project(u, pid)),
            }
        self.assertEqual(results["viewer"], dict(restore=False, rename=False, share=False, delete=False))
        self.assertEqual(results["editor"], dict(restore=True, rename=False, share=False, delete=False))
        self.assertEqual(results["stranger"], dict(restore=False, rename=False, share=False, delete=False))
        self.assertTrue(h.set_member(self.admin, pid, "stranger", "viewer"))        # админ делится
        self.assertEqual(h.role_of(self.stranger, pid), "viewer")
        h.rename_project(self.admin, pid, "админское")
        h.delete_project(self.admin, pid)

    def test_admin_sees_all_with_role_admin_but_is_not_a_member(self):
        rows = self.hub.list_projects(self.admin)
        self.assertEqual([r["role"] for r in rows], ["admin"])

    def test_last_owner_protected(self):
        h, pid = self.hub, self.pid
        for role in ("editor", "viewer", None):
            with self.assertRaises(HubError) as cm:
                h.set_member(self.owner, pid, "owner", role)
            self.assertEqual(cm.exception.status, 400)
        h.set_member(self.owner, pid, "editor", "owner")                # второй владелец
        h.set_member(self.owner, pid, "owner", "viewer")                # теперь можно понизить первого
        self.assertEqual(h.role_of(self.editor, pid), "owner")
        with self.assertRaises(HubError):
            h.set_member(self.editor, pid, "editor", None)              # а последнего — нельзя
        self.assertEqual(json.loads((Path(self._tmp.name) / ".hub" / "projects" / pid / "meta.json").read_text(encoding="utf-8"))["owner"], "editor")

    def test_set_member_validation(self):
        with self.assertRaises(HubError) as cm:
            self.hub.set_member(self.owner, self.pid, "ghost", "viewer")
        self.assertEqual(cm.exception.status, 404)
        with self.assertRaises(HubError):
            self.hub.set_member(self.owner, self.pid, "stranger", "boss")
        self.hub.set_member(self.owner, self.pid, "viewer", None)
        self.assertIsNone(self.hub.role_of(self.viewer, self.pid))

    def test_disabled_user_has_no_role(self):
        self.hub.update_user(self.admin, "editor", disabled=True)
        self.assertIsNone(self.hub.role_of(self.editor, self.pid))


class PushConflict(Base):
    def setUp(self):
        super().setUp()
        self.pid = self.new_project(sample_project())

    def push(self, base, sections, user=None, client="c1"):
        return self.hub.push(user or self.editor, self.pid, base, sections, client)

    def test_push_ok_bumps_rev_and_sec_rev(self):
        new_a = layer_section("a", "u1", "u2", "u7")
        self.assertEqual(self.push(1, {"layer:a": new_a}), {"rev": 2})
        p = self.hub.get_project(self.owner, self.pid)
        self.assertEqual((p["rev"], p["sec_rev"]), (2, {"meta": 1, "layer:a": 2, "layer:b": 1}))
        self.assertEqual(len(p["sections"]["layer:a"]["data"]["fc"]["features"]), 3)
        _, raw = self.hub.project_file(self.owner, self.pid)
        self.assertEqual(len(json.loads(raw)["data"]["a"]["fc"]["features"]), 3)     # файл перезаписан
        self.assertEqual(self.hub.get_sections(self.owner, self.pid, ["layer:a", "layer:zzz"])["sections"]["layer:zzz"], None)

    def test_other_sections_do_not_conflict_same_do(self):
        self.push(1, {"layer:a": layer_section("a", "u1")})
        self.assertEqual(self.push(1, {"layer:b": layer_section("b", "u3", "u4")}, self.owner, "c2"), {"rev": 3})
        with self.assertRaises(Conflict) as cm:
            self.push(1, {"layer:a": layer_section("a", "zzz")}, self.owner, "c2")
        e = cm.exception
        self.assertEqual(e.status, 409)
        self.assertEqual(e.payload["rev"], 3)
        self.assertEqual(set(e.payload["conflicts"]), {"layer:a"})
        self.assertEqual(e.payload["conflicts"]["layer:a"]["rev"], 2)
        self.assertEqual(len(e.payload["conflicts"]["layer:a"]["value"]["data"]["fc"]["features"]), 1)
        self.assertEqual(self.push(3, {"layer:a": layer_section("a", "zzz")}, self.owner, "c2"), {"rev": 4})

    def test_conflict_is_all_or_nothing(self):
        self.push(1, {"layer:a": layer_section("a", "u1")})
        before = self.hub.get_project(self.owner, self.pid)
        with self.assertRaises(Conflict) as cm:
            self.push(1, {"layer:a": layer_section("a", "bad"), "layer:b": layer_section("b", "good"),
                          "layer:new": layer_section("new", "n")}, self.owner, "c2")
        self.assertEqual(set(cm.exception.payload["conflicts"]), {"layer:a"})
        after = self.hub.get_project(self.owner, self.pid)
        self.assertEqual(after, before)                                  # b и new не записаны
        self.assertNotIn("layer:new", after["sections"])
        self.assertEqual(after["rev"], 2)

    def test_delete_layer_leaves_tombstone(self):
        self.assertEqual(self.push(1, {"layer:b": None}), {"rev": 2})
        p = self.hub.get_project(self.owner, self.pid)
        self.assertNotIn("layer:b", p["sections"])
        self.assertEqual(p["sections"]["meta"]["current_order"], ["a"])       # порядок поправился сам
        self.assertEqual(p["sec_rev"]["layer:b"], 2)
        self.assertEqual(p["sec_rev"]["meta"], 2)
        with self.assertRaises(Conflict) as cm:                              # правка удалённого слоя отстаёт
            self.push(1, {"layer:b": layer_section("b", "u3", "u9")}, self.owner, "c2")
        self.assertIsNone(cm.exception.payload["conflicts"]["layer:b"]["value"])
        _, raw = self.hub.project_file(self.owner, self.pid)
        self.assertEqual([l["key"] for l in json.loads(raw)["layers"]], ["a"])

    def test_new_layer_is_appended_to_order(self):
        self.push(1, {"layer:c": layer_section("c", "q")})
        p = self.hub.get_project(self.owner, self.pid)
        self.assertEqual(p["sections"]["meta"]["current_order"], ["b", "a", "c"])
        self.assertEqual(p["sec_rev"]["meta"], 2)

    def test_push_meta_order_and_name_forced(self):
        meta = copy.deepcopy(self.hub.get_project(self.owner, self.pid)["sections"]["meta"])
        meta["current_order"] = ["a", "b"]
        meta["name"] = "подмена"
        meta["groups"] = []
        self.push(1, {"meta": meta})
        p = self.hub.get_project(self.owner, self.pid)
        self.assertEqual(p["sections"]["meta"]["current_order"], ["a", "b"])
        self.assertEqual((p["name"], p["sections"]["meta"]["name"], p["sections"]["meta"]["groups"]), ("Проект", "Проект", []))

    def test_validation(self):
        bad_sets = [
            {"nope": {}}, {"layer:": layer_section("a")}, {"layer:a b": layer_section("a")},
            {"layer:a\n": layer_section("a")}, {"layer:__proto__": layer_section("a")},
            {"layer:a": {"spec": {}}}, {"layer:a": "x"}, {"layer:a": {"spec": 1, "data": {}}},
            {"meta": None}, {"meta": []}, {"layer:" + "x" * 201: layer_section("x")}, [], None,
        ]
        for sections in bad_sets:
            with self.assertRaises(HubError) as cm:
                self.push(1, sections)
            self.assertEqual(cm.exception.status, 400, repr(sections)[:60])
        for base in (-1, 1.5, "1", None, True, 99):
            with self.assertRaises(HubError) as cm:
                self.push(base, {"layer:a": layer_section("a")})
            self.assertEqual(cm.exception.status, 400, repr(base))
        for client in ("", "bad client", None, "x" * 65):
            with self.assertRaises(HubError):
                self.push(1, {"layer:a": layer_section("a")}, client=client)
        nan = layer_section("a", "u1")
        nan["data"]["fc"]["features"][0]["properties"]["v"] = float("nan")
        with self.assertRaises(HubError) as cm:
            self.push(1, {"layer:a": nan})
        self.assertEqual(cm.exception.status, 400)
        self.assertEqual(self.hub.get_project(self.owner, self.pid)["rev"], 1)       # ничего не записано
        self.assertEqual(self.push(1, {}), {"rev": 1})                                # пустая запись — не ревизия

    def test_spec_key_forced_to_section_name(self):
        sec = layer_section("other")
        self.push(1, {"layer:c": sec})
        self.assertEqual(self.hub.get_project(self.owner, self.pid)["sections"]["layer:c"]["spec"]["key"], "c")

    def test_concurrent_pushes_serialize(self):
        results, errors = [], []

        def worker(i):
            try:
                results.append(self.hub.push(self.editor, self.pid, 1, {f"layer:w{i}": layer_section(f"w{i}", f"x{i}")}, f"c{i}")["rev"])
            except Exception as e:              # noqa: BLE001
                errors.append(e)
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(sorted(results), list(range(2, 10)))
        self.assertEqual(self.hub.get_project(self.owner, self.pid)["rev"], 9)

    def test_survives_restart(self):
        self.push(1, {"layer:a": layer_section("a", "u1", "after")})
        again = Hub(Path(self._tmp.name) / ".hub")
        p = again.get_project(self.owner, self.pid)
        self.assertEqual(p["rev"], 2)
        self.assertEqual(p["sections"]["layer:a"]["data"]["fc"]["features"][1]["properties"]["_uid"], "after")


class History(Base):
    def setUp(self):
        super().setUp()
        self.pid = self.new_project(sample_project())
        self.dir = Path(self._tmp.name) / ".hub" / "projects" / self.pid / "history"

    def test_snapshot_rule_one_per_ten_minutes(self):
        h, pid = self.hub, self.pid
        h.push(self.editor, pid, 1, {"layer:a": layer_section("a", "e1")}, "c")      # снимок ревизии 1
        self.assertEqual([s["rev"] for s in h.history(self.owner, pid)], [1])
        self.tick(60)
        h.push(self.editor, pid, 2, {"layer:a": layer_section("a", "e2")}, "c")      # в окне 10 минут: снимка нет
        self.assertEqual(len(h.history(self.owner, pid)), 1)
        self.tick(hub.HISTORY_INTERVAL)
        h.push(self.owner, pid, 3, {"layer:a": layer_section("a", "e3")}, "c")       # новый снимок — ревизия 3
        hist = h.history(self.owner, pid)
        self.assertEqual([(s["rev"], s["login"]) for s in hist], [(3, "editor"), (1, "owner")])
        self.assertTrue(all(s["size"] > 0 for s in hist))
        self.assertTrue(all(HISTORY_NAME.fullmatch(p.name) for p in self.dir.iterdir()))

    def test_restore_writes_new_revision_and_snapshots_before(self):
        h, pid = self.hub, self.pid
        h.push(self.editor, pid, 1, {"layer:a": layer_section("a", "v2"), "layer:c": layer_section("c", "only-later")}, "c")
        self.tick(hub.HISTORY_INTERVAL + 1)
        h.push(self.editor, pid, 2, {"layer:a": layer_section("a", "v3")}, "c")      # снимок ревизии 2
        # возврат к ревизии 2 (там a=v2 и есть слой c)
        self.assertEqual(h.restore(self.editor, pid, 2), {"rev": 4})
        p = h.get_project(self.owner, pid)
        self.assertEqual(p["rev"], 4)
        self.assertEqual(p["sections"]["layer:a"]["data"]["fc"]["features"][0]["properties"]["_uid"], "v2")
        self.assertIn("layer:c", p["sections"])
        self.assertTrue(all(r == 4 for n, r in p["sec_rev"].items() if n in ("layer:a", "layer:c", "layer:b", "meta")))
        self.assertIn(3, [s["rev"] for s in h.history(self.owner, pid)])              # снимок перед возвратом (ревизия 3)
        # возврат к ревизии 1 убирает слой c (раздел становится удалённым)
        h.restore(self.editor, pid, 1)
        p = h.get_project(self.owner, pid)
        self.assertNotIn("layer:c", p["sections"])
        self.assertEqual(p["sections"]["layer:a"]["data"]["fc"]["features"][0]["properties"]["_uid"], "u1")
        with self.assertRaises(HubError) as cm:
            h.restore(self.editor, pid, 999)
        self.assertEqual(cm.exception.status, 404)
        for bad in (-1, "1", None, True):
            with self.assertRaises(HubError):
                h.restore(self.editor, pid, bad)

    def test_restore_by_viewer_forbidden(self):
        self.hub.push(self.editor, self.pid, 1, {"layer:a": layer_section("a", "z")}, "c")
        with self.assertRaises(HubError) as cm:
            self.hub.restore(self.viewer, self.pid, 1)
        self.assertEqual(cm.exception.status, 403)

    def test_history_is_trimmed(self):
        h, pid = self.hub, self.pid
        for i in range(hub.HISTORY_KEEP + 5):
            self.tick(hub.HISTORY_INTERVAL + 1)
            h.push(self.editor, pid, i + 1, {"layer:a": layer_section("a", f"n{i}")}, "c")
        hist = h.history(self.owner, pid)
        self.assertEqual(len(hist), hub.HISTORY_KEEP)
        self.assertEqual(hist[0]["rev"], hub.HISTORY_KEEP + 5)            # остались самые новые

    def test_snapshot_is_gzipped_project(self):
        self.hub.push(self.editor, self.pid, 1, {"layer:a": layer_section("a", "z")}, "c")
        (snap,) = list(self.dir.iterdir())
        p = json.loads(gzip.decompress(snap.read_bytes()))
        self.assertEqual((p["format"], p["data"]["a"]["fc"]["features"][0]["properties"]["_uid"]), ("grado2", "u1"))

    def test_activity_feed(self):
        h, pid = self.hub, self.pid
        h.push(self.editor, pid, 1, {"layer:a": layer_section("a", "z")}, "c")
        h.add_comment(self.viewer, pid, "вопрос", {"lonlat": [1, 2]})
        acts = h.activity(self.owner, pid)
        self.assertEqual([a["action"] for a in acts][:2], ["comment", "push"])        # новые сверху
        self.assertEqual({"t", "login", "action", "detail"}, set(acts[0]))
        self.assertEqual(acts[-1]["action"], "create")


HISTORY_NAME = hub.HISTORY_RE


class Comments(Base):
    def setUp(self):
        super().setUp()
        self.pid = self.new_project()

    def test_crud(self):
        h, pid = self.hub, self.pid
        c = h.add_comment(self.viewer, pid, "  Здесь ошибка  ", {"lonlat": [37.6, 55.7]})
        self.assertEqual((c["author"], c["text"], c["resolved"], c["replies"], c["anchor"]),
                         ("viewer", "Здесь ошибка", False, [], {"lonlat": [37.6, 55.7]}))
        c2 = h.add_comment(self.editor, pid, "к объекту", {"layer": "a", "uid": "abc123"})
        self.assertEqual(len(h.comments(self.stranger_or_owner(), pid)), 2)
        r = h.reply(self.owner, pid, c["id"], "исправлю")
        self.assertEqual([x["author"] for x in r["replies"]], ["owner"])
        self.assertEqual(set(r["replies"][0]), {"id", "author", "created", "text"})
        u = h.update_comment(self.owner, pid, c["id"], resolved=True)            # владелец закрывает чужой
        self.assertTrue(u["resolved"])
        u = h.update_comment(self.viewer, pid, c["id"], text="Поправил текст", resolved=False)
        self.assertEqual((u["text"], u["resolved"]), ("Поправил текст", False))
        h.delete_comment(self.viewer, pid, c["id"])                               # автор удаляет своё
        h.delete_comment(self.owner, pid, c2["id"])                               # владелец удаляет чужое
        self.assertEqual(h.comments(self.owner, pid), [])

    def stranger_or_owner(self):
        return self.owner

    def test_permissions(self):
        h, pid = self.hub, self.pid
        c = h.add_comment(self.editor, pid, "мой", {"lonlat": [1, 2]})
        with self.assertRaises(HubError) as cm:                                   # чужой текст править нельзя
            h.update_comment(self.viewer, pid, c["id"], text="подмена")
        self.assertEqual(cm.exception.status, 403)
        with self.assertRaises(HubError) as cm:
            h.delete_comment(self.viewer, pid, c["id"])
        self.assertEqual(cm.exception.status, 403)
        h.update_comment(self.viewer, pid, c["id"], resolved=True)                # а закрыть — можно
        for fn in (lambda: h.comments(self.stranger, pid), lambda: h.add_comment(self.stranger, pid, "x", {"lonlat": [1, 2]}),
                   lambda: h.reply(self.stranger, pid, c["id"], "x"), lambda: h.delete_comment(self.stranger, pid, c["id"])):
            with self.assertRaises(HubError) as cm:
                fn()
            self.assertEqual(cm.exception.status, 403)
        h.delete_comment(self.admin, pid, c["id"])

    def test_validation(self):
        h, pid = self.hub, self.pid
        good = {"lonlat": [1, 2]}
        bad_text = ["", "   ", None, 5, "я" * (hub.COMMENT_MAX + 1)]
        for t in bad_text:
            with self.assertRaises(HubError):
                h.add_comment(self.owner, pid, t, good)
        h.add_comment(self.owner, pid, "я" * hub.COMMENT_MAX, good)
        bad_anchor = [None, {}, {"lonlat": [1]}, {"lonlat": [float("nan"), 1]}, {"lonlat": ["a", 1]}, {"lonlat": [1, 2], "x": 1},
                      {"lonlat": [1, 95]}, {"layer": "a"}, {"layer": "a b", "uid": "x"}, {"layer": "a", "uid": ""},
                      {"layer": "a", "uid": 5}, "lonlat", [1, 2], {"lonlat": [True, 1]}]
        for a in bad_anchor:
            with self.assertRaises(HubError, msg=repr(a)):
                h.add_comment(self.owner, pid, "x", a)
        with self.assertRaises(HubError) as cm:
            h.update_comment(self.owner, pid, "nope", text="x")
        self.assertEqual(cm.exception.status, 404)
        c = h.comments(self.owner, pid)[0]
        with self.assertRaises(HubError):
            h.update_comment(self.owner, pid, c["id"])
        with self.assertRaises(HubError):
            h.update_comment(self.owner, pid, c["id"], resolved="yes")

    def test_persist_and_event(self):
        h, pid = self.hub, self.pid
        sub = h.subscribe(self.owner, pid)
        self.assertEqual(sub.get(0)["type"], "presence")
        c = h.add_comment(self.editor, pid, "событие", {"lonlat": [1, 2]})
        ev = sub.get(1)
        self.assertEqual((ev["type"], ev["rev_c"]), ("comments", 1))
        h.update_comment(self.owner, pid, c["id"], resolved=True)
        h.reply(self.owner, pid, c["id"], "ответ")
        self.assertEqual(sub.get(1)["rev_c"], 3)                      # подряд идущие comments склеены
        self.assertIsNone(sub.get(0))
        again = Hub(Path(self._tmp.name) / ".hub")
        self.assertEqual(again.comments(self.owner, pid)[0]["text"], "событие")
        sub.close()


class Presence(Base):
    def setUp(self):
        super().setUp()
        self.pid = self.new_project()

    def users(self, sub_or_none=None):
        sub = self.hub.subscribe(self.owner, self.pid)
        try:
            return sub.get(0)["users"]
        finally:
            sub.close()

    def test_entry_fields_ttl_and_colour(self):
        h, pid = self.hub, self.pid
        h.presence(self.editor, pid, "cE", [37.6, 55.7], "a", ["u1", "u2"])
        h.presence(self.viewer, pid, "cV", None, None, [])
        us = {u["login"]: u for u in self.users()}
        self.assertEqual(set(us), {"editor", "viewer"})
        e = us["editor"]
        self.assertEqual((e["name"], e["client"], e["cursor"], e["layer"], e["sel"]), ("Редактор", "cE", [37.6, 55.7], "a", ["u1", "u2"]))
        self.assertIn(e["color"], hub.PALETTE)
        self.assertEqual(e["color"], hub._color("editor"))
        self.assertEqual(hub._color("editor"), hub._color("editor"))
        self.assertEqual(self.hub._online_count(pid), 2)
        self.assertEqual(h.list_projects(self.owner)[0]["online"], 2)
        self.tick(hub.PRESENCE_TTL - 1)
        h.presence(self.editor, pid, "cE", None, None, [])            # editor обновился, viewer — нет
        self.tick(2)
        self.assertEqual([u["login"] for u in self.users()], ["editor"])
        self.tick(hub.PRESENCE_TTL + 1)
        self.assertEqual(self.users(), [])
        self.assertEqual(h.list_projects(self.owner)[0]["online"], 0)

    def test_colours_come_from_palette_and_spread(self):
        colours = {hub._color(f"user{i}") for i in range(60)}
        self.assertTrue(colours <= set(hub.PALETTE) and len(colours) >= 6)
        self.assertEqual(len(hub.PALETTE), 8)

    def test_broadcast_throttle_two_per_second(self):
        h, pid = self.hub, self.pid
        sub = h.subscribe(self.owner, pid)
        sub.get(0)                                                     # стартовый снимок
        seen = []

        def drain():
            while (ev := sub.get(0)) is not None:
                seen.append(ev)
        for i in range(10):                                            # десять обновлений за одну секунду
            h.presence(self.editor, pid, "cE", [float(i), 1.0], None, [])
            self.tick(0.1)
            drain()
        self.assertLessEqual(len(seen), 2 + 1)
        self.assertTrue(seen and seen[-1]["type"] == "presence")
        self.tick(1)
        drain()                                                        # отложенное (dirty) уходит на шаге ожидания
        self.assertEqual(seen[-1]["users"][0]["cursor"], [9.0, 1.0])
        sub.close()

    def test_validation(self):
        h, pid = self.hub, self.pid
        good = dict(client="c1", cursor=[1.0, 2.0], layer="a", sel=["u1"])
        h.presence(self.editor, pid, **good)
        bad = [dict(client="bad client"), dict(client=""), dict(cursor=[1.0]), dict(cursor=[float("nan"), 1.0]),
               dict(cursor=[float("inf"), 1.0]), dict(cursor="x"), dict(cursor=[True, 1]), dict(cursor=[1, 99]),
               dict(layer="a b"), dict(layer=5), dict(sel="u1"), dict(sel=[1]), dict(sel=["x" * 65]),
               dict(sel=["u"] * (hub.SEL_MAX + 1)), dict(sel=[""])]
        for patch in bad:
            with self.assertRaises(HubError, msg=repr(patch)):
                h.presence(self.editor, pid, **{**good, **patch})
        h.presence(self.editor, pid, **{**good, "sel": ["u"] * hub.SEL_MAX})        # граница допустима
        h.presence(self.editor, pid, "c1", None, None, None)

    def test_subscribe_sees_current_users(self):
        self.hub.presence(self.editor, self.pid, "cE", None, None, [])
        sub = self.hub.subscribe(self.viewer, self.pid)
        ev = sub.get(0)
        self.assertEqual([u["login"] for u in ev["users"]], ["editor"])
        sub.close()

    def test_expiry_publishes_to_waiting_subscriber(self):
        h, pid = self.hub, self.pid
        h.presence(self.editor, pid, "cE", None, None, [])
        sub = h.subscribe(self.owner, pid)
        sub.get(0)
        self.tick(hub.PRESENCE_TTL + 1)
        ev = sub.get(1)                                               # шаг ожидания замечает просрочку
        self.assertEqual((ev["type"], ev["users"]), ("presence", []))
        sub.close()


class Events(Base):
    def setUp(self):
        super().setUp()
        self.pid = self.new_project(sample_project())

    def test_rev_event_across_threads(self):
        h, pid = self.hub, self.pid
        got = []
        sub = h.subscribe(self.viewer, pid)
        self.assertEqual(sub.get(0)["type"], "presence")

        def reader():
            got.append(sub.get(5))
        t = threading.Thread(target=reader)
        t.start()
        time.sleep(0.1)
        h.push(self.editor, pid, 1, {"layer:a": layer_section("a", "e1"), "layer:b": None}, "tab-7")
        t.join(6)
        self.assertEqual(got[0], {"type": "rev", "rev": 2, "sections": ["layer:a", "layer:b", "meta"], "by": "editor", "client": "tab-7"})
        sub.close()

    def test_presence_event_across_threads(self):
        h, pid = self.hub, self.pid
        sub = h.subscribe(self.owner, pid)
        sub.get(0)
        out = []
        t = threading.Thread(target=lambda: out.append(sub.get(5)))
        t.start()
        time.sleep(0.1)
        h.presence(self.editor, pid, "cE", [1.0, 2.0], "a", ["u1"])
        t.join(6)
        self.assertEqual(out[0]["type"], "presence")
        self.assertEqual(out[0]["users"][0]["login"], "editor")
        sub.close()

    def test_get_timeout_returns_none(self):
        sub = self.hub.subscribe(self.owner, self.pid)
        sub.get(0)
        start = time.monotonic()
        self.assertIsNone(sub.get(0.2))
        self.assertLess(time.monotonic() - start, 2)
        sub.close()

    def test_deleted_event_then_closed(self):
        h, pid = self.hub, self.pid
        subs = [h.subscribe(self.editor, pid), h.subscribe(self.viewer, pid)]
        for s in subs:
            s.get(0)
        h.delete_project(self.owner, pid)
        for s in subs:
            self.assertEqual(s.get(1), {"type": "deleted"})
            self.assertTrue(s.closed)
            self.assertIsNone(s.get(0.1))

    def test_removed_member_subscription_closes(self):
        h, pid = self.hub, self.pid
        mine, other = h.subscribe(self.viewer, pid), h.subscribe(self.editor, pid)
        mine.get(0), other.get(0)
        h.set_member(self.owner, pid, "viewer", None)
        self.assertEqual(mine.get(1), {"type": "members"})
        self.assertTrue(mine.closed)
        self.assertEqual(other.get(1), {"type": "members"})
        self.assertFalse(other.closed)
        with self.assertRaises(HubError):
            h.subscribe(self.viewer, pid)
        other.close()

    def test_disabled_user_subscription_closes(self):
        sub = self.hub.subscribe(self.viewer, self.pid)
        self.hub.update_user(self.admin, "viewer", disabled=True)
        self.assertTrue(sub.closed)

    def test_members_event_and_no_leak_between_projects(self):
        h = self.hub
        other = self.new_project()
        sub_a, sub_b = h.subscribe(self.owner, self.pid), h.subscribe(self.owner, other)
        sub_a.get(0), sub_b.get(0)
        h.set_member(self.owner, self.pid, "stranger", "viewer")
        self.assertEqual(sub_a.get(1), {"type": "members"})
        self.assertIsNone(sub_b.get(0))
        sub_a.close(), sub_b.close()

    def test_close_unregisters(self):
        sub = self.hub.subscribe(self.owner, self.pid)
        sub.close()
        self.assertTrue(sub.closed)
        self.assertNotIn(self.pid, self.hub._subs)

    def test_overflow_coalesces_revs_and_stays_bounded(self):
        h, pid = self.hub, self.pid
        sub = h.subscribe(self.owner, pid)
        sub.get(0)
        rev = 1
        for i in range(hub.QUEUE_MAX + 60):
            h.push(self.editor, pid, rev, {f"layer:n{i % 40}": layer_section(f"n{i % 40}", f"x{i}")}, "c%d" % (i % 2))
            rev += 1
        self.assertLessEqual(len(sub._q), hub.QUEUE_MAX)
        events = []
        while (ev := sub.get(0)) is not None:
            events.append(ev)
        self.assertEqual(events[-1]["rev"], rev)                        # последняя ревизия не потеряна
        merged = [e for e in events if e["type"] == "rev" and len(e["sections"]) > 1]
        self.assertTrue(merged)
        self.assertIsNone(merged[0]["client"])                           # слиты события разных клиентов
        sub.close()

    def test_coalesce_unit(self):
        sub = hub.Subscription(self.hub, self.pid, "owner")
        for i in range(hub.QUEUE_MAX):
            sub._put({"type": "rev", "rev": i, "sections": [f"layer:{i % 3}"], "by": "x", "client": "c"})
        sub._put({"type": "rev", "rev": 500, "sections": ["meta"], "by": "y", "client": "c"})
        self.assertLess(len(sub._q), 5)
        merged, last = sub._q[0], sub._q[-1]
        self.assertEqual((last["rev"], last["by"]), (500, "y"))
        self.assertEqual((merged["rev"], merged["sections"]), (hub.QUEUE_MAX - 1, ["layer:0", "layer:1", "layer:2"]))


class Teams(Base):
    """Команды (рабочие пространства): роли, проекты команды, перенос, рассылка изменений доступа."""

    def setUp(self):
        super().setUp()
        self.tid = self.hub.create_team(self.owner, "Отдел")["id"]
        self.hub.set_team_member(self.owner, self.tid, "editor", "member")

    def team_project(self, access="edit"):
        return self.hub.create_project(self.owner, "Командный", None, self.tid, access)["id"]

    def status(self, fn):
        with self.assertRaises(HubError) as c:
            fn()
        return c.exception.status

    def test_create_list_rename(self):
        h = self.hub
        self.assertRegex(self.tid, r"^[0-9a-f]{16}$")
        blank = h.create_team(self.owner, "   ")["id"]
        mine = {t["id"]: t for t in h.list_teams(self.owner)}
        self.assertEqual(mine[blank]["name"], "Новая команда")
        self.assertEqual(mine[self.tid]["name"], "Отдел")
        self.assertEqual(mine[self.tid]["role"], "owner")
        self.assertEqual(mine[self.tid]["members"], [{"login": "editor", "name": "Редактор", "role": "member"},
                                                    {"login": "owner", "name": "Владелец", "role": "owner"}])
        self.assertEqual(mine[self.tid]["projects"], 0)
        self.team_project()
        got = h.list_teams(self.editor)
        self.assertEqual((len(got), got[0]["role"], got[0]["projects"]), (1, "member", 1))
        self.assertEqual(h.list_teams(self.stranger), [])
        self.assertEqual(h.rename_team(self.owner, self.tid, "  Новый   отдел "), "Новый отдел")
        self.assertEqual(h.list_teams(self.editor)[0]["name"], "Новый отдел")
        for bad in ("", "   ", None):
            self.assertEqual(self.status(lambda: h.rename_team(self.owner, self.tid, bad)), 400)
        self.assertEqual(self.status(lambda: h.rename_team(self.editor, self.tid, "Взлом")), 403)
        self.assertEqual(Hub(h.root).teams[self.tid]["name"], "Новый отдел")      # команды лежат на диске

    def test_admin_sees_all_teams_as_admin(self):
        t = [t for t in self.hub.list_teams(self.admin) if t["id"] == self.tid]
        self.assertEqual(t[0]["role"], "admin")
        self.hub.rename_team(self.admin, self.tid, "От админа")
        self.hub.set_team_member(self.admin, self.tid, "viewer", "member")

    def test_unknown_team_is_404(self):
        h = self.hub
        for tid in ("0" * 16, "xx", None, 5):
            self.assertEqual(self.status(lambda: h.rename_team(self.owner, tid, "x")), 404)
        self.assertEqual(self.status(lambda: h.set_team_member(self.owner, "0" * 16, "viewer", "member")), 404)
        self.assertEqual(self.status(lambda: h.delete_team(self.owner, "0" * 16)), 404)

    def test_member_add_change_remove(self):
        h = self.hub
        res = h.set_team_member(self.owner, self.tid, "viewer", "member")
        self.assertEqual([m["login"] for m in res], ["editor", "owner", "viewer"])
        res = h.set_team_member(self.owner, self.tid, "viewer", "owner")
        self.assertEqual({m["login"]: m["role"] for m in res}["viewer"], "owner")
        res = h.set_team_member(self.owner, self.tid, "viewer", None)
        self.assertEqual([m["login"] for m in res], ["editor", "owner"])
        self.assertEqual(h.list_teams(self.viewer), [])

    def test_leave(self):
        h = self.hub
        h.set_team_member(self.editor, self.tid, "editor", None)
        self.assertEqual(h.list_teams(self.editor), [])
        self.assertEqual(self.status(lambda: h.set_team_member(self.stranger, self.tid, "owner", None)), 403)

    def test_member_cannot_manage(self):
        h = self.hub
        for call in (lambda: h.set_team_member(self.editor, self.tid, "viewer", "member"),
                     lambda: h.set_team_member(self.editor, self.tid, "owner", None),
                     lambda: h.set_team_member(self.editor, self.tid, "editor", "owner"),
                     lambda: h.delete_team(self.editor, self.tid),
                     lambda: h.set_team_member(self.stranger, self.tid, "stranger", "owner")):
            self.assertEqual(self.status(call), 403)

    def test_last_owner_protected(self):
        h = self.hub
        for call in (lambda: h.set_team_member(self.owner, self.tid, "owner", None),
                     lambda: h.set_team_member(self.owner, self.tid, "owner", "member")):
            with self.assertRaises(HubError) as c:
                call()
            self.assertEqual(c.exception.status, 400)
            self.assertIn("владелец", c.exception.message)
        h.set_team_member(self.owner, self.tid, "editor", "owner")
        h.set_team_member(self.owner, self.tid, "owner", None)    # теперь можно: владелец остаётся
        self.assertEqual(h.list_teams(self.editor)[0]["role"], "owner")

    def test_unknown_user_404_and_bad_role(self):
        h = self.hub
        self.assertEqual(self.status(lambda: h.set_team_member(self.owner, self.tid, "nobody", "member")), 404)
        self.assertEqual(self.status(lambda: h.set_team_member(self.owner, self.tid, "viewer", "editor")), 400)

    def test_caps(self):
        h = self.hub
        old = hub.TEAM_MEMBERS_MAX
        hub.TEAM_MEMBERS_MAX = 3
        self.addCleanup(setattr, hub, "TEAM_MEMBERS_MAX", old)
        h.set_team_member(self.owner, self.tid, "viewer", "member")
        self.assertEqual(self.status(lambda: h.set_team_member(self.owner, self.tid, "stranger", "member")), 400)
        h.set_team_member(self.owner, self.tid, "viewer", "owner")        # смена роли у своего — не новый участник
        old = hub.TEAMS_PER_USER
        hub.TEAMS_PER_USER = 2
        self.addCleanup(setattr, hub, "TEAMS_PER_USER", old)
        h.create_team(self.owner, "Вторая")
        self.assertEqual(self.status(lambda: h.create_team(self.owner, "Третья")), 400)

    def test_team_project_roles(self):
        h = self.hub
        pid = self.team_project()
        self.assertEqual(h.role_of(self.editor, pid), "editor")
        self.assertEqual(h.role_of(self.owner, pid), "owner")
        self.assertIsNone(h.role_of(self.stranger, pid))
        row = [p for p in h.list_projects(self.editor) if p["id"] == pid][0]
        self.assertEqual((row["team"], row["team_name"], row["team_access"], row["role"]),
                         (self.tid, "Отдел", "edit", "editor"))
        self.assertEqual(h.get_project(self.editor, pid)["role"], "editor")
        h.push(self.editor, pid, 1, {"meta": {"name": "x"}}, "c1")       # редактор команды правит
        view = self.team_project("view")
        self.assertEqual(h.role_of(self.editor, view), "viewer")
        self.assertEqual(self.status(lambda: h.push(self.editor, view, 1, {"meta": {"name": "x"}}, "c1")), 403)
        none = self.team_project("none")
        self.assertIsNone(h.role_of(self.editor, none))
        self.assertNotIn(none, [p["id"] for p in h.list_projects(self.editor)])
        self.assertEqual(self.status(lambda: h.get_project(self.editor, none)), 403)
        h.set_team_member(self.owner, self.tid, "viewer", "owner")        # владелец команды — владелец проекта
        self.assertEqual(h.role_of(self.viewer, none), "owner")
        self.assertEqual(h.role_of(self.viewer, pid), "owner")

    def test_personal_share_for_guest_and_strongest_wins(self):
        h = self.hub
        pid = self.team_project("view")
        h.set_member(self.owner, pid, "stranger", "viewer")
        self.assertEqual(h.role_of(self.stranger, pid), "viewer")
        row = [p for p in h.list_projects(self.stranger) if p["id"] == pid][0]
        self.assertEqual(row["team"], self.tid)
        h.set_member(self.owner, pid, "editor", "editor")                # команда смотрит, лично правит
        self.assertEqual(h.role_of(self.editor, pid), "editor")
        pid2 = self.team_project("edit")
        h.set_member(self.owner, pid2, "editor", "viewer")               # команда правит, лично смотрит
        self.assertEqual(h.role_of(self.editor, pid2), "editor")

    def test_create_project_in_foreign_team_forbidden(self):
        h = self.hub
        self.assertEqual(self.status(lambda: h.create_project(self.stranger, "Чужой", None, self.tid)), 403)
        self.assertEqual(self.status(lambda: h.create_project(self.owner, "Плохой", None, self.tid, "all")), 400)
        self.assertEqual(self.status(lambda: h.create_project(self.owner, "Нет", None, "0" * 16)), 404)
        pid = h.create_project(self.admin, "От админа", None, self.tid)["id"]      # администратору можно
        self.assertEqual(h._meta(pid)["team"], self.tid)
        pid = h.create_project(self.editor, "От участника", None, self.tid)["id"]
        self.assertEqual(h.role_of(self.editor, pid), "owner")
        self.assertEqual(h.role_of(self.owner, pid), "owner")             # владелец команды — владелец проекта
        personal = h.create_project(self.owner, "Личный")["id"]
        row = [p for p in h.list_projects(self.owner) if p["id"] == personal][0]
        self.assertEqual((row["team"], row["team_name"], row["team_access"]), (None, None, "edit"))

    def test_set_project_team_in_and_out(self):
        h = self.hub
        pid = h.create_project(self.editor, "Личный")["id"]
        self.assertIsNone(h.role_of(self.owner, pid))
        self.assertEqual(h.set_project_team(self.editor, pid, self.tid, "view"), {"team": self.tid, "team_access": "view"})
        self.assertEqual(h.role_of(self.owner, pid), "owner")             # владелец команды
        self.assertEqual(h.activity(self.editor, pid)[0]["action"], "team")
        self.assertEqual(h.set_project_team(self.editor, pid, self.tid, "edit")["team_access"], "edit")
        # наружу: личный владелец остаётся, второго не добавляется
        self.assertEqual(h.set_project_team(self.editor, pid, None, "view"), {"team": None, "team_access": "edit"})
        self.assertIsNone(h.role_of(self.owner, pid))
        self.assertEqual(h._meta(pid)["members"], {"editor": "owner"})
        # проект, где личного владельца нет: переносящий становится им
        pid2 = self.team_project()
        h.set_member(self.owner, pid2, "owner", None)                     # допустимо: владелец команды остаётся
        self.assertEqual(h._meta(pid2)["members"], {})
        h.set_project_team(self.owner, pid2, None, "edit")
        self.assertEqual(h._meta(pid2)["members"], {"owner": "owner"})
        self.assertIsNone(h.role_of(self.editor, pid2))

    def test_set_project_team_permissions(self):
        h = self.hub
        pid = self.team_project()
        self.assertEqual(self.status(lambda: h.set_project_team(self.editor, pid, None, "edit")), 403)
        mine = h.create_project(self.stranger, "Мой")["id"]
        self.assertEqual(self.status(lambda: h.set_project_team(self.stranger, mine, self.tid, "edit")), 403)
        self.assertEqual(self.status(lambda: h.set_project_team(self.stranger, mine, "0" * 16, "edit")), 404)
        self.assertEqual(self.status(lambda: h.set_project_team(self.owner, pid, self.tid, "all")), 400)

    def test_set_member_last_owner_counts_team_owners(self):
        h = self.hub
        pid = self.team_project()
        h.set_member(self.owner, pid, "editor", "owner")
        h.set_member(self.owner, pid, "owner", "viewer")                  # личный владелец остаётся — editor
        self.assertEqual(h._meta(pid)["owner"], "editor")
        h.set_member(self.owner, pid, "editor", "viewer")                 # личных нет, но владелец команды есть
        self.assertEqual(h._meta(pid)["owner"], "editor")                 # квота остаётся на прежнем
        self.assertEqual(h.role_of(self.owner, pid), "owner")
        bare = h.create_project(self.owner, "Личный")["id"]
        self.assertEqual(self.status(lambda: h.set_member(self.owner, bare, "owner", None)), 400)

    def test_delete_team(self):
        h = self.hub
        pid = self.team_project()
        with self.assertRaises(HubError) as c:
            h.delete_team(self.owner, self.tid)
        self.assertEqual((c.exception.status, c.exception.message),
                         (400, "в команде есть проекты: перенесите или удалите их"))
        h.delete_project(self.owner, pid)
        h.delete_team(self.owner, self.tid)
        self.assertEqual(h.list_teams(self.owner), [])
        self.assertEqual(self.status(lambda: h.delete_team(self.owner, self.tid)), 404)

    def test_old_meta_without_team_is_personal(self):
        h = self.hub
        pid = h.create_project(self.owner, "Старый")["id"]
        meta = h._meta(pid)
        meta.pop("team"), meta.pop("team_access")
        h._save_meta(pid, meta)
        self.assertNotIn("team", h._meta(pid))
        self.assertEqual(h.role_of(self.owner, pid), "owner")
        self.assertIsNone(h.role_of(self.editor, pid))
        row = [p for p in h.list_projects(self.owner) if p["id"] == pid][0]
        self.assertEqual((row["team"], row["team_name"], row["team_access"]), (None, None, "edit"))
        h.set_member(self.owner, pid, "viewer", "viewer")
        self.assertEqual(h.role_of(self.viewer, pid), "viewer")

    def test_deleted_team_gives_no_role(self):
        h = self.hub
        pid = self.team_project()
        del h.teams[self.tid]                                             # битая ссылка на команду: личные роли целы
        self.assertIsNone(h.role_of(self.editor, pid))
        self.assertEqual(h.role_of(self.owner, pid), "owner")
        row = [p for p in h.list_projects(self.owner) if p["id"] == pid][0]
        self.assertIsNone(row["team"])

    def test_disabled_user_has_no_team_role(self):
        h = self.hub
        pid = self.team_project()
        h.update_user(self.admin, "editor", disabled=True)
        self.assertIsNone(h.role_of(self.editor, pid))

    def test_removed_member_streams_close_on_every_team_project(self):
        h = self.hub
        p1, p2, p3 = self.team_project(), self.team_project(), self.team_project()
        other = h.create_project(self.owner, "Не командный")["id"]
        h.set_member(self.owner, other, "editor", "editor")
        subs = [h.subscribe(self.editor, p) for p in (p1, p2, p3)]
        keep = h.subscribe(self.owner, p1)
        elsewhere = h.subscribe(self.editor, other)
        for s in subs + [keep, elsewhere]:
            s.get(0)
        h.set_team_member(self.owner, self.tid, "editor", None)
        for s in subs:
            self.assertEqual(s.get(1), {"type": "members"})
            self.assertTrue(s.closed)
        self.assertEqual(keep.get(1), {"type": "members"})
        self.assertFalse(keep.closed)
        self.assertFalse(elsewhere.closed)
        self.assertIsNone(elsewhere.get(0))
        self.assertEqual(self.status(lambda: h.subscribe(self.editor, p1)), 403)
        keep.close(), elsewhere.close()

    def test_access_change_propagates(self):
        h = self.hub
        pid = self.team_project()
        sub = h.subscribe(self.editor, pid)
        sub.get(0)
        h.set_team_member(self.owner, self.tid, "viewer", "member")      # новый человек: событие, поток остаётся
        self.assertEqual(sub.get(1), {"type": "members"})
        self.assertFalse(sub.closed)
        h.set_project_team(self.owner, pid, self.tid, "none")            # доступ команды снят: поток закрыт
        self.assertEqual(sub.get(1), {"type": "members"})
        self.assertTrue(sub.closed)
        owner_sub = h.subscribe(self.owner, pid)
        owner_sub.get(0)
        h.set_project_team(self.owner, pid, None, "edit")                # вышел из команды наружу: владелец проекта
        self.assertEqual(owner_sub.get(1), {"type": "members"})
        self.assertFalse(owner_sub.closed)
        owner_sub.close()

    def test_review_fixes_access_owner_and_streams(self):
        h = self.hub
        pid = self.team_project("view")
        # доступ команды не указан: в той же команде не меняется, при переезде в другую — «правит»
        self.assertEqual(h.set_project_team(self.owner, pid, self.tid, None)["team_access"], "view")
        other = h.create_team(self.owner, "Второй")["id"]
        self.assertEqual(h.set_project_team(self.owner, pid, other, None)["team_access"], "edit")
        h.set_project_team(self.owner, pid, self.tid, "view")
        # снятие личной роли не рвёт поток, если доступ остался через команду
        h.set_member(self.owner, pid, "editor", "editor")
        sub = h.subscribe(self.editor, pid)
        sub.get(0)
        h.set_member(self.owner, pid, "editor", None)
        self.assertEqual(sub.get(1), {"type": "members"})
        self.assertFalse(sub.closed)
        self.assertEqual(h.role_of(self.editor, pid), "viewer")
        sub.close()
        # перенос в личные: если создателя в проекте уже нет, владельцем записывается переносящий
        h.set_team_member(self.owner, self.tid, "editor", "owner")
        h.set_member(self.owner, pid, "owner", None)
        h.set_project_team(self.editor, pid, None, None)
        meta = h._meta(pid)
        self.assertEqual((meta["members"], meta["owner"]), ({"editor": "owner"}, "editor"))

    def test_teams_file_is_resynced_from_disk(self):
        other = Hub(self.hub.root)                                        # второй процесс (CLI) правит teams.json
        tid2 = other.create_team(self.stranger, "Из другого процесса")["id"]
        self.assertIn(tid2, [t["id"] for t in self.hub.list_teams(self.stranger)])

    def test_adding_to_team_respects_per_user_cap(self):
        h = self.hub
        old = hub.TEAMS_PER_USER
        hub.TEAMS_PER_USER = 1
        self.addCleanup(setattr, hub, "TEAMS_PER_USER", old)
        h.create_team(self.stranger, "Своя")
        self.assertEqual(self.status(lambda: h.set_team_member(self.owner, self.tid, "stranger", "member")), 400)

    def test_cli_list_prints_teams(self):
        import contextlib
        import io
        import os
        from unittest import mock
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"GRADO2_HUB_DIR": str(self.hub.root)}), contextlib.redirect_stdout(buf):
            self.assertEqual(hub.main(["list"]), 0)
        self.assertIn(f"команда {self.tid}\tОтдел\tучастников 2", buf.getvalue())


class Hardening(Base):
    """Проверки по разбору безопасности: сессии, лимиты, квоты, общие файлы с командной строкой."""

    def setUp(self):
        super().setUp()
        self.pid = self.new_project(sample_project())

    def patch(self, **kw):
        for k, v in kw.items():
            old = getattr(hub, k)
            setattr(hub, k, v)
            self.addCleanup(setattr, hub, k, old)

    # ----- аккаунты -----

    def test_password_change_kills_other_sessions_but_keeps_current(self):
        t1, _ = self.hub.login("owner", PW, "1.1.1.1")
        t2, _ = self.hub.login("owner", PW, "1.1.1.2")
        other, _ = self.hub.login("editor", PW, "1.1.1.3")
        self.hub.change_password(self.hub.session_user(t1), PW, "brand-new-pw", keep_token=t1)
        self.assertIsNotNone(self.hub.session_user(t1))
        self.assertIsNone(self.hub.session_user(t2))                       # украденная сессия не переживает смену пароля
        self.assertIsNotNone(self.hub.session_user(other))                 # чужие входы не задеты
        self.hub.change_password(self.hub.session_user(t1), "brand-new-pw", "newer-pw-123")
        self.assertIsNone(self.hub.session_user(t1))                       # без keep_token гаснут все

    def test_wrong_old_password_is_throttled_and_right_one_not_counted(self):
        t, _ = self.hub.login("owner", PW, "1.1.1.1")
        u = self.hub.session_user(t)
        for _ in range(hub.LOGIN_FAILS):
            with self.assertRaises(HubError) as cm:
                self.hub.change_password(u, "wrong-wrong", "other-pw-123", keep_token=t)
            self.assertEqual(cm.exception.status, 401)
        with self.assertRaises(HubError) as cm:
            self.hub.change_password(u, PW, "other-pw-123", keep_token=t)
        self.assertEqual(cm.exception.status, 429)

    def test_parallel_login_burst_cannot_beat_the_limit(self):
        real = Hub._password_ok
        gate = threading.Barrier(12)

        def slow(u, pw):
            time.sleep(0.05)                                                # scrypt занимает время: все запросы успевают пройти проверку лимита
            return real(u, pw)
        Hub._password_ok = staticmethod(slow)
        self.addCleanup(setattr, Hub, "_password_ok", staticmethod(real))
        results = []

        def attempt():
            gate.wait()
            try:
                self.hub.login("owner", "wrong-password", "4.4.4.4")
                results.append(200)
            except HubError as e:
                results.append(e.status)
        ts = [threading.Thread(target=attempt) for _ in range(12)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(results.count(401), hub.LOGIN_FAILS)               # не больше пяти проверок пароля
        self.assertEqual(results.count(429), 12 - hub.LOGIN_FAILS)

    def test_successful_logins_do_not_fill_the_ip_counter(self):
        for _ in range(hub.IP_FAILS + 5):
            self.hub.login("owner", PW, "3.3.3.3")
        with self.assertRaises(HubError) as cm:                             # а одна неудача считается
            self.hub.login("owner", "wrong-password", "3.3.3.3")
        self.assertEqual(cm.exception.status, 401)

    def test_sessions_per_user_are_capped(self):
        self.patch(SESSIONS_PER_USER=3)
        tokens = [self.hub.login("owner", PW, "1.1.1.1")[0] for _ in range(5)]
        alive = [t for t in tokens if self.hub.session_user(t)]
        self.assertEqual(alive, tokens[-3:])                                # вытесняются старейшие
        self.assertIsNotNone(self.hub.session_user(self.hub.login("editor", PW, "1.1.1.1")[0]))

    def test_invites_are_capped_and_old_ones_pruned(self):
        self.patch(INVITES_MAX=3)
        codes = [self.hub.create_invite(self.admin) for _ in range(3)]
        with self.assertRaises(HubError) as cm:
            self.hub.create_invite(self.admin)
        self.assertEqual(cm.exception.status, 400)
        self.tick(hub.INVITE_TTL + 31 * 24 * 3600)                         # все просрочены давно: вычищаются, место освободилось
        self.hub.create_invite(self.admin)
        self.assertEqual(len(self.hub.invites), 1)
        self.assertNotIn(codes[0], self.hub.invites)

    def test_cli_changes_are_seen_by_running_hub(self):
        """hub.py adduser/passwd/invite — другой процесс (тут: второй экземпляр) на тех же файлах."""
        root = Path(self._tmp.name) / ".hub"
        token, _ = self.hub.login("owner", PW, "1.1.1.1")
        cli = Hub(root)
        cli.create_user("newcomer", PW, "Новенький")
        cli.set_password("owner", "reset-by-cli-1")
        code = cli._new_invite("cli")
        self.assertEqual(self.hub.login("newcomer", PW, "1.1.1.1")[1]["login"], "newcomer")      # работающий хаб видит нового
        self.assertIsNone(self.hub.session_user(token))                     # и сброс входов после passwd
        self.assertEqual(self.hub.login("owner", "reset-by-cli-1", "1.1.1.1")[1]["login"], "owner")
        self.assertEqual(self.hub.register(code, "viainvite", "", PW, "1.1.1.1")[1]["login"], "viainvite")
        # запись сервера не стирает пользователя, добавленного из командной строки
        self.assertEqual({"newcomer", "viainvite", "owner"} <= set(json.loads((root / "users.json").read_text("utf-8"))), True)
        with self.assertRaises(HubError):
            cli.login("owner", PW, "9.9.9.9")                               # и командная строка видит пароль, сменённый сервером

    def test_corrupt_users_file_during_sync_keeps_old_data(self):
        root = Path(self._tmp.name) / ".hub"
        (root / "users.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(self.hub.login("owner", PW, "1.1.1.1")[1]["login"], "owner")

    def test_non_ascii_password_hash_in_file_is_just_a_failure(self):
        self.hub.users["owner"]["pw"] = "пароль"
        with self.assertRaises(HubError) as cm:
            self.hub.login("owner", PW, "1.1.1.1")
        self.assertEqual(cm.exception.status, 401)

    # ----- разделы и проекты -----

    def test_object_prototype_names_are_not_layer_keys(self):
        for key in ("hasOwnProperty", "toString", "valueOf", "__proto__", "constructor", "prototype"):
            with self.assertRaises(HubError, msg=key):
                self.hub.push(self.editor, self.pid, 1, {f"layer:{key}": layer_section(key, "u1")}, "c1")
            self.assertEqual(hub.split_project({"layers": [{"key": key}], "data": {key: {}}}).keys(), {"meta"})
        self.hub.push(self.editor, self.pid, 1, {"layer:hasOwnProperty2": layer_section("hasOwnProperty2", "u1")}, "c1")

    def test_project_size_cap_writes_nothing(self):
        self.patch(PROJECT_MAX_BYTES=50_000)
        rev = self.hub.get_project(self.owner, self.pid)["rev"]
        big = layer_section("big", *[f"{i:012x}" for i in range(2000)])
        with self.assertRaises(HubError) as cm:
            self.hub.push(self.editor, self.pid, rev, {"layer:big": big}, "c1")
        self.assertEqual(cm.exception.status, 413)
        after = self.hub.get_project(self.owner, self.pid)
        self.assertEqual((after["rev"], "layer:big" in after["sections"]), (rev, False))
        with self.assertRaises(HubError):
            self.hub.create_project(self.owner, "Большой", {**sample_project(), "data": {"a": big["data"]},
                                                              "layers": [big["spec"] | {"key": "a"}]})

    def test_quota_blocks_big_writes_only(self):
        self.patch(QUOTA_BYTES=1000, QUOTA_CHECK_FROM=2000)
        self.hub.push(self.editor, self.pid, 1, {"layer:small": layer_section("small", "u1")}, "c1")   # мелкая правка проходит
        self.patch(QUOTA_CHECK_FROM=0)
        with self.assertRaises(HubError) as cm:
            self.hub.push(self.editor, self.pid, 2, {"layer:more": layer_section("more", "u1")}, "c1")
        self.assertEqual(cm.exception.status, 507)
        with self.assertRaises(HubError) as cm:
            self.hub.create_project(self.owner, "Ещё", None)
        self.assertEqual(cm.exception.status, 507)
        self.assertEqual(len(self.hub.list_projects(self.owner)), 1)       # отказ не оставил каталога
        self.assertEqual([p.name for p in (self.hub.root / "projects").iterdir()], [self.pid])

    def test_projects_per_owner_are_capped(self):
        self.patch(PROJECTS_PER_USER=2)
        self.hub.create_project(self.editor, "Раз", None)
        self.hub.create_project(self.editor, "Два", None)
        with self.assertRaises(HubError) as cm:
            self.hub.create_project(self.editor, "Три", None)
        self.assertEqual(cm.exception.status, 400)
        self.hub.create_project(self.viewer, "Чужой счёт не задет", None)

    def test_members_are_capped(self):
        self.patch(MEMBERS_MAX=3)                                           # owner, editor, viewer уже есть
        with self.assertRaises(HubError) as cm:
            self.hub.set_member(self.owner, self.pid, "stranger", "viewer")
        self.assertEqual(cm.exception.status, 400)
        self.hub.set_member(self.owner, self.pid, "viewer", "editor")      # смена роли у своих — можно

    def test_failed_create_leaves_no_directory(self):
        orig = Hub._save_meta
        Hub._save_meta = lambda self, pid, meta: (_ for _ in ()).throw(OSError("диск"))
        self.addCleanup(setattr, Hub, "_save_meta", orig)
        with self.assertRaises(OSError):
            self.hub.create_project(self.owner, "Сбой", None)
        self.assertEqual([p.name for p in (self.hub.root / "projects").iterdir()], [self.pid])

    def test_delete_leaves_no_trash_and_init_clears_leftovers(self):
        self.hub.delete_project(self.owner, self.pid)
        self.assertEqual(list((self.hub.root / "projects").iterdir()), [])
        junk = self.hub.root / "projects" / ".del-0123456789abcdef"
        junk.mkdir()
        (junk / "meta.json").write_text("{}", encoding="utf-8")
        Hub(self.hub.root)
        self.assertFalse(junk.exists())
        self.assertEqual(self.hub.list_projects(self.admin), [])           # недоудалённое не считается проектом

    # ----- комментарии и присутствие -----

    def test_comments_file_size_is_capped(self):
        self.patch(COMMENTS_BYTES=3000)
        c = self.hub.add_comment(self.viewer, self.pid, "точка", {"lonlat": [37.6, 55.7]})
        with self.assertRaises(HubError) as cm:
            for _ in range(30):
                self.hub.reply(self.editor, self.pid, c["id"], "я" * 400)
        self.assertEqual(cm.exception.status, 400)
        self.assertLessEqual(len((self.hub.root / "projects" / self.pid / "comments.json").read_bytes()), 3000)
        rev_c = self.hub._meta(self.pid)["rev_c"]
        with self.assertRaises(HubError):
            self.hub.update_comment(self.owner, self.pid, c["id"], text="я" * 4000)
        self.assertEqual(self.hub._meta(self.pid)["rev_c"], rev_c)         # отказ ничего не записал

    def test_presence_entries_per_user_are_capped(self):
        self.patch(PRESENCE_PER_USER=3)
        for i in range(3):
            self.hub.presence(self.viewer, self.pid, f"tab{i}", None, None, [])
        with self.assertRaises(HubError) as cm:
            self.hub.presence(self.viewer, self.pid, "tab3", None, None, [])
        self.assertEqual(cm.exception.status, 429)
        self.hub.presence(self.viewer, self.pid, "tab0", [37.6, 55.7], None, [])      # своя вкладка обновляется
        self.hub.presence(self.editor, self.pid, "e0", None, None, [])                 # чужие не заняты им
        self.assertEqual(len(self.hub._presence[self.pid]), 4)

    # ----- потоки событий -----

    def test_sse_caps_per_user_and_total(self):
        self.patch(SSE_PER_USER=3, SSE_TOTAL=5)
        mine = [self.hub.subscribe(self.owner, self.pid) for _ in range(3)]
        with self.assertRaises(HubError) as cm:
            self.hub.subscribe(self.owner, self.pid)
        self.assertEqual(cm.exception.status, 429)
        other = [self.hub.subscribe(self.editor, self.pid) for _ in range(2)]        # всего 5
        with self.assertRaises(HubError) as cm:
            self.hub.subscribe(self.viewer, self.pid)
        self.assertEqual(cm.exception.status, 429)
        mine[0].close()                                                               # закрытый поток освобождает место
        self.hub.subscribe(self.viewer, self.pid).close()
        for s in mine[1:] + other:
            s.close()

    def test_sse_limit_counts_across_projects(self):
        self.patch(SSE_PER_USER=2)
        other = self.new_project()
        a, b = self.hub.subscribe(self.owner, self.pid), self.hub.subscribe(self.owner, other)
        with self.assertRaises(HubError):
            self.hub.subscribe(self.owner, other)
        a.close(), b.close()

    def test_admin_demotion_closes_streams_in_foreign_projects_only(self):
        second = self.hub.create_user("boss2", PW, "Второй админ", admin=True)
        foreign = self.hub.subscribe(second, self.pid)                               # админ не участник
        own_pid = self.hub.create_project(second, "Свой", None)["id"]
        own = self.hub.subscribe(second, own_pid)
        self.hub.update_user(self.admin, "boss2", admin=False)
        self.assertTrue(foreign.closed)
        self.assertFalse(own.closed)                                                  # в своём проекте остаётся
        with self.assertRaises(HubError):
            self.hub.subscribe(second, self.pid)
        own.close()


if __name__ == "__main__":
    unittest.main()
