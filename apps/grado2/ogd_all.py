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
import math
import re
import threading
import time
import zipfile
from pathlib import Path
from datetime import datetime

import ezdxf
from ezdxf.enums import TextEntityAlignment

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
    """Код линии ГИС ОГД объекта → имена типов линий: REDLN97, а для кодов, которых в REDLN97 нет (29 — технические
    зоны и др.), — штриховой LGR_NN по Эталону ЛГР (redln["dash"], метры). Пусто, если кода нет."""
    from grado_render import acad_lin
    code = next((v for k, v in props.items() if k.lower() in ("linelineco", "linecode")), None)
    pairs = acad_lin.parse_line_codes(code)
    if not pairs:
        return []
    names = acad_lin.linetypes_for_codes(pairs, redln["lib"]["linetypes"], redln["idx"])
    dash = redln.get("dash") or {}
    return names + [f"LGR_{c:02d}" for c, _ in acad_lin.missing_codes(pairs, redln["lib"]["linetypes"], redln["idx"]) if c in dash]


def _lgr_code(name):
    return int(name[4:]) if name.startswith("LGR_") else dxf_io._code_of(name)


# Слой границ → (слой полигонов той же папки ГИС ОГД, код линии, чья сторона смотрит на эти полигоны).
_AREA_OF = {"l18": ("virtual138", 18), "l21": ("virtual139", 21)}


def _polys(features):
    """GeoJSON-объекты → [(bbox, [кольца])] полигонов."""
    out = []
    for f in features:
        g = f.get("geometry") or {}
        for rings in ([g["coordinates"]] if g.get("type") == "Polygon" else g.get("coordinates") or [] if g.get("type") == "MultiPolygon" else []):
            xs = [p[0] for p in rings[0]]
            ys = [p[1] for p in rings[0]]
            out.append(((min(xs), min(ys), max(xs), max(ys)), rings))
    return out


def _inside(x, y, rings):
    """Точка внутри полигона с дырами (чёт-нечет по всем кольцам)."""
    hit = False
    for ring in rings:
        for (x1, y1, *_), (x2, y2, *_) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                hit = not hit
    return hit


