import json
import tempfile
import unittest
import io
from unittest import mock
from pathlib import Path

import server


class AutosaveTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / ".autosave.json"

    def tearDown(self):
        self.tempdir.cleanup()

    @staticmethod
    def state(name, count):
        return {
            "schema_version": 1,
            "name": name,
            "features": [{"id": index + 1} for index in range(count)],
            "albumConfig": {"sheets": ["title", "tep"]},
        }

    def test_writes_versioned_envelope_and_metadata(self):
        meta, changed = server.save_autosave(self.state("Проект", 2), path=self.path)
        payload = json.loads(self.path.read_text(encoding="utf-8"))

        self.assertTrue(changed)
        self.assertEqual(server.VERSION_INFO["state_schema_version"], payload["schema_version"])
        self.assertEqual("Проект", payload["state"]["name"])
        self.assertEqual(2, meta["feature_count"])
        self.assertTrue(payload["saved_at"].endswith("Z"))
        self.assertEqual(64, len(payload["checksum"]))

    def test_identical_state_does_not_create_backup(self):
        state = self.state("Проект", 1)
        server.save_autosave(state, path=self.path)
        _, changed = server.save_autosave(state, path=self.path)

        self.assertFalse(changed)
        self.assertFalse(server._autosave_backup_path(self.path, 1).exists())

    def test_rotates_previous_states_and_lists_them(self):
        server.save_autosave(self.state("Первая", 1), path=self.path)
        server.save_autosave(self.state("Вторая", 2), path=self.path)
        server.save_autosave(self.state("Третья", 3), path=self.path)

        backups = server.list_autosave_backups(self.path)
        self.assertEqual(["Вторая", "Первая"], [item["name"] for item in backups])
        self.assertEqual([2, 1], [item["feature_count"] for item in backups])
        older = json.loads(server._autosave_backup_path(self.path, 2).read_text(encoding="utf-8"))
        self.assertEqual("Первая", server._autosave_state(older)["name"])

    def test_rotates_legacy_raw_state_without_losing_it(self):
        legacy = self.state("Старая", 4)
        self.path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")

        server.save_autosave(self.state("Новая", 1), path=self.path)

        backup = json.loads(server._autosave_backup_path(self.path, 1).read_text(encoding="utf-8"))
        self.assertEqual(legacy, backup)
        self.assertEqual("Старая", server.list_autosave_backups(self.path)[0]["name"])

    def test_keeps_only_configured_number_of_previous_states(self):
        for index in range(13):
            server.save_autosave(self.state(f"Версия {index}", index), path=self.path)

        backups = server.list_autosave_backups(self.path)
        self.assertEqual(10, len(backups))
        self.assertEqual("Версия 11", backups[0]["name"])
        self.assertEqual("Версия 2", backups[-1]["name"])

    def test_rejects_invalid_state_before_touching_current_file(self):
        original = self.state("Надёжная", 1)
        server.save_autosave(original, path=self.path)
        before = self.path.read_bytes()

        with self.assertRaises(ValueError):
            server.save_autosave({"name": "сломано"}, path=self.path)

        self.assertEqual(before, self.path.read_bytes())

    def test_preserves_damaged_current_file_and_continues_saving(self):
        damaged = b'{"features": ['
        self.path.write_bytes(damaged)

        server.save_autosave(self.state("Исправная", 2), path=self.path)

        self.assertEqual(damaged, server._autosave_corrupt_path(self.path).read_bytes())
        current = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual("Исправная", server._autosave_state(current)["name"])


