"""ГРАДО 2 · собирает кадр панорамы из скачанных JPEG-тайлов без интерфейса.

Общий API для UI/MCP: проверка метаданных, проекция Pillow MESH, отдельный кэш,
отмена и общий срок 120 секунд. Проверки: tests/test_panorama_io.py.
"""
from __future__ import annotations

import asyncio
import base64
import io
import math
import os
import threading
import time
from pathlib import Path

from PIL import Image
from grado_connectors import netutil
from grado_connectors.contract import ConnectorError
from grado_connectors import yandex_panorama as Y

import portalgate
from preparation import atomic_write, body_hash, utcnow

WIDTH, HEIGHT, HFOV = 1500, 1000, 80
MAX_TILES, MAX_PIXELS, MAX_CACHE = 64, 16_000_000, 512 * 2**20
_SLOT = threading.BoundedSemaphore(1)


def _alive(deadline, cancel):
    if cancel is not None and cancel.is_set():
        raise Y.PanoramaError("cancelled", "Получение кадра отменено")
    if time.monotonic() >= deadline:
        raise Y.PanoramaError("timeout", "Истёк общий срок получения кадра")


def azimuth(point, target):
    lon1, lat1, lon2, lat2 = map(math.radians, [*point, *target])
    dl = lon2 - lon1
    x = math.sin(dl) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dl)
    if abs(x) + abs(y) < 1e-10:
        raise Y.PanoramaError("metadata_unconfirmed", "Для совпавших точки и цели задайте направление вручную")
    return math.degrees(math.atan2(x, y)) % 360


def distance(a, b):
    from grado_connectors import crs
    if 35 <= a[0] <= 40 and 35 <= b[0] <= 40 and 53 <= a[1] <= 58 and 53 <= b[1] <= 58:
        x,y=crs.wgs84_to_msk(*a);u,v=crs.wgs84_to_msk(*b)
        return math.hypot(u-x,v-y)
    x, y, u, v = map(math.radians, [*a, *b])
    z = math.sin((v-y)/2)**2 + math.cos(y)*math.cos(v)*math.sin((u-x)/2)**2
    return 6371008.8 * 2 * math.asin(min(1., math.sqrt(z)))


def plan(meta, bearing, width=WIDTH, height=HEIGHT, deadline=math.inf, cancel=None):
    levels = sorted(meta["levels"], key=lambda v: v["width"])
    level = next((v for v in levels if v["width"] * math.tan(math.radians(HFOV/2)) / math.pi >= width), None)
    if level is None:
        raise Y.PanoramaError("insufficient_resolution", "У панорамы нет уровня нужного разрешения")
    w, h, tw, th = level["width"], level["height"], meta["tileWidth"], meta["tileHeight"]
    focal = width / (2 * math.tan(math.radians(HFOV/2)))
    def uv(px, py):
        x, y = (px-width/2)/focal, (height/2-py)/focal
        u = ((bearing-meta["origin"])/360 + math.atan2(x, 1)/(2*math.pi)) * w
        v = (.5-math.atan2(y, math.hypot(x, 1))/math.pi) * h
        return u, v
    xs, ys = list(range(0, width, 8)) + [width], list(range(0, height, 8)) + [height]
    grid = []
    for yy in ys:
        _alive(deadline, cancel)
        grid.append([uv(xx, yy) for xx in xs])
    points = [p for row in grid for p in row]
    left = math.floor(min(p[0] for p in points))-3
    top = max(0, math.floor(min(p[1] for p in points))-3)
    right = math.ceil(max(p[0] for p in points))+3
    bottom = min(h, math.ceil(max(p[1] for p in points))+3)
    if (right-left)*(bottom-top) > MAX_PIXELS:
        raise Y.PanoramaError("budget_exceeded", "Рабочее изображение превышает предел памяти кадра")
    placements = []
    for period in range(math.floor(left/w), math.floor((right-1)/w)+1):
        lo, hi = max(0, left-period*w), min(w, right-period*w)
        for tx in range(math.floor(lo/tw), math.ceil(hi/tw)):
            for ty in range(math.floor(top/th), math.ceil(bottom/th)):
                placements.append((tx, ty, tx*tw+period*w-left, ty*th-top))
    keys = sorted({(tx, ty) for tx, ty, _, _ in placements})
    if len(keys) > MAX_TILES:
        raise Y.PanoramaError("budget_exceeded", "Для кадра требуется больше 64 тайлов")
    mesh = []
    for row in range(len(ys)-1):
        _alive(deadline, cancel)
        for col in range(len(xs)-1):
            box = (xs[col], ys[row], xs[col+1], ys[row+1])
            # Pillow QUAD: upper-left, lower-left, lower-right, upper-right.
            quad = [grid[r][c] for r,c in ((row,col),(row+1,col),(row+1,col+1),(row,col+1))]
            mesh.append((box, tuple(v for u,vv in quad for v in (u-left,vv-top))))
    return {"level": level["level"], "keys": keys, "placements": placements, "mesh": mesh,
            "workSize": (right-left,bottom-top), "outputSize": (width,height), "uv": uv}


