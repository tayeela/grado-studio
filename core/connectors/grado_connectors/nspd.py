"""Коннектор НСПД (Росреестр): захват моста + прямая выгрузка по экстенту.

Захват (NspdCapture): браузерное расширение GRADO перехватывает fetch()
с 'intersects' и отправляет GeoJSON как есть (EPSG:3857, вложенный словарь
options в properties). Коннектор нормализует такие payload'ы: options →
плоские opt_*-поля (как в плагине), координаты → WGS84, дедупликация по
геометрии, стабильный ключ — кадастровый номер.

Прямая выгрузка (NspdDirect): тот же запрос, что делает сам геопортал
nspd.gov.ru при «поиске в области», без авторизации (протокол снят с бандла
геопортала и проверен живыми запросами, 07.2026):
    POST /api/geoportal/v1/intersects?typeIntersect=fullObject
    {"geom": FeatureCollection EPSG:3857 (crs внутри geometry),
     "categories": [{"id": N}]}          ← именно объекты {"id": ...}
Ответ — та же FeatureCollection, что перехватывал мост, поэтому
нормализация переиспользует NspdCapture.
"""

import hashlib
import json
import ssl
import time
import urllib.request
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


# --- прямая выгрузка по экстенту (без браузерного моста) --------------------

INTERSECTS_URL = ("https://nspd.gov.ru/api/geoportal/v1/intersects"
                  "?typeIntersect=fullObject")

# Категории геопортала НСПД (проверены живыми intersects-запросами 07.2026).
NSPD_CATEGORIES = {
    36368: "Земельные участки ЕГРН",
    36369: "Здания",
    36383: "Сооружения",
    469038: "ЗОУИТ объектов культурного наследия",
    469039: "ЗОУИТ объектов энергетики, связи, транспорта",
    469040: "ЗОУИТ охраняемых объектов и безопасности",
    469041: "ЗОУИТ природных территорий",
    469042: "Иные ЗОУИТ",
}

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) grado-studio/0.1"


def _ssl_context():
    # Сборки Python.org на macOS не видят системные CA — без certifi HTTPS
    # падает CERTIFICATE_VERIFY_FAILED (правило 6 CLAUDE.md проекта).
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _ssl_context_unverified():
    # nspd.gov.ru подписан НУЦ Минцифры («Russian Trusted Root CA»), которого
    # нет ни в certifi, ни в системных CA вне РФ-сборок. Проверку пробуем
    # честно (контекст выше); если цепочка не строится — офиц. рекомендация
    # Госуслуг либо ставить НУЦ-корень, либо работать без проверки. Данные
    # справочные и открытые — деградация допустима.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class NspdDirect(Connector):
    """Выгрузка объектов НСПД по прямоугольнику WGS84 (см. докстринг модуля)."""
    name = "nspd"
    source = "nspd"

    def __init__(self, transport=None):
        self.transport = transport or self._http_post

    def _http_post(self, url, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={
            "User-Agent": _UA, "Content-Type": "application/json",
            "Referer": "https://nspd.gov.ru/map"})
        ctx = _ssl_context()
        last = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=45, context=ctx) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:   # лимит частоты геопортала
                    time.sleep(1.5 * (attempt + 1))
                    last = e
                    continue
                try:
                    detail = json.loads(e.read().decode("utf-8")).get("message", "")
                except Exception:
                    detail = ""
                raise ConnectorError(
                    f"НСПД ответил HTTP {e.code}"
                    + (f": {detail}" if detail else "")) from None
            except Exception as e:
                # сертификат НУЦ Минцифры не строится через certifi (urllib
                # заворачивает SSLCertVerificationError в URLError) —
                # деградируем до соединения без проверки
                is_cert = isinstance(e, ssl.SSLCertVerificationError) or \
                    "CERTIFICATE_VERIFY_FAILED" in str(e)
                if is_cert and ctx.verify_mode != ssl.CERT_NONE:
                    ctx = _ssl_context_unverified()
                    continue
                raise ConnectorError(f"НСПД недоступен: {e}") from None
        raise ConnectorError(f"НСПД: слишком много запросов ({last})")

    @staticmethod
    def _bbox_fc(bbox):
        west, south, east, north = map(float, bbox)
        ring = [[west, south], [east, south], [east, north],
                [west, north], [west, south]]
        merc = [list(crs.wgs84_to_merc(lon, lat)) for lon, lat in ring]
        return {"type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {},
            "geometry": {
                "crs": {"type": "name", "properties": {"name": "EPSG:3857"}},
                "type": "Polygon", "coordinates": [merc]}}]}

    def fetch(self, bbox, categories):
        """bbox = (west, south, east, north) WGS84; categories = [int, ...]."""
        geom = self._bbox_fc(bbox)
        raw, notes = [], []
        for i, cid in enumerate(categories):
            if i:
                time.sleep(0.4)   # бережём лимит частоты геопортала
            try:
                data = self.transport(
                    INTERSECTS_URL,
                    {"geom": geom, "categories": [{"id": int(cid)}]})
            except ConnectorError as e:
                notes.append(f"{NSPD_CATEGORIES.get(int(cid), cid)}: {e}")
                continue
            raw.extend(data.get("features") or [])
        # дальше — тот же путь нормализации, что у захвата моста
        result = NspdCapture().fetch(payload={"features": raw})
        result["params"] = {
            "bbox": ",".join(f"{float(v):.5f}" for v in bbox),
            "categories": sorted(int(c) for c in categories)}
        result["source_doc"] = "НСПД (nspd.gov.ru), выгрузка по экстенту"
        result["notes"].extend(notes)
        if notes:
            # отказ геопортала — ошибка, а не пустой слой: пустой ответ при повторной выгрузке затёр бы слой с правками
            raise ConnectorError("; ".join(notes))
        return result
