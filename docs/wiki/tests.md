<!-- генерируется tools/wiki.py — не править руками -->

# Тесты

Запуск всего — `tools/gate.sh` (с E2E: `E2E=1 tools/gate.sh`).

| файл | классы | проверок |
|---|---|---|
| `test_album_lint.py` | AlbumLintTest, WrapTest, TextTest, ExpectTest, PptxTest, FormatLinesTest | 28 |
| `test_album_settings.py` | AlbumSettings | 4 |
| `test_albumgeo_js.py` | AlbumGeoJs | 1 |
| `test_albummeta_js.py` | AlbumMetaJs | 1 |
| `test_blocks.py` | UrbanBlocks | 1 |
| `test_cadcore.py` | CadCore | 1 |
| `test_catalog.py` | Preview, LocalRoutes, HubPreview | 14 |
| `test_collab_js.py` | CollabJs | 1 |
| `test_dxf.py` | DxfRoundTrip, LinetypeProps, AcadNames | 8 |
| `test_e2e.py` | BrowserScenarios | 3 |
| `test_error_texts.py` | ErrorTextsRussian | 1 |
| `test_export.py` | Http, GeoJsonExport, GeoJsonExportHardening, XlsxExport, PlaceByArea | 20 |
| `test_export_shp.py` | ShpExport, FieldNames | 4 |
| `test_file_io.py` | FileImport, PortalFields, Fgistp, SizeCeiling | 21 |
| `test_fonts.py` | Fonts | 9 |
| `test_gpzones_js.py` | GpZonesJs | 1 |
| `test_hub.py` | Base, Accounts, SplitJoin, Projects, Roles, PushConflict, History, Comments, Presence, Events, Teams, Hardening, Stage2, AlbumSection | 152 |
| `test_insol.py` | Insolation | 1 |
| `test_label_qa.py` | LabelQA | 6 |
| `test_labelfmt_js.py` | LabelFmtJs | 1 |
| `test_layout_io.py` | LayoutPrint, LayoutsInProject | 13 |
| `test_legendrules_js.py` | LegendRulesJs | 1 |
| `test_migrate_js.py` | MigrateJs | 1 |
| `test_msk.py` | MskBrowserCopy | 2 |
| `test_next_ui.py` | NextUi | 24 |
| `test_ogd_all.py` | OgdAll, SheetValidation | 16 |
| `test_ogd_warm.py` | Warm, WarmStart | 5 |
| `test_portalgate.py` | PortalGate | 3 |
| `test_print.py` | Print, SatBasemapRobust, Clip, PresentationSlides, TileNegativeCache, SlidePanelsAndPhotos, SlideLabels, LayoutEdits, Pptx, PptKrtSheets, ConceptSheets, Typography, LabelsInFrame, PptxBasemapAndHeavyMaps, CoarseTileNote | 56 |
| `test_railstations_js.py` | RailStationsJs | 1 |
| `test_roadsrc_js.py` | RoadSrcJs | 2 |
| `test_roles_js.py` | RolesJs, LayerRolesApi | 5 |
| `test_rowsgeom_js.py` | RowsGeomJs | 1 |
| `test_sat.py` | FakeTiles, SatExport | 8 |
| `test_server.py` | Grado2Server, Egko, DataBboxT70, Yandex, YandexSatBreaker, SituationPlanSources, RailRoute, Projects, PublicHost, SplitArea, AnyOgdLayer, ProjectVersions, AdminReference, HttpHardening, AccessToken, HubHttp, DxfUidNotExported, NonHubUnchanged, SearchCadastral, SearchKrt, SearchAddress, T61Portal | 161 |
| `test_sheetlayout_js.py` | SheetLayoutJs | 1 |
| `test_sheetmodel_js.py` | SheetModelJs | 1 |
| `test_snap_js.py` | SnapJs | 1 |
| `test_t78_labels.py` | StationNotOnRail, StationNotOnDiagonalRail, StationBestSpot, DistrictBoundaryObstacle, Quotes, LeadersAndCaptions, NestedQuotes | 11 |
| `test_t80_albums_print.py` | OverLayerOrder, TopLayerOverTerritory, LineLabelInsideMap, LegendLineLabel, MapNoteCorners, ConceptSwatchRail, LinetypeMarksThin, YandexSatPath | 17 |
| `test_t82_rail_icons.py` | RailIcons | 9 |
| `test_t86_pptx_speed.py` | FakeEgko, EgkoCache, RasterFill, FontsEmbedded, Progress | 7 |
| `test_t89_labels.py` | StreetGapFromDash, StreetAvoidsViewArrow | 3 |
| `test_tglogin.py` | TgProtocol, HubTgLogin, TgHttp, SiteCookie, SiteHttp | 25 |
| `albumgeo_test.js` | JS | 16 |
| `albummeta_test.js` | JS | 30 |
| `blocks_test.js` | JS | 9 |
| `cadcore_test.js` | JS | 60 |
| `collab_test.js` | JS | 83 |
| `gpzones_test.js` | JS | 18 |
| `insol_test.js` | JS | 22 |
| `labelfmt_test.js` | JS | 51 |
| `legendrules_test.js` | JS | 43 |
| `migrate_test.js` | JS | 22 |
| `railstations_test.js` | JS | 30 |
| `roadclean_test.js` | JS | 27 |
| `roadsrc_test.js` | JS | 15 |
| `roles_test.js` | JS | 22 |
| `sheetlayout_test.js` | JS | 302 |
| `snap_test.js` | JS | 11 |

Группы браузерных сценариев (E2E_ONLY=…): `t52`, `t55`, `t56`, `t59`, `t6`, `t61`, `t62`, `t66`, `t67`, `t71`, `t74`, `t76`, `t80`, `t84`, `t86`, `t88`, `t89`, `t90`, `t91`, `t92`
