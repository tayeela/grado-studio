"""Коннектор ГИС ОГД Москвы — приём ZIP-выгрузок.

Портал отдаёт ZIP (часто ZIP-в-ZIP) с шейпами в МСК-50. Логика распаковки
повторяет рабочий GRADO-плагин; пересчёт SHP МСК-50 → WGS84 делает ogr2ogr
(GDAL из комплекта QGIS-LTR или системный). GeoJSON-члены архива читаются
без внешних зависимостей и считаются уже в WGS84.
"""

import glob
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .contract import Connector, ConnectorError, make_result
from .crs import OGD_PROJ4

# Запасные расположения ogr2ogr (GDAL), если его нет в PATH. Основной путь —
# shutil.which; здесь — типовые установки QGIS по ОС (macOS + Windows).
_OGR2OGR_FALLBACKS = [
    "/Applications/QGIS-LTR.app/Contents/MacOS/bin/ogr2ogr",
    "/Applications/QGIS.app/Contents/MacOS/bin/ogr2ogr",
]


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
    found = shutil.which("ogr2ogr")
    if found:
        return found
    for path in _OGR2OGR_FALLBACKS + _windows_ogr2ogr_candidates():
        if os.path.exists(path):
            return path
    return None


def _extract_recursive(zip_path, dest):
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    while True:
        inner = glob.glob(os.path.join(dest, "**", "*.zip"), recursive=True)
        if not inner:
            return
        for z in inner:
            try:
                with zipfile.ZipFile(z) as zf:
                    zf.extractall(os.path.dirname(z))
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
        out = shp[:-4] + ".converted.geojson"
        subprocess.run(
            [self.ogr2ogr, "-f", "GeoJSON", out, shp,
             "-s_srs", OGD_PROJ4, "-t_srs", "EPSG:4326"],
            check=True, capture_output=True, timeout=300)
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
            if self.ogr2ogr:
                try:
                    members[Path(shp).stem] = self._shp_to_geojson(shp)
                except subprocess.CalledProcessError as e:
                    notes.append(f"{Path(shp).name}: ogr2ogr не смог "
                                 f"({e.stderr.decode(errors='replace')[:200]})")
            else:
                notes.append(f"{Path(shp).name}: пропущен — нет ogr2ogr "
                             "(нужен GDAL/QGIS)")
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
