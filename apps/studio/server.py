"""ГРАДО Студия — локальный сервер рабочей программы.

    python3 apps/studio/server.py [порт]

Статика: apps/studio/web. API:
    POST /api/tep    {features, params} → живой ТЭП
    POST /api/album  {features, params, name} → PDF альбома АГК
    POST /api/grado  {features, name} → файл проекта .grado (открывается QGIS)
"""

import json
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

INBOX = []          # выгрузки от расширения, ждущие холст
INBOX_LOCK = threading.Lock()
BRIDGE_ON = False


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
                              "layer": data.get("grado_layer_name")})
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
        # Safari охотно кэширует статику — интерфейс всегда свежий
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
        super().do_GET()

    def do_POST(self):
        try:
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
                pdf = studio_core.make_album(features, name, params)
                self._send(pdf, "application/pdf", "grado_agk_album.pdf")
            elif self.path == "/api/grado":
                data = studio_core.make_grado(features, name)
                self._send(data, "application/octet-stream", "project.grado")
            elif self.path == "/api/import-nspd":
                out = studio_core.import_nspd(body.get("payload") or body)
                self._send(json.dumps(out, ensure_ascii=False).encode(),
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
