"""Спутник Яндекса для AutoCAD: снимок рамки листа, пересчитанный в МСК (как в QGIS владельца).

Тайлы спутника Яндекса лежат в эллипсоидальном Меркаторе EPSG:3395, лист ГРАДО 2 — в МСК, и сетки повёрнуты друг
к другу (в Москве — до полуградуса). Поэтому снимок не склеивается «как есть», а пересобирается по сетке МСК:
выходной растр режется на блоки, углы каждого блока пересчитываются МСК → WGS84 → 3395 → пиксели тайлов, и блок
берётся из мозаики сеткой четырёхугольников (Pillow, Image.MESH) — ошибка меньше пикселя.

Архив: sputnik_yandex.jpg + sputnik_yandex.jgw (файл привязки: МСК, метры) + sputnik_yandex.dxf (растр IMAGE на своём
месте в МСК, AutoCAD находит снимок рядом с чертежом) + .dwg, если стоит ODA File Converter.
Снимки Яндекса — для работы и эскиза, в сдаваемые материалы не включать (как слои Яндекса, решение владельца).
"""

import io
import math
import os
import ssl
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from grado_connectors import crs
from grado_connectors.yandex_vmap import HALF, HEADERS, lonlat_to_3395, scale_3395

URL = "https://core-sat.maps.yandex.net/tiles?l=sat&x={x}&y={y}&z={z}&scale=1&lang=ru_RU"
TTL = 90 * 24 * 3600
MAX_PX = 80_000_000          # выходной снимок: 80 Мп (0,5 м/пикс — около 9 × 9 км)
MAX_TILES = 4000
BLOCK = 256                  # блок пересборки, пикселей выхода
NAME = "sputnik_yandex"


class SatError(ValueError):
    pass


def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


class YandexSat:
    """Тайлы спутника Яндекса: с диска (90 дней), иначе по одному с паузой; нет тайла — серое место."""

    def __init__(self, cache_dir, pause=0.15, transport=None):
        self.cache_dir, self.pause = Path(cache_dir), pause
        self._ctx = None if transport else _ctx()
        self.transport = transport or self._get

    def _get(self, url):
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30, context=self._ctx) as r:
            return r.read()

    def path(self, z, x, y):
        return self.cache_dir / f"{z}_{x}_{y}.jpg"

    def ensure(self, z, x, y):
        """Тайл на диске. True — пришлось скачать."""
        p = self.path(z, x, y)
        if p.exists() and time.time() - p.stat().st_mtime < TTL:
            return False
        data = None
        for attempt in range(3):
            if attempt:
                time.sleep(1 + attempt)
            try:
                data = self.transport(URL.format(x=x, y=y, z=z))
                break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    break
            except OSError:
                pass
        if data and data[:2] == b"\xff\xd8":               # только JPEG: заглушка или капча в кэш не идёт
            p.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".part")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, p)
        if self.pause:
            time.sleep(self.pause)
        return True


def frame_msk(center, rect, scale):
    """Рамка карты листа в МСК (x0, y0, x1, y1), метры: лист ГРАДО 2 ориентирован по сетке МСК (print_io.MapTransform)."""
    cx, cy = crs.wgs84_to_msk(*center)
    hw, hh = rect[2] / 2 * scale / 1000.0, rect[3] / 2 * scale / 1000.0
    return cx - hw, cy - hh, cx + hw, cy + hh


def bbox_msk(bbox):
    """Рамка листа в градусах (w, s, e, n) → охватывающий прямоугольник в МСК."""
    w, s, e, n = bbox
    pts = [crs.wgs84_to_msk(x, y) for x in (w, e) for y in (s, n)]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def auto_mpp(frame, limit=25_000_000):
    """Самый подробный пиксель из 0,5 / 1 / 2 / 4 м, при котором снимок не больше limit пикселей."""
    area = (frame[2] - frame[0]) * (frame[3] - frame[1])
    return next((m for m in (0.5, 1.0, 2.0, 4.0) if area / m / m <= limit), 4.0)


def zoom_for(mpp, lat):
    """Самый мелкий уровень тайлов, у которого пиксель на местности не крупнее mpp (не больше 19)."""
    k = scale_3395(lonlat_to_3395(0, lat)[1])
    z = math.ceil(math.log2(2 * HALF / 256 / (mpp * k)))
    return max(10, min(19, z))


