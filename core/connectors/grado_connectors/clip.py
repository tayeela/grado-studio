"""Обрезка геометрии GeoJSON по прямоугольнику (w, s, e, n) — shapely 2 (GEOS clip_by_rect).

Вызывают gisogd_api (кэш слоёв ГИС ОГД по области) и apps/grado2/ogd_all.py (данные листа). Полигоны режутся честно:
вогнутый контур распадается на части, дыры остаются дырами; линии — на части по выходам из рамки; точки — фильтром.
Целиком внутри — та же геометрия, целиком снаружи или ничего не осталось — None. Тесты: core/connectors/tests/test_egko.py.
"""
import shapely
from shapely.geometry import mapping, shape

_DIM = {"Point": 0, "MultiPoint": 0, "LineString": 1, "MultiLineString": 1, "Polygon": 2, "MultiPolygon": 2}
_MULTI = {0: "MultiPoint", 1: "MultiLineString", 2: "MultiPolygon"}


def _bbox_of(coords, acc):
    if coords and isinstance(coords[0], (int, float)):
        acc[0] = min(acc[0], coords[0]); acc[1] = min(acc[1], coords[1])
        acc[2] = max(acc[2], coords[0]); acc[3] = max(acc[3], coords[1])
    else:
        for c in coords or ():
            _bbox_of(c, acc)
    return acc


def _lists(c):
    return [_lists(x) for x in c] if isinstance(c[0], (list, tuple)) else [c[0], c[1]]


def _parts(g, dim):
    """Части результата нужной размерности (у полигона по краю рамки GEOS может вернуть и отрезки)."""
    if g.is_empty:
        return []
    if g.geom_type.startswith("Multi") or g.geom_type == "GeometryCollection":
        return [p for sub in g.geoms for p in _parts(sub, dim)]
    return [g] if _DIM.get(g.geom_type) == dim and not (dim == 2 and g.area <= 0) else []


def clip_geometry(geom, box):
    """GeoJSON-геометрия → обрезанная по рамке box = (w, s, e, n) либо None. Целиком внутри — возвращается как есть."""
    if not geom or not geom.get("coordinates"):
        return None
    t = geom.get("type")
    b = _bbox_of(geom["coordinates"], [float("inf"), float("inf"), float("-inf"), float("-inf")])
    if b[0] >= box[0] and b[2] <= box[2] and b[1] >= box[1] and b[3] <= box[3]:
        return geom
    if b[2] < box[0] or b[0] > box[2] or b[3] < box[1] or b[1] > box[3]:
        return None
    if t not in _DIM:
        return geom                                 # GeometryCollection и прочее — как есть (в ЕГКО не встречается)
    dim = _DIM[t]
    g = shapely.force_2d(shape(geom))
    if dim == 0:
        out = shapely.intersection(g, shapely.box(*box))     # точки на самой рамке остаются, как прежде
    else:
        try:
            out = shapely.clip_by_rect(g, *box)
        except shapely.errors.GEOSException:        # кривой контур портала: сначала починить
            out = shapely.clip_by_rect(shapely.make_valid(g), *box)
    parts = _parts(out, dim)
    if not parts:
        return None
    if len(parts) == 1 and not (t == "MultiPoint"):
        return {"type": parts[0].geom_type, "coordinates": _lists(mapping(parts[0])["coordinates"])}
    return {"type": _MULTI[dim], "coordinates": [_lists(mapping(p)["coordinates"]) for p in parts]}
