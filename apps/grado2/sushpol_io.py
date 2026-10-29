"""ГРАДО 2 · единое содержание презентации сущпола для интерфейса и MCP.

Строит 14 видов и продолжения на существующей PrintSpec; поля имеют происхождение,
неполнота не скрывается. Компоновка — mytishchi_io, геометрия — Shapely/МСК.
"""
from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

from shapely import union_all
from shapely.geometry import Point, box, mapping, shape

import preparation as P
import mytishchi_io as M
import sushpol_rules as R
from sushpol_accessibility import clinic_zones, education_zones

TITLES=dict(zip(P.KINDS,["Существующее положение","Расположение рассматриваемой территории в структуре города и округа",
 "Ортофотоплан района","Ортофотоплан с границами подготовки проекта планировки территории",
 "Существующее состояние и использование территории","Характеристика земельно-правовых и имущественных отношений",
 "Земельные участки и объекты капитального строительства","Градостроительные ограничения",
 "Материалы фотофиксации","Фрагмент Генерального плана города Москвы","Правила землепользования и застройки",
 "Утверждённая и разрабатываемая градостроительная документация","Объекты образования (существующее положение)",
 "Объекты здравоохранения (существующее положение)"]))
BASE=["egko.green","egko.water","egko.roads","egko.paths","egko.buildings","egko.place_labels","egko.addresses"]
FALLBACK=["yandex.green","yandex.water","yandex.hd_roads","yandex.buildings","yandex.transport"]
RESTRICTIONS=["gisogd.red_lines","gisogd.szz","gisogd.vodookhr","gisogd.zouit","gisogd.airfield","gisogd.okn","nspd.zouit"]
GP=["gisogd.func_zones","gisogd.func_zones_tinao"]
DOCS=["gisogd.ppt","gisogd.pmt","gisogd.gpzu"]
DEPENDENCIES={
 "title":["gisogd.admin"],"location":["gisogd.admin"],"district_ortho":["gisogd.admin"],"territory_ortho":[],
 "existing_use":["nspd.parcels","nspd.buildings","osm.landuse","gisogd.red_lines"],
 "land_rights":["nspd.parcels"],"parcels_oks":["nspd.parcels","nspd.buildings"],"restrictions":RESTRICTIONS,
 "photos":["osm.roads"],"general_plan":GP,"pzz":["gisogd.pzz_zones","gisogd.pzz_sub"],
 "planning_docs":DOCS,"education":["osm.social","gisogd.admin"],"healthcare":["osm.social"]}
ALL_SOURCES=list(dict.fromkeys(["gisogd.admin",*BASE,*FALLBACK,*[k for keys in DEPENDENCIES.values() for k in keys]]))
DEFAULTS={"egko.green":("#cfe4b3","#9cbf80",0),"egko.water":("#bfe0f5","#78aee6",.8),
 "egko.roads":("#ffffff","#9e9e9e",.7),"egko.paths":("#ffffff","#9e9e9e",.4),
 "egko.buildings":("#d8d3c9","#8f897f",.5),"nspd.buildings":("#cbc6be","#4d4d4d",.8),
 "nspd.parcels":(None,"#7d8288",.8),"gisogd.pzz_zones":(None,"#6a3d9a",1.4),
 "gisogd.pzz_sub":(None,"#8a5a00",.6)}
GP_LIB=json.loads((R.ROOT/"core/render/grado_render/styles/moscow_genplan.json").read_text())
GP_STYLES={str(v.get("gp_zone") or v.get("title")).lower():v for v in GP_LIB["styles"].values()}
LGR_LIB=json.loads((R.ROOT/"core/render/grado_render/styles/moscow_lgr.json").read_text())
LGR={int(v["lgr_code"]):v for v in LGR_LIB["styles"].values() if v.get("lgr_code") is not None}


def feature_key(f):
    p=f.get("properties") or {}
    return str(p.get("Кадастровый номер") or p.get("_key") or f.get("id") or P.digest(f))


def features(project,key):
    return (((project.get("data") or {}).get(key) or {}).get("fc") or {}).get("features") or []


def _value(v):
    return v is not None and (not isinstance(v,str) or bool(v.strip()))


def _sort_key(text):
    return tuple((0,int(x)) if x.isdigit() else (1,x) for x in re.split(r"(\d+)",str(text)))


def frame_geometry(extent,rect):
    minx,miny,maxx,maxy=extent.bounds
    cx,cy=(minx+maxx)/2,(miny+maxy)/2
    need=max((maxx-minx)*1100/rect[2],(maxy-miny)*1100/rect[3],1)
    scales=[500,1000,2000,5000,6000,10000,20000,50000,100000,200000,500000,1000000,2000000,5000000]
    scale=next((s for s in scales if s>=need),math.ceil(need/100000)*100000)
    center=list(P.to_wgs(Point(cx,cy)).coords)[0]
    region=P.to_wgs(box(cx-rect[2]*scale/2000,cy-rect[3]*scale/2000,cx+rect[2]*scale/2000,cy+rect[3]*scale/2000))
    return center,scale,region


