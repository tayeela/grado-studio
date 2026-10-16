"""Ночная выгрузка ГИС ОГД и ЕГКО на сервер: все слои лежат на диске свежими, «Данные» и DXF берут их оттуда, а не с портала.

Запускается таймером grado-warm (00:30 UTC, 03:30 МСК). Владелец 16.10.2026: «пусть выгрузки всех слоёв ГИС ОГД и ЕГКО
обновляются и полностью скачиваются ночью на сервер, а при выгрузке отдаются с нашего сервера». Поэтому каждую ночь
заново скачиваются все слои каталога ГИС ОГД и картоосновы ЕГКО старше REFRESH (20 ч), самые старые первыми; днём
коннектор отдаёт их с диска (срок слоя в кэше 7 дней у ГИС ОГД и 30 у ЕГКО — ночь пропустили, днём всё равно с диска).
Новые слои после UNTIL (07:00 МСК) не начинаются: остаток — следующей ночью, первым в очереди.
Слои ГИС ОГД — по WORKERS сразу (параллель внутри одной выгрузки разрешена, #51), ЕГКО — по одному (газоны 1,3 ГБ).
Пока сайт сам качает с портала (первая загрузка слоя или «DXF ГИС ОГД»), новые слои не начинаются: один портал
не качают из двух мест сразу. Слои, которые портал не отдаёт, пишутся в список неудач «DXF ГИС ОГД» (сутки не повторяются).
Итог прогона — в журнал (journalctl -u grado-warm) и в <кэш>/warm_status.json.
Прогон один за раз (замок <кэш>/warm.lock): сайт начинает его и днём, если ночного итога нет или он старше суток
(владелец 16.10: «начинай сейчас»), и ночной таймер тогда не запускает второй.

Запуск вручную:  python3 apps/grado2/ogd_warm.py [--cache DIR] [--egko-cache DIR] [--limit N] [--no-egko]
"""

import argparse
import json
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
for sub in ("core/connectors", "core/render", "core/layout"):      # ogd_all тянет dxf_io, ему нужен рендер
    sys.path.insert(0, str(HERE.parents[1] / sub))
sys.path.insert(0, str(HERE))

from grado_connectors.contract import ConnectorError      # noqa: E402
from grado_connectors.gisogd_api import GisogdApi, catalog  # noqa: E402

import ogd_all  # noqa: E402

REFRESH = 20 * 3600                     # слой моложе — уже обновлён этой ночью (или прошлой поздно), не трогаем
UNTIL = 4                               # час UTC (07:00 МСК): позже новые слои не начинаются
WORKERS = 4                             # слоёв ГИС ОГД сразу
FAR = (0.0, 0.0, 0.001, 0.001)          # область вне Москвы: слой кладётся в кэш, объекты в ответ не нужны


def busy(port):
    """Программа сейчас сама качает с портала?"""
    h = {"Host": f"127.0.0.1:{port}"}
    try:
        for path in ("/api/progress", "/api/ogd_all/status"):
            with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=h), timeout=5) as r:
                d = json.load(r)
            if (path == "/api/progress" and d) or (path != "/api/progress" and d.get("running")):
                return True
    except OSError:
        return False                       # программа не отвечает — мешать некому
    return False


def ogd_age(api, code):
    """Возраст слоя ГИС ОГД в кэше, с; нет слоя или он недособран — бесконечность."""
    gz, lines = api._cache_path(code), api._lines_path(code)
    if not (gz.exists() and lines.exists() and lines.stat().st_mtime >= gz.stat().st_mtime):
        return float("inf")
    return time.time() - gz.stat().st_mtime


def egko_age(api, code):
    meta = api._grid_dir(code) / "_meta.json"
    return time.time() - meta.stat().st_mtime if meta.exists() else float("inf")


def stale(items, age):
    """Слои старше REFRESH, самые старые (и не скачанные вовсе) первыми."""
    out = [(age(it["code"]), it) for it in items]
    return [it for a, it in sorted(out, key=lambda x: -x[0]) if a >= REFRESH]


def late(now=None):
    """Утро: ночной прогон новых слоёв уже не начинает (запуск вручную днём не ограничен)."""
    h = (now or datetime.now(timezone.utc)).hour
    return UNTIL <= h < 12


