"""«Всё из ГИС ОГД в DWG»: все слои портала ИСОГД по области — одним чертежом, слой портала = слой чертежа.

Портал не режет по области (параметр bbox игнорирует, выгрузка «по области» в самом портале — только после входа
через mos.ru, без входа HTTP 401; проверено 25.09.2026). Поэтому каждый слой берётся коннектором GisogdApi: первый раз
целиком с портала (по одному, с паузой), дальше с диска, и режется по рамке здесь. Первая полная выгрузка идёт
долго (сотни слоёв), следующие площадки — из кэша.

Чертёж: DXF R2018 в МСК (как в QGIS), метры; рядом тот же чертёж в DWG, если стоит ODA File Converter.
Атрибуты объекта — в XDATA приложения GISOGD («поле=значение») и в таблицах CSV по слоям (столбец Handle —
дескриптор объекта в чертеже).

Выгрузка идёт фоном, одна за раз: POST /api/ogd_all/start, GET /api/ogd_all/status, GET /api/ogd_all/file,
POST /api/ogd_all/cancel.
"""

import csv
import io
import json
import re
import threading
import time
import zipfile
from datetime import datetime

import ezdxf

from grado_connectors import crs
from grado_connectors.clip import clip_geometry
from grado_connectors.contract import ConnectorError
from grado_connectors.gisogd_api import GisogdApi, catalog

import dxf_io

_BAD = re.compile(r'[<>/\\":;?*|=`]')
_XDATA_LIMIT = 15000            # AutoCAD: не больше 16 КБ XDATA на объект
# Слои, которые портал не отдаёт (HTTP 500 у четырёх слоёв, сети lines_pp/polygon_pp не отдаются и за 4 минуты —
# 25.09.2026), иначе каждая выгрузка ждала бы их заново до 15 минут на слой. Повтор — через сутки.
_FAILED_FILE, _FAILED_TTL = "ogd_all_failed.json", 24 * 3600


