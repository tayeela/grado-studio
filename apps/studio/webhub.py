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

# ключи state, общие для всех участников проекта; личные (вид, активный
# слой, подложка, undo/redo) на сервер не попадают — каждый смотрит своё
SHARED_STATE_KEYS = (
    "features", "nextId", "name", "density", "ratio", "krail", "kba",
    "layersVisible", "layerLocked", "layerRules", "layerOrder", "layerFmt",
    "layerFields", "layerTitles", "userLayers", "projectStyles",
    "projectCustomKinds", "sources", "albumConfig")


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
        self.lock = threading.RLock()
        self.users = self._load("users.json")
        self.invites = self._load("invites.json")
        self.sessions = self._load("sessions.json")
        self._prune_sessions()
        self.presence = {}   # pid → {login: last_seen_ts} (только память)
        # пустой хаб: печатаем стартовый инвайт, чтобы можно было войти
        if not self.users and not any(
                v.get("used_by") is None for v in self.invites.values()):
            code = self._new_invite_locked()
            if not quiet:
                print(f"Веб-хаб пуст — стартовый инвайт-код: {code}")
                print("Первый зарегистрировавшийся станет администратором.")

    # ---------- файлы ----------

    def _load(self, name):
        try:
            with open(self.root / name, encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, name, data):
        tmp = self.root / (name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(self.root / name)

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
            if not user or not user.get("admin"):
                raise HubError(403, "инвайты создаёт администратор")
            return self._new_invite_locked()

    def register(self, invite, login, password):
        with self.lock:
            inv = self.invites.get(invite or "")
            if not inv or inv.get("used_by"):
                raise HubError(403, "инвайт-код не найден или уже использован")
            if not LOGIN_RE.match(login or ""):
                raise HubError(400, "логин: 3-32 символа, латиница/цифры/._-")
            if login in self.users:
                raise HubError(409, "такой логин уже занят")
            if len(password or "") < 6:
                raise HubError(400, "пароль слишком короткий (минимум 6)")
            salt = os.urandom(16)
            self.users[login] = {
                "pw": _scrypt(password, salt), "salt": salt.hex(),
                "admin": not self.users,      # первый пользователь — админ
                "created": time.time(), "invite": invite}
            inv["used_by"] = login
            self._save("users.json", self.users)
            self._save("invites.json", self.invites)
            return self._new_session_locked(login)

    def login(self, login, password):
        with self.lock:
            user = self.users.get(login or "")
            if not user or _scrypt(password or "",
                                   bytes.fromhex(user["salt"])) != user["pw"]:
                raise HubError(401, "неверный логин или пароль")
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
        stale = [t for t, s in self.sessions.items()
                 if s.get("created", 0) < deadline]
        for t in stale:
            del self.sessions[t]

    def session_user(self, token):
        """Логин по токену сессии (None — не авторизован)."""
        with self.lock:
            s = self.sessions.get(token or "")
            if not s or s.get("created", 0) < time.time() - SESSION_TTL:
                return None
            return s["login"]

    def user_info(self, login):
        u = self.users.get(login)
        return {"login": login, "admin": bool(u and u.get("admin"))}

    # ---------- проекты ----------

    def _project_path(self, pid):
        if not re.match(r"^[a-z0-9]{12}$", pid or ""):
            raise HubError(400, "некорректный id проекта")
        return self.projects_dir / f"{pid}.json"

    def _read_project(self, pid):
        try:
            with open(self._project_path(pid), encoding="utf-8") as fh:
                return json.load(fh)
        except OSError:
            raise HubError(404, "проект не найден") from None

    def _write_project(self, proj):
        path = self._project_path(proj["id"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(proj, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def _check_access(self, proj, login):
        if login != proj["owner"] and login not in proj.get("members", []):
            raise HubError(403, "нет доступа к проекту")

    def list_projects(self, login):
        out = []
        with self.lock:
            for f in sorted(self.projects_dir.glob("*.json")):
                try:
                    with open(f, encoding="utf-8") as fh:
                        p = json.load(fh)
                except (OSError, ValueError):
                    continue
                if login == p.get("owner") or login in p.get("members", []):
                    out.append({
                        "id": p["id"], "name": p.get("name", "Без имени"),
                        "owner": p["owner"], "members": p.get("members", []),
                        "rev": p.get("rev", 0), "updated": p.get("updated"),
                        "objects": len((p.get("state") or {})
                                       .get("features") or [])})
        out.sort(key=lambda p: -(p["updated"] or 0))
        return out

    def create_project(self, login, name):
        name = (name or "").strip() or "Новый проект"
        pid = secrets.token_hex(6)
        proj = {"id": pid, "name": name[:120], "owner": login,
                "members": [], "rev": 0, "updated": time.time(),
                "state": {}}
        with self.lock:
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
        with self.lock:
            proj = self._read_project(pid)
            self._check_access(proj, login)
            self._touch_presence_locked(pid, login)
            online = self._online_locked(pid)
            if since is not None and int(since) == proj.get("rev", 0):
                return {"unchanged": True, "rev": proj["rev"],
                        "online": online}
            return {"rev": proj.get("rev", 0), "state": proj.get("state") or {},
                    "name": proj.get("name"), "owner": proj["owner"],
                    "members": proj.get("members", []), "online": online}

    def put_state(self, pid, login, base_rev, state):
        """Запись state при совпадении base_rev; иначе 409 + актуальное.

        Сервер не сливает — только сериализует: проигравший 409-клиент
        мержит у себя и повторяет с новым base_rev."""
        if not isinstance(state, dict):
            raise HubError(400, "state должен быть объектом")
        shared = {k: state[k] for k in SHARED_STATE_KEYS if k in state}
        with self.lock:
            proj = self._read_project(pid)
            self._check_access(proj, login)
            self._touch_presence_locked(pid, login)
            if int(base_rev) != proj.get("rev", 0):
                return {"conflict": True, "rev": proj["rev"],
                        "state": proj.get("state") or {},
                        "online": self._online_locked(pid)}
            proj["state"] = shared
            proj["rev"] = proj.get("rev", 0) + 1
            proj["updated"] = time.time()
            if shared.get("name"):
                proj["name"] = str(shared["name"])[:120]
            self._write_project(proj)
            return {"rev": proj["rev"], "online": self._online_locked(pid)}
