"""Проектная БД: файл .grado = GeoPackage с расширенными таблицами.

Инварианты (docs/architecture.md): слой обязан ссылаться на код
классификатора; у каждого объекта — провенанс (источник, дата, документ);
координаты — в проекционной СК проекта, метры.
"""

import json
import sqlite3
from datetime import date
from pathlib import Path

from . import geometry, gpkg
from .classifier import Classifier

GRADO_VERSION = "0.1.0"
DEFAULT_SRS_ID = 32637

SOURCES = {"manual", "nspd", "fgistp", "gisogd", "osm", "import"}


class ProjectError(ValueError):
    pass


# Реестр слоёв v2 (MODEL-01): идентичность (layer_id) отделена от
# семантического класса (classifier_code); у слоя своя стадия, стиль и
# вид источника. table_name уникален (от layer_id).
_GRADO_LAYERS_DDL = """
    CREATE TABLE grado_layers (
        layer_id TEXT PRIMARY KEY,
        table_name TEXT NOT NULL UNIQUE REFERENCES gpkg_contents(table_name),
        classifier_code TEXT NOT NULL,
        title TEXT NOT NULL,
        stage TEXT,
        style_id TEXT,
        source_kind TEXT,
        fields TEXT,
        created TEXT NOT NULL)"""

_LAYER_COLS = ("layer_id, table_name, classifier_code, title, "
               "stage, style_id, source_kind")
# те же поля + пользовательские (per-слой атрибуты сверх классификатора)
_LAYER_READ = _LAYER_COLS + ", fields"

# служебные колонки feature-таблицы — на них пользовательское поле лечь не может
_RESERVED_COLS = {"id", "geom", "source", "source_date", "source_doc", "style_id"}


def _table_name(layer_id):
    # имя таблицы — от layer_id (уникального), не от semantic_class:
    # два слоя одного класса (source.fgistp.func_zones и project.tp.func_zone)
    # обязаны иметь разные таблицы
    return "l_" + layer_id.replace(".", "_")


