"""ГРАДО 2 · круги доступности нового набора в МСК без подмены маршрутом.

Медицина: выбранный владельцем примерный радиус и заданная подпись. Образование:
правила действующего SERVICES, округ по подтверждённым границам. Проверки рядом.
"""
import math
from shapely import union_all
from shapely.geometry import Point, mapping, shape
import preparation as P

CLINIC_LABEL = "Транспортно-пешеходная доступность"


def clinic_zones(territory, features, radius_m=1000):
    if isinstance(radius_m,bool) or not isinstance(radius_m,(int,float)) or not math.isfinite(radius_m) or radius_m<=0:
        raise P.PreparationError("invalid_input","Радиус должен быть положительным числом в метрах",400)
    t=P.to_msk(P.polygon(territory));circles=[];objects=[]
    for f in features:
        if (f.get("properties") or {}).get("Вид")!="поликлиника" or (f.get("geometry") or {}).get("type")!="Point":continue
        center=P.to_msk(shape(f["geometry"]))
        if center.distance(t)>radius_m:continue
        circles.append(center.buffer(radius_m,quad_segs=32));objects.append(f)
    return {"method":"approximate_radius","radius_m":radius_m,"label":CLINIC_LABEL,"objects":objects,
            "circles":[mapping(P.to_wgs(g)) for g in circles],
            "coverage":mapping(P.to_wgs(union_all(circles))) if circles else None}


def education_zones(territory,features,admin):
    t=P.to_msk(P.polygon(territory));parts=[];circles=[];rules=[];issues=[]
    for f in admin:
        p=f.get("properties") or {}
        if p.get("Уровень")!="округ":continue
        try:a=P.to_msk(P.polygon(f["geometry"]));part=t.intersection(a)
        except P.PreparationError:continue
        if part.is_empty or part.area<=1e-6:continue
        name=str(p.get("Наименование") or p.get("Округ") or "")
        if not name:
            issues.append("unknown_rule");continue
        cao="Центральн" in name or name=="ЦАО"
        parts.append(part)
        for kind,r,key in (("детский сад",500 if cao else 300,"детские сады · Москва (2151-ПП)"),
                           ("школа",None if cao else 1000,"школы · Москва (2151-ПП)")):
            rules.append({"okrug":name,"kind":kind,"radius_m":r,"ruleKey":key,"reasonCode":"radius_not_defined" if r is None else None})
            if r is None:continue
            for obj in features:
                if (obj.get("properties") or {}).get("Вид")!=kind or (obj.get("geometry") or {}).get("type")!="Point":continue
                center=P.to_msk(shape(obj["geometry"]))
                if center.distance(part)>r:continue
                circle=center.buffer(r,quad_segs=32).intersection(a)
                circles.append({"geometry":mapping(P.to_wgs(circle)),"kind":kind,"radius_m":r,"ruleKey":key})
    if not parts or t.difference(union_all(parts)).area>max(.01,t.area*1e-7):issues.append("unknown_rule")
    return {"circles":circles,"rules":rules,"reasonCodes":sorted(set(issues))}
