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
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import crs, netutil
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


_CERT_HELP = (
    "НСПД: сертификат nspd.gov.ru не прошёл проверку — корневой сертификат "
    "НУЦ Минцифры не установлен. Скачайте russian_trusted_root_ca_pem.crt и "
    "russian_trusted_sub_ca_pem.crt с gu-st.ru/content/Other/doc/ и положите "
    "их в папку ~/.grado2/ca/ (либо укажите файл PEM в переменной "
    "GRADO_NSPD_CA). Проверка сертификата отключается только явно: "
    "GRADO_NSPD_INSECURE=1.")

_insecure_warned = False


def _extra_ca_files():
    """Дополнительные корни: GRADO_NSPD_CA, затем ~/.grado2/ca/, затем certs/ в репозитории."""
    files = []
    env = os.environ.get("GRADO_NSPD_CA")
    if env:
        files.append(Path(env).expanduser())
    for d in (Path.home() / ".grado2" / "ca", Path(__file__).parent / "certs"):
        try:
            files.extend(sorted(p for p in d.iterdir()
                                if p.suffix.lower() in (".crt", ".pem")))
        except OSError:
            pass
    return files


def _ssl_context():
    # Сборки Python.org на macOS не видят системные CA — без certifi HTTPS
    # падает CERTIFICATE_VERIFY_FAILED (правило 6 CLAUDE.md проекта).
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    # nspd.gov.ru подписан НУЦ Минцифры, которого нет в certifi: подгружаем
    # его корни из файлов (битые и нечитаемые пропускаем молча).
    for f in _extra_ca_files():
        try:
            ctx.load_verify_locations(cafile=str(f))
        except (ssl.SSLError, OSError, ValueError):
            pass
    return ctx


def _ssl_context_unverified():
    # Только по явному GRADO_NSPD_INSECURE=1: соединение без проверки сертификата.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _warn_insecure():
    global _insecure_warned
    if not _insecure_warned:
        _insecure_warned = True
        print("ВНИМАНИЕ: GRADO_NSPD_INSECURE=1 — соединение с НСПД БЕЗ проверки "
              "сертификата. Установите корни НУЦ Минцифры в ~/.grado2/ca/.",
              file=sys.stderr)


def _short(text):
    """Текст ответа/исключения для сообщения: без переводов строк, не длиннее 200 знаков."""
    return " ".join(str(text).split())[:200]


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
                with netutil.open_url(req, 45, ctx) as r:
                    return json.loads(netutil.read_capped(r).decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:   # лимит частоты геопортала
                    time.sleep(1.5 * (attempt + 1))
                    last = e
                    continue
                try:
                    detail = _short(json.loads(
                        netutil.read_capped(e).decode("utf-8")).get("message", ""))
                except Exception:
                    detail = ""
                raise ConnectorError(
                    f"НСПД ответил HTTP {e.code}"
                    + (f": {detail}" if detail else "")) from None
            except Exception as e:
                # urllib заворачивает SSLCertVerificationError в URLError
                is_cert = isinstance(e, ssl.SSLCertVerificationError) or \
                    "CERTIFICATE_VERIFY_FAILED" in str(e)
                if is_cert and ctx.verify_mode != ssl.CERT_NONE:
                    if os.environ.get("GRADO_NSPD_INSECURE") == "1":
                        _warn_insecure()
                        ctx = _ssl_context_unverified()
                        continue
                    raise ConnectorError(_CERT_HELP) from None
                raise ConnectorError(f"НСПД недоступен: {_short(e)}") from None
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


# --- поиск участка по кадастровому номеру ------------------------------------
# GET /api/geoportal/v2/search/geoportal?query=<номер>&thematicSearchId=1 —
# тот же вызов, что делает строка поиска геопортала (проверен 26.09.2026).
# Ответ — GeoJSON EPSG:3857 с геометрией и атрибутами; дальше путь тот же,
# что у выгрузки по области (NspdCapture): options → opt_*, координаты → WGS84.

SEARCH_URL = "https://nspd.gov.ru/api/geoportal/v2/search/geoportal"
CAD_RE = re.compile(r"^[0-9]{2}:[0-9]{2}:[0-9]{6,7}:[0-9]+$")
SEARCH_MAX = 20


class _Retryable(ConnectorError):
    """Сбой, который стоит повторить: лимит частоты, 5xx, сеть."""


def _http_get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA, "Accept": "application/json",
        "Referer": "https://nspd.gov.ru/map?thematic=PKK",
        "Origin": "https://nspd.gov.ru"})
    ctx = _ssl_context()
    for _ in range(2):                       # второй заход — только для явного GRADO_NSPD_INSECURE=1
        try:
            with netutil.open_url(req, 30, ctx) as r:
                return json.loads(netutil.read_capped(r).decode("utf-8"))
        except urllib.error.HTTPError as e:
            cls = _Retryable if e.code == 429 or e.code >= 500 else ConnectorError
            raise cls(f"НСПД ответил HTTP {e.code}") from None
        except Exception as e:
            is_cert = isinstance(e, ssl.SSLCertVerificationError) or \
                "CERTIFICATE_VERIFY_FAILED" in str(e)
            if is_cert and ctx.verify_mode != ssl.CERT_NONE:
                if os.environ.get("GRADO_NSPD_INSECURE") == "1":
                    _warn_insecure()
                    ctx = _ssl_context_unverified()
                    continue
                raise ConnectorError(_CERT_HELP) from None
            raise _Retryable(f"НСПД недоступен: {_short(e)}") from None
    raise ConnectorError("НСПД недоступен")


