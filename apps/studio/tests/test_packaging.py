import tempfile
import unittest
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[3] / "packaging"))
from build_support import data_files_for_tree  # noqa: E402
from build_pages import build_pages  # noqa: E402
from windows_version import build_version_file  # noqa: E402
from windows_entry import _data_dir  # noqa: E402


class TestPackagingResources(unittest.TestCase):
    def test_resource_manifest_excludes_local_and_generated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            (source / "nested").mkdir(parents=True)
            (source / "nested" / "keep.json").write_text("{}")
            (source / ".DS_Store").write_text("finder")
            (source / "style_overrides.json").write_text("{}")
            (source / ".sources").mkdir()
            (source / ".sources" / "private.json").write_text("{}")

            manifest = data_files_for_tree(root, "source", "web")
            paths = [Path(path).name for _target, files in manifest for path in files]
            targets = [Path(target).as_posix() for target, _files in manifest]

        self.assertEqual(paths, ["keep.json"])
        self.assertEqual(targets, ["web/nested"])

    def test_repository_manifest_contains_web_but_no_finder_files(self):
        root = Path(__file__).parents[3]
        manifest = data_files_for_tree(root, "apps/studio/web", "web")
        paths = [path for _target, files in manifest for path in files]
        self.assertTrue(any(path.endswith("index.html") for path in paths))
        self.assertFalse(any(Path(path).name == ".DS_Store" for path in paths))

    def test_pages_build_is_self_contained_and_loads_adapter_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = build_pages(tmp)
            html = (output / "index.html").read_text(encoding="utf-8")

            self.assertTrue((output / "app.js").is_file())
            self.assertTrue((output / "redesign" / "studio2.css").is_file())
            self.assertNotIn('src="/', html)
            self.assertNotIn('href="/', html)
            self.assertLess(html.index("pages-adapter.js"), html.index("app.js"))
            self.assertNotIn("презентационная страница", html.lower())

    def test_windows_release_files_and_version_are_reproducible(self):
        root = Path(__file__).parents[3]
        with tempfile.TemporaryDirectory() as tmp:
            version_file = build_version_file(Path(tmp) / "version.txt")
            version_text = version_file.read_text(encoding="utf-8")

        self.assertIn("0.9.0-beta.8", version_text)
        self.assertTrue((root / "packaging/AppIcon.ico").is_file())
        self.assertTrue((root / "packaging/windows.spec").is_file())
        spec = (root / "packaging/windows.spec").read_text(encoding="utf-8")
        self.assertIn("grado_wizard/album_templates.json", spec)
        installer = (root / "packaging/windows-installer.iss").read_text(encoding="utf-8")
        self.assertIn("GradoStudio.Project", installer)
        self.assertIn("PrivilegesRequired=lowest", installer)

    def test_windows_entry_honors_explicit_data_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(
                    "os.environ", {"GRADO_STUDIO_DATA_DIR": tmp}, clear=True):
                self.assertEqual(_data_dir(), Path(tmp))

    def test_frontend_escapes_imported_titles_and_provenance(self):
        root = Path(__file__).parents[3]
        source = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")
        self.assertIn('escHtml((L || {}).title || f.kind)', source)
        self.assertIn('escHtml(f.prov.source)', source)
