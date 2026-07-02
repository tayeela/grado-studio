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

SOURCES = {"manual", "nspd", "fgistp", "gisogd", "import"}


class ProjectError(ValueError):
    pass


def _table_name(code):
    return "l_" + code.replace(".", "_")


class Layer:
    def __init__(self, project, code):
        self.project = project
        self.code = code
        self.cls = project.classifier.get(code)
        self.table = _table_name(code)

    def add_feature(self, geom, attrs=None, source="manual", source_date=None, source_doc=None):
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
        self.cls.validate_attrs(attrs)
        source_date = source_date or date.today().isoformat()

        cols = ["geom", "source", "source_date", "source_doc"]
        vals = [geometry.gpkg_blob(geom, self.project.srs_id), source, source_date, source_doc]
        for key, value in attrs.items():
            cols.append(f'"{key}"')
            vals.append(value)
        cur = self.project.conn.execute(
            f'INSERT INTO "{self.table}" ({",".join(cols)}) VALUES ({",".join("?" * len(vals))})',
            vals)
        xs = [p[0] for p in _flat_points(geom)]
        ys = [p[1] for p in _flat_points(geom)]
        gpkg.update_bounds(self.project.conn, self.table, min(xs), min(ys), max(xs), max(ys))
        self.project.conn.commit()
        return cur.lastrowid

    def features(self):
        attr_ids = [a["id"] for a in self.cls.attrs]
        cols = ", ".join(f'"{a}"' for a in attr_ids)
        sql = f'SELECT id, geom, source, source_date, source_doc{", " + cols if cols else ""} FROM "{self.table}"'
        for row in self.project.conn.execute(sql):
            geom, _srs = geometry.gpkg_parse(row[1]) if row[1] else (None, None)
            yield {
                "id": row[0],
                "geom": geom,
                "source": row[2],
                "source_date": row[3],
                "source_doc": row[4],
                "attrs": dict(zip(attr_ids, row[5:])),
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
        conn.execute("""
            CREATE TABLE grado_layers (
                table_name TEXT PRIMARY KEY REFERENCES gpkg_contents(table_name),
                classifier_code TEXT NOT NULL,
                title TEXT NOT NULL,
                created TEXT NOT NULL)""")
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
            raise ProjectError(f"{path} — не проект ГРАДО (нет grado_meta)") from None
        return cls(conn, path)

    def meta(self, key):
        row = self.conn.execute("SELECT value FROM grado_meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def add_layer(self, code, title=None):
        c = self.classifier.get(code)
        table = _table_name(code)
        exists = self.conn.execute(
            "SELECT 1 FROM grado_layers WHERE table_name=?", (table,)).fetchone()
        if exists:
            raise ProjectError(f"слой {code} уже есть в проекте")
        columns = [(a["id"], a["type"]) for a in c.attrs]
        gpkg.add_feature_table(self.conn, table, title or c.title, c.geom_type,
                               self.srs_id, columns, description=f"grado:{code}")
        self.conn.execute(
            "INSERT INTO grado_layers VALUES (?,?,?,?)",
            (table, code, title or c.title, gpkg.now_iso()))
        self.conn.commit()
        return Layer(self, code)

    def layer(self, code):
        row = self.conn.execute(
            "SELECT 1 FROM grado_layers WHERE classifier_code=?", (code,)).fetchone()
        if not row:
            raise ProjectError(f"в проекте нет слоя {code}")
        return Layer(self, code)

    def layers(self):
        rows = self.conn.execute(
            "SELECT classifier_code, title, table_name FROM grado_layers ORDER BY table_name")
        return [{"code": r[0], "title": r[1], "table": r[2]} for r in rows]

    def close(self):
        self.conn.close()