def orient_lines(lines, areas, code):
    """Развернуть линии границ так, чтобы сторона кода линии code смотрела на свои полигоны.

    В ГИС ОГД у границы природного комплекса знак кода (18 — объект справа, −18 — слева по ходу линии) местами
    не совпадает с тем, где на самом деле лежит территория: знаки REDLN97 тогда смотрят наружу. Сторона
    проверяется по полигонам того же объекта (слой «Природные и озеленённые территории»): у середин самых длинных
    отрезков берётся точка в 0,5 м слева и справа. Если территория явно с другой стороны, линия разворачивается —
    вместе с ней меняют сторону и остальные коды линии, их взаимное положение сохраняется. Линия с кодом на обе
    стороны (18,−18) или без явного ответа остаётся как есть. Возвращает число развёрнутых линий."""
    polys = _polys(areas)
    grid = {}
    cell = 0.005
    for i, (b, _) in enumerate(polys):
        for gx in range(int(b[0] // cell), int(b[2] // cell) + 1):
            for gy in range(int(b[1] // cell), int(b[3] // cell) + 1):
                grid.setdefault((gx, gy), []).append(i)

    def covered(x, y):
        for i in grid.get((int(x // cell), int(y // cell)), ()):
            b, rings = polys[i]
            if b[0] <= x <= b[2] and b[1] <= y <= b[3] and _inside(x, y, rings):
                return True
        return False

    flipped = 0
    for f in lines:
        props = f.get("properties") or {}
        raw = next((v for k, v in props.items() if k.lower() in ("linelineco", "linecode")), None)
        signs = set()
        for part in str(raw or "").split(","):
            try:
                n = int(float(part))
            except ValueError:
                continue
            if abs(n) == code:
                signs.add(1 if n > 0 else -1)
        g = f.get("geometry") or {}
        if len(signs) != 1 or g.get("type") not in ("LineString", "MultiLineString"):
            continue
        sign = signs.pop()
        parts = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        vote = 0.0
        for line in parts:
            segs = []
            for (x1, y1, *_), (x2, y2, *_) in zip(line, line[1:]):
                kx = 111320 * math.cos(math.radians(y1))            # градусы → метры на месте
                dx, dy = (x2 - x1) * kx, (y2 - y1) * 110540
                ln = math.hypot(dx, dy)
                if ln > 1.5:
                    segs.append((ln, x1, y1, x2, y2, dx, dy, kx))
            for ln, x1, y1, x2, y2, dx, dy, kx in sorted(segs, reverse=True)[:7]:
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                nx, ny = dy / ln * 0.5, -dx / ln * 0.5               # 0,5 м вправо по ходу линии
                right = covered(mx + nx / kx, my + ny / 110540)
                left = covered(mx - nx / kx, my - ny / 110540)
                if right != left:
                    vote += ln if right else -ln
        if vote * sign < 0:
            f["geometry"] = ({"type": "LineString", "coordinates": parts[0][::-1]} if g["type"] == "LineString"
                             else {"type": "MultiLineString", "coordinates": [p[::-1] for p in parts[::-1]]})
            flipped += 1
    return flipped


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


_KIND = {"Point": 1, "MultiPoint": 1, "LineString": 2, "MultiLineString": 2, "Polygon": 3, "MultiPolygon": 3}
_CSS_ORDER = ("text-fill", "line-color", "marker-line-color", "polygon-fill", "marker-fill")


def portal_color(css, geom=None):
    """Цвет слоя как на карте портала из его CartoCSS. geom — тип геометрии слоя: берётся блок стиля
    ['mapnik::geometry_type'=N] этого типа (у линий технических зон в нём красный, а первый цвет в CSS — белая
    заливка значка точки). Внутри — цвет подписи, линии, обводки значка, заливки; белый пропускается."""
    css = css or ""
    m = re.search(r"geometry_type'\s*=\s*%d\]\s*\{([^}]*)\}" % _KIND[geom], css) if geom in _KIND else None
    for part in ([m.group(1)] if m else []) + [css]:
        for prop in _CSS_ORDER:
            for c in re.findall(prop + r"\s*:\s*(#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b)", part):
                c = "#" + "".join(ch * 2 for ch in c[1:]) if len(c) == 4 else c
                if c.lower() != "#ffffff":
                    return c.lower()
    return None


_DECL = re.compile(r"([a-z-]+)\s*:\s*([^;{}]+);")


def _decls(body):
    """Объявления CartoCSS верхнего уровня блока (вложенные блоки — категории, ::text — не входят)."""
    flat, depth = [], 0
    for ch in body:
        depth += ch == "{"
        if depth == 0:
            flat.append(ch)
        depth -= ch == "}"
    return {k: v.strip().strip("'\"") for k, v in _DECL.findall("".join(flat))}


def _hex(v):
    """Цвет CartoCSS (#abc, #aabbcc, rgb(…), rgba(…)) → #aabbcc."""
    r = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", (v or "").strip())
    if r:
        return "#" + "".join(f"{min(255, int(x)):02x}" for x in r.groups())
    m = re.match(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", (v or "").strip())
    if not m:
        return None
    c = m.group(1)
    return "#" + (c if len(c) == 6 else "".join(ch * 2 for ch in c)).lower()


def _num(v, d):
    try:
        return float(str(v).split()[0])
    except (TypeError, ValueError, IndexError):
        return d


# Оформление, заданное владельцем вместо карты портала (и в проекте, и в DXF). rev — номер правки: слой, оформленный
# по прежней правке, в проекте перекрашивается один раз заново.
OWN_STYLE = {"zu_29_06_2021": {"rev": 2, "style": {"fill": "#0000ff", "stroke": "#0000ff", "width": 1.0, "opacity": 0, "hatch": False}}}


# Слой ГИС ОГД → код ЛГР Эталона (приказ Москомархитектуры № 65) по названию слоя и его папки: у зон и надписей
# кода линии в атрибутах часто нет. Порядок важен — частное раньше общего. Код из атрибутов (zonelineco,
# textlineco, linelineco) сильнее названия.
_ETALON_WORDS = [
    ("берегов", 41), ("прибрежн", 17), ("водоохран", 16), ("затоплен", 22),
    ("сильного подтоп", 64), ("сильное подтоп", 64), ("умеренного подтоп", 65), ("умеренное подтоп", 65),
    ("слабого подтоп", 66), ("слабое подтоп", 66), ("приаэродром", 50), ("воздушных подход", 51),
    ("охраняемого объекта", 44), ("1а пояса", 59), ("1б пояса", 60), ("жесткая зона", 15), ("жёсткая зона", 15),
    ("3 пояса", 61), ("iii пояса", 61), ("2 пояса", 14), ("ii пояса", 14), ("1 пояса", 13), ("i пояса", 13),
    ("расчетн", 62), ("расчётн", 62), ("ориентировочн", 63), ("санитарно-защит", 5), ("сзз", 5),
    ("военн", 30), ("радиотехнич", 31), ("охранные зоны оопт", 19), ("охранных зон оопт", 19), ("сооружений связи", 34), ("гидроэнерг", 32), ("окс на оопт", 57), ("режимов особой охраны", 7), ("подзона", 50), ("электроэнерг", 32),
    ("линий связи", 34), ("тепловых сет", 40), ("минимальных расстоян", 39), ("трубопровод", 35),
    ("пунктов наблюд", 37), ("геодезич", 38), ("метрополитен", 36), ("технические зоны", 29), ("технических зон", 29),
    ("памятник", 55), ("размещения окс на оопт", 57), ("резерв", 46), ("особо охраняемых зелен", 47),
    ("режимы особой охраны", 7), ("режимами регулирования", 21), ("природного комплекса", 18), ("пк ", 18),
    ("оопт", 8), ("особо охраняемые природные", 8), ("полос отвода", 6), ("полосы отвода", 6),
    ("внеуличных пешеход", 45), ("линии застройки", 26), ("линий застройки", 26), ("транспортных сооружен", 25),
    ("транспортных коммуникац", 58), ("лесопарков", 49), ("регулирования застройки", 23),
    ("охраняемого природного ландшафта", 11), ("охранных зон объектов культурного", 10), ("защитных зон объектов культурного", 20), ("охранной зоны", 10),
    ("защитные зоны", 20), ("защитная зона", 20), ("охранные зоны объектов культурного", 10),
    ("территорий объектов культурного", 9), ("территории объектов культурного", 9),
]


def etalon_code(name, path="", field=None):
    """Код ЛГР Эталона слоя: из атрибута (field), иначе по названию слоя, затем по названию его папки."""
    try:
        if field not in (None, ""):
            return abs(int(float(str(field).split(",")[0])))
    except ValueError:
        pass
    for head, code in (("1.1.", 1), ("1.2.", 2), ("1.3.", 3), ("1.4.1", 25), ("1.4.", 4)):   # папки красных линий
        if (path or "").startswith(head):
            return code
    for text in (name, path):
        t = (text or "").lower().replace("ё", "е")
        for word, code in _ETALON_WORDS:
            if word.replace("ё", "е") in t:
                return code
    return None


# Оформление зон по Эталону владельца вместо Эталона: береговые полосы — синий штриховой контур без заливки
ETALON_NO_FILL = {41}
ETALON_REV = 3          # номер правки оформления «по Эталону» (см. OWN_STYLE: слой перекрашивается один раз)


_LGR_FILE = Path(__file__).resolve().parents[2] / "core/render/grado_render/styles/moscow_lgr.json"
_LGR_BY_CODE = {}


def lgr_entry(code):
    """Запись Эталона ЛГР по коду (moscow_lgr.json, читается один раз)."""
    if not _LGR_BY_CODE:
        for v in json.loads(_LGR_FILE.read_text("utf-8"))["styles"].values():
            if v.get("lgr_code") is not None:
                _LGR_BY_CODE[int(v["lgr_code"])] = v
    return _LGR_BY_CODE.get(code) if code is not None else None


def dxf_hatch(code):
    """Штриховка зоны Эталона для DXF: (цвет, угол, сетка, шаг мм на бумаге) или None."""
    v = lgr_entry(code)
    h = (v or {}).get("hatch") or {}
    if not h.get("color") or code in ETALON_NO_FILL:
        return None
    return h["color"], int(h["angle"] if h.get("angle") is not None else 45), bool(h.get("cross")), float(h.get("spacing_mm") or 2)


def etalon_style(lgr, geom):
    """Запись Эталона ЛГР (moscow_lgr.json) → оформление слоя ГРАДО 2: контур цветом и штрихом знака, штриховка зоны
    её цветом и углом, подписи («Надписи …») — цветом знака, по углу из ГИС ОГД, без значка точки."""
    stroke = lgr.get("stroke") or "#ff0000"
    dash = [round(v, 2) for v in lgr.get("dash_px") or []]
    width = max(1.0, round(float(lgr.get("width_px") or 1), 2))
    if geom == "point":
        return {"fill": stroke, "stroke": stroke, "width": 0, "opacity": 1, "marker": False,
                "label": "text", "labelSize": 11, "labelColor": stroke, "labelAngle": "_angle"}
    if geom == "line":
        return {"fill": stroke, "width": width, "dash": dash}
    out = {"fill": stroke, "stroke": stroke, "strokeOwn": True, "width": width, "dash": dash, "opacity": 0, "hatch": False}
    h = lgr.get("hatch") or {}
    if int(lgr.get("lgr_code") or 0) not in ETALON_NO_FILL:
        if h.get("color"):
            ang = str(int(h["angle"] if h.get("angle") is not None else 45))
            out.update(fill=h["color"], hatch=True, hatchPat=("x" + ("45" if ang in ("45", "135") else "0")) if h.get("cross") else ang,
                       hatchStep=round(float(h.get("spacing_px") or 8), 1))
        elif lgr.get("fill"):
            out.update(fill=lgr["fill"], opacity=0.35)
    return out


def layer_style(code, css, geom):
    """Оформление слоя портала в проекте: своё (OWN_STYLE), иначе — как на карте портала."""
    own = OWN_STYLE.get(code)
    return dict(own["style"]) if own and geom == "poly" else portal_style(css, geom)


def portal_style(css, geom):
    """CartoCSS слоя портала ГИС ОГД → оформление слоя ГРАДО 2 (как на карте портала): заливка и её прозрачность,
    контур и толщина, штриховка (polygon-pattern-file; угол — из описания условного знака в комментарии),
    категории по полю ([поле='значение'] { … }), подпись (text-name). geom — "poly" | "line" | "point".
    Пусто, если в стиле нет цвета."""
    css = css or ""
    angle = re.search(r"угол наклона\s*(\d+)", css)
    css = re.sub(r"//[^\n]*", "", css)
    n = {"point": 1, "line": 2, "poly": 3}[geom]
    m = re.search(r"geometry_type'\s*=\s*%d\]\s*\{" % n, css)
    if m:                                               # блок своего типа геометрии: до парной скобки
        depth, i = 1, m.end()
        while i < len(css) and depth:
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        body = css[m.end():i - 1]
    else:
        body = css
        while True:                                     # внешние обёртки [zoom>14] { … } снимаются
            w = re.fullmatch(r"\s*\[[^\]]*zoom[^\]]*\]\s*\{(.*)\}\s*", body, re.S)
            if not w:
                break
            body = w.group(1)
    d = _decls(body)
    text = re.search(r"text-name\s*:\s*\[(\w+)\]", body)
    text_fill = _hex((re.search(r"text-fill\s*:\s*([^;]+);", body) or [None, ""])[1])
    out = {}
    if geom == "poly":
        fill, stroke = _hex(d.get("polygon-fill")), _hex(d.get("line-color"))
        hatch = "polygon-pattern-file" in d
        fill = fill or (stroke if hatch else None)      # узор-картинка без цвета — штриховка цветом контура
        op = _num(d.get("polygon-opacity"), 1.0)
        if not fill and not stroke:
            return {}
        out = {"fill": fill or stroke or "#9aa1a8", "stroke": stroke or fill, "width": round(_num(d.get("line-width"), 1.0), 2),
               "opacity": round(op, 2) if fill else 0}
        if not stroke and not hatch:
            out["width"] = 0.8
        if hatch:
            out.update(hatch=True, hatchPat={"0": "0", "90": "90", "135": "135"}.get(angle.group(1) if angle else "", "45"))
        elif fill and op >= 0.99:
            out["opacity"] = 0.35                       # сплошная заливка портала прозрачнее: под ней видно подложку
    elif geom == "line":
        c = _hex(d.get("line-color"))
        if not c:
            return {}
        out = {"fill": c, "width": round(_num(d.get("line-width"), 1.0), 2)}
    else:
        c = text_fill or _hex(d.get("marker-line-color")) or _hex(d.get("marker-fill"))
        if not c or c == "#ffffff":
            return {}
        out = {"fill": c, "stroke": "#ffffff", "width": 0.5, "opacity": 1}
    cats = re.findall(r"\[\s*(\w+)\s*=\s*['\"]([^'\"]*)['\"]\s*\]\s*\{([^{}]*)\}", body)
    colors = {}
    for field, value, block in cats:
        dd = _decls(block)
        c = _hex(dd.get("polygon-fill") if geom == "poly" else dd.get("line-color")) or _hex(dd.get("line-color")) or _hex(dd.get("text-fill"))
        if c:
            colors.setdefault(field, {})[value] = c
    if colors:
        field = max(colors, key=lambda k: len(colors[k]))
        out.update(mode="cat", cat={"field": field, "colors": colors[field], "off": []})
    if text and geom == "point":                        # подписи площадных слоёв портал даёт только вблизи — не включаются
        out.update(label=text.group(1), labelSize=11)
    return out


def label_siblings(cat, code):
    """Слои той же папки ГИС ОГД, что и слой надписей code (границы и зоны), — по ним подпись ставится вдоль линии."""
    me = next((x for x in cat if x.get("code") == code), None)
    if not me:
        return []
    return [x["code"] for x in cat if x.get("parent_id") == me.get("parent_id") and x["code"] != code
            and x.get("type") in ("layer", "virtual") and not str(x.get("name", "")).lower().startswith("надпис")]


def label_angles(points, features, tol=30.0):
    """Угол подписи вдоль ближайшей линии: points — [(lon, lat)], features — GeoJSON соседних слоёв (границы — линии,
    зоны — их контуры). Для каждой точки — угол ближайшего отрезка не дальше tol метров, в градусах против часовой
    стрелки от востока, развёрнутый так, чтобы подпись не стояла вверх ногами (−90…90]; None — линии рядом нет."""
    if not points:
        return []
    lat0 = sum(p[1] for p in points) / len(points)
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110540
    cell, grid = 50.0, {}
    for f in features:
        g = f.get("geometry") or {}
        t, c = g.get("type"), g.get("coordinates")
        lines = ([c] if t == "LineString" else c if t == "MultiLineString" else
                 [r for r in c] if t == "Polygon" else [r for p in c for r in p] if t == "MultiPolygon" else [])
        for line in lines:
            for (x1, y1, *_), (x2, y2, *_) in zip(line, line[1:]):
                a, b = (x1 * kx, y1 * ky), (x2 * kx, y2 * ky)
                for gx in range(int(min(a[0], b[0]) // cell), int(max(a[0], b[0]) // cell) + 1):
                    for gy in range(int(min(a[1], b[1]) // cell), int(max(a[1], b[1]) // cell) + 1):
                        grid.setdefault((gx, gy), []).append((a, b))
    out = []
    for lon, lat, *_ in points:
        x, y = lon * kx, lat * ky
        best = None
        for gx in range(int(x // cell) - 1, int(x // cell) + 2):
            for gy in range(int(y // cell) - 1, int(y // cell) + 2):
                for a, b in grid.get((gx, gy), ()):
                    dx, dy = b[0] - a[0], b[1] - a[1]
                    L2 = dx * dx + dy * dy
                    if L2 < 1e-6:
                        continue
                    t = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
                    d = math.hypot(a[0] + t * dx - x, a[1] + t * dy - y)
                    if d <= tol and (best is None or d < best[0]):
                        best = (d, dx, dy)
        if best is None:
            out.append(None)
            continue
        ang = math.degrees(math.atan2(best[2], best[1]))
        out.append(round((ang + 90) % 180 - 90 if (ang + 90) % 180 - 90 != -90 else 90, 2))
    return out


def set_label_angles(features, siblings):
    """Подписям (точкам с text) — угол вдоль ближайшей границы своей папки в поле _angle (градусы против часовой)."""
    pts = [(i, f["geometry"]["coordinates"]) for i, f in enumerate(features)
           if (f.get("geometry") or {}).get("type") == "Point" and str((f.get("properties") or {}).get("text") or "").strip()]
    for (i, _), ang in zip(pts, label_angles([p for _, p in pts], siblings)):
        if ang is not None:
            features[i].setdefault("properties", {})["_angle"] = ang
    return features


def _zone_hatch(msp, geom, layer, sheet):
    """Штриховка зоны по Эталону ЛГР (HATCH): цвет штриховки знака, угол, шаг — мм на бумаге в масштабе листа
    (без листа — М 1:2000, масштаб Эталона). ANSI31 — косые через 3,175 единицы под 45°, поворачивается до угла знака."""
    color, angle, cross, step = layer["hatch"]
    scale = float(sheet["scale"]) if sheet else 2000.0
    h = msp.add_hatch(dxfattribs={"layer": layer["dxf"]})
    h.rgb = tuple(int(color[k:k + 2], 16) for k in (1, 3, 5))
    h.set_pattern_fill("ANSI37" if cross else "ANSI31", scale=step * scale / 1000 / 3.175, angle=angle - 45)
    for rings in ([geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]):
        for ring in rings:
            pts = [(x, y) for x, y, *_ in ring]
            if len(pts) >= 3:
                h.paths.add_polyline_path(pts, is_closed=True)
    return h


def _label(msp, xy, text, props, attrs):
    """Подпись ГИС ОГД (слои «Надписи …»: text, textangle, textheight) → TEXT по центру точки. Угол в ГИС ОГД идёт
    по часовой стрелке; подпись разворачивается так, чтобы не стоять вверх ногами. Высота — textheight ГИС ОГД
    как есть (метры на местности): подписи расставлены порталом под неё, крупнее они налезают друг на друга."""
    try:                                               # вдоль своей границы (_angle), иначе — угол ГИС ОГД
        ang = float(props["_angle"]) if props.get("_angle") is not None else -float(props.get("textangle") or 0)
    except (TypeError, ValueError):
        ang = 0.0
    ang = (ang + 90) % 180 - 90
    try:
        h = float(props.get("textheight") or 0) or 4.0
    except (TypeError, ValueError):
        h = 4.0
    t = msp.add_text(text[:250], height=h, rotation=ang, dxfattribs={**attrs, "style": "GISOGD"})
    t.set_placement(xy, align=TextEntityAlignment.MIDDLE_CENTER)
    return t


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
    doc.styles.add("GISOGD", font="arial.ttf")             # кириллица: у стандартного txt.shx её нет
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
                text = str(props.get("text") or "").strip()
                for x, y, *_ in ([geom["coordinates"]] if geom["type"] == "Point" else geom["coordinates"]):
                    if text:                                   # слои «Надписи …»: подпись линии на её месте
                        ents.append(_label(msp, (x, y), text, props, attrs))
                    else:
                        ents.append(msp.add_point((x, y), dxfattribs=attrs))
            else:
                lts = _linetypes(props, redln) if redln else []
                if redln and not lts and layer.get("lgr") and geom["type"] in ("Polygon", "MultiPolygon") \
                        and layer["lgr"] not in (1, 2, 3, 4):    # контур зоны — штрихом знака Эталона (у линий — свой код)
                    lts = _linetypes({"linecode": str(layer["lgr"])}, redln)
                for n in lts:
                    if n in doc.linetypes:
                        continue
                    if n.startswith("LGR_"):
                        d = redln["dash"][int(n[4:])]
                        doc.linetypes.add(n, pattern=[sum(d)] + [v if k % 2 == 0 else -v for k, v in enumerate(d)],
                                          description=f"ЛГР код {int(n[4:])}")
                    else:
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
                            code = _lgr_code(n)
                            if code in redln["colors"]:
                                a["true_color"] = dxf_io._rgb(redln["colors"][code])
                        ents.append(msp.add_lwpolyline(pts, close=closed, dxfattribs=a))
            if layer.get("hatch") and geom["type"] in ("Polygon", "MultiPolygon"):
                ents.append(_zone_hatch(msp, geom, layer, sheet))
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
            cat = catalog()
            todo = layer_list(cat, self.codes)
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
            if self.redln:                              # знаки границ ПК — в сторону своих полигонов
                st.update(current="", message="Стороны границ природного комплекса…")
                have = {it["code"]: it for it in found}
                for code, (area, lc) in _AREA_OF.items():
                    if code in have:
                        try:
                            feats = have[area]["features"] if area in have else api.fetch(self.bbox, area)["features"]
                            orient_lines(have[code]["features"], feats, lc)
                        except ConnectorError:          # полигонов нет — стороны остаются, как в ГИС ОГД
                            pass
            st.update(current="", message="Сборка чертежа…")
            have = {it["code"]: it for it in found}
            for it in found:                            # подписи — вдоль границ своей папки
                if any(str((f.get("properties") or {}).get("text") or "").strip() for f in it["features"][:20]):
                    sib = []
                    for c in label_siblings(cat, it["code"]):
                        try:
                            sib += have[c]["features"] if c in have else api.fetch(self.bbox, c)["features"]
                        except ConnectorError:
                            pass
                    set_label_angles(it["features"], sib)
            for it in found:                            # знак Эталона ЛГР слоя: цвет слоя и тип контура зон
                field = next((p.get("zonelineco") or p.get("textlineco") for p in (f["properties"] for f in it["features"][:50])
                              if p.get("zonelineco") or p.get("textlineco")), None)
                parent = it.get("path", "").rsplit(" / ", 2)[-2] if " / " in it.get("path", "") else ""
                it["lgr"] = etalon_code(it["title"], parent, field)
                if any((f.get("geometry") or {}).get("type") in ("Polygon", "MultiPolygon") for f in it["features"][:20]):
                    it["hatch"] = dxf_hatch(it["lgr"])   # зона Эталона — со штриховкой, как на карте
            if self.styles:
                st.update(current="", message="Цвета слоёв, как на карте портала…")
                for it in found:
                    try:
                        own = OWN_STYLE.get(it["code"])
                        lgr_color = (self.redln or {}).get("colors", {}).get(it["lgr"]) if it.get("lgr") else None
                        it["color"] = own["style"]["stroke"] if own else lgr_color or portal_color(self.styles(it["code"]), it["features"][0]["geometry"]["type"])
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
