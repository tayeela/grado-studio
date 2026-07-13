import json
import shutil
import subprocess
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
            self.assertTrue((output / "pages-core.js").is_file())
            self.assertTrue((output / "redesign" / "studio2.css").is_file())
            self.assertNotIn('src="/', html)
            self.assertNotIn('href="/', html)
            self.assertLess(html.index("pages-core.js"), html.index("pages-adapter.js"))
            self.assertLess(html.index("pages-adapter.js"), html.index("app.js"))
            self.assertNotIn("презентационная страница", html.lower())
            release = json.loads((output / "version.json").read_text(
                encoding="utf-8"))["bundle_version"]
            self.assertIn(f'window.__GRADO_ASSET_VERSION__="{release}"', html)
            self.assertIn(f'src="./app.js?v={release}"', html)
            self.assertIn(f'href="./redesign/studio2.css?v={release}"', html)

    def test_accessibility_layer_replaces_native_browser_tooltips(self):
        root = Path(__file__).parents[3]
        source = (root / "apps/studio/web/redesign/a11y.js").read_text(
            encoding="utf-8")
        styles = (root / "apps/studio/web/redesign/shell.css").read_text(
            encoding="utf-8")

        self.assertIn("node.removeAttribute('title')", source)
        self.assertIn("tooltip.setAttribute('role', 'tooltip')", source)
        self.assertIn("setAttribute('aria-describedby', tooltip.id)", source)
        self.assertIn(".ui-tooltip", styles)

    def test_close_controls_stay_quiet_and_empty_layers_have_guidance(self):
        root = Path(__file__).parents[3]
        web = root / "apps/studio/web"
        modal_sources = "\n".join((web / name).read_text(encoding="utf-8") for name in (
            "app.js", "app-style-ui.js", "app-attr.js", "app-data.js",
        ))
        html = (web / "index.html").read_text(encoding="utf-8")
        app = (web / "app.js").read_text(encoding="utf-8")
        a11y = (web / "redesign/a11y.js").read_text(encoding="utf-8")

        self.assertNotIn('class="modal-x" title=', modal_sources)
        self.assertIn(".modal-x, .panel-close, .errbar-close", a11y)
        self.assertIn('id="start-draw"', html)
        self.assertIn('title.textContent = "Начертите первый объект"', app)
        self.assertIn('document.getElementById("cv")?.focus()', app)

    def test_panel_resizer_prevents_selection_and_always_cleans_up(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")
        styles = (root / "apps/studio/web/redesign/shell.css").read_text(
            encoding="utf-8")

        self.assertIn("e.preventDefault()", app)
        self.assertIn("lostpointercapture", app)
        self.assertIn("window.addEventListener('blur', finish", app)
        self.assertIn("body.panel-resizing *", styles)
        self.assertIn("user-select:none!important", styles)

    def test_ui_copy_uses_normal_project_names_and_russian_plurals(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")
        adapter = (root / "apps/studio/web/pages-adapter.js").read_text(
            encoding="utf-8")
        html = (root / "apps/studio/web/index.html").read_text(encoding="utf-8")

        self.assertNotIn("объект(ов)", app)
        self.assertNotIn("проект браузера", adapter)
        self.assertIn("Сохранить проект…", html)
        self.assertIn("function ruCount", app)

    def test_compact_header_and_inspector_remain_accessible(self):
        root = Path(__file__).parents[3]
        html = (root / "apps/studio/web/index.html").read_text(encoding="utf-8")
        shell = (root / "apps/studio/web/redesign/shell.css").read_text(
            encoding="utf-8")

        self.assertIn('aria-label="Найти инструмент, слой или действие"', html)
        compact = shell.split("@media (max-width:900px)", 1)[1]
        self.assertIn("background:var(--panel)", compact)
        self.assertIn("backdrop-filter:none", compact)

    def test_browser_menus_skip_unavailable_desktop_actions(self):
        root = Path(__file__).parents[3]
        adapter = (root / "apps/studio/web/pages-adapter.js").read_text(
            encoding="utf-8")
        a11y = (root / "apps/studio/web/redesign/a11y.js").read_text(
            encoding="utf-8")

        self.assertIn('setAttribute("aria-disabled", "true")', adapter)
        self.assertIn('row.matches(".menu-row")', adapter)
        self.assertIn('addMenuNote("menu-data"', adapter)
        self.assertIn('addMenuNote("menu-out"', adapter)
        self.assertIn("function enabledMenuItems", a11y)
        self.assertIn("item.getAttribute('aria-disabled') !== 'true'", a11y)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser-engine parity")
    def test_browser_tep_matches_desktop_engine_for_release_fixture(self):
        root = Path(__file__).parents[3]
        script = r"""
const core = require(process.argv[1]);
const features = JSON.parse(process.argv[2]);
const params = JSON.parse(process.argv[3]);
const out = core.computeTep({features, params});
process.stdout.write(JSON.stringify({
  inputs: out.inputs,
  fact: out.fact,
  rows: Object.fromEntries(out.results.map(row => [row.id, row.value])),
}));
"""
        features = [
            {"kind": "boundary", "ring": [[0, 0], [500, 0], [500, 300], [0, 300]], "props": {}},
            {"kind": "restrict", "ring": [[0, 0], [200, 0], [200, 100], [0, 100]], "props": {}},
            {"kind": "zone", "ring": [[0, 100], [500, 100], [500, 300], [0, 300]], "props": {"zone_title": "Ж-1"}},
            {"kind": "building", "ring": [[50, 150], [80, 150], [80, 170], [50, 170]], "props": {"floors": 10}},
            {"kind": "redline", "line": [[0, 120], [500, 120]], "props": {}},
            {"kind": "social", "point": [400, 200], "props": {"capacity": 500}},
        ]
        params = {"density": 25, "ratio_zh": 80, "education_zone": 2,
                  "k_rail": 0.75, "k_ba": 0.2}
        completed = subprocess.run(
            ["node", "-e", script, str(root / "apps/studio/web/pages-core.js"),
             json.dumps(features), json.dumps(params)],
            check=True, capture_output=True, text=True,
        )
        browser = json.loads(completed.stdout)

        sys.path.insert(0, str(root / "apps/studio"))
        import studio_core
        desktop = studio_core.compute_tep(features, params)
        desktop_rows = {row["id"]: row["value"] for row in desktop["results"]}

        self.assertEqual(browser["inputs"], desktop["inputs"])
        self.assertEqual(browser["fact"], desktop["fact"])
        self.assertEqual(browser["rows"], desktop_rows)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser preflight")
    def test_browser_preflight_rejects_invalid_geometry(self):
        root = Path(__file__).parents[3]
        script = r"""
const core = require(process.argv[1]);
process.stdout.write(JSON.stringify(core.preflightProject(JSON.parse(process.argv[2]))));
"""
        payload = {"target": "grado", "features": [
            {"id": 1, "kind": "boundary", "layer_id": "project.territory.boundary",
             "ring": [[0, 0], [100, 0], [100, 100], [0, 100]]},
            {"id": 2, "kind": "zone", "layer_id": "project.tp.func_zone",
             "line": [[0, 0], [10, 10]]},
        ]}
        completed = subprocess.run(
            ["node", "-e", script, str(root / "apps/studio/web/pages-core.js"),
             json.dumps(payload)], check=True, capture_output=True, text=True,
        )
        report = json.loads(completed.stdout)
        self.assertFalse(report["can_export"])
        self.assertEqual(report["errors"][0]["code"], "invalid_geometry")
        self.assertEqual(report["errors"][0]["feature_ids"], ["2"])

    def test_frontend_defensively_restores_projects_and_async_errors(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")
        styles = (root / "apps/studio/web/style.css").read_text(encoding="utf-8")

        self.assertIn("function normalizeRestoredState", app)
        self.assertIn("hasValidGeometry(feature)", app)
        self.assertIn("Object.create(null)", app)
        self.assertIn('window.addEventListener("unhandledrejection"', app)
        self.assertIn("position: fixed", styles.split("#errbar", 1)[1].split("}", 1)[0])

    def test_windows_release_files_and_version_are_reproducible(self):
        root = Path(__file__).parents[3]
        release_version = json.loads(
            (root / "apps/studio/web/version.json").read_text(encoding="utf-8")
        )["version"]
        with tempfile.TemporaryDirectory() as tmp:
            version_file = build_version_file(Path(tmp) / "version.txt")
            version_text = version_file.read_text(encoding="utf-8")

        self.assertIn(release_version, version_text)
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
