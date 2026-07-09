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

    def fetch(self, zip_path):
        zip_path = Path(zip_path)
        if not zip_path.exists():
            raise ConnectorError(f"нет файла {zip_path}")
        tmp = tempfile.mkdtemp(prefix="grado_ogd_")
        _extract_recursive(zip_path, tmp)

        members = {}   # имя члена → путь GeoJSON
        notes = []
        for gj in glob.glob(os.path.join(tmp, "**", "*.geojson"), recursive=True) + \
                glob.glob(os.path.join(tmp, "**", "*.json"), recursive=True):
            members[Path(gj).stem] = gj
        shps = glob.glob(os.path.join(tmp, "**", "*.shp"), recursive=True)
        for shp in shps:
            if self.ogr2ogr:
                try:
                    members[Path(shp).stem] = self._shp_to_geojson(shp)
                except subprocess.CalledProcessError as e:
                    notes.append(f"{Path(shp).name}: ogr2ogr не смог ({e.stderr.decode(errors='replace')[:200]})")
            else:
                notes.append(f"{Path(shp).name}: пропущен — нет ogr2ogr (нужен GDAL/QGIS)")
        if not members and not shps:
            notes.append("в архиве нет ни shp, ни geojson")

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
            params={"zip": zip_path.name},
            source_doc=f"ГИС ОГД Москвы, выгрузка {zip_path.name}",
            notes=notes)
