"""ГРАДО Студия — локальный сервер рабочей программы.

    python3 apps/studio/server.py [порт]

Статика: apps/studio/web. API:
    POST /api/tep         {features, params} → живой ТЭП
    POST /api/album       {features, params, name} → PDF альбома АГК
    POST /api/grado       {features, name} → файл проекта .grado (открывается QGIS)
    POST /api/open-grado  тело .grado → {name, features} — открыть проект обратно
    POST /api/import-nspd {payload} → фигуры холста из захвата НСПД
    POST /api/import-gisogd  тело ZIP → фигуры холста из выгрузки ГИС ОГД
    GET  /api/inbox       выгрузки браузерного моста, ждущие холст
    GET/POST /api/autosave  файловый бэкап состояния холста (резерв к localStorage)
    GET  /api/basemap-info  {origin_lon, origin_lat, attribution}
    GET  /api/tiles/<z>/<x>/<y>.png  тайловая подложка (прокси + дисковый кэш)
Порт 8081: приёмник браузерного расширения GRADO (совместим с QGIS-плагином).
"""

import json
import re
import socket
import sys
import tempfile
import threading
import traceback
from http.server import (BaseHTTPRequestHandler, SimpleHTTPRequestHandler,
                         ThreadingHTTPServer)
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import studio_core  # noqa: E402

WEB = Path(__file__).parent / "web"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8643
BRIDGE_PORT = 8081  # совместимость с браузерным расширением GRADO

# Тайловая подложка: прокси + дисковый кэш (снимает CORS, бережёт источник
# от повторных запросов). Кэш и загрузка живут в studio_core — их же
# использует подложка листов альбома и печати.
TILE_RE = re.compile(r"^/api/tiles/(\d+)/(\d+)/(\d+)\.png$")

INBOX = []          # выгрузки от расширения, ждущие холст
INBOX_LOCK = threading.Lock()
BRIDGE_ON = False

# файловый автосейв — резервная копия localStorage браузера на диске:
# переживает чистку данных сайта/приватный режим/смену браузера
AUTOSAVE_PATH = Path(__file__).parent / ".autosave.json"
AUTOSAVE_LOCK = threading.Lock()


class BridgeHandler(BaseHTTPRequestHandler):
    """Приёмник браузерного моста GRADO (как HTTP-сервер QGIS-плагина)."""

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path != "/add_feature":
            self.send_error(404)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            source = data.get("grado_source", "nspd")
            if source == "nspd":
                out = studio_core.import_nspd(data)
            elif source == "fgis_tp":
                out = studio_core.import_fgistp(data)
            else:
                out = {"features": [], "notes": [f"неизвестный источник {source}"]}
            with INBOX_LOCK:
                INBOX.append({"source": source, "features": out["features"],
                              "notes": out.get("notes", []),
                              "layer": data.get("grado_layer_name"),
                              "snapshot": out.get("snapshot"),
                              "diff": out.get("diff")})
        except Exception:
            traceback.print_exc()
        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, fmt, *args):
        pass