def project_frame(meta, frame_plan, tiles, deadline=math.inf, cancel=None):
    _alive(deadline, cancel)
    work = Image.new("RGB", frame_plan["workSize"])
    try:
        for tx, ty, x, y in frame_plan["placements"]:
            _alive(deadline, cancel)
            if (tx,ty) not in tiles:
                raise Y.PanoramaError("tile_missing", "Для кадра не хватает необходимого тайла")
            raw = tiles[(tx,ty)]
            Y.check_jpeg(raw, meta["tileWidth"], meta["tileHeight"])
            with Image.open(io.BytesIO(raw)) as tile:
                work.paste(tile.convert("RGB"), (x,y))
        _alive(deadline, cancel)
        image = work.transform(frame_plan["outputSize"], Image.Transform.MESH,
                               frame_plan["mesh"], Image.Resampling.BICUBIC)
        try:
            _alive(deadline, cancel)
            result = io.BytesIO()
            image.save(result, "JPEG", quality=92, subsampling=0)
            _alive(deadline, cancel)
            return result.getvalue()
        finally:
            image.close()
    finally:
        work.close()


def _trim(cache, keep):
    files = sorted(cache.rglob("*.jpg"), key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in files)
    for p in files:
        if total <= MAX_CACHE:
            break
        if p in keep:
            continue
        size = p.stat().st_size
        p.unlink(missing_ok=True)
        total -= size


async def get_frame(candidate, target, cache, *, bearing=None, cancel=None, deadline=None, excluded=None):
    start = time.monotonic()
    deadline = min(deadline, start+120) if deadline is not None else start+120
    if not _SLOT.acquire(blocking=False):
        raise Y.PanoramaError("source_unavailable", "Сейчас уже получается другой кадр")
    token, acquired = object(), False
    cache = Path(cache) / "panorama"
    try:
        _alive(deadline, cancel)
        while True:
            _alive(deadline, cancel)
            try:
                portalgate.GATE.acquire({"yandex"}, token, timeout=min(.1, deadline-time.monotonic()), cancel=cancel)
                acquired = True
                break
            except portalgate.Cooling as e:
                raise netutil.RateLimited(429, headers={"Retry-After": str(max(1.,e.until-time.time()))}) from None
            except portalgate.Busy:
                await asyncio.sleep(.1)
        meta = await Y.metadata(*candidate, deadline=deadline, cancel=cancel)
        last_request = time.monotonic()
        if distance(candidate, meta["point"]) > 100:
            raise Y.PanoramaError("no_panorama", "Панорама находится дальше 100 м от выбранной точки")
        direction = float(bearing) % 360 if bearing is not None else azimuth(meta["point"], target)
        if not math.isfinite(direction):
            raise Y.PanoramaError("invalid_input", "Направление должно быть конечным числом")
        if any(pid==meta["panoramaId"] and abs((angle-direction+180)%360-180)<15 for pid,angle in excluded or []):
            raise Y.PanoramaError("duplicate_frame", "Это направление панорамы уже использовано")
        fp = plan(meta, direction, deadline=deadline, cancel=cancel)
        tiles, keep = {}, set()
        for x,y in fp["keys"]:
            _alive(deadline, cancel)
            path = cache / meta["imageId"] / f"{fp['level']}.{x}.{y}.jpg"
            keep.add(path)
            raw = None
            if path.exists():
                try:
                    raw = path.read_bytes()
                    Y.check_jpeg(raw, meta["tileWidth"], meta["tileHeight"])
                    os.utime(path, None)
                except (OSError, Y.PanoramaError):
                    raw = None
            if raw is None:
                while time.monotonic()-last_request < 1:
                    _alive(deadline,cancel)
                    await asyncio.sleep(min(.1, max(0.,1-(time.monotonic()-last_request))))
                try:
                    raw = await Y.tile(meta, fp["level"], x,y, deadline=deadline, cancel=cancel)
                finally:
                    last_request = time.monotonic()
                atomic_write(path, raw)
            tiles[(x,y)] = raw
        # Портал свободен во время локального преобразования; слот кадра ещё удерживается.
        portalgate.GATE.release({"yandex"},token)
        acquired = False
        raw = project_frame(meta,fp,tiles,deadline,cancel)
        _trim(cache,keep)
        return {"image": {"mime":"image/jpeg","data":base64.b64encode(raw).decode("ascii"),
                          "width":WIDTH,"height":HEIGHT,"sha256":body_hash(raw)},
                "panoramaId":meta["panoramaId"],"imageId":meta["imageId"],"point":meta["point"],
                "azimuthDeg":direction,"hfovDeg":HFOV,"takenAt":meta["takenAt"],"downloadedAt":utcnow(),
                "sourceUrl":"https://yandex.ru/maps/?"+f"panorama%5Bpoint%5D={meta['point'][0]},{meta['point'][1]}"}
    except (TimeoutError, asyncio.TimeoutError):
        raise Y.PanoramaError("timeout","Истёк общий срок получения кадра") from None
    except netutil.RateLimited as e:
        # Также работает без глобального policy (например при прямом вызове SDK-сервиса).
        until = portalgate.GATE.defer("yandex",e.headers.get("Retry-After"))
        err = Y.PanoramaError("rate_limited","Яндекс запросил паузу; повторите после указанного срока")
        err.retry_after_at = until
        raise err from None
    except netutil.HttpError as e:
        raise Y.PanoramaError("tile_missing" if e.code==404 else "source_unavailable", "Источник изображения не ответил") from None
    except netutil.NetError:
        raise Y.PanoramaError("source_unavailable", "Нет соединения с источником изображения") from None
    except Y.PanoramaError:
        raise
    except ConnectorError:
        if cancel is not None and cancel.is_set():
            raise Y.PanoramaError("cancelled", "Получение кадра отменено") from None
        raise Y.PanoramaError("source_unavailable", "Источник изображения не ответил") from None
    finally:
        if acquired:
            portalgate.GATE.release({"yandex"},token)
        _SLOT.release()
