"""ГРАДО Студия — локальный сервер рабочей программы.

    python3 apps/studio/server.py [порт]

Статика: apps/studio/web. API:
    POST /api/tep    {features, params} → живой ТЭП
    POST /api/album  {features, params, name} → PDF альбома АГК
    POST /api/grado  {features, name} → файл проекта .grado (открывается QGIS)
"""

import json
import sys
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import studio_core  # noqa: E402

WEB = Path(__file__).parent / "web"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8643


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, fmt, *args):
        pass

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

    def do_POST(self):
        try:
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
    print(f"ГРАДО Студия: http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