class Layer:
    """Слой проекта: идентичность layer_id != семантический класс (code).

    code (=semantic_class) задаёт класс классификатора (схему атрибутов, тип
    геометрии, роль ТЭП); layer_id уникален. У слоя своя стадия, стиль
    по умолчанию и вид источника (MODEL-01)."""

    def __init__(self, project, spec):
        self.project = project
        self.layer_id = spec["layer_id"]
        self.code = spec["code"]            # semantic_class (код классификатора)
        self.semantic_class = spec["code"]
        self.title = spec.get("title")
        self.table = spec["table"]
        self.stage = spec.get("stage")
        self.style_id = spec.get("style_id")
        self.source_kind = spec.get("source_kind")
        self.cls = project.classifier.get(self.code)
        # пользовательские поля слоя (атрибутивная таблица студии) — колонки
        # сверх схемы классификатора: [{"id", "type"}], type в терминах gpkg
        self.user_fields = spec.get("fields") or []

    def _coerce(self, geom, attrs, source, source_date):
        geometry.validate(geom)
        if geom["type"] != self.cls.geom_type:
            # Polygon в MultiPolygon-слой оборачиваем автоматически, как GDAL
            if self.cls.geom_type == "Multi" + geom["type"]:
                geom = {"type": self.cls.geom_type, "coordinates": [geom["coordinates"]]}
            else:
                raise ProjectError(
                    f"слой {self.code}: ожидается {self.cls.geom_type}, получено {geom['type']}")
        if source not in SOURCES:
            raise ProjectError(f"неизвестный источник {source!r}; допустимы {sorted(SOURCES)}")
        attrs = attrs or {}
        # классификаторные атрибуты валидируем строго (как прежде), а
        # пользовательские поля слоя пропускаем — их схема живёт на слое,
        # значения приводит к типу вызывающий (studio_core при экспорте)
        user_ids = {f["id"] for f in self.user_fields}
        # "arc"/"circle" internal CAD (parametric as JSON); not validated as classifier attr
        self.cls.validate_attrs({k: v for k, v in attrs.items() if k not in user_ids and k not in ("arc", "circle")})
        return geom, attrs, source_date or date.today().isoformat()

    def _write(self, fid, geom, attrs, source, source_date, source_doc, style_id):
        cols = ["geom", "source", "source_date", "source_doc", "style_id"]
        vals = [geometry.gpkg_blob(geom, self.project.srs_id), source,
                source_date, source_doc, style_id]
        for key, value in attrs.items():
            cols.append(f'"{key}"')
            vals.append(value)
        if fid is None:
            cur = self.project.conn.execute(
                f'INSERT INTO "{self.table}" ({",".join(cols)}) VALUES ({",".join("?" * len(vals))})',
                vals)
            fid = cur.lastrowid
        else:
            self.project.conn.execute(
                f'INSERT OR REPLACE INTO "{self.table}" (id, {",".join(cols)}) '
                f'VALUES ({",".join("?" * (len(vals) + 1))})', [fid] + vals)
        xs = [p[0] for p in _flat_points(geom)]
        ys = [p[1] for p in _flat_points(geom)]
        gpkg.update_bounds(self.project.conn, self.table, min(xs), min(ys), max(xs), max(ys))
        self.project.conn.commit()
        return fid

    def add_feature(self, geom, attrs=None, source="manual", source_date=None,
                    source_doc=None, style_id=None):
        geom, attrs, source_date = self._coerce(geom, attrs, source, source_date)
        return self._write(None, geom, attrs, source, source_date, source_doc, style_id)

    def set_feature(self, fid, snapshot):
        """Записывает объект с заданным id (реплей дельт журнала)."""
        geom, attrs, source_date = self._coerce(
            snapshot["geom"], snapshot.get("attrs"),
            snapshot.get("source", "manual"), snapshot.get("source_date"))
        return self._write(fid, geom, attrs, snapshot.get("source", "manual"),
                           source_date, snapshot.get("source_doc"),
                           snapshot.get("style_id"))

    def delete_feature(self, fid):
        cur = self.project.conn.execute(f'DELETE FROM "{self.table}" WHERE id=?', (fid,))
        self.project.conn.commit()
        return cur.rowcount > 0

    def get_feature(self, fid):
        for f in self.features(where_id=fid):
            return f
        return None

    def features(self, where_id=None):
        attr_ids = [a["id"] for a in self.cls.attrs] + \
                   [f["id"] for f in self.user_fields]
        # include internal CAD "arc"/"circle" columns (parametric for arcs, circles/radii/buffers) if present
        try:
            pragma = self.project.conn.execute(f'PRAGMA table_info("{self.table}")').fetchall()
            have = {r[1] for r in pragma}
            for ic in ("arc", "circle"):
                if ic in have and ic not in attr_ids:
                    attr_ids.append(ic)
        except Exception:
            pass
        cols = ", ".join(f'"{a}"' for a in attr_ids)
        sql = (f'SELECT id, geom, source, source_date, source_doc, style_id'
               f'{", " + cols if cols else ""} FROM "{self.table}"')
        params = ()
        if where_id is not None:
            sql += " WHERE id=?"
            params = (where_id,)
        for row in self.project.conn.execute(sql, params):
            geom, _srs = geometry.gpkg_parse(row[1]) if row[1] else (None, None)
            yield {
                "id": row[0],
                "geom": geom,
                "source": row[2],
                "source_date": row[3],
                "source_doc": row[4],
                "style_id": row[5],
                "attrs": dict(zip(attr_ids, row[6:])),
            }

    def count(self):
        (n,) = self.project.conn.execute(f'SELECT count(*) FROM "{self.table}"').fetchone()
        return n

    def area_ha(self):
        return sum(geometry.area(f["geom"]) for f in self.features() if f["geom"]) / 10000.0

    def length_m(self):
        return sum(geometry.length(f["geom"]) for f in self.features() if f["geom"])


def _flat_points(geom):
    coords = geom["coordinates"]
    gtype = geom["type"]
    if gtype == "Point":
        return [coords]
    if gtype in ("LineString", "MultiPoint"):
        return coords
    if gtype in ("Polygon", "MultiLineString"):
        return [p for part in coords for p in part]
    return [p for poly in coords for ring in poly for p in ring]


