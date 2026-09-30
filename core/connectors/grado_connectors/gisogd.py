"""Коннектор ГИС ОГД Москвы — приём ZIP-выгрузок.

Портал отдаёт ZIP (часто ZIP-в-ZIP) с шейпами в МСК-50. Логика распаковки
повторяет рабочий GRADO-плагин; пересчёт SHP МСК-50 → WGS84 делает ogr2ogr
(GDAL из комплекта QGIS-LTR или системный). GeoJSON-члены архива читаются
без внешних зависимостей и считаются уже в WGS84.
"""

import glob
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .contract import Connector, ConnectorError, make_result
from .crs import OGD_PROJ4

# Известные расположения ogr2ogr (GDAL): типовые установки QGIS по ОС (macOS + Windows).
# Ищутся первыми; PATH (shutil.which) — только последняя очередь, чтобы подложенный в PATH файл не выигрывал.
_OGR2OGR_FALLBACKS = [
    "/Applications/QGIS-LTR.app/Contents/MacOS/bin/ogr2ogr",
    "/Applications/QGIS.app/Contents/MacOS/bin/ogr2ogr",
]
MAX_ARCHIVE_FILES = 20_000
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024


def _windows_ogr2ogr_candidates():
    """ogr2ogr.exe в стандартных установках QGIS на Windows (любая версия)."""
    import glob
    cands = []
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        if not base:
            continue
        cands += glob.glob(os.path.join(base, "QGIS*", "bin", "ogr2ogr.exe"))
        cands += glob.glob(os.path.join(base, "QGIS*", "apps", "*", "bin", "ogr2ogr.exe"))
    return cands


def find_ogr2ogr():
    for path in _OGR2OGR_FALLBACKS + _windows_ogr2ogr_candidates():
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    found = shutil.which("ogr2ogr")
    if found and os.path.isabs(found) and os.path.isfile(found) and os.access(found, os.X_OK):
        return found
    return None


_PATH_RE = re.compile(r"(?<![:\w/])(?:/[^\s/'\"():;,]+){2,}|[A-Za-z]:\\[^\s'\"]+")


def clean_msg(text, limit=200, tmp=None):
    """Текст ошибки для интерфейса: без путей файловой системы и переводов строки, не длиннее limit."""
    t = str(text)
    if tmp:
        t = t.replace(str(tmp), "<tmp>")
    t = _PATH_RE.sub("<path>", t)
    return " ".join(t.split())[:limit]


def _safe_extract(zip_path, dest, budget):
    """Распаковать недоверенный ZIP без выхода из каталога и zip-bomb."""
    root = Path(dest).resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            parts = [part for part in name.split("/") if part not in ("", ".")]
            if (not parts or name.startswith("/") or ".." in parts or
                    ":" in parts[0] or
                    stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK):
                raise ConnectorError(f"небезопасный путь в ZIP: {info.filename}")
            target = root.joinpath(*parts).resolve()
            if root not in target.parents and target != root:
                raise ConnectorError(f"путь выходит из ZIP-каталога: {info.filename}")
            budget["files"] += 1
            budget["bytes"] += info.file_size
            if budget["files"] > MAX_ARCHIVE_FILES:
                raise ConnectorError("слишком много файлов в ZIP")
            if budget["bytes"] > MAX_ARCHIVE_BYTES:
                raise ConnectorError("распакованный ZIP больше 1 ГБ")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def _extract_recursive(zip_path, dest):
    budget = {"files": 0, "bytes": 0}
    _safe_extract(zip_path, dest, budget)
    while True:
        inner = glob.glob(os.path.join(dest, "**", "*.zip"), recursive=True)
        if not inner:
            return
        for z in inner:
            try:
                _safe_extract(z, os.path.dirname(z), budget)
            except zipfile.BadZipFile:
                pass
            finally:
                os.remove(z)