def run(todo, api, failed, port, limit, workers, label, stats):
    """Скачать слои todo; при занятом сайте и после UNTIL новые не начинаются."""
    lock, n = threading.Lock(), [0]

    def one(it):
        code = it["code"]
        bad = failed.get(code)
        if bad and time.time() - bad["at"] < ogd_all._FAILED_TTL:
            return
        with lock:
            if (limit and n[0] >= limit) or late():
                stats["left"] += 1
                return
            n[0] += 1
        while busy(port):
            time.sleep(60)
        try:
            api.fetch(FAR, code)
            with lock:
                failed.pop(code, None)
                stats["got"] += 1
            print(f"{label}: обновлён {code} «{it.get('title') or it.get('name')}»", flush=True)
        except ConnectorError as e:
            with lock:
                failed[code] = {"at": time.time(), "why": str(e)[:80]}
                stats["err"] += 1
            print(f"{label}: не отдан {code} «{it.get('title') or it.get('name')}»: {e}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, todo))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", default=str(Path.home() / ".grado2/cache/gisogd"))
    ap.add_argument("--egko-cache", default=None, help="кэш ЕГКО (по умолчанию — egko рядом с кэшем ГИС ОГД)")
    ap.add_argument("--port", type=int, default=8650)
    ap.add_argument("--limit", type=int, default=0, help="не больше N скачиваний на портал за прогон (0 — без предела)")
    ap.add_argument("--no-egko", action="store_true", help="только ГИС ОГД")
    a = ap.parse_args()
    cache = Path(a.cache)
    egko_cache = Path(a.egko_cache) if a.egko_cache else cache.parent / "egko"
    import fcntl                           # только на сервере (Linux, macOS)
    cache.mkdir(parents=True, exist_ok=True)
    lockf = open(cache / "warm.lock", "w")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("выгрузка уже идёт (другой прогон держит warm.lock) — выхожу", flush=True)
        return
    t0 = time.time()
    report = {"started": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    api = GisogdApi(cache_dir=cache, ttl=REFRESH)
    failed = ogd_all._load_failed(cache)
    items = ogd_all.layer_list(catalog())
    todo = stale(items, lambda c: ogd_age(api, c))
    st = {"got": 0, "err": 0, "left": 0}
    run(todo, api, failed, a.port, a.limit, WORKERS, "ГИС ОГД", st)
    ogd_all._save_failed(cache, failed)
    report["gisogd"] = {"layers": len(items), "fresh": len(items) - len(todo), **st}
    print(f"ГИС ОГД: слоёв {len(items)}, были свежими {len(items) - len(todo)}, обновлено {st['got']}, "
          f"не отдано {st['err']}, отложено до следующей ночи {st['left']}", flush=True)

    if not a.no_egko:
        eapi = GisogdApi(cache_dir=egko_cache, map_name="base2", ttl=REFRESH)
        efailed = ogd_all._load_failed(egko_cache)
        try:
            eitems = [x for x in catalog(map_name="base2") if x.get("code") and x.get("type") != "folder"]
        except ConnectorError as e:
            eitems = []
            print(f"ЕГКО: каталог не получен: {e}", flush=True)
        etodo = stale(eitems, lambda c: egko_age(eapi, c))
        es = {"got": 0, "err": 0, "left": 0}
        left = max(a.limit - st["got"] - st["err"], 0) if a.limit else 0
        if not a.limit or left:
            run(etodo, eapi, efailed, a.port, left, 1, "ЕГКО", es)
        egko_cache.mkdir(parents=True, exist_ok=True)
        ogd_all._save_failed(egko_cache, efailed)
        report["egko"] = {"layers": len(eitems), "fresh": len(eitems) - len(etodo), **es}
        print(f"ЕГКО: слоёв {len(eitems)}, были свежими {len(eitems) - len(etodo)}, обновлено {es['got']}, "
              f"не отдано {es['err']}, отложено до следующей ночи {es['left']}", flush=True)

    report["seconds"] = round(time.time() - t0)
    (cache / "warm_status.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print(f"итог за {report['seconds']} с", flush=True)


if __name__ == "__main__":
    main()
