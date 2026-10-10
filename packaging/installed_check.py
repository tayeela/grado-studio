"""Check a running ГРАДО 2 (installed or from source) the way an urban planner would use it, and time each step.

Called by .github/workflows/grado2-release.yml after the Windows installer is installed on the runner, and by hand on a
test port (never the owner's 8650): health and version, both interfaces with their assets, ТЭП, DXF / GeoJSON / XLSX export,
a PDF and PPTX album sheet; with --portals also a small data download on an empty cache. Standard library only.
Writes a Markdown table (stdout, and --report FILE); exit code 1 when a required step fails.
"""

import argparse
import io
import json
import re
import sys
import time
import urllib.request
import zipfile

# маленький участок в Хорошёво (lon/lat): здания и дороги ЕГКО, OSM — на пустом кэше это первая настоящая выгрузка
BBOX = [37.4930, 55.7760, 37.4990, 55.7790]
PORTAL_SOURCES = ["egko.buildings", "egko.roads"]
SQ = [[37.4950, 55.7770], [37.4960, 55.7770], [37.4960, 55.7776], [37.4950, 55.7776], [37.4950, 55.7770]]
LAYER = {"name": "Эскиз: здания", "color": "#c08040",
         "features": {"type": "FeatureCollection", "features": [
             {"type": "Feature", "properties": {"Этажность": 9}, "geometry": {"type": "Polygon", "coordinates": [SQ]}}]}}
TEP_SHEET = {"meta": {"object": "Проверка установки"},
             "sheets": [{"title": "ТЭП", "size": "A3", "kind": "tep", "tep": [["Территория", "1,0 га"], ["Население", "120 чел."]]}]}


def call(base, path, body=None, timeout=60):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json"} if data is not None else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def wait_health(base, seconds):
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        try:
            return json.loads(call(base, "/api/health", timeout=2)[2]), time.monotonic() - t0
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(f"no answer from {base}/api/health in {seconds} s")


def zip_names(body):
    return zipfile.ZipFile(io.BytesIO(body)).namelist()


def steps(base, expect_version):
    def health():
        h = json.loads(call(base, "/api/health")[2])
        if expect_version and h.get("version") != expect_version:
            raise AssertionError(f"version {h.get('version')} != {expect_version}")
        return f"версия {h.get('version')}"

    def new_ui():
        st, _, page = call(base, "/next/")
        html = page.decode("utf-8")
        assets = sorted(set(re.findall(r'(?:src|href)="(/next/assets/[^"]+|\./assets/[^"]+|assets/[^"]+)"', html)))
        if not assets:
            raise AssertionError("в /next/ нет ссылок на assets")
        size = 0
        for a in assets:
            url = a if a.startswith("/") else "/next/" + a.removeprefix("./")
            size += len(call(base, url)[2])
        return f"{len(assets)} файлов, {size // 1024} КБ"

    def old_ui():
        st, _, page = call(base, "/old")
        if b"<script" not in page:
            raise AssertionError("/old без скриптов")
        return f"{len(page) // 1024} КБ"

    def sources():
        n = len(json.loads(call(base, "/api/sources")[2]))
        if n < 20:
            raise AssertionError(f"источников {n}")
        return f"{n} источников"

    def tep():
        r = json.loads(call(base, "/api/tep", {"terr_ha": 46, "restrict_ha": 5, "spp_new_m2": 300000, "share": 0.8})[2])
        if not r:
            raise AssertionError("пустой ответ")
        return f"{len(r)} полей"

    def dxf():
        names = zip_names(call(base, "/api/export/dxf", {"layers": [LAYER]})[2])
        need = [n for n in ("red_lns.shx", "REDLN97.LIN") if n not in names] + ([] if any(n.endswith(".dxf") for n in names) else [".dxf"])
        if need:
            raise AssertionError(f"в архиве нет {need}: {names}")
        return ", ".join(names)

    def geojson():
        names = zip_names(call(base, "/api/export/geojson", {"layers": [{"name": LAYER["name"], "features": LAYER["features"]["features"]}]})[2])
        if not any(n.endswith(".geojson") for n in names):
            raise AssertionError(f"нет .geojson: {names}")
        return ", ".join(names)

    def xlsx():
        body = call(base, "/api/export/xlsx", {"tep": [{"group": "Территория", "title": "Площадь", "value": 1.0, "unit": "га"}],
                                               "sheets": [{"n": 1, "title": "ТЭП", "format": "A3", "scale": ""}]})[2]
        if not body.startswith(b"PK"):
            raise AssertionError("не xlsx")
        return f"{len(body) // 1024} КБ"

    def pdf():
        body = call(base, "/api/print/pdf", TEP_SHEET, timeout=120)[2]
        if not body.startswith(b"%PDF") or b"/ToUnicode" not in body:
            raise AssertionError("не PDF или текст не выделяется (нет /ToUnicode)")
        return f"{len(body) // 1024} КБ, текст выделяется"

    def pptx():
        body = call(base, "/api/print/pptx", TEP_SHEET, timeout=120)[2]
        if not body.startswith(b"PK"):
            raise AssertionError("не pptx")
        return f"{len(body) // 1024} КБ"

    return [("Сервер отвечает, версия", health), ("Новый интерфейс /next/ и его файлы", new_ui), ("Прежний интерфейс /old", old_ui),
            ("Список источников данных", sources), ("ТЭП", tep), ("Экспорт DXF (чертёж, red_lns.shx, REDLN97.LIN)", dxf),
            ("Экспорт GeoJSON", geojson), ("Экспорт XLSX", xlsx), ("Альбом PDF", pdf), ("Альбом PPTX", pptx)]