class GisogdZip(Connector):
    name = "gisogd"
    source = "gisogd"

    def __init__(self, ogr2ogr=None):
        self.ogr2ogr = ogr2ogr or find_ogr2ogr()

    def _shp_to_geojson(self, shp):
        """SHP (МСК-50) → GeoJSON (WGS84), путь к результату. С ogr2ogr —
        доверенный путь PROJ; без GDAL — свой ридер + пересчёт МСК-50→WGS84
        (сверено с PROJ, расхождение < 1 м)."""
        out = shp[:-4] + ".converted.geojson"
        if self.ogr2ogr:
            subprocess.run(
                [self.ogr2ogr, "-f", "GeoJSON", out, shp,
                 "-s_srs", OGD_PROJ4, "-t_srs", "EPSG:4326"],
                check=True, capture_output=True, timeout=300)
            return out
        from .crs import msk50_to_wgs84, transform_geom
        from .shp_reader import read_shp
        feats = []
        for f in read_shp(shp):
            g = f.get("geometry")
            if not g:
                continue
            feats.append({"type": "Feature",
                          "geometry": transform_geom(g, msk50_to_wgs84),
                          "properties": f.get("properties") or {}})
        Path(out).write_text(
            json.dumps({"type": "FeatureCollection", "features": feats}),
            encoding="utf-8")
        return out

    def _collect(self, base, only=None):
        """Собрать члены (имя → путь GeoJSON) под каталогом base. only —
        ограничить одним stem (импорт одиночного файла). SHP конвертируются
        МСК-50 → WGS84 через ogr2ogr (если найден)."""
        members, notes = {}, []
        gjs = (glob.glob(os.path.join(base, "**", "*.geojson"), recursive=True) +
               glob.glob(os.path.join(base, "**", "*.json"), recursive=True))
        shps = glob.glob(os.path.join(base, "**", "*.shp"), recursive=True)
        if only is not None:
            gjs = [p for p in gjs if Path(p).stem == only]
            shps = [p for p in shps if Path(p).stem == only]
        for gj in gjs:
            members[Path(gj).stem] = gj
        for shp in shps:
            try:
                members[Path(shp).stem] = self._shp_to_geojson(shp)
            except subprocess.CalledProcessError as e:
                notes.append(f"{Path(shp).name}: ogr2ogr не смог "
                             f"({clean_msg(e.stderr.decode(errors='replace'), tmp=base)})")
            except Exception as e:
                notes.append(f"{Path(shp).name}: не удалось прочитать SHP ({clean_msg(e, tmp=base)})")
        if not members and not shps:
            notes.append("не найдено ни shp, ни geojson")
        return members, notes

    def fetch(self, source):
        """Приём выгрузки ГИС ОГД: ZIP (в т.ч. ZIP-в-ZIP), папка с распакованными
        слоями или одиночный файл (.geojson/.json/.shp). SHP считаются в МСК-50,
        GeoJSON — уже WGS84; имя члена (для маршрутизации) = имя файла-слоя."""
        source = Path(source)
        if not source.exists():
            raise ConnectorError(f"нет файла {source}")
        tmp = None
        try:
            if source.is_dir():
                base, only, label = str(source), None, source.name
            elif source.suffix.lower() == ".zip":
                tmp = tempfile.mkdtemp(prefix="grado_ogd_")
                _extract_recursive(str(source), tmp)
                base, only, label = tmp, None, source.name
            elif source.suffix.lower() in (".geojson", ".json", ".shp"):
                base, only, label = str(source.parent), source.stem, source.name
            else:
                raise ConnectorError(
                    f"неподдерживаемый формат: {source.suffix} — нужен "
                    ".zip, .geojson, .json, .shp или папка")
            members, notes = self._collect(base, only)
            features = []
            for member, path in sorted(members.items()):
                try:
                    gj = json.loads(Path(path).read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    notes.append(f"{member}: не GeoJSON")
                    continue
                for i, f in enumerate(gj.get("features") or []):
                    props = dict(f.get("properties") or {})
                    props["grado_member"] = member
                    features.append({
                        "type": "Feature",
                        "grado_key": f"{member}:{f.get('id', i)}",
                        "geometry": f.get("geometry"),
                        "properties": props,
                    })
            return make_result(
                features,
                params={"source": label},
                source_doc=f"ГИС ОГД Москвы, выгрузка {label}",
                notes=notes)
        finally:
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
