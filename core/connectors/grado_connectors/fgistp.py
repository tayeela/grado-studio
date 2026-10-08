"""Коннектор ФГИС ТП (Минэк, mnp.economy.gov.ru) — протокол v2 (JSP).

Прежний протокол (WFS 2.0.0 GetFeature на /geoserver/wfs) МЁРТВ: портал
отвечает «Service WFS is disabled». Живой протокол снят с работающего
вьюера geomnpn (viewapp/settings/Settings.js, проверено 2026-07-19):

- каталог документов: JSP/json_stp_list.jsp?fdate=0&tdate=0&sub=<код АТЕ>
  → {"stp_list": [{uin, stp_name, stp_extent}]}  (~27 000 документов при sub='')
- состав документа:   JSP/json_layers_stp_list.jsp?uin=...
  → {"layer_stp_list": [{classid, class_name, class_title, geom_type, stp_name}]}
- объекты слоя:       JSP/json_stp_layer_obj_list.jsp?uin=..&obj_code=<classid>
                        &geom_type=<100|010|001>&st_code=<1|2>&reg_code=0
  → GeoJSON FeatureCollection в EPSG:3857; атрибуты лежат ПРЯМО в feature
    (naim, tp_stat, reg_stat, globalid, number), поля properties НЕТ.

Авторизация НЕ нужна — но WAF портала режет не-браузерный User-Agent
(403 на «grado-studio/…»), поэтому запросы идут с браузерным UA. Прежняя
пометка «нужен браузерный мост с сессией» была следствием именно UA, а не
авторизации. CORS порталом не отдаётся — браузерной редакции путь закрыт,
импорт только через сервер (desktop).

Геометрия конвертируется в WGS84 ещё в коннекторе (merc_to_wgs84), чтобы
контракт make_result остался прежним (вниз по конвейеру всё ждёт WGS84).
"""

import json
import urllib.parse

from .contract import Connector, ConnectorError, make_result
from . import crs, netutil

DEFAULT_BASE = "https://mnp.economy.gov.ru"
APP_PATH = "/geo/geomnpn/viewapp"
LIST_PATH = APP_PATH + "/JSP/json_layers_stp_list.jsp"
CATALOG_PATH = APP_PATH + "/JSP/json_stp_list.jsp"
OBJECTS_PATH = APP_PATH + "/JSP/json_stp_layer_obj_list.jsp"

# WAF пропускает только браузерные UA (иначе 403 на всё, включая статику)
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

STATUS_NAMES = {"1": "существующий", "2": "планируемый"}
GEOM_TYPES = ("100", "010", "001")   # полигоны / линии / точки


def check_base_url(url):
    """https:// обязателен; http:// допустим только для локального хоста (тесты, отладка)."""
    p = urllib.parse.urlsplit(str(url))
    if p.scheme == "https" and p.hostname:
        return url
    if p.scheme == "http" and p.hostname in ("127.0.0.1", "localhost", "::1"):
        return url
    raise ConnectorError(
        f"base-url {url!r} отклонён: нужен https:// "
        "(http:// допустим только для 127.0.0.1/localhost)")


class FgistpConnector(Connector):
    name = "fgistp"
    source = "fgistp"

    def __init__(self, transport=None, base_url=DEFAULT_BASE):
        self.base_url = check_base_url(base_url).rstrip("/")
        self.transport = transport or self._http_get

    def _http_get(self, url):
        try:
            return netutil.request(url, headers={"User-Agent": BROWSER_UA}, timeout=120).content
        except ConnectorError as e:
            raise ConnectorError(f"ФГИС ТП недоступен: {e}") from None

    # ---------- URL-строители (отделены для тестов) ----------

    def catalog_url(self, sub=""):
        q = urllib.parse.urlencode({"fdate": 0, "tdate": 0, "sub": sub})
        return f"{self.base_url}{CATALOG_PATH}?{q}"

    def list_url(self, uin):
        q = urllib.parse.urlencode({"uin": uin, "page": 1, "start": 0, "limit": 500})
        return f"{self.base_url}{LIST_PATH}?{q}"

    def objects_url(self, uin, classid, geom_type="100", status="1"):
        if geom_type not in GEOM_TYPES:
            raise ConnectorError(f"неизвестный geom_type {geom_type!r}")
        q = urllib.parse.urlencode({
            "uin": uin, "obj_code": classid, "geom_type": geom_type,
            "st_code": status, "reg_code": 0,
        })
        return f"{self.base_url}{OBJECTS_PATH}?{q}"

    # ---------- операции ----------

    def catalog(self, sub=""):
        """Каталог документов терпланирования: [{uin, stp_name, stp_extent}].

        sub — код АТЕ для фильтра по территории; пусто = вся РФ (~27 000)."""
        data = json.loads(self.transport(self.catalog_url(sub)))
        return data.get("stp_list") or []

    def discover(self, uin):
        """Состав документа: список слоёв с classid/geom_type."""
        data = json.loads(self.transport(self.list_url(uin)))
        layers = data.get("layer_stp_list") or []
        if not layers:
            raise ConnectorError(f"документ {uin} не найден или не содержит слоёв")
        return layers

    def _fetch_layer(self, uin, layer, status):
        raw = self.transport(self.objects_url(
            uin, layer["classid"], layer.get("geom_type", "100"), status))
        try:
            gj = json.loads(raw)
        except Exception:
            raise ConnectorError(
                f"слой {layer['classid']}: портал вернул не-JSON") from None
        out = []
        for i, f in enumerate(gj.get("features") or []):
            geom = f.get("geometry")
            if not geom:
                continue
            # атрибуты у портала лежат в самом feature — собираем properties
            props = {k: v for k, v in f.items()
                     if k not in ("type", "geometry", "properties") and v not in (None, "")}
            props["class_name"] = layer.get("class_name")
            props["class_title"] = layer.get("class_title")
            props["status_name"] = STATUS_NAMES.get(str(status), "—")
            props["uin"] = uin
            out.append({
                "type": "Feature",
                # globalid стабилен между выгрузками; фолбэк — классид+статус+индекс
                "grado_key": str(f.get("globalid") or f.get("id")
                                 or f"{layer['classid']}:{status}:{i}"),
                "geometry": crs.transform_geom(geom, crs.merc_to_wgs84),
                "properties": props,
            })
        return out

    def fetch(self, uin, classids=None, geom_type=None, statuses=("1", "2"),
              layers=None):
        """Выгрузка слоёв документа (существующие И планируемые по умолчанию).

        classids=None — все слои; geom_type=None — все типы геометрии."""
        layers = layers if layers is not None else self.discover(uin)
        selected = [l for l in layers
                    if (geom_type is None or l.get("geom_type") == geom_type)
                    and (classids is None or l["classid"] in classids)]
        notes, features = [], []
        if not selected:
            notes.append("подходящих слоёв в документе нет")
        for layer in selected:
            got = []
            for status in statuses:
                got.extend(self._fetch_layer(uin, layer, status))
            if not got:
                notes.append(f"{layer['classid']} ({layer.get('class_name')}): 0 объектов")
            features.extend(got)
        doc_name = (layers[0].get("stp_name") if layers else None) or uin
        return make_result(
            features,
            params={"uin": uin,
                    "classids": sorted(classids) if classids else None,
                    "geom_type": geom_type, "statuses": list(statuses)},
            source_doc=f"ФГИС ТП, УИН {uin} ({doc_name})",
            notes=notes)
