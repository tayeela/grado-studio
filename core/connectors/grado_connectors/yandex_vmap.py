"""Яндекс Карты: векторные тайлы vmap3 (обратная разработка, сверено 23.09.2026) — только стандартная библиотека.

Формат (проверено на тайлах района Владыкино):
  * тайл — protobuf без схемы: поле 2 — все координаты тайла (varint, zigzag, дельты по x и y), поле 3 — длины частей,
    поле 4 — наборы имён атрибутов, поле 5 — значения атрибутов, поле 6 — слой (имя и объекты);
  * значение атрибута: 1 — строка, 8 — строка во вложенном сообщении, 5 — float32, 2 — целое со знаком (zigzag:
    высота 6 в тайле — это 3 м, z_level 1 — это −1; feature_id совпадает с id объекта только после раскодирования),
    3 и 4 — целые без знака, 6 — флаг;
  * сетка тайлов — EPSG:3395 (эллипсоидальный Меркатор), НЕ 3857: иначе всё уезжает на ~20 км;
  * координаты в тайле — сетка 8192 с началом в центре, ось y вниз; 4095 на правом и нижнем краю означает 4096;
  * id объекта один и тот же во всех тайлах: куски здания на соседних тайлах собираются по id. У зданий id объединяет
    части комплекса (башни и стилобат); у каждой части свои высота, назначение и feature_id, поэтому объект — куски
    одного id с одинаковыми атрибутами, а ключ части комплекса дополнен её feature_id.

Куски одного объекта не перекрываются и склеиваются по стыкам тайлов в общей целочисленной сетке (рёбра на стыке
гасятся встречными; линии соединяются концами), так что здание через стык — один контур без шва; площадь и длина —
на местности (метры EPSG:3395 делятся на масштаб проекции в точке). Для анализа и эскиза: это
пользовательская карта Яндекса, в сдаваемые материалы её не включать.
"""

import math
import os
import re
import struct
import tempfile
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import netutil
from .contract import Connector, ConnectorError, make_result

URL = ("https://core-renderer-tiles.maps.yandex.net/vmap3/tiles"
       "?lang=ru_RU&x={x}&y={y}&z={z}&zmin={z}&zmax={z}")
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://yandex.ru/maps/"}
ZOOM = 18                    # полная детализация: z19 отличается на ~1 %, z16 даёт дрожание контура ±1 м
TTL = 30 * 24 * 3600
EXTENT = 8192
R = 6378137.0
E = 0.0818191908426          # эксцентриситет WGS84
HALF = math.pi * R
# служебные слои рендера — не выгружаются (маски во весь тайл, подписи, суша, границы населённых пунктов)
# road_label и place_label (подписи улиц и мест) больше не пропускаются: их берут листы альбома (#47), остальные источники их не просят
SKIP = frozenset({"hd_road_interchange", "land", "locality_a", "model_p", "roadnet_a_label", "road_symbol"})
SOURCE_DOC = "Яндекс Карты (векторные тайлы vmap3) — для анализа и эскиза; в сдаваемые материалы не включать"


# ---------- protobuf без схемы ----------
def _varint(b, i):
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return r, i


def _parse(b):
    """Сообщение → [(поле, тип, значение)]."""
    i, out, n = 0, [], len(b)
    while i < n:
        k, i = _varint(b, i)
        f, w = k >> 3, k & 7
        if w == 0:
            v, i = _varint(b, i)
        elif w == 1:
            v, i = b[i:i + 8], i + 8
        elif w == 5:
            v, i = b[i:i + 4], i + 4
        elif w == 2:
            ln, i = _varint(b, i)
            v, i = b[i:i + ln], i + ln
        else:
            raise ValueError(f"тип поля {w}")
        out.append((f, w, v))
    if i != n:
        raise ValueError("сообщение обрезано")
    return out


def _varints(b):
    i, out = 0, []
    while i < len(b):
        v, i = _varint(b, i)
        out.append(v)
    return out


def _zz(n):
    return (n >> 1) ^ -(n & 1)


