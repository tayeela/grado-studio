"""Коннектор НСПД (Росреестр) — режим захвата.

Официального API нет; браузерное расширение GRADO перехватывает fetch()
с 'intersects' и отправляет GeoJSON как есть (EPSG:3857, вложенный словарь
options в properties). Коннектор нормализует такие payload'ы: options →
плоские opt_*-поля (как в плагине), координаты → WGS84, дедупликация по
геометрии, стабильный ключ — кадастровый номер.

В продукте место транспорта займёт WebView сервиса данных с авторизованной
сессией; формат payload не меняется.
"""

import hashlib
import json
from pathlib import Path

from . import crs
from .contract import Connector, ConnectorError, make_result


def _flatten_options(props):
    if "options" not in props:
        return props
    try:
        opts = props.pop("options")
        if isinstance(opts, str):
            opts = json.loads(opts)
        for k, v in opts.items():
            props[f"opt_{k}"] = v
    except Exception:
        pass
    return props


def _geom_sig(geom):
    payload = json.dumps(
        {"t": geom["type"], "c": geom["coordinates"]}, sort_keys=True, default=float)
    return hashlib.sha1(payload.encode()).hexdigest()


class NspdCapture(Connector):
    name = "nspd"
    source = "nspd"

    def __init__(self, drop_dir=None):
        self.drop_dir = Path(drop_dir) if drop_dir else None

    def discover(self):
        """Необработанные захваты в папке моста."""
        if not self.drop_dir or not self.drop_dir.is_dir():
            return []
        return sorted(str(p) for p in self.drop_dir.glob("*.json"))

    def fetch(self, payload=None, path=None):
        if payload is None:
            if path is None:
                raise ConnectorError("нужен payload или path")
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("grado_source", "nspd") != "nspd":
            raise ConnectorError(f"это не НСПД-захват: {payload.get('grado_source')!r}")

        features, seen = [], set()
        for f in payload.get("features") or []:
            geom = f.get("geometry")
            if not geom:
                continue
            sig = _geom_sig(geom)
            if sig in seen:
                continue
            seen.add(sig)
            props = _flatten_options(dict(f.get("properties") or {}))
            key = (f.get("id") or props.get("cad_num")
                   or props.get("opt_cad_num") or f"geom:{sig[:12]}")
            features.append({
                "type": "Feature",
                "grado_key": str(key),
                "geometry": crs.transform_geom(geom, crs.merc_to_wgs84),
                "properties": props,
            })
        return make_result(
            features,
            params={"path": str(path) if path else None},
            source_doc=payload.get("grado_doc"),
            notes=[f"дубликатов по геометрии отброшено: "
                   f"{len(payload.get('features') or []) - len(features)}"])
