<!-- генерируется tools/wiki.py — не править руками -->

# Маршруты сервера (server.py)

```
ГРАДО 2: локальный сервер.

Отдаёт веб-интерфейс из web/ и два метода:
  POST /api/fetch  {bbox:[w,s,e,n], sources:[ключ,...]} → реальные слои по области
  POST /api/tep    {terr_ha, restrict_ha, spp_new_m2, share, spp_kept_m2} → ТЭП (методика КРТ)
  POST /api/import/files {files:[{name, b64}]} → слои из GeoJSON, KML/KMZ, Shapefile, DXF (WGS84)
  POST /api/export/sat {center, rect, scale | bbox, base} → спутник Яндекса по рамке листа в МСК для AutoCAD (zip: JPG, JGW, DXF)
  POST /api/print/pdf {meta, sheets:[…]} → альбом PDF (листы А3/А1, рамка и штамп ГОСТ), /api/print/pptx → тот же альбом
  редактируемой презентацией PowerPoint, /api/print/svg → лист для просмотра
  GET  /api/fonts → шрифты для подписей (готовые, компьютера, свои), GET /api/fonts/file?f=… → TTF для просмотра,
  POST /api/fonts {name, b64} → свой файл шрифта (fonts.py)
  GET  /api/projects, GET|POST /api/project?name=… | ?autosave=1 → проекты в «Документы/ГРАДО 2»
  GET  /api/project/preview?name=…, /api/projects/trash; POST /api/project/{rename,copy,delete,restore,star} → каталог (catalog.py)

Данные берутся коннекторами ядра (core/connectors), ТЭП — движком ядра (core/compute).
Геометрия на выходе всегда WGS84 (GeoJSON), без пересчёта в СК холста.
HTTP — Starlette под uvicorn, тела запросов проверяет pydantic (раздел «HTTP» ниже).

Запуск: python3 apps/grado2/server.py [порт] [--hub]   (по умолчанию 8650; --hub или GRADO2_HUB=1 — совместный режим)
```

Все упомянутые в коде пути (63):

- `/api/export/`
- `/api/export/dxf`
- `/api/export/geojson`
- `/api/export/sat`
- `/api/export/shp`
- `/api/export/xlsx`
- `/api/fetch`
- `/api/fgistp/docs`
- `/api/fgistp/fetch`
- `/api/fgistp/layers`
- `/api/fonts`
- `/api/fonts/file`
- `/api/health`
- `/api/hub/`
- `/api/hub/guest`
- `/api/hub/invites`
- `/api/hub/join`
- `/api/hub/login`
- `/api/hub/logout`
- `/api/hub/me`
- `/api/hub/password`
- `/api/hub/projects`
- `/api/hub/register`
- `/api/hub/teams`
- `/api/hub/tg/start`
- `/api/hub/users`
- `/api/hub/users/`
- `/api/import/`
- `/api/import/dxf`
- `/api/import/files`
- `/api/layer_roles`
- `/api/login`
- `/api/logout`
- `/api/ogd_all/cancel`
- `/api/ogd_all/file`
- `/api/ogd_all/label_angles`
- `/api/ogd_all/scan`
- `/api/ogd_all/start`
- `/api/ogd_all/status`
- `/api/ogd_all/styles`
- `/api/ogd_all/tree`
- `/api/place`
- `/api/print/`
- `/api/print/layout`
- `/api/print/layout_svg`
- `/api/print/map_svg`
- `/api/print/pdf`
- `/api/print/pptx`
- `/api/print/progress`
- `/api/print/svg`
- `/api/progress`
- `/api/project`
- `/api/project/preview`
- `/api/projects`
- `/api/projects/trash`
- `/api/rail_route`
- `/api/search`
- `/api/search/address`
- `/api/search/cadastral`
- `/api/site`
- `/api/sources`
- `/api/tep`
- `/api/tep/norms`
