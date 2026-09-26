"""«Всё из ГИС ОГД в DWG»: все слои портала ИСОГД по области — одним чертежом, слой портала = слой чертежа.

Портал не режет по области (параметр bbox игнорирует, выгрузка «по области» в самом портале — только после входа
через mos.ru, без входа HTTP 401; проверено 25.09.2026). Поэтому каждый слой берётся коннектором GisogdApi: первый раз
целиком с портала (по одному, с паузой), дальше с диска, и режется по рамке здесь. Первая полная выгрузка идёт
долго (сотни слоёв), следующие площадки — из кэша.

Область — рамка листа (формат × масштаб, как на листе альбома), а не граница территории: чертёж для передачи.
Чертёж: DXF R2018 в МСК (как в QGIS), метры; слои «Рамка листа» и «Граница территории»; рядом тот же чертёж в DWG, если стоит ODA File Converter.
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
from grado_connectors.crs import transform_geom
from grado_connectors.gisogd_api import GisogdApi, catalog

import dxf_io

_BAD = dxf_io._ACAD_BAD                 # те же запрещённые знаки, что у acad_name (с запятой)
_XDATA_LIMIT = 15000            # AutoCAD: не больше 16 КБ XDATA на объект
_XDATA_STR = 250                # и не больше 255 БАЙТ в строке XDATA: русская буква — 2 байта (с 464 байтами AutoCAD не открывал чертёж)
_NAME_MAX = 100                 # имя слоя: AutoCAD допускает 255 знаков, но старые версии и конвертеры считают байты
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


def catalog_tree(cat):
    """Дерево каталога в порядке портала: [{"name", "num", "code"?, "children"}]. num — номер по дереву («11.02.04»):
    под корнем «Слои» — от раздела (номера разделов совпадают с порталом), под «Территория» — с приставкой «Т».
    Без id/parent_id (старый формат каталога) — плоский список слоёв в порядке каталога."""
    if not any(x.get("id") is not None for x in cat):
        return [{"name": x.get("name") or x["code"], "num": f"{i + 1:03d}", "code": x["code"], "path": x.get("path") or "", "children": []}
                for i, x in enumerate(x for x in cat if x.get("type") in ("layer", "virtual") and x.get("code"))]
    ids = {x.get("id") for x in cat}
    kids = {}
    for x in cat:
        kids.setdefault(x.get("parent_id") if x.get("parent_id") in ids else None, []).append(x)

    def build(pid, prefix, path):
        out = []
        for i, x in enumerate(kids.get(pid, [])):
            num = f"{prefix}.{i + 1:02d}" if prefix else f"{i + 1:02d}"
            name = x.get("name") or x.get("code") or ""
            node = {"name": name, "num": num, "path": " / ".join([*path, name]), "children": build(x.get("id"), num, [*path, name])}
            if x.get("type") in ("layer", "virtual") and x.get("code"):
                node["code"] = x["code"]
            out.append(node)
        return out
    roots = []
    for x in kids.get(None, []):
        pre = "" if x.get("name") == "Слои" else "Т"      # «Слои / 11 …» → 11.…, «Территория / ВАО …» → Т.02.…
        roots.append({"name": x.get("name") or "", "num": pre, "path": x.get("name") or "",
                      "children": build(x.get("id"), pre, [x.get("name") or ""])})
    return roots


def layer_list(cat, codes=None):
    """Слои каталога в порядке портала (обычные и «виртуальные») с именем слоя чертежа
    «ОГД <номер по дереву> <папка> - <слой>»: AutoCAD сортирует слои по имени, номер держит порядок ГИС ОГД.
    codes — выгрузить только эти слои."""
    out, used = [], set()

    def walk(nodes, parent):
        for n in nodes:
            if n.get("code") and (codes is None or n["code"] in codes):
                num = n["num"].lstrip(".")
                name = _BAD.sub("_", f"ОГД {num} {parent + ' - ' if parent else ''}{n['name']}").strip()
                if len(name) > _NAME_MAX:                  # длинное — режется имя папки (или она уходит), номер и слой остаются
                    head, tail = f"ОГД {num} ", _BAD.sub("_", n["name"])
                    room = _NAME_MAX - len(head) - len(tail) - 3
                    name = (head + (_BAD.sub("_", parent)[:room].strip() + " - " if room >= 12 else "") + tail)[:_NAME_MAX].strip()
                name = dxf_io.acad_name(name, _NAME_MAX)        # и повторы пробелов из названий портала
                if name.lower() in used:
                    name = f"{name[:_NAME_MAX - len(n['code']) - 3].strip()} ({n['code']})"
                used.add(name.lower())
                out.append({"code": n["code"], "title": n["name"], "path": n.get("path", ""), "dxf": name})
            walk(n["children"], n["name"] if n["children"] else parent)
    walk(catalog_tree(cat), "")
    return out


def _linetypes(props, redln):
    """Код линии ГИС ОГД объекта → имена типов REDLN97 (пусто, если кода нет или типа под код нет)."""
    from grado_render import acad_lin
    code = next((v for k, v in props.items() if k.lower() in ("linelineco", "linecode")), None)
    pairs = acad_lin.parse_line_codes(code)
    return acad_lin.linetypes_for_codes(pairs, redln["lib"]["linetypes"], redln["idx"]) if pairs else []


def _cut_bytes(s, limit):
    """Строка не длиннее limit байт UTF-8, без разрезанной посередине буквы."""
    b = s.encode("utf-8")
    return s if len(b) <= limit else b[:limit].decode("utf-8", "ignore")


def _xdata(props):
    tags, size = [], 0
    for k, v in props.items():
        if v in (None, ""):
            continue
        s = _cut_bytes(f"{k}={v}".replace("\n", " ").replace("\r", " "), _XDATA_STR)
        size += len(s.encode("utf-8")) + 4
        if size > _XDATA_LIMIT:
            break
        tags.append((1000, s))
    return tags


def sheet_box(sheet):
    """Лист в МСК: центр c=[X, Y], размер на местности w × h, м → (x0, y0, x1, y1)."""
    (cx, cy), w, h = sheet["c"], float(sheet["w"]), float(sheet["h"])
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def sheet_bbox_wgs(sheet):
    """Прямоугольник WGS84, накрывающий лист МСК целиком (углы и середины сторон)."""
    x0, y0, x1, y1 = sheet_box(sheet)
    pts = [crs.msk_to_wgs84(x, y) for x in (x0, (x0 + x1) / 2, x1) for y in (y0, (y0 + y1) / 2, y1)]
    return (min(p[0] for p in pts) - 1e-5, min(p[1] for p in pts) - 1e-5,
            max(p[0] for p in pts) + 1e-5, max(p[1] for p in pts) + 1e-5)


_CSS_COLOR = re.compile(r"(?:line|polygon|marker)-(?:color|fill)\s*:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\b")


def portal_color(css):
    """Цвет слоя как на карте портала: первый цвет линии, заливки или значка из его CartoCSS."""
    m = _CSS_COLOR.search(css or "")
    if not m:
        return None
    c = m.group(1)
    return "#" + "".join(ch * 2 for ch in c[1:]) if len(c) == 4 else c


def build_drawing(layers, boundary=None, frame=None, sheet=None, redln=None):
    """layers: [{"dxf", "title", "code", "features": [GeoJSON WGS84], "color"?}] → байты zip: DXF, DWG (если есть ODA), CSV.

    sheet — лист, нарисованный на карте: {c, w, h (МСК, м), paper [ширина, высота] мм, scale, title}. Тогда объекты
    режутся точно по листу в МСК, в модели есть слой «Рамка листа», а в чертеже — лист бумаги нужного формата с
    видовым экраном в масштабе листа (как лист AutoCAD). frame — прежний прямоугольник WGS84 без листа бумаги.
    redln — {"lib", "idx", "colors"} типов линий REDLN97 владельца: у объектов с кодом линии ГИС ОГД (LineCode,
    в .dbf linelineco — линии СПРИТ l1…l57) линия получает тип REDLN97 и цвет ЛГР, как в обычной выгрузке DXF;
    RED_LNS.SHX и REDLN97.LIN кладутся в архив рядом с чертежом."""
    doc = ezdxf.new("R2018", setup=False)
    doc.header["$INSUNITS"] = 6
    doc.header.custom_vars.append("GRADO_CRS", "MSK")
    doc.appids.new("GISOGD")
    msp = doc.modelspace()
    box = sheet_box(sheet) if sheet else None
    shapes = {}
    if redln:
        doc.header["$LTSCALE"] = 1.0
        doc.styles.add_shx("red_lns.shx")
        shapes = {k.upper(): v for k, v in redln["lib"]["shapes"].items()}
    tables = {}
    for i, layer in enumerate(layers):
        la = doc.layers.add(layer["dxf"], color=1 + i % 254)
        if layer.get("color"):
            la.rgb = tuple(int(layer["color"][k:k + 2], 16) for k in (1, 3, 5))
        rows, fields = [], {}
        for f in layer["features"]:
            props = f.get("properties") or {}
            geom = transform_geom(f["geometry"], crs.wgs84_to_msk)
            if box:
                geom = clip_geometry(geom, box)
                if not geom:
                    continue
            attrs = {"layer": layer["dxf"]}
            ents = []
            if geom["type"] in ("Point", "MultiPoint"):
                for x, y, *_ in ([geom["coordinates"]] if geom["type"] == "Point" else geom["coordinates"]):
                    ents.append(msp.add_point((x, y), dxfattribs=attrs))
            else:
                lts = _linetypes(props, redln) if redln else []
                for n in lts:
                    dxf_io._add_linetype(doc, n, redln["lib"]["linetypes"][n], shapes)
                for ring, closed in dxf_io._rings(geom):
                    pts = [(x, y) for x, y, *_ in ring]
                    if closed and len(pts) > 1 and pts[0] == pts[-1]:
                        pts = pts[:-1]
                    if len(pts) < 2:
                        continue
                    for n in lts or [None]:              # несколько кодов у линии — по линии на каждый тип (как в DXF ГРАДО)
                        a = dict(attrs)
                        if n:
                            a["linetype"] = n
                            a["flags"] = dxf_io.PLINEGEN
                            code = dxf_io._code_of(n)
                            if code in redln["colors"]:
                                a["true_color"] = dxf_io._rgb(redln["colors"][code])
                        ents.append(msp.add_lwpolyline(pts, close=closed, dxfattribs=a))
            tags = _xdata(props)
            for e in ents:
                if tags:
                    e.set_xdata("GISOGD", tags)
                rows.append({"Handle": e.dxf.handle, **props})
            fields.update(dict.fromkeys(props))
        if rows:
            tables[layer["dxf"]] = (["Handle", *fields], rows)
    bnd = transform_geom(boundary, crs.wgs84_to_msk) if boundary else None
    bnd = clip_geometry(bnd, box) if bnd and box else bnd      # на листе — только часть границы внутри листа
    if bnd:
        doc.layers.add("Граница территории", color=1)
        for ring, closed in dxf_io._rings(bnd):
            pts = [(x, y) for x, y, *_ in ring]
            msp.add_lwpolyline(pts[:-1] if pts[0] == pts[-1] else pts, close=True, dxfattribs={"layer": "Граница территории"})
    if frame:                                          # рамка листа: по ней обрезаны все слои
        w, s, e, n = frame
        doc.layers.add("Рамка листа", color=5)
        msp.add_lwpolyline([crs.wgs84_to_msk(x, y) for x, y in ((w, s), (e, s), (e, n), (w, n))], close=True,
                           dxfattribs={"layer": "Рамка листа"})
    if sheet:
        x0, y0, x1, y1 = box
        doc.layers.add("Рамка листа", color=5)
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": "Рамка листа"})
        # лист бумаги: формат листа, видовой экран на весь лист в его масштабе (мм бумаги на метр модели = 1000 / M)
        # map — поле карты на бумаге (мм): у листа без штампа бумага с полями, у ГОСТ и слайдов бумага = поле карты
        pw, ph = (float(v) for v in sheet["paper"])
        mw, mh = (float(v) for v in sheet.get("map") or sheet["paper"])
        name = dxf_io.acad_name(f"Лист {sheet.get('title') or ''} 1-{int(sheet['scale'])}", 60)
        # лист по умолчанию «Layout1» переименовывается, а не удаляется: удаление оставляло лист с порядком вкладки 3 и
        # сменой *Paper_Space — структуру, какой AutoCAD сам не пишет
        doc.layouts.rename("Layout1", name)
        lay = doc.layouts.get(name)
        lay.page_setup(size=(pw, ph), margins=(0, 0, 0, 0), units="mm")
        lay.add_viewport(center=(pw / 2, ph / 2), size=(mw, mh), view_center_point=((x0 + x1) / 2, (y0 + y1) / 2),
                         view_height=y1 - y0, dxfattribs={"layer": "Рамка листа"})
        mx, my = (pw - mw) / 2, (ph - mh) / 2
        lay.add_lwpolyline([(mx, my), (mx + mw, my), (mx + mw, my + mh), (mx, my + mh)], close=True, dxfattribs={"layer": "Рамка листа"})
    dxf_io.fit_view(doc)
    if sheet:                                               # открывается на рамке листа, а не на всём, что обрезано вокруг
        x0, y0, x1, y1 = box
        doc.set_modelspace_vport(height=(y1 - y0) * 1.08, center=((x0 + x1) / 2, (y0 + y1) / 2))
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
        if redln and any(lt.dxf.name not in ("ByBlock", "ByLayer", "Continuous") for lt in doc.linetypes):
            z.write(dxf_io.STANDARD / "RED_LNS.SHX", "red_lns.shx")          # без .shx AutoCAD не рисует знаки на линиях
            z.write(dxf_io.STANDARD / "REDLN97.LIN", "REDLN97.LIN")
        for name, (cols, rows) in tables.items():
            s = io.StringIO()
            w = csv.DictWriter(s, cols, delimiter=";", extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
            z.writestr(f"атрибуты/{name}.csv", ("﻿" + s.getvalue()).encode("utf-8"))   # BOM: Excel читает UTF-8
    return out.getvalue(), bool(dwg)


def portal_styles(cache_dir, get=None):
    """styles(code) → CartoCSS слоя портала (GET /layers/{code}/, поле css_style). Кэш на диске 30 дней: цвета нужны
    только слоям с объектами на листе, первый раз — по запросу на слой с паузой."""
    from grado_connectors import gisogd_api
    get = get or gisogd_api._http_get
    path = cache_dir / "ogd_all_styles.json"
    try:
        known = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        known = {}

    def styles(code):
        hit = known.get(code)
        if hit and time.time() - hit["at"] < 30 * 24 * 3600:
            return hit["css"]
        meta = json.loads(get(f"{gisogd_api.BASE}/layers/{code}/", timeout=30))
        known[code] = {"at": time.time(), "css": meta.get("css_style") or ""}
        _save_json(path, known)
        time.sleep(0.3)
        return known[code]["css"]
    return styles


def _save_json(path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    except OSError:
        pass


def scan(bbox, cache_dir, cat):
    """Сколько объектов каждого слоя на листе — только из кэша на диске (портал не трогается): {code: n};
    слоя нет в кэше или он устарел — None (узнать можно только выгрузкой)."""
    api = GisogdApi(cache_dir=cache_dir)
    counts = {}
    for it in layer_list(cat):
        try:
            feats = api._from_lines(it["code"], tuple(bbox))
        except Exception:
            feats = None
        counts[it["code"]] = None if feats is None else sum(1 for f in feats if f.get("geometry") and clip_geometry(f["geometry"], tuple(bbox)))
    return counts


class Job:
    """Одна фоновая выгрузка. Состояние читает GET /api/ogd_all/status."""

    def __init__(self, bbox, boundary, cache_dir, out_dir, name="gisogd", sheet=None, styles=None, codes=None, where="", redln=None):
        """bbox WGS84 или sheet — лист МСК (см. build_drawing); styles(code) → CartoCSS слоя портала или None;
        redln — типы линий REDLN97 (см. build_drawing)."""
        self.sheet, self.styles, self.codes, self.redln = sheet, styles, (set(codes) if codes is not None else None), redln
        bbox = sheet_bbox_wgs(sheet) if sheet else bbox
        self.bbox, self.boundary, self.cache_dir, self.out_dir = bbox, boundary, cache_dir, out_dir
        self.name = re.sub(r'[<>/\\":;?*|=`\s]+', "_", name).strip("_")[:60] or "gisogd"
        self.state = {"running": True, "where": str(where or "")[:200], "done": 0, "total": 0, "current": "", "found": 0, "objects": 0,
                      "errors": [], "file": None, "dwg": False, "message": "Каталог слоёв портала…",
                      "started": time.time()}
        self.cancel = threading.Event()
        self.file = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        st = self.state
        try:
            todo = layer_list(catalog(), self.codes)
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
            if self.styles:
                st.update(current="", message="Цвета слоёв, как на карте портала…")
                for it in found:
                    try:
                        it["color"] = portal_color(self.styles(it["code"]))
                    except Exception:              # без цвета слой остаётся со своим номером цвета
                        pass
            st.update(message="Сборка чертежа…")
            body, dwg = (build_drawing(found, self.boundary, sheet=self.sheet, redln=self.redln) if self.sheet
                         else build_drawing(found, self.boundary, self.bbox, redln=self.redln))
            self.out_dir.mkdir(parents=True, exist_ok=True)
            path = self.out_dir / f"{self.name}-{datetime.now():%Y%m%d-%H%M%S}.zip"
            path.write_bytes(body)
            self.file = path
            st.update(running=False, file=path.name, dwg=dwg, message="Готово.")
        except Exception as e:
            st.update(running=False, message=f"Выгрузка не удалась: {e}")
