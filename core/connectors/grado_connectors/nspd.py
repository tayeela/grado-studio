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

Релей (когда НСПД недоступен с места запуска, например из облака): задайте
GRADO_NSPD_BASE=https://<домен релея> и GRADO_NSPD_RELAY_TOKEN=<токен> — запросы
пойдут на релей в РФ, а он — на nspd.gov.ru. Токен уходит только на релей.
Описание — tools/nspd_relay/README.md.
"""

import hashlib
import json
import os
import re
import ssl
import time
import urllib.parse
from pathlib import Path

from . import crs, netutil
from .contract import Connector, ConnectorError, make_result, with_acquisition


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

NSPD_BASE = "https://nspd.gov.ru"
INTERSECTS_PATH = "/api/geoportal/v1/intersects?typeIntersect=fullObject"
INTERSECTS_URL = NSPD_BASE + INTERSECTS_PATH      # адрес по умолчанию (без релея)
RELAY_TOKEN_HEADER = "X-Grado-Relay-Token"


def _base_url():
    """Базовый адрес геопортала: GRADO_NSPD_BASE (релей) или сам НСПД."""
    raw = (os.environ.get("GRADO_NSPD_BASE") or "").strip().rstrip("/")
    if not raw:
        return NSPD_BASE
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query:
        raise ConnectorError("GRADO_NSPD_BASE задан неверно: нужен адрес вида https://host (только https, без пути)")
    return raw


def _relay_headers(base):
    """Токен релея — только если базовый адрес не сам НСПД (токен не должен уйти на nspd.gov.ru)."""
    token = (os.environ.get("GRADO_NSPD_RELAY_TOKEN") or "").strip()
    if token and base != NSPD_BASE:
        return {RELAY_TOKEN_HEADER: token}
    return {}


def _intersects_url():
    return _base_url() + INTERSECTS_PATH

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
    "НУЦ Минцифры не установлен. Скачайте russian_trusted_root_ca.cer и "
    "russian_trusted_sub_ca.cer с gu-st.ru/content/Other/doc/ и положите "
    "их в папку ~/.grado2/ca/ (либо укажите файл в переменной "
    "GRADO_NSPD_CA). Подойдут .cer, .crt и .pem.")


def _extra_ca_files():
    """Дополнительные корни: GRADO_NSPD_CA, затем ~/.grado2/ca/, затем certs/ в репозитории."""
    files = []
    env = os.environ.get("GRADO_NSPD_CA")
    if env:
        files.append(Path(env).expanduser())
    for d in (Path.home() / ".grado2" / "ca", Path(__file__).parent / "certs"):
        try:
            files.extend(sorted(p for p in d.iterdir()
                                if p.suffix.lower() in (".crt", ".pem", ".cer")))
        except OSError:
            pass
    return files


def _extra_ca_pem():
    """Корни из _extra_ca_files() в PEM; битые и нечитаемые файлы пропускаются молча."""
    out = []
    for f in _extra_ca_files():
        try:
            raw = f.read_bytes()
            pem = raw.decode("ascii", "ignore") if b"-----BEGIN" in raw[:4096] \
                else ssl.DER_cert_to_PEM_cert(raw)          # .cer от Минцифры — обычно DER
            ssl.create_default_context().load_verify_locations(cadata=pem)   # проверка: файл читается как сертификат
            out.append(pem)
        except (ssl.SSLError, OSError, ValueError):
            pass
    return out


def _ssl_context():
    # nspd.gov.ru подписан НУЦ Минцифры, которого нет в certifi: к корням certifi добавляются его корни из файлов.
    return netutil.ssl_context(_extra_ca_pem())


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
        headers = {"User-Agent": _UA, "Content-Type": "application/json",
                   "Referer": "https://nspd.gov.ru/map"}
        headers.update(_relay_headers(_base_url()))
        try:
            return _request(url, method="POST", content=json.dumps(body).encode("utf-8"),
                            headers=headers, timeout=45).json()
        except netutil.HttpError as e:
            try:
                detail = _short(json.loads(e.body.decode("utf-8")).get("message", ""))
            except Exception:
                detail = ""
            raise ConnectorError(f"НСПД ответил HTTP {e.code}" + (f": {detail}" if detail else "")) from None
        except netutil.NetError as e:
            raise ConnectorError(f"НСПД недоступен: {_short(e)}") from None

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
                    _intersects_url(),
                    {"geom": geom, "categories": [{"id": int(cid)}]})
            except ConnectorError as e:
                notes.append(f"{NSPD_CATEGORIES.get(int(cid), cid)}: {e}")
                continue
            if not isinstance(data, dict) or not isinstance(data.get("features"), list):
                raise ConnectorError("НСПД вернул неизвестную схему вместо списка объектов")
            raw.extend(data["features"])
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
        return with_acquisition(result, bbox, [str(c) for c in categories])


# --- поиск участка по кадастровому номеру ------------------------------------
# GET /api/geoportal/v2/search/geoportal?query=<номер>&thematicSearchId=1 —
# тот же вызов, что делает строка поиска геопортала (проверен 26.09.2026).
# Ответ — GeoJSON EPSG:3857 с геометрией и атрибутами; дальше путь тот же,
# что у выгрузки по области (NspdCapture): options → opt_*, координаты → WGS84.

SEARCH_PATH = "/api/geoportal/v2/search/geoportal"
SEARCH_URL = NSPD_BASE + SEARCH_PATH              # адрес по умолчанию (без релея)
CAD_RE = re.compile(r"^[0-9]{2}:[0-9]{2}:[0-9]{6,7}:[0-9]+$")
SEARCH_MAX = 20


def _request(url, **kw):
    """Запрос к НСПД по общему правилу netutil (повторы на 429, 5xx и обрыв сети). Сертификат не прошёл проверку —
    понятная подсказка про корни Минцифры. Проверка сертификата не отключается никогда (железное правило 4)."""
    try:
        return netutil.request(url, context=_ssl_context(), **kw)
    except netutil.NetError as e:
        if not e.cert:
            raise
        raise ConnectorError(_CERT_HELP) from None


def _http_get(url):
    headers = {"User-Agent": _UA, "Accept": "application/json",
               "Referer": "https://nspd.gov.ru/map?thematic=PKK",
               "Origin": "https://nspd.gov.ru"}
    headers.update(_relay_headers(_base_url()))
    try:
        return _request(url, headers=headers, timeout=30).json()
    except netutil.HttpError as e:
        raise ConnectorError(f"НСПД ответил HTTP {e.code}") from None
    except netutil.NetError as e:
        raise ConnectorError(f"НСПД недоступен: {_short(e)}") from None


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

    Один запрос на номер, строго по очереди, до 3 попыток на номер (netutil). Не найденные номера просто
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
        url = _base_url() + SEARCH_PATH + "?" + urllib.parse.urlencode({"query": num, "thematicSearchId": 1})
        data = None
        try:                                  # повторы — в netutil (общее правило порталов)
            data = get(url)
        except ConnectorError as e:
            if errors is not None:
                errors.append((num, str(e)))
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
