"""Спутник Яндекса для AutoCAD: снимок рамки листа, пересчитанный в МСК (как в QGIS владельца).

Тайлы спутника Яндекса лежат в эллипсоидальном Меркаторе EPSG:3395, лист ГРАДО 2 — в МСК, и сетки повёрнуты друг
к другу (в Москве — до полуградуса). Поэтому снимок не склеивается «как есть», а пересобирается по сетке МСК:
выходной растр режется на блоки, углы каждого блока пересчитываются МСК → WGS84 → 3395 → пиксели тайлов, и блок
берётся из мозаики сеткой четырёхугольников (Pillow, Image.MESH) — ошибка меньше пикселя.

Подробность: всегда z18 — самый подробный настоящий уровень Яндекса в Москве и области (~0,34 м на пиксель; z19 —
растянутый z18, сверено 30.09.2026 у Вороново), выход — 0,3 м на пиксель. Большой лист режется на куски не больше
4096 px: каждый кусок — свой JPEG со своим файлом привязки.

Архив — одна папка <имя>/: куски sputnik_yandex_NN.jpg + .jgw (МСК, метры), sputnik_yandex.dxf (растры IMAGE на своих
местах и рамка), sputnik_yandex.scr (запасной путь: вставка командой -IMAGE), README. AutoCAD показывает растр из DXF
при открытии, только если путь к снимку полный (с относительным — «Unreferenced» до ручной перезагрузки, владелец
30.09.2026; ezdxf discussions #845), поэтому в DXF пишется полный путь: папка загрузок браузера (её задаёт владелец
один раз) / имя архива / файл — туда архив и распаковывается двойным щелчком.
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
from grado_connectors.yandex_vmap import HALF, HEADERS, lonlat_to_3395

FAIL_TTL = 3600                                           # неудачный тайл не запрашивается час
URL = "https://core-sat.maps.yandex.net/tiles?l=sat&x={x}&y={y}&z={z}&scale=1&lang=ru_RU"
TTL = 90 * 24 * 3600
ZOOM = 18
MPP = 0.3                    # метров на пиксель выхода
MAX_PX = 400_000_000         # весь снимок: 400 Мп (0,3 м/пикс — около 6 × 6 км)
MAX_TILES = 12000
MAX_TILE_BYTES = 2**20       # тайл Яндекса — десятки КБ; больше мегабайта — не тайл (заглушка, чужой ответ)
MAX_TILE_PX = 512            # настоящий тайл 256 × 256; больший рисунок в мозаику не берётся
CHUNK = 4096                 # кусок снимка, пикселей по стороне
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
    """Тайлы спутника Яндекса: с диска (90 дней), иначе скачать с паузой; нет тайла — серое место."""

    def __init__(self, cache_dir, pause=0.1, transport=None):
        self.cache_dir, self.pause = Path(cache_dir), pause
        self._ctx = None if transport else _ctx()
        self.transport = transport or self._get

    def _get(self, url):
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30, context=self._ctx) as r:
            return r.read(MAX_TILE_BYTES + 1)              # не больше мегабайта + 1 байт: длиннее отсекает ensure

    def path(self, z, x, y):
        return self.cache_dir / f"{z}_{x}_{y}.jpg"

    def ensure(self, z, x, y):
        """Тайл на диске. True — пришлось скачать."""
        p = self.path(z, x, y)
        if p.exists() and time.time() - p.stat().st_mtime < TTL:
            return False
        mark = p.with_suffix(".fail")                      # отрицательный кэш: неудача — метка на час, без запросов
        try:
            if time.time() - mark.stat().st_mtime < FAIL_TTL:
                return False
        except OSError:
            pass
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
        if data and len(data) <= MAX_TILE_BYTES and data[:2] == b"\xff\xd8":   # только JPEG и не больше 1 МБ: заглушка или капча в кэш не идёт
            p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".part")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, p)
            mark.unlink(missing_ok=True)
        else:
            try:
                p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                mark.touch()
                os.utime(mark)
            except OSError:
                pass
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


def export_sat(frame, cache_dir, base="", progress=None, tiles=None, mpp=MPP, z=ZOOM):
    """frame — рамка в МСК; base — полный путь папки, куда распакуется архив (для путей в DXF). → zip (bytes)."""
    from PIL import Image
    x0, y0, x1, y1 = frame
    W, H = max(1, round((x1 - x0) / mpp)), max(1, round((y1 - y0) / mpp))
    if W * H > MAX_PX:
        raise SatError(f"too large: {W}x{H} px")
    size = 2 * HALF / 2 ** z
    gp = lambda X, Y: (lambda m: ((m[0] + HALF) / size * 256, (HALF - m[1]) / size * 256))(lonlat_to_3395(*crs.msk_to_wgs84(X, Y)))
    # пиксели мозаики по краям рамки (с шагом — края в 3395 слегка изогнуты)
    edge = [gp(x0 + (x1 - x0) * i / 16, y) for i in range(17) for y in (y0, y1)] + [gp(x, y0 + (y1 - y0) * i / 16) for i in range(17) for x in (x0, x1)]
    tx0, tx1 = int(min(p[0] for p in edge) // 256), int(max(p[0] for p in edge) // 256)
    ty0, ty1 = int(min(p[1] for p in edge) // 256), int(max(p[1] for p in edge) // 256)
    need = [(x, y) for y in range(ty0, ty1 + 1) for x in range(tx0, tx1 + 1)]
    if len(need) > MAX_TILES:
        raise SatError(f"too many tiles: {len(need)}")
    tiles = tiles or YandexSat(Path(cache_dir))
    done = [0]

    def get(t):
        tiles.ensure(z, *t)
        done[0] += 1
        if progress:
            progress(done[0], len(need))
    for t in need:                                           # по одному, с паузой: порталы не долбим (правило проекта)
        get(t)
    cache, order = {}, []

    def tile(x, y):                                          # последние ~64 тайла держатся в памяти
        if (x, y) not in cache:
            p = tiles.path(z, x, y)
            try:
                im = Image.open(p) if p.exists() else None
                if im is not None and (im.width > MAX_TILE_PX or im.height > MAX_TILE_PX):
                    im = None                                # чужой размер: мозаика рассчитана на 256 × 256
                cache[(x, y)] = im.convert("RGB") if im is not None else None
            except (OSError, ValueError, SyntaxError):
                cache[(x, y)] = None
            order.append((x, y))
            if len(order) > 64:
                cache.pop(order.pop(0), None)
        return cache[(x, y)]

    def render(cx, cy, cw, ch):                              # кусок снимка: пиксели выхода cx…cx+cw, cy…cy+ch
        out = Image.new("RGB", (cw, ch), (200, 200, 200))
        sub = BLOCK // 4
        for by in range(0, ch, BLOCK):
            for bx in range(0, cw, BLOCK):
                bw, bh = min(BLOCK, cw - bx), min(BLOCK, ch - by)
                X = lambda px: x0 + (cx + bx + px) * mpp
                Y = lambda py: y1 - (cy + by + py) * mpp
                corners = [gp(X(px), Y(py)) for px in (0, bw) for py in (0, bh)]
                mx0, my0 = int(min(c[0] for c in corners) // 256), int(min(c[1] for c in corners) // 256)
                mx1, my1 = int(max(c[0] for c in corners) // 256), int(max(c[1] for c in corners) // 256)
                mosaic = Image.new("RGB", ((mx1 - mx0 + 1) * 256, (my1 - my0 + 1) * 256), (200, 200, 200))
                for ty in range(my0, my1 + 1):
                    for tx in range(mx0, mx1 + 1):
                        t = tile(tx, ty)
                        if t:
                            mosaic.paste(t, ((tx - mx0) * 256, (ty - my0) * 256))
                ox, oy, mesh = mx0 * 256, my0 * 256, []
                for sy in range(0, bh, sub):
                    for sx in range(0, bw, sub):
                        ex_, ey = min(sx + sub, bw), min(sy + sub, bh)
                        q = [gp(X(a), Y(b)) for a, b in ((sx, sy), (sx, ey), (ex_, ey), (ex_, sy))]   # NW, SW, SE, NE — порядок MESH
                        mesh.append(((sx, sy, ex_, ey), tuple(v for c in q for v in (c[0] - ox, c[1] - oy))))
                out.paste(mosaic.transform((bw, bh), Image.MESH, mesh, Image.BILINEAR), (bx, by))
        buf = io.BytesIO()
        out.save(buf, "JPEG", quality=90)
        return buf.getvalue()

    # куски: слева направо, сверху вниз; у каждого — рамка в МСК (левый нижний угол и размер)
    parts = []
    for cy in range(0, H, CHUNK):
        for cx in range(0, W, CHUNK):
            cw, ch = min(CHUNK, W - cx), min(CHUNK, H - cy)
            parts.append({"jpg": render(cx, cy, cw, ch), "x": x0 + cx * mpp, "y": y1 - (cy + ch) * mpp, "w": cw, "h": ch})
    return _package(parts, frame, mpp, W, H, z, base)


def _package(parts, frame, mpp, W, H, z, base=""):
    """Архив для AutoCAD: одна папка с кусками снимка, DXF (растры на местах, полный путь base/<файл>), сценарий .scr."""
    import ezdxf
    import dxf_io
    x0, y0, x1, y1 = frame
    base = "".join(c for c in (base or "") if c.isprintable())     # путь уходит в DXF и README: без \r, \n и управляющих
    folder = Path(base).name if base else NAME
    names = [f"{NAME}_{i + 1:02d}.jpg" if len(parts) > 1 else f"{NAME}.jpg" for i in range(len(parts))]
    doc = ezdxf.new("R2018")
    doc.header["$PROJECTNAME"] = ""                        # искать снимки сначала в папке чертежа
    lay_img, lay_fr = dxf_io.acad_name("Спутник Яндекс"), dxf_io.acad_name("Рамка снимка Яндекса")
    doc.layers.add(lay_img)
    doc.layers.add(lay_fr, color=1)
    msp = doc.modelspace()
    scr = []
    for n, p in zip(names, parts):
        w, h = p["w"] * mpp, p["h"] * mpp
        img = doc.add_image_def(filename=(base.rstrip("/\\") + "/" + n) if base else n, size_in_pixel=(p["w"], p["h"]))
        msp.add_image(img, insert=(p["x"], p["y"]), size_in_units=(w, h), rotation=0, dxfattribs={"layer": lay_img})
        scr += ["-IMAGE", "A", n, f"{p['x']:.3f},{p['y']:.3f}", f"{w:.3f}", "0"]
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": lay_fr})
    dxf_io.fit_view(doc)
    buf = io.StringIO()
    doc.write(buf)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, p in zip(names, parts):
            zf.writestr(f"{folder}/{n}", p["jpg"])
            zf.writestr(f"{folder}/{n[:-4]}.jgw", f"{mpp:.6f}\n0.0\n0.0\n{-mpp:.6f}\n{p['x'] + mpp / 2:.4f}\n{p['y'] + p['h'] * mpp - mpp / 2:.4f}\n")
        zf.writestr(f"{folder}/{NAME}.dxf", buf.getvalue().encode("utf-8"))
        zf.writestr(f"{folder}/{NAME}.scr", ("\n".join(scr + ["ZOOM", "E"]) + "\n").encode("utf-8"))
        zf.writestr(f"{folder}/README.txt", (
            "Yandex satellite image of the sheet frame, resampled to MSK (QGIS custom CRS 'MSK': +proj=tmerc +lat_0=55.66666666667 "
            "+lon_0=37.5 +k=1 +x_0=0 +y_0=0 +ellps=bessel), metres.\n"
            f"Pixel {mpp} m, {W} x {H} px in {len(parts)} piece(s), Yandex tiles z{z}. Frame: X {x0:.2f}..{x1:.2f}, Y {y0:.2f}..{y1:.2f}.\n\n"
            f"AutoCAD: open {NAME}.dxf - the images are linked by full path{(' ' + base) if base else ''}; unzip the archive "
            "exactly there (double click in the downloads folder does it).\n"
            f"If the images show as not found: run command SCRIPT with {NAME}.scr while {NAME}.dxf is open.\n"
            "QGIS and AutoCAD Map 3D read the world files .jgw.\n"
            "For working drawings only; not for submitted materials.\n").encode("utf-8"))
    return out.getvalue()
