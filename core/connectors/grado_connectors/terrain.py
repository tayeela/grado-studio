"""Коннектор рельефа: горизонтали (изолинии высот) по видимому экстенту.

Открытый тайловый DEM — AWS Terrain Tiles (terrarium PNG, на базе SRTM/GMTED,
без ключа и без регистрации; SRTM — в каталоге bella-mir.github.io/openSpData).
Высота пикселя закодирована в RGB: elev = R*256 + G + B/256 - 32768 (метры).
Тайлы, покрывающие bbox, мозаичим в одну сетку высот; изолинии строим методом
marching squares на адаптивном интервале сечения; отдаём LineString (WGS84) с
высотой в свойстве `elev`. Дальше studio_core проецирует WGS84 → СК проекта, как
у прочих источников «Данных». Локальный однопользовательский инструмент —
«лёгкое использование» тайлового сервиса.

Требует Pillow (декодирование PNG) — в проекте опциональная зависимость; при
отсутствии коннектор поднимает ConnectorError с понятным текстом.
"""

import io
import math
import ssl
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque

from . import netutil
from .contract import Connector, ConnectorError, make_result

TERRARIUM_URL = ("https://s3.amazonaws.com/elevation-tiles-prod/"
                 "terrarium/{z}/{x}/{y}.png")
_UA = "grado-studio/0.1 (local single-user desktop tool for urban planning)"

_MAX_TILES = 12       # страховка на размер мозаики (не тянуть гигантский растр)
_MAX_ZOOM = 13        # выше — интерполяция SRTM без новой детализации
_MIN_ZOOM = 9
_MAX_GRID = 260       # рабочая сетка ужимается до этого размера по стороне
_MAX_LEVELS = 500     # предел числа уровней сечения (страховка от крошечного шага)
_MAX_CHAINS = 2500    # предел изолиний в одной выгрузке (не раздувать проект)

# «Красивые» шаги сечения рельефа, м — выбираем ближайший, дающий ~15–25 линий.
_NICE_STEPS = [0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200, 250, 500]

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()


# ---- тайловая математика (Web Mercator, EPSG:3857) -------------------------

def _lon2tilex(lon, z):
    return int((lon + 180.0) / 360.0 * (1 << z))


def _lat2tiley(lat, z):
    r = math.radians(lat)
    return int((1.0 - math.asinh(math.tan(r)) / math.pi) / 2.0 * (1 << z))


def _gpix2lonlat(gx, gy, z):
    """Глобальный пиксель Web Mercator → (lon, lat). Точная обратная проекция
    (широта нелинейна по пикселю — считаем аналитически, без аппроксимаций)."""
    world = 256.0 * (1 << z)
    lon = gx / world * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * gy / world))))
    return [lon, lat]


def _pick_zoom(bbox):
    """Подобрать зум: максимум детализации при лимите числа тайлов."""
    west, south, east, north = bbox
    for z in range(_MAX_ZOOM, _MIN_ZOOM - 1, -1):
        x0, x1 = _lon2tilex(west, z), _lon2tilex(east, z)
        y0, y1 = _lat2tiley(north, z), _lat2tiley(south, z)
        nx, ny = abs(x1 - x0) + 1, abs(y1 - y0) + 1
        if nx * ny <= _MAX_TILES:
            return z, min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
    z = _MIN_ZOOM
    x0, x1 = _lon2tilex(west, z), _lon2tilex(east, z)
    y0, y1 = _lat2tiley(north, z), _lat2tiley(south, z)
    return z, min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def _nice_interval(rng):
    raw = rng / 18.0
    for step in _NICE_STEPS:
        if step >= raw:
            return step
    return _NICE_STEPS[-1]


# ---- загрузка и декодирование высот ---------------------------------------

