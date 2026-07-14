"""ГРАДО Студия — локальный сервер рабочей программы.

    python3 apps/studio/server.py [порт] [/path/to/project.grado] [--open]
    python3 apps/studio/server.py [порт] [/path/to/project.grado] [--desktop]
    python3 apps/studio/server.py [порт] --hub     ← веб-режим (совместная работа)

Веб-режим (--hub): аккаунты по инвайт-кодам, проекты на сервере с живой
синхронизацией (см. webhub.py). Все /api/* кроме /api/auth/* и /api/hub
требуют сессию; статика открыта (на ней форма входа). Без --hub — локальный
однопользовательский режим, как раньше (авторизации нет).

Статика: apps/studio/web. API:
    POST /api/tep         {features, params} → живой ТЭП
    POST /api/preflight   {features, layers, target} → проверка перед выпуском
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
    GET  /api/health       готовность ресурсов и каталога рабочих данных
    GET  /api/basemap-info  {origin_lon, origin_lat, attribution}
    GET  /api/tiles/<z>/<x>/<y>.png  тайловая подложка (прокси + дисковый кэш)
Порт 8081: приёмник браузерного расширения GRADO (совместим с QGIS-плагином).
"""

import hashlib
import hmac
import json
import math
import os
import re
import socket
import sys
import tempfile
import threading
import traceback
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import (BaseHTTPRequestHandler, SimpleHTTPRequestHandler,
                         ThreadingHTTPServer)
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).parent))


def _cloud_mode():
    return "--cloud" in sys.argv or os.environ.get("GRADO_CLOUD") == "1"


def _desktop_mode():
    """Запуск пользователем через приложение или системный лаунчер."""
    return "--desktop" in sys.argv or bool(getattr(sys, "frozen", False))


def _studio_data_dir():
    explicit = os.environ.get("GRADO_STUDIO_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser()
    if sys.platform == "win32" and _desktop_mode():
        base = (os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or
                str(Path.home() / "AppData" / "Local"))
        return Path(base) / "GRADO Studio"
    if getattr(sys, "frozen", False) and sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ГРАДО Студия"
    return Path(__file__).parent


DATA_DIR = _studio_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("GRADO_STUDIO_DATA_DIR", str(DATA_DIR))
import studio_core  # noqa: E402

RESOURCE_ROOT = Path(os.environ.get("RESOURCEPATH", Path(__file__).parent))
WEB = RESOURCE_ROOT / "web"
VERSION_PATH = WEB / "version.json"
VERSION_INFO = json.loads(VERSION_PATH.read_text(encoding="utf-8"))
try:
    PORT = int(os.environ.get("PORT", "8643"))
except ValueError:
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

# --- веб-режим (совместная работа): --hub / --cloud -------------------------
HUB = None
if "--hub" in sys.argv or _cloud_mode():
    from webhub import Hub, HubError, SESSION_COOKIE
    HUB = Hub(DATA_DIR / ".hub")
else:
    from webhub import HubError, SESSION_COOKIE  # noqa: F401 (единый except)
# в hub-режиме без сессии доступны только эти /api/-пути (вход + статика)
HUB_PUBLIC_API = {"/api/hub", "/api/health", "/api/auth/login", "/api/auth/register",
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
AUTOSAVE_PATH = DATA_DIR / ".autosave.json"
AUTOSAVE_LOCK = threading.Lock()
AUTOSAVE_BACKUPS = 10
AUTOSAVE_BACKUP_RE = re.compile(r"^/api/autosave/backups/([1-9]|10)$")
MAX_JSON_BODY = 64 * 1024 * 1024
MAX_FILE_UPLOAD = 256 * 1024 * 1024
REQUEST_TIMEOUT = 60
MAX_PROJECT_NAME = 240
PREFLIGHT_TARGETS = {"album", "grado", "dxf", "print", "tep"}
JS_SAFE_INTEGER = 2 ** 53 - 1
MAX_AUTOSAVE_JSON_DEPTH = 64


class RequestBodyTooLarge(ValueError):
    pass


class BadRequest(ValueError):
    """Запрос клиента нельзя разобрать или он не соответствует API-контракту."""


def _reject_json_constant(token):
    """Python json принимает NaN/Infinity, хотя это не JSON и ломает геометрию."""
    raise BadRequest(f"non-finite JSON number: {token}")


def _autosave_backup_path(path, index):
    return path.with_name(f"{path.stem}.{index}{path.suffix}")


def _autosave_corrupt_path(path):
    return path.with_name(f"{path.stem}.corrupt{path.suffix}")


def _validate_autosave_json(value, path="autosave", depth=0):
    """Reject values that JSON can encode but the browser cannot restore safely."""
    if depth > MAX_AUTOSAVE_JSON_DEPTH:
        raise ValueError(f"{path}: structure is too deep")
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int):
        if abs(value) > JS_SAFE_INTEGER:
            raise ValueError(f"{path}: integer is outside the safe range")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path}: number must be finite")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_autosave_json(item, f"{path}[{index}]", depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path}: object keys must be strings")
            _validate_autosave_json(item, f"{path}.{key}", depth + 1)
        return
    raise ValueError(f"{path}: unsupported value type")


