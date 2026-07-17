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
            self.assertTrue((output / "crs.js").is_file())
            self.assertTrue((output / "pages-core.js").is_file())
            styles = json.loads((output / "styles.json").read_text(encoding="utf-8"))
            self.assertGreater(len(styles), 50)
            self.assertIn("boundary.line", styles)
            self.assertTrue((output / "redesign" / "studio2.css").is_file())
            self.assertTrue((output / "favicon.svg").is_file())
            self.assertNotIn('src="/', html)
            self.assertNotIn('href="/', html)
            self.assertLess(html.index("crs.js"), html.index("pages-core.js"))
            self.assertLess(html.index("pages-core.js"), html.index("pages-adapter.js"))
            self.assertLess(html.index("pages-adapter.js"), html.index("app.js"))
            self.assertNotIn("презентационная страница", html.lower())
            release = json.loads((output / "version.json").read_text(
                encoding="utf-8"))["bundle_version"]
            self.assertIn(f'window.__GRADO_ASSET_VERSION__="{release}"', html)
            # правила маршрутизации ОГД обязаны впекаться (беззвучный '' в
            # rules_js оставил бы веб на устаревшей своей копии — класс beta.84)
            self.assertIn("window.__GRADO_GISOGD_RULES__", html)
            self.assertIn('"beregov"', html)
            self.assertIn(f'src="./app.js?v={release}"', html)
            self.assertIn(f'href="./redesign/studio2.css?v={release}"', html)
            self.assertIn(f'href="./favicon.svg?v={release}"', html)
            adapter = (output / "pages-adapter.js").read_text(encoding="utf-8")
            self.assertIn('new URL("./styles.json"', adapter)

    def test_pages_build_does_not_reset_active_desktop_styles(self):
        root = Path(__file__).parents[3]
        sys.path.insert(0, str(root / "apps/studio"))
        import studio_core
        original = studio_core.current_style_overrides()
        override = {"boundary.line": {"stroke": "#abcdef"}}
        try:
            studio_core.apply_style_overrides(override)
            with tempfile.TemporaryDirectory() as tmp:
                output = build_pages(tmp)
                packaged = json.loads((output / "styles.json").read_text(
                    encoding="utf-8"))
            self.assertEqual(studio_core.current_style_overrides(), override)
            self.assertEqual(
                studio_core.frontend_styles()["boundary.line"]["stroke"],
                "#abcdef",
            )
            self.assertNotEqual(packaged["boundary.line"]["stroke"], "#abcdef")
        finally:
            studio_core.apply_style_overrides(original)

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
        self.assertIn('id="start-unlock"', html)
        self.assertIn('title.textContent = "Начертите первый объект"', app)
        self.assertIn("function isDrawableLayer", app)
        self.assertIn("!layer.annotation && !layer.import_only && !layer.locked", app)
        self.assertIn('document.getElementById("cv")?.focus()', app)

    def test_new_project_name_and_dialog_names_are_lossless(self):
        root = Path(__file__).parents[3]
        web = root / "apps/studio/web"
        html = (web / "index.html").read_text(encoding="utf-8")
        app = (web / "app.js").read_text(encoding="utf-8")
        a11y = (web / "redesign/a11y.js").read_text(encoding="utf-8")

        self.assertIn('id="project-name" value="Новый проект" maxlength="240"', html)
        self.assertIn('on("project-name", "input", event => {', app)
        self.assertIn('rememberPendingProjectName(event.target.value)', app)
        self.assertIn('PENDING_PROJECT_NAME_KEY', app)
        self.assertIn('if (applyPendingProjectName()) persist(0)', app)
        self.assertNotIn('on("project-name", "change", persist)', app)
        self.assertIn('window.addEventListener("pagehide", flushPendingAutosave)', app)
        self.assertIn('document.visibilityState === "hidden"', app)
        self.assertIn("copy.querySelectorAll('button, input, select, textarea, a')", a11y)
        self.assertIn("dialog.hasAttribute('aria-label')", a11y)

    def test_gisogd_source_choice_has_a_real_cancel_path(self):
        root = Path(__file__).parents[3]
        web = root / "apps/studio/web"
        app = (web / "app.js").read_text(encoding="utf-8")
        imports = (web / "app-import.js").read_text(encoding="utf-8")

        self.assertIn("function uiChoice(msg, choices", app)
        self.assertIn('if (event.key === "Escape") done(null)', app)
        self.assertIn('const source = await uiChoice(', imports)
        self.assertIn('if (source === "file")', imports)
        self.assertIn('else if (source === "url")', imports)
        self.assertNotIn('cancel: "По ссылке"', imports)

    def test_statusbar_stays_single_line_when_inspector_is_wide(self):
        root = Path(__file__).parents[3]
        shell = (root / "apps/studio/web/redesign/shell.css").read_text(
            encoding="utf-8")

        self.assertRegex(shell, r"\.statusbar\{[\s\S]*?white-space:nowrap;overflow:hidden")
        self.assertRegex(shell, r"\.statusbar \.st-active\{[\s\S]*?text-overflow:ellipsis")
        self.assertIn(".statusbar .push{flex:1;min-width:0}", shell)
        self.assertIn("#stage{flex:1 1 0;position:relative;min-width:0;min-height:0;overflow:hidden;container-type:inline-size}", shell)
        self.assertIn("@container (max-width:680px)", shell)
        self.assertIn("#st-coords,#st-grid,.cv-scale{display:none!important}", shell)
        self.assertNotIn("#st-snap{display:none!important}", shell)

    def test_dialog_focus_and_numeric_editors_are_guarded(self):
        root = Path(__file__).parents[3]
        web = root / "apps/studio/web"
        app = (web / "app.js").read_text(encoding="utf-8")
        style = (web / "app-style-ui.js").read_text(encoding="utf-8")
        a11y = (web / "redesign/a11y.js").read_text(encoding="utf-8")
        css = (web / "redesign/studio2.css").read_text(encoding="utf-8")
        html = (web / "index.html").read_text(encoding="utf-8")

        self.assertIn("const popupTriggerFor = element =>", a11y)
        self.assertIn("previousFocus.set(overlay, focusReturnTarget(source))", a11y)
        self.assertIn("const previous = focusReturnTarget(previousFocus.get(overlay))", a11y)
        self.assertIn('aria-label="Закрыть окно восстановления"', app)
        self.assertIn('overlay.querySelector(".recovery-close").focus()', app)
        self.assertIn('id="tep-form-error" role="alert" hidden', app)
        self.assertIn('invalid.setAttribute("aria-invalid", "true")', app)
        self.assertIn('.modal-overlay [aria-invalid="true"]', css)
        self.assertIn('#props-body [aria-invalid="true"]', css)
        self.assertIn('id="panel-resizer" title="Перетащите — ширина инспектора" data-no-tooltip', html)
        self.assertIn("function boundedNumber(value, minimum, maximum, fallback)", app)
        self.assertIn('boundedNumber($("fmt-width").value, 0.2, 8, 1)', style)
        self.assertIn('boundedNumber($("lib-mperiod").value, 6, 200, 40)', style)
        self.assertIn('id="style-form-error" role="alert" hidden', style)
        self.assertIn("const validateSingleStyle = () =>", style)
        self.assertIn('if (mode === "single" && !validateSingleStyle()) return', style)
        self.assertIn('const validateRules = () =>', style)
        self.assertIn('if (mode === "rules" && !validateRules()) return', style)
        self.assertIn('overlay.querySelectorAll(".cr-op").forEach', style)
        self.assertIn('class="layer-select" aria-pressed=', app)
        self.assertIn('const selectButton = row.querySelector(".layer-select")', app)
        self.assertIn('event.key !== "Enter" && event.key !== " "', app)
        self.assertIn('freshButton.focus({ preventScroll: true })', app)
        self.assertIn('.layer-row:focus-within .lrow-menu', css)
        self.assertIn('function validatePropertyNumber(input, label)', app)
        self.assertIn('if (!validatePropertyNumber(distanceInput, "Офсет")) return false', app)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser-engine bounds")
    def test_browser_tep_rejects_values_outside_moscow_preset(self):
        root = Path(__file__).parents[3]
        script = r"""
const core = require(process.argv[1]);
const rows = params => Object.fromEntries(
  core.computeTep({features:[], params}).results.map(row => [row.id, row.value]));
process.stdout.write(JSON.stringify({
  baseline: rows({}),
  invalid: rows({density:60.1, ratio_zh:100.1, percent_vpp:30.1,
    k_rail:0.49, k_ba:1.01}),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script,
             str(root / "apps/studio/web/pages-core.js")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["invalid"], result["baseline"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser-engine test")
    def test_geojson_import_routes_by_linecode(self):
        root = Path(__file__).parents[3]
        script = r"""
