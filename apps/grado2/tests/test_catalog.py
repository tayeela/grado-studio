"""Каталог проектов (catalog.py и маршруты server.py): превью, переименование, копия, корзина, избранное, превью общих проектов.

Запуск: python -m unittest discover -s apps/grado2/tests -p test_catalog.py (PYTHONPATH — как в tools/gate.sh); весь набор — tools/gate.sh.
"""

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import catalog as C  # noqa: E402
import server as S  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "next_ui_project.grado2"


class Preview(unittest.TestCase):
    def test_fixture_draws_visible_layers(self):
        png, n_layers, n_feat = C.render_preview(json.loads(FIXTURE.read_text("utf-8")))
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertGreater(n_layers, 3)
        self.assertGreater(n_feat, 10)

    def test_empty_project_has_no_preview(self):
        self.assertEqual(C.render_preview({"format": "grado2", "layers": [], "data": {}}), (None, 0, 0))

    def test_hidden_layer_and_group_are_skipped(self):
        p = json.loads(FIXTURE.read_text("utf-8"))
        for lay in p["layers"]:
            lay["visible"] = False
        self.assertEqual(C.render_preview(p)[0], None)

    def test_territory_alone_is_drawn(self):
        ring = [[37.80, 55.82], [37.81, 55.82], [37.81, 55.83], [37.80, 55.82]]
        png, _, _ = C.render_preview({"territory": {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}}})
        self.assertTrue(png)

    def test_cache_follows_file_stamp(self):
        with tempfile.TemporaryDirectory() as d:
            cat, f = C.Catalog(Path(d) / C.DB_NAME), Path(d) / "a.grado2"
            f.write_bytes(FIXTURE.read_bytes())
            first = cat.preview("a", f)
            with mock.patch.object(C, "render_preview", side_effect=AssertionError("не из кэша")):
                self.assertEqual(cat.preview("a", f), first)
            f.write_text(json.dumps({"layers": [], "data": {}}))
            self.assertIsNone(cat.preview("a", f))              # файл сменился — превью пересчитано

    def test_broken_database_is_set_aside(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / C.DB_NAME
            db.write_bytes(b"not a database at all" * 100)
            cat = C.Catalog(db)
            cat.set_star("x", True)
            self.assertTrue(cat.marks()["x"]["star"])
            self.assertTrue(list(Path(d).glob(C.DB_NAME + ".broken-*")))


class LocalRoutes(unittest.TestCase):
    """Маршруты каталога на временной папке проектов (настоящую «Документы/ГРАДО 2» тесты не трогают)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "p"
        self.dir.mkdir()
        self.old, S.PROJECTS = S.PROJECTS, self.dir
        self.srv = S.Server(("127.0.0.1", 0))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        (self.dir / "Гольяново.grado2").write_bytes(FIXTURE.read_bytes())

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        S.PROJECTS = self.old
        self.tmp.cleanup()

    def call(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"} if data else {})
        try:
            r = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as e:
            r = e
        raw = r.read()
        return r.status if hasattr(r, "status") else r.code, (json.loads(raw) if raw[:1] == b"{" else raw)

    def names(self):
        return [p["name"] for p in self.call("/api/projects")[1]["projects"]]

    def test_preview_png(self):
        code, body = self.call("/api/project/preview?name=" + urllib.request.quote("Гольяново"))
        self.assertEqual((code, body[:4]), (200, b"\x89PNG"))
        self.assertEqual(self.call("/api/project/preview?name=nope")[0], 404)
        self.assertEqual(self.call("/api/project/preview?name=..%2Fx")[0], 404)

    def test_rename_moves_file_versions_and_star(self):
        (self.dir / ".versions" / "Гольяново").mkdir(parents=True)
        self.call("/api/project/star", {"name": "Гольяново", "on": True})
        code, j = self.call("/api/project/rename", {"name": "Гольяново", "to": "Гольяново, КРТ 12"})
        self.assertEqual((code, j["name"]), (200, "Гольяново, КРТ 12"))
        self.assertEqual(self.names(), ["Гольяново, КРТ 12"])
        self.assertTrue((self.dir / ".versions" / "Гольяново, КРТ 12").is_dir())
        self.assertTrue(self.call("/api/projects")[1]["projects"][0]["star"])

    def test_rename_refuses_clash_bad_names_and_autosave(self):
        (self.dir / "Другой.grado2").write_text("{}")
        code, j = self.call("/api/project/rename", {"name": "Гольяново", "to": "другой"})
        self.assertEqual((code, j["clash"]), (409, "Другой"))
        for bad in ("a/b", ".скрытый", "", S.AUTOSAVE):
            self.assertEqual(self.call("/api/project/rename", {"name": "Гольяново", "to": bad})[0], 400, bad)
        self.assertEqual(self.call("/api/project/rename", {"name": "нет такого", "to": "x"})[0], 400)
        self.assertIn("Гольяново", self.names())

    def test_copy_gets_free_name(self):
        self.assertEqual(self.call("/api/project/copy", {"name": "Гольяново"})[1]["name"], "Гольяново — копия")
        self.assertEqual(self.call("/api/project/copy", {"name": "Гольяново"})[1]["name"], "Гольяново — копия 2")
        self.assertEqual(self.call("/api/project/copy", {"name": "Гольяново", "to": "гольяново — КОПИЯ"})[0], 409)

    def test_delete_goes_to_trash_and_restores(self):
        code, j = self.call("/api/project/delete", {"name": "Гольяново"})
        self.assertEqual((code, j["trash"]), (200, 1))
        self.assertEqual(self.names(), [])
        trash = self.call("/api/projects/trash")[1]["trash"]
        self.assertEqual(trash[0]["name"], "Гольяново")
        (self.dir / "Гольяново.grado2").write_text("{}")                  # название снова занято
        code, j = self.call("/api/project/restore", {"id": trash[0]["id"]})
        self.assertEqual((code, j["name"]), (200, "Гольяново (восстановлен)"))
        self.assertEqual(self.call("/api/project/restore", {"id": "../../etc"})[0], 400)

    def test_open_marks_recent(self):
        self.call("/api/project?name=" + urllib.request.quote("Гольяново"))
        self.assertIsNotNone(self.call("/api/projects")[1]["projects"][0]["opened"])

    def test_closed_in_hub_mode(self):
        # общий сервер: без входа — 401 от охраны, с входом — 403 «проекты хранятся на сервере»
        with mock.patch.object(S, "HUB", object()):
            for path in ("/api/project/preview?name=x", "/api/projects/trash"):
                self.assertIn(self.call(path)[0], (401, 403), path)
            self.assertIn(self.call("/api/project/rename", {"name": "Гольяново", "to": "x"})[0], (401, 403))
        c = mock.Mock(route="/api/project/rename")
        with mock.patch.object(S, "HUB", object()):
            for fn in (S.get_project_preview, S.get_trash, S.post_catalog):
                self.assertEqual(fn(c).status_code, 403)
        self.assertIn("Гольяново", self.names())


class HubPreview(unittest.TestCase):
    def test_member_gets_preview_stranger_does_not(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(S.hubmod, "SCRYPT_N", 2 ** 4):
            hub = S.hubmod.Hub(Path(d) / "hub")
            hub.create_user("ann", "password-ann", "Анна")
            hub.create_user("bob", "password-bob", "Борис")
            ann, bob = hub.session_user(hub.login("ann", "password-ann", "1.1.1.1")[0]), hub.session_user(hub.login("bob", "password-bob", "1.1.1.2")[0])
            pid = hub.create_project(ann, "Общий", json.loads(FIXTURE.read_text("utf-8")))["id"]
            path, rev = hub.project_source(ann, pid)
            self.assertTrue(C.Catalog(hub.root / "catalog.sqlite").preview("hub:" + pid, path, str(rev)))
            with self.assertRaises(S.hubmod.HubError):
                hub.project_source(bob, pid)


if __name__ == "__main__":
    unittest.main()