def export_sat(frame, mpp, cache_dir, progress=None, tiles=None):
    """frame — рамка в МСК, mpp — метров на пиксель выхода. → zip (bytes)."""
    from PIL import Image
    x0, y0, x1, y1 = frame
    W, H = max(1, round((x1 - x0) / mpp)), max(1, round((y1 - y0) / mpp))
    if W * H > MAX_PX:
        raise SatError(f"too large: {W}x{H} px; choose a coarser resolution")
    lat = crs.msk_to_wgs84((x0 + x1) / 2, (y0 + y1) / 2)[1]
    z = zoom_for(mpp, lat)
    size = 2 * HALF / 2 ** z
    gp = lambda X, Y: (lambda m: ((m[0] + HALF) / size * 256, (HALF - m[1]) / size * 256))(lonlat_to_3395(*crs.msk_to_wgs84(X, Y)))
    # пиксели мозаики по краям рамки (с шагом — края в 3395 слегка изогнуты)
    edge = [gp(x0 + (x1 - x0) * i / 16, y) for i in range(17) for y in (y0, y1)] + [gp(x, y0 + (y1 - y0) * i / 16) for i in range(17) for x in (x0, x1)]
    tx0, tx1 = int(min(p[0] for p in edge) // 256), int(max(p[0] for p in edge) // 256)
    ty0, ty1 = int(min(p[1] for p in edge) // 256), int(max(p[1] for p in edge) // 256)
    need = [(x, y) for y in range(ty0, ty1 + 1) for x in range(tx0, tx1 + 1)]
    if len(need) > MAX_TILES:
        raise SatError(f"too many tiles: {len(need)}; choose a coarser resolution")
    tiles = tiles or YandexSat(Path(cache_dir))
    for i, (x, y) in enumerate(need):
        tiles.ensure(z, x, y)
        if progress:
            progress(i + 1, len(need))
    out = Image.new("RGB", (W, H), (200, 200, 200))
    cache, order = {}, []

    def tile(x, y):                                          # последние ~64 тайла держатся в памяти
        if (x, y) not in cache:
            p = tiles.path(z, x, y)
            try:
                cache[(x, y)] = Image.open(p).convert("RGB") if p.exists() else None
            except OSError:
                cache[(x, y)] = None
            order.append((x, y))
            if len(order) > 64:
                cache.pop(order.pop(0), None)
        return cache[(x, y)]

    sub = BLOCK // 4                                         # четырёхугольник сетки — 64 пикселя выхода
    for by in range(0, H, BLOCK):
        for bx in range(0, W, BLOCK):
            bw, bh = min(BLOCK, W - bx), min(BLOCK, H - by)
            X = lambda px: x0 + (bx + px) * mpp
            Y = lambda py: y1 - (by + py) * mpp
            corners = [gp(X(px), Y(py)) for px in (0, bw) for py in (0, bh)]
            mx0, my0 = int(min(c[0] for c in corners) // 256), int(min(c[1] for c in corners) // 256)
            mx1, my1 = int(max(c[0] for c in corners) // 256), int(max(c[1] for c in corners) // 256)
            mosaic = Image.new("RGB", ((mx1 - mx0 + 1) * 256, (my1 - my0 + 1) * 256), (200, 200, 200))
            for ty in range(my0, my1 + 1):
                for tx in range(mx0, mx1 + 1):
                    t = tile(tx, ty)
                    if t:
                        mosaic.paste(t, ((tx - mx0) * 256, (ty - my0) * 256))
            ox, oy = mx0 * 256, my0 * 256
            mesh = []
            for sy in range(0, bh, sub):
                for sx in range(0, bw, sub):
                    ex, ey = min(sx + sub, bw), min(sy + sub, bh)
                    q = [gp(X(a), Y(b)) for a, b in ((sx, sy), (sx, ey), (ex, ey), (ex, sy))]   # NW, SW, SE, NE — порядок MESH
                    mesh.append(((sx, sy, ex, ey), tuple(v for c in q for v in (c[0] - ox, c[1] - oy))))
            out.paste(mosaic.transform((bw, bh), Image.MESH, mesh, Image.BILINEAR), (bx, by))
    jpg = io.BytesIO()
    out.save(jpg, "JPEG", quality=88, optimize=True)
    return _package(jpg.getvalue(), frame, mpp, W, H, z)


def _package(jpg, frame, mpp, W, H, z):
    import ezdxf
    import dxf_io
    x0, y0, x1, y1 = frame
    jgw = f"{mpp:.6f}\n0.0\n0.0\n{-mpp:.6f}\n{x0 + mpp / 2:.4f}\n{y1 - mpp / 2:.4f}\n"
    doc = ezdxf.new("R2018")
    doc.layers.add(dxf_io.acad_name("Спутник Яндекс"))
    img = doc.add_image_def(filename=f"{NAME}.jpg", size_in_pixel=(W, H))
    doc.modelspace().add_image(img, insert=(x0, y0), size_in_units=(W * mpp, H * mpp), rotation=0,
                               dxfattribs={"layer": dxf_io.acad_name("Спутник Яндекс")})
    dxf_io.fit_view(doc)
    buf = io.StringIO()
    doc.write(buf)
    dxf = buf.getvalue().encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{NAME}.jpg", jpg)
        zf.writestr(f"{NAME}.jgw", jgw)
        zf.writestr(f"{NAME}.dxf", dxf)
        if dxf_io.oda_converter():
            try:
                zf.writestr(f"{NAME}.dwg", dxf_io.oda_convert(dxf, "dxf", "DWG"))
            except (OSError, ValueError):
                pass
        zf.writestr("README.txt", (
            "Yandex satellite image of the sheet frame, resampled to MSK (QGIS custom CRS 'MSK': +proj=tmerc +lat_0=55.66666666667 "
            "+lon_0=37.5 +k=1 +x_0=0 +y_0=0 +ellps=bessel), metres.\n"
            f"Pixel {mpp} m, {W} x {H} px, Yandex tiles z{z}. Frame: X {x0:.2f}..{x1:.2f}, Y {y0:.2f}..{y1:.2f}.\n"
            f"AutoCAD: open {NAME}.dxf (the image lies in place; keep {NAME}.jpg next to the drawing), or insert {NAME}.jpg "
            f"with insertion point X {x0:.2f} Y {y0:.2f}, scale {W * mpp:.2f}, rotation 0.\n"
            f"QGIS and AutoCAD Map 3D read the world file {NAME}.jgw.\n"
            "For working drawings only; not for submitted materials.\n").encode("utf-8"))
    return out.getvalue()
