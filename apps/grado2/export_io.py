"""Экспорт ГРАДО 2 в обменные форматы: GeoJSON для QGIS (МСК), SHP в раскладке ГИС ОГД (МСК) и таблица ТЭП с перечнем листов в XLSX.

SHP пишет pyshp, остальное — стандартная библиотека. Тексты ошибок — ASCII (ValueError → ответ 400 в server.py)."""

import io
import json
import math
import re
import zipfile
from xml.sax.saxutils import escape

from grado_connectors import crs

MAX_LAYERS = 500
MAX_ROWS = 20000
MAX_FEATURES = 200000                # объектов в одном экспорте GeoJSON (вход и выход после разбора составных геометрий)
MAX_GC_DEPTH = 4                     # вложенность GeometryCollection
MAX_TEXT = 32000                     # предел ячейки Excel — 32767 знаков
_GEOM_DEPTH = {"Point": 0, "LineString": 1, "MultiPoint": 1, "Polygon": 2, "MultiLineString": 2, "MultiPolygon": 3}
_BAD_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


def _num(v, what, lim=1e15):
    """Число из JSON: не bool, не NaN/inf, не огромное (int больше 10**15 — отказ, а не OverflowError)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{what} must be a number")
    if isinstance(v, float) and not math.isfinite(v):
        raise ValueError(f"{what} must be finite")
    if abs(v) > lim:
        raise ValueError(f"{what} is out of range")
    return v


def _text(v, what, required=False):
    if v is None and not required:
        return ""
    if not isinstance(v, str):
        raise ValueError(f"{what} must be a string")
    if len(v) > MAX_TEXT:
        raise ValueError(f"{what} is too long")
    if required and not v.strip():
        raise ValueError(f"{what} must not be empty")
    return v


# ---------- GeoJSON в МСК ----------

def _walk_coords(c, depth, what):
    if depth == 0:
        if not isinstance(c, list) or len(c) < 2:
            raise ValueError(f"{what}: position must be [lon, lat]")
        lon, lat = _num(c[0], what, 180), _num(c[1], what, 90)
        return list(crs.wgs84_to_msk(lon, lat))
    if not isinstance(c, list):
        raise ValueError(f"{what}: coordinates must be an array")
    return [_walk_coords(x, depth - 1, what) for x in c]


def _to_msk(geom, what):
    if geom is None:
        return None
    if not isinstance(geom, dict) or geom.get("type") not in _GEOM_DEPTH:
        raise ValueError(f"{what}: unsupported geometry type")
    return {"type": geom["type"], "coordinates": _walk_coords(geom.get("coordinates"), _GEOM_DEPTH[geom["type"]], what)}


def _parts(geom, depth=0):
    """Геометрия → список простых геометрий: GeometryCollection раскладывается на части (рекурсивно), пустые части отбрасываются."""
    if isinstance(geom, dict) and geom.get("type") == "GeometryCollection":
        gs = geom.get("geometries")
        if not isinstance(gs, list):
            raise ValueError("geometries must be an array")
        if depth >= MAX_GC_DEPTH:
            raise ValueError("GeometryCollection is nested too deeply")
        return [p for g in gs for p in _parts(g, depth + 1)]
    return [] if geom is None else [geom]


def _file_name(name, used):
    base = _BAD_NAME.sub("_", name).strip(" .") [:100] or "layer"
    if base.split(".")[0].strip().upper() in _WIN_RESERVED:       # Windows: CON, NUL, COM1... нельзя как имя файла, в том числе с расширением
        base += "_"
    n, out = 1, base
    while out.lower() in used:
        n += 1
        out = f"{base}_{n}"
    used.add(out.lower())
    return out + ".geojson"


README_GEOJSON = (
    "Координаты в этих файлах — МСК (местная система Москвы, метры), а не широта и долгота.\n"
    "Каждый слой — отдельный файл .geojson в кодировке UTF-8; имена полей сохранены как в ГРАДО 2.\n"
    "Составные геометрии (GeometryCollection) разложены на отдельные объекты с теми же свойствами.\n\n"
    "Как открыть в QGIS: Слой - Добавить слой - Добавить векторный слой, выберите файл. Система координат берётся\n"
    "из самого файла (элемент crs). Если QGIS её не распознал, задайте слою пользовательскую СК «МСК»\n"
    "(Слой - Свойства - Источник - Назначить СК) со строкой PROJ:\n"
    + crs.MSK_PROJ4 + "\n"
)


def _msk_layers(layers):
    """Проверка слоёв выгрузки и перевод в МСК: [(имя, [Feature в МСК])], число пропущенных без геометрии и разложенных составных."""
    if not isinstance(layers, list) or not layers or len(layers) > MAX_LAYERS:
        raise ValueError("layers must be a non-empty array")
    res, total, made, skipped, split = [], 0, 0, 0, 0
    for i, layer in enumerate(layers):
        if not isinstance(layer, dict):
            raise ValueError("layer must be an object")
        name = _text(layer.get("name"), "layer name", True)
        fs = layer.get("features")
        if isinstance(fs, dict):                                 # как слой в /api/export/dxf: FeatureCollection
            fs = fs.get("features")
        if not isinstance(fs, list):
            raise ValueError("features must be an array")
        total += len(fs)
        if total > MAX_FEATURES:
            raise ValueError(f"too many features: at most {MAX_FEATURES} per export")
        feats = []
        for f in fs:
            if not isinstance(f, dict):
                raise ValueError("feature must be an object")
            props = f.get("properties")
            if props is not None and not isinstance(props, dict):
                raise ValueError("properties must be an object")
            geoms = _parts(f.get("geometry"))
            if f.get("geometry") is None or not geoms:
                skipped += 1                                     # без геометрии: в QGIS нечего показывать
                continue
            if isinstance(f.get("geometry"), dict) and f["geometry"].get("type") == "GeometryCollection":
                split += 1
            made += len(geoms)
            if made > MAX_FEATURES:
                raise ValueError(f"too many features: at most {MAX_FEATURES} per export")
            for g in geoms:
                feats.append({"type": "Feature", "properties": props or {}, "geometry": _to_msk(g, f"layer {i}")})
        res.append((name, feats))
    return res, skipped, split


def _notes(readme, skipped, split):
    if skipped or split:
        readme += "\n"
        if split:
            readme += f"Составных геометрий разложено на части: {split}.\n"
        if skipped:
            readme += f"Пропущено объектов без геометрии: {skipped}.\n"
    return readme


def export_geojson(layers):
    """layers: [{"name", "features": [GeoJSON Feature в lon/lat] или FeatureCollection}] → zip: .geojson на слой (МСК) + README.txt."""
    res, skipped, split = _msk_layers(layers)
    out, used = io.BytesIO(), set()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, feats in res:
            fc = {"type": "FeatureCollection", "name": name,
                  "crs": {"type": "name", "properties": {"name": crs.MSK_PROJ4}}, "features": feats}
            z.writestr(_file_name(name, used), json.dumps(fc, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        z.writestr("README.txt", _notes(README_GEOJSON, skipped, split).encode("utf-8"))
    return out.getvalue()


# ---------- SHP в раскладке ГИС ОГД ----------
# Как в выгрузках ГИС ОГД (кэш ~/.grado2/cache/gisogd, 11.10.2026): файлы слоя с русским именем, поля — латиница
# строчными до 10 знаков, кодировка UTF-8 (.cpg), .prj «Moscow_bessel» (тот же текст, что у ОГД). Координаты — МСК
# (железное правило 3). Полный русский заголовок каждого поля — в fields.csv. Пишет библиотека pyshp (MIT).

PRJ_MSK = ('PROJCS["Moscow_bessel",GEOGCS["GCS_Bessel_1841",DATUM["D_Bessel_1841",SPHEROID["Bessel_1841",6377397.155,299.1528128]],'
           'PRIMEM["Greenwich",0.0],UNIT["Degree",0.017453292519943295]],PROJECTION["Transverse_Mercator"],'
           'PARAMETER["False_Easting",0.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",37.5],'
           'PARAMETER["Scale_Factor",1.0],PARAMETER["Latitude_Of_Origin",55.66666666666666],UNIT["Meter",1.0]]')
# поля ГРАДО 2 → короткие имена; остальные — транслитерацией
OGD_FIELDS = {"№": "num", "Вид": "vid", "Площадь, м²": "area_m2", "Мест": "mest", "Норма": "norma", "Типология": "tipologia",
              "Корпус": "korpus", "Этажность": "etazh", "Площадь застройки, м²": "s_zastr_m2", "СПП, м²": "spp_m2",
              "Блок": "blok", "Блоков": "blokov", "1 этаж": "etazh_1", "Ряд": "ryad", "Участок": "uchastok",
              "Места": "mesta", "Дефицит": "deficit", "Площадь, сот.": "area_sot", "Причина": "prichina",
              "Назначение": "naznach", "Высота, м": "vysota_m", "Адрес": "adres", "Название": "nazvanie"}
_TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f",
                "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))
_SHP_KIND = {"Point": "pnt", "MultiPoint": "pnt", "LineString": "lin", "MultiLineString": "lin", "Polygon": "pol", "MultiPolygon": "pol"}


def _field_name(title, used):
    s = OGD_FIELDS.get(title)
    if not s:
        s = "".join(_TR.get(ch, ch) for ch in title.lower())
        s = re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "pole"
        if s[0].isdigit():
            s = "f" + s
    s, n, out = s[:10], 1, s[:10]
    while out in used:
        n += 1
        out = s[:10 - len(str(n)) - 1] + "_" + str(n)
    used.add(out)
    return out


def _ring_area(r):
    return sum(r[k][0] * r[k + 1][1] - r[k + 1][0] * r[k][1] for k in range(len(r) - 1)) / 2


def _shp_rings(g):
    """Полигон → кольца по правилу SHP: внешнее по часовой стрелке, дыры — против."""
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    rings = []
    for p in polys:
        for k, r in enumerate(p):
            r = [list(map(float, q[:2])) for q in r]
            if len(r) < 4:
                continue
            if (_ring_area(r) > 0) == (k == 0):              # площадь > 0 — против часовой
                r = r[::-1]
            rings.append(r)
    return rings


def _field_spec(vals):
    """Тип поля DBF по значениям: числа — N (дробные с 3 знаками), остальное — C до 254 байт."""
    xs = [v for v in vals if v is not None and v != ""]
    if xs and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in xs):
        return ("N", 24, 3) if any(isinstance(v, float) and v != int(v) for v in xs) else ("N", 24, 0)
    return ("C", 254, 0)


def _dbf_value(v, spec):
    if v is None or v == "":
        return None
    if spec[0] == "N":
        return v
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
    b = s.encode("utf-8")[:254]
    return b.decode("utf-8", "ignore")


README_SHP = (
    "Слои ГРАДО 2 в формате ESRI Shapefile, раскладка как в выгрузках ГИС ОГД:\n"
    "- один слой — набор файлов .shp .shx .dbf .prj .cpg с русским именем; слой с точками, линиями и площадями\n"
    "  разложен на три набора с приставками «— точки», «— линии», «— площади»;\n"
    "- имена полей латиницей, до 10 знаков; полное русское название каждого поля — в fields.csv;\n"
    "- кодировка текста UTF-8 (файл .cpg), координаты МСК (как в QGIS), метры; .prj такой же, как у ГИС ОГД.\n"
    "Точный перечень полей для сдачи в ГИС ОГД задаёт её регламент: сверяйте fields.csv с ним.\n"
)


def export_shp(layers):
    """layers как у export_geojson → zip: SHP-набор на слой и вид геометрии (МСК, раскладка ГИС ОГД) + fields.csv + README.txt."""
    import shapefile                                             # pyshp
    res, skipped, split = _msk_layers(layers)
    out, used, rows = io.BytesIO(), set(), [("file", "field", "title")]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, feats in res:
            groups = {}
            for f in feats:
                groups.setdefault(_SHP_KIND[f["geometry"]["type"]], []).append(f)
            for kind, fs in groups.items():
                suffix = "" if len(groups) == 1 else {"pnt": " — точки", "lin": " — линии", "pol": " — площади"}[kind]
                base = _file_name(name + suffix, used)[:-len(".geojson")]
                titles = list(dict.fromkeys(k for f in fs for k in f["properties"]))
                fused, cols = set(), []
                for t in titles:
                    spec = _field_spec([f["properties"].get(t) for f in fs])
                    cols.append((t, _field_name(str(t), fused), spec))
                    rows.append((base, cols[-1][1], str(t)))
                shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
                w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, encoding="utf-8",
                                     shapeType={"pnt": shapefile.MULTIPOINT, "lin": shapefile.POLYLINE, "pol": shapefile.POLYGON}[kind])
                for _, fn, spec in cols:
                    w.field(fn, *spec)
                if not cols:
                    w.field("id", "N", 10, 0)
                for k, f in enumerate(fs):
                    g = f["geometry"]
                    if kind == "pol":
                        w.poly(_shp_rings(g))
                    elif kind == "lin":
                        w.line([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"])
                    else:
                        w.multipoint([g["coordinates"]] if g["type"] == "Point" else g["coordinates"])
                    w.record(*([_dbf_value(f["properties"].get(t), spec) for t, _, spec in cols] if cols else [k + 1]))
                w.close()
                for ext, buf in ((".shp", shp), (".shx", shx), (".dbf", dbf)):
                    z.writestr(base + ext, buf.getvalue())
                z.writestr(base + ".prj", PRJ_MSK)
                z.writestr(base + ".cpg", "UTF-8")
        csv = io.StringIO()
        for r in rows:
            csv.write(";".join('"' + c.replace('"', '""') + '"' for c in r) + "\r\n")
        z.writestr("fields.csv", csv.getvalue().encode("utf-8-sig"))
        z.writestr("README.txt", _notes(README_SHP, skipped, split).encode("utf-8"))
    return out.getvalue()


# ---------- XLSX ----------

_XML_BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def _col(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


class _Sheet:
    """Лист XLSX: строки ячеек (None | число | текст) со стилем; текст пишется inline-строкой и формулой не становится."""

    def __init__(self):
        self.rows, self.width = [], []

    def add(self, cells, style=0):
        self.rows.append([(c, style) for c in cells])
        for i, c in enumerate(cells):
            w = len(str(c)) if isinstance(c, str) else (len(repr(c)) if c is not None else 0)
            while len(self.width) <= i:
                self.width.append(0)
            self.width[i] = max(self.width[i], w)

    def xml(self):
        rows = []
        for r, cells in enumerate(self.rows, start=1):
            cs = []
            for j, (v, st) in enumerate(cells):
                ref, s = f"{_col(j)}{r}", f' s="{st}"' if st else ""
                if v is None or v == "":
                    cs.append(f'<c r="{ref}"{s}/>')
                elif isinstance(v, str):
                    cs.append(f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{escape(_XML_BAD.sub("", v))}</t></is></c>')
                else:
                    cs.append(f'<c r="{ref}"{s} t="n"><v>{v!r}</v></c>')
            rows.append(f'<row r="{r}">{"".join(cs)}</row>')
        cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{min(80, max(10, w + 2))}" customWidth="1"/>' for i, w in enumerate(self.width))
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<cols>{cols}</cols><sheetData>{"".join(rows)}</sheetData></worksheet>')


STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
          '<numFmts count="1"><numFmt numFmtId="164" formatCode="&quot;1:&quot;0"/></numFmts>'
          '<fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><name val="Arial"/></font></fonts>'
          '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
          '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
          '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
          '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
          '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
          '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
          '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
BOLD, SCALE = 1, 2


def _cell(v, what):
    if v is None or isinstance(v, str):
        return _text(v, what)
    return _num(v, what)


def export_xlsx(tep, sheets, note=None, project=None):
    """tep: [{group, title, value, unit}], sheets: [{n, title, format, scale}] → bytes .xlsx (листы «ТЭП» и «Листы»).
    Числа — настоящие числовые ячейки; строки (в том числе начинающиеся с = + - @) — только текст."""
    if not isinstance(tep, list) or not isinstance(sheets, list) or len(tep) > MAX_ROWS or len(sheets) > MAX_ROWS:
        raise ValueError("tep and sheets must be arrays")
    t = _Sheet()
    if project:
        t.add([_text(project, "project")], BOLD)
    if note:
        t.add([_text(note, "note")], BOLD)
    if project or note:
        t.add([])
    t.add(["Показатель", "Значение", "Ед. изм."], BOLD)
    group = None
    for r in tep:
        if not isinstance(r, dict):
            raise ValueError("tep row must be an object")
        g, title = _text(r.get("group"), "group"), _text(r.get("title"), "title", True)
        if g and g != group:
            t.add([g], BOLD)
        group = g or group
        t.add([title, _cell(r.get("value"), "value"), _text(r.get("unit"), "unit")])
    s = _Sheet()
    s.add(["№", "Название", "Формат", "Масштаб"], BOLD)
    for r in sheets:
        if not isinstance(r, dict):
            raise ValueError("sheet row must be an object")
        sc = _cell(r.get("scale"), "scale")
        s.rows.append([(_cell(r.get("n"), "n"), 0), (_text(r.get("title"), "title"), 0), (_text(r.get("format"), "format"), 0),
                       (sc, SCALE if isinstance(sc, (int, float)) else 0)])
        for i, c in enumerate(s.rows[-1]):
            s.width[i] = max(s.width[i], len(str(c[0])))
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in (1, 2))
          + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
          '<sheets><sheet name="ТЭП" sheetId="1" r:id="rId1"/><sheet name="Листы" sheetId="2" r:id="rId2"/></sheets></workbook>')
    wbrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
              '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
              '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in (("[Content_Types].xml", ct), ("_rels/.rels", rels), ("xl/workbook.xml", wb), ("xl/_rels/workbook.xml.rels", wbrels),
                           ("xl/styles.xml", STYLES), ("xl/worksheets/sheet1.xml", t.xml()), ("xl/worksheets/sheet2.xml", s.xml())):
            z.writestr(name, data.encode("utf-8"))
    return out.getvalue()