def normalize_cadastral(text_or_list):
    """Строка (через запятую/пробел/перевод строки) или список → (верные номера без повторов, отброшенное)."""
    if isinstance(text_or_list, str):
        parts = re.split(r"[,;\s]+", text_or_list)
    else:
        parts = [str(x) for x in text_or_list]
    good, bad = [], []
    for p in (x.strip() for x in parts):
        if not p:
            continue
        if CAD_RE.match(p):
            if p not in good:
                good.append(p)
        else:
            bad.append(p)
    return good, bad


def _search_features(data):
    """Объекты из ответа поиска: FeatureCollection на верхнем уровне или внутри data."""
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict) and "features" in inner:
            data = inner
        return [f for f in (data.get("features") or []) if isinstance(f, dict)]
    return []


def search_cadastral(numbers, transport=None, pause=0.5, sleep=time.sleep, errors=None, nogeom=None):
    """Участки по кадастровым номерам → нормализованные объекты (WGS84, свойства как у выгрузки по области).

    Один запрос на номер, строго по очереди, до 3 попыток на номер. Не найденные номера просто
    отсутствуют в результате; найденные без контура — в nogeom (номера), не молча; сбои порталa (после 3 попыток) складываются в errors как (номер, текст).
    """
    nums, _ = normalize_cadastral(numbers)
    if not nums:
        raise ConnectorError("нет верных кадастровых номеров")
    nums = nums[:SEARCH_MAX]
    get = transport or _http_get
    out, seen = [], set()
    for i, num in enumerate(nums):
        if i:
            sleep(pause)
        url = SEARCH_URL + "?" + urllib.parse.urlencode({"query": num, "thematicSearchId": 1})
        data = None
        for attempt in range(3):
            try:
                data = get(url)
                break
            except _Retryable as e:
                if attempt == 2:
                    if errors is not None:
                        errors.append((num, str(e)))
                else:
                    sleep(1.5 * (attempt + 1))
            except ConnectorError as e:
                if errors is not None:
                    errors.append((num, str(e)))
                break
        if data is None:
            continue
        raw = _search_features(data)
        flat = [_flatten_options(dict(f.get("properties") or {})) for f in raw]
        hit = [f for f, p in zip(raw, flat)
               if num in (p.get("opt_cad_num"), p.get("cad_num"), p.get("descr"))]
        if not hit and len(raw) == 1 and not any(
                p.get("opt_cad_num") or p.get("cad_num") for p in flat):
            hit = raw                     # поле номера не пришло, объект один — берём его
        for f in hit:
            if not f.get("geometry"):
                if nogeom is not None and num not in nogeom:
                    nogeom.append(num)
                continue
            f = dict(f)
            f["id"] = f.get("id") or num
            f["properties"] = dict(f.get("properties") or {})
            f["properties"].setdefault("opt_cad_num", num)
            for g in NspdCapture().fetch(payload={"features": [f]})["features"]:
                if g["grado_key"] not in seen:
                    seen.add(g["grado_key"])
                    g["grado_key"] = num
                    out.append(g)
    return out
