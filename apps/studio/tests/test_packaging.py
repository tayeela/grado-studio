import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "packaging"))
from build_support import data_files_for_tree  # noqa: E402
from build_pages import build_pages  # noqa: E402


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
            targets = [target for target, _files in manifest]

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
