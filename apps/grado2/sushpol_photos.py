"""ГРАДО 2 · воспроизводимые позиции автоматической фотофиксации по границе и OSM.

Наружные кольца канонизируются в МСК; закрытые/неподходящие дороги исключаются.
Одна основная и одна запасная точка на позицию. Проверки: tests/test_sushpol_photos.py.
"""
import math
from shapely.geometry import Point, LineString, shape
from shapely.strtree import STRtree

import preparation as P
from sushpol_io import features, feature_key

ALLOWED={"residential","living_street","service","unclassified","tertiary","secondary","primary",
         "footway","pedestrian","path","steps","track"}


def allowed_road(properties):
    highway=properties.get("Тип дороги") or properties.get("highway")
    if highway not in ALLOWED:return False
    access=str(properties.get("access") or "").lower();foot=str(properties.get("foot") or "").lower()
    if foot in ("no","private"):return False
    if access in ("no","private") and foot not in ("yes","designated","permissive"):return False
    try:layer=float(properties.get("layer") or 0)
    except (ValueError,TypeError):return False
    if not math.isfinite(layer):return False
    tunnel=str(properties.get("tunnel") or "").lower();bridge=str(properties.get("bridge") or "").lower()
    if tunnel and tunnel!="no" and layer<0:return False
    if bridge and bridge!="no" and layer>0:return False
    return True


def _ring(polygon):
    ring=polygon.exterior
    values=list(ring.coords)[:-1]
    if not ring.is_ccw:values.reverse()
    start=min(range(len(values)),key=lambda i:values[i])
    values=values[start:]+values[:start]
    return values+[values[0]]


def photo_plan(project):
    territory=P.to_msk(P.project_territory(project))
    polygons=list(territory.geoms) if territory.geom_type=="MultiPolygon" else [territory]
    parts=[(p.area,_ring(p)) for p in polygons]
    parts.sort(key=lambda p:(-p[0],p[1]))
    rings=[LineString(coords) for _,coords in parts]
    length=sum(r.length for r in rings)
    roads=[];identities=[]
    raw=(project.get("data") or {}).get("osm.roads") or {}
    if raw.get("osmSchema")==2:
        for f in features(project,"osm.roads"):
            if not allowed_road(f.get("properties") or {}):continue
            try:g=P.to_msk(shape(f["geometry"]))
            except (ValueError,KeyError,TypeError):continue
            lines=list(g.geoms) if g.geom_type=="MultiLineString" else [g] if g.geom_type=="LineString" else []
            for n,line in enumerate(lines):
                roads.append(line);identities.append((feature_key(f),n))
    tree=STRtree(roads) if roads else None
    state=((project.get("album") or {}).get("meta") or {}).get("sushpolPreparation") or {}
    iid=state.get("instanceId") or P.RECIPE
    result=[]
    for i in range(8):
        offset=(i+.5)*length/8
        for ring in rings:
            if offset<=ring.length:
                target=ring.interpolate(offset);break
            offset-=ring.length
        candidates=[]
        if tree is not None:
            for index in tree.query(target.buffer(250)):
                coords=list(roads[index].coords);key,part=identities[index]
                for seg,(a,b) in enumerate(zip(coords,coords[1:])):
                    line=LineString([a,b])
                    if line.length==0:continue
                    at=line.project(target);point=line.interpolate(at);dist=point.distance(target)
                    if dist<=250+1e-8:candidates.append((dist,key,part,seg,at/line.length,point))
        candidates.sort(key=lambda x:x[:5])
        selected=[]
        for candidate in candidates:
            point=candidate[-1]
            if any(point.distance(p)<10 for p in selected):continue
            selected.append(point)
            if len(selected)==2:break
        result.append({"id":f"{iid}:photo:{i}","target":list(P.to_wgs(target).coords)[0],
                       "candidates":[list(P.to_wgs(p).coords)[0] for p in selected],
                       "reasonCode":None if selected else "missing_source"})
    return result