class V6Server(ThreadingHTTPServer):
    # Safari резолвит localhost в ::1 — слушаем оба loopback-стека
    address_family = socket.AF_INET6


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        # Safari охотно кэширует статику — интерфейс всегда свежий.
        # Тайлы подложки — исключение, у них свой Cache-Control (см. _serve_tile).
        if not self.path.startswith("/api/tiles/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json_body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _send(self, data, ctype, filename=None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            self.send_header("Content-Disposition",
                             f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/inbox":
            with INBOX_LOCK:
                items, INBOX[:] = list(INBOX), []
            self._send(json.dumps({"bridge": BRIDGE_ON, "items": items},
                                  ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")
            return
        if self.path == "/api/styles":
            self._send(json.dumps(studio_core.frontend_styles(),
                                  ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")
            return
        if self.path == "/api/sources":
            self._send(json.dumps(studio_core.sources_journal(),
                                  ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")
            return
        if self.path == "/api/autosave":
            data = AUTOSAVE_PATH.read_bytes() if AUTOSAVE_PATH.exists() else b"null"
            self._send(data, "application/json; charset=utf-8")
            return
        if self.path == "/api/basemap-info":
            from grado_connectors.crs import ORIGIN_LAT, ORIGIN_LON
            self._send(json.dumps({"origin_lon": ORIGIN_LON, "origin_lat": ORIGIN_LAT,
                                   "attribution": studio_core.TILE_ATTRIBUTION},
                                  ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")
            return
        m = TILE_RE.match(self.path)
        if m:
            self._serve_tile(*map(int, m.groups()))
            return
        super().do_GET()

    def _serve_tile(self, z, x, y):
        if not (0 <= z <= 19 and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
            self.send_error(400, "tile coordinates out of range")
            return
        try:
            cache_path = studio_core.fetch_tile_png(z, x, y)
        except Exception:
            # send_error кодирует сообщение как latin-1 — никакой кириллицы
            # и никакого текста исключения (в нём может быть что угодно)
            traceback.print_exc()
            self.send_error(502, "tile upstream error")
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Cache-Control", "public, max-age=604800")  # свои — год не меняются
        data = cache_path.read_bytes()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            if self.path == "/api/autosave":
                n = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(n)
                json.loads(raw)  # не пишем на диск то, что не распарсится обратно
                with AUTOSAVE_LOCK:
                    tmp = AUTOSAVE_PATH.with_suffix(".tmp")
                    tmp.write_bytes(raw)
                    tmp.replace(AUTOSAVE_PATH)
                self.send_response(204)
                self.end_headers()
                return
            if self.path == "/api/import-gisogd":
                n = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(n)
                out = studio_core.import_gisogd(raw)
                self._send(json.dumps(out, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
                return
            if self.path == "/api/open-grado":
                n = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(n)
                with tempfile.NamedTemporaryFile(suffix=".grado") as tmp:
                    tmp.write(raw)
                    tmp.flush()
                    out = studio_core.grado_to_features(tmp.name)
                self._send(json.dumps(out, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
                return
            body = self._json_body()
            features = body.get("features", [])
            params = body.get("params")
            name = body.get("name") or "Концепция развития территории"
            if self.path == "/api/tep":
                out = studio_core.compute_tep(features, params)
                self._send(json.dumps(out, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
            elif self.path == "/api/album":
                pdf = studio_core.make_album(
                    features, name, params, basemap=bool(body.get("basemap")))
                self._send(pdf, "application/pdf", "grado_agk_album.pdf")
            elif self.path == "/api/grado":
                data = studio_core.make_grado(features, name)
                self._send(data, "application/octet-stream", "project.grado")
            elif self.path == "/api/import-nspd":
                out = studio_core.import_nspd(body.get("payload") or body)
                self._send(json.dumps(out, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
            elif self.path == "/api/dxf":
                data = studio_core.make_dxf(features, name)
                self._send(data, "application/dxf", "project.dxf")
            elif self.path == "/api/redline-offset":
                pts = studio_core.redline_offset(
                    body["line"], body.get("radius", 0), body["dist"])
                self._send(json.dumps({"line": pts}).encode(),
                           "application/json; charset=utf-8")
            elif self.path == "/api/print":
                pdf, used = studio_core.make_print(
                    features, name, body.get("scale"), body.get("paper", "A2"),
                    basemap=bool(body.get("basemap")))
                self._send(pdf, "application/pdf",
                           f"chertezh_1-{used}.pdf")
            elif self.path == "/api/redline-stations":
                out = studio_core.redline_stations(
                    body["line"], body.get("radius", 0), body.get("step", 100))
                self._send(json.dumps({"stations": out}).encode(),
                           "application/json; charset=utf-8")
            else:
                self.send_error(404)
        except Exception as e:
            traceback.print_exc()
            msg = json.dumps({"error": str(e)}, ensure_ascii=False).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)


if __name__ == "__main__":
    servers = [ThreadingHTTPServer(("127.0.0.1", PORT), Handler)]
    try:
        servers.append(V6Server(("::1", PORT), Handler))
    except OSError:
        pass  # система без IPv6 — хватит IPv4
    try:
        servers.append(ThreadingHTTPServer(("127.0.0.1", BRIDGE_PORT), BridgeHandler))
        BRIDGE_ON = True
        print(f"Мост расширения GRADO: порт {BRIDGE_PORT}")
    except OSError:
        print(f"Порт {BRIDGE_PORT} занят (вероятно, QGIS с плагином GRADO) — "
              "мост выключен, выгрузки идут в QGIS")
    print(f"ГРАДО Студия: http://localhost:{PORT}")
    if "--open" in sys.argv:
        import webbrowser
        threading.Timer(0.4, webbrowser.open,
                        [f"http://localhost:{PORT}"]).start()
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    servers[0].serve_forever()
