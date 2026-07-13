"""ГРАДО Студия — локальный сервер рабочей программы.

    python3 apps/studio/server.py [порт] [/path/to/project.grado] [--open]
    python3 apps/studio/server.py [порт] --hub     ← веб-режим (совместная работа)

Веб-режим (--hub): аккаунты по инвайт-кодам, проекты на сервере с живой
синхронизацией (см. webhub.py). Все /api/* кроме /api/auth/* и /api/hub
требуют сессию; статика открыта (на ней форма входа). Без --hub — локальный
однопользовательский режим, как раньше (авторизации нет).

Статика: apps/studio/web. API:
    POST /api/tep         {features, params} → живой ТЭП
    POST /api/album       {features, params, name} → PDF альбома АГК
    POST /api/grado       {features, name} → файл проекта .grado (открывается QGIS)
    POST /api/open-grado  тело .grado → {name, features} — открыть проект обратно
    GET  /api/initial-grado  (если сервер запущен с .grado arg) → JSON проекта для авто-открытия (packaging / двойной клик)
    POST /api/import-nspd {payload} → фигуры холста из захвата НСПД
    POST /api/import-gisogd  тело ZIP → фигуры холста из выгрузки ГИС ОГД
    GET  /api/inbox       выгрузки браузерного моста, ждущие холст
    GET/POST /api/autosave  файловый автосейв (резерв к localStorage)
    GET  /api/autosave/backups[/N]  список/чтение предыдущих снимков
    GET  /api/version      единая версия приложения и схемы состояния
    GET  /api/basemap-info  {origin_lon, origin_lat, attribution}
    GET  /api/tiles/<z>/<x>/<y>.png  тайловая подложка (прокси + дисковый кэш)
Порт 8081: приёмник браузерного расширения GRADO (совместим с QGIS-плагином).
"""

import hashlib
import json
import re
import socket
import sys
import tempfile
import threading
import traceback
from datetime import datetime, timezone
from http.server import (BaseHTTPRequestHandler, SimpleHTTPRequestHandler,
                         ThreadingHTTPServer)
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import studio_core  # noqa: E402

WEB = Path(__file__).parent / "web"
VERSION_PATH = WEB / "version.json"
VERSION_INFO = json.loads(VERSION_PATH.read_text(encoding="utf-8"))
PORT = 8643
INITIAL_GRADO = None
for a in sys.argv[1:]:
    if a.isdigit():
        PORT = int(a)
    else:
        p = Path(a)
        if p.suffix.lower() == ".grado" and p.exists():
            INITIAL_GRADO = p
BRIDGE_PORT = 8081  # совместимость с браузерным расширением GRADO

# --- веб-режим (совместная работа): --hub ----------------------------------
HUB = None
if "--hub" in sys.argv:
    from webhub import Hub, HubError, SESSION_COOKIE
    HUB = Hub(Path(__file__).parent / ".hub")
else:
    from webhub import HubError, SESSION_COOKIE  # noqa: F401 (единый except)
# в hub-режиме без сессии доступны только эти /api/-пути (вход + статика)
HUB_PUBLIC_API = {"/api/hub", "/api/auth/login", "/api/auth/register",
                  "/api/auth/logout"}

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
AUTOSAVE_BACKUPS = 10
AUTOSAVE_BACKUP_RE = re.compile(r"^/api/autosave/backups/([1-9]|10)$")


def _autosave_backup_path(path, index):
    return path.with_name(f"{path.stem}.{index}{path.suffix}")


def _autosave_corrupt_path(path):
    return path.with_name(f"{path.stem}.corrupt{path.suffix}")


def _autosave_state(payload):
    """Return state from current envelope or a legacy raw-state autosave."""
    if not isinstance(payload, dict):
        raise ValueError("autosave must be an object")
    state = payload.get("state") if isinstance(payload.get("state"), dict) else payload
    if not isinstance(state.get("features"), list):
        raise ValueError("autosave features must be an array")
    return state


def _autosave_envelope(state, raw=None):
    state = _autosave_state(state)
    canonical = raw if raw is not None else json.dumps(
        state, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "schema_version": VERSION_INFO["state_schema_version"],
        "saved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "checksum": hashlib.sha256(canonical).hexdigest(),
        "state": state,
    }