def fund_share(value,fraction):
    """Строго числовой фонд/диапазон в тыс. м²; текстовые условия не превращаются в число."""
    if isinstance(value,bool) or not math.isfinite(fraction) or not 0<=fraction<=1:return None
    text=str(value).strip().replace(",",".").replace("\u00a0","")
    number=r"\d+(?:\.\d+)?"
    match=re.fullmatch(r"("+number+r")(?:\s*[-–—]\s*("+number+r"))?",text)
    if not match:return None
    low=float(match[1]);high=float(match[2]) if match[2] is not None else None
    if not math.isfinite(low) or high is not None and (not math.isfinite(high) or high<low):return None
    result=f"{low*fraction:.3f}".rstrip("0").rstrip(".")
    if high is not None:result+="–"+f"{high*fraction:.3f}".rstrip("0").rstrip(".")+" (диапазон)"
    return result


def latest_coverage(state,key,region):
    receipts=[v for v in (state.get("requests") or {}).values() if v.get("sourceKey")==key]
    if not receipts:return False
    receipt=receipts[-1]
    return receipt.get("state") in ("received","empty") and P.coverage(mapping(region),receipt.get("checkedParts") or [],receipt.get("expectedSublayers") or [key])["complete"]


ISSUE_TEXT={"unknown_outcome":"Получение источника ещё не подтверждено","partial_coverage":"Источник получен не для всей рамки карты",
 "partial_attributes":"В источнике неполные атрибуты","source_unavailable":"Источник недоступен","missing_field":"Не хватает сведений",
 "invalid_geometry":"Проверьте геометрию объекта","manual_conflict":"Ручное уточнение требует повторного подтверждения",
 "unknown_rule":"Не определено правило для этой территории","needs_check":"Нужна проверка листа","missing_source":"Не хватает исходных данных",
 "stale_dependency":"После изменений нужна повторная сборка"}
FIELD_TITLES={"parcel.address":"Адрес участка","parcel.area_m2":"Площадь участка","parcel.cadNumber":"Кадастровый номер",
 "parcel.rightType":"Вид права","parcel.holder":"Правообладатель","parcel.rightDocument":"Правоустанавливающий документ",
 "parcel.validity":"Период действия права","parcel.purpose":"Цель использования","parcel.key":"Идентификатор участка",
 "szz.title":"Название объекта СЗЗ","szz.address":"Адрес объекта СЗЗ","szz.document_size":"Решение РПН или размер СЗЗ",
 "useClass":"Класс использования территории","basemap":"Спутниковый снимок","labels":"Подписи на листе"}


