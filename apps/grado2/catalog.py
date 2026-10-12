"""Каталог проектов ГРАДО 2: превью-картинки, избранное, когда открывали, корзина — база SQLite рядом с файлами.

Файлы .grado2 в папке проектов остаются главными (их видно в Finder, их копирует Time Machine); база `.catalog.sqlite`
в той же папке хранит только то, что о файлах помнит каталог: превью (PNG, пересчитывается по дате и размеру файла),
звёздочку и время последнего открытия. Потеря базы не теряет проектов: она соберётся заново.
Хаб совместной работы держит в своей папке такую же базу для превью общих проектов (ключ «hub:<id>», метка — ревизия).
Вызывает server.py (маршруты /api/projects, /api/project/*, /api/hub/project/<id>/preview); проверяет tests/test_catalog.py.
"""

import io
import json
import math
import re
import shutil
import sqlite3
import threading
import time
import unicodedata
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw

DB_NAME = ".catalog.sqlite"
TRASH = ".trash"
PREVIEW_W, PREVIEW_H = 480, 300          # превью карточки 16:10; рисуется вдвое крупнее и сглаживается уменьшением
MAX_POINTS = 400_000                      # вершин на превью: дальше слои рисуются без мелочи (быстро и для больших проектов)
PAPER = (241, 243, 246, 255)
TERRITORY = (36, 70, 216, 255)            # акцент «Синьки»: граница территории

SCHEMA = """
CREATE TABLE IF NOT EXISTS project (name TEXT PRIMARY KEY, star INTEGER NOT NULL DEFAULT 0, opened REAL);
CREATE TABLE IF NOT EXISTS preview (key TEXT PRIMARY KEY, stamp TEXT NOT NULL, png BLOB, layers INTEGER, features INTEGER);
"""


def norm(name):
    """Название для сравнения: файловая система Mac не различает регистр и формы «й»/«ё»."""
    return unicodedata.normalize("NFC", name).casefold()