def _fetch_grid(z, x0, y0, x1, y1, http):
    """Мозаика высот по тайлам terrarium → (grid, px0, py0, stride, z).

    grid[r][c] — высота (м), row 0 = север. Сетка ужимается страйдом до
    _MAX_GRID по большей стороне (детализация SRTM ~30 м всё равно грубее)."""
    from PIL import Image
    nx = (x1 - x0 + 1)
    ny = (y1 - y0 + 1)
    full_w, full_h = nx * 256, ny * 256
    stride = max(1, math.ceil(max(full_w, full_h) / _MAX_GRID))
    # столбцы/строки исходных пикселей, которые реально берём
    cols = list(range(0, full_w, stride))
    rows = list(range(0, full_h, stride))
    grid = [[0.0] * len(cols) for _ in rows]
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            data = http(z, tx, ty)
            im = Image.open(io.BytesIO(data)).convert("RGB")
            px = im.load()
            ox, oy = (tx - x0) * 256, (ty - y0) * 256   # смещение тайла в мозаике
            for ri, gy in enumerate(rows):
                if gy < oy or gy >= oy + 256:
                    continue
                iy = gy - oy
                for ci, gx in enumerate(cols):
                    if gx < ox or gx >= ox + 256:
                        continue
                    r, g, b = px[gx - ox, iy]
                    grid[ri][ci] = (r * 256.0 + g + b / 256.0) - 32768.0
    return grid, x0 * 256, y0 * 256, stride, z


def _http_get(z, x, y):
    url = TERRARIUM_URL.format(z=z, x=x, y=y)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    last = None
    for attempt in range(3):                 # S3 изредка не отвечает на рукопожатие TLS — повторить, а не терять слой
        try:
            with netutil.open_url(req, 20, _SSL_CTX) as resp:
                return netutil.read_capped(resp)
        except urllib.error.HTTPError as e:
            raise ConnectorError(f"DEM-тайл {z}/{x}/{y}: HTTP {e.code}") from None
        except Exception as e:
            last = e
            time.sleep(0.5 * (attempt + 1))
    raise ConnectorError(f"DEM-тайл {z}/{x}/{y}: {last}")


# ---- marching squares ------------------------------------------------------

def _cell_segments(tl, tr, br, bl, c, r, level):
    """Отрезки изолинии `level` внутри ячейки (углы TL,TR,BR,BL). Пересечения
    считаем по сменам знака на рёбрах (робастно, без таблицы 16 случаев);
    седло (4 пересечения) разводим по среднему значению центра."""
    def interp(a, b):        # доля от a к b, где значение = level
        return (level - a) / (b - a)

    pts = {}
    if (tl - level) * (tr - level) < 0:      # верх: TL→TR
        pts['T'] = (c + interp(tl, tr), r)
    if (tr - level) * (br - level) < 0:      # право: TR→BR
        pts['R'] = (c + 1, r + interp(tr, br))
    if (bl - level) * (br - level) < 0:      # низ: BL→BR
        pts['B'] = (c + interp(bl, br), r + 1)
    if (tl - level) * (bl - level) < 0:      # лево: TL→BL
        pts['L'] = (c, r + interp(tl, bl))
    if len(pts) == 2:
        (a, b) = pts.values()
        return [(a, b)]
    if len(pts) == 4:
        center = (tl + tr + br + bl) / 4.0
        if center >= level:
            return [(pts['T'], pts['L']), (pts['R'], pts['B'])]
        return [(pts['T'], pts['R']), (pts['B'], pts['L'])]
    return []


def _stitch(segments):
    """Склейка коротких отрезков в длинные полилинии по общим концам."""
    def key(p):
        return (round(p[0], 7), round(p[1], 7))

    ends = defaultdict(list)
    for i, (a, b) in enumerate(segments):
        ends[key(a)].append(i)
        ends[key(b)].append(i)
    used = [False] * len(segments)
    chains = []
    for i in range(len(segments)):
        if used[i]:
            continue
        used[i] = True
        a, b = segments[i]
        chain = deque([a, b])
        changed = True
        while changed:
            changed = False
            for head in (False, True):
                p = chain[0] if head else chain[-1]
                for j in ends[key(p)]:
                    if used[j]:
                        continue
                    sa, sb = segments[j]
                    if key(sa) == key(p):
                        nxt = sb
                    elif key(sb) == key(p):
                        nxt = sa
                    else:
                        continue
                    used[j] = True
                    if head:
                        chain.appendleft(nxt)
                    else:
                        chain.append(nxt)
                    changed = True
                    break
        chains.append(list(chain))
    return chains


