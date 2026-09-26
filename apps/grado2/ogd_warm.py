"""Прогрев кэша ГИС ОГД на сервере: все слои каталога лежат на диске свежими, выгрузка по листу берёт их оттуда.

Запускается таймером grado-warm (ночью). Слой в кэше живёт 7 дней (TTL коннектора); здесь заново скачиваются
слои старше REFRESH (6 дней), чтобы днём срок ни у одного не истёк. Свежие слои пропускаются без чтения.
По одному слою, с паузой коннектора: портал не долбим. Пока в самой программе идёт выгрузка (первая загрузка слоя
или «DXF ГИС ОГД»), прогрев ждёт — два параллельных скачивания с портала запрещены правилами проекта.
Слои, которые портал не отдаёт, пишутся в тот же список неудач, что и у «DXF ГИС ОГД» (сутки не повторяются).

Запуск вручную:  python3 apps/grado2/ogd_warm.py [--cache DIR] [--limit N]
"""

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
for sub in ("core/connectors", "core/render", "core/layout"):      # ogd_all тянет dxf_io, ему нужен рендер
    sys.path.insert(0, str(HERE.parents[1] / sub))
sys.path.insert(0, str(HERE))

from grado_connectors.contract import ConnectorError      # noqa: E402
from grado_connectors.gisogd_api import GisogdApi, catalog  # noqa: E402

import ogd_all  # noqa: E402

REFRESH = 6 * 24 * 3600
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


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", default=str(Path.home() / ".grado2/cache/gisogd"))
    ap.add_argument("--port", type=int, default=8650)
    ap.add_argument("--limit", type=int, default=0, help="не больше N скачиваний за прогон (0 — без предела)")
    a = ap.parse_args()
    cache = Path(a.cache)
    api = GisogdApi(cache_dir=cache, ttl=REFRESH)
    failed = ogd_all._load_failed(cache)
    fresh = got = err = 0
    t0 = time.time()
    for it in ogd_all.layer_list(catalog()):
        code = it["code"]
        gz, lines = api._cache_path(code), api._lines_path(code)
        if gz.exists() and lines.exists() and time.time() - gz.stat().st_mtime < REFRESH and lines.stat().st_mtime >= gz.stat().st_mtime:
            fresh += 1
            continue
        bad = failed.get(code)
        if bad and time.time() - bad["at"] < ogd_all._FAILED_TTL:
            continue
        if a.limit and got >= a.limit:
            break
        while busy(a.port):
            time.sleep(60)
        try:
            api.fetch(FAR, code)
            failed.pop(code, None)
            got += 1
            print(f"обновлён {code} «{it['title']}»", flush=True)
        except ConnectorError as e:
            failed[code] = {"at": time.time(), "why": str(e)[:80]}
            err += 1
            print(f"не отдан {code} «{it['title']}»: {e}", flush=True)
        ogd_all._save_failed(cache, failed)
    print(f"итог: свежих {fresh}, обновлено {got}, не отдано {err}, {time.time() - t0:.0f} с")


if __name__ == "__main__":
    main()
