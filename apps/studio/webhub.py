"""Веб-хаб «ГРАДО Студии» — совместная работа (аккаунты, проекты, ревизии).

Включается флагом сервера --hub; без него студия остаётся локальной
однопользовательской (никакой авторизации, всё как раньше).

Модель совместной работы — «живая синхронизация» (решение пользователя):
проект хранится на сервере целиком (тот же формат, что автосейв холста)
с номером ревизии rev. Клиент шлёт state вместе с base_rev; совпало —
принято (rev+1), отстало — 409 с актуальным state, клиент делает
по-объектное слияние и повторяет. Чужие правки клиенты забирают поллингом
GET state?since=rev (204 — без изменений). Сервер конфликты не разрешает —
он только сериализует записи; слияние клиентское (3-way по id объектов).

Хранение файловое, в духе кодовой базы (без БД):
    .hub/users.json      логин → {pw: scrypt, salt, admin, created}
    .hub/invites.json    код → {created, used_by}
    .hub/sessions.json   токен → {login, created}
    .hub/projects/<pid>.json  {id, name, owner, members, rev, updated, state}
Записи атомарные (tmp+replace), доступ под глобальным Lock (нагрузка —
единицы пользователей). Пароли: hashlib.scrypt. Presence (кто онлайн) —
в памяти, на диск не пишется.
"""

import hashlib
import json
import math
import os
import re
import secrets
import threading
import time
from pathlib import Path

SESSION_COOKIE = "grado_session"
SESSION_TTL = 30 * 24 * 3600          # 30 дней
PRESENCE_TTL = 15                     # секунд с последнего поллинга = «онлайн»
LOGIN_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
PASSWORD_MIN_LENGTH = 8
LOGIN_FAILURE_LIMIT = 5
LOGIN_CLIENT_FAILURE_LIMIT = 25
LOGIN_FAILURE_WINDOW = 60
_DUMMY_SALT = bytes.fromhex("4a3f10b9b3e24815bd62a804674b0f2c")
JS_SAFE_INTEGER = 2 ** 53 - 1
MAX_JSON_DEPTH = 64

# ключи state, общие для всех участников проекта; личные (вид, активный
# слой, подложка, undo/redo) на сервер не попадают — каждый смотрит своё
SHARED_STATE_KEYS = (
    "features", "nextId", "name", "density", "ratio", "educationZone",
    "territoryMode", "krail", "kba",
    "layersVisible", "layerLocked", "layerRules", "layerOrder", "layerFmt",
    "layerFields", "layerTitles", "userLayers", "projectStyles",
    "projectCustomKinds", "sources", "albumConfig")

_SHARED_MAP_KEYS = {
    "layersVisible", "layerLocked", "layerRules", "layerFmt", "layerFields",
    "layerTitles", "projectStyles", "albumConfig",
}
_SHARED_OBJECT_LIST_KEYS = {"features", "userLayers", "projectCustomKinds", "sources"}