class Content:
    def __init__(self,project):
        self.project=project
        self.territory=P.project_territory(project)
        self.msk=P.to_msk(self.territory)
        self.album=project.setdefault("album",{"meta":{},"sheets":[]})
        self.meta=self.album.setdefault("meta",{})
        self.state=self.meta.setdefault("sushpolPreparation",P.new_state())
        if self.state.get("schemaVersion")!=P.SCHEMA:raise P.PreparationError("unsupported_schema","Неизвестная схема подготовки")
        self.issues=[]
        self.refs=P.revisions(project)
        self.parcels=[]
        for f in features(project,"nspd.parcels"):
            try:
                if P.to_msk(P.polygon(f.get("geometry"))).intersection(self.msk).area>1e-6:self.parcels.append(f)
            except P.PreparationError:self.issue("land_rights","invalid_geometry","nspd.parcels",feature_key(f))
        for f in self.parcels:
            p=f.get("properties") or {}
            if not (p.get("Кадастровый номер") or p.get("_key") or f.get("id")):
                self.issue("land_rights","missing_field","nspd.parcels",feature_key(f),"parcel.key")
        self.parcels=sorted({feature_key(f):f for f in self.parcels}.values(),key=lambda f:_sort_key(feature_key(f)))
        self.numbering=self.state.setdefault("numbering",{})
        no=max(self.numbering.values(),default=0)
        for f in self.parcels:
            key=feature_key(f)
            if key not in self.numbering:no+=1;self.numbering[key]=no
        self.adm=features(project,"gisogd.admin")
        self.okrugs=[];self.districts=[]
        for f in self.adm:
            try:
                if P.to_msk(P.polygon(f.get("geometry"))).intersection(self.msk).area>1e-6:
                    if (f.get("properties") or {}).get("Уровень")=="округ":self.okrugs.append(f)
                    elif (f.get("properties") or {}).get("Уровень")=="район":self.districts.append(f)
            except P.PreparationError:continue

    def issue(self,kind,code,source=None,key=None,field=None,message=None):
        source_title=((self.project.get("data") or {}).get(source) or {}).get("title") or next((v.get("title") for v in self.project.get("layers",[]) if v.get("key")==source),"")
        item={"sheetId":self.state["sheets"][kind]["sheetId"],"kind":kind,"reasonCode":code,
              "sourceKey":source,"sourceTitle":source_title,"objectKey":key,"field":field,"fieldTitle":FIELD_TITLES.get(field,""),
              "message":message or ISSUE_TEXT.get(code,"Нужна проверка исходных сведений")}
        if item not in self.issues:self.issues.append(item)

    def field(self,kind,f,name,source,raw,optional=False):
        key=feature_key(f);rev=P.digest(f)
        for override in self.state.get("overrides",[]):
            scope=override.get("scope") or {}
            if scope.get("sourceKey",source)==source and scope.get("objectKey")==key and scope.get("field")==name:
                if override.get("dependencyRevision")==rev and override.get("state")=="accepted":return override.get("value")
                self.issue(kind,"manual_conflict",source,key,name)
        if name.endswith("area_m2") and _value(raw):
            try:
                raw=float(str(raw).replace(",","."))
                if not math.isfinite(raw) or raw<=0:raw=None
            except (TypeError,ValueError):raw=None
        if _value(raw):return raw
        for d in self.state.get("decisions",[]):
            scope=d.get("scope") or {}
            if scope.get("sourceKey",source)==source and scope.get("objectKey")==key and scope.get("field")==name and d.get("dependencyRevision")==rev and d.get("basis"):
                if d.get("code")=="not_applicable":return "Не применимо"
                if d.get("code")=="allow_missing":return "Нет сведений"
        if optional:return ""
        self.issue(kind,"missing_field",source,key,name,"Дополнить поле внутри ГРАДО")
        return "Требует уточнения"

    def require(self,kind,keys,region=None):
        receipts=list((self.state.get("requests") or {}).values())
        for key in keys:
            found=[r for r in receipts if r.get("sourceKey")==key]
            if not found:
                self.issue(kind,"unknown_outcome",key,message="Нет подтверждения получения источника")
            elif region is not None and not latest_coverage(self.state,key,region):
                deferred=next((v for v in self.state.get("deferredSources",[]) if v.get("kind")==kind and v.get("sourceKey")==key),None)
                self.issue(kind,"budget_exceeded" if deferred else found[-1].get("reasonCode") or "partial_coverage",key,
                           message="Рамка района превышает предел загрузки источника; крупные листы получены отдельно" if deferred else None)
            elif found[-1].get("state") not in ("received","empty"):
                self.issue(kind,found[-1].get("reasonCode") or "partial_coverage",key)

    def tinao(self,f):
        try:p=shape(f["geometry"]).representative_point()
        except (KeyError,ValueError):return False
        return any(re.search(r"^(?:ТАО|НАО)$|Новомосковск|Троицк",str((a.get("properties") or {}).get("Наименование") or (a.get("properties") or {}).get("Округ") or ""),re.IGNORECASE)
                   and shape(a["geometry"]).covers(p) for a in self.okrugs)

    def map(self,kind,role,keys,extent=None,satellite=False):
        rect=M.BLOCKS[kind][role]["rect"]
        extent=extent if extent is not None else self.msk
        if extent.is_empty:extent=self.msk
        center,scale,region=frame_geometry(extent,rect)
        if keys[:len(BASE)]==BASE and not all(latest_coverage(self.state,k,region) for k in BASE) and all(latest_coverage(self.state,k,region) for k in FALLBACK):
            keys=FALLBACK+keys[len(BASE):]
        self.require(kind,[k for k in keys if k!="gisogd.admin"],region)
        layers=[];legend=[]
        ordered_keys=list(dict.fromkeys(keys))
        if kind=="existing_use" and "osm.landuse" in ordered_keys and "nspd.parcels" in ordered_keys:
            # Класс по ВРИ ЕГРН подтверждён сильнее общей территории OSM: рисуется поверх неё.
            ordered_keys.remove("osm.landuse");ordered_keys.insert(ordered_keys.index("nspd.parcels"),"osm.landuse")
        for key in ordered_keys:
            rows=[]
            for f in features(self.project,key):
                try:
                    g=shape(f["geometry"])
                    if g.is_empty or not g.is_valid or not g.intersects(region):continue
                except (ValueError,KeyError,TypeError):
                    self.issue(kind,"invalid_geometry",key,feature_key(f));continue
                p=f.get("properties") or {}
                fill,stroke,width=DEFAULTS.get(key,(None,"#555555",.8))
                if key.startswith("yandex."):
                    alias={"yandex.green":"egko.green","yandex.water":"egko.water","yandex.hd_roads":"egko.roads","yandex.buildings":"egko.buildings"}.get(key)
                    fill,stroke,width=DEFAULTS.get(alias,(None,"#555555",.8))
                label=p.get("Название") or p.get("Наименование")
                out={"g":f["geometry"],"fill":fill,"stroke":stroke,"w":width,"a":1 if fill else 0,
                     "label":str(label) if label else None,"ls":3.0,"lf":"sans-bold","lh":.4,"lcol":"#141414",
                     "sourceObjectKey":feature_key(f)}
                if key=="nspd.parcels":
                    out.update(label=str(self.numbering.get(feature_key(f),"")),a=0)
                    if kind=="existing_use":
                        cls=R.land_class(p,self.tinao(f))
                        if cls is None:
                            # Фактическое использование OSM — отдельное подтверждённое происхождение, не право/ВРИ.
                            pt=g.representative_point()
                            for osm in features(self.project,"osm.landuse"):
                                try:
                                    if shape(osm["geometry"]).covers(pt):cls=R.osm_class(osm.get("properties") or {},self.tinao(f))
                                except (ValueError,KeyError):continue
                                if cls is not None:break
                        if cls is None:self.issue(kind,"missing_field",key,feature_key(f),"useClass")
                        else:
                            title,color=R.ZONES[cls];out.update(fill=color,a=1)
                            if title not in legend:legend.append(title)
                elif key=="osm.landuse":
                    cls=R.osm_class(p,self.tinao(f))
                    if cls in R.ZONES:
                        title,color=R.ZONES[cls];out.update(fill=color,a=1,label=None)
                        if title not in legend:legend.append(title)
                elif key in GP:
                    title=str(p.get("naimfunkzony") or p.get("Вид зоны") or p.get("name") or "")
                    idx=str(p.get("fztip") or p.get("fz_type") or "")
                    palette=GP_STYLES.get(title.lower()) or GP_STYLES.get(str(GP_LIB["fz_code"].get(idx,"")).lower())
                    if palette:out.update(fill=palette["fill"],stroke=palette.get("stroke"),a=1)
                    out["label"]="\n".join(str(v) for v in (p.get("n") or p.get("number_fz"),idx) if v)
                    if title and title not in legend:legend.append(title)
                elif key=="gisogd.pzz_zones":out["label"]=str(p.get("Номер зоны") or p.get("Индекс") or "")
                elif key=="gisogd.pzz_sub":out["label"]=str(p.get("Номер подзоны") or "")
                elif key in RESTRICTIONS:
                    title=str(p.get("Вид зоны") or p.get("Наименование") or p.get("Наименование зоны") or key)
                    code=R.RULES["ZOUIT_LGR"].get(title)
                    style=LGR.get(code) or {}
                    stroke=style.get("stroke") or "#000000"
                    if key=="gisogd.szz":stroke="#000000"
                    out.update(stroke=stroke,fill=stroke,a=0,h=True,lt=p.get("_lt"),miss=p.get("_miss"),label=None)
                    if title not in legend:legend.append(title)
                rows.append(out)
            if rows:layers.append({"key":key,"title":((self.project.get("data") or {}).get(key) or {}).get("title",key),"features":rows})
        extra={}
        if kind in ("district_ortho","territory_ortho"):
            west,south,east,north=self.territory.bounds
            up=(region.bounds[3]-north)*110540/(scale/1000)>=35
            strip=box(west,north-(north-south)*.3,east,north) if up else box(west,south,east,south+(north-south)*.3)
            edge=self.territory.intersection(strip)
            target=(edge if not edge.is_empty else self.territory).representative_point()
            area=f"{self.msk.area/10000:.2f}".replace(".",",")
            layers.append({"key":"territory-callout","title":"Выноска территории","features":[{
                "g":{"type":"Point","coordinates":[target.x,north if up else south]},"nodot":True,"lead":[target.x,target.y],
                "label":f"Проектируемая территория – {area} га","ls":3.4,"lf":"sans-bold","lcol":"#111111",
                "lbox":R.RULES["C_TERR"],"lboxW":.7,"lboxAlpha":1,"leadSolid":True,"ldy":-22 if up else 16}]})
            if kind=="district_ortho" and self.districts:
                extra["distMask"]={"alpha":.45,"geometry":mapping(union_all([shape(f["geometry"]) for f in self.districts]))}
        return {"role":role,"sheet":{"size":"PA3","center":center,"scale":scale,"layers":layers,**extra,
                "territory":mapping(self.territory),"terrStyle":{"stroke":R.RULES["C_TERR"],"width":R.RULES["C_TW"],"dash":[R.RULES["C_TW"],R.RULES["C_TW"]]},
                "basemap":"sat" if satellite else None,"legend":[],"tep":[],"labelFont":"montserrat"},"legend":legend}

    def land_rows(self):
        rows=[];cards=[]
        for f in self.parcels:
            p=f.get("properties") or {};key=feature_key(f);num=self.numbering[key]
            value=lambda name,raw,optional=False:self.field("land_rights",f,name,"nspd.parcels",raw,optional)
            ar=p.get("Площадь уточнённая, м²") or p.get("Площадь участка, м²")
            vals=[str(num),value("parcel.address",p.get("Адрес")),value("parcel.area_m2",ar),
                  value("parcel.cadNumber",p.get("Кадастровый номер")),value("parcel.rightType",p.get("Вид права")),
                  value("parcel.holder",None),value("parcel.rightDocument",None),value("parcel.validity",None),
                  value("parcel.purpose",p.get("ВРИ")),value("parcel.notes",None,True)]
            rows.append({"key":key,"values":[str(v) for v in vals]})
            linked=[];candidates=[]
            for obj in features(self.project,"nspd.buildings"):
                okey=feature_key(obj)
                try:
                    if not shape(obj["geometry"]).intersects(shape(f["geometry"])):continue
                except (ValueError,KeyError):continue
                confirmed=any(d.get("code")=="confirm_relation" and (d.get("scope") or {}).get("objectKey")==okey and
                   (d.get("value")==key or isinstance(d.get("value"),list) and key in d["value"]) and
                   d.get("dependencyRevision")==P.digest(obj) and d.get("basis") for d in self.state.get("decisions",[]))
                if confirmed:linked.append(obj)
                else:candidates.append(obj)
            if candidates:self.issue("parcels_oks","manual_conflict","nspd.buildings",key,"oks.parcelKey","Подтвердить связь ОКС и ЗУ; пересечения недостаточно")
            building_receipts=[r for r in (self.state.get("requests") or {}).values() if r.get("sourceKey")=="nspd.buildings"]
            confirmed_source=bool(building_receipts and building_receipts[-1].get("state") in ("received","empty"))
            count=str(len(linked)) if not candidates and confirmed_source else "Требует подтверждения"
            areas=[(o.get("properties") or {}).get("Площадь, м²") for o in linked]
            total=sum(areas) if all(isinstance(a,(int,float)) and math.isfinite(a) and a>=0 for a in areas) and not candidates and confirmed_source else None
            if total is None:self.issue("parcels_oks","missing_field","nspd.buildings",key,"card.oksArea_m2")
            cards.append({"key":key,"text":f"{num}. {vals[3]}\nВид права: {vals[4]}\nПериод: {vals[7]}\nПлощадь ЗУ, м²: {vals[2]}\nОКС: {count}\nПлощадь ОКС, м²: {total if total is not None else 'Требует уточнения'}"})
        return rows,cards

    def metric_value(self,key,group,info):
        field=("metrics." if group=="existingMetrics" else "demolitionMetrics.")+key
        revision=P.digest(self.project.get("territory"));raw=info.get("value") if info.get("basis") else None
        for override in self.state.get("overrides",[]):
            scope=override.get("scope") or {}
            if scope.get("objectKey")=="project.metrics" and scope.get("field")==field:
                if override.get("dependencyRevision")==revision and override.get("basis"):raw=override.get("value")
                else:self.issue("existing_use","manual_conflict",field=field)
        try:
            if isinstance(raw,bool):raise ValueError()
            value=float(raw)
            if not math.isfinite(value) or value<0 or key=="residentialRatio" and value>100 or key=="jobs" and not value.is_integer():raise ValueError()
            return int(value) if value.is_integer() else value
        except (ValueError,TypeError,OverflowError):pass
        for decision in self.state.get("decisions",[]):
            scope=decision.get("scope") or {}
            if scope.get("objectKey")=="project.metrics" and scope.get("field")==field and decision.get("dependencyRevision")==revision and decision.get("basis"):
                if decision.get("code")=="not_applicable":return "Не применимо"
                if decision.get("code")=="allow_missing":return "Нет сведений"
        self.issue("existing_use","missing_field",None,"project.metrics",field,"Нужен показатель с основанием либо явное решение по этому полю")
        return None

    def metric_rows(self):
        # СПП/рабочие места не выводятся из площади ЕГРН или этажности по умолчанию.
        metrics=self.meta.get("existingMetrics") or {}
        specs=[("territoryArea","Площадь территории","га",round(self.msk.area/10000,3)),
               ("residentialRatio","Соотношение жилой/нежилой застройки","%",None),
               ("spp","СПП всего, в том числе нежилых зданий","тыс. м²",None),
               ("publicSpp","Общественные объекты","тыс. м²",None),
               ("industrialSpp","Производственные/коммунальные объекты","тыс. м²",None),
               ("mixedSpp","Объекты смешанного назначения","тыс. м²",None),
               ("nonResidentialAboveGround","Нежилая наземная площадь","тыс. м²",None),
               ("jobs","Рабочие места","мест",None)]
        rows=[]
        for i,(key,title,unit,calculated) in enumerate(specs,1):
            info=metrics.get(key) or {}
            v=calculated if calculated is not None else self.metric_value(key,"existingMetrics",info)
            demolition=(self.meta.get("demolitionMetrics") or {}).get(key) or {}
            dv="" if key=="territoryArea" else self.metric_value(key,"demolitionMetrics",demolition)
            rows.append({"key":key,"values":[str(i),title,unit,str(v) if v is not None else "Требует уточнения",str(dv) if dv is not None else "Требует уточнения"]})
        return rows