class Catalog:
    """База каталога одной папки. Соединение на вызов (сервер отвечает из пула потоков), записи под одним замком."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            con = sqlite3.connect(self.path, timeout=10)
            con.executescript(SCHEMA)
        except sqlite3.DatabaseError:
            # испорченная база — не повод отказывать в каталоге: откладываем её в сторону и начинаем заново
            self.path.replace(self.path.with_name(self.path.name + f".broken-{int(time.time())}"))
            con = sqlite3.connect(self.path, timeout=10)
            con.executescript(SCHEMA)
        return con

    def _run(self, sql, args=(), many=False):
        with self.lock:
            con = self._db()
            try:
                with con:
                    cur = con.executemany(sql, args) if many else con.execute(sql, args)
                    return cur.fetchall()
            finally:
                con.close()

    # ---------- избранное и недавние ----------
    def marks(self):
        """{название: {"star": bool, "opened": время или None}}."""
        return {n: {"star": bool(s), "opened": o} for n, s, o in self._run("SELECT name, star, opened FROM project")}

    def set_star(self, name, on):
        self._run("INSERT INTO project(name, star) VALUES(?, ?) ON CONFLICT(name) DO UPDATE SET star=excluded.star", (name, int(bool(on))))

    def opened(self, name):
        self._run("INSERT INTO project(name, opened) VALUES(?, ?) ON CONFLICT(name) DO UPDATE SET opened=excluded.opened", (name, time.time()))

    def rename(self, old, new):
        with self.lock:
            con = self._db()
            try:
                with con:
                    con.execute("DELETE FROM project WHERE name=? AND name<>?", (new, old))
                    con.execute("UPDATE project SET name=? WHERE name=?", (new, old))
                    con.execute("DELETE FROM preview WHERE key IN (?, ?)", (new, old))
            finally:
                con.close()

    def forget(self, name):
        self._run("DELETE FROM preview WHERE key=?", (name,))

    # ---------- превью ----------
    def preview(self, key, path, stamp=None):
        """PNG превью файла проекта (bytes) или None, если рисовать нечего. Пересчитывается, когда меняется метка
        (по умолчанию — дата и размер файла)."""
        if stamp is None:
            st = path.stat()
            stamp = f"{st.st_mtime_ns}:{st.st_size}"
        row = self._run("SELECT stamp, png FROM preview WHERE key=?", (key,))
        if row and row[0][0] == stamp:
            return row[0][1]
        try:
            obj = json.loads(path.read_bytes())
        except (OSError, ValueError):
            return None
        png, n_layers, n_feat = render_preview(obj)
        self._run("INSERT OR REPLACE INTO preview(key, stamp, png, layers, features) VALUES(?, ?, ?, ?, ?)",
                  (key, stamp, png, n_layers, n_feat))
        return png


# ---------- корзина папки проектов ----------
def trash_put(folder, path):
    """Файл проекта → <папка>/.trash/<название>~<ГГГГММДД-ЧЧММСС>.grado2. Удаление обратимо: «Корзина» в каталоге."""
    d = Path(folder) / TRASH
    d.mkdir(parents=True, exist_ok=True)
    dst = d / f"{path.stem}~{time.strftime('%Y%m%d-%H%M%S')}.grado2"
    n = 2
    while dst.exists():
        dst = d / f"{path.stem}~{time.strftime('%Y%m%d-%H%M%S')}-{n}.grado2"
        n += 1
    shutil.move(str(path), str(dst))
    return dst


TRASH_RE = re.compile(r"(.+)~(\d{8}-\d{6})(?:-\d+)?")


def trash_list(folder):
    d = Path(folder) / TRASH
    out = []
    for p in d.glob("*.grado2") if d.exists() else []:
        m = TRASH_RE.fullmatch(p.stem)
        if not m:
            continue
        st = p.stat()
        deleted = time.mktime(time.strptime(m.group(2), "%Y%m%d-%H%M%S"))
        out.append({"id": p.name, "name": m.group(1), "deleted": deleted, "size": st.st_size})
    return sorted(out, key=lambda x: -x["deleted"])


def free_name(folder, base, taken_extra=()):
    """Свободное название в папке: «Имя», «Имя 2», «Имя 3»… (сравнение без регистра)."""
    taken = {norm(p.stem) for p in Path(folder).glob("*.grado2")} | {norm(x) for x in taken_extra}
    name, n = base, 2
    while norm(name) in taken:
        name = f"{base} {n}"
        n += 1
    return name


# ---------- рисование превью ----------
def _rgba(color, alpha):
    try:
        r, g, b = ImageColor.getrgb(str(color))[:3]
    except ValueError:
        r, g, b = 134, 142, 150
    return (r, g, b, max(0, min(255, round(alpha * 255))))


def _merc(lon, lat):
    lat = max(-85.0, min(85.0, lat))
    return lon * 111319.49, math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * 6378137.0


def _parts(geom):
    """Геометрия GeoJSON → [(вид, [кольца или линии]), …]; вид: "poly", "line", "point"."""
    t, c = (geom or {}).get("type"), (geom or {}).get("coordinates")
    if not c and t != "GeometryCollection":
        return []
    if t == "Polygon":
        return [("poly", c)]
    if t == "MultiPolygon":
        return [("poly", p) for p in c]
    if t == "LineString":
        return [("line", [c])]
    if t == "MultiLineString":
        return [("line", c)]
    if t == "Point":
        return [("point", [[c]])]
    if t == "MultiPoint":
        return [("point", [c])]
    if t == "GeometryCollection":
        return [x for g in geom.get("geometries") or [] for x in _parts(g)]
    return []


def _layers(obj):
    """Видимые слои снизу вверх: [(стиль, [части])]. Первый слой файла — верхний на карте (ui/src/maplayers.js)."""
    groups = {g.get("id"): g for g in obj.get("groups") or [] if isinstance(g, dict)}
    data = obj.get("data") or {}
    out = []
    for lay in reversed([x for x in obj.get("layers") or [] if isinstance(x, dict) and x.get("key")]):
        g = groups.get(lay.get("group"))
        if lay.get("visible") is False or (g and g.get("visible") is False):
            continue
        fc = (data.get(lay["key"]) or {}).get("fc")
        if isinstance(fc, str) and fc == "=fc":
            fc = None
        feats = (fc or {}).get("features") if isinstance(fc, dict) else None
        if not feats:
            continue
        parts = [p for f in feats if isinstance(f, dict) for p in _parts(f.get("geometry"))]
        if parts:
            out.append((lay.get("style") or {}, parts))
    return out


def _bounds(rings):
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def render_preview(obj, w=PREVIEW_W, h=PREVIEW_H):
    """Проект (dict файла .grado2) → (PNG bytes или None, слоёв, объектов). Карта без подложки: слои своими цветами,
    граница территории — синей линией; кадр — по границе, без неё — по всем объектам."""
    layers = _layers(obj)
    terr = (obj.get("territory") or {}).get("geometry") if isinstance(obj.get("territory"), dict) else None
    terr_parts = _parts(terr)
    n_feat = sum(len(p) for _, p in layers)
    if not layers and not terr_parts:
        return None, 0, 0
    step = max(1, math.ceil(sum(len(r) for _, ps in layers for _, rs in ps for r in rs) / MAX_POINTS))

    def ll(r):
        return [_merc(float(p[0]), float(p[1])) for p in r[::step if len(r) > 8 else 1] if len(p) >= 2]

    src = terr_parts or [x for _, ps in layers for x in ps]
    box = _bounds([ll(r) for _, rs in src for r in rs])
    if not box:
        return None, len(layers), n_feat
    x0, y0, x1, y1 = box
    pad = 0.08 if terr_parts else 0.04
    bw, bh = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    x0, x1, y0, y1 = x0 - bw * pad, x1 + bw * pad, y0 - bh * pad, y1 + bh * pad
    W, H = w * 2, h * 2
    k = min(W / (x1 - x0), H / (y1 - y0))
    ox, oy = (W - (x1 - x0) * k) / 2, (H - (y1 - y0) * k) / 2

    def px(r):
        return [(ox + (x - x0) * k, H - (oy + (y - y0) * k)) for x, y in ll(r)]

    img = Image.new("RGBA", (W, H), PAPER)
    for st, parts in layers:
        op = float(st.get("opacity", 0.7) if isinstance(st.get("opacity"), (int, float)) else 0.7)
        fill, stroke = _rgba(st.get("fill", "#868e96"), max(op, 0.15)), _rgba(st.get("stroke", "#495057"), 1)
        width = max(1, round(float(st.get("width") or 1) * 1.5)) if isinstance(st.get("width"), (int, float)) else 2
        over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        for kind, rings in parts:
            if kind == "poly":
                outer = px(rings[0]) if rings and rings[0] else []
                if len(outer) >= 3:
                    d.polygon(outer, fill=fill, outline=stroke, width=max(1, width // 2))
            elif kind == "line":
                for r in rings:
                    q = px(r)
                    if len(q) >= 2:
                        d.line(q, fill=stroke, width=width, joint="curve")
            else:
                for r in rings:
                    for x, y in px(r):
                        d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=_rgba(st.get("fill", "#868e96"), 1), outline=(255, 255, 255, 255), width=2)
        img.alpha_composite(over)
    if terr_parts:
        d = ImageDraw.Draw(img)
        for _, rings in terr_parts:
            for r in rings:
                q = px(r)
                if len(q) >= 2:
                    d.line(q + q[:1], fill=TERRITORY, width=5, joint="curve")
    out = io.BytesIO()
    img.resize((w, h), Image.LANCZOS).convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue(), len(layers), n_feat