def _contours(grid, px0, py0, stride, z, interval, base=0.0):
    """Изолинии сетки высот: список (level, [ [lon,lat], ... ]) в WGS84."""
    nrows, ncols = len(grid), len(grid[0])
    lo = min(min(row) for row in grid)
    hi = max(max(row) for row in grid)
    # уровни-кратные интервала строго внутри диапазона
    k0 = math.floor((lo - base) / interval) + 1
    k1 = math.ceil((hi - base) / interval) - 1
    result = []
    for k in range(k0, k1 + 1):
        level = base + k * interval
        lv = level + 1e-6
        segs = []
        for r in range(nrows - 1):
            row0, row1 = grid[r], grid[r + 1]
            for c in range(ncols - 1):
                tl, tr = row0[c], row0[c + 1]
                bl, br = row1[c], row1[c + 1]
                cmin = tl if tl < tr else tr
                if bl < cmin:
                    cmin = bl
                if br < cmin:
                    cmin = br
                cmax = tl if tl > tr else tr
                if bl > cmax:
                    cmax = bl
                if br > cmax:
                    cmax = br
                # уровень чуть сдвинут с данных: высоты тайлов целые, и угол ровно на уровне терял бы отрезки
                if lv < cmin or lv > cmax:
                    continue
                segs.extend(_cell_segments(tl, tr, br, bl, c, r, lv))
        if not segs:
            continue
        # grid-координаты (col,row) → глобальный пиксель → lon/lat
        def to_ll(p):
            gx = px0 + p[0] * stride
            gy = py0 + p[1] * stride
            return tuple(_gpix2lonlat(gx, gy, z))

        ll_segs = [(to_ll(a), to_ll(b)) for a, b in segs]
        for chain in _stitch(ll_segs):
            if len(chain) >= 2:
                result.append((level, [list(pt) for pt in chain]))
    return result


class TerrainContours(Connector):
    name = "terrain"
    source = "terrain"

    def __init__(self, transport=None):
        self.transport = transport or _http_get

    def fetch(self, bbox, interval=None):
        """bbox = (west, south, east, north) WGS84. interval — шаг сечения, м
        (None → авто). Возвращает make_result с LineString-горизонталями."""
        west, south, east, north = map(float, bbox)
        z, x0, y0, x1, y1 = _pick_zoom((west, south, east, north))
        grid, px0, py0, stride, z = _fetch_grid(z, x0, y0, x1, y1, self.transport)
        lo = min(min(row) for row in grid)
        hi = max(max(row) for row in grid)
        rng = hi - lo
        notes = []
        if rng < 0.5:
            return make_result(
                [], params={"bbox": ",".join(f"{v:.5f}" for v in bbox),
                            "zoom": z},
                source_doc="AWS Terrain Tiles (terrarium, SRTM/GMTED)",
                notes=["рельеф ровный: перепад высот < 0.5 м, "
                       "горизонтали не построены"])
        if interval is not None:
            try:
                step = float(interval)
            except (TypeError, ValueError):
                step = float("nan")
            if not math.isfinite(step) or step <= 0:
                raise ConnectorError("шаг сечения должен быть конечным числом больше нуля")
            if rng / step > _MAX_LEVELS:
                raise ConnectorError(
                    f"слишком мелкий шаг сечения {step:g} м: при перепаде {rng:.0f} м "
                    f"выйдет больше {_MAX_LEVELS} уровней — увеличьте шаг")
        else:
            step = _nice_interval(rng)
        lines = _contours(grid, px0, py0, stride, z, step)
        if len(lines) > _MAX_CHAINS:
            notes.append(f"горизонталей много ({len(lines)}) — оставлены первые "
                         f"{_MAX_CHAINS}, увеличьте шаг сечения или уменьшите область")
            lines = lines[:_MAX_CHAINS]
        features = []
        for i, (level, coords) in enumerate(lines):
            features.append({
                "type": "Feature",
                "grado_key": f"contour/{level:.2f}/{i}",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {"elev": round(level, 2), "grado_set": "contours"}})
        notes.append(f"перепад {lo:.0f}…{hi:.0f} м, сечение {step:g} м, "
                     f"зум {z}")
        return make_result(
            features,
            params={"bbox": ",".join(f"{v:.5f}" for v in bbox),
                    "zoom": z, "interval": step},
            source_doc="AWS Terrain Tiles (terrarium, SRTM/GMTED)",
            notes=notes)