def _load_failed(cache_dir):
    try:
        return json.loads((cache_dir / _FAILED_FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _save_failed(cache_dir, failed):
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / _FAILED_FILE).write_text(json.dumps(failed, ensure_ascii=False), "utf-8")
    except OSError:
        pass


def layer_list(cat):
    """Слои каталога (обычные и «виртуальные» — оба выгружаются) с именем слоя чертежа
    «ОГД-<номер раздела ИСОГД>-<папка слоя>-<слой>»: в AutoCAD слои встают по разделам. Путь в каталоге —
    «Слои / 11 Сводный план … / … / папка / слой» или «Территория / ВАО / Районы ВАО / район»."""
    out, used = [], set()
    for x in cat:
        if x.get("type") not in ("layer", "virtual") or not x.get("code"):
            continue
        parts = [p.strip() for p in (x.get("path") or "").split(" / ") if p.strip()]
        if parts and parts[0] == "Слои":
            parts = parts[1:]
        m = re.match(r"(\d+)\s", parts[0]) if len(parts) > 1 else None
        head = [f"{int(m.group(1)):02d}" if m else parts[0]] if len(parts) > 1 else []
        folder = [parts[-2]] if len(parts) > 2 else []
        name = _BAD.sub("_", "-".join(["ОГД", *head, *folder, x.get("name") or x["code"]])).strip()[:200]
        if name.lower() in used:                       # одинаковые имена в разных папках — различаются кодом
            name = f"{name[:180]} ({x['code']})"
        used.add(name.lower())
        out.append({"code": x["code"], "title": x.get("name") or x["code"], "path": x.get("path") or "", "dxf": name})
    return out


def _xdata(props):
    tags, size = [], 0
    for k, v in props.items():
        if v in (None, ""):
            continue
        s = f"{k}={v}".replace("\n", " ")[:250]
        size += len(s.encode("utf-8")) + 4
        if size > _XDATA_LIMIT:
            break
        tags.append((1000, s))
    return tags


def build_drawing(layers, boundary=None):
    """layers: [{"dxf", "title", "code", "features": [GeoJSON WGS84]}] → байты zip: DXF, DWG (если есть ODA), CSV."""
    doc = ezdxf.new("R2018", setup=False)
    doc.header["$INSUNITS"] = 6
    doc.header.custom_vars.append("GRADO_CRS", "MSK")
    doc.appids.new("GISOGD")
    msp = doc.modelspace()
    tables = {}
    for i, layer in enumerate(layers):
        doc.layers.add(layer["dxf"], color=1 + i % 254)
        rows, fields = [], {}
        for f in layer["features"]:
            props = f.get("properties") or {}
            geom = f["geometry"]
            attrs = {"layer": layer["dxf"]}
            ents = []
            if geom["type"] in ("Point", "MultiPoint"):
                for x, y, *_ in ([geom["coordinates"]] if geom["type"] == "Point" else geom["coordinates"]):
                    ents.append(msp.add_point(crs.wgs84_to_msk(x, y), dxfattribs=attrs))
            else:
                for ring, closed in dxf_io._rings(geom):
                    pts = [crs.wgs84_to_msk(x, y) for x, y, *_ in ring]
                    if closed and len(pts) > 1 and pts[0] == pts[-1]:
                        pts = pts[:-1]
                    if len(pts) > 1:
                        ents.append(msp.add_lwpolyline(pts, close=closed, dxfattribs=attrs))
            tags = _xdata(props)
            for e in ents:
                if tags:
                    e.set_xdata("GISOGD", tags)
                rows.append({"Handle": e.dxf.handle, **props})
            fields.update(dict.fromkeys(props))
        tables[layer["dxf"]] = (["Handle", *fields], rows)
    if boundary:
        doc.layers.add("Граница области", color=1)
        for ring, closed in dxf_io._rings(boundary):
            msp.add_lwpolyline([crs.wgs84_to_msk(x, y) for x, y, *_ in ring][:-1], close=True,
                               dxfattribs={"layer": "Граница области"})
    buf = io.StringIO()
    doc.write(buf)
    dxf = buf.getvalue().encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        dwg = None
        if dxf_io.oda_converter():
            try:
                dwg = dxf_io.oda_convert(dxf, "dxf", "DWG")
            except (OSError, ValueError, dxf_io.subprocess.SubprocessError):
                dwg = None
        if dwg:
            z.writestr("gisogd.dwg", dwg)
        z.writestr("gisogd.dxf", dxf)
        for name, (cols, rows) in tables.items():
            s = io.StringIO()
            w = csv.DictWriter(s, cols, delimiter=";", extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
            z.writestr(f"атрибуты/{name}.csv", ("﻿" + s.getvalue()).encode("utf-8"))   # BOM: Excel читает UTF-8
    return out.getvalue(), bool(dwg)


class Job:
    """Одна фоновая выгрузка. Состояние читает GET /api/ogd_all/status."""

    def __init__(self, bbox, boundary, cache_dir, out_dir):
        self.bbox, self.boundary, self.cache_dir, self.out_dir = bbox, boundary, cache_dir, out_dir
        self.state = {"running": True, "done": 0, "total": 0, "current": "", "found": 0, "objects": 0,
                      "errors": [], "file": None, "dwg": False, "message": "Каталог слоёв портала…",
                      "started": time.time()}
        self.cancel = threading.Event()
        self.file = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        st = self.state
        try:
            todo = layer_list(catalog())
            st["total"] = len(todo)

            def tell(code, got, total, stage):
                st["message"] = (f"первая выгрузка слоя целиком: {got / 1e6:.0f}"
                                 + (f" из {total / 1e6:.0f}" if total else "") + " МБ") if stage == "download" else "разбор слоя"
            api = GisogdApi(cache_dir=self.cache_dir, progress=tell)
            failed = _load_failed(self.cache_dir)
            found = []
            for it in todo:
                if self.cancel.is_set():
                    st.update(running=False, message="Выгрузка остановлена.")
                    return
                st.update(current=it["title"], message="")
                bad = failed.get(it["code"])
                if bad and time.time() - bad["at"] < _FAILED_TTL:
                    st["errors"].append(f"{it['title']}: пропущен — портал не отдал слой "
                                        f"{datetime.fromtimestamp(bad['at']):%d.%m %H:%M} ({bad['why']}), повтор через сутки")
                    st["done"] += 1
                    continue
                try:
                    feats = []
                    for f in api.fetch(self.bbox, it["code"])["features"]:
                        g = clip_geometry(f.get("geometry"), self.bbox) if f.get("geometry") else None
                        if g:
                            feats.append({"geometry": g, "properties": f.get("properties") or {}})
                    if feats:
                        found.append({**it, "features": feats})
                        st["found"], st["objects"] = len(found), st["objects"] + len(feats)
                    failed.pop(it["code"], None)
                except ConnectorError as e:             # портал не отдал слой: сутки не ждать его заново
                    st["errors"].append(f"{it['title']}: {e}")
                    failed[it["code"]] = {"at": time.time(), "why": str(e)[:80]}
                    _save_failed(self.cache_dir, failed)
                except Exception as e:                  # один битый слой не останавливает остальные
                    st["errors"].append(f"{it['title']}: {type(e).__name__}: {e}")
                st["done"] += 1
            _save_failed(self.cache_dir, failed)
            st.update(current="", message="Сборка чертежа…")
            body, dwg = build_drawing(found, self.boundary)
            self.out_dir.mkdir(parents=True, exist_ok=True)
            path = self.out_dir / f"gisogd-{datetime.now():%Y%m%d-%H%M%S}.zip"
            path.write_bytes(body)
            self.file = path
            st.update(running=False, file=path.name, dwg=dwg, message="Готово.")
        except Exception as e:
            st.update(running=False, message=f"Выгрузка не удалась: {e}")