def _value(msg):
    p = _parse(msg)
    if not p:
        return None
    a, _, v = p[0]
    if a == 1:
        return v.decode("utf-8", "replace")
    if a == 8:
        inner = _parse(v) if v else []
        return inner[0][2].decode("utf-8", "replace") if inner else ""
    if a == 5:
        return struct.unpack("<f", v)[0]
    if a == 2:
        return _zz(v)
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    return v


def decode(buf):
    """Тайл → [{layer, type: point|line|polygon, parts, id?, props}] в координатах сетки тайла.

    parts: точка — [(x, y)], линия — [кусок, …], полигон — [[кольцо, дыра, …], …]."""
    if not buf:
        return []
    top = _parse(buf)
    geo = next((v for f, w, v in top if f == 2), b"")
    lens = next((v for f, w, v in top if f == 3), b"")
    G, C = _varints(geo), _varints(lens)
    keys = [[x[2].decode("utf-8", "replace") for x in _parse(v)] for f, w, v in top if f == 4]
    vals = [_value(v) for f, w, v in top if f == 5]
    parts, k = [], 0
    for n in C:
        x = y = 0
        ring = []
        for _ in range(n):
            x += _zz(G[k])
            y += _zz(G[k + 1])
            k += 2
            ring.append((x, y))
        parts.append(ring)
    pi, out = 0, []
    for f, w, v in top:
        if f != 6:
            continue
        L = _parse(v)
        layer = L[0][2].decode("utf-8", "replace")
        for f2, w2, v2 in L[1:]:
            if f2 != 2:
                continue
            fe = {"layer": layer}
            for a, wa, va in _parse(v2):
                if a == 1:
                    fe["type"], fe["parts"] = "point", parts[pi]
                    pi += 1
                elif a == 2:
                    d = {x[0]: x[2] for x in _parse(va)}
                    fe["type"], fe["parts"] = "line", parts[pi:pi + d[1]]
                    pi += d[1]
                elif a == 3:
                    d = {x[0]: x[2] for x in _parse(va)}
                    polys, j = [], pi
                    for rc in d.get(1, b""):
                        polys.append(parts[j:j + rc])
                        j += rc
                    fe["type"], fe["parts"] = "polygon", polys
                    pi = j + d.get(2, 0)         # поле 2 — контуры обводки, в геометрию не идут
                elif a == 5:
                    fe["id"] = va
                elif a == 6:
                    d = {x[0]: x[2] for x in _parse(va)}
                    fe["props"] = {kk: vals[i] for kk, i in zip(keys[d[1]], _varints(d[2]))}
            out.append(fe)
    if pi != len(parts):
        raise ConnectorError(f"тайл Яндекса не разобран: частей {len(parts)}, прочитано {pi}")
    return out


# ---------- EPSG:3395 ↔ WGS84 ----------
def lonlat_to_3395(lon, lat):
    p = math.radians(lat)
    es = E * math.sin(p)
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + p / 2) * ((1 - es) / (1 + es)) ** (E / 2))


def lat_from_3395(y):
    """Обратный эллипсоидальный Меркатор: широта итерациями до 1e-13 рад (< 1 мм)."""
    t = math.exp(-y / R)
    p = math.pi / 2 - 2 * math.atan(t)
    for _ in range(20):
        es = E * math.sin(p)
        q = math.pi / 2 - 2 * math.atan(t * ((1 - es) / (1 + es)) ** (E / 2))
        if abs(q - p) < 1e-13:
            return math.degrees(q)
        p = q
    return math.degrees(p)


def to_lonlat(x, y):
    return math.degrees(x / R), lat_from_3395(y)


def scale_3395(y):
    """Масштаб проекции в точке: во столько раз метр EPSG:3395 длиннее метра на местности."""
    p = math.radians(lat_from_3395(y))
    return math.sqrt(1 - (E * math.sin(p)) ** 2) / math.cos(p)


MAX_TILES = 2500   # потолок числа тайлов за одну выгрузку (обычная область — сотни)