def portals(base):
    st, _, body = call(base, "/api/fetch", {"bbox": BBOX, "territory": BBOX, "sources": PORTAL_SOURCES}, timeout=120)
    r = json.loads(body)
    got = {k: len((v or {}).get("features", [])) for k, v in (r.get("layers") or {}).items()} if isinstance(r.get("layers"), dict) else r.get("layers")
    if r.get("errors"):
        raise AssertionError(f"ошибки порталов: {r['errors']}")
    return f"объектов: {got}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:8651")
    ap.add_argument("--expect-version", default="")
    ap.add_argument("--wait", type=float, default=0, help="seconds to wait for /api/health first (start time is reported)")
    ap.add_argument("--portals", action="store_true", help="also download a small area from the portals (not required to pass)")
    ap.add_argument("--report", default="")
    a = ap.parse_args(argv)
    base = a.url.rstrip("/")
    rows, failed = [], False
    if a.wait:
        try:
            _, took = wait_health(base, a.wait)
            rows.append(("Запуск до первого ответа", "да", f"{took:.1f} с", ""))
        except RuntimeError as e:
            rows.append(("Запуск до первого ответа", "НЕТ", "", str(e)))
            failed = True
    if not failed:
        for title, fn in steps(base, a.expect_version):
            t0 = time.monotonic()
            try:
                note, ok = fn(), "да"
            except Exception as e:
                note, ok, failed = f"{type(e).__name__}: {e}"[:300], "НЕТ", True
            rows.append((title, ok, f"{time.monotonic() - t0:.2f} с", note))
        if a.portals:
            t0 = time.monotonic()
            try:
                note, ok = portals(base), "да"
            except Exception as e:
                note, ok = f"{type(e).__name__}: {e}"[:300], "нет (не обязательно)"
            rows.append(("Выгрузка с порталов на пустом кэше (здания и дороги ЕГКО)", ok, f"{time.monotonic() - t0:.1f} с", note))
    text = "| шаг | прошёл | время | что видно |\n|---|---|---|---|\n" + "".join(
        f"| {t} | {ok} | {s} | {n.replace('|', '/')} |\n" for t, ok, s, n in rows)
    print(text)
    if a.report:
        with open(a.report, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