class Project:
    def __init__(self, conn, path):
        self.conn = conn
        self.path = Path(path)
        self.classifier = Classifier.load()
        self.srs_id = int(self.meta("srs_id"))

    @classmethod
    def create(cls, path, name, srs_id=DEFAULT_SRS_ID):
        path = Path(path)
        if path.exists():
            raise ProjectError(f"файл уже существует: {path}")
        conn = gpkg.create_gpkg(str(path))
        conn.execute("CREATE TABLE grado_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(_GRADO_LAYERS_DDL)
        conn.executemany(
            "INSERT INTO grado_meta VALUES (?,?)",
            [("name", name), ("srs_id", str(srs_id)),
             ("grado_version", GRADO_VERSION), ("created", gpkg.now_iso())])
        conn.commit()
        return cls(conn, path)

    @classmethod
    def open(cls, path):
        path = Path(path)
        if not path.exists():
            raise ProjectError(f"нет файла {path}")
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("SELECT 1 FROM grado_meta LIMIT 1")
        except sqlite3.OperationalError:
            # На Windows открытый sqlite-дескриптор блокирует удаление файла.
            # Невалидный проект не возвращает Project, поэтому закрываем его
            # здесь явно, а не оставляем освобождение сборщику мусора.
            conn.close()
            raise ProjectError(f"{path} — не проект ГРАДО (нет grado_meta)") from None
        try:
            cls._migrate_v2(conn)
            return cls(conn, path)
        except Exception:
            conn.close()
            raise

    @staticmethod
    def _migrate_v2(conn):
        """Апгрейд .grado, созданных до MODEL-01: layer_id/stage/style_id/
        source_kind в grado_layers и колонка style_id в feature-таблицах.
        Для legacy layer_id = classifier_code (журналы дельт валидны)."""
        cols = [r[1] for r in conn.execute("PRAGMA table_info(grado_layers)")]
        if "layer_id" not in cols:
            classifier = Classifier.load()
            old = conn.execute(
                "SELECT table_name, classifier_code, title, created "
                "FROM grado_layers").fetchall()
            conn.execute("ALTER TABLE grado_layers RENAME TO grado_layers_v1")
            conn.execute(_GRADO_LAYERS_DDL)
            for table_name, code, title, created in old:
                c = classifier.classes.get(code)
                conn.execute(
                    f"INSERT INTO grado_layers ({_LAYER_COLS}, created) "
                    f"VALUES (?,?,?,?,?,?,?,?)",
                    (code, table_name, code, title,
                     c.stage if c else None, c.style_id if c else None,
                     None, created))
            conn.execute("DROP TABLE grado_layers_v1")
        # пользовательские поля слоёв (экспорт атрибутивной таблицы студии) —
        # добавлены позже MODEL-01; на старых v2-файлах колонки ещё нет
        cols = [r[1] for r in conn.execute("PRAGMA table_info(grado_layers)")]
        if "fields" not in cols:
            conn.execute("ALTER TABLE grado_layers ADD COLUMN fields TEXT")
        for (table_name,) in conn.execute("SELECT table_name FROM grado_layers"):
            fcols = [r[1] for r in conn.execute(
                f'PRAGMA table_info("{table_name}")')]
            if "style_id" not in fcols:
                conn.execute(f'ALTER TABLE "{table_name}" ADD COLUMN style_id TEXT')
        conn.commit()

    def meta(self, key):
        row = self.conn.execute("SELECT value FROM grado_meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key, value):
        """Сохранить метаданные проекта (в т.ч. project_styles)."""
        self.conn.execute(
            "INSERT OR REPLACE INTO grado_meta (key, value) VALUES (?, ?)",
            (key, str(value) if value is not None else "")
        )
        self.conn.commit()

    def add_layer(self, code, title=None, layer_id=None, stage=None,
                  style_id=None, source_kind=None, fields=None):
        """Создаёт слой. layer_id по умолчанию = code (legacy 1:1); передав
        отдельный layer_id, можно завести несколько слоёв одного класса
        (напр. source.fgistp.func_zones и project.tp.func_zone). stage и
        style_id по умолчанию берутся из классификатора. fields — [{id,type}]
        пользовательских полей (атрибутивная таблица студии): колонки сверх
        схемы классификатора, type в терминах gpkg (string|integer|number)."""
        c = self.classifier.get(code)
        layer_id = layer_id or code
        table = _table_name(layer_id)
        exists = self.conn.execute(
            "SELECT 1 FROM grado_layers WHERE layer_id=?", (layer_id,)).fetchone()
        if exists:
            raise ProjectError(f"слой {layer_id} уже есть в проекте")
        title = title or c.title
        # identifier в gpkg_contents уникален на уровне GeoPackage — если два
        # слоя одного класса получат одинаковый заголовок (оба без явного
        # title), различаем их по layer_id вместо падения сырым
        # IntegrityError внутри add_feature_table
        if self.conn.execute(
                "SELECT 1 FROM grado_layers WHERE title=?", (title,)).fetchone():
            title = f"{title} ({layer_id})"
        stage = c.stage if stage is None else stage
        style_id = c.style_id if style_id is None else style_id
        # пользовательские поля: пропускаем коллизии с классификатором/служебными
        # колонками и дубли; тип, неизвестный gpkg, приводим к string
        cls_ids = {a["id"] for a in c.attrs}
        user_fields, seen = [], set()
        for f in (fields or []):
            fid = f.get("id")
            if not fid or fid in cls_ids or fid in _RESERVED_COLS or fid in seen:
                continue
            ftype = f.get("type") if f.get("type") in gpkg._SQL_TYPES else "string"
            user_fields.append({"id": fid, "type": ftype})
            seen.add(fid)
        columns = [(a["id"], a["type"]) for a in c.attrs] + \
                  [(f["id"], f["type"]) for f in user_fields]
        # internal columns for CAD arcs/circles (parametric for roundtrip, radii, buffers; not user attrs)
        for internal in ("arc", "circle"):
            if not any(col[0] == internal for col in columns):
                columns.append((internal, "string"))
        gpkg.add_feature_table(self.conn, table, title, c.geom_type,
                               self.srs_id, columns, description=f"grado:{code}")
        fields_json = json.dumps(user_fields, ensure_ascii=False) if user_fields else None
        self.conn.execute(
            f"INSERT INTO grado_layers ({_LAYER_COLS}, fields, created) "
            f"VALUES (?,?,?,?,?,?,?,?,?)",
            (layer_id, table, code, title, stage, style_id, source_kind,
             fields_json, gpkg.now_iso()))
        self.conn.commit()
        return Layer(self, {"layer_id": layer_id, "code": code, "title": title,
                            "table": table, "stage": stage, "style_id": style_id,
                            "source_kind": source_kind, "fields": user_fields})

    def _layer_spec(self, layer_id=None, code=None):
        if layer_id is not None:
            row = self.conn.execute(
                f"SELECT {_LAYER_READ} FROM grado_layers WHERE layer_id=?",
                (layer_id,)).fetchone()
        else:
            row = self.conn.execute(
                f"SELECT {_LAYER_READ} FROM grado_layers WHERE classifier_code=? "
                f"ORDER BY table_name LIMIT 1", (code,)).fetchone()
        if not row:
            return None
        return {"layer_id": row[0], "table": row[1], "code": row[2],
                "title": row[3], "stage": row[4], "style_id": row[5],
                "source_kind": row[6],
                "fields": json.loads(row[7]) if row[7] else []}

    def layer(self, ident):
        """Слой по layer_id или (legacy) по коду класса (первый при 1:1)."""
        spec = self._layer_spec(layer_id=ident) or self._layer_spec(code=ident)
        if spec is None:
            raise ProjectError(f"в проекте нет слоя {ident}")
        return Layer(self, spec)

    def layer_by_id(self, layer_id):
        spec = self._layer_spec(layer_id=layer_id)
        if spec is None:
            raise ProjectError(f"в проекте нет слоя с id {layer_id}")
        return Layer(self, spec)

    def layers(self):
        rows = self.conn.execute(
            f"SELECT {_LAYER_COLS} FROM grado_layers ORDER BY table_name")
        return [{"code": r[2], "layer_id": r[0], "semantic_class": r[2],
                 "title": r[3], "table": r[1], "stage": r[4],
                 "style_id": r[5], "source_kind": r[6]} for r in rows]

    def close(self):
        self.conn.close()