def _autosave_state(payload):
    """Return state from current envelope or a legacy raw-state autosave."""
    if not isinstance(payload, dict):
        raise ValueError("autosave must be an object")
    state = payload.get("state") if isinstance(payload.get("state"), dict) else payload
    if not isinstance(state.get("features"), list):
        raise ValueError("autosave features must be an array")
    if any(not isinstance(feature, dict) for feature in state["features"]):
        raise ValueError("autosave features must contain objects")
    _validate_autosave_json(state)
    return state


def _canonical_autosave_state(state):
    """Stable bytes used to detect silent autosave corruption."""
    return json.dumps(
        _autosave_state(state), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _autosave_envelope(state, raw=None):
    state = _autosave_state(state)
    canonical = _canonical_autosave_state(state)
    return {
        "schema_version": VERSION_INFO["state_schema_version"],
        "saved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "checksum_kind": "sha256-canonical-state-v1",
        "checksum": hashlib.sha256(canonical).hexdigest(),
        "state": state,
    }


def _read_autosave(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_autosave_checksum(payload):
    """Validate current envelopes while accepting old and raw-state files."""
    if payload.get("checksum_kind") != "sha256-canonical-state-v1":
        return
    expected = payload.get("checksum")
    actual = hashlib.sha256(_canonical_autosave_state(payload)).hexdigest()
    if not isinstance(expected, str) or not hmac.compare_digest(expected, actual):
        raise ValueError("autosave checksum mismatch")


def load_autosave(path):
    """Read a usable autosave or fail before malformed JSON reaches the UI."""
    payload = _read_autosave(path)
    _autosave_state(payload)
    _validate_autosave_checksum(payload)
    return payload


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


def _stage_autosave_bytes(path, data):
    """Write and fsync a same-directory temporary file without replacing target."""
    path = Path(path)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return tmp


def _fsync_directory(path):
    """Persist rename metadata where supported; Windows has no directory fsync."""
    if os.name == "nt":
        return
    try:
        fd = os.open(Path(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_bytes(path, data):
    staged = _stage_autosave_bytes(path, data)
    try:
        os.replace(staged, path)
        _fsync_directory(Path(path).parent)
    finally:
        staged.unlink(missing_ok=True)


def save_autosave(state, raw=None, path=None, backups=AUTOSAVE_BACKUPS):
    """Atomically save state and rotate changed snapshots for recovery."""
    path = Path(path or AUTOSAVE_PATH)
    envelope = _autosave_envelope(state, raw=raw)
    data = json.dumps(
        envelope, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    staged = _stage_autosave_bytes(path, data)
    try:
        if path.exists():
            try:
                current = load_autosave(path)
                if _autosave_state(current) == envelope["state"]:
                    return _autosave_meta(current, path=path), False
                for index in range(backups, 1, -1):
                    older = _autosave_backup_path(path, index - 1)
                    if older.exists():
                        older.replace(_autosave_backup_path(path, index))
                # Keep the current file at its canonical path until the new
                # snapshot is fully staged. A crash cannot leave no autosave.
                _atomic_write_bytes(
                    _autosave_backup_path(path, 1), path.read_bytes())
            except (ValueError, json.JSONDecodeError):
                # Повреждённый текущий файл не должен навсегда остановить новые
                # сохранения. Оставляем его отдельно для ручной диагностики.
                _atomic_write_bytes(_autosave_corrupt_path(path), path.read_bytes())
        os.replace(staged, path)
        _fsync_directory(path.parent)
        return _autosave_meta(envelope, path=path), True
    finally:
        staged.unlink(missing_ok=True)


def list_autosave_backups(path=None, backups=AUTOSAVE_BACKUPS):
    path = path or AUTOSAVE_PATH
    result = []
    for index in range(1, backups + 1):
        backup = _autosave_backup_path(path, index)
        if not backup.exists():
            continue
        try:
            result.append(_autosave_meta(load_autosave(backup), index, backup))
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

    def setup(self):
        super().setup()
        self.connection.settimeout(REQUEST_TIMEOUT)

    def _reply(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

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
            if n < 0:
                raise BadRequest("invalid content length")
            if n > MAX_JSON_BODY:
                self._reply(413, {"error": "request body is too large"})
                return
            raw = self.rfile.read(n)
            if len(raw) != n:
                raise BadRequest("incomplete request body")
            data = json.loads(raw.decode("utf-8"),
                              parse_constant=_reject_json_constant)
            if not isinstance(data, dict):
                raise BadRequest("JSON body must be an object")
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
        except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._reply(400, {"error": str(exc) or "invalid request"})
            return
        except Exception:
            traceback.print_exc()
            self._reply(500, {"error": "bridge import failed"})
            return
        self._reply(200, {"ok": True})

    def log_message(self, fmt, *args):
        pass


class V6Server(ThreadingHTTPServer):
    # Safari резолвит localhost в ::1 — слушаем оба loopback-стека
    address_family = socket.AF_INET6
    # Долгий внешний импорт/рендер не должен удерживать процесс после того,
    # как пользователь закрыл настольное приложение.
    daemon_threads = True


PROJ_STATE_RE = re.compile(r"^/api/projects/([a-z0-9]{12})/state$")
PROJ_SHARE_RE = re.compile(r"^/api/projects/([a-z0-9]{12})/share$")
PROJ_DELETE_RE = re.compile(r"^/api/projects/([a-z0-9]{12})/delete$")


class Handler(SimpleHTTPRequestHandler):
    server_version = "GRADO-Studio"
    sys_version = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def version_string(self):
        return self.server_version

    def setup(self):
        super().setup()
        # Облачный режим не должен бессрочно держать поток на клиенте,
        # объявившем Content-Length и переставшем передавать тело запроса.
        self.connection.settimeout(REQUEST_TIMEOUT)

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
        secure = "; Secure" if _cloud_mode() or os.environ.get(
            "GRADO_SECURE_COOKIES") == "1" else ""
        if clear:
            return (f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; "
                    f"Max-Age=0{secure}")
        return (f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; "
                f"SameSite=Lax; Max-Age={30 * 24 * 3600}{secure}")

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

    def _same_origin_post(self):
        """Браузерные POST принимаются только со страницы этого сервера.

        У CLI и нативных интеграций Origin отсутствует — их не блокируем.
        Проверка защищает локальные файловые и сетевые API от фонового вызова
        произвольным сайтом, открытым в браузере пользователя.
        """
        origin = (self.headers.get("Origin") or "").strip()
        if not origin:
            return True
        host = (self.headers.get("Host") or "").strip().lower()
        try:
            parsed = urlsplit(origin)
        except ValueError:
            return False
        if parsed.scheme not in {"http", "https"} or not host or \
                parsed.netloc.lower() != host:
            return False
        # Сравнить Origin и Host недостаточно: при DNS rebinding вредоносная
        # страница может открыться как evil.example -> 127.0.0.1 и прислать
        # одинаковые Host/Origin. Локальная Студия штатно доступна только через
        # loopback-имена; нативные интеграции без Origin остаются совместимы.
        if not _cloud_mode():
            return (parsed.hostname or "").lower() in {
                "localhost", "127.0.0.1", "::1",
            }
        return True

    def end_headers(self):
        # Safari охотно кэширует статику — интерфейс всегда свежий.
        # Тайлы подложки — исключение, у них свой Cache-Control (см. _serve_tile).
        if not self.path.startswith("/api/tiles/"):
            self.send_header("Cache-Control", "no-store")
        if _cloud_mode():
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Permissions-Policy",
                             "camera=(), microphone=(), geolocation=()")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data: blob:; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; connect-src 'self'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.send_header("Strict-Transport-Security",
                             "max-age=31536000; includeSubDomains")
        super().end_headers()

    def _json_body(self):
        try:
            payload = json.loads(
                self._read_body(MAX_JSON_BODY).decode("utf-8"),
                parse_constant=_reject_json_constant)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BadRequest("invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise BadRequest("JSON body must be an object")
        return payload

    def _read_body(self, limit):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            raise ValueError("invalid content length") from None
        if length < 0:
            raise ValueError("invalid content length")
        if length > limit:
            raise RequestBodyTooLarge(f"request exceeds {limit} bytes")
        body = self.rfile.read(length)
        if len(body) != length:
            raise BadRequest("incomplete request body")
        return body

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
        if parsed0.path == "/api/health":
            checks = {
                "web": (WEB / "index.html").is_file(),
                "preset": studio_core.PRESET.is_file(),
                "data_writable": DATA_DIR.is_dir() and os.access(DATA_DIR, os.W_OK),
            }
            ok = all(checks.values())
            self._json({"ok": ok, "version": VERSION_INFO["version"],
                        "packaged": bool(getattr(sys, "frozen", False)),
                        "checks": checks}, 200 if ok else 503)
            return
        if HUB and parsed0.path == "/api/projects":
            if HUB.user_info(hub_login)["admin"]:
                self._json(HUB.list_projects(hub_login, include_damaged=True))
            else:
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
                    self._json(load_autosave(backup))
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
            if not AUTOSAVE_PATH.exists():
                self._json(None)
                return
            try:
                with AUTOSAVE_LOCK:
                    self._json(load_autosave(AUTOSAVE_PATH))
            except (OSError, ValueError, json.JSONDecodeError):
                self._json({"error": "autosave is damaged"}, 500)
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
            if not _server_side_import_enabled():
                self._send(b'{"files": []}',
                           "application/json; charset=utf-8")
                return
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
        if parsed.path.startswith("/api/"):
            self._json({"error": "api endpoint not found"}, 404)
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
            if not self._same_origin_post():
                self._json({"error": "cross-origin request rejected"}, 403)
                return
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
                        client = self.client_address[0] if self.client_address else "local"
                        token = HUB.login(b.get("login"), b.get("password"),
                                          client_key=client)
                        self._json(HUB.user_info(HUB.session_user(token)),
                                   set_cookie=self._session_cookie(token))
                    elif self.path == "/api/auth/logout":
                        HUB.logout(self._cookie_token())
                        self._json({"ok": True},
                                   set_cookie=self._session_cookie("", clear=True))
                    else:
                        self._json({"error": "api endpoint not found"}, 404)
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
                raw = self._read_body(MAX_JSON_BODY)
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
                overrides = self._json_body()
                studio_core.save_style_overrides(overrides)
                self.send_response(204)
                self.end_headers()
                return
            if self.path == "/api/import-gisogd":
                raw = self._read_body(MAX_FILE_UPLOAD)
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
                if not _server_side_import_enabled():
                    self.send_error(403, "URL import disabled in cloud mode")
                    return
                body = self._json_body()
                url = body.get("url")
                if not url:
                    self.send_error(400, "url required")
                    return
                parsed_url = urlsplit(url) if isinstance(url, str) else None
                if not parsed_url or parsed_url.scheme not in {"http", "https"}:
                    self._json({"error": "допустимы только ссылки http и https"}, 400)
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
                        declared = resp.headers.get("Content-Length")
                        if declared is not None and int(declared) > MAX_FILE_UPLOAD:
                            self._json({"error": "скачиваемый файл слишком большой"}, 413)
                            return
                        raw = resp.read(MAX_FILE_UPLOAD + 1)
                        if len(raw) > MAX_FILE_UPLOAD:
                            self._json({"error": "скачиваемый файл слишком большой"}, 413)
                            return
                except Exception:
                    traceback.print_exc()
                    msg = json.dumps(
                        {"error": "не удалось скачать файл по указанной ссылке"},
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
                if not _server_side_import_enabled():
                    self.send_error(403, "path import disabled in cloud mode")
                    return
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
                raw = self._read_body(MAX_FILE_UPLOAD)
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
            raw_name = body.get("name")
            if raw_name is not None and not isinstance(raw_name, str):
                raise BadRequest("name must be a string")
            name = (raw_name or "Концепция развития территории").strip()
            name = (name or "Концепция развития территории")[:MAX_PROJECT_NAME]
            # слои, созданные в панели студии («+ слой») — их шаблон
            # маршрутизации не встроен в сервер, приходит с холста
            layers = body.get("layers")
            if not isinstance(features, list):
                raise BadRequest("features must be an array")
            if any(not isinstance(item, dict) for item in features):
                raise BadRequest("features must contain objects")
            if params is not None and not isinstance(params, dict):
                raise BadRequest("params must be an object")
            if layers is not None and (not isinstance(layers, list)
                                       or any(not isinstance(item, dict)
                                              for item in layers)):
                raise BadRequest("layers must be an array of objects")
            for key, expected in (("projectStyles", dict),
                                  ("projectCustomKinds", list),
                                  ("albumConfig", dict),
                                  ("studioState", dict),
                                  ("undo_stack", list),
                                  ("redo_stack", list)):
                if body.get(key) is not None and not isinstance(body[key], expected):
                    raise BadRequest(f"{key} has invalid type")
            if body.get("projectCustomKinds") is not None and any(
                    not isinstance(item, dict) for item in body["projectCustomKinds"]):
                raise BadRequest("projectCustomKinds must contain objects")
            for key in ("undo_stack", "redo_stack"):
                if body.get(key) is not None and any(
                        not isinstance(item, str) for item in body[key]):
                    raise BadRequest(f"{key} must contain strings")
            output_targets = {
                "/api/album": "album", "/api/grado": "grado",
                "/api/dxf": "dxf", "/api/print": "print",
            }
            if self.path in output_targets:
                report = studio_core.preflight_project(
                    features, layers=layers, target=output_targets[self.path])
                if report["errors"]:
                    self._json({"error": "project preflight failed",
                                "report": report}, 400)
                    return
            if self.path == "/api/preflight":
                target = body.get("target", "grado")
                if target not in PREFLIGHT_TARGETS:
                    raise BadRequest("unsupported preflight target")
                out = studio_core.preflight_project(
                    features, layers=layers, target=target)
                self._send(json.dumps(out, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
            elif self.path == "/api/tep":
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
                studio_state = body.get("studioState")
                data = studio_core.make_grado(
                    features, name, layers=layers,
                    project_styles=project_styles,
                    project_custom_kinds=project_kinds,
                    undo_stack=undo_stack, redo_stack=redo_stack,
                    studio_state=studio_state)
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
                self._json({"error": "api endpoint not found"}, 404)
        except RequestBodyTooLarge:
            self._json({"error": "request body too large"}, 413)
        except (BadRequest, json.JSONDecodeError, UnicodeDecodeError,
                TypeError, ValueError, KeyError):
            self._json({"error": "invalid request body"}, 400)
        except Exception:
            traceback.print_exc()
            # Детали остаются в локальном журнале, но не покидают сервер:
            # пути, URL источников и содержимое исключений могут быть приватными.
            self._json({"error": "internal server error"}, 500)


def _should_open_browser():
    return ("--open" in sys.argv or _desktop_mode()) and \
           os.environ.get("GRADO_NO_BROWSER") != "1"


def _running_studio_version(port):
    """Версия уже работающей Студии на порту или None для чужого сервиса."""
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/version", timeout=0.35) as response:
            payload = json.loads(response.read().decode("utf-8"))
        version = payload.get("version") if isinstance(payload, dict) else None
        return version if isinstance(version, str) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _port_candidates(port):
    """В настольном запуске ищем свободный порт; dev-запуск остаётся строгим."""
    if _desktop_mode():
        return range(port, port + 10)
    return (port,)


def _server_host():
    explicit = os.environ.get("GRADO_HOST")
    if explicit:
        return explicit
    return "0.0.0.0" if _cloud_mode() else "127.0.0.1"


def _bridge_enabled():
    return not _cloud_mode() and os.environ.get("GRADO_DISABLE_BRIDGE") != "1"


def _server_side_import_enabled():
    """Не превращать облачный сервер в файловый или сетевой прокси."""
    return not _cloud_mode()


def main():
    global PORT, BRIDGE_ON
    servers = []
    original_port = PORT
    host = _server_host()
    for candidate in _port_candidates(original_port):
        try:
            servers = [ThreadingHTTPServer((host, candidate), Handler)]
            PORT = candidate
            break
        except OSError:
            # Повторный двойной клик без файла просто возвращает пользователя
            # в уже открытую Студию. Проект .grado запускаем на новом порту,
            # чтобы переданный файл не потерялся.
            if (candidate == original_port and INITIAL_GRADO is None and
                    _running_studio_version(candidate)):
                if _should_open_browser():
                    webbrowser.open(f"http://localhost:{candidate}")
                print(f"ГРАДО Студия уже работает: http://localhost:{candidate}")
                return 0
            if not _desktop_mode():
                raise
    if not servers:
        raise OSError("no free local port for GRADO Studio")
    if host in ("127.0.0.1", "localhost"):
        try:
            servers.append(V6Server(("::1", PORT), Handler))
        except OSError:
            pass  # система без IPv6 — хватит IPv4
    if _bridge_enabled():
        try:
            servers.append(ThreadingHTTPServer(("127.0.0.1", BRIDGE_PORT), BridgeHandler))
            BRIDGE_ON = True
            print(f"Мост расширения GRADO: порт {BRIDGE_PORT}")
        except OSError:
            print(f"Порт {BRIDGE_PORT} занят (вероятно, QGIS с плагином GRADO) — "
                  "мост выключен, выгрузки идут в QGIS")
    shown_host = "localhost" if host in ("0.0.0.0", "127.0.0.1") else host
    print(f"ГРАДО Студия: http://{shown_host}:{PORT}")
    if _should_open_browser():
        threading.Timer(0.4, webbrowser.open,
                        [f"http://localhost:{PORT}"]).start()
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for server in servers:
            server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