def tile_range(bbox, z=ZOOM):
    w, s, e, n = bbox
    size = 2 * HALF / 2 ** z
    x1, y1 = lonlat_to_3395(w, s)
    x2, y2 = lonlat_to_3395(e, n)
    tx = range(int((min(x1, x2) + HALF) // size), int((max(x1, x2) + HALF) // size) + 1)
    ty = range(int((HALF - max(y1, y2)) // size), int((HALF - min(y1, y2)) // size) + 1)
    if len(tx) * len(ty) > MAX_TILES:
        raise ConnectorError(
            f"слишком большая область: {len(tx) * len(ty)} тайлов Яндекса (предел {MAX_TILES}) — уменьшите область")
    return [(x, y) for x in tx for y in ty]


def tile_to_3395(z, x, y):
    """Функция: точка сетки тайла → метры EPSG:3395. Край 4095 возвращается на 4096 — иначе щель на стыке тайлов."""
    size = 2 * HALF / 2 ** z
    cx, cy, k = -HALF + (x + 0.5) * size, HALF - (y + 0.5) * size, size / EXTENT
    return lambda px, py: (cx + (4096 if px == 4095 else px) * k, cy - (4096 if py == 4095 else py) * k)


# ---------- площадь и длина на местности ----------
def _ring_area(r):
    return abs(sum(r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1] for i in range(len(r) - 1))) / 2


def _poly_area_m2(poly):
    """Кусок полигона в метрах EPSG:3395 → площадь на местности (масштаб — по средней широте внешнего кольца)."""
    outer = poly[0]
    k = scale_3395(sum(p[1] for p in outer) / len(outer))
    return max(0.0, _ring_area(outer) - sum(_ring_area(h) for h in poly[1:])) / k ** 2


def _line_len_m(line):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) / scale_3395((a[1] + b[1]) / 2) for a, b in zip(line, line[1:]))


def _closed(r):
    return r if r[0] == r[-1] else r + [r[0]]


def _ll(r):
    return [[round(c, 9) for c in to_lonlat(x, y)] for x, y in r]


# ---------- склейка кусков по стыкам тайлов (без shapely) ----------
# Все куски объекта переводятся в общую целочисленную сетку тайлов уровня z: GX = x·8192 + 4096 + px (4095 → 4096),
# GY так же по y. Стык тайлов — линия, кратная 8192. Соседние куски полигона лежат по разные стороны стыка, поэтому их
# рёбра на стыке идут навстречу друг другу и взаимно гасятся; оставшиеся рёбра собираются в кольца. Точка среза на стыке
# в соседних тайлах бывает округлена по-разному (на 1 клетку ≈ 2 см) — от этого остаётся ступенька в 1 клетку, её
# вершины снимаются чисткой почти прямых углов на линии стыка.
def _to_grid(x, y):
    ox, oy = x * EXTENT + 4096, y * EXTENT + 4096
    return lambda px, py: (ox + (4096 if px == 4095 else px), oy + (4096 if py == 4095 else py))


def _grid_to_3395(zoom):
    k = 2 * HALF / 2 ** zoom / EXTENT
    return lambda gx, gy: (-HALF + gx * k, HALF - gy * k)


def _sarea(r):
    """Знаковая площадь открытого кольца (в клетках сетки)."""
    n = len(r)
    return sum(r[i][0] * r[(i + 1) % n][1] - r[(i + 1) % n][0] * r[i][1] for i in range(n)) / 2


def _seam(p):
    return p[0] % EXTENT == 0 or p[1] % EXTENT == 0


def _clean(r):
    """Снять повторы, вершины на прямой и ступеньки в 1–2 клетки на линии стыка."""
    changed = True
    while changed and len(r) > 3:
        changed = False
        i = 0
        while i < len(r) and len(r) > 3:           # один проход с шагом назад после удаления, без перезапуска
            a, c, b = r[i - 1], r[i], r[(i + 1) % len(r)]
            cross = (c[0] - a[0]) * (b[1] - c[1]) - (c[1] - a[1]) * (b[0] - c[0])
            base = math.hypot(b[0] - a[0], b[1] - a[1])
            if c == a or cross == 0 or (_seam(c) and base and abs(cross) / base <= 1.5):
                del r[i]
                changed = True
                i = max(i - 1, 0)
                continue
            i += 1
    return r


def _inside(pt, ring):
    x, y = pt
    inside = False
    for i in range(len(ring)):
        (x1, y1), (x2, y2) = ring[i - 1], ring[i]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _dissolve(polys):
    """Куски полигона (открытые кольца в сетке, [внешнее, дыры…]) → полигоны, склеенные по стыкам тайлов.
    Если склейка не сходится (кольцо не замкнулось, площадь разошлась) — куски как были."""
    if len(polys) < 2:
        return polys
    edges, total = [], 0.0
    for poly in polys:
        for i, r in enumerate(poly):
            a = _sarea(r)
            if not a:
                continue
            if (a > 0) != (i == 0):          # внешнее — против часовой (в осях сетки), дыры — по часовой
                r, a = r[::-1], -a
            total += a
            edges += [(r[k], r[(k + 1) % len(r)]) for k in range(len(r))]
    seams, rest = {}, []
    for p, q in edges:
        if p == q:
            continue
        if p[0] == q[0] and p[0] % EXTENT == 0:
            seams.setdefault((0, p[0]), []).append((p[1], q[1]))
        elif p[1] == q[1] and p[1] % EXTENT == 0:
            seams.setdefault((1, p[1]), []).append((p[0], q[0]))
        else:
            rest.append((p, q))
    for (axis, c), segs in seams.items():     # на линии стыка остаётся только то, что покрыто в одну сторону
        ev = {}
        for a, b in segs:
            sgn = 1 if b > a else -1
            ev[min(a, b)] = ev.get(min(a, b), 0) + sgn
            ev[max(a, b)] = ev.get(max(a, b), 0) - sgn
        cov, ts = 0, sorted(ev)
        for t0, t1 in zip(ts, ts[1:]):
            cov += ev[t0]
            if abs(cov) > 1:
                return polys
            if cov:
                a, b = (t0, t1) if cov > 0 else (t1, t0)
                rest.append(((c, a), (c, b)) if axis == 0 else ((a, c), (b, c)))
    out = {}
    for p, q in rest:
        out.setdefault(p, []).append(q)
    rings = []
    while out:
        start = next(iter(out))
        ring, prev, cur = [start], None, start
        while True:
            cands = out.get(cur)
            if not cands:
                return polys
            if len(cands) > 1 and prev:           # касание в вершине: самый левый поворот держит кольца раздельными
                dx, dy = cur[0] - prev[0], cur[1] - prev[1]
                nxt = max(cands, key=lambda q: math.atan2(dx * (q[1] - cur[1]) - dy * (q[0] - cur[0]),
                                                           dx * (q[0] - cur[0]) + dy * (q[1] - cur[1])))
            else:
                nxt = cands[0]
            cands.remove(nxt)
            if not cands:
                del out[cur]
            if nxt == start:
                break
            ring.append(nxt)
            prev, cur = cur, nxt
        rings.append(ring)
    # гашение встречных рёбер сохраняет площадь точно — иначе склейка не сошлась
    if abs(sum(_sarea(r) for r in rings) - total) > 1e-6:
        return polys
    rings = [r for r in (_clean(r) for r in rings) if len(r) >= 3 and _sarea(r)]
    outers = [r for r in rings if _sarea(r) > 0]
    result = [[r] for r in outers]
    for h in (r for r in rings if _sarea(r) < 0):
        # самый внутренний контур: дыра острова внутри пруда принадлежит острову, а не внешнему полигону
        host = min((p for p in result if _inside(h[0], p[0])), key=lambda p: abs(_sarea(p[0])), default=None)
        if host is None:
            return polys
        host.append(h)
    return result or polys


def _join(lines):
    """Куски линии (в сетке) → соединённые по концам на стыке тайлов (с допуском в 2 клетки на округление среза)."""
    lines = [list(l) for l in lines]
    near = lambda a, b: abs(a[0] - b[0]) <= 2 and abs(a[1] - b[1]) <= 2
    joined = True
    while joined and len(lines) > 1:
        joined = False
        for i, a in enumerate(lines):
            if not _seam(a[-1]):
                continue
            for j, b in enumerate(lines):
                if i == j:
                    continue
                if near(a[-1], b[0]) and _seam(b[0]):
                    a.extend(b[1:])
                elif near(a[-1], b[-1]) and _seam(b[-1]):
                    a.extend(b[-2::-1])
                else:
                    continue
                del lines[j]
                joined = True
                break
            if joined:
                break
    return lines


def features_from_tiles(blobs, layers, zoom=ZOOM, bbox=None):
    """[((x, y), байты тайла)] → объекты GeoJSON (WGS84) выбранных слоёв; с рамкой — только пересекающие её.

    Объект — куски одного id с одинаковыми атрибутами со всех тайлов, склеенные по стыкам тайлов (MultiPolygon /
    MultiLineString); площадь и длина — на местности."""
    want = set(layers) - SKIP
    xs = [x for (x, _y), _ in blobs] or [0]
    ys = [y for (_x, y), _ in blobs] or [0]
    gxl, gxr, gyt, gyb = min(xs) * EXTENT, (max(xs) + 1) * EXTENT, min(ys) * EXTENT, (max(ys) + 1) * EXTENT
    objs = {}        # (слой, id, атрибуты) → [тип, атрибуты, куски в общей сетке тайлов]
    for (x, y), data in blobs:
        to = _to_grid(x, y)
        for n, fe in enumerate(decode(data)):
            layer = fe["layer"]
            if layer not in want or "type" not in fe:
                continue
            t = fe["type"]
            if t == "point":
                geom = [to(*fe["parts"][0])] if fe["parts"] else None
            elif t == "line":
                geom = [[to(*p) for p in r] for r in fe["parts"] if len(r) >= 2]
            else:
                geom = []
                for poly in fe["parts"]:
                    rings = []
                    for r in poly:
                        r = [to(*p) for p in r]
                        if len(r) > 1 and r[0] == r[-1]:
                            r = r[:-1]
                        if len(r) >= 3:
                            rings.append(r)
                    if rings and _sarea(rings[0]):
                        geom.append(rings)
            if not geom:
                continue
            oid = fe.get("id")
            props = fe.get("props") or {}
            # id объединяет части комплекса (башни и стилобат одного id), а высота и назначение у каждой части свои:
            # объект — куски одного id с одинаковыми атрибутами (так же склеивает эталон yaexport.py)
            key = (layer, oid if oid is not None else f"{zoom}_{x}_{y}_{n}", tuple(sorted((k, repr(v)) for k, v in props.items())))
            o = objs.setdefault(key, [t, props, []])
            if t == "point":
                o[2] = o[2] or geom
            else:
                o[2].extend(geom)

    m = _grid_to_3395(zoom)
    w, s, e, n = bbox or (-180, -90, 180, 90)
    # рамка скачанных тайлов в тех же округлённых координатах, что и вершины: объект, дошедший до неё, обрезан —
    # карта не рисует разрез контуром, а у площади есть пометка, что она неполная
    lw, ln_ = _ll([m(gxl, gyt)])[0]
    le, ls = _ll([m(gxr, gyb)])[0]
    frame = [lw, ls, le, ln_]
    feats, parts_of = [], {}
    for layer, oid, _ in objs:
        parts_of[layer, oid] = parts_of.get((layer, oid), 0) + 1
    for (layer, oid, pk), (t, props, pieces) in objs.items():
        if t == "point":
            lon, lat = to_lonlat(*m(*pieces[0]))
            if not (w <= lon <= e and s <= lat <= n):
                continue
            geom, extra = {"type": "Point", "coordinates": [round(lon, 9), round(lat, 9)]}, {}
        else:
            if t == "line":
                parts = [[m(*p) for p in r] for r in _join(pieces)]
                flat = [p for r in parts for p in r]
            else:
                dis = _dissolve(pieces)
                cut = any(p[0] in (gxl, gxr) or p[1] in (gyt, gyb) for poly in dis for p in poly[0])
                parts = [[_closed([m(*p) for p in r]) for r in poly] for poly in dis]
                flat = [p for poly in parts for p in poly[0]]
            lo = to_lonlat(min(p[0] for p in flat), min(p[1] for p in flat))
            hi = to_lonlat(max(p[0] for p in flat), max(p[1] for p in flat))
            if hi[0] < w or lo[0] > e or hi[1] < s or lo[1] > n:
                continue
            if t == "line":
                geom = {"type": "MultiLineString", "coordinates": [_ll(r) for r in parts]}
                extra = {"Длина, м": round(sum(_line_len_m(r) for r in parts), 1)}
            else:
                geom = {"type": "MultiPolygon", "coordinates": [[_ll(r) for r in poly] for poly in parts]}
                extra = {"Площадь, м²": round(sum(_poly_area_m2(poly) for poly in parts), 1),
                         **({"Площадь": "только в области выгрузки: объект обрезан её рамкой"} if cut else {})}
        key = f"yandex:{layer}:{oid}"
        if parts_of[layer, oid] > 1:       # часть комплекса: своя метка, устойчивая между выгрузками
            key += ":" + str(props.get("feature_id") or zlib.crc32(repr(pk).encode("utf-8")))
        feats.append({"type": "Feature", "geometry": geom, "grado_key": key,
                      "properties": {**props, **extra, "grado_layer": layer},
                      **({"grado_clip": frame} if t not in ("point", "line") and cut else {})})
    return feats


class YandexVmap(Connector):
    """fetch(bbox, layers) → объекты слоёв Яндекса, пересекающие область; свойство grado_layer — слой тайла."""
    name = "yandex"
    source = "yandex"

    def __init__(self, transport=None, cache_dir=None, ttl=TTL, zoom=ZOOM, workers=3, pause=0.3, progress=None):
        self.transport = transport or self._http_get
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.ttl, self.zoom, self.workers, self.pause, self.progress = ttl, zoom, workers, pause, progress

    def _http_get(self, url, timeout=30):
        """Тайл по сети → байты; b"" — тайла нет (404). Капча или обрезанный ответ (decode не прочёл) — повтор
        по общему правилу netutil, а не кэш на 30 дней."""
        try:
            return netutil.request(url, headers=HEADERS, timeout=timeout,
                                   check=lambda data: data and decode(data)).content
        except netutil.HttpError as e:
            if e.code == 404:              # нет данных в тайле
                return b""
            # отказ Яндекса словами (<message> в XML) — в текст ошибки: «HTTP 400» без причины не разобрать с сайта
            why = re.search(rb"<message>\s*(.*?)\s*</message>", e.body or b"", re.S)
            if why:
                raise ConnectorError(f"HTTP {e.code}: {why.group(1).decode('utf-8', 'replace')[:200]}") from None
            raise

    def _tile(self, x, y):
        """(данные, скачан ли из сети). Повторы — в netutil (_http_get); после каждого скачанного тайла — пауза."""
        z = self.zoom
        path = self.cache_dir / f"{z}_{x}_{y}.pbf" if self.cache_dir else None
        if path and path.exists() and time.time() - path.stat().st_mtime < self.ttl:
            return path.read_bytes(), False
        try:
            data = self.transport(URL.format(x=x, y=y, z=z), timeout=30)
        except ConnectorError as e:
            raise ConnectorError(f"тайл Яндекса {z}/{x}/{y} не скачан: {e}") from None
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".part")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
        if self.pause:
            time.sleep(self.pause)
        return data, True

    def fetch(self, bbox, layers):
        want = set(layers) - SKIP
        tiles = tile_range(bbox, self.zoom)
        done, net = [0], [0]

        def one(t):
            data, fresh = self._tile(*t)
            done[0] += 1
            net[0] += fresh
            if self.progress:
                self.progress(done[0], len(tiles))
            return t, data

        with ThreadPoolExecutor(max(1, self.workers)) as ex:
            blobs = list(ex.map(one, tiles))

        feats = features_from_tiles(blobs, want, self.zoom, bbox)
        notes = [] if net[0] else ["тайлы с диска: повторно Яндекс не запрашивался"]
        return make_result(feats, {"bbox": list(bbox), "layers": sorted(want), "zoom": self.zoom, "tiles": len(tiles),
                                   "downloaded": net[0]}, source_doc=SOURCE_DOC, notes=notes)
