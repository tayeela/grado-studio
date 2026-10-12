"""Хаб совместной работы ГРАДО 2 (режим GRADO2_HUB=1): аккаунты, проекты с ролями, ревизии разделов,
живые события (presence, комментарии), история версий.

Контракт — docs/specs/collab-contract.md. Модель — как у старого хаба студии (apps/studio/webhub.py):
сервер хранит проект целиком с номером ревизии и сериализует записи, клиент сливает правки сам.
Новое: ревизия у каждого раздела (sec_rev) — конфликт только если кто-то менял тот же раздел.

Хранение — файлы без БД, записи атомарные (tmp + os.replace) под одним RLock на экземпляр Hub:
    users.json, invites.json, sessions.json              (в sessions.json только sha256 токена)
    projects/<pid>/meta.json, project.grado2, comments.json, activity.json, history/<rev>-<ГГГГММДД-ЧЧММСС>-<login>.grado2.gz
    catalog.sqlite — превью общих проектов для каталога (catalog.py, server.py hub_get «preview»)
Живые данные (presence, подписчики SSE) — только в памяти, под отдельным замком _live:
порядок замков всегда lock -> _live -> Subscription._cond, назад никогда.

Только стандартная библиотека. CLI: python3 apps/grado2/hub.py adduser|passwd|invite|list.
"""

import calendar
import collections
import copy
import gzip
import hashlib
import hmac
import json
import math
import mmap
import os
import re
import secrets
import shutil
import sys
import threading
import time
from pathlib import Path

# ---------- параметры (константы модуля: тесты подменяют их) ----------
SCRYPT_N = 2 ** 14                 # стоимость scrypt; в тестах снижается
SESSION_TTL = 30 * 24 * 3600       # сессия живёт 30 дней с последнего обращения (скользящий срок)
GUEST_LOGIN = "guest"                # гостевая учётная запись (GRADO2_GUEST=1 на сервере): вход без пароля
SESSION_TOUCH = 600                # last_seen обновляется на диске не чаще раза в 10 минут
INVITE_TTL = 7 * 24 * 3600
LOGIN_FAILS = 5                    # неудач на один логин
IP_FAILS = 25                      # неудач с одного адреса
FAIL_WINDOW = 15 * 60
PASSWORD_MIN = 8
PASSWORD_MAX = 512
HISTORY_INTERVAL = 10 * 60         # не чаще одного снимка в 10 минут (кроме снимка перед возвратом версии)
HISTORY_KEEP = 60
ACTIVITY_KEEP = 300
COMMENT_MAX = 4000
COMMENTS_PER_PROJECT = 2000
REPLIES_PER_COMMENT = 200
MAX_SECTIONS = 4000
PRESENCE_TTL = 20
PRESENCE_MIN_INTERVAL = 0.5        # не чаще 2 рассылок в секунду от одного клиента
PRESENCE_MAX_ENTRIES = 300
SEL_MAX = 2000
QUEUE_MAX = 200
TICK = 0.5                         # шаг ожидания Subscription.get: на каждом шаге чистится presence
CACHE_PROJECTS = 3                 # сколько разобранных проектов держать в памяти
SSE_PER_USER = 8                   # открытых потоков событий на одного человека
SSE_TOTAL = 200                    # и на весь сервер: поток держит нить, без предела их можно исчерпать
PRESENCE_PER_USER = 8              # записей присутствия одного человека в проекте (вкладок); иначе один забьёт все 300
COMMENTS_BYTES = 8 * 2**20         # размер comments.json: счёт по числу комментариев не ограничивает ответы
MEMBERS_MAX = 200
PROJECTS_PER_USER = 100            # проектов, где человек владелец
INVITES_MAX = 500                  # действующих приглашений (не использованных и не просроченных)
SESSIONS_PER_USER = 20             # входов (устройств) на человека: старейший вытесняется
PROJECT_MAX_BYTES = 400 * 2**20    # файл проекта не больше тела запроса push (MAX_PROJECT_BODY сервера)
QUOTA_BYTES = 20 * 2**30           # вся папка хаба вместе с историей; сервер выставляет PROJECTS_CAP
QUOTA_CHECK_FROM = 2**20           # обход папки ради квоты — только для записей крупнее этого

PALETTE = ("#e4572e", "#17a398", "#3f7cac", "#f2a541", "#8e5ea2", "#2e933c", "#d6457a", "#6b705c")

LOGIN_RE = re.compile(r"[a-z0-9_.-]{3,32}")
PID_RE = re.compile(r"[0-9a-f]{16}")
SECTION_RE = re.compile(r"(meta|album|layer:[^\s]{1,200})")     # только fullmatch: «$» пропустил бы перевод строки
LAYER_KEY_RE = re.compile(r"[^\s]{1,200}")
CLIENT_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
HISTORY_RE = re.compile(r"(\d+)-(\d{8}-\d{6})-([a-z0-9_.-]+)\.grado2\.gz")
_BAD_KEYS = frozenset({"__proto__", "constructor", "prototype", "hasOwnProperty", "toString", "valueOf",   # клиент кладёт
                       "toLocaleString", "isPrototypeOf", "propertyIsEnumerable", "__defineGetter__",     # ключи слоёв в обычные
                       "__defineSetter__", "__lookupGetter__", "__lookupSetter__"})                       # объекты
ROLES = ("owner", "editor", "viewer")
TEAM_MEMBERS_MAX = 200
TEAMS_PER_USER = 50                # команд, в которых состоит один человек
TEAM_ROLES = ("owner", "member")
STARS_MAX = 500                    # избранных проектов на человека
LINK_USERS_MAX = 500               # людей, вошедших в проект по ссылке
LINK_ROLES = ("viewer", "editor")
JOIN_KEYS = ("j", "ji")              # свои ключи счётчика неудач: плохие ссылки не блокируют вход по паролю
TEAM_ACCESS = ("edit", "view", "none")     # что получает вся команда в проекте команды
ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}
LAYOUT = 2                         # раскладка разделов: 2 = альбом в своём разделе «album» (1 = внутри meta)
META_KEYS = ("name", "territory", "checked", "groups", "views", "graph", "imports", "current_order")


def _now():
    return time.time()