def _assert_json_value(value, path="state", depth=0):
    """Отклонить значения, которые нельзя без потерь передать браузеру."""
    if depth > MAX_JSON_DEPTH:
        raise HubError(400, f"{path}: слишком глубокая структура")
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int):
        if abs(value) > JS_SAFE_INTEGER:
            raise HubError(400, f"{path}: целое число выходит за безопасный диапазон")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise HubError(400, f"{path}: число должно быть конечным")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_json_value(item, f"{path}[{index}]", depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise HubError(400, f"{path}: ключи объекта должны быть строками")
            _assert_json_value(item, f"{path}.{key}", depth + 1)
        return
    raise HubError(400, f"{path}: неподдерживаемый тип значения")


def _clean_project_name(value, fallback="Новый проект"):
    """Однострочное имя без управляющих символов, безопасное для списков UI."""
    if not isinstance(value, str):
        value = "" if value is None else str(value)
    cleaned = " ".join(value.split()).strip()
    return (cleaned or fallback)[:120]


def _parse_revision(value, field):
    if isinstance(value, bool):
        raise HubError(400, f"{field} должен быть неотрицательным целым числом")
    if isinstance(value, int):
        revision = value
    elif isinstance(value, str) and re.fullmatch(r"\d+", value):
        revision = int(value)
    else:
        raise HubError(400, f"{field} должен быть неотрицательным целым числом")
    if revision < 0 or revision > JS_SAFE_INTEGER:
        raise HubError(400, f"{field} выходит за допустимый диапазон")
    return revision


def _validated_shared_state(state):
    """Оставить разрешённые ключи и отклонить заведомо повреждённый payload."""
    if not isinstance(state, dict):
        raise HubError(400, "state должен быть объектом")
    _assert_json_value(state)
    shared = {key: state[key] for key in SHARED_STATE_KEYS if key in state}
    for key in _SHARED_MAP_KEYS:
        if key in shared and not isinstance(shared[key], dict):
            raise HubError(400, f"{key} должен быть объектом")
    for key in _SHARED_OBJECT_LIST_KEYS:
        if key in shared and (not isinstance(shared[key], list)
                              or not all(isinstance(item, dict) for item in shared[key])):
            raise HubError(400, f"{key} должен быть массивом объектов")
    if "layerOrder" in shared and (not isinstance(shared["layerOrder"], list)
                                    or not all(isinstance(item, str)
                                               for item in shared["layerOrder"])):
        raise HubError(400, "layerOrder должен быть массивом строк")
    if "name" in shared and not isinstance(shared["name"], str):
        raise HubError(400, "name должен быть строкой")
    if "nextId" in shared and (not isinstance(shared["nextId"], int)
                                or isinstance(shared["nextId"], bool)
                                or shared["nextId"] < 1):
        raise HubError(400, "nextId должен быть положительным целым числом")
    for key in ("density", "ratio", "educationZone", "territoryMode", "krail", "kba"):
        value = shared.get(key)
        try:
            valid_number = not isinstance(value, bool) and math.isfinite(float(value))
        except (TypeError, ValueError):
            valid_number = False
        if key in shared and not valid_number:
            raise HubError(400, f"{key} должен быть числом")
    return shared


class HubError(ValueError):
    """Ошибка уровня API: (код HTTP, сообщение пользователю)."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _scrypt(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt,
                          n=2 ** 14, r=8, p=1).hex()


class Hub:
    def __init__(self, root, quiet=False):
        self.root = Path(root)
        self.projects_dir = self.root / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self._secure_permissions(self.root, 0o700)
        self._secure_permissions(self.projects_dir, 0o700)
        self.lock = threading.RLock()
        # Password hashing is deliberately serialized away from the project
        # lock: a slow/hostile login must not stall saves, polling or exports.
        self.login_lock = threading.Lock()
        self.users = self._load("users.json")
        self.invites = self._load("invites.json")
        self.sessions, sessions_reset = self._load_sessions()
        self._validate_account_stores()
        if sessions_reset or self._prune_sessions():
            self._save("sessions.json", self.sessions)
        if sessions_reset and not quiet:
            print("Файл сессий был повреждён — активные входы безопасно сброшены.")
        self.presence = {}   # pid → {login: last_seen_ts} (только память)
        self.login_failures = {}  # (client, login) → timestamps; only memory
        # пустой хаб: печатаем стартовый инвайт, чтобы можно было войти
        if not self.users and not any(
                v.get("used_by") is None for v in self.invites.values()):
            code = self._new_invite_locked()
            if not quiet:
                print(f"Веб-хаб пуст — стартовый инвайт-код: {code}")
                print("Первый зарегистрировавшийся станет администратором.")

    # ---------- файлы ----------

    @staticmethod
    def _secure_permissions(path, mode):
        """Закрыть локальные аккаунты и проекты от других пользователей ОС."""
        try:
            Path(path).chmod(mode)
        except OSError:
            # На Windows ACL управляются системой; chmod может быть недоступен
            # или иметь ограниченную семантику, поэтому запуск не блокируем.
            pass

    def _load(self, name):
        path = self.root / name
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, TypeError):
            raise HubError(500, f"файл хаба {name} повреждён или недоступен") from None
        if not isinstance(data, dict):
            raise HubError(500, f"файл хаба {name} повреждён")
        return data

    def _load_sessions(self):
        """Повреждение эфемерных сессий не должно останавливать весь хаб."""
        path = self.root / "sessions.json"
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return {}, False
        except OSError:
            raise HubError(500, "файл хаба sessions.json недоступен") from None
        except (ValueError, TypeError):
            return {}, True
        return (data, False) if isinstance(data, dict) else ({}, True)

    def _save(self, name, data):
        tmp = self.root / (name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1, allow_nan=False)
            fh.flush()
            os.fsync(fh.fileno())
        path = self.root / name
        tmp.replace(path)
        self._secure_permissions(path, 0o600)

    def _validate_account_stores(self):
        """Не запускать авторизацию на частично записанных учётных данных."""
        for login, user in self.users.items():
            try:
                salt = bytes.fromhex(user["salt"])
                created = user["created"]
                valid = (
                    isinstance(login, str) and LOGIN_RE.fullmatch(login)
                    and isinstance(user, dict)
                    and isinstance(user.get("pw"), str)
                    and re.fullmatch(r"[0-9a-f]{128}", user["pw"])
                    and len(salt) == 16
                    and isinstance(user.get("admin"), bool)
                    and not isinstance(created, bool)
                    and math.isfinite(float(created))
                )
            except (KeyError, TypeError, ValueError, OverflowError):
                valid = False
            if not valid:
                raise HubError(500, "файл хаба users.json повреждён")
        if self.users and not any(user.get("admin") for user in self.users.values()):
            raise HubError(500, "файл хаба users.json повреждён")

        for code, invite in self.invites.items():
            try:
                created = invite["created"]
                used_by = invite.get("used_by")
                valid = (
                    isinstance(code, str) and 8 <= len(code) <= 128
                    and isinstance(invite, dict)
                    and not isinstance(created, bool)
                    and math.isfinite(float(created))
                    and (used_by is None or used_by in self.users)
                )
            except (KeyError, TypeError, ValueError, OverflowError):
                valid = False
            if not valid:
                raise HubError(500, "файл хаба invites.json повреждён")
        for login, user in self.users.items():
            invite_code = user.get("invite")
            invite = self.invites.get(invite_code) if isinstance(invite_code, str) else None
            if not isinstance(invite, dict) or invite.get("used_by") != login:
                raise HubError(500, "файлы учётных данных хаба рассогласованы")

    # ---------- инвайты и аккаунты ----------

    def _new_invite_locked(self):
        code = secrets.token_urlsafe(9)
        self.invites[code] = {"created": time.time(), "used_by": None}
        self._save("invites.json", self.invites)
        return code

    def create_invite(self, login):
        """Новый инвайт-код (только администратор)."""
        with self.lock:
            user = self.users.get(login)
            if not isinstance(user, dict) or not user.get("admin"):
                raise HubError(403, "инвайты создаёт администратор")
            return self._new_invite_locked()

    def register(self, invite, login, password):
        if not LOGIN_RE.match(login or ""):
            raise HubError(400, "логин: 3-32 символа, латиница/цифры/._-")
        if not isinstance(password, str) or len(password) < PASSWORD_MIN_LENGTH:
            raise HubError(400, f"пароль слишком короткий (минимум {PASSWORD_MIN_LENGTH})")
        # Reject invalid invites before paying the scrypt cost. The same
        # checks run again after hashing to close the concurrency window.
        with self.lock:
            inv = self.invites.get(invite or "")
            if not isinstance(inv, dict) or inv.get("used_by"):
                raise HubError(403, "инвайт-код не найден или уже использован")
            if login in self.users:
                raise HubError(409, "такой логин уже занят")
        # Scrypt may take noticeable CPU time. Compute it before entering the
        # global project lock; invite/login uniqueness is rechecked below.
        salt = os.urandom(16)
        password_hash = _scrypt(password, salt)
        with self.lock:
            inv = self.invites.get(invite or "")
            if not isinstance(inv, dict) or inv.get("used_by"):
                raise HubError(403, "инвайт-код не найден или уже использован")
            if login in self.users:
                raise HubError(409, "такой логин уже занят")
            self.users[login] = {
                "pw": password_hash, "salt": salt.hex(),
                "admin": not self.users,      # первый пользователь — админ
                "created": time.time(), "invite": invite}
            inv["used_by"] = login
            self._save("users.json", self.users)
            self._save("invites.json", self.invites)
            return self._new_session_locked(login)

    def login(self, login, password, client_key=""):
        with self.login_lock:
            login_key = login if isinstance(login, str) else "<invalid>"
            client_id = str(client_key or "local")[:128]
            throttle_key = (client_id, login_key[:64])
            client_throttle_key = (client_id, "*")
            now = time.time()
            if len(self.login_failures) > 2048:
                for key, stamps in list(self.login_failures.items()):
                    recent = [stamp for stamp in stamps
                              if stamp > now - LOGIN_FAILURE_WINDOW]
                    if recent:
                        self.login_failures[key] = recent
                    else:
                        del self.login_failures[key]
            attempts = [stamp for stamp in self.login_failures.get(throttle_key, [])
                        if stamp > now - LOGIN_FAILURE_WINDOW]
            client_attempts = [stamp for stamp in self.login_failures.get(
                client_throttle_key, []) if stamp > now - LOGIN_FAILURE_WINDOW]
            if (len(attempts) >= LOGIN_FAILURE_LIMIT or
                    len(client_attempts) >= LOGIN_CLIENT_FAILURE_LIMIT):
                self.login_failures[throttle_key] = attempts
                self.login_failures[client_throttle_key] = client_attempts
                raise HubError(429, "слишком много попыток входа; повторите позже")
            with self.lock:
                stored_user = self.users.get(login or "") if isinstance(login, str) else None
                user = dict(stored_user) if isinstance(stored_user, dict) else None
            try:
                salt = bytes.fromhex(user["salt"]) if user else _DUMMY_SALT
                expected = user["pw"] if user else "-"
            except (KeyError, TypeError, ValueError):
                user = None
                salt = _DUMMY_SALT
                expected = "-"
            # Неизвестный логин проходит тот же дорогой scrypt, что и
            # существующий: ответ по времени не должен выдавать аккаунты.
            candidate = _scrypt(password if isinstance(password, str) else "", salt)
            if not user or not secrets.compare_digest(candidate, expected):
                attempts.append(now)
                client_attempts.append(now)
                self.login_failures[throttle_key] = attempts
                self.login_failures[client_throttle_key] = client_attempts
                raise HubError(401, "неверный логин или пароль")
            self.login_failures.pop(throttle_key, None)
            with self.lock:
                return self._new_session_locked(login)

    def _new_session_locked(self, login):
        token = secrets.token_urlsafe(32)
        self.sessions[token] = {"login": login, "created": time.time()}
        self._prune_sessions()
        self._save("sessions.json", self.sessions)
        return token

    def logout(self, token):
        with self.lock:
            if self.sessions.pop(token or "", None) is not None:
                self._save("sessions.json", self.sessions)

    def _prune_sessions(self):
        deadline = time.time() - SESSION_TTL
        stale = []
        for token, session in self.sessions.items():
            if not isinstance(session, dict):
                stale.append(token)
                continue
            login = session.get("login")
            created = session.get("created")
            try:
                valid_created = (not isinstance(created, bool)
                                 and math.isfinite(float(created))
                                 and float(created) >= deadline)
            except (TypeError, ValueError, OverflowError):
                valid_created = False
            if not isinstance(login, str) or login not in self.users or not valid_created:
                stale.append(token)
        for t in stale:
            del self.sessions[t]
        return bool(stale)

    def session_user(self, token):
        """Логин по токену сессии (None — не авторизован)."""
        with self.lock:
            session_token = token or ""
            s = self.sessions.get(session_token)
            if not s:
                return None
            if s.get("created", 0) < time.time() - SESSION_TTL:
                del self.sessions[session_token]
                self._save("sessions.json", self.sessions)
                return None
            return s["login"]

    def user_info(self, login):
        with self.lock:
            u = self.users.get(login)
            return {"login": login,
                    "admin": bool(isinstance(u, dict) and u.get("admin"))}

    # ---------- проекты ----------

    def _project_path(self, pid):
        if not re.match(r"^[a-z0-9]{12}$", pid or ""):
            raise HubError(400, "некорректный id проекта")
        return self.projects_dir / f"{pid}.json"

    def _read_project(self, pid):
        try:
            with open(self._project_path(pid), encoding="utf-8") as fh:
                project = json.load(fh)
        except FileNotFoundError:
            raise HubError(404, "проект не найден") from None
        except OSError:
            raise HubError(500, "файл проекта недоступен") from None
        except (TypeError, ValueError):
            raise HubError(500, "файл проекта повреждён") from None
        if not isinstance(project, dict) or project.get("id") != pid:
            raise HubError(500, "файл проекта повреждён")
        owner = project.get("owner")
        members = project.get("members")
        updated = project.get("updated")
        try:
            valid_updated = (updated is None or
                             (not isinstance(updated, bool)
                              and math.isfinite(float(updated))))
            _parse_revision(project.get("rev"), "rev")
            _validated_shared_state(project.get("state"))
        except (HubError, TypeError, ValueError, OverflowError):
            raise HubError(500, "файл проекта повреждён") from None
        if (not isinstance(owner, str) or not LOGIN_RE.fullmatch(owner)
                or not isinstance(project.get("name"), str)
                or not isinstance(members, list)
                or not all(isinstance(member, str) and LOGIN_RE.fullmatch(member)
                           for member in members)
                or len(set(members)) != len(members)
                or not valid_updated):
            raise HubError(500, "файл проекта повреждён")
        return project

    def _write_project(self, proj):
        path = self._project_path(proj["id"])
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(proj, fh, ensure_ascii=False, allow_nan=False)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
        self._secure_permissions(path, 0o600)

    def _check_access(self, proj, login):
        if login != proj["owner"] and login not in proj.get("members", []):
            raise HubError(403, "нет доступа к проекту")

    def list_projects(self, login, include_damaged=False):
        out = []
        damaged = 0
        with self.lock:
            for f in sorted(self.projects_dir.glob("*.json")):
                try:
                    p = self._read_project(f.stem)
                except HubError:
                    damaged += 1
                    continue
                if login == p.get("owner") or login in p.get("members", []):
                    out.append({
                        "id": p["id"], "name": p.get("name", "Без имени"),
                        "owner": p["owner"], "members": p.get("members", []),
                        "rev": p.get("rev", 0), "updated": p.get("updated"),
                        "objects": len((p.get("state") or {})
                                       .get("features") or [])})
        out.sort(key=lambda p: -(p["updated"] or 0))
        if include_damaged:
            return {"projects": out, "damaged": damaged}
        return out

    def create_project(self, login, name):
        name = _clean_project_name(name)
        with self.lock:
            for _ in range(32):
                pid = secrets.token_hex(6)
                if not self._project_path(pid).exists():
                    break
            else:
                raise HubError(503, "не удалось создать уникальный id проекта")
            proj = {"id": pid, "name": name, "owner": login,
                    "members": [], "rev": 0, "updated": time.time(),
                    "state": {}}
            self._write_project(proj)
        return {"id": pid, "name": proj["name"]}

    def share_project(self, pid, login, member):
        with self.lock:
            proj = self._read_project(pid)
            if proj["owner"] != login:
                raise HubError(403, "делиться проектом может только владелец")
            if member == proj["owner"]:
                raise HubError(400, "владелец уже имеет доступ")
            if member not in self.users:
                raise HubError(404, f"пользователь «{member}» не найден")
            if member not in proj["members"]:
                proj["members"].append(member)
                self._write_project(proj)
            return proj["members"]

    def delete_project(self, pid, login):
        with self.lock:
            proj = self._read_project(pid)
            if proj["owner"] != login:
                raise HubError(403, "удалять проект может только владелец")
            self._project_path(pid).unlink(missing_ok=True)
            self.presence.pop(pid, None)

    # ---------- состояние проекта: ревизии и синхронизация ----------

    def _touch_presence_locked(self, pid, login):
        seen = self.presence.setdefault(pid, {})
        seen[login] = time.time()

    def _online_locked(self, pid):
        seen = self.presence.get(pid, {})
        deadline = time.time() - PRESENCE_TTL
        return sorted(u for u, ts in seen.items() if ts >= deadline)

    def get_state(self, pid, login, since=None):
        """Состояние проекта; since=rev → None, если не менялось (204)."""
        parsed_since = _parse_revision(since, "since") if since is not None else None
        with self.lock:
            proj = self._read_project(pid)
            self._check_access(proj, login)
            self._touch_presence_locked(pid, login)
            online = self._online_locked(pid)
            if parsed_since is not None and parsed_since == proj.get("rev", 0):
                return {"unchanged": True, "rev": proj["rev"],
                        "online": online}
            return {"rev": proj.get("rev", 0), "state": proj.get("state") or {},
                    "name": proj.get("name"), "owner": proj["owner"],
                    "members": proj.get("members", []), "online": online}

    def put_state(self, pid, login, base_rev, state):
        """Запись state при совпадении base_rev; иначе 409 + актуальное.

        Сервер не сливает — только сериализует: проигравший 409-клиент
        мержит у себя и повторяет с новым base_rev."""
        shared = _validated_shared_state(state)
        revision = _parse_revision(base_rev, "base_rev")
        with self.lock:
            proj = self._read_project(pid)
            self._check_access(proj, login)
            self._touch_presence_locked(pid, login)
            if revision != proj.get("rev", 0):
                return {"conflict": True, "rev": proj["rev"],
                        "state": proj.get("state") or {},
                        "online": self._online_locked(pid)}
            proj["state"] = shared
            proj["rev"] = proj.get("rev", 0) + 1
            proj["updated"] = time.time()
            if shared.get("name"):
                proj["name"] = _clean_project_name(shared["name"])
            self._write_project(proj)
            return {"rev": proj["rev"], "online": self._online_locked(pid)}