def _read_autosave(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _autosave_meta(payload, index=None, path=None):
    state = _autosave_state(payload)
    return {
        "id": index,
        "saved_at": payload.get("saved_at") if payload is not state else None,
        "checksum": payload.get("checksum") if payload is not state else None,
        "name": state.get("name") or "Без названия",
        "feature_count": len(state["features"]),
        "size": path.stat().st_size if path and path.exists() else None,
    }


def save_autosave(state, raw=None, path=None, backups=AUTOSAVE_BACKUPS):
    """Atomically save state and rotate changed snapshots for recovery."""
    path = path or AUTOSAVE_PATH
    envelope = _autosave_envelope(state, raw=raw)
    data = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    if path.exists():
        try:
            current = _read_autosave(path)
            if _autosave_state(current) == envelope["state"]:
                tmp.unlink(missing_ok=True)
                return _autosave_meta(current, path=path), False
            for index in range(backups, 1, -1):
                older = _autosave_backup_path(path, index - 1)
                if older.exists():
                    older.replace(_autosave_backup_path(path, index))
            path.replace(_autosave_backup_path(path, 1))
        except ValueError:
            # Повреждённый текущий файл не должен навсегда остановить новые
            # сохранения. Оставляем его отдельно для ручной диагностики.
            path.replace(_autosave_corrupt_path(path))
    tmp.replace(path)
    return _autosave_meta(envelope, path=path), True


def list_autosave_backups(path=None, backups=AUTOSAVE_BACKUPS):
    path = path or AUTOSAVE_PATH
    result = []
    for index in range(1, backups + 1):
        backup = _autosave_backup_path(path, index)
        if not backup.exists():
            continue
        try:
            result.append(_autosave_meta(_read_autosave(backup), index, backup))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return result


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


PROJ_STATE_RE = re.compile(r"^/api/projects/([a-z0-9]{12})/state$")
PROJ_SHARE_RE = re.compile(r"^/api/projects/([a-z0-9]{12})/share$")
PROJ_DELETE_RE = re.compile(r"^/api/projects/([a-z0-9]{12})/delete$")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, fmt, *args):
        pass

    # ---------- веб-режим: сессии и JSON-ответы ----------

    def _cookie_token(self):
        from http.cookies import SimpleCookie
        c = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = c.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def _hub_user(self):
        return HUB.session_user(self._cookie_token()) if HUB else None

    def _json(self, obj, status=200, set_cookie=None):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if set_cookie is not None:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def _session_cookie(token, clear=False):
        # Secure не ставим: локально HTTP; на VPS добавит reverse-proxy
        if clear:
            return f"{SESSION_COOKIE}=; Path=/; HttpOnly; Max-Age=0"
        return (f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; "
                f"SameSite=Lax; Max-Age={30 * 24 * 3600}")

    def _hub_gate(self, path):
        """Гейт hub-режима: /api/* без сессии → 401 (кроме входа).

        Возвращает (allowed, login). В локальном режиме всегда allowed."""
        if not HUB or not path.startswith("/api/") or path in HUB_PUBLIC_API:
            return True, self._hub_user() if HUB else None
        login = self._hub_user()
        if not login:
            self._json({"error": "нужен вход"}, 401)
            return False, None
        return True, login

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
        from urllib.parse import urlparse, parse_qs
        parsed0 = urlparse(self.path)
        allowed, hub_login = self._hub_gate(parsed0.path)
        if not allowed:
            return
        if parsed0.path == "/favicon.ico":
            # У приложения пока нет отдельного значка; пустой штатный ответ
            # не создаёт ложную 404-ошибку в консоли браузера.
            self.send_response(204)
            self.end_headers()
            return
        if parsed0.path == "/api/hub":
            info = {"hub": bool(HUB)}
            if HUB and hub_login:
                info.update(HUB.user_info(hub_login))
            self._json(info)
            return
        if parsed0.path == "/api/version":
            self._json(VERSION_INFO)
            return
        if HUB and parsed0.path == "/api/projects":
            self._json({"projects": HUB.list_projects(hub_login)})
            return
        m = PROJ_STATE_RE.match(parsed0.path) if HUB else None
        if m:
            q = parse_qs(parsed0.query)
            since = (q.get("since") or [None])[0]
            try:
                out = HUB.get_state(m.group(1), hub_login,
                                    since=since if since is not None else None)
            except HubError as e:
                self._json({"error": str(e)}, e.status)
                return
            except ValueError:
                self._json({"error": "bad since"}, 400)
                return
            if out.get("unchanged"):
                # 204 нельзя с телом; онлайн-список нужен каждому поллу —
                # отдаём лёгкий 200 без state
                self._json({"rev": out["rev"], "online": out["online"]})
            else:
                self._json(out)
            return
        if HUB and parsed0.path.startswith("/api/autosave"):
            # в hub-режиме файловый автосейв не используется (общий файл
            # затирали бы разные пользователи) — проекты живут в .hub/
            self._send(b"null", "application/json; charset=utf-8")
            return
        if parsed0.path == "/api/autosave/backups":
            with AUTOSAVE_LOCK:
                self._json({"backups": list_autosave_backups()})
            return
        backup_match = AUTOSAVE_BACKUP_RE.match(parsed0.path)
        if backup_match:
            backup = _autosave_backup_path(AUTOSAVE_PATH, int(backup_match.group(1)))
            if not backup.exists():
                self._json({"error": "backup not found"}, 404)
                return
            try:
                with AUTOSAVE_LOCK:
                    self._json(_read_autosave(backup))
            except (OSError, ValueError, json.JSONDecodeError):
                self._json({"error": "backup is damaged"}, 500)
            return
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
        if self.path == "/api/style-overrides":
            self._send(json.dumps(studio_core.load_style_overrides(),
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
                                   "attribution": studio_core.TILE_ATTRIBUTIONS["osm"],
                                   "attributions": studio_core.TILE_ATTRIBUTIONS},
                                  ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")
            return
        if self.path == "/api/initial-grado":
            if INITIAL_GRADO and INITIAL_GRADO.exists():
                try:
                    out = studio_core.grado_to_features(str(INITIAL_GRADO))
                    self._send(json.dumps(out, ensure_ascii=False).encode(),
                               "application/json; charset=utf-8")
                    return
                except Exception:
                    traceback.print_exc()
            # Обычный запуск без переданного .grado — штатный пустой ответ.
            # 200 + null не засоряет консоль браузера ложной ошибкой 404.
            self._send(b"null", "application/json; charset=utf-8")
            return
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        if parsed.path == "/api/downloads-scan":
            # вахта за ~/Downloads: свежие ZIP (выгрузки ГИС ОГД и т.п.),
            # появившиеся после отметки since (unix-секунды). Только чтение
            # списка — сам импорт идёт отдельным подтверждённым запросом.
            try:
                since = float((parse_qs(parsed.query).get("since") or ["0"])[0])
            except ValueError:
                since = 0.0
            files = []
            dl = Path.home() / "Downloads"
            try:
                for p in dl.glob("*.zip"):
                    st = p.stat()
                    if st.st_mtime > since and st.st_size > 0:
                        files.append({"name": p.name, "path": str(p),
                                      "size": st.st_size, "mtime": st.st_mtime})
            except OSError:
                pass
            files.sort(key=lambda f: -f["mtime"])
            self._send(json.dumps({"files": files[:5]}, ensure_ascii=False)
                       .encode(), "application/json; charset=utf-8")
            return
        m = TILE_RE.match(parsed.path)
        if m:
            src = (parse_qs(parsed.query).get("src") or ["osm"])[0]
            self._serve_tile(*map(int, m.groups()), src)
            return
        super().do_GET()

    def _serve_tile(self, z, x, y, source="osm"):
        if not (0 <= z <= 19 and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
            self.send_error(400, "tile coordinates out of range")
            return
        try:
            data, ctype = studio_core.tile_response(z, x, y, source)
        except Exception:
            # send_error кодирует сообщение как latin-1 — никакой кириллицы
            # и никакого текста исключения (в нём может быть что угодно)
            traceback.print_exc()
            self.send_error(502, "tile upstream error")
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "public, max-age=604800")  # свои — год не меняются
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            allowed, hub_login = self._hub_gate(self.path)
            if not allowed:
                return
            # ---------- веб-режим: вход/регистрация/проекты ----------
            if HUB and self.path.startswith("/api/auth/"):
                try:
                    if self.path == "/api/auth/register":
                        b = self._json_body()
                        token = HUB.register(b.get("invite"), b.get("login"),
                                             b.get("password"))
                        self._json(HUB.user_info(HUB.session_user(token)),
                                   set_cookie=self._session_cookie(token))
                    elif self.path == "/api/auth/login":
                        b = self._json_body()
                        token = HUB.login(b.get("login"), b.get("password"))
                        self._json(HUB.user_info(HUB.session_user(token)),
                                   set_cookie=self._session_cookie(token))
                    elif self.path == "/api/auth/logout":
                        HUB.logout(self._cookie_token())
                        self._json({"ok": True},
                                   set_cookie=self._session_cookie("", clear=True))
                    else:
                        self.send_error(404)
                except HubError as e:
                    self._json({"error": str(e)}, e.status)
                return
            if HUB and self.path == "/api/invites":
                try:
                    self._json({"invite": HUB.create_invite(hub_login)})
                except HubError as e:
                    self._json({"error": str(e)}, e.status)
                return
            if HUB and self.path == "/api/projects":
                b = self._json_body()
                self._json(HUB.create_project(hub_login, b.get("name")))
                return
            if HUB:
                m = (PROJ_STATE_RE.match(self.path)
                     or PROJ_SHARE_RE.match(self.path)
                     or PROJ_DELETE_RE.match(self.path))
                if m:
                    pid = m.group(1)
                    try:
                        if self.path.endswith("/state"):
                            b = self._json_body()
                            out = HUB.put_state(pid, hub_login,
                                                b.get("base_rev", -1),
                                                b.get("state"))
                            self._json(out, 409 if out.get("conflict") else 200)
                        elif self.path.endswith("/share"):
                            b = self._json_body()
                            members = HUB.share_project(pid, hub_login,
                                                        (b.get("login") or "").strip())
                            self._json({"members": members})
                        else:                       # /delete
                            HUB.delete_project(pid, hub_login)
                            self._json({"ok": True})
                    except HubError as e:
                        self._json({"error": str(e)}, e.status)
                    except (TypeError, ValueError):
                        self._json({"error": "bad request"}, 400)
                    return
            if HUB and self.path == "/api/autosave":
                self.send_response(204)   # без записи: проекты живут в .hub/
                self.end_headers()
                return
            if self.path == "/api/autosave":
                n = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(n)
                try:
                    state = json.loads(raw)
                    with AUTOSAVE_LOCK:
                        meta, changed = save_autosave(state, raw=raw)
                except (json.JSONDecodeError, ValueError):
                    self._json({"error": "bad autosave state"}, 400)
                    return
                self._json({"saved": changed, **meta})
                return
            if self.path == "/api/style-overrides":
                n = int(self.headers.get("Content-Length", 0))
                overrides = json.loads(self.rfile.read(n))
                if not isinstance(overrides, dict):
                    self.send_error(400, "expected object")
                    return
                studio_core.save_style_overrides(overrides)
                self.send_response(204)
                self.end_headers()
                return
            if self.path == "/api/import-gisogd":
                n = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(n)
                # имя файла (для маршрутизации одиночного GeoJSON) — URL-энкод
                # в заголовке (правило 5: заголовки строго ASCII, кириллица
                # едет процент-кодированной)
                fn = self.headers.get("X-Grado-Filename")
                if fn:
                    from urllib.parse import unquote
                    fn = unquote(fn)
                out = studio_core.import_gisogd(raw, filename=fn or None)
                self._send(json.dumps(out, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
                return
            if self.path == "/api/import-gisogd-url":
                body = self._json_body()
                url = body.get("url")
                if not url:
                    self.send_error(400, "url required")
                    return
                # ZIP по прямой ссылке (пользователь генерирует на портале).
                # SSLContext c certifi обязателен (правило 6: сборка Python.org
                # не видит системные CA); текст ошибки — в JSON-теле, не в
                # send_error (правило 5: заголовки — строго ASCII).
                import urllib.request
                try:
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "grado-studio/0.1"})
                    with urllib.request.urlopen(
                            req, timeout=60,
                            context=studio_core.TILE_SSL_CTX) as resp:
                        raw = resp.read()
                except Exception as e:
                    msg = json.dumps({"error": f"не удалось скачать по ссылке: {e}"},
                                     ensure_ascii=False).encode()
                    self.send_response(400)
                    self.send_header("Content-Type",
                                     "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(msg)))
                    self.end_headers()
                    self.wfile.write(msg)
                    return
                out = studio_core.import_gisogd(raw)
                self._send(json.dumps(out, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
                return
            if self.path == "/api/import-gisogd-path":
                # импорт ГИС ОГД по пути: ZIP (автоподхват из «Загрузок»),
                # распакованная папка или одиночный файл (.geojson/.json/.shp).
                # Безопасность: только внутри ~/Downloads — произвольные пути
                # с холста не читаем (тот же принцип, что был для *.zip)
                body = self._json_body()
                p = Path(str(body.get("path") or "")).resolve()
                dl = (Path.home() / "Downloads").resolve()
                inside = p == dl or dl in p.parents
                ok_kind = (p.is_dir() or
                           (p.is_file() and p.suffix.lower() in
                            (".zip", ".geojson", ".json", ".shp")))
                if not inside or not ok_kind:
                    self.send_error(400, "expected a zip/geojson/shp or folder "
                                         "inside Downloads")
                    return
                out = studio_core.import_gisogd_path(str(p))
                self._send(json.dumps(out, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
                return
            if self.path == "/api/fetch-extent":
                # «Данные по области»: прямые открытые источники (OSM/НСПД)
                # по прямоугольнику WGS84, без моста и без портала
                body = self._json_body()
                bbox = body.get("bbox")
                sources = body.get("sources") or []
                if (not isinstance(bbox, (list, tuple)) or len(bbox) != 4
                        or not isinstance(sources, list)):
                    self.send_error(400, "bbox[4] and sources[] required")
                    return
                try:
                    out = studio_core.fetch_extent(bbox, sources)
                except ValueError as e:   # область больше предела источника
                    msg = json.dumps({"error": str(e)},
                                     ensure_ascii=False).encode()
                    self.send_response(400)
                    self.send_header("Content-Type",
                                     "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(msg)))
                    self.end_headers()
                    self.wfile.write(msg)
                    return
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
            # слои, созданные в панели студии («+ слой») — их шаблон
            # маршрутизации не встроен в сервер, приходит с холста
            layers = body.get("layers")
            if self.path == "/api/tep":
                out = studio_core.compute_tep(features, params)
                self._send(json.dumps(out, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
            elif self.path == "/api/album":
                basemap_source = body.get("basemapSource")
                if basemap_source not in studio_core.TILE_SOURCES:
                    basemap_source = "osm"
                canvas_styles = body.get("canvasStyles")
                if not isinstance(canvas_styles, dict):
                    canvas_styles = None
                project_styles = body.get("projectStyles")
                album_config = body.get("albumConfig")
                pdf = studio_core.make_album(
                    features, name, params, basemap=bool(body.get("basemap")),
                    layers=layers, basemap_source=basemap_source,
                    canvas_styles=canvas_styles, project_styles=project_styles,
                    album_config=album_config)
                self._send(pdf, "application/pdf", "grado_agk_album.pdf")
            elif self.path == "/api/grado":
                project_styles = body.get("projectStyles")
                project_kinds = body.get("projectCustomKinds")
                undo_stack = body.get("undo_stack")
                redo_stack = body.get("redo_stack")
                data = studio_core.make_grado(features, name, layers=layers, project_styles=project_styles, project_custom_kinds=project_kinds, undo_stack=undo_stack, redo_stack=redo_stack)
                self._send(data, "application/octet-stream", "project.grado")
            elif self.path == "/api/import-nspd":
                out = studio_core.import_nspd(body.get("payload") or body)
                self._send(json.dumps(out, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
            elif self.path == "/api/dxf":
                data = studio_core.make_dxf(features, name, layers=layers)
                self._send(data, "application/dxf", "project.dxf")
            elif self.path == "/api/redline-offset":
                pts = studio_core.redline_offset(
                    body["line"], body.get("radius", 0), body["dist"])
                self._send(json.dumps({"line": pts}).encode(),
                           "application/json; charset=utf-8")
            elif self.path == "/api/buffer":
                # общая генерация буферов: точки → circle, линии/дуги/полигоны → офсеты
                dist = float(body.get("dist", 0))
                fillet = float(body.get("fillet", body.get("radius", 0)))
                sides = body.get("sides", "both")
                feats = body.get("features") or []
                # если передали selection-like, используем как есть
                bufs = studio_core.make_buffer(feats, dist, fillet=fillet, sides=sides)
                self._send(json.dumps({"features": bufs}).encode(),
                           "application/json; charset=utf-8")
            elif self.path == "/api/print":
                basemap_source = body.get("basemapSource")
                if basemap_source not in studio_core.TILE_SOURCES:
                    basemap_source = "osm"
                canvas_styles = body.get("canvasStyles")
                if not isinstance(canvas_styles, dict):
                    canvas_styles = None
                project_styles = body.get("projectStyles")
                pdf, used = studio_core.make_print(
                    features, name, body.get("scale"), body.get("paper", "A2"),
                    basemap=bool(body.get("basemap")), layers=layers,
                    basemap_source=basemap_source, canvas_styles=canvas_styles,
                    project_styles=project_styles)
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