const core = require(process.argv[1]);
core.setLgrCodeStyles(require(process.argv[2]).styles);
const line = props => ({type:"FeatureCollection", features:[{type:"Feature",
  properties: props, geometry:{type:"LineString", coordinates:[[37.6,55.75],[37.61,55.75]]}}]});
// имя файла «красные линии УДС», а LineCode = -41 (береговая) — тип из ДАННЫХ
const a = core.importGeoJson(line({LineCode:"-41"}), "krasnye_linii_uds.geojson");
// многокодовый: одна геометрия → два знака в два слоя
const b = core.importGeoJson(line({LineCode:"1,-29"}), "x.geojson");
// без LineCode — прежний маршрут по имени файла, объект не теряется
const c = core.importGeoJson({type:"FeatureCollection", features:[{type:"Feature",
  properties:{}, geometry:{type:"Polygon", coordinates:[[[37.6,55.75],[37.61,55.75],[37.61,55.76],[37.6,55.75]]]}}]},
  "vodoohrannaya_zona.geojson");
process.stdout.write(JSON.stringify({
  aLayer: a.features[0].layer_id, aStyle: a.features[0].style_id, aSide: a.features[0].props.line_side,
  aLayers: a.layers.map(L => L.id),
  bLayers: b.features.map(f => f.layer_id), bReported: b.layers.map(L => [L.id, L.kind]),
  cLayer: c.features[0].layer_id, cStyle: c.features[0].style_id,
  cLayers: c.layers.map(L => L.id),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script,
             str(root / "apps/studio/web/pages-core.js"),
             str(root / "core/render/grado_render/styles/moscow_lgr.json")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        out = json.loads(completed.stdout)
        # LineCode бьёт имя файла по ЗНАКУ: -41 → береговая. А СЛОЙ = файл-
        # источник (требование юзера), а не слой-знак.
        self.assertEqual(out["aLayer"], "source.gisogd.member.krasnye_linii_uds")
        self.assertEqual(out["aStyle"], "lgr.beregovaya")
        self.assertEqual(out["aSide"], -1)
        self.assertEqual(out["aLayers"], ["source.gisogd.member.krasnye_linii_uds"])
        # многокодовый: оба знака в ОДНОМ слое-источнике (файл x.geojson)
        self.assertEqual(out["bLayers"],
                         ["source.gisogd.member.x", "source.gisogd.member.x"])
        self.assertEqual(out["bReported"], [["source.gisogd.member.x", "redline"]])
        # без LineCode — знак по имени, слой = файл-источник
        self.assertEqual(out["cLayer"], "source.gisogd.member.vodoohrannaya_zona")
        self.assertEqual(out["cStyle"], "lgr.vodookhr")
        self.assertEqual(out["cLayers"], ["source.gisogd.member.vodoohrannaya_zona"])

    def test_modal_close_control_cannot_be_shifted_by_legacy_styles(self):
        root = Path(__file__).parents[3]
        styles = (root / "apps/studio/web/redesign/studio2.css").read_text(
            encoding="utf-8")

        self.assertIn(".modal-head .modal-x{", styles)
        self.assertIn("margin:0;padding:0!important", styles)
        self.assertIn("display:grid;", styles)
        self.assertIn("place-items:center", styles)
        self.assertIn("transform:translateY(-50%)", styles)
        self.assertIn(".modal-head .modal-x:focus-visible", styles)

    def test_user_style_and_property_values_are_bounded_and_escaped(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")
        style_ui = (root / "apps/studio/web/app-style-ui.js").read_text(
            encoding="utf-8")

        self.assertIn('value="${escHtml(val)}"', app)
        self.assertIn('/^[A-Za-z][A-Za-z0-9_.-]{0,63}$/.test(cleanId)', app)
        self.assertIn('value="${escHtml(st.title || id)}"', app)
        self.assertIn('boundedNumber(st.width, 0.2, 8, 1.5)', app)
        self.assertIn('id="ps-error" role="alert" hidden', app)
        self.assertIn('<span id="project-style-edit-title">', app)
        self.assertIn('boundedNumber(f.props._offdist, 0.5, 200, 15)', app)
        self.assertIn('typeof c !== "string"', style_ui)
        self.assertIn('const hex = normHex(c)', style_ui)
        self.assertIn('<optgroup label="${escHtml(g)}">', style_ui)
        self.assertIn('<option value="${escHtml(sid)}"', style_ui)
        self.assertIn('>${escHtml(title)}</option>', style_ui)
        self.assertIn('boundedNumber(cur.width, 0.2, 8, 1)', style_ui)
        self.assertIn('Array.isArray(dash) ? dash.join(",")', app)

    def test_panel_close_is_only_visible_in_compact_drawer(self):
        root = Path(__file__).parents[3]
        styles = (root / "apps/studio/web/redesign/shell.css").read_text(
            encoding="utf-8")
        desktop, compact = styles.split("@media (max-width:900px)", 1)

        self.assertIn(".phbtn.panel-close{display:none}", desktop)
        self.assertGreater(
            desktop.index(".phbtn.panel-close{display:none}"),
            desktop.index(".phbtn{"),
            "desktop close rule must win over the generic phbtn display",
        )
        self.assertIn(".phbtn.panel-close{display:grid}", compact)

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

    def test_panel_resizer_preserves_canvas_and_reports_effective_width(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")
        styles = (root / "apps/studio/web/redesign/shell.css").read_text(
            encoding="utf-8")
        html = (root / "apps/studio/web/index.html").read_text(encoding="utf-8")

        self.assertIn("const MIN_STAGE_WIDTH = 480", app)
        self.assertIn("const effectiveMaxWidth", app)
        self.assertIn("window.innerWidth * 0.48", app)
        self.assertIn("aria-valuetext", app)
        self.assertIn("window.addEventListener('resize'", app)
        self.assertIn("max-width:min(640px,48vw)", styles)
        panel_close = html.split('id="btn-panel-close"', 1)[0].rsplit("<button", 1)[1]
        self.assertNotIn("title=", panel_close)

    def test_fit_all_uses_feature_extents_and_visible_layers(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")

        self.assertIn("function featureViewBox(f)", app)
        self.assertIn("function unionViewBoxes(boxes)", app)
        self.assertIn("if (layer && !layer.visible) continue", app)
        self.assertIn("if (boxes.length > 4)", app)
        self.assertIn("fitBox(b.minx, b.miny, b.maxx, b.maxy)", app)

    def test_default_boundary_stroke_tracks_canvas_theme(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")

        self.assertIn("function canvasStrokeOf(f, st)", app)
        self.assertIn('styleId === "boundary.line"', app)
        self.assertIn('return cvColor("boundary", st.stroke || "#1c1c1a")', app)
        self.assertIn("ctx.strokeStyle = canvasStrokeOf(f, st)", app)

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

    def test_browser_menu_exposes_safe_file_imports(self):
        root = Path(__file__).parents[3]
        adapter = (root / "apps/studio/web/pages-adapter.js").read_text(
            encoding="utf-8")
        importer = (root / "apps/studio/web/app-import.js").read_text(
            encoding="utf-8")
        cmdk = (root / "apps/studio/web/redesign/cmdk.js").read_text(
            encoding="utf-8")

        blocked = adapter.split("const blocked = new Set(", 1)[1].split(");", 1)[0]
        self.assertNotIn('"btn-nspd"', blocked)
        self.assertNotIn('"btn-gisogd"', blocked)
        self.assertNotIn('"btn-data"', blocked)
        self.assertIn('gisogdInput.accept = ".geojson,.json', adapter)
        self.assertIn("В веб-версии доступны OSM и НСПД по видимой области", adapter)
        self.assertIn('path === "/api/fetch-extent"', adapter)
        self.assertIn("window.GRADO_STATIC ? await file.text()", importer)
        self.assertIn('isWeb ? "Импорт ГИС ОГД (GeoJSON)"', cmdk)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser imports")
    def test_browser_core_imports_nspd_and_gisogd_geojson(self):
        root = Path(__file__).parents[3]
        script = r"""
const core = require(process.argv[1]);
const merc = [[[4187345.5,7509247.8],[4187445.5,7509247.8],
  [4187445.5,7509347.8],[4187345.5,7509247.8]]];
const nspd = core.importNspd({type:'FeatureCollection',grado_source:'nspd',features:[
  {id:'77:09:0004021:181',geometry:{type:'Polygon',coordinates:merc},
   properties:{options:{cad_num:'77:09:0004021:181',land_record_category_type:'земли'}}},
  {id:'duplicate',geometry:{type:'Polygon',coordinates:merc},properties:{}}
]});
const poly = [[[37.6155646254,55.7522242128],[37.617,55.7522242128],
  [37.617,55.753],[37.6155646254,55.7522242128]]];
const ogd = core.importGeoJson({type:'FeatureCollection',features:[
  {type:'Feature',id:7,properties:{NAME:'Ж-1'},geometry:{type:'Polygon',coordinates:poly}}
]}, 'funkcionalnie_zony.geojson');
process.stdout.write(JSON.stringify({
  nspdCount:nspd.features.length,nspdKind:nspd.features[0].kind,
  cad:nspd.features[0].props.cad_num,nspdPoint:nspd.features[0].ring[0],
  duplicateNote:nspd.notes[0],ogdCount:ogd.features.length,
  ogdKind:ogd.features[0].kind,ogdLayer:ogd.features[0].layer_id,
  ogdPoint:ogd.features[0].ring[0],field:ogd.fields['source.gisogd.member.funkcionalnie_zony'][0].name
}));
"""
        completed = subprocess.run(
            ["node", "-e", script, str(root / "apps/studio/web/pages-core.js")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        result = json.loads(completed.stdout)
        self.assertEqual(1, result["nspdCount"])
        self.assertEqual("parcel", result["nspdKind"])
        self.assertEqual("77:09:0004021:181", result["cad"])
        self.assertAlmostEqual(107, result["nspdPoint"][0], delta=15)
        self.assertAlmostEqual(1371, result["nspdPoint"][1], delta=15)
        self.assertIn("дубликатов", result["duplicateNote"])
        self.assertEqual(1, result["ogdCount"])
        self.assertEqual("zone", result["ogdKind"])
        # слой = файл-источник (требование юзера), не слой-знак func_zones
        self.assertEqual("source.gisogd.member.funkcionalnie_zony", result["ogdLayer"])
        self.assertAlmostEqual(107, result["ogdPoint"][0], delta=15)
        self.assertEqual("NAME", result["field"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser extent imports")
    def test_browser_core_builds_and_normalizes_extent_sources(self):
        root = Path(__file__).parents[3]
        script = r"""
const core = require(process.argv[1]);
const bbox=[37.615,55.755,37.616,55.756];
const query=core.buildOsmExtentRequest(bbox,['osm.roads','osm.buildings']);
const osm=core.importOsmExtent({elements:[
  {type:'way',id:10,tags:{highway:'residential',name:'Улица'},geometry:[
    {lon:37.6151,lat:55.7551},{lon:37.6158,lat:55.7558}]},
  {type:'way',id:20,tags:{building:'yes','building:levels':'5'},geometry:[
    {lon:37.6152,lat:55.7552},{lon:37.6154,lat:55.7552},
    {lon:37.6154,lat:55.7554},{lon:37.6152,lat:55.7552}]}
]},['osm.roads','osm.buildings'],bbox);
const request=core.buildNspdExtentRequest(bbox,'nspd.buildings');
const merc=[[[4187345.5,7509247.8],[4187445.5,7509247.8],
  [4187445.5,7509347.8],[4187345.5,7509247.8]]];
const nspd=core.importNspdExtent({features:[{id:7,geometry:{type:'Polygon',coordinates:merc},
  properties:{options:{cad_num:'77:01:7',building_name:'Дом',floors:'8'}}}]},
  'nspd.buildings',bbox);
process.stdout.write(JSON.stringify({query,osm:osm.groups.map(g=>[g.source,g.count]),
  roadKey:osm.groups[0].features[0].srcKey,categories:request.categories,
  nspdCount:nspd.groups[0].count,nspdKind:nspd.groups[0].features[0].kind,
  floors:nspd.groups[0].features[0].props.floors}));
"""
        completed = subprocess.run(
            ["node", "-e", script, str(root / "apps/studio/web/pages-core.js")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        result = json.loads(completed.stdout)
        self.assertIn('way["highway"]', result["query"])
        self.assertEqual([["osm.roads", 1], ["osm.buildings", 1]], result["osm"])
        self.assertIn("way/10", result["roadKey"])
        self.assertEqual([{"id": 36369}], result["categories"])
        self.assertEqual(1, result["nspdCount"])
        self.assertEqual("building", result["nspdKind"])
        self.assertEqual(8, result["floors"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser CRS")
    def test_browser_crs_matches_proj_and_roundtrips(self):
        root = Path(__file__).parents[3]
        script = r"""
const crs=require(process.argv[1]);
const cases=[
  [[37.6176,55.7558],[413242.9638,6179766.5783]],
  [[39.0,55.0],[500000.0,6094791.4210]],
  [[37.5,55.667],[405649.3971,6170038.5624]],
];
const projected=cases.map(([point,expected])=>{
  const got=crs.wgs84ToUtm37n(point);
  const back=crs.utm37nToWgs84(got);
  return {dx:got[0]-expected[0],dy:got[1]-expected[1],
    dlon:back[0]-point[0],dlat:back[1]-point[1]};
});
const originLocal=crs.wgs84ToLocal(crs.ORIGIN_WGS84);
process.stdout.write(JSON.stringify({projected,originLocal}));
"""
        completed = subprocess.run(
            ["node", "-e", script, str(root / "apps/studio/web/crs.js")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        result = json.loads(completed.stdout)
        for case in result["projected"]:
            self.assertLess(abs(case["dx"]), 0.005)
            self.assertLess(abs(case["dy"]), 0.005)
            self.assertLess(abs(case["dlon"]), 1e-7)
            self.assertLess(abs(case["dlat"]), 1e-7)
        self.assertLess(abs(result["originLocal"][0]), 0.001)
        self.assertLess(abs(result["originLocal"][1]), 0.001)

    def test_basemap_uses_exact_projected_corners(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")
        data = (root / "apps/studio/web/app-data.js").read_text(encoding="utf-8")
        self.assertIn("exactCrs.localToWgs84([x, y])", app)
        self.assertIn("exactCrs.wgs84ToLocal([lon, lat])", app)
        self.assertIn("const ne = lonLatToLocal", app)
        self.assertIn("const sw = lonLatToLocal", app)
        self.assertIn("ctx.transform((p10[0] - p00[0])", app)
        self.assertIn("[[0, 0], [w, 0], [w, h], [0, h]]", data)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser snapping")
    def test_browser_object_snap_prefers_object_points_over_grid(self):
        root = Path(__file__).parents[3]
        script = r"""
const fs=require('fs'),vm=require('vm');
const state={features:[{id:1,ring:[[0,0],[100,0],[100,100],[0,100]]}],
  view:{k:1},osnap:true,gridSnap:true,_snapIndex:null,guides:[]};
const c={state,Math,Map,Set,console,isHidden:()=>false,gridStep:()=>10,
  lastDrawingPt:()=>null,selectionIds:()=>[],shiftDown:false,segIntersect:()=>null,
  isAngleInSweep:()=>true,segCircleIntersections:()=>[],circleCircleIntersections:()=>[],
  ctx:{save(){},restore(){}},w2s:(x,y)=>[x,y],cvColor:()=>'',layerOf:()=>({}),
  isLocked:()=>false,LAYERS_V2:[]};
vm.createContext(c);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c);
process.stdout.write(JSON.stringify({vertex:c.snapPoint(3,4),mid:c.snapPoint(50,4)}));
"""
        completed = subprocess.run(
            ["node", "-e", script, str(root / "apps/studio/web/app-snap.js")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        result = json.loads(completed.stdout)
        self.assertEqual("вершина", result["vertex"]["kind"])
        self.assertEqual([0, 0], result["vertex"]["p"])
        self.assertEqual("середина", result["mid"]["kind"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for pages adapter")
    def test_pages_adapter_accepts_geojson_and_rejects_zip(self):
        root = Path(__file__).parents[3]
        script = r"""
global.window = global;
window.location = {href: 'https://example.test/'};
window.fetch = async url => String(url).includes('overpass/api/interpreter')
  ? new Response(JSON.stringify({elements:[{type:'way',id:10,
      tags:{highway:'residential'},geometry:[{lon:37.6151,lat:55.7551},
      {lon:37.6158,lat:55.7558}]}]}), {status: 200})
  : new Response('{}', {status: 200});
window.addEventListener = () => {};
global.document = {addEventListener: () => {}, getElementById: () => null,
  querySelectorAll: () => [], querySelector: () => null,
  head: {appendChild: () => {}}, createElement: () => ({})};
global.localStorage = {getItem: () => null, setItem: () => {}, removeItem: () => {}};
global.GRADO_PAGES_CORE = require(process.argv[1]);
require(process.argv[2]);
(async () => {
  const payload = {type:'FeatureCollection',features:[{type:'Feature',
    properties:{name:'Слой'},geometry:{type:'Point',coordinates:[37.62,55.75]}}]};
  const good = await window.fetch('/api/import-gisogd', {method:'POST',
    headers:{'X-Grado-Filename':encodeURIComponent('opory.geojson')},
    body:JSON.stringify(payload)});
  const goodBody = await good.json();
  const zip = await window.fetch('/api/import-gisogd', {method:'POST',
    headers:{'X-Grado-Filename':'export.zip'},body:'PK'});
  const badCrs = await window.fetch('/api/import-gisogd', {method:'POST',
    headers:{'X-Grado-Filename':'bad.geojson'},body:JSON.stringify({
      type:'FeatureCollection',features:[{type:'Feature',properties:{},
      geometry:{type:'Point',coordinates:[4187000,7509000]}}]})});
  const wrongMethod = await window.fetch('/api/import-gisogd');
  const basemap = await window.fetch('/api/basemap-info');
  const basemapBody = await basemap.json();
  const extent = await window.fetch('/api/fetch-extent', {method:'POST',
    body:JSON.stringify({bbox:[37.615,55.755,37.616,55.756],sources:['osm.roads']})});
  const extentBody = await extent.json();
  process.stdout.write(JSON.stringify({good:good.status,count:goodBody.features.length,
    kind:goodBody.features[0].kind,zip:zip.status,badCrs:badCrs.status,
    wrongMethod:wrongMethod.status,extent:extent.status,
    extentCount:extentBody.groups[0].count,
    origin:[basemapBody.origin_lon,basemapBody.origin_lat]}));
})();
"""
        completed = subprocess.run(
            ["node", "-e", script,
             str(root / "apps/studio/web/pages-core.js"),
             str(root / "apps/studio/web/pages-adapter.js")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(
            {"good": 200, "count": 1, "kind": "generic", "zip": 415,
             "badCrs": 400, "wrongMethod": 405, "extent": 200,
             "extentCount": 1,
             "origin": [37.61429248873298, 55.73988778495185]},
            json.loads(completed.stdout),
        )

    def test_snap_status_and_color_palette_are_discoverable(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")
        style = (root / "apps/studio/web/app-style-ui.js").read_text(encoding="utf-8")
        shell = (root / "apps/studio/web/redesign/shell.css").read_text(encoding="utf-8")
        html = (root / "apps/studio/web/index.html").read_text(encoding="utf-8")

        self.assertIn('class="cfield-action">Палитра</span>', style)
        self.assertIn('aria-label="Открыть палитру цвета"', style)
        self.assertIn('function updateSnapStatus(hit = null)', app)
        self.assertIn('button.setAttribute("aria-pressed", String(state.osnap))', app)
        self.assertIn('#st-snap.snap-active', shell)
        self.assertNotIn('#st-coords,#st-grid,#st-snap{display:none!important}', shell)
        self.assertIn('id="btn-snap" title="Привязки (X)" aria-pressed="true"', html)

    def test_command_palette_matches_web_and_current_ui_availability(self):
        root = Path(__file__).parents[3]
        source = (root / "apps/studio/web/redesign/cmdk.js").read_text(
            encoding="utf-8")
        html = (root / "apps/studio/web/index.html").read_text(encoding="utf-8")

        self.assertIn("const isWeb = !!window.GRADO_STATIC", source)
        self.assertIn("(!isWeb || !i.desktop)", source)
        self.assertIn("(!i.available || i.available())", source)
        self.assertIn('isWeb ? "Сохранить проект (.grado-web.json)"', source)
        self.assertIn('available: () => toolEnabled("polygon")', source)
        self.assertIn('desktop: true', source)
        self.assertIn('aria-controls="cmdk" aria-expanded="false"', html)
        self.assertIn('trigger?.setAttribute("aria-expanded", "true")', source)
        self.assertIn('trigger?.setAttribute("aria-expanded", "false")', source)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for collaboration merge")
    def test_collaboration_merge_applies_remote_and_combines_independent_changes(self):
        root = Path(__file__).parents[3]
        script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[1], "utf8");
const window = { addEventListener() {} };
const context = { window, document: { readyState: "loading" }, console,
  setTimeout, clearTimeout, setInterval, clearInterval, Symbol, Object, JSON };
vm.createContext(context);
vm.runInContext(source, context);
const merge = context.window.Collab._mergeShared;
const base = { features: [{ id: 1, x: 0 }], density: "25",
  layersVisible: { a: true, b: true }, layerFmt: { a: { stroke: "#111" } } };

const remoteOnly = merge(base, JSON.parse(JSON.stringify(base)), {
  ...base, density: "30", layersVisible: { a: true, b: false }
});
if (remoteOnly.merged.density !== "30" || remoteOnly.merged.layersVisible.b !== false)
  throw new Error("remote-only change was lost");

const independent = merge(base, {
  ...base, layersVisible: { a: false, b: true },
  layerFmt: { a: { stroke: "#111", width: 2 } }
}, {
  ...base, layersVisible: { a: true, b: false },
  layerFmt: { a: { stroke: "#222" } }
});
if (independent.merged.layersVisible.a !== false || independent.merged.layersVisible.b !== false)
  throw new Error("independent map edits were not combined");
if (independent.merged.layerFmt.a.stroke !== "#222" || independent.merged.layerFmt.a.width !== 2)
  throw new Error("nested style edits were not combined");

const conflict = merge(base, { ...base, density: "28" }, { ...base, density: "32" });
if (conflict.merged.density !== "28" || conflict.conflicts < 1)
  throw new Error("conflict policy is not local-wins with reporting");
'''
        subprocess.run(
            ["node", "-e", script, str(root / "apps/studio/web/collab.js")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for collaboration races")
    def test_collaboration_ignores_stale_requests_and_advances_merge_base(self):
        root = Path(__file__).parents[3]
        script = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[1], "utf8");
const response = (status, data) => ({
  ok: status >= 200 && status < 300, status, json: async () => data,
});
function load(fetchImpl, initialState) {
  let state = JSON.parse(JSON.stringify(initialState || {}));
  const applied = [];
  const window = {
    addEventListener() {},
    collectState: () => JSON.parse(JSON.stringify(state)),
    collectPersonal: () => ({}),
    applyRestoredState(next) {
      state = JSON.parse(JSON.stringify(next));
      applied.push(state);
    },
    afterExternalApply() {},
  };
  const document = { readyState: "loading", getElementById: () => null };
  const context = { window, document, fetch: fetchImpl, console,
    setTimeout, clearTimeout, setInterval, clearInterval, Symbol, Object, JSON,
    Promise, Number };
  vm.createContext(context);
  vm.runInContext(source, context);
  return { collab: window.Collab, applied, getState: () => state };
}

(async () => {
  // Интервал не должен запускать второй GET, пока первый ещё не завершился.
  let releasePoll;
  let pollCalls = 0;
  const pendingPoll = new Promise(resolve => { releasePoll = resolve; });
  const first = load(async () => {
    pollCalls++;
    await pendingPoll;
    return response(200, { rev: 1, online: [] });
  }, { features: [], density: "25" });
  Object.assign(first.collab, { active: true, pid: "a", rev: 1,
    base: first.getState() });
  const pollOne = first.collab._poll();
  const pollTwo = first.collab._poll();
  if (pollCalls !== 1) throw new Error("overlapping poll request was started");
  releasePoll();
  await Promise.all([pollOne, pollTwo]);

  // Поздний ответ старого проекта не применяется после смены контекста.
  let releaseOld;
  let switchCalls = 0;
  const oldPending = new Promise(resolve => { releaseOld = resolve; });
  const switched = load(async () => {
    switchCalls++;
    if (switchCalls === 1) {
      await oldPending;
      return response(200, { rev: 9, online: [],
        state: { features: [], density: "99" } });
    }
    return response(200, { rev: 2, online: [],
      state: { features: [], density: "30" } });
  }, { features: [], density: "25" });
  Object.assign(switched.collab, { active: true, pid: "old", rev: 1,
    base: switched.getState() });
  const oldPoll = switched.collab._poll();
  switched.collab.projectEpoch++;
  switched.collab.pid = "new";
  switched.collab.base = switched.getState();
  await switched.collab._poll();
  if (switchCalls !== 2 || switched.collab.rev !== 2
      || switched.getState().density !== "30")
    throw new Error("old request blocked the new project's first poll");
  releaseOld();
  await oldPoll;
  if (switched.applied.length !== 1 || switched.collab.rev !== 2)
    throw new Error("old project response mutated the new project");

  // Даже в том же проекте более старая ревизия не откатывает интерфейс.
  const stale = load(async () => response(200, { rev: 4, online: [],
    state: { features: [], density: "4" } }), { features: [], density: "25" });
  Object.assign(stale.collab, { active: true, pid: "a", rev: 5,
    base: stale.getState() });
  await stale.collab._poll();
  if (stale.applied.length || stale.collab.rev !== 5)
    throw new Error("stale revision rolled the project back");

  // Два последовательных 409: второй серверный откат должен сохраниться.
  const base = { features: [], density: "25", layersVisible: { a: true } };
  const local = { features: [], density: "25", layersVisible: { a: false } };
  const posts = [];
  const replies = [
    response(409, { rev: 1, state: {
      features: [], density: "30", layersVisible: { a: true } } }),
    response(409, { rev: 2, state: {
      features: [], density: "25", layersVisible: { a: true } } }),
    response(200, { rev: 3, online: [] }),
  ];
  const pushing = load(async (_url, options) => {
    posts.push(JSON.parse(options.body));
    return replies.shift();
  }, local);
  Object.assign(pushing.collab, { active: true, pid: "a", rev: 0,
    base, dirty: true });
  const pushOne = pushing.collab._pushNow();
  const pushTwo = pushing.collab._pushNow();
  if (pushOne !== pushTwo) throw new Error("callers did not share the active push");
  await pushOne;
  const finalPost = posts.at(-1).state;
  if (finalPost.density !== "25" || finalPost.layersVisible.a !== false)
    throw new Error("consecutive conflict used a stale merge base");
})();
'''
        subprocess.run(
            ["node", "-e", script, str(root / "apps/studio/web/collab.js")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )

    def test_collaboration_surfaces_damaged_project_files_to_admins(self):
        root = Path(__file__).parents[3]
        client = (root / "apps/studio/web/collab.js").read_text(encoding="utf-8")
        server = (root / "apps/studio/server.py").read_text(encoding="utf-8")

        self.assertIn("Number.isInteger(res.data.damaged)", client)
        self.assertIn('class="collab-warning" role="status"', client)
        self.assertIn("include_damaged=True", server)

    def test_layer_style_tabs_follow_keyboard_and_aria_tab_pattern(self):
        root = Path(__file__).parents[3]
        source = (root / "apps/studio/web/app-style-ui.js").read_text(
            encoding="utf-8")

        self.assertIn('role="tabpanel" aria-labelledby="style-mode-single"', source)
        self.assertIn('aria-controls="ls-rules"', source)
        self.assertIn('b.tabIndex = selected ? 0 : -1', source)
        self.assertIn('event.key === "ArrowRight"', source)
        self.assertIn('event.key === "ArrowLeft"', source)
        self.assertIn('event.key === "Home"', source)
        self.assertIn('event.key === "End"', source)

    def test_pages_autosave_prefers_indexeddb_with_localstorage_fallback(self):
        root = Path(__file__).parents[3]
        adapter = (root / "apps/studio/web/pages-adapter.js").read_text(
            encoding="utf-8")

        self.assertIn('const DB_NAME = "grado-studio-pages"', adapter)
        self.assertIn('indexedDB.open(DB_NAME, 1)', adapter)
        self.assertIn('databaseRequest("readwrite"', adapter)
        self.assertIn('await storedProjectSet(AUTOSAVE_KEY, envelope)', adapter)
        self.assertIn('return readStoredJson(key)', adapter)

    def test_layer_and_style_controls_have_specific_accessible_names(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")
        style_ui = (root / "apps/studio/web/app-style-ui.js").read_text(
            encoding="utf-8")
        styles = (root / "apps/studio/web/redesign/studio2.css").read_text(
            encoding="utf-8")

        self.assertIn('aria-label="Показывать слой «${layerTitle}»"', app)
        self.assertIn('aria-label="Действия со слоем «${layerTitle}»"', app)
        self.assertIn('"Переместить выше"', app)
        self.assertIn('"Переместить ниже"', app)
        self.assertIn('aria-label="Включить заливку"', style_ui)
        self.assertIn('aria-label="Удалить правило ${i + 1}"', style_ui)
        self.assertIn('fieldCols.length ? "" : " disabled"', style_ui)
        self.assertNotIn(".style-preview-canvas::before", styles)
        self.assertIn("background:var(--canvas-bg)", styles)

    def test_first_project_steps_and_tep_explain_actual_vs_normative(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")
        styles = (root / "apps/studio/web/redesign/studio2.css").read_text(
            encoding="utf-8")

        self.assertIn("Слой границы готов. Поставьте первую точку", app)
        self.assertIn('aria-label="Следующий шаг проекта"', app)
        self.assertIn("Добавить здание", app)
        self.assertIn("Фактическая посадка", app)
        self.assertIn("Расчётный потенциал", app)
        self.assertIn("Контрольная копия появится перед созданием или открытием другого проекта", app)
        self.assertIn(".props-next-step", styles)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for pages adapter")
    def test_pages_autosave_has_one_primary_and_checkpoint_recovery(self):
        root = Path(__file__).parents[3]
        script = r"""
global.window = global;
window.location = {href: 'https://example.test/'};
window.fetch = async () => new Response('{}', {status: 200});
window.addEventListener = () => {};
global.document = {addEventListener: () => {}, getElementById: () => null,
  querySelectorAll: () => [], head: {appendChild: () => {}}, createElement: () => ({})};
const store = new Map([['grado_studio_v1', JSON.stringify({name:'Старый',features:[]})]]);
global.localStorage = {
  getItem: key => store.has(key) ? store.get(key) : null,
  setItem: (key, value) => store.set(key, String(value)),
  removeItem: key => store.delete(key),
};
global.GRADO_PAGES_CORE = require(process.argv[1]);
require(process.argv[2]);
(async () => {
  const current = {name:'Текущий',features:[{id:1}]};
  await window.fetch('/api/autosave', {method:'POST', body:JSON.stringify(current)});
  const before = await (await window.fetch('/api/autosave/backups')).json();
  await window.fetch('/api/autosave', {method:'POST',
    headers:{'X-Grado-Checkpoint':'1'}, body:JSON.stringify(current)});
  await window.fetch('/api/autosave', {method:'POST', body:JSON.stringify({name:'Новый',features:[]})});
  const after = await (await window.fetch('/api/autosave/backups')).json();
  const backup = await (await window.fetch('/api/autosave/backups/1')).json();
  process.stdout.write(JSON.stringify({
    before: before.backups.length,
    after: after.backups.length,
    backupName: backup.state.name,
    backupCount: backup.state.features.length,
    legacy: store.has('grado_studio_v1'),
    keys: [...store.keys()].sort(),
  }));
})();
"""
        completed = subprocess.run(
            ["node", "-e", script,
             str(root / "apps/studio/web/pages-core.js"),
             str(root / "apps/studio/web/pages-adapter.js")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        result = json.loads(completed.stdout)
        self.assertEqual(0, result["before"])
        self.assertEqual(1, result["after"])
        self.assertEqual("Текущий", result["backupName"])
        self.assertEqual(1, result["backupCount"])
        self.assertFalse(result["legacy"])
        self.assertEqual(
            ["grado_pages_autosave_checkpoint_v1", "grado_pages_autosave_v1"],
            result["keys"],
        )

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for pages adapter")
    def test_pages_autosave_preserves_request_order_when_older_body_is_slow(self):
        root = Path(__file__).parents[3]
        script = r"""
global.window = global;
window.location = {href: 'https://example.test/'};
window.fetch = async () => new Response('{}', {status: 200});
window.addEventListener = () => {};
global.document = {addEventListener: () => {}, getElementById: () => null,
  querySelectorAll: () => [], head: {appendChild: () => {}}, createElement: () => ({})};
const store = new Map();
global.localStorage = {
  getItem: key => store.has(key) ? store.get(key) : null,
  setItem: (key, value) => store.set(key, String(value)),
  removeItem: key => store.delete(key),
};
global.GRADO_PAGES_CORE = require(process.argv[1]);
require(process.argv[2]);
(async () => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const slowBody = {text: async () => {
    await gate;
    return JSON.stringify({name:'Старый', features:[{id:1}]});
  }};
  const oldRequest = window.fetch('/api/autosave', {method:'POST', body:slowBody});
  const newRequest = window.fetch('/api/autosave', {method:'POST',
    body:JSON.stringify({name:'Новый', features:[{id:2}]})});
  release();
  await Promise.all([oldRequest, newRequest]);
  const loaded = await (await window.fetch('/api/autosave')).json();
  process.stdout.write(JSON.stringify({name:loaded.state.name,
    id:loaded.state.features[0].id}));
})();
"""
        completed = subprocess.run(
            ["node", "-e", script,
             str(root / "apps/studio/web/pages-core.js"),
             str(root / "apps/studio/web/pages-adapter.js")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual({"name": "Новый", "id": 2}, json.loads(completed.stdout))

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for pages adapter")
    def test_pages_autosave_retries_indexeddb_after_transient_open_failure(self):
        root = Path(__file__).parents[3]
        script = r"""
global.window = global;
window.location = {href: 'https://example.test/'};
window.fetch = async () => new Response('{}', {status: 200});
window.addEventListener = () => {};
global.document = {addEventListener: () => {}, getElementById: () => null,
  querySelectorAll: () => [], head: {appendChild: () => {}}, createElement: () => ({})};
const data = new Map();
const database = {
  objectStoreNames: {contains: () => false},
  createObjectStore: () => {}, close: () => {},
  transaction: () => {
    const transaction = {};
    const request = work => {
      const result = {};
      setImmediate(() => {
        try { result.result = work(); result.onsuccess && result.onsuccess(); }
        catch (error) { result.error = error; result.onerror && result.onerror(); return; }
        setImmediate(() => transaction.oncomplete && transaction.oncomplete());
      });
      return result;
    };
    transaction.objectStore = () => ({
      get: key => request(() => data.get(key)),
      put: (value, key) => request(() => { data.set(key, value); return key; }),
    });
    return transaction;
  },
};
let openCalls = 0;
global.indexedDB = {open: () => {
  const request = {};
  openCalls++;
  setImmediate(() => {
    if (openCalls === 1) {
      request.error = new Error('temporary');
      request.onerror && request.onerror();
      return;
    }
    request.result = database;
    request.onupgradeneeded && request.onupgradeneeded();
    request.onsuccess && request.onsuccess();
  });
  return request;
}};
global.localStorage = {
  getItem: () => null,
  setItem: () => { throw new Error('quota'); },
  removeItem: () => {},
};
global.GRADO_PAGES_CORE = require(process.argv[1]);
require(process.argv[2]);
(async () => {
  const first = await window.fetch('/api/autosave', {method:'POST',
    body:JSON.stringify({name:'Первый',features:[]})});
  const second = await window.fetch('/api/autosave', {method:'POST',
    body:JSON.stringify({name:'Второй',features:[{id:2}]})});
  const loaded = await (await window.fetch('/api/autosave')).json();
  process.stdout.write(JSON.stringify({first:first.status, second:second.status,
    openCalls, name:loaded.state.name}));
})();
"""
        completed = subprocess.run(
            ["node", "-e", script,
             str(root / "apps/studio/web/pages-core.js"),
             str(root / "apps/studio/web/pages-adapter.js")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(
            {"first": 507, "second": 200, "openCalls": 2, "name": "Второй"},
            json.loads(completed.stdout),
        )

    def test_application_serializes_autosave_and_checkpoint_requests(self):
        root = Path(__file__).parents[3]
        source = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")

        self.assertIn("let saveStateQueue = Promise.resolve()", source)
        self.assertIn("const pending = saveStateQueue.then(", source)
        self.assertIn("saveStateQueue = pending.catch(() => {})", source)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for pages adapter")
    def test_pages_adapter_validates_api_and_storage_failures(self):
        root = Path(__file__).parents[3]
        script = r"""
global.window = global;
window.location = {href: 'https://example.test/'};
window.fetch = async () => new Response('{}', {status: 200});
window.addEventListener = () => {};
global.document = {addEventListener: () => {}, getElementById: () => null,
  querySelectorAll: () => [], head: {appendChild: () => {}}, createElement: () => ({})};
global.localStorage = {getItem: () => null, setItem: () => { throw new Error('quota'); }};
global.GRADO_PAGES_CORE = require(process.argv[1]);
require(process.argv[2]);
(async () => {
  const tep = await window.fetch('/api/tep', {method:'POST', body:'{"features":{}}'});
  const grado = await window.fetch('/api/grado', {method:'POST', body:JSON.stringify({
    features:[{id:1,kind:'boundary',layer_id:'project.territory.boundary',ring:[[0,0],[1e308,0],[0,1]]}]
  })});
  const autosave = await window.fetch('/api/autosave', {method:'POST', body:JSON.stringify({features:[]})});
  process.stdout.write(JSON.stringify({tep:tep.status, grado:grado.status, autosave:autosave.status}));
})();
"""
        completed = subprocess.run(
            ["node", "-e", script,
             str(root / "apps/studio/web/pages-core.js"),
             str(root / "apps/studio/web/pages-adapter.js")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(
            {"tep": 400, "grado": 400, "autosave": 507},
            json.loads(completed.stdout),
        )

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for pages adapter")
    def test_pages_adapter_saves_large_project_in_indexeddb_when_localstorage_is_full(self):
        root = Path(__file__).parents[3]
        script = r"""
global.window = global;
window.location = {href: 'https://example.test/'};
window.fetch = async () => new Response('{}', {status: 200});
window.addEventListener = () => {};
global.document = {addEventListener: () => {}, getElementById: () => null,
  querySelectorAll: () => [], head: {appendChild: () => {}}, createElement: () => ({})};
const data = new Map();
const database = {
  objectStoreNames: {contains: () => false},
  createObjectStore: () => {},
  transaction: () => {
    const transaction = {};
    const request = work => {
      const result = {};
      setImmediate(() => {
        try { result.result = work(); result.onsuccess && result.onsuccess(); }
        catch (error) { result.error = error; result.onerror && result.onerror(); return; }
        setImmediate(() => transaction.oncomplete && transaction.oncomplete());
      });
      return result;
    };
    transaction.objectStore = () => ({
      get: key => request(() => data.get(key)),
      put: (value, key) => request(() => { data.set(key, value); return key; }),
    });
    return transaction;
  },
};
global.indexedDB = {open: () => {
  const request = {};
  setImmediate(() => {
    request.result = database;
    request.onupgradeneeded && request.onupgradeneeded();
    request.onsuccess && request.onsuccess();
  });
  return request;
}};
global.localStorage = {
  getItem: () => null,
  setItem: () => { throw new Error('quota'); },
  removeItem: () => {},
};
global.GRADO_PAGES_CORE = require(process.argv[1]);
require(process.argv[2]);
(async () => {
  const marker = 'x'.repeat(6 * 1024 * 1024);
  const state = {name:'Большой', features:[{id:1, props:{marker}}]};
  const saved = await window.fetch('/api/autosave', {method:'POST', body:JSON.stringify(state)});
  const loaded = await (await window.fetch('/api/autosave')).json();
  process.stdout.write(JSON.stringify({
    status: saved.status,
    name: loaded.state.name,
    size: loaded.state.features[0].props.marker.length,
    databaseKeys: [...data.keys()].sort(),
  }));
})();
"""
        completed = subprocess.run(
            ["node", "-e", script,
             str(root / "apps/studio/web/pages-core.js"),
             str(root / "apps/studio/web/pages-adapter.js")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(
            {"status": 200, "name": "Большой", "size": 6 * 1024 * 1024,
             "databaseKeys": ["grado_pages_autosave_v1"]},
            json.loads(completed.stdout),
        )

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
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        browser = json.loads(completed.stdout)

        sys.path.insert(0, str(root / "apps/studio"))
        import studio_core
        desktop = studio_core.compute_tep(features, params)
        desktop_rows = {row["id"]: row["value"] for row in desktop["results"]}

        self.assertEqual(browser["inputs"], desktop["inputs"])
        self.assertEqual(browser["fact"], desktop["fact"])
        self.assertEqual(browser["rows"], desktop_rows)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser-engine parity")
    def test_browser_tep_matches_desktop_engine_at_numeric_edges(self):
        root = Path(__file__).parents[3]
        scenarios = []
        for width, height, floors, density, ratio in (
            (17.3, 19.1, 2.5, 7.5, 17),
            (123.45, 177.7, "2.5", 33.3, 99.5),
            (50, 60, "invalid", 1, 0),
            (250, 100, 0, 60, 100),
            (100, 100, "1000000000000", "invalid", "invalid"),
            (100, 100, None, None, ""),
        ):
            scenarios.append({
                "features": [
                    {"kind": "boundary", "ring": [
                        [0, 0], [width, 0], [width, height], [0, height],
                    ], "props": {}},
                    {"kind": "restrict", "ring": [
                        [0, 0], [width / 3, 0],
                        [width / 3, height / 4], [0, height / 4],
                    ], "props": {}},
                    {"kind": "building", "ring": [
                        [width * .2, height * .2], [width * .55, height * .2],
                        [width * .55, height * .5], [width * .2, height * .5],
                    ], "props": {"floors": floors}},
                ],
                "params": {
                    "density": density, "ratio_zh": ratio,
                    "percent_vpp": 13.5, "education_zone": 2,
                    "territory_mode": 2, "k_rail": .5, "k_ba": .25,
                },
            })
        script = r"""
const core = require(process.argv[1]);
const scenarios = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(scenarios.map(payload => {
  const out = core.computeTep(payload);
  return {inputs: out.inputs, fact: out.fact,
    rows: Object.fromEntries(out.results.map(row => [row.id, row.value]))};
})));
"""
        completed = subprocess.run(
            ["node", "-e", script, str(root / "apps/studio/web/pages-core.js"),
             json.dumps(scenarios)],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        browser_results = json.loads(completed.stdout)
        sys.path.insert(0, str(root / "apps/studio"))
        import studio_core
        for scenario, browser in zip(scenarios, browser_results):
            desktop = studio_core.compute_tep(
                scenario["features"], scenario["params"])
            expected = {
                "inputs": desktop["inputs"], "fact": desktop["fact"],
                "rows": {row["id"]: row["value"] for row in desktop["results"]},
            }
            self.assertEqual(browser, expected)

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
             json.dumps(payload)], check=True, capture_output=True, text=True, encoding="utf-8",
        )
        report = json.loads(completed.stdout)
        self.assertFalse(report["can_export"])
        self.assertEqual(report["errors"][0]["code"], "invalid_geometry")
        self.assertEqual(report["errors"][0]["feature_ids"], ["2"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser preflight")
    def test_browser_preflight_accepts_supported_import_layers_and_curves(self):
        root = Path(__file__).parents[3]
        script = r"""
const core = require(process.argv[1]);
process.stdout.write(JSON.stringify(core.preflightProject(JSON.parse(process.argv[2]))));
"""
        payload = {"target": "grado", "features": [
            {"id": 1, "kind": "boundary",
             "layer_id": "project.territory.boundary",
             "circle": {"cx": 0, "cy": 0, "r": 100}},
            {"id": 2, "kind": "generic", "layer_id": "source.osm.roads",
             "line": [[0, 0], [10, 10]]},
            {"id": 3, "kind": "generic", "layer_id": "source.nspd.buildings",
             "ring": [[0, 0], [10, 0], [10, 10], [0, 10]]},
        ]}
        completed = subprocess.run(
            ["node", "-e", script, str(root / "apps/studio/web/pages-core.js"),
             json.dumps(payload)], check=True, capture_output=True, text=True, encoding="utf-8",
        )
        report = json.loads(completed.stdout)
        self.assertTrue(report["can_export"])
        self.assertEqual(report["summary"]["exportable"], 3)

        payload["features"][0] = {
            "id": 1, "kind": "boundary",
            "layer_id": "project.territory.boundary",
            "ring": [[0, 0], [1e308, 0], [0, 10]],
        }
        completed = subprocess.run(
            ["node", "-e", script, str(root / "apps/studio/web/pages-core.js"),
             json.dumps(payload)], check=True, capture_output=True, text=True, encoding="utf-8",
        )
        report = json.loads(completed.stdout)
        self.assertFalse(report["can_export"])
        self.assertEqual(report["errors"][0]["code"], "invalid_geometry")

    def test_frontend_defensively_restores_projects_and_async_errors(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")
        styles = (root / "apps/studio/web/style.css").read_text(encoding="utf-8")

        self.assertIn("function normalizeRestoredState", app)
        self.assertIn("hasValidGeometry(feature)", app)
        self.assertIn("Object.create(null)", app)
        self.assertIn('window.addEventListener("unhandledrejection"', app)
        self.assertIn("position: fixed", styles.split("#errbar", 1)[1].split("}", 1)[0])

    def test_tep_requests_cannot_overwrite_newer_project_state(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")

        self.assertIn("let tepRequestVersion = 0", app)
        self.assertIn("tepAbortController?.abort()", app)
        self.assertIn("requestVersion !== tepRequestVersion", app)
        self.assertIn("window.lastTepSignature === requestBody", app)
        self.assertIn("function renderTepUnavailable", app)
        self.assertIn('new Set(["doo_places", "school_places", "policlinic_places"])', app)

    def test_station_requests_cannot_overwrite_changed_or_deleted_redlines(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")

        self.assertIn("const stationRequests = new Map()", app)
        self.assertIn("previous?.controller.abort()", app)
        self.assertIn("stationRequests.get(f.id) !== request", app)
        self.assertIn("state.features.find(feature => feature.id === f.id) !== f", app)
        self.assertIn("stationRequestKey(f) !== key", app)
        self.assertIn("cancelStaleStationRequests()", app)

    def test_geometry_generators_prevent_duplicate_submissions(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")

        self.assertIn("const offsetRequests = new WeakSet()", app)
        self.assertIn("if (offsetRequests.has(f)) return false", app)
        self.assertIn("let bufferRequestPending = false", app)
        self.assertIn("if (bufferRequestPending) return false", app)
        self.assertIn('createButton.textContent = "Создание…"', app)

    def test_style_preview_uses_one_clear_canvas_surface(self):
        root = Path(__file__).parents[3]
        styles = (root / "apps/studio/web/redesign/studio2.css").read_text(
            encoding="utf-8")

        self.assertNotIn(".style-preview-canvas::before", styles)
        self.assertNotIn("linear-gradient(90deg,#f8fafc", styles)
        self.assertIn("background:var(--canvas-bg)", styles)

    def test_source_import_skips_broken_objects_without_aborting_batch(self):
        root = Path(__file__).parents[3]
        app = (root / "apps/studio/web/app.js").read_text(encoding="utf-8")
        imports = (root / "apps/studio/web/app-import.js").read_text(encoding="utf-8")
        data = (root / "apps/studio/web/app-data.js").read_text(encoding="utf-8")

        importer = app.split("function importSourceFeatures(features)", 1)[1].split(
            "const DEFAULT_ALBUM_CONFIG", 1)[0]
        self.assertIn("try {", importer)
        self.assertIn("invalid++", importer)
        self.assertIn("return { added, dup, invalid }", importer)
        self.assertIn("поврежд. пропущено", imports)
        self.assertIn("invalidAll", data)

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


class TestBrowserLineCodeRouting(unittest.TestCase):
    """Браузерная редакция маршрутизирует ОГД по LineCode — как настольная.

    Значения — реальные из выгрузки слоя l1 «Границы УДС»: «1», «-1», «1,-29»,
    «-1,18,29». Раньше веб-версия знала только маршрут по ИМЕНИ слоя, поэтому
    береговая уезжала в «прочие», а многокодовые объекты (34% геометрий)
    теряли половину смысла.
    """

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser-engine test")
    def test_linecode_routes_match_desktop(self):
        root = Path(__file__).parents[3]
        script = r"""
const core = require(process.argv[1]);
const styles = require(process.argv[2]).styles;
core.setLgrCodeStyles(styles);
const r = v => core.lineCodeRoutes({linelineco: v}).map(([c, s, sid]) => [c, s, sid]);
process.stdout.write(JSON.stringify({
  one: r("1"), minus: r("-1"), multi: r("1,-29"), three: r("-1,18,29"),
  garbage: r("NOT_FOUND"), empty: r(""), dup: core.parseLineCodes("1,-1"),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script,
             str(root / "apps/studio/web/pages-core.js"),
             str(root / "core/render/grado_render/styles/moscow_lgr.json")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        out = json.loads(completed.stdout)
        # LineCode даёт ЗНАК и сторону; слой больше НЕ отсюда (слой = источник)
        self.assertEqual(out["one"], [[1, 1, "lgr.kl.uds"]])
        self.assertEqual(out["minus"], [[1, -1, "lgr.kl.uds"]])
        # одна геометрия → два ЗНАКА (слой у обоих — слоя-источника)
        self.assertEqual(out["multi"],
                         [[1, 1, "lgr.kl.uds"], [29, -1, "lgr.tech.zone"]])
        self.assertEqual([c for c, *_ in out["three"]], [1, 18, 29])
        self.assertEqual([s for _, s, *_ in out["three"]], [-1, 1, 1])
        # без LineCode — прежний маршрут по имени слоя, объект не теряется
        self.assertEqual(out["garbage"], [])
        self.assertEqual(out["empty"], [])
        self.assertEqual(out["dup"], [[1, 1]], "дубль кода схлопывается")

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser-engine test")
    def test_import_splits_multicode_and_reports_layers(self):
        root = Path(__file__).parents[3]
        script = r"""
const core = require(process.argv[1]);
core.setLgrCodeStyles(require(process.argv[2]).styles);
const gj = {type: "FeatureCollection", features: [
  {type:"Feature", properties:{linelineco:"1,-29", orbis_id:"a"},
   geometry:{type:"LineString", coordinates:[[37.6,55.75],[37.61,55.75]]}},
  {type:"Feature", properties:{linelineco:"-1", orbis_id:"b"},
   geometry:{type:"LineString", coordinates:[[37.6,55.76],[37.61,55.76]]}},
]};
const out = core.importGisogdExtent(gj, {code:"l1", name:"Границы улично-дорожной сети (красные линии)"},
  [-180,-90,180,90]);
const g = out.groups[0];
process.stdout.write(JSON.stringify({
  count: g.features.length,
  layers: g.features.map(f => f.layer_id),
  sides: g.features.map(f => f.props.line_side),
  kinds: g.features.map(f => f.kind),
  reported: (out.layers || []).map(L => [L.id, L.kind]),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script,
             str(root / "apps/studio/web/pages-core.js"),
             str(root / "core/render/grado_render/styles/moscow_lgr.json")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        out = json.loads(completed.stdout)
        # 2 геометрии → 3 объекта: «1,-29» разделился на красную линию и техзону
        self.assertEqual(out["count"], 3)
        # ВСЕ в слое-источнике (l1), а не в слоях-знаках (требование юзера):
        # различаются знаком (style_id) и видом, а слой один
        self.assertEqual(out["layers"], ["source.gisogd.l1"] * 3)
        self.assertEqual(out["sides"], [1, -1, -1])
        # вид — по СМЫСЛУ кода, а не по виду слоя-источника
        self.assertEqual(out["kinds"], ["redline", "restrict", "redline"])
