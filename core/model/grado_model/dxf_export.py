"""Экспорт проекта в DXF R12 (AC1009) — читается AutoCAD/nanoCAD/QGIS.

R12 выбран сознательно: его понимает всё, что открывает DXF вообще.
Кириллица в подписях — через кодировку cp1251 и $DWGCODEPAGE ANSI_1251.
Полигоны и линии — POLYLINE/VERTEX/SEQEND (замкнутость флагом 70),
подписи — TEXT в центроиде, точечные объекты — POINT.
"""

# Слой DXF и цвет ACI по коду классификатора. Значения по умолчанию
# синхронны со styles/default.json (единый источник, шаг 3): приложение
# передаёт актуальную карту слоёв параметром layers= в project_to_dxf,
# так что правка JSON меняет и DXF; эта константа — автономный дефолт
# для прямого использования модели (демо/тесты) без пакета render.
LAYERS = {
    "terr.boundary": ("GRANICA_TERRITORII", 7),
    "terr.restrict": ("OGRANICHENIYA", 1),
    "cad.parcel": ("UCHASTKI_EGRN", 8),
    "cad.zouit": ("ZOUIT", 5),
    "tp.func_zone": ("FUNKC_ZONY", 2),
    "pp.red_line": ("KRASNYE_LINII", 1),
    "pp.placement_zone": ("ZONY_OKS", 6),
    "oks.building": ("ZDANIYA", 30),
    "uds.road_axis": ("UDS_OSI", 8),
    "social.object": ("SOC_OBEKTY", 5),
    "annot.dim": ("RAZMERY", 3),   # размерные линии студии (аннотация)
}
FALLBACK_LAYER = ("PROCHEE", 7)

LABEL_ATTRS = ("zone_title", "cad_num", "purpose", "floors", "kind", "name")


def _g(code, value):
    return f"{code}\n{value}\n"


def _centroid(ring):
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(a) < 1e-12:
        return ring[0]
    return (cx / (3 * a), cy / (3 * a))


def _polyline(layer, pts, closed):
    out = _g(0, "POLYLINE") + _g(8, layer) + _g(66, 1) + _g(70, 1 if closed else 0)
    for x, y in pts:
        out += (_g(0, "VERTEX") + _g(8, layer)
                + _g(10, f"{x:.4f}") + _g(20, f"{y:.4f}") + _g(30, "0.0"))
    return out + _g(0, "SEQEND")


def _text(layer, x, y, value, height=2.5):
    return (_g(0, "TEXT") + _g(8, layer)
            + _g(10, f"{x:.4f}") + _g(20, f"{y:.4f}") + _g(30, "0.0")
            + _g(40, height) + _g(1, str(value)[:64]))


def _label(attrs):
    for key in LABEL_ATTRS:
        v = attrs.get(key)
        if v is not None and v != "":
            return v
    return None


def project_to_dxf(project, label_height=2.5, layers=None, fallback_layer=None):
    """DXF R12 из слоёв проекта. Возвращает bytes (cp1251).

    layers — карта код классификатора → (имя слоя DXF, цвет ACI); если не
    передана, берётся автономный дефолт LAYERS. Приложение подаёт карту,
    построенную из styles/default.json, — тогда правка JSON меняет DXF."""
    layers = LAYERS if layers is None else layers
    fallback_layer = FALLBACK_LAYER if fallback_layer is None else fallback_layer
    used = []
    entities = ""
    for info in project.layers():
        layer, _color = layers.get(info["code"], fallback_layer)
        if info["code"] in layers and info["code"] not in [u[0] for u in used]:
            used.append((info["code"], layers[info["code"]]))
        for f in project.layer(info["code"]).features():
            geom = f["geom"]
            if not geom:
                continue
            t = geom["type"]
            if t == "Point":
                x, y = geom["coordinates"]
                entities += _g(0, "POINT") + _g(8, layer) \
                    + _g(10, f"{x:.4f}") + _g(20, f"{y:.4f}") + _g(30, "0.0")
                label = _label(f["attrs"])
                if label is not None:
                    entities += _text(layer, x + label_height, y, label, label_height)
            elif t == "LineString":
                entities += _polyline(layer, geom["coordinates"], closed=False)
            else:
                polys = [geom["coordinates"]] if t == "Polygon" else geom["coordinates"]
                for poly in polys:
                    ring = poly[0]
                    ring = ring[:-1] if ring[0] == ring[-1] else ring
                    entities += _polyline(layer, ring, closed=True)
                    label = _label(f["attrs"])
                    if label is not None:
                        cx, cy = _centroid([tuple(p) for p in ring])
                        entities += _text(layer, cx, cy, label, label_height)

    layer_defs = list(dict.fromkeys(list(layers.values()) + [fallback_layer]))
    layer_table = _g(0, "TABLE") + _g(2, "LAYER") + _g(70, len(layer_defs))
    for name, color in layer_defs:
        layer_table += (_g(0, "LAYER") + _g(2, name) + _g(70, 0)
                        + _g(62, color) + _g(6, "CONTINUOUS"))
    layer_table += _g(0, "ENDTAB")

    ltype_table = (_g(0, "TABLE") + _g(2, "LTYPE") + _g(70, 1)
                   + _g(0, "LTYPE") + _g(2, "CONTINUOUS") + _g(70, 0)
                   + _g(3, "Solid line") + _g(72, 65) + _g(73, 0) + _g(40, "0.0")
                   + _g(0, "ENDTAB"))

    dxf = (_g(0, "SECTION") + _g(2, "HEADER")
           + _g(9, "$ACADVER") + _g(1, "AC1009")
           + _g(9, "$DWGCODEPAGE") + _g(3, "ANSI_1251")
           + _g(0, "ENDSEC")
           + _g(0, "SECTION") + _g(2, "TABLES")
           + ltype_table + layer_table
           + _g(0, "ENDSEC")
           + _g(0, "SECTION") + _g(2, "ENTITIES")
           + entities
           + _g(0, "ENDSEC")
           + _g(0, "EOF"))
    return dxf.encode("cp1251", errors="replace")
