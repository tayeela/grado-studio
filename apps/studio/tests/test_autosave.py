import json
import tempfile
import unittest
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
        manifest = json.loads((root / "apps/studio/web/version.json").read_text())
        packaging = (root / "packaging/py2app_setup.py").read_text()

        self.assertEqual("0.9.0-beta.1", manifest["version"])
        self.assertEqual(manifest, server.VERSION_INFO)
        self.assertIn("apps/studio/web/version.json", packaging)

    def test_frontend_persists_schema_and_album_configuration(self):
        root = Path(__file__).parents[3]
        source = (root / "apps/studio/web/app.js").read_text()

        self.assertIn("schema_version: STATE_SCHEMA_VERSION", source)
        self.assertIn("albumConfig: state.albumConfig", source)


if __name__ == "__main__":
    unittest.main()
