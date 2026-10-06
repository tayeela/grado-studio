<!-- генерируется tools/wiki.py — не править руками -->

# Тесты

Запуск всего — `tools/gate.sh` (с E2E: `E2E=1 tools/gate.sh`).

| файл | классы | проверок |
|---|---|---|
| `test_albumgeo_js.py` | AlbumGeoJs | 1 |
| `test_albummeta_js.py` | AlbumMetaJs | 1 |
| `test_blocks.py` | UrbanBlocks | 1 |
| `test_cadcore.py` | CadCore | 1 |
| `test_collab_js.py` | CollabJs | 1 |
| `test_dxf.py` | DxfRoundTrip, LinetypeProps, AcadNames | 8 |
| `test_e2e.py` | BrowserScenarios | 2 |
| `test_export.py` | Http, GeoJsonExport, GeoJsonExportHardening, XlsxExport, PlaceByArea | 20 |
| `test_file_io.py` | FileImport, PortalFields, Fgistp, SizeCeiling | 21 |
| `test_gpzones_js.py` | GpZonesJs | 1 |
| `test_hub.py` | Base, Accounts, SplitJoin, Projects, Roles, PushConflict, History, Comments, Presence, Events, Teams, Hardening, Stage2, AlbumSection | 152 |
| `test_insol.py` | Insolation | 1 |
| `test_labelfmt_js.py` | LabelFmtJs | 1 |
| `test_legendrules_js.py` | LegendRulesJs | 1 |
| `test_migrate_js.py` | MigrateJs | 1 |
| `test_msk.py` | MskBrowserCopy | 2 |
| `test_ogd_all.py` | OgdAll, SheetValidation | 14 |
| `test_print.py` | Print, SatBasemapRobust, Clip, PresentationSlides, TileNegativeCache, SlidePanelsAndPhotos, SlideLabels, LayoutEdits, Pptx, PptKrtSheets, ConceptSheets, LabelsInFrame, PptxBasemapAndHeavyMaps, CoarseTileNote | 51 |
| `test_railstations_js.py` | RailStationsJs | 1 |
| `test_roadsrc_js.py` | RoadSrcJs | 2 |
| `test_roles_js.py` | RolesJs, LayerRolesApi | 5 |
| `test_sat.py` | FakeTiles, SatExport | 7 |
| `test_server.py` | Grado2Server, Egko, DataBboxT70, Yandex, YandexSatBreaker, SituationPlanSources, RailRoute, Projects, PublicHost, SplitArea, AnyOgdLayer, ProjectVersions, AdminReference, HttpHardening, AccessToken, HubHttp, DxfUidNotExported, NonHubUnchanged, SearchCadastral, SearchKrt, SearchAddress, T61Portal | 151 |
| `test_sheetlayout_js.py` | SheetLayoutJs | 1 |
| `test_t78_labels.py` | StationNotOnRail, StationNotOnDiagonalRail, StationBestSpot, DistrictBoundaryObstacle, Quotes, LeadersAndCaptions, NestedQuotes | 11 |
| `test_t80_albums_print.py` | OverLayerOrder, MapNoteCorners, ConceptSwatchRail, LinetypeMarksThin, YandexSatPath | 10 |
| `test_t82_rail_icons.py` | RailIcons | 9 |
| `test_t86_pptx_speed.py` | FakeEgko, EgkoCache, RasterFill, FontsEmbedded, Progress | 7 |
| `albumgeo_test.js` | JS | 12 |
| `albummeta_test.js` | JS | 24 |
| `blocks_test.js` | JS | 7 |
| `cadcore_test.js` | JS | 60 |
| `collab_test.js` | JS | 83 |
| `gpzones_test.js` | JS | 18 |
| `insol_test.js` | JS | 22 |
| `labelfmt_test.js` | JS | 51 |
| `legendrules_test.js` | JS | 35 |
| `migrate_test.js` | JS | 22 |
| `railstations_test.js` | JS | 30 |
| `roadclean_test.js` | JS | 27 |
| `roadsrc_test.js` | JS | 15 |
| `roles_test.js` | JS | 22 |
| `sheetlayout_test.js` | JS | 302 |

Группы браузерных сценариев (E2E_ONLY=…): `t52`, `t55`, `t56`, `t59`, `t6`, `t61`, `t62`, `t66`, `t67`, `t71`, `t74`, `t76`, `t80`, `t84`, `t86`