class HubError(Exception):
    """Ошибка API: код HTTP и сообщение пользователю."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class Conflict(HubError):
    """409: часть разделов успели изменить. payload = {"rev", "conflicts": {раздел: {"value", "rev"}}}."""

    def __init__(self, payload):
        super().__init__(409, "проект уже изменён другим участником")
        self.payload = payload


# ---------- разделы проекта ----------

def _norm_album(src):
    """Раздел album: объект {meta, sheets, ...}; не объект — пустой альбом."""
    return src if isinstance(src, dict) else {"meta": {}, "sheets": []}


def _layer_key_ok(key):
    return isinstance(key, str) and LAYER_KEY_RE.fullmatch(key) is not None and key not in _BAD_KEYS


def _norm_meta(src):
    """Раздел meta в нормальном виде: только известные поля, у каждого допустимый тип."""
    def lst(v):
        return v if isinstance(v, list) else []
    territory, graph = src.get("territory"), src.get("graph")
    return {
        "name": src["name"] if isinstance(src.get("name"), str) else "",
        "territory": territory if isinstance(territory, dict) else None,
        "checked": lst(src.get("checked")),
        "groups": lst(src.get("groups")),
        "views": lst(src.get("views")),
        "graph": graph if isinstance(graph, dict) else None,
        "imports": src["imports"] if isinstance(src.get("imports"), dict) else {},
        "current_order": [k for k in lst(src.get("current_order")) if _layer_key_ok(k)],
    }


_ALBUM_KEY = re.compile(rb'"album"\s*:\s*(?=\{)')


def album_summary(path):
    """(листов в альбоме, когда собран) по файлу проекта .grado2 — без разбора всего файла: альбом лежит в начале, до слоёв и данных,
    поэтому разбирается только значение ключа «album», окном, которое растёт, пока объект не поместится. Нет альбома — (None, None)."""
    try:
        with open(path, "rb") as fh:
            if os.fstat(fh.fileno()).st_size == 0:
                return None, None
            with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                dec = json.JSONDecoder()
                for k, m in enumerate(_ALBUM_KEY.finditer(mm)):
                    if k >= 4:
                        break
                    size = 1 << 18
                    while True:
                        end = min(len(mm), m.end() + size)
                        try:
                            alb = dec.raw_decode(mm[m.end():end].decode("utf-8", "replace"))[0]
                            break
                        except ValueError:
                            if end >= len(mm):
                                alb = None
                                break
                            size *= 4
                    if isinstance(alb, dict) and isinstance(alb.get("sheets"), list):
                        meta = alb.get("meta") if isinstance(alb.get("meta"), dict) else {}
                        at = meta.get("builtAt")
                        return len(alb["sheets"]), at if isinstance(at, str) else None
    except (OSError, ValueError, RecursionError):
        pass
    return None, None


def split_project(obj):
    """Файл .grado2 (объект) -> разделы {"meta": {...}, "layer:<key>": {"spec", "data"}}.
    Личное (view, current, dirty, file) отбрасывается. Слой без данных или без ключа пропускается."""
    if not isinstance(obj, dict):
        raise ValueError("проект должен быть объектом")
    layers = obj.get("layers") if isinstance(obj.get("layers"), list) else []
    data = obj.get("data") if isinstance(obj.get("data"), dict) else {}
    sections, order = {}, []
    for spec in layers:
        key = spec.get("key") if isinstance(spec, dict) else None
        if not _layer_key_ok(key) or f"layer:{key}" in sections or not isinstance(data.get(key), dict):
            continue
        order.append(key)
        sections[f"layer:{key}"] = {"spec": spec, "data": data[key]}
    meta = _norm_meta(obj)
    meta["current_order"] = order
    return {"meta": meta, "album": _norm_album(obj.get("album")), **sections}


def join_sections(sections, name=None):
    """Разделы -> обычный объект .grado2 (его открывает и локальный режим). Слои идут в порядке
    meta.current_order, остальные (которых в порядке нет) — по алфавиту в конце; пустой раздел слоя пропускается."""
    raw_meta = sections.get("meta") or {}
    # старая раскладка (до раздела album): альбом лежит в meta, отдельного раздела нет -> берём оттуда
    album = _norm_album(sections["album"] if "album" in sections else raw_meta.get("album"))
    meta = _norm_meta(raw_meta)
    layers = {n[6:]: s for n, s in sections.items()
              if n.startswith("layer:") and isinstance(s, dict) and isinstance(s.get("spec"), dict)
              and isinstance(s.get("data"), dict) and _layer_key_ok(n[6:])}
    order = []
    for key in meta["current_order"] + sorted(layers):
        if key in layers and key not in order:
            order.append(key)
    return {
        "format": "grado2", "version": 2, "app": "ГРАДО 2 (совместный проект)",
        "name": name if name else meta["name"],
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_now())), "dirty": False,
        "territory": meta["territory"], "imports": meta["imports"], "checked": meta["checked"],
        "groups": meta["groups"], "views": meta["views"], "album": album,
        "layers": [{**layers[k]["spec"], "key": k} for k in order],
        "data": {k: layers[k]["data"] for k in order},
        "graph": meta["graph"],
    }


def _check_sections(sections):
    """Проверка разделов из push: имена, типы; meta приводится к нормальному виду. Возвращает копию."""
    if not isinstance(sections, dict):
        raise HubError(400, "sections должен быть объектом")
    if len(sections) > MAX_SECTIONS:
        raise HubError(400, "слишком много разделов в одной записи")
    clean = {}
    for name, value in sections.items():
        if not isinstance(name, str) or not SECTION_RE.fullmatch(name) or name[6:] in _BAD_KEYS:
            raise HubError(400, "некорректное имя раздела")
        if name == "meta":
            if not isinstance(value, dict):
                raise HubError(400, "раздел meta нельзя удалить и он должен быть объектом")
            if "album" in value:      # старый клиент: альбом внутри meta; принять нельзя, он затёр бы раздел album
                raise HubError(426, "версия страницы устарела: обновите страницу (Ctrl+Shift+R)")
            clean[name] = _norm_meta(value)
        elif name == "album":
            if not isinstance(value, dict):
                raise HubError(400, "раздел album нельзя удалить и он должен быть объектом")
            clean[name] = _norm_album(value)
        elif value is None:
            clean[name] = None
        elif (isinstance(value, dict) and isinstance(value.get("spec"), dict) and isinstance(value.get("data"), dict)):
            clean[name] = {"spec": {**value["spec"], "key": name[6:]}, "data": value["data"]}
        else:
            raise HubError(400, f"раздел {name[:40]}: ожидался объект {{spec, data}} или null")
    return clean


# ---------- проверки входных значений ----------

def _clean_name(value, default, limit=60):
    if not isinstance(value, str):
        value = ""
    return (" ".join(value.split()) or default)[:limit]


def _clean_login(value):
    login = value.strip().lower() if isinstance(value, str) else ""
    if not LOGIN_RE.fullmatch(login):
        raise HubError(400, "логин: 3-32 символа, латинские буквы, цифры и . _ -")
    return login


def _check_password(value):
    if not isinstance(value, str) or len(value) < PASSWORD_MIN:
        raise HubError(400, f"пароль слишком короткий (минимум {PASSWORD_MIN} символов)")
    if len(value) > PASSWORD_MAX:
        raise HubError(400, "пароль слишком длинный")


def _clean_client(value):
    if not isinstance(value, str) or not CLIENT_RE.fullmatch(value):
        raise HubError(400, "некорректный идентификатор клиента")
    return value


def _check_pid(pid):
    if not isinstance(pid, str) or not PID_RE.fullmatch(pid):
        raise HubError(400, "некорректный id проекта")
    return pid


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _clean_text(text):
    if not isinstance(text, str) or not text.strip():
        raise HubError(400, "текст не может быть пустым")
    if len(text) > COMMENT_MAX:
        raise HubError(400, f"текст длиннее {COMMENT_MAX} символов")
    return text.strip()


def _clean_anchor(anchor):
    if isinstance(anchor, dict) and set(anchor) == {"lonlat"}:
        ll = anchor["lonlat"]
        if (isinstance(ll, (list, tuple)) and len(ll) == 2 and all(_is_num(v) for v in ll)
                and abs(ll[0]) <= 720 and abs(ll[1]) <= 90):
            return {"lonlat": [float(ll[0]), float(ll[1])]}
    elif isinstance(anchor, dict) and set(anchor) == {"layer", "uid"}:
        layer, uid = anchor["layer"], anchor["uid"]
        if _layer_key_ok(layer) and isinstance(uid, str) and re.fullmatch(r"\S{1,64}", uid):
            return {"layer": layer, "uid": uid}
    raise HubError(400, "некорректная привязка комментария")


def _hash_password(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=8, p=1, dklen=32).hex()


def _color(login):
    return PALETTE[int(hashlib.sha256(login.encode("utf-8")).hexdigest()[:8], 16) % len(PALETTE)]


_DUMMY_SALT = bytes(16)


# ---------- живые события ----------

class Subscription:
    """Очередь событий одной вкладки. get() блокируется до события, закрытия или таймаута."""

    def __init__(self, hub, pid, login):
        self.hub, self.pid, self.login = hub, pid, login
        self.closed = False
        self._q = collections.deque()
        self._cond = threading.Condition()

    def _put(self, ev):
        with self._cond:
            if self.closed:
                return
            kind = ev["type"]
            if kind in ("presence", "comments", "members"):      # важно только последнее
                self._q = collections.deque(e for e in self._q if e["type"] != kind)
            elif len(self._q) >= QUEUE_MAX:
                self._coalesce()
            self._q.append(ev)
            while len(self._q) > QUEUE_MAX:
                self._q.popleft()
            self._cond.notify_all()

    def _coalesce(self):
        """Очередь переполнена: все rev-события сливаются в одно (объединение разделов, последняя ревизия)."""
        revs = [e for e in self._q if e["type"] == "rev"]
        if len(revs) < 2:
            return
        last = revs[-1]
        merged = {"type": "rev", "rev": last["rev"], "by": last["by"],
                  "sections": sorted({s for e in revs for s in e["sections"]}),
                  "client": last["client"] if all(e["client"] == last["client"] for e in revs) else None}
        self._q = collections.deque(merged if e is last else e for e in self._q
                                    if e["type"] != "rev" or e is last)

    def get(self, timeout):
        """Следующее событие (dict) или None: таймаут либо подписка закрыта и очередь пуста."""
        end = time.monotonic() + max(0.0, float(timeout))
        while True:
            self.hub._tick(self.pid)
            with self._cond:
                if self._q:
                    return self._q.popleft()
                remaining = end - time.monotonic()
                if self.closed or remaining <= 0:
                    return None
                self._cond.wait(min(remaining, TICK))

    def _shutdown(self):
        """Закрытие со стороны хаба: уже лежащие в очереди события (например deleted) ещё можно забрать."""
        with self._cond:
            self.closed = True
            self._cond.notify_all()

    def close(self):
        self._shutdown()
        with self._cond:
            self._q.clear()
        self.hub._unsubscribe(self)


# ---------- хаб ----------

class Hub:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()
        self._live = threading.RLock()
        self._auth = threading.Lock()
        self._mkdir(self.root)
        self._mkdir(self.root / "projects")
        for d in (self.root / "projects").glob(".del-*"):         # недоудалённое при сбое прошлого запуска
            shutil.rmtree(d, ignore_errors=True)
        self._stamps = {}                                # имя файла -> (mtime_ns, размер) на момент нашего чтения/записи
        self.users = self._load("users.json")
        self.invites = self._load("invites.json")
        self.sessions = self._load("sessions.json")
        self.teams = self._load("teams.json")
        self.stars = self._load("stars.json")
        self._pid_team = None                            # pid -> tid|None; строится одним обходом при первом обращении
        if self._prune_sessions():
            self._save("sessions.json", self.sessions)
        self._fails = {}                                 # ("l", логин) | ("i", ip) -> [время неудач]
        self._presence = {}                              # pid -> {(login, client): запись}
        self._subs = {}                                  # pid -> [Subscription]
        self._album_sum = {}                              # pid -> (rev, (листов, собран)) для списка проектов
        self._cache = collections.OrderedDict()          # pid -> (rev, разделы)

    # ----- файлы -----

    @staticmethod
    def _mkdir(path):
        Path(path).mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            Path(path).chmod(0o700)
        except OSError:
            pass

    def _stamp(self, name):
        try:
            st = os.stat(self.root / name)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _load(self, name):
        self._stamps[name] = self._stamp(name)
        try:
            with open(self.root / name, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            raise HubError(500, f"файл хаба {name} повреждён или недоступен") from None
        if not isinstance(data, dict):
            raise HubError(500, f"файл хаба {name} повреждён")
        return data

    def _sync(self):
        """Под self.lock. users/invites/sessions держатся в памяти, а `hub.py adduser|passwd|invite` — отдельный процесс,
        пишущий те же файлы. Без пересчитывания с диска сервер не видел бы нового пользователя, не гасил бы сессии после
        `passwd`, а первая его запись затёрла бы правку из командной строки."""
        for name, attr in (("users.json", "users"), ("invites.json", "invites"), ("sessions.json", "sessions"),
                           ("teams.json", "teams"), ("stars.json", "stars")):
            if self._stamp(name) != self._stamps.get(name):
                try:
                    setattr(self, attr, self._load(name))
                except HubError:
                    pass                                   # файл мог быть виден на середине чужой записи: прежние данные целее

    @staticmethod
    def _stage(path, data):
        """Записать данные во временный файл рядом и вернуть его путь; заменить им файл — os.replace."""
        tmp = path.with_name(path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        return tmp

    def _write(self, path, data):
        os.replace(self._stage(path, data), path)

    @staticmethod
    def _dump(obj):
        try:
            return json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        except (ValueError, TypeError, RecursionError):
            raise HubError(400, "в данных недопустимые значения (NaN, бесконечность или слишком глубокая вложенность)") from None

    def _save(self, name, data):
        self._write(self.root / name, json.dumps(data, ensure_ascii=False, allow_nan=False, indent=1).encode("utf-8"))
        self._stamps[name] = self._stamp(name)

    # ----- пользователи -----

    def _public(self, login):
        u = self.users[login]
        out = {"login": login, "name": u.get("name") or login, "admin": bool(u.get("admin"))}
        if u.get("guest"):
            out["guest"] = True
        return out

    def _actor(self, user):
        """Свежая запись пользователя по словарю от session_user (не верим устаревшему admin)."""
        self._sync()
        login = user.get("login") if isinstance(user, dict) else None
        u = self.users.get(login) if isinstance(login, str) else None
        if not u or u.get("disabled"):
            raise HubError(401, "нужно войти")
        return login, u

    def _admin(self, user):
        login, u = self._actor(user)
        if not u.get("admin"):
            raise HubError(403, "только для администратора")
        return login

    def _add_user(self, login, password, name, admin):
        salt = os.urandom(16)
        pw = _hash_password(password, salt)
        with self.lock:
            self._sync()
            if login in self.users:
                raise HubError(409, "такой логин уже занят")
            self.users[login] = {"pw": pw, "salt": salt.hex(), "admin": bool(admin), "name": name,
                                 "created": _now(), "disabled": False}
            self._save("users.json", self.users)
            return self._public(login)

    def create_user(self, login, password, name="", admin=False):
        login = _clean_login(login)
        _check_password(password)
        return self._add_user(login, password, _clean_name(name, login), admin)

    def _drop_sessions(self, login, keep=None):
        """Убрать все входы пользователя, кроме одного (keep — sha256 токена, с которого сменили пароль)."""
        stale = [k for k, s in self.sessions.items() if s.get("login") == login and k != keep]
        for k in stale:
            del self.sessions[k]
        if stale:
            self._save("sessions.json", self.sessions)

    def set_password(self, login, new, keep_sessions=False, keep_token=None):
        """Задать пароль (админ/CLI). По умолчанию все входы пользователя сбрасываются; keep_token — единственный вход,
        который остаётся (тот, с которого человек сменил пароль сам)."""
        _check_password(new)
        salt = os.urandom(16)
        pw = _hash_password(new, salt)
        with self.lock:
            self._sync()
            u = self.users.get(login)
            if not u:
                raise HubError(404, "пользователь не найден")
            u["pw"], u["salt"] = pw, salt.hex()
            self._save("users.json", self.users)
            if not keep_sessions:
                keep = hashlib.sha256(keep_token.encode()).hexdigest() if isinstance(keep_token, str) and keep_token else None
                self._drop_sessions(login, keep)

    def change_password(self, user, old, new, keep_token=None):
        """Смена своего пароля. Все остальные входы гасятся (украденная сессия не переживает смену пароля);
        keep_token — токен текущей сессии, она остаётся. Без него гасятся все."""
        with self.lock:
            login, u = self._actor(user)
            u = dict(u)
        _check_password(new)
        self._throttle_check(login, None, reserve=True)   # попытка занята заранее: пачка параллельных запросов лимит не обходит
        if not self._password_ok(u, old):
            raise HubError(401, "неверный пароль")
        self._forgive(login)
        self.set_password(login, new, keep_token=keep_token)

    @staticmethod
    def _password_ok(u, password):
        """Проверка пароля; у неизвестного логина (u=None) тоже считается scrypt — по времени аккаунты не различить."""
        try:
            salt = bytes.fromhex(u["salt"]) if u else _DUMMY_SALT
            expected = u["pw"] if u else "-"
        except (KeyError, TypeError, ValueError):
            u, salt, expected = None, _DUMMY_SALT, "-"
        if not isinstance(password, str) or len(password) > PASSWORD_MAX:
            password = ""
        candidate = _hash_password(password, salt)
        return bool(u) and hmac.compare_digest(candidate.encode(), str(expected).encode())   # байты: не-ASCII в файле не даёт TypeError

    # ----- ограничение попыток входа -----

    def _gc_fails(self, now):
        if len(self._fails) > 4096:                         # чтобы перебор логинов не раздувал память
            for key in [k for k, v in self._fails.items() if not v or v[-1] <= now - FAIL_WINDOW]:
                del self._fails[key]
            if len(self._fails) > 4096:                     # все записи свежие: оставляем самые новые, остальных не жалко
                for key in sorted(self._fails, key=lambda k: self._fails[k][-1])[:len(self._fails) - 4096]:
                    del self._fails[key]

    def _throttle_check(self, login, ip, reserve=False, pre=("l", "i"), msg="слишком много попыток входа; повторите позже"):
        """429, если предел неудач исчерпан. reserve=True: попытка записывается сразу, до проверки пароля (scrypt занимает
        десятки миллисекунд, и без этого пачка параллельных запросов видела бы пустой счётчик и обходила лимит);
        успешный вход потом снимает отметку через _refund."""
        now = _now()
        keys = [(k, lim) for k, lim in (((pre[0], login), LOGIN_FAILS), ((pre[1], ip), IP_FAILS)) if k[1] is not None]
        with self._auth:
            for key, limit in keys:
                stamps = [t for t in self._fails.get(key, ()) if t > now - FAIL_WINDOW]
                if stamps:
                    self._fails[key] = stamps
                else:
                    self._fails.pop(key, None)
                if len(stamps) >= limit:
                    raise HubError(429, msg)
            if reserve:
                for key, _ in keys:
                    self._fails.setdefault(key, []).append(now)
                self._gc_fails(now)

    def _fail(self, login, ip, pre=("l", "i")):
        now = _now()
        with self._auth:
            for key in ((pre[0], login), (pre[1], ip)):
                if key[1] is not None:
                    self._fails.setdefault(key, []).append(now)
            self._gc_fails(now)

    def _refund(self, ip):
        """Снять занятую попытку адреса (вход удался или упёрся не в пароль)."""
        if ip is None:
            return
        with self._auth:
            stamps = self._fails.get(("i", ip))
            if stamps:
                stamps.pop()
                if not stamps:
                    del self._fails[("i", ip)]

    def _forgive(self, login):
        with self._auth:
            self._fails.pop(("l", login), None)

    # ----- сессии -----

    def _prune_sessions(self):
        deadline = _now() - SESSION_TTL
        stale = [k for k, s in self.sessions.items()
                 if not isinstance(s, dict) or s.get("login") not in self.users
                 or not _is_num(s.get("last_seen")) or s["last_seen"] < deadline]
        for k in stale:
            del self.sessions[k]
        return bool(stale)

    def _new_session(self, login, ua):
        token = secrets.token_urlsafe(32)
        now = _now()
        self._prune_sessions()
        mine = sorted((k for k, s in self.sessions.items() if s.get("login") == login), key=lambda k: self.sessions[k]["last_seen"])
        for k in mine[:max(0, len(mine) - SESSIONS_PER_USER + 1)]:      # старейшие входы вытесняются: файл не растёт без предела
            del self.sessions[k]
        self.sessions[hashlib.sha256(token.encode()).hexdigest()] = {
            "login": login, "created": now, "last_seen": now, "ua": str(ua or "")[:200]}
        self._save("sessions.json", self.sessions)
        return token

    def login(self, login, password, ip, ua=""):
        lk = login.strip().lower()[:64] if isinstance(login, str) else ""
        ip = str(ip or "?")[:64]
        self._throttle_check(lk, ip, reserve=True)        # неудача уже записана: пачка параллельных запросов лимит не обходит
        with self.lock:
            self._sync()
            u = dict(self.users[lk]) if lk in self.users else None
        ok = self._password_ok(u, password)
        if not ok:
            raise HubError(401, "неверный логин или пароль")
        self._forgive(lk)
        self._refund(ip)                                  # верный пароль не считается неудачей адреса
        if u.get("disabled"):
            raise HubError(403, "учётная запись отключена")
        with self.lock:
            self._sync()
            if self.users.get(lk, {}).get("disabled"):
                raise HubError(403, "учётная запись отключена")
            return self._new_session(lk, ua), self._public(lk)

    def guest_session(self, ua=""):
        """Гостевой вход (сервер с GRADO2_GUEST=1, владелец 06.10.2026): учётная запись GUEST_LOGIN без известного пароля,
        не администратор — видит свои проекты и те, куда её позвали в «Доступе». Логин, занятый обычным человеком,
        гостю не отдаётся. Отключённый в «Пользователях» гость не входит."""
        salt = os.urandom(16)
        pw = _hash_password(secrets.token_urlsafe(32), salt)      # пароль никто не знает: войти по паролю нельзя
        with self.lock:
            self._sync()
            u = self.users.get(GUEST_LOGIN)
            if u is None:
                self.users[GUEST_LOGIN] = {"pw": pw, "salt": salt.hex(), "admin": False, "name": "Гость",
                                           "created": _now(), "disabled": False, "guest": True}
                self._save("users.json", self.users)
            elif not u.get("guest"):
                raise HubError(409, "логин guest занят обычной учётной записью")
            elif u.get("disabled"):
                raise HubError(403, "гостевой вход отключён администратором")
            return self._new_session(GUEST_LOGIN, ua), self._public(GUEST_LOGIN)

    def register(self, invite, login, name, password, ip, ua=""):
        ip = str(ip or "?")[:64]
        self._throttle_check(None, ip)
        login = _clean_login(login)
        _check_password(password)
        name = _clean_name(name, login)

        def check_invite():
            inv = self.invites.get(invite) if isinstance(invite, str) else None
            if not isinstance(inv, dict) or inv.get("used_by") or inv.get("expires", 0) < _now():
                self._fail(None, ip)                      # подбор инвайтов считается как неудачный вход
                raise HubError(403, "приглашение не найдено, просрочено или уже использовано")
            if login in self.users:
                raise HubError(409, "такой логин уже занят")
            return inv

        with self.lock:
            self._sync()
            check_invite()
        salt = os.urandom(16)
        pw = _hash_password(password, salt)
        with self.lock:
            self._sync()
            inv = check_invite()                          # пока считался scrypt, код мог уйти другому
            self.users[login] = {"pw": pw, "salt": salt.hex(), "admin": False, "name": name,
                                 "created": _now(), "disabled": False}
            inv["used_by"], inv["used_at"] = login, _now()
            self._save("users.json", self.users)
            self._save("invites.json", self.invites)
            return self._new_session(login, ua), self._public(login)

    def session_user(self, token):
        if not isinstance(token, str) or not 16 <= len(token) <= 200:
            return None
        key = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            self._sync()
            s = self.sessions.get(key)
            if not s:
                return None
            now = _now()
            if now - s["last_seen"] > SESSION_TTL:
                del self.sessions[key]
                self._save("sessions.json", self.sessions)
                return None
            u = self.users.get(s["login"])
            if not u or u.get("disabled"):
                return None
            if now - s["last_seen"] > SESSION_TOUCH:
                s["last_seen"] = now
                self._save("sessions.json", self.sessions)
            return self._public(s["login"])

    def logout(self, token):
        if not isinstance(token, str):
            return
        with self.lock:
            self._sync()
            if self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None) is not None:
                self._save("sessions.json", self.sessions)

    # ----- приглашения и управление пользователями (админ) -----

    def _new_invite(self, by):
        self._sync()
        code = secrets.token_urlsafe(9)
        now = _now()
        for c in [c for c, i in self.invites.items()                  # старые использованные и просроченные уходят из файла
                  if not isinstance(i, dict) or i.get("expires", 0) < now - 30 * 24 * 3600]:
            del self.invites[c]
        active = sum(1 for i in self.invites.values() if not i.get("used_by") and i.get("expires", 0) >= now)
        if active >= INVITES_MAX:
            raise HubError(400, "слишком много действующих приглашений")
        self.invites[code] = {"created": now, "by": by, "used_by": None, "used_at": None, "expires": now + INVITE_TTL}
        self._save("invites.json", self.invites)
        return code

    def create_invite(self, user):
        with self.lock:
            return self._new_invite(self._admin(user))

    def list_invites(self, user):
        with self.lock:
            self._admin(user)
            return sorted(({"code": c, **i} for c, i in self.invites.items()), key=lambda i: -i["created"])

    def _user_row(self, login):
        u = self.users[login]
        return {**self._public(login), "disabled": bool(u.get("disabled")), "created": u.get("created")}

    def list_users(self, user):
        with self.lock:
            self._admin(user)
            return [self._user_row(login) for login in sorted(self.users)]

    def update_user(self, user, login, **fields):
        unknown = set(fields) - {"disabled", "admin", "name"}
        if unknown:
            raise HubError(400, "нельзя менять поля: " + ", ".join(sorted(unknown)))
        with self.lock:
            me = self._admin(user)
            u = self.users.get(login)
            if not u:
                raise HubError(404, "пользователь не найден")
            for key in ("disabled", "admin"):
                if key in fields and not isinstance(fields[key], bool):
                    raise HubError(400, f"{key} должен быть true или false")
            new_admin = fields.get("admin", u.get("admin"))
            new_disabled = fields.get("disabled", u.get("disabled"))
            if login == me and new_disabled:
                raise HubError(400, "нельзя отключить самого себя")
            others = [k for k, v in self.users.items() if k != login and v.get("admin") and not v.get("disabled")]
            if (u.get("admin") and not u.get("disabled")) and (not new_admin or new_disabled) and not others:
                raise HubError(400, "нельзя лишить прав последнего администратора")
            if "name" in fields:
                u["name"] = _clean_name(fields["name"], login)
            demoted = bool(u.get("admin")) and not new_admin
            u["admin"], u["disabled"] = bool(new_admin), bool(new_disabled)
            self._save("users.json", self.users)
            if u["disabled"]:
                self._drop_sessions(login)
        if u["disabled"]:
            self._close_user_everywhere(login)
        elif demoted:
            self._recheck_subs(login)                      # поток админа в чужом проекте закрывается сразу, а не при переподключении
        with self.lock:
            return self._user_row(login)

    # ----- проекты: служебное -----

    def _pdir(self, pid):
        return self.root / "projects" / _check_pid(pid)

    def _meta(self, pid):
        try:
            with open(self._pdir(pid) / "meta.json", encoding="utf-8") as fh:
                meta = json.load(fh)
        except FileNotFoundError:
            raise HubError(404, "проект не найден") from None
        except (OSError, ValueError):
            raise HubError(500, "файл проекта повреждён") from None
        if not isinstance(meta, dict) or meta.get("id") != pid:
            raise HubError(500, "файл проекта повреждён")
        if meta.get("layout") != LAYOUT:                  # проект до раздела album: альбом «изменён» на текущей ревизии (на диск попадёт со следующей записью)
            meta["layout"] = LAYOUT
            if isinstance(meta.get("sec_rev"), dict):
                meta["sec_rev"].setdefault("album", meta.get("rev", 0))
        return meta

    def _save_meta(self, pid, meta):
        self._write(self._pdir(pid) / "meta.json", self._dump(meta))
        if self._pid_team is not None:                     # карта проект -> команда следует за записью meta
            tid = meta.get("team")
            self._pid_team[pid] = tid if isinstance(tid, str) else None

    def _team_counts(self):
        """Сколько проектов в каждой команде. Под self.lock. Карта pid -> команда строится одним обходом meta.json и дальше
        ведётся в _save_meta и при удалении; если набор каталогов проектов разошёлся с картой (кто-то менял папку снаружи),
        карта строится заново."""
        pids = {d.name for d in (self.root / "projects").iterdir() if PID_RE.fullmatch(d.name)}
        if self._pid_team is None or set(self._pid_team) != pids:
            fresh = {}
            for pid in pids:
                try:
                    tid = self._meta(pid).get("team")
                except HubError:
                    tid = None
                fresh[pid] = tid if isinstance(tid, str) else None
            self._pid_team = fresh
        counts = {}
        for tid in self._pid_team.values():
            if tid is not None:
                counts[tid] = counts.get(tid, 0) + 1
        return counts

    def _check_size(self, data):
        """Файл проекта не больше PROJECT_MAX_BYTES, а вся папка хаба (с историей) — не больше QUOTA_BYTES.
        Обход папки — только для крупных записей: мелкие правки квоту не съедят."""
        if len(data) > PROJECT_MAX_BYTES:
            raise HubError(413, f"проект больше {PROJECT_MAX_BYTES // 2**20} МБ")
        if len(data) < QUOTA_CHECK_FROM:
            return
        used = 0
        for base, _, names in os.walk(self.root):
            for n in names:
                try:
                    used += os.stat(os.path.join(base, n)).st_size
                except OSError:
                    pass
        if used + len(data) > QUOTA_BYTES:
            raise HubError(507, f"хранилище совместных проектов заполнено (больше {QUOTA_BYTES // 2**30} ГБ): удалите старые проекты")

    def _team_role(self, login, meta):
        """Роль, которую человеку даёт команда проекта (None — проект личный, команды нет или доступа нет). Под self.lock."""
        tid = meta.get("team")
        team = self.teams.get(tid) if isinstance(tid, str) else None
        if not isinstance(team, dict) or (self.users.get(login) or {}).get("disabled"):
            return None
        r = (team.get("members") or {}).get(login)
        if r == "owner":
            return "owner"
        if r == "member":
            return {"edit": "editor", "view": "viewer"}.get(meta.get("team_access") or "edit")
        return None

    @staticmethod
    def _link_role(login, meta):
        """Роль по ссылке: ссылка включена и человек по ней уже входил (owner по ссылке выдать нельзя)."""
        link = meta.get("link")
        users = meta.get("link_users")
        if isinstance(link, dict) and link.get("role") in LINK_ROLES and isinstance(users, list) and login in users:
            return link["role"]
        return None

    def _role(self, u, login, meta):
        """Единая точка решения о доступе: сильнейшая из личной роли, роли от команды проекта и роли по ссылке."""
        if not u or u.get("disabled"):
            return None
        if u.get("admin"):
            return "admin"
        roles = [r for r in (meta["members"].get(login), self._team_role(login, meta),
                                  self._link_role(login, meta)) if r in ROLE_RANK]
        return max(roles, key=ROLE_RANK.__getitem__) if roles else None

    def role_of(self, user, pid):
        try:
            with self.lock:
                login, u = self._actor(user)
                return self._role(u, login, self._meta(pid))
        except HubError:
            return None

    def _require(self, user, pid, need):
        """need: read | edit | owner. Возвращает (login, meta, role). Комментировать может любой участник."""
        login, u = self._actor(user)
        meta = self._meta(pid)
        role = self._role(u, login, meta)
        if role is None:
            raise HubError(403, "нет доступа к проекту")
        if need == "edit" and role == "viewer":
            raise HubError(403, "только просмотр: попросите владельца дать права на правку")
        if need == "owner" and role not in ("owner", "admin"):
            raise HubError(403, "это может сделать только владелец проекта")
        return login, meta, role

    def _members_list(self, meta):
        return [{"login": m, "name": (self.users.get(m) or {}).get("name") or m, "role": r}
                for m, r in sorted(meta["members"].items())]

    def _sections(self, pid, rev):
        """Разделы проекта: из кэша в памяти (ключ — ревизия) или разбором project.grado2."""
        hit = self._cache.get(pid)
        if hit and hit[0] == rev:
            self._cache.move_to_end(pid)
            return hit[1]
        try:
            with open(self._pdir(pid) / "project.grado2", encoding="utf-8") as fh:
                sections = split_project(json.load(fh))
        except (OSError, ValueError, RecursionError):
            raise HubError(500, "файл проекта повреждён") from None
        self._cache_put(pid, rev, sections)
        return sections

    def _cache_put(self, pid, rev, sections):
        self._cache[pid] = (rev, sections)
        self._cache.move_to_end(pid)
        while len(self._cache) > CACHE_PROJECTS:
            self._cache.popitem(last=False)

    def _activity_add(self, pid, login, action, detail=""):
        path = self._pdir(pid) / "activity.json"
        try:
            with open(path, encoding="utf-8") as fh:
                items = json.load(fh)
            if not isinstance(items, list):
                items = []
        except (OSError, ValueError):
            items = []
        items.append({"t": int(_now()), "login": login, "action": action, "detail": str(detail)[:200]})
        self._write(path, self._dump(items[-ACTIVITY_KEEP:]))

    # ----- проекты -----

    def list_projects(self, user):
        out = []
        with self.lock:
            login, u = self._actor(user)
            starred = self._stars_of(login)
            for d in sorted((self.root / "projects").iterdir()):
                if not PID_RE.fullmatch(d.name):
                    continue
                try:
                    meta = self._meta(d.name)
                except HubError:
                    continue
                role = self._role(u, login, meta)
                if role is None:
                    continue
                tid = meta.get("team")
                team = self.teams.get(tid) if isinstance(tid, str) else None
                alb_n, alb_at = self._album_info(d.name, meta["rev"])
                out.append({"id": meta["id"], "album_n": alb_n, "album_at": alb_at, "name": meta["name"], "owner": meta["owner"], "role": role,
                            "rev": meta["rev"], "updated": meta["updated"], "updated_by": meta["updated_by"],
                            "members": self._members_list(meta), "online": self._online_count(meta["id"]),
                            "team": tid if team else None, "team_name": team.get("name") if team else None,
                            "team_access": meta.get("team_access") or "edit", "star": meta["id"] in starred,
                            "link_role": ((meta.get("link") or {}).get("role") if isinstance(meta.get("link"), dict) else None)
                            if role in ("owner", "admin") else None})
        out.sort(key=lambda p: -p["updated"])
        return out

    def _album_info(self, pid, rev):
        """Листов в альбоме и когда собран — для списка проектов; по ревизии запоминается."""
        hit = self._album_sum.get(pid)
        if hit and hit[0] == rev:
            return hit[1]
        res = album_summary(self._pdir(pid) / "project.grado2")
        self._album_sum[pid] = (rev, res)
        return res

    def create_project(self, user, name, project=None, team=None, team_access="edit"):
        name = _clean_name(name, "Новый проект")
        if project is None:
            sections = {"meta": _norm_meta({}), "album": _norm_album(None)}
        else:
            if not isinstance(project, dict) or project.get("format") != "grado2":
                raise HubError(400, "это не файл проекта ГРАДО 2")
            if not isinstance(project.get("version", 1), int) or project.get("version", 1) > 2:
                raise HubError(400, "файл сохранён более новой версией ГРАДО 2")
            sections = split_project(project)
        return self._make_project(user, name, sections, team, team_access, "create", name)

    def _make_project(self, user, name, sections, team, team_access, action, detail):
        """Общая часть создания и копирования: проверки, квота, каталог проекта, meta последней. sections — уже
        разобранные разделы (кэш не меняется: join_sections их только читает)."""
        team_access = team_access or "edit"
        if team_access not in TEAM_ACCESS:
            raise HubError(400, "доступ команды: edit, view или none")
        if len(sections) > MAX_SECTIONS:
            raise HubError(400, "в проекте слишком много слоёв")
        with self.lock:
            login, u = self._actor(user)
            if team is not None:
                self._team_member_or_admin(u, login, self._team(team))
            obj = join_sections(sections, name)
            data = self._dump(obj)
            self._check_size(data)
            owned = 0
            for d0 in (self.root / "projects").iterdir():
                try:
                    owned += PID_RE.fullmatch(d0.name) is not None and self._meta(d0.name).get("owner") == login
                except HubError:
                    pass
            if owned >= PROJECTS_PER_USER:
                raise HubError(400, f"у вас уже {PROJECTS_PER_USER} проектов: удалите ненужные")
            while True:
                pid = secrets.token_hex(8)
                if not (self.root / "projects" / pid).exists():
                    break
            d = self.root / "projects" / pid
            self._mkdir(d)
            self._mkdir(d / "history")
            now = _now()
            norm = split_project(obj)
            meta = {"id": pid, "name": name, "owner": login, "members": {login: "owner"}, "rev": 1,
                    "sec_rev": {n: 1 for n in norm}, "created": now, "updated": now, "updated_by": login,
                    "snap_t": 0, "rev_c": 0, "layout": LAYOUT, "team": team, "team_access": team_access if team else "edit"}
            try:
                self._write(d / "project.grado2", data)
                self._save_meta(pid, meta)                # meta последней: без неё каталог не считается проектом
            except BaseException:
                shutil.rmtree(d, ignore_errors=True)       # не оставляем недописанный проект (и его занятое место)
                raise
            self._cache_put(pid, 1, norm)
            self._activity_add(pid, login, action, detail)
        return {"id": pid, "rev": 1}

    def copy_project(self, user, pid, name=None, team=None, team_access=None):
        """Копия проекта: текущее содержимое файла, владелец — копирующий. Комментарии, история, участники, ссылка и
        избранное не переносятся. Правила команды и квота — как при создании."""
        with self.lock:
            login, meta, role = self._require(user, pid, "read")
            if name is None:
                name = _clean_name(_clean_name(meta["name"], "Проект", 52) + " — копия", "Копия")
            else:
                name = _clean_name(name, _clean_name(_clean_name(meta["name"], "Проект", 52) + " — копия", "Копия"))
            sections = self._sections(pid, meta["rev"])
            return self._make_project(user, name, sections, team, team_access, "copy", meta["name"])

    def get_project(self, user, pid):
        with self.lock:
            login, meta, role = self._require(user, pid, "read")
            return {"id": pid, "name": meta["name"], "role": role, "rev": meta["rev"],
                    "sec_rev": dict(meta["sec_rev"]), "sections": dict(self._sections(pid, meta["rev"]))}

    def get_sections(self, user, pid, names):
        if not isinstance(names, (list, tuple)) or len(names) > MAX_SECTIONS:
            raise HubError(400, "names должен быть списком")
        for n in names:
            if not isinstance(n, str) or not SECTION_RE.fullmatch(n):
                raise HubError(400, "некорректное имя раздела")
        with self.lock:
            login, meta, role = self._require(user, pid, "read")
            cur = self._sections(pid, meta["rev"])
            return {"rev": meta["rev"], "sec_rev": dict(meta["sec_rev"]),
                    "sections": {n: cur.get(n) for n in names}}    # нет раздела = удалён (None)

    def push(self, user, pid, base_rev, sections, client):
        if not isinstance(base_rev, int) or isinstance(base_rev, bool) or base_rev < 0:
            raise HubError(400, "base_rev должен быть неотрицательным целым числом")
        client = _clean_client(client)
        clean = _check_sections(sections)
        with self.lock:
            login, meta, role = self._require(user, pid, "edit")
            if base_rev > meta["rev"]:
                raise HubError(400, "base_rev больше текущей ревизии проекта")
            if not clean:
                return {"rev": meta["rev"]}
            stale = {n: meta["sec_rev"].get(n, 0) for n in clean if meta["sec_rev"].get(n, 0) > base_rev}
            if stale:
                cur = self._sections(pid, meta["rev"])
                raise Conflict({"rev": meta["rev"],
                                "conflicts": {n: {"value": cur.get(n), "rev": r} for n, r in stale.items()}})
            return self._commit(pid, meta, clean, login, client, "push",
                                "разделы: " + ", ".join(sorted(clean)))

    def _commit(self, pid, meta, changes, login, client, action, detail, force_snap=False):
        """Единая точка записи (push, возврат версии, переименование). Под self.lock.
        Всё готовится в памяти и во временных файлах; на диск попадает только целиком."""
        rev = meta["rev"] + 1
        old = self._sections(pid, meta["rev"])
        new = dict(old)
        for n, v in changes.items():
            if v is None:
                new.pop(n, None)
            else:
                new[n] = v
        obj = join_sections(new, meta["name"])
        data = self._dump(obj)
        self._check_size(data)                            # до снимка и до любой записи
        norm = split_project(obj)                         # нормальный вид: порядок слоёв, типы meta
        changed = set(changes)
        if "meta" not in changed and norm["meta"] != old.get("meta"):
            changed.add("meta")                            # порядок слоёв изменился сам (слой добавили/убрали)
        now = _now()
        new_meta = dict(meta, rev=rev, updated=now, updated_by=login,
                        sec_rev={**meta["sec_rev"], **{n: rev for n in changed}})
        d = self._pdir(pid)
        if force_snap or now - meta.get("snap_t", 0) >= HISTORY_INTERVAL:
            self._snapshot(pid, meta)
            new_meta["snap_t"] = now
        tmp_file = self._stage(d / "project.grado2", data)
        tmp_meta = self._stage(d / "meta.json", self._dump(new_meta))
        os.replace(tmp_file, d / "project.grado2")
        os.replace(tmp_meta, d / "meta.json")
        self._cache_put(pid, rev, norm)
        self._activity_add(pid, login, action, detail)
        with self._live:
            self._publish(pid, {"type": "rev", "rev": rev, "sections": sorted(changed), "by": login,
                                "client": client})
        return {"rev": rev}

    # ----- история -----

    def _snapshot(self, pid, meta):
        """Снимок текущего (ещё не заменённого) файла проекта: <rev>-<время правки>-<автор>.grado2.gz."""
        src = self._pdir(pid) / "project.grado2"
        try:
            raw = src.read_bytes()
        except OSError:
            return
        hdir = self._pdir(pid) / "history"
        self._mkdir(hdir)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(meta["updated"]))
        name = f"{meta['rev']}-{stamp}-{meta['updated_by']}.grado2.gz"
        self._write(hdir / name, gzip.compress(raw, compresslevel=3))
        files = sorted(self._history_files(pid), key=lambda e: (e[0], e[1]))
        for _, _, _, path in files[:-HISTORY_KEEP]:
            path.unlink(missing_ok=True)

    def _history_files(self, pid):
        out = []
        hdir = self._pdir(pid) / "history"
        if hdir.is_dir():
            for p in hdir.iterdir():
                m = HISTORY_RE.fullmatch(p.name)
                if m:
                    t = calendar.timegm(time.strptime(m.group(2), "%Y%m%d-%H%M%S"))
                    out.append((int(m.group(1)), t, m.group(3), p))
        return out

    def history(self, user, pid):
        with self.lock:
            self._require(user, pid, "read")
            files = sorted(self._history_files(pid), key=lambda e: (e[0], e[1]), reverse=True)
            return [{"rev": r, "t": t, "login": lg, "size": p.stat().st_size} for r, t, lg, p in files]

    def restore(self, user, pid, rev):
        if not isinstance(rev, int) or isinstance(rev, bool) or rev < 0:
            raise HubError(400, "rev должен быть неотрицательным целым числом")
        with self.lock:
            login, meta, role = self._require(user, pid, "edit")
            found = [e for e in self._history_files(pid) if e[0] == rev]
            if not found:
                raise HubError(404, "такой версии в истории нет")
            try:
                snap = split_project(json.loads(gzip.decompress(max(found, key=lambda e: e[1])[3].read_bytes())))
            except (OSError, ValueError, EOFError, RecursionError):
                raise HubError(500, "снимок истории повреждён") from None
            cur = self._sections(pid, meta["rev"])
            changes = {n: v for n, v in snap.items()}
            changes.update({n: None for n in cur if n not in snap})
            return self._commit(pid, meta, changes, login, "", "restore", f"возврат к версии {rev}",
                                force_snap=True)

    def activity(self, user, pid):
        with self.lock:
            self._require(user, pid, "read")
            try:
                with open(self._pdir(pid) / "activity.json", encoding="utf-8") as fh:
                    items = json.load(fh)
            except (OSError, ValueError):
                items = []
            return list(reversed(items if isinstance(items, list) else []))     # новые сверху

    # ----- переименование, доступ, удаление, файл -----

    def rename_project(self, user, pid, name):
        name = _clean_name(name, "")
        if not name:
            raise HubError(400, "название не может быть пустым")
        with self.lock:
            login, meta, role = self._require(user, pid, "owner")
            new_meta = dict(meta, name=name)
            # название живёт в разделе meta: переименование — обычная новая ревизия
            self._commit(pid, new_meta, {"meta": {**self._sections(pid, meta["rev"])["meta"], "name": name}},
                         login, "", "rename", name)
        return name

    def set_member(self, user, pid, login, role):
        if role is not None and role not in ROLES:
            raise HubError(400, "роль: owner, editor, viewer или null")
        with self.lock:
            me, meta, _ = self._require(user, pid, "owner")
            target = self.users.get(login) if isinstance(login, str) else None
            if not target:
                raise HubError(404, f"пользователь «{str(login)[:40]}» не найден")
            members = dict(meta["members"])
            if role is None:
                members.pop(login, None)
            else:
                if login not in members and len(members) >= MEMBERS_MAX:
                    raise HubError(400, f"в проекте уже {MEMBERS_MAX} участников")
                members[login] = role
            personal = sorted(m for m, r in members.items() if r == "owner")
            tid = meta.get("team")
            team = self.teams.get(tid) if isinstance(tid, str) else None
            team_owners = self._active_owners((team or {}).get("members") or {})   # отключённый владелец команды не в счёт
            if not personal and not team_owners:         # владельцы: личные плюс владельцы команды проекта
                raise HubError(400, "у проекта должен остаться хотя бы один владелец")
            new_meta = dict(meta, members=members)       # в файл пишется копия; общая структура не трогается до записи
            if personal and meta["owner"] not in personal:
                new_meta["owner"] = personal[0]          # личных владельцев нет — квота остаётся на создателе
            self._save_meta(pid, new_meta)
            self._activity_add(pid, me, "member", f"{login}: {role or 'удалён'}")
            result = self._members_list(new_meta)
        self._access_changed([pid])          # поток закрывается, только если доступа не осталось и через команду
        return result

    # ----- команды -----

    def _team(self, tid):
        """Команда по id или 404. Под self.lock."""
        team = self.teams.get(tid) if isinstance(tid, str) and PID_RE.fullmatch(tid) else None
        if not isinstance(team, dict):
            raise HubError(404, "команда не найдена")
        return team

    @staticmethod
    def _team_member_or_admin(u, login, team):
        if not u.get("admin") and login not in (team.get("members") or {}):
            raise HubError(403, "вы не участник этой команды")

    def _team_projects(self, tid):
        """id проектов команды. Под self.lock."""
        out = []
        for d in sorted((self.root / "projects").iterdir()):
            if not PID_RE.fullmatch(d.name):
                continue
            try:
                if self._meta(d.name).get("team") == tid:
                    out.append(d.name)
            except HubError:
                pass
        return out

    def _team_manager(self, user, tid):
        """Владелец команды или администратор. Под self.lock. Возвращает (login, команда)."""
        login, u = self._actor(user)
        team = self._team(tid)
        if not u.get("admin") and (team.get("members") or {}).get(login) != "owner":
            raise HubError(403, "это может сделать только владелец команды")
        return login, team

    def _team_members_list(self, team):
        return [{"login": m, "name": (self.users.get(m) or {}).get("name") or m, "role": r}
                for m, r in sorted((team.get("members") or {}).items())]

    def _active_owners(self, members):
        """Владельцы команды, чьи учётные записи не отключены. Под self.lock."""
        return [m for m, r in members.items() if r == "owner" and not (self.users.get(m) or {}).get("disabled")]

    def _save_teams(self, teams):
        """Записать копию teams.json и только после успеха сделать её текущей: сбой записи не оставляет в памяти правку,
        которой нет на диске. Под self.lock."""
        self._save("teams.json", teams)
        self.teams = teams

    def _teams_of(self, login):
        return sum(1 for t in self.teams.values() if login in (t.get("members") or {}))

    def list_teams(self, user):
        with self.lock:
            login, u = self._actor(user)
            counts = self._team_counts()
            out = []
            for tid, t in self.teams.items():
                mine = (t.get("members") or {}).get(login)
                if mine is None and not u.get("admin"):
                    continue
                out.append({"id": tid, "name": t.get("name") or "", "role": "admin" if u.get("admin") else mine,
                            "members": self._team_members_list(t), "projects": counts.get(tid, 0)})
        out.sort(key=lambda t: (t["name"].lower(), t["id"]))
        return out

    def create_team(self, user, name):
        name = _clean_name(name, "Новая команда")
        with self.lock:
            login, _ = self._actor(user)
            if self._teams_of(login) >= TEAMS_PER_USER:
                raise HubError(400, f"вы уже состоите в {TEAMS_PER_USER} командах: выйдите из ненужных")
            while True:
                tid = secrets.token_hex(8)
                if tid not in self.teams:
                    break
            teams = copy.deepcopy(self.teams)
            teams[tid] = {"name": name, "created": _now(), "by": login, "members": {login: "owner"}}
            self._save_teams(teams)
        return {"id": tid}

    def rename_team(self, user, tid, name):
        name = _clean_name(name, "")
        if not name:
            raise HubError(400, "название не может быть пустым")
        with self.lock:
            self._team_manager(user, tid)
            teams = copy.deepcopy(self.teams)
            teams[tid]["name"] = name
            self._save_teams(teams)
        return name

    def set_team_member(self, user, tid, login, role):
        if role is not None and role not in TEAM_ROLES:
            raise HubError(400, "роль: owner, member или null")
        with self.lock:
            me, _ = self._actor(user)
            team = self._team(tid)
            members = dict(team.get("members") or {})
            leaving = login == me and role is None and me in members      # выйти из команды может любой участник
            if not leaving:
                self._team_manager(user, tid)
            target = self.users.get(login) if isinstance(login, str) else None
            if not target:
                raise HubError(404, f"пользователь «{str(login)[:40]}» не найден")
            if role is None:
                members.pop(login, None)
            else:
                if login not in members:
                    if len(members) >= TEAM_MEMBERS_MAX:
                        raise HubError(400, f"в команде уже {TEAM_MEMBERS_MAX} участников")
                    if self._teams_of(login) >= TEAMS_PER_USER:
                        raise HubError(400, f"этот человек уже состоит в {TEAMS_PER_USER} командах")
                members[login] = role
            if not any(r == "owner" for r in members.values()) or (
                    not self._active_owners(members) and self._active_owners(team.get("members") or {})):
                # отключённый владелец не считается; но команду, где активного владельца уже нет, администратор чинит
                raise HubError(400, "в команде должен остаться хотя бы один владелец")
            teams = copy.deepcopy(self.teams)
            teams[tid]["members"] = members
            self._save_teams(teams)
            result = self._team_members_list(teams[tid])
            pids = self._team_projects(tid)
        self._access_changed(pids)
        return result

    def delete_team(self, user, tid):
        with self.lock:
            self._team_manager(user, tid)
            if self._team_projects(tid):
                raise HubError(400, "в команде есть проекты: перенесите или удалите их")
            teams = copy.deepcopy(self.teams)
            del teams[tid]
            self._save_teams(teams)

    def set_project_team(self, user, pid, team, team_access):
        if team_access is not None and team_access not in TEAM_ACCESS:
            raise HubError(400, "доступ команды: edit, view или none")
        with self.lock:
            me, meta, _ = self._require(user, pid, "owner")
            if team_access is None:              # не указан: в той же команде доступ не меняется, в новой — «правит»
                team_access = (meta.get("team_access") if team == meta.get("team") else None) or "edit"
            if team is not None:
                self._team_member_or_admin(self.users[me], me, self._team(team))   # переезд В команду — только её участнику
            members = dict(meta["members"])
            new_owner = None
            if team is None:
                team_access = "edit"
                if not any(r == "owner" for r in members.values()):
                    # владелец был только от команды: без личного владельца проект осиротеет. Им становится тот, кто
                    # переносит; глобальный администратор, не состоящий в проекте, тоже записывается (иначе доступа нет ни у кого)
                    members[me] = "owner"
                    if meta.get("owner") not in members:
                        new_owner = me               # иначе квота и поле «владелец» висели бы на ушедшем создателе
            new_meta = dict(meta, members=members, team=team, team_access=team_access)
            if new_owner:
                new_meta["owner"] = new_owner
            self._save_meta(pid, new_meta)
            name = self.teams[team]["name"] if team else "личные"
            self._activity_add(pid, me, "team", f"{name}: {team_access}")
        self._access_changed([pid])
        return {"team": team, "team_access": team_access}

    # ----- избранное -----

    def _stars_of(self, login):
        v = self.stars.get(login)
        return set(x for x in v if isinstance(x, str)) if isinstance(v, list) else set()

    def set_star(self, user, pid, on):
        if not isinstance(on, bool):
            raise HubError(400, "on должен быть true или false")
        with self.lock:
            if on:
                login, meta, _ = self._require(user, pid, "read")
            else:                                        # убрать звезду можно и без доступа: проект мог стать недоступен
                login, _ = self._actor(user)
                _check_pid(pid)
            # исчезнувшие проекты отбрасываются при записи; недоступные просто не показываются при чтении списка
            cur = [p for p in self._stars_of(login) if p != pid and PID_RE.fullmatch(p)
                   and (self.root / "projects" / p / "meta.json").exists()]
            cur.sort()
            if on:
                if len(cur) >= STARS_MAX:
                    raise HubError(400, f"в избранном уже {STARS_MAX} проектов: уберите ненужные")
                cur.append(pid)
            stars = dict(self.stars)
            stars[login] = cur
            self._save("stars.json", stars)
            self.stars = stars
        return {"star": on}

    # ----- доступ по ссылке -----

    def _link_info(self, meta):
        """{"link": {token, role} | None, "users": [{login, name}]} — без тех, у кого есть личная или командная роль. Под self.lock."""
        link = meta.get("link")
        if not isinstance(link, dict):
            return {"link": None, "users": []}
        users = []
        for m in meta.get("link_users") or []:
            if m in meta["members"] or self._team_role(m, meta) or m not in self.users:
                continue
            users.append({"login": m, "name": self.users[m].get("name") or m})
        return {"link": {"token": link["token"], "role": link["role"]}, "users": users}

    def get_link(self, user, pid):
        with self.lock:
            _, meta, _ = self._require(user, pid, "owner")
            return self._link_info(meta)

    def set_link(self, user, pid, role, rotate=False):
        if role is not None and role not in LINK_ROLES:
            raise HubError(400, "роль по ссылке: viewer, editor или null")
        if not isinstance(rotate, bool):
            raise HubError(400, "rotate должен быть true или false")
        with self.lock:
            me, meta, _ = self._require(user, pid, "owner")
            link = meta.get("link")
            if role is None:
                new_meta = dict(meta, link=None, link_users=[])
            elif isinstance(link, dict) and isinstance(link.get("token"), str) and not rotate:
                new_meta = dict(meta, link=dict(link, role=role))          # токен и люди остаются
            else:
                new_meta = dict(meta, link={"token": secrets.token_urlsafe(18), "role": role, "created": _now(), "by": me},
                                link_users=[])
            self._save_meta(pid, new_meta)
            self._activity_add(pid, me, "link", role or "off")             # токен в журнал не попадает
            result = self._link_info(new_meta)
        self._access_changed([pid])
        return result

    def join(self, user, token, ip):
        """Войти в проект по ссылке. Неверные ссылки считаются отдельно от неудач входа по паролю."""
        if not isinstance(token, str) or not 0 < len(token) <= 64:
            raise HubError(400, "некорректная ссылка")
        ip = str(ip or "?")[:64]
        with self.lock:
            login, u = self._actor(user)
            self._throttle_check(login, ip, pre=JOIN_KEYS, msg="слишком много неверных ссылок; повторите позже")
            raw, found = token.encode("utf-8"), None
            for d in sorted((self.root / "projects").iterdir()):
                if not PID_RE.fullmatch(d.name):
                    continue
                try:
                    meta = self._meta(d.name)
                except HubError:
                    continue
                link = meta.get("link")
                if isinstance(link, dict) and isinstance(link.get("token"), str) \
                        and hmac.compare_digest(raw, link["token"].encode("utf-8")) and found is None:
                    found = meta
            if found is None:
                self._fail(login, ip, pre=JOIN_KEYS)
                raise HubError(404, "ссылка недействительна или отключена")
            meta, pid = found, found["id"]
            users = list(meta.get("link_users") or [])
            # у кого роль и без ссылки не слабее ссылочной, в список вошедших по ссылке не попадает: иначе, убранный
            # из участников, он сохранил бы доступ по ссылке незаметно для владельца
            base = self._role(u, login, dict(meta, link_users=[]))
            link_role = (meta.get("link") or {}).get("role")
            strong = base == "admin" or (base in ROLE_RANK and link_role in ROLE_RANK and ROLE_RANK[base] >= ROLE_RANK[link_role])
            added = login not in users and not strong
            if added:
                if len(users) >= LINK_USERS_MAX:
                    raise HubError(400, f"по ссылке уже вошли {LINK_USERS_MAX} человек")
                users.append(login)
                meta = dict(meta, link_users=users)
                self._save_meta(pid, meta)
            result = {"id": pid, "name": meta["name"], "role": self._role(u, login, meta)}
        if added:
            self._publish(pid, {"type": "members"})
        return result

    def _access_changed(self, pids):
        """Доступ к проектам мог измениться: сообщить участникам и закрыть потоки тех, у кого роли больше нет.
        role_of берёт self.lock, поэтому её нельзя звать под self._live (см. _recheck_subs)."""
        for pid in pids:
            self._publish(pid, {"type": "members"})
        with self._live:
            pairs = {(s.pid, s.login) for pid in pids for s in self._subs.get(pid, ())}
        lost = {(pid, login) for pid, login in pairs if self.role_of({"login": login}, pid) is None}
        if lost:
            with self._live:
                for pid in {p for p, _ in lost}:
                    self._shutdown_subs(pid, lambda s, pid=pid: (pid, s.login) in lost)

    def delete_project(self, user, pid):
        with self.lock:
            self._require(user, pid, "owner")
            gone = self.root / "projects" / f".del-{pid}"     # сначала одним переименованием убираем каталог из виду:
            shutil.rmtree(gone, ignore_errors=True)             # оборванное удаление не оставит проект без файлов
            os.replace(self._pdir(pid), gone)
            shutil.rmtree(gone, ignore_errors=True)
            self._cache.pop(pid, None)
            if self._pid_team is not None:
                self._pid_team.pop(pid, None)
        with self._live:
            self._publish(pid, {"type": "deleted"})
            self._shutdown_subs(pid, lambda s: True)
            self._presence.pop(pid, None)
            self._subs.pop(pid, None)

    def project_source(self, user, pid):
        """Файл общего проекта и его ревизия — для превью в каталоге (catalog.py); доступ — как на чтение.
        Запись файла атомарная (tmp + os.replace), поэтому читать его можно уже без замка."""
        with self.lock:
            meta = self._require(user, pid, "read")[1]
            return self._pdir(pid) / "project.grado2", meta["rev"]

    def project_file(self, user, pid):
        with self.lock:
            login, meta, role = self._require(user, pid, "read")
            try:
                data = (self._pdir(pid) / "project.grado2").read_bytes()
            except OSError:
                raise HubError(500, "файл проекта недоступен") from None
            base = re.sub(r"[^\w .-]", "_", meta["name"]).strip(" .") or "project"
            return base + ".grado2", data

    # ----- комментарии -----

    def _comments_load(self, pid):
        try:
            with open(self._pdir(pid) / "comments.json", encoding="utf-8") as fh:
                items = json.load(fh)
            return items if isinstance(items, list) else []
        except (OSError, ValueError):
            return []

    def _comments_save(self, pid, meta, items, login, action, detail):
        data = self._dump(items)
        if len(data) > COMMENTS_BYTES:
            raise HubError(400, "комментарии проекта заняли слишком много места: удалите ненужные")
        self._write(self._pdir(pid) / "comments.json", data)
        meta["rev_c"] = meta.get("rev_c", 0) + 1
        self._save_meta(pid, meta)
        self._activity_add(pid, login, action, detail)
        with self._live:
            self._publish(pid, {"type": "comments", "rev_c": meta["rev_c"]})

    @staticmethod
    def _find_comment(items, cid):
        for c in items:
            if c["id"] == cid:
                return c
        raise HubError(404, "комментарий не найден")

    def comments(self, user, pid):
        with self.lock:
            self._require(user, pid, "read")
            return self._comments_load(pid)

    def add_comment(self, user, pid, text, anchor):
        text, anchor = _clean_text(text), _clean_anchor(anchor)
        with self.lock:
            login, meta, role = self._require(user, pid, "read")
            items = self._comments_load(pid)
            if len(items) >= COMMENTS_PER_PROJECT:
                raise HubError(400, "слишком много комментариев в проекте")
            c = {"id": secrets.token_hex(6), "author": login, "created": _now(), "text": text,
                 "anchor": anchor, "resolved": False, "replies": []}
            items.append(c)
            self._comments_save(pid, meta, items, login, "comment", text[:80])
            return c

    def update_comment(self, user, pid, cid, text=None, resolved=None):
        if text is None and resolved is None:
            raise HubError(400, "нечего менять")
        if resolved is not None and not isinstance(resolved, bool):
            raise HubError(400, "resolved должен быть true или false")
        if text is not None:
            text = _clean_text(text)
        with self.lock:
            login, meta, role = self._require(user, pid, "read")
            items = self._comments_load(pid)
            c = self._find_comment(items, cid)
            if text is not None:
                if login != c["author"] and role not in ("owner", "admin"):
                    raise HubError(403, "текст комментария меняет его автор или владелец проекта")
                c["text"], c["edited"] = text, _now()
            if resolved is not None:
                c["resolved"] = resolved
            self._comments_save(pid, meta, items, login, "comment-edit", cid)
            return c

    def reply(self, user, pid, cid, text):
        text = _clean_text(text)
        with self.lock:
            login, meta, role = self._require(user, pid, "read")
            items = self._comments_load(pid)
            c = self._find_comment(items, cid)
            if len(c["replies"]) >= REPLIES_PER_COMMENT:
                raise HubError(400, "слишком много ответов")
            c["replies"].append({"id": secrets.token_hex(6), "author": login, "created": _now(), "text": text})
            self._comments_save(pid, meta, items, login, "reply", text[:80])
            return c

    def delete_comment(self, user, pid, cid):
        with self.lock:
            login, meta, role = self._require(user, pid, "read")
            items = self._comments_load(pid)
            c = self._find_comment(items, cid)
            if login != c["author"] and role not in ("owner", "admin"):
                raise HubError(403, "удалить комментарий может автор или владелец проекта")
            items.remove(c)
            self._comments_save(pid, meta, items, login, "comment-delete", cid)

    # ----- присутствие и события -----

    def _expire(self, pid, now):
        """Убрать устаревшие записи presence. Под self._live. True, если что-то убрано."""
        ents = self._presence.get(pid)
        if not ents:
            return False
        stale = [k for k, e in ents.items() if e["t"] < now - PRESENCE_TTL]
        for k in stale:
            del ents[k]
        if not ents:
            self._presence.pop(pid, None)
        return bool(stale)

    def _presence_event(self, pid):
        users = [{"login": e["login"], "name": e["name"], "color": _color(e["login"]), "client": e["client"],
                  "cursor": e["cursor"], "layer": e["layer"], "sel": e["sel"], "t": e["t"]}
                 for e in sorted(self._presence.get(pid, {}).values(), key=lambda e: (e["login"], e["client"]))]
        return {"type": "presence", "users": users}

    def _online_count(self, pid):
        now = _now()
        with self._live:
            return len({e["login"] for e in self._presence.get(pid, {}).values() if e["t"] >= now - PRESENCE_TTL})

    def _publish(self, pid, event):
        with self._live:
            for sub in list(self._subs.get(pid, ())):
                sub._put(event)

    def _tick(self, pid):
        """Вызывается подписчиками на каждом шаге ожидания: чистит presence и досылает отложенные обновления."""
        now = _now()
        with self._live:
            changed = self._expire(pid, now)
            for e in self._presence.get(pid, {}).values():
                if e["dirty"] and now - e["bcast"] >= PRESENCE_MIN_INTERVAL:
                    e["dirty"], e["bcast"] = False, now
                    changed = True
            if changed:
                self._publish(pid, self._presence_event(pid))

    def presence(self, user, pid, client, cursor, layer, sel):
        client = _clean_client(client)
        if cursor is not None:
            if not (isinstance(cursor, (list, tuple)) and len(cursor) == 2 and all(_is_num(v) for v in cursor)
                    and abs(cursor[0]) <= 720 and abs(cursor[1]) <= 90):
                raise HubError(400, "некорректный курсор")
            cursor = [float(cursor[0]), float(cursor[1])]
        if layer is not None and not _layer_key_ok(layer):
            raise HubError(400, "некорректный слой")
        if sel is None:
            sel = []
        if (not isinstance(sel, (list, tuple)) or len(sel) > SEL_MAX
                or not all(isinstance(s, str) and 0 < len(s) <= 64 for s in sel)):
            raise HubError(400, "некорректное выделение")
        with self.lock:
            login, meta, role = self._require(user, pid, "read")
            name = self.users[login].get("name") or login
        now = _now()
        with self._live:
            expired = self._expire(pid, now)
            ents = self._presence.setdefault(pid, {})
            key = (login, client)
            old = ents.get(key)
            if old is None and (len(ents) >= PRESENCE_MAX_ENTRIES
                                or sum(1 for k in ents if k[0] == login) >= PRESENCE_PER_USER):
                raise HubError(429, "слишком много подключений к проекту")
            entry = {"login": login, "name": name, "client": client, "cursor": cursor, "layer": layer,
                     "sel": list(sel), "t": now, "bcast": old["bcast"] if old else 0, "dirty": False}
            ents[key] = entry
            if now - entry["bcast"] >= PRESENCE_MIN_INTERVAL:
                entry["bcast"] = now
                self._publish(pid, self._presence_event(pid))
            else:
                entry["dirty"] = True                      # уйдёт на ближайшем шаге _tick, не чаще 2/с
                if expired:
                    self._publish(pid, self._presence_event(pid))

    def subscribe(self, user, pid):
        with self.lock:
            login, meta, role = self._require(user, pid, "read")
        sub = Subscription(self, pid, login)
        with self._live:
            live = [s for subs in self._subs.values() for s in subs]
            if len(live) >= SSE_TOTAL or sum(1 for s in live if s.login == login) >= SSE_PER_USER:
                raise HubError(429, "слишком много открытых окон; закройте лишние вкладки")
            self._subs.setdefault(pid, []).append(sub)
            self._expire(pid, _now())
            sub._put(self._presence_event(pid))            # новая вкладка сразу видит, кто в проекте
        return sub

    def _unsubscribe(self, sub):
        with self._live:
            subs = self._subs.get(sub.pid, [])
            if sub in subs:
                subs.remove(sub)
            if not subs:
                self._subs.pop(sub.pid, None)

    def _shutdown_subs(self, pid, pred):
        """Закрыть подписки проекта по условию. Под self._live."""
        keep = []
        for s in self._subs.get(pid, []):
            if pred(s):
                s._shutdown()
            else:
                keep.append(s)
        if keep:
            self._subs[pid] = keep
        else:
            self._subs.pop(pid, None)

    def _close_user_everywhere(self, login):
        with self._live:
            for pid in list(self._subs):
                self._shutdown_subs(pid, lambda s: s.login == login)

    def _recheck_subs(self, login):
        """Закрыть потоки человека в проектах, к которым у него больше нет доступа (сняли флаг администратора)."""
        with self._live:
            pids = [pid for pid, subs in self._subs.items() if any(s.login == login for s in subs)]
        lost = {pid for pid in pids if self.role_of({"login": login}, pid) is None}     # role_of берёт lock: не под _live
        if lost:
            with self._live:
                for pid in lost:
                    self._shutdown_subs(pid, lambda s: s.login == login)


# ---------- командная строка ----------

def default_root():
    env = os.environ.get("GRADO2_HUB_DIR")
    if env:
        return Path(env)
    projects = os.environ.get("GRADO2_PROJECTS") or Path.home() / "Documents" / "ГРАДО 2"
    return Path(projects) / ".hub"


def _read_password(prompt="Пароль: "):
    if sys.stdin.isatty():
        import getpass
        return getpass.getpass(prompt)
    return sys.stdin.readline().rstrip("\r\n")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="hub.py", description="Управление хабом совместной работы ГРАДО 2")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("adduser", help="создать пользователя (пароль со стандартного ввода)")
    p.add_argument("login")
    p.add_argument("--admin", action="store_true")
    p.add_argument("--name", default="")
    p = sub.add_parser("passwd", help="сменить пароль (со стандартного ввода)")
    p.add_argument("login")
    sub.add_parser("invite", help="напечатать новый код приглашения")
    sub.add_parser("list", help="пользователи, проекты, действующие приглашения")
    args = ap.parse_args(argv)
    hub = Hub(default_root())
    try:
        if args.cmd == "adduser":
            u = hub.create_user(args.login, _read_password(), args.name, args.admin)
            print(f"Создан пользователь {u['login']}" + (" (администратор)" if u["admin"] else ""))
        elif args.cmd == "passwd":
            hub.set_password(args.login.strip().lower(), _read_password("Новый пароль: "))
            print("Пароль изменён, все входы этого пользователя сброшены.")
        elif args.cmd == "invite":
            with hub.lock:
                print(hub._new_invite("cli"))
        else:
            for login in sorted(hub.users):
                u = hub.users[login]
                print(f"пользователь {login}\t{u.get('name') or ''}\t{'admin' if u.get('admin') else ''}"
                      f"\t{'отключён' if u.get('disabled') else ''}")
            for tid, t in sorted(hub.teams.items(), key=lambda x: (x[1].get("name") or "", x[0])):
                print(f"команда {tid}\t{t.get('name') or ''}\tучастников {len(t.get('members') or {})}")
            now = _now()
            for code, i in sorted(hub.invites.items(), key=lambda x: x[1]["created"]):
                if not i.get("used_by") and i.get("expires", 0) > now:
                    print(f"приглашение {code}\tдо {time.strftime('%d.%m.%Y %H:%M', time.localtime(i['expires']))}")
            for d in sorted((hub.root / "projects").iterdir()):
                try:
                    m = hub._meta(d.name)
                    print(f"проект {m['id']}\t{m['name']}\tвладелец {m['owner']}\tревизия {m['rev']}")
                except HubError:
                    pass
    except HubError as e:
        print(f"Ошибка: {e.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