class ReleaseManifestTests(unittest.TestCase):
    def test_manifest_is_single_source_for_server_and_packaging(self):
        root = Path(__file__).parents[3]
        manifest = json.loads((root / "apps/studio/web/version.json").read_text(
            encoding="utf-8"))
        packaging = (root / "packaging/py2app_setup.py").read_text(
            encoding="utf-8")

        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
        self.assertEqual(manifest, server.VERSION_INFO)
        self.assertIn("apps/studio/web/version.json", packaging)

    def test_frontend_persists_schema_and_album_configuration(self):
        root = Path(__file__).parents[3]
        source = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")

        self.assertIn("schema_version: STATE_SCHEMA_VERSION", source)
        self.assertIn("albumConfig: state.albumConfig", source)
        self.assertIn("renderLayers(); renderProps(); updateLayerStatus(); persist(); draw();", source)

    def test_frontend_opens_grado_once_and_embeds_project_settings(self):
        root = Path(__file__).parents[3]
        source = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")
        handler = source.split('on("grado-file", "change"', 1)[1].split(
            "function loadProjectData", 1)[0]

        self.assertEqual(1, handler.count("loadProjectData(data)"))
        self.assertNotIn("state.features = data.features", handler)
        self.assertIn("studioState: collectProjectSettings()", source)
        self.assertIn('on("btn-new-project", "click", newProject)', source)

    def test_packaged_app_opens_browser_automatically(self):
        with mock.patch.object(server.sys, "frozen", "macosx_app", create=True), \
                mock.patch.dict(server.os.environ, {}, clear=True), \
                mock.patch.object(server.sys, "argv", ["studio"]):
            self.assertTrue(server._should_open_browser())

    def test_release_smoke_can_disable_automatic_browser(self):
        with mock.patch.object(server.sys, "frozen", "macosx_app", create=True), \
                mock.patch.dict(server.os.environ, {"GRADO_NO_BROWSER": "1"}, clear=True):
            self.assertFalse(server._should_open_browser())

    def test_windows_launcher_uses_desktop_mode_and_user_data_dir(self):
        with mock.patch.object(server.sys, "frozen", False, create=True), \
                mock.patch.object(server.sys, "platform", "win32"), \
                mock.patch.object(server.sys, "argv", ["studio", "--desktop"]), \
                mock.patch.dict(server.os.environ,
                                {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"},
                                clear=True):
            self.assertTrue(server._should_open_browser())
            self.assertEqual(
                Path(r"C:\Users\Test\AppData\Local") / "GRADO Studio",
                server._studio_data_dir())

    def test_cloud_mode_binds_publicly_and_disables_local_bridge(self):
        with mock.patch.object(server.sys, "argv", ["studio", "--cloud"]), \
                mock.patch.dict(server.os.environ, {}, clear=True):
            self.assertTrue(server._cloud_mode())
            self.assertEqual("0.0.0.0", server._server_host())
            self.assertFalse(server._bridge_enabled())
            self.assertFalse(server._server_side_import_enabled())

    def test_cloud_session_cookie_is_https_only(self):
        with mock.patch.object(server.sys, "argv", ["studio", "--cloud"]), \
                mock.patch.dict(server.os.environ, {}, clear=True):
            cookie = server.Handler._session_cookie("token")
            cleared = server.Handler._session_cookie("", clear=True)
        for value in (cookie, cleared):
            self.assertIn("HttpOnly", value)
            self.assertIn("SameSite=Lax", value)
            self.assertIn("Secure", value)

    def test_request_body_limit_rejects_oversized_upload(self):
        handler = object.__new__(server.Handler)
        handler.headers = {"Content-Length": str(server.MAX_FILE_UPLOAD + 1)}
        handler.rfile = io.BytesIO(b"")
        with self.assertRaises(server.RequestBodyTooLarge):
            handler._read_body(server.MAX_FILE_UPLOAD)

    @staticmethod
    def api_handler(path, body):
        handler = object.__new__(server.Handler)
        handler.path = path
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler._json = mock.Mock()
        return handler

    def test_json_body_rejects_malformed_and_non_object_payloads(self):
        malformed = self.api_handler("/api/tep", b'{"features": [')
        array_body = self.api_handler("/api/tep", b"[]")

        with self.assertRaises(server.BadRequest):
            malformed._json_body()
        with self.assertRaises(server.BadRequest):
            array_body._json_body()

    def test_api_reports_bad_json_as_400_json(self):
        handler = self.api_handler("/api/tep", b'{"features": [')

        handler.do_POST()

        handler._json.assert_called_once_with(
            {"error": "invalid request body"}, 400)

    def test_api_reports_oversized_body_as_413_json(self):
        handler = self.api_handler("/api/tep", b"")
        handler.headers["Content-Length"] = str(server.MAX_JSON_BODY + 1)

        handler.do_POST()

        handler._json.assert_called_once_with(
            {"error": "request body too large"}, 413)

    def test_api_does_not_expose_internal_exception_details(self):
        body = json.dumps({"features": [], "params": {}}).encode()
        handler = self.api_handler("/api/tep", body)

        with mock.patch.object(
                server.studio_core, "compute_tep",
                side_effect=RuntimeError("/private/project/customer.grado")), \
                mock.patch.object(server.traceback, "print_exc"):
            handler.do_POST()

        handler._json.assert_called_once_with(
            {"error": "internal server error"}, 500)

    def test_packaged_app_has_fallback_ports_but_dev_is_strict(self):
        with mock.patch.object(server.sys, "frozen", "macosx_app", create=True):
            self.assertEqual(list(range(8643, 8653)), list(server._port_candidates(8643)))
        with mock.patch.object(server.sys, "frozen", False, create=True):
            self.assertEqual([8643], list(server._port_candidates(8643)))
        with mock.patch.object(server.sys, "frozen", False, create=True), \
                mock.patch.object(server.sys, "argv", ["studio", "--desktop"]):
            self.assertEqual(list(range(8643, 8653)),
                             list(server._port_candidates(8643)))


if __name__ == "__main__":
    unittest.main()