def build_spec(project,photos=None):
    """Не меняет вход: полная print-сцена и подготовленные метаданные, без сетевых запросов."""
    project=copy.deepcopy(project);c=Content(project);state=c.state
    if photos is not None:c.refs=P.revisions(project,photos=photos)
    old={s.get("id"):s for s in c.album.get("sheets") or []}
    output=[];land_rows,cards=c.land_rows()
    for kind in P.KINDS:
        blocks=M.BLOCKS[kind];sid=state["sheets"][kind]["sheetId"]
        template={"id":sid,"recipeId":P.RECIPE,"recipeVersion":1,"mytishchiKind":kind,"style":"mytishchi",
                  "kind":"photos" if kind=="photos" else "title" if kind=="title" else "map","size":"PA3",
                  "title":TITLES[kind],"maps":[],"textBlocks":{},"tables":{},"photos":[],"edits":{},"items":[]}
        c.require(kind,DEPENDENCIES[kind])
        if kind in ("title","location","district_ortho") and not c.okrugs:c.issue(kind,"unknown_rule","gisogd.admin",message="Не определён округ территории")
        if kind=="title" and not c.project.get("name"):c.issue(kind,"missing_field",field="project.name")
        if kind=="location":
            city=union_all([P.to_msk(P.polygon(a["geometry"])) for a in c.adm if (a.get("properties") or {}).get("Уровень")=="округ"])
            district=union_all([P.to_msk(P.polygon(a["geometry"])) for a in c.okrugs])
            template["maps"]=[c.map(kind,"city_map",["gisogd.admin"],city),c.map(kind,"okrug_map",["gisogd.admin"],district)]
        elif kind=="pzz":
            template["maps"]=[c.map(kind,"pzz_zones_map",BASE+["gisogd.pzz_zones"]),c.map(kind,"pzz_parameters_map",BASE+["gisogd.pzz_sub"])]
        elif "map" in blocks:
            keys=list(DEPENDENCIES[kind]);sat=kind in ("district_ortho","territory_ortho","parcels_oks","photos")
            extent=union_all([P.to_msk(P.polygon(a["geometry"])) for a in c.districts]) if kind=="district_ortho" and c.districts else c.msk
            if kind in ("education","healthcare"):
                radius=float(c.meta.get("clinicRadiusM",1000))
                if not math.isfinite(radius) or radius<=0 or radius>10000:raise P.PreparationError("invalid_input","Радиус должен быть от 0 до 10000 м",400)
                extent=c.msk.buffer(max(1000,radius))
            _,_,region=frame_geometry(extent,blocks["map"]["rect"])
            base=BASE if all(latest_coverage(state,k,region) for k in BASE) else FALLBACK
            template["maps"]=[c.map(kind,"map",base+keys,extent,sat)]
            if sat:c.issue(kind,"needs_check",field="basemap",message="Покрытие снимка проверяется до готовой выгрузки")
        texts={}
        if kind=="land_rights":
            b=blocks["rights_table"];table=M.table_pages(land_rows,["№","Адрес участка","Площадь, м²","Кадастровый номер","Вид права","Землепользователь","Документ","Период","Цель использования","Примечания"],b["columnWidthsMm"],b["rect"],11)
            template["tableSeries"]={"rights_table":table}
        if kind=="existing_use":
            b=blocks["metrics"];table=M.table_pages(c.metric_rows(),["№","Показатель","Ед. изм.","Существующее положение","Снос"],b["columnWidthsMm"],b["rect"],7.5)
            template["tableSeries"]={"metrics":table}
        if kind=="parcels_oks":texts["right_column"]=cards
        elif kind in ("general_plan","planning_docs","restrictions"):
            keys=GP if kind=="general_plan" else DOCS if kind=="planning_docs" else RESTRICTIONS
            items=[];seen=set()
            for key in keys:
                for f in features(project,key):
                    try:
                        if not shape(f["geometry"]).intersects(c.territory):continue
                    except (KeyError,ValueError):continue
                    p=f.get("properties") or {};obj=feature_key(f)
                    if obj in seen:continue
                    seen.add(obj)
                    if kind=="general_plan":
                        fields=[p.get("n") or p.get("number_fz"),p.get("fztip") or p.get("fz_type"),p.get("naimfunkzony") or p.get("Вид зоны") or p.get("name"),p.get("summfondpersp") or p.get("interval_fo")]
                    elif kind=="planning_docs":fields=[p.get("document_1"),p.get("document_n"),p.get("document_d")]
                    else:fields=[p.get("Вид зоны") or p.get("Наименование") or key,p.get("Документ") or p.get("document_n")]
                    values=[c.field(kind,f,f"{kind}.{i}",key,v) for i,v in enumerate(fields)]
                    text=f"{len(items)+1}. "+"; ".join(map(str,values))
                    if kind=="general_plan":
                        zone=P.to_msk(P.polygon(f["geometry"]))
                        fraction=min(1.,zone.intersection(c.msk).area/zone.area) if zone.area else 0.
                        raw_fund=p.get("summfondpersp") if _value(p.get("summfondpersp")) else p.get("interval_fo")
                        share=fund_share(raw_fund,fraction)
                        text+=f"; доля зоны на территории: {fraction*100:.2f} %"
                        if share is not None:text+=f"; фонд части: {share} тыс. м²"
                        elif raw_fund not in (None,"", "*"):
                            c.issue(kind,"needs_check",key,obj,"general_plan.fundShare","Фонд задан текстом; числовой пересчёт не выполнен")
                        template.setdefault("sourceFacts",[]).append({"objectKey":obj,"sourceKey":key,"fraction":fraction,
                            "areaM2":zone.area,"intersectionAreaM2":zone.intersection(c.msk).area,"fundOriginal":raw_fund,
                            "fundPart":share,"unit":"тыс. м²","sourceFields":{"fund":"summfondpersp" if _value(p.get("summfondpersp")) else "interval_fo"}})
                    items.append({"key":obj,"text":text})
            texts["right_column"]=items
            if kind=="restrictions":
                rows=[];_,_,region=frame_geometry(c.msk,blocks["map"]["rect"])
                for f in sorted(features(project,"gisogd.szz"),key=feature_key):
                    try:
                        if not shape(f["geometry"]).intersects(region):continue
                    except (ValueError,KeyError):continue
                    props=f.get("properties") or {}
                    value=lambda name,raw:c.field(kind,f,name,"gisogd.szz",raw)
                    doc="; ".join(str(props.get(k)) for k in ("Документ","document_1","document_n","document_d") if _value(props.get(k))) or None
                    rows.append({"key":feature_key(f),"values":[str(len(rows)+1),str(value("szz.title",props.get("Наименование") or props.get("name"))),
                       str(value("szz.address",props.get("Адрес"))),str(value("szz.document_size",doc))]})
                block=blocks["restrictions_table"]
                template["tableSeries"]={"restrictions_table":M.table_pages(rows,["№","Название","Адрес","Решение РПН / размер СЗЗ"],block["columnWidthsMm"],block["rect"],8,padding=.4)}
        elif kind=="pzz":
            for source,role in (("gisogd.pzz_zones","pzz_zones_notes"),("gisogd.pzz_sub","pzz_parameters_notes")):
                items=[]
                for f in features(project,source):
                    try:
                        if not shape(f["geometry"]).intersects(c.territory):continue
                    except (KeyError,ValueError):continue
                    p=f.get("properties") or {}
                    fs=[("Номер зоны",p.get("Номер зоны")),("ВРИ (коды)",p.get("ВРИ (коды)")),("ВРИ",p.get("ВРИ"))] if source.endswith("zones") else [(k,p.get(k)) for k in ("Номер подзоны","Плотность, тыс. м²/га","Высота, м","Застроенность, %","Регламент")]
                    text="; ".join(f"{k}: {c.field(kind,f,k,source,v)}" for k,v in fs)
                    items.append({"key":feature_key(f),"text":text})
                texts[role]=items
        elif kind in ("education","healthcare"):
            social=features(project,"osm.social")
            if kind=="healthcare":
                result=clinic_zones(mapping(c.territory),social,float(c.meta.get("clinicRadiusM",1000)))
                circles=result["circles"];legend=[{"key":"clinic","text":result["label"]}] if circles else []
            else:
                result=education_zones(mapping(c.territory),social,c.adm)
                for reason in result["reasonCodes"]:c.issue(kind,reason,"gisogd.admin")
                circles=[v["geometry"] for v in result["circles"]]
                legend=[{"key":r["ruleKey"]+r["okrug"],"text":f"{r['kind']}: {r['radius_m']} м" if r["radius_m"] is not None else "Школы: в границах ЦАО"} for r in result["rules"] if any(v["kind"]==r["kind"] for v in result["circles"])]
            if template["maps"]:
                mp=template["maps"][0]["sheet"]
                mp["layers"].insert(0,{"key":"accessibility","title":"Доступность","features":[{"g":g,"fill":"#dbe7bd","stroke":"#3e8050","w":1,"a":.35} for g in circles]})
            texts["right_column"]=legend
        elif kind=="photos":
            values=photos if photos is not None else [p for s in c.album.get("sheets") or [] if s.get("kind")=="photos" for p in s.get("photos") or []]
            for i,p in enumerate(values):
                if p.get("data") and p.get("at") is not None and p.get("dir") is not None:
                    template["photos"].append({**p,"id":p.get("id") or f"{state['instanceId']}:photo:{i}","number":i+1})
                else:c.issue(kind,"missing_field",key=p.get("id"),field="photo.point_direction")
            if len(template["photos"])<8:c.issue(kind,"missing_source",field="photos",message="Получить восемь кадров либо принять исключения позиций")
        if kind=="photos" and template["maps"]:
            arrows=[]
            for p in template["photos"]:
                arrows.append({"g":{"type":"Point","coordinates":p["at"]},"mk":"view","dir":p["dir"],
                               "label":str(p["number"]),"fill":"#1f3fbf","stroke":"#1f3fbf","w":1.})
            template["maps"][0]["sheet"]["layers"].append({"key":"photo-points","title":"Точки съёмки","top":True,"features":arrows})
        if template["maps"]:
            first=template["maps"][0]
            template.update(center=first["sheet"]["center"],scale=first["sheet"]["scale"],rect=blocks[first["role"]]["rect"])
        for mp in template["maps"]:
            if mp.get("legend") and "right_column" in blocks and kind not in ("parcels_oks",):
                existing=texts.setdefault("right_column",[])
                for title in mp["legend"]:existing.insert(0,{"key":"legend:"+title,"text":title})
        text_series={role:M.text_pages(items,blocks[role]["rect"],8) for role,items in texts.items()}
        table_series=template.pop("tableSeries",{})
        n=max([1,*[len(v) for v in text_series.values()],*[len(t["pages"]) for t in table_series.values()],math.ceil(len(template["photos"])/8)])
        sheet_pages=[]
        for i in range(n):
            page=copy.deepcopy(template);page["id"]=f"{sid}:{i}";page["sheetId"]=sid;page["pageNo"]=len(output)+1
            page["textBlocks"]={role:pages[i] if i<len(pages) else [] for role,pages in text_series.items()}
            page["tables"]={role:{**{k:v for k,v in t.items() if k!="pages"},"rows":t["pages"][i]} for role,t in table_series.items() if i<len(t["pages"])}
            page["photos"]=template["photos"][i*8:(i+1)*8]
            before=old.get(page["id"]) or {}
            page["automatic"]={"title":template["title"],"center":template.get("center"),"scale":template.get("scale")}
            previous=before.get("automatic") or {}
            for name in ("title","center","scale"):
                if name in before and name in previous and before[name]!=previous[name]:page[name]=copy.deepcopy(before[name])
            if page["maps"]:
                page["maps"][0]["sheet"].update(center=page["center"],scale=page["scale"])
            for name in ("edits","items"):
                if name in before:page[name]=copy.deepcopy(before[name])
            sheet_pages.append(page["id"]);output.append(page)
        own=[v for v in c.issues if v["kind"]==kind]
        state["sheets"][kind].update(state="needs_data" if own else "ready",reasonCodes=sorted({v["reasonCode"] for v in own}),
              pageIds=sheet_pages,dependencyRevisions={k:c.refs["dependencyRevisions"].get(k) for k in DEPENDENCIES[kind]},inputRevision=c.refs["inputRevision"])
    if len(output)>P.LIMITS["pages"]:raise P.PreparationError("budget_exceeded","Комплект превышает 200 страниц")
    ready=not c.issues
    for page in output:page["draft"]=not ready
    return {"spec":{"meta":{**{k:v for k,v in c.meta.items() if k!="sushpolPreparation"},"object":c.meta.get("object") or project.get("name"),"year":c.meta.get("year") or P.utcnow()[:4],"place":c.meta.get("place") or ", ".join(str((f.get("properties") or {}).get("Наименование") or "") for f in c.okrugs+c.districts)},"sheets":output},
            "preparation":state,"issues":c.issues,"ready":ready,"inputRevision":c.refs["inputRevision"]}
