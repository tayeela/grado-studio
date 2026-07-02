"""Коннектор ФГИС ТП (Минэк, mnp.economy.gov.ru).

Протокол снят с работающего GRADO-моста (browser ext v2):
- discover: /geo/geomnpn/viewapp/JSP/json_layers_stp_list.jsp?uin=...
  → {"layer_stp_list": [{classid, class_name, class_title, geom_type, stp_name}]}
- fetch: /geoserver/wfs, WFS 2.0.0 GetFeature, outputFormat=application/json,
  srsName=EPSG:4326, CQL: uin + mt_classid + ((kit is null) OR (kit='irrelevant'))
  + опционально mt_status ('1' существующие / '2' планируемые).

Портал отдаёт данные только в авторизованной браузерной сессии (снаружи 403),
поэтому транспорт заменяемый: в продукте — браузерный мост/WebView сервиса
данных, в тестах — фикстуры. UIN фиксируется параметром вызова — гонка UIN
(авто-перехват перетирал выбранный документ) исключена конструктивно.
"""

import json
import urllib.parse
import urllib.request

from .contract import Connector, ConnectorError, make_result

DEFAULT_BASE = "https://mnp.economy.gov.ru"
LIST_PATH = "/geo/geomnpn/viewapp/JSP/json_layers_stp_list.jsp"
WFS_PATH = "/geoserver/wfs"

# pol подтверждён рабочим плагином; lin/pnt — по той же схеме (в плагине
# помечены как предположительные)
TYPENAMES = {
    "100": "min_eco_test:geo_db_data_fgistp_pol",
    "010": "min_eco_test:geo_db_data_fgistp_lin",
    "001": "min_eco_test:geo_db_data_fgistp_pnt",
}

STATUS_NAMES = {1: "существующая", 2: "планируемая"}


class FgistpConnector(Connector):
    name = "fgistp"
    source = "fgistp"

    def __init__(self, transport=None, base_url=DEFAULT_BASE):
        self.base_url = base_url.rstrip("/")
        self.transport = transport or self._http_get

    def _http_get(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "grado-studio/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception as e:
            raise ConnectorError(
                f"ФГИС ТП недоступен напрямую ({e}); нужен транспорт браузерного "
                "моста с сессией портала") from None

    def list_url(self, uin):
        q = urllib.parse.urlencode({"uin": uin, "page": 1, "start": 0, "limit": 500})
        return f"{self.base_url}{LIST_PATH}?{q}"

    def wfs_url(self, uin, classid, geom_type="100", status=None):
        typename = TYPENAMES.get(geom_type)
        if typename is None:
            raise ConnectorError(f"неизвестный geom_type {geom_type!r}")
        cql = (f"uin='{uin}' AND mt_classid='{classid}'"
               " AND ((kit is null) OR (kit='irrelevant'))")
        if status in ("1", "2"):
            cql += f" AND mt_status='{status}'"
        q = urllib.parse.urlencode({
            "service": "wfs", "version": "2.0.0", "request": "GetFeature",
            "typeName": typename, "outputFormat": "application/json",
            "srsName": "EPSG:4326", "CQL_FILTER": cql,
        })
        return f"{self.base_url}{WFS_PATH}?{q}"

    def discover(self, uin):
        """Состав документа: список слоёв с classid/geom_type."""
        data = json.loads(self.transport(self.list_url(uin)))
        layers = data.get("layer_stp_list") or []
        if not layers:
            raise ConnectorError(f"документ {uin} не найден или не содержит слоёв")
        return layers

    def fetch(self, uin, classids=None, geom_type="100", status=None, layers=None):
        """Выгрузка слоёв документа. uin фиксирован на весь вызов."""
        layers = layers if layers is not None else self.discover(uin)
        selected = [l for l in layers
                    if l.get("geom_type") == geom_type
                    and (classids is None or l["classid"] in classids)]
        notes = []
        if not selected:
            notes.append(f"в документе нет слоёв geom_type={geom_type} "
                         "(ЗОУИТ и линейные объекты — в других таблицах WFS)")
        features = []
        for layer in selected:
            raw = self.transport(self.wfs_url(uin, layer["classid"], geom_type, status))
            gj = json.loads(raw)
            got = gj.get("features") or []
            if not got:
                notes.append(f"{layer['classid']} ({layer.get('class_name')}): 0 объектов")
            for i, f in enumerate(got):
                props = f.setdefault("properties", {})
                props["class_name"] = layer.get("class_name")
                props["class_title"] = layer.get("class_title")
                props["status_name"] = STATUS_NAMES.get(props.get("mt_status"), "—")
                props["uin"] = uin
                f["grado_key"] = f.get("id") or f"{layer['classid']}:{i}"
                features.append(f)
        doc_name = (layers[0].get("stp_name") if layers else None) or uin
        return make_result(
            features,
            params={"uin": uin, "geom_type": geom_type,
                    "classids": sorted(classids) if classids else None,
                    "status": status},
            source_doc=f"ФГИС ТП, УИН {uin} ({doc_name})",
            notes=notes)
