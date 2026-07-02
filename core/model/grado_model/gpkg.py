"""Минимальный GeoPackage-писатель/читатель на чистом sqlite3.

Реализует обязательное ядро спецификации OGC GeoPackage 1.3 (features):
gpkg_spatial_ref_sys, gpkg_contents, gpkg_geometry_columns, application_id.
Без зависимостей от GDAL — файл при этом открывается GDAL/OGR и QGIS.
"""

import sqlite3
from datetime import datetime, timezone

APPLICATION_ID = 0x47504B47  # 'GPKG'
USER_VERSION = 10300  # GeoPackage 1.3

UTM37N_WKT = (
    'PROJCS["WGS 84 / UTM zone 37N",GEOGCS["WGS 84",DATUM["WGS_1984",'
    'SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],'
    'AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],'
    'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
    'AUTHORITY["EPSG","4326"]],PROJECTION["Transverse_Mercator"],'
    'PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",39],'
    'PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],'
    'PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]],'
    'AXIS["Easting",EAST],AXIS["Northing",NORTH],AUTHORITY["EPSG","32637"]]'
)

WGS84_WKT = (
    'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,'
    'AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],'
    'PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],'
    'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
    'AUTHORITY["EPSG","4326"]]'
)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def create_gpkg(path):
    """Создаёт пустой GeoPackage с обязательными таблицами. Возвращает соединение."""
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
    conn.execute(f"PRAGMA user_version = {USER_VERSION}")
    conn.execute("""
        CREATE TABLE gpkg_spatial_ref_sys (
            srs_name TEXT NOT NULL,
            srs_id INTEGER PRIMARY KEY,
            organization TEXT NOT NULL,
            organization_coordsys_id INTEGER NOT NULL,
            definition TEXT NOT NULL,
            description TEXT)""")
    conn.executemany(
        "INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)",
        [
            ("Undefined Cartesian SRS", -1, "NONE", -1, "undefined",
             "undefined cartesian coordinate reference system"),
            ("Undefined Geographic SRS", 0, "NONE", 0, "undefined",
             "undefined geographic coordinate reference system"),
            ("WGS 84", 4326, "EPSG", 4326, WGS84_WKT, None),
            ("WGS 84 / UTM zone 37N", 32637, "EPSG", 32637, UTM37N_WKT,
             "рабочая проекционная СК до модуля калибровки МСК"),
        ])
    conn.execute("""
        CREATE TABLE gpkg_contents (
            table_name TEXT NOT NULL PRIMARY KEY,
            data_type TEXT NOT NULL,
            identifier TEXT UNIQUE,
            description TEXT DEFAULT '',
            last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
            srs_id INTEGER,
            CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id)
                REFERENCES gpkg_spatial_ref_sys(srs_id))""")
    conn.execute("""
        CREATE TABLE gpkg_geometry_columns (
            table_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            geometry_type_name TEXT NOT NULL,
            srs_id INTEGER NOT NULL,
            z TINYINT NOT NULL,
            m TINYINT NOT NULL,
            CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
            CONSTRAINT fk_gc_tn FOREIGN KEY (table_name)
                REFERENCES gpkg_contents(table_name),
            CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id)
                REFERENCES gpkg_spatial_ref_sys(srs_id))""")
    conn.commit()
    return conn


_SQL_TYPES = {"string": "TEXT", "integer": "INTEGER", "number": "DOUBLE"}


def add_feature_table(conn, table, identifier, geom_type, srs_id, columns, description=""):
    """columns: [(id, json_type)] — атрибуты поверх обязательных полей провенанса."""
    cols = "".join(f', "{cid}" {_SQL_TYPES[ctype]}' for cid, ctype in columns)
    conn.execute(f"""
        CREATE TABLE "{table}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            geom BLOB,
            source TEXT NOT NULL DEFAULT 'manual',
            source_date TEXT NOT NULL,
            source_doc TEXT{cols})""")
    conn.execute(
        "INSERT INTO gpkg_contents (table_name, data_type, identifier, description, last_change, srs_id) "
        "VALUES (?, 'features', ?, ?, ?, ?)",
        (table, identifier, description, now_iso(), srs_id))
    conn.execute(
        "INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', ?, ?, 0, 0)",
        (table, geom_type.upper(), srs_id))
    conn.commit()


def update_bounds(conn, table, xmin, ymin, xmax, ymax):
    conn.execute(
        "UPDATE gpkg_contents SET min_x=min(coalesce(min_x,?),?), min_y=min(coalesce(min_y,?),?), "
        "max_x=max(coalesce(max_x,?),?), max_y=max(coalesce(max_y,?),?), last_change=? "
        "WHERE table_name=?",
        (xmin, xmin, ymin, ymin, xmax, xmax, ymax, ymax, now_iso(), table))
