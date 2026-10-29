"""ГРАДО 2 · ограниченный серверный запуск подготовки для UI и MCP.

Сервер владеет lease, повторно проверяет права, сохраняет этапы и неизменяемый
кандидат. Перезапуск не продолжает задачи сам. Проверки: tests/test_sushpol_jobs.py.
"""
from __future__ import annotations

import asyncio
import base64
import copy
import io
import json
import math
import sys
import threading
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone

from PIL import Image, ImageOps
from shapely.geometry import box, mapping, shape
from shapely import union_all

import preparation as P
import preparation_api as A
import sushpol_io as C

HEAVY=threading.BoundedSemaphore(1)
_SERVICES={}
_SERVICES_LOCK=threading.Lock()


def service(server):
    key=(id(server),str(server.PROJECTS),str(server.CACHE),id(server.HUB))
    with _SERVICES_LOCK:
        if key not in _SERVICES:_SERVICES[key]=Runs(server)
        return _SERVICES[key]


def _run_state(project):
    return ((project.get("album") or {}).get("meta") or {}).get("sushpolPreparation") or {}


def _expected(server,key):
    value=server.SOURCES[key][1]
    return list(value) if isinstance(value,(dict,list,tuple)) else [value] if isinstance(value,str) else [key]


def _source_bounds(project,key,context_limit=None,deferred=None):
    content=C.Content(copy.deepcopy(project));regions=[]
    territory=content.msk
    radius=float(content.meta.get("clinicRadiusM",1000))
    if not math.isfinite(radius) or not 0<radius<=10000:
        raise P.PreparationError("invalid_input","Радиус должен быть положительным и не больше 10000 м",400)
    for kind in P.KINDS:
        for role,block in C.M.BLOCKS[kind].items():
            if block.get("geometryPart") is None and not (role.endswith("map") or role=="map"):continue
            if not (role.endswith("map") or role=="map"):continue
            if kind=="location":continue
            extent=territory
            if kind=="district_ortho" and content.districts:
                extent=union_all([P.to_msk(P.polygon(f["geometry"])) for f in content.districts])
            elif kind in ("education","healthcare"):extent=territory.buffer(max(1000,radius))
            if key in C.BASE+C.FALLBACK or key in C.DEPENDENCIES[kind]:
                region=C.frame_geometry(extent,block["rect"])[2]
                area=P.to_msk(box(*region.bounds)).area/1e6
                if kind=="district_ortho" and key in C.BASE+C.FALLBACK and context_limit is not None and area>context_limit:
                    if deferred is not None:deferred.append({"kind":kind,"role":role,"sourceKey":key,"reasonCode":"budget_exceeded", "requestedArea":mapping(region),"actualAreaKm2":area,"maxAreaKm2":context_limit})
                    continue
                regions.append(region)
    if key=="osm.roads":regions.append(P.to_wgs(territory.buffer(350)))
    if key=="gisogd.admin":return list(P.to_wgs(territory).bounds)
    return list(union_all(regions).bounds) if regions else list(P.to_wgs(territory).bounds)


def _merged(previous,incoming,bounds,preserve_absent=False):
    """Трёхстороннее слияние по ключу источника; ручное изменение сильнее ответа портала."""
    previous=previous or {};current=(previous.get("fc") or {}).get("features") or []
    original=previous.get("original")
    base=current if original in (None,"=fc") else original.get("features",[]) if isinstance(original,dict) else current
    old={C.feature_key(f):f for f in base};manual={C.feature_key(f):f for f in current}
    new={C.feature_key(f):f for f in incoming};region=box(*bounds)
    for key,f in old.items():
        try:outside=not shape(f["geometry"]).intersects(region)
        except (ValueError,KeyError):outside=True
        if outside or preserve_absent:new.setdefault(key,f)
    source=copy.deepcopy(list(new.values()))
    for key,f in manual.items():
        if key not in old or P.digest(f)!=P.digest(old[key]):new[key]=copy.deepcopy(f)
    for key in old.keys()-manual.keys():new.pop(key,None)
    return list(new.values()),source


def _issue_summary(issues):
    codes={};sheets={}
    for x in issues:
        code=x.get("reasonCode","unknown");kind=x.get("kind","project")
        codes[code]=codes.get(code,0)+1;sheets[kind]=sheets.get(kind,0)+1
    return {"total":len(issues),"byCode":codes,"bySheet":sheets,"examples":issues[:8]}


class Runs:
    def __init__(self,server):
        self.server=server;self.jobs={};self.lock=threading.RLock()
        self.root=server.CACHE/"preparation"

    def _path(self,record,run_id):
        rid=str(uuid.UUID(run_id))
        namespace=record["meta"].get("preparationProjectId")
        if namespace:namespace=str(uuid.UUID(namespace))
        else:namespace=P.digest(str(record["tx"].project))[:32]
        return self.root/namespace/rid

    def _write(self,record,project,metadata,command_id=None):
        s=self.server
        P.check_profile(project)
        body=P.dump(project)
        if s.HUB:s.HUB._check_size(body)
        if s.projects_size()+len(body)*3>s.PROJECTS_CAP and not s.HUB:
            raise P.PreparationError("checkpoint_failed","Недостаточно места для контрольной версии и безопасной записи",507)
        if s.HUB:
            new_rev=record["meta"]["rev"]+1
            metadata={**metadata,"rev":new_rev,"updated":time.time(),"updated_by":record["actor"],
                      "sec_rev":{**record["meta"]["sec_rev"],"meta":new_rev,"album":new_rev,
                                 **{"layer:"+k:new_rev for k in project.get("data",{})}}}
        result=record["tx"].publish(body,metadata,command_id or str(uuid.uuid4()),record["revision"])
        if s.HUB:
            pid=metadata["id"]
            s.HUB._cache_put(pid,metadata["rev"],s.hubmod.split_project(project))
            with s.HUB._live:
                s.HUB._publish(pid,{"type":"rev","rev":metadata["rev"],"sections":sorted(metadata["sec_rev"]),"by":record["actor"],"client":"preparation"})
        return result

    def _mark(self,job,**changes):
        job.update(changes)
        with A.access(self.server,job["actor"],job["projectId"],True,metadata_only=True) as rec:
            metadata=rec["meta"]
            runs=dict(metadata.get("preparationRuns") or {})
            runs[job["runId"]]={k:job[k] for k in ("runId","actorId","state","phase","startedAt","updatedAt","ready","progress") if k in job}
            if job.get("report"):runs[job["runId"]]["report"]=job["report"]
            if job.get("candidateSHA256"):runs[job["runId"]]["candidateSHA256"]=job["candidateSHA256"]
            if job.get("result"):runs[job["runId"]]["result"]=job["result"]
            metadata={**metadata,"preparationRuns":dict(list(runs.items())[-64:])}
            P.atomic_write(rec["tx"].meta,P.dump(metadata))

    def _check(self,job):
        if job["cancel"].is_set():raise P.PreparationError("cancelled","Подготовка остановлена")
        if time.monotonic()>job["deadline"]:raise P.PreparationError("budget_exceeded","Истёк общий срок подготовки")
        with A.access(self.server,job["actor"],job["projectId"],True,metadata_only=True) as rec:
            lease=rec["meta"].get("preparationLease") or {}
            if lease.get("leaseId")!=job["leaseId"] or lease.get("expiresAt",0)<=time.time():
                raise P.PreparationError("version_conflict","Утрачено право на запуск")

    def start(self,c,req):
        s=self.server;pid=str(req.get("projectId") or "");cid=A._uuid(req.get("commandId"));actor=A._actor(s,c)
        for key in ("refresh","photos"):
            if key in req and type(req[key]) is not bool:raise P.PreparationError("invalid_input",f"{key}: ожидается логическое значение",400)
        args={"refresh":req.get("refresh",True),"photos":req.get("photos",True),"resumeRunId":req.get("resumeRunId"),"recipeId":P.RECIPE}
        if args["resumeRunId"]:A._uuid(args["resumeRunId"])
        with A.access(s,actor,pid,True) as rec:
            A.require_capabilities(c.headers,rec["meta"])
            if args["resumeRunId"] and args["resumeRunId"] not in (rec["meta"].get("preparationRuns") or {}):
                raise P.PreparationError("run_not_found","Возобновляемый запуск не найден",404)
            sig=P.digest(args);idkey=rec["actor"]+":"+cid
            starts=dict(rec["meta"].get("preparationStarts") or {})
            if idkey in starts:
                before=starts[idkey]
                if before["argsDigest"]!=sig:raise P.PreparationError("version_conflict","Идентификатор старта использован с другими настройками")
                status=(rec["meta"].get("preparationRuns") or {}).get(before["runId"]) or {}
                active=self.jobs.get(before["runId"])
                state=active.get("state") if active else "interrupted" if status.get("state") in ("running","planned") else status.get("state","interrupted")
                return {"projectId":pid,"runId":before["runId"],"state":state,"reused":True}
            if len(starts)>=1000:raise P.PreparationError("budget_exceeded","Достигнут лимит 1000 команд подготовки проекта; создайте новую рабочую копию",413)
            if not HEAVY.acquire(blocking=False):raise P.PreparationError("busy","Сервер занят другой подготовкой или выгрузкой",503)
            try:
                project=copy.deepcopy(rec["project"]);P.project_territory(project);P.check_profile(project)
                if req.get("expectedProjectRevision") and req["expectedProjectRevision"]!=rec["revision"]:
                    raise P.PreparationError("version_conflict","Проект изменён после просмотра")
                run_id=str(uuid.uuid4());now=P.utcnow()
                # Фиксируем роли до базовой ревизии, чтобы собственный импорт не был принят за ручную правку.
                layers=project.setdefault("layers",[]);known={v["key"] for v in layers}
                for key in C.ALL_SOURCES:
                    if key in s.SOURCES and key not in known:layers.append({"key":key,"title":s.SOURCES[key][2],"visible":True,"style":{}})
                for sheet in project.get("album",{}).get("sheets",[]):
                    for i,ph in enumerate(sheet.get("photos") or []):ph.setdefault("id",str(uuid.uuid4()))
                meta=project.setdefault("album",{}).setdefault("meta",{})
                st=meta.setdefault("sushpolPreparation",P.new_state())
                if st.get("schemaVersion")!=P.SCHEMA:raise P.PreparationError("unsupported_schema","Схема подготовки не поддерживается")
                meta["requiredCapabilities"]=[P.CAPABILITY]
                refs=P.revisions(project)
                if s.HUB:s.HUB._check_size(P.dump(project))
                elif s.projects_size()+len(rec["body"])*3>s.PROJECTS_CAP:
                    raise P.PreparationError("checkpoint_failed","Недостаточно места для безопасной контрольной версии",507)
                cp=rec["tx"].checkpoint(rec["revision"])
                lease=rec["tx"].lease("acquire",run_id,"server:"+rec["actor"]+":"+run_id,cid,expected_revision=rec["revision"])
                metadata=rec["tx"].read()[1]
                metadata.setdefault("preparationProjectId",str(uuid.uuid4()))
                metadata["requiredCapabilities"]=[P.CAPABILITY]
                starts[idkey]={"runId":run_id,"argsDigest":sig,"actor":rec["actor"],"createdAt":now}
                metadata["preparationStarts"]=starts
                recorded=dict(metadata.get("preparationRuns") or {})
                recorded[run_id]={"runId":run_id,"actorId":rec["actor"],"state":"running","phase":"planned", "ready":False,
                                  "startedAt":now,"updatedAt":now,"progress":{"got":0,"total":len(C.ALL_SOURCES)}}
                metadata["preparationRuns"]=dict(list(recorded.items())[-64:])
                st["activeRun"]={"runId":run_id,"ownerClientId":"server","state":"running",**refs,
                      "startedAt":now,"updatedAt":now,"reasonCodes":[],"checkpointId":cp["checkpointId"],"committedRevision":None}
                result=self._write(rec,project,metadata,cid)
                job={"projectId":pid,"runId":run_id,"actor":copy.deepcopy(actor),"actorId":rec["actor"],
                     "state":"running","phase":"sources","startedAt":now,"updatedAt":now,"progress":{"got":0,"total":len(C.ALL_SOURCES)},
                     "ready":False,"cancel":threading.Event(),"stopHeartbeat":threading.Event(),"leaseId":lease["leaseId"],
                     "leaseOwner":"server:"+rec["actor"]+":"+run_id,"deadline":time.monotonic()+1800,"args":args,
                     "baseInputsRevision":refs["baseInputsRevision"],"path":self._path({**rec,"meta":metadata},run_id)}
                self.jobs[run_id]=job
            except BaseException:
                HEAVY.release();raise
        thread=threading.Thread(target=self._run,args=(job,),name="grado-prepare-"+run_id[:8],daemon=True)
        job["thread"]=thread;thread.start()
        return {"projectId":pid,"runId":run_id,"state":"running","checkpointId":cp["checkpointId"],"reused":False}

    def _heartbeat(self,job):
        while not job["stopHeartbeat"].wait(10):
            try:
                with A.access(self.server,job["actor"],job["projectId"],True,metadata_only=True) as rec:
                    rec["tx"].lease("renew",job["runId"],job["leaseOwner"],str(uuid.uuid4()),lease_id=job["leaseId"])
            except Exception:
                job["cancel"].set();return

    def _sources(self,job):
        s=self.server
        with A.access(s,job["actor"],job["projectId"]) as rec:
            prior=list((_run_state(rec["project"]).get("requests") or {}).values())
            retry_alternative=not job["args"]["refresh"] and any(v.get("sourceKey") in C.BASE and v.get("state")=="failed" for v in prior)
        order=["gisogd.admin",*C.FALLBACK,*[k for k in C.ALL_SOURCES if k not in C.FALLBACK and k!="gisogd.admin"]] if retry_alternative else C.ALL_SOURCES
        for i,key in enumerate(order):
            self._check(job)
            if key not in s.SOURCES:continue
            with A.access(s,job["actor"],job["projectId"],True) as rec:
                project=rec["project"]
                source_kind=s.SOURCES[key][0]
                limit=s.TILE_KM2[source_kind]*s.MAX_TILES if source_kind in s.TILE_CAPPED else s.LIMIT_KM2[source_kind]
                deferred=[]
                bounds=_source_bounds(project,key,limit,deferred)
                state=_run_state(project)
                planned=[v for v in state.get("deferredSources",[]) if v.get("sourceKey")!=key]+deferred
                if planned!=state.get("deferredSources",[]):
                    state["deferredSources"]=planned
                    self._write(rec,project,rec["meta"])
                previous=[v for v in (state.get("requests") or {}).values() if v.get("sourceKey")==key]
                if not job["args"]["refresh"] and previous and previous[-1].get("state") in ("received","empty") and (key!="osm.roads" or ((project.get("data") or {}).get(key) or {}).get("osmSchema")==2):
                    proof=previous[-1]
                    if P.coverage(mapping(box(*bounds)),proof.get("checkedParts") or [],_expected(s,key))["complete"]:
                        continue
                # После реального отказа ЕГКО продолжение сначала проверяет запасную основу.
                # Подтверждённый полный Яндекс не заставляет снова качать неудавшийся общегородской слой.
                if retry_alternative and key in C.BASE and all(C.latest_coverage(state,k,box(*bounds)) for k in C.FALLBACK):continue
                # Не гоняем запасной Яндекс поверх полностью полученной основы ЕГКО.
                if key in C.FALLBACK:
                    receipts=list((state.get("requests") or {}).values())
                    if all(C.latest_coverage(state,k,box(*bounds)) for k in C.BASE):continue
            self._mark(job,phase="sources",updatedAt=P.utcnow(),progress={"got":i,"total":len(C.ALL_SOURCES),"sourceKey":key})
            layers,errors=s.fetch(bounds,[key])
            self._check(job)
            request_id=str(uuid.uuid5(uuid.UUID(job["runId"]),key+P.digest(bounds)))
            proof=P.receipt(key,bounds,layers.get(key),errors.get(key),_expected(s,key),job["runId"],request_id)
            with A.access(s,job["actor"],job["projectId"],True) as rec:
                current=rec["project"]
                if P.revisions(current)["baseInputsRevision"]!=job["baseInputsRevision"]:
                    raise P.PreparationError("manual_conflict","Входные настройки изменились во время получения данных")
                state=_run_state(current);state.setdefault("requests",{})[request_id]=proof
                if key in layers:
                    incoming=layers[key];old=(current.get("data") or {}).get(key) or {}
                    merged,original=_merged(old,incoming["features"]["features"],bounds,preserve_absent=proof["state"] not in ("received","empty"))
                    data=current.setdefault("data",{})
                    data[key]={k:v for k,v in incoming.items() if k not in ("features","acquisition")}
                    data[key].update(title=old.get("title") or incoming["title"],fc={"type":"FeatureCollection","features":merged},
                       original={"type":"FeatureCollection","features":original},acquisitionRefs=[request_id],bbox=bounds)
                    if P.digest(merged)==P.digest(original):data[key]["original"]="=fc"
                    proof["dataRevision"]=P.revisions(current)["dependencyRevisions"][key]
                state["activeRun"]["updatedAt"]=P.utcnow()
                self._write(rec,current,rec["meta"])

    def _photos(self,job,project):
        # Владелецские кадры не заменяются автоматическим видом при обновлении.
        existing=[p for sheet in (project.get("album") or {}).get("sheets") or [] if sheet.get("kind")=="photos" for p in sheet.get("photos") or []]
        if not job["args"]["photos"]:return existing
        from sushpol_photos import photo_plan
        from panorama_io import get_frame
        plan=photo_plan(project)
        result=[];consumed=set()
        existing_by_id={p.get("id"):p for p in existing}
        for i,slot in enumerate(plan):
            self._check(job)
            old=existing_by_id.get(slot["id"])
            if old is None and i<len(existing) and not str(existing[i].get("id","")).startswith((_run_state(project).get("instanceId") or "")+":photo:"):
                old=existing[i]
            if old and old.get("data") and old.get("source")!="yandex":
                result.append(old);consumed.add(old.get("id"));continue
            self._mark(job,phase="photos",progress={"got":i,"total":len(plan)},updatedAt=P.utcnow())
            photo={"id":slot["id"],"name":f"Снимок {i+1}","source":"yandex","target":slot["target"]}
            for candidate in slot["candidates"]:
                try:
                    frame=asyncio.run(get_frame(candidate,slot["target"],self.server.CACHE,cancel=job["cancel"],deadline=job["deadline"],
                           excluded=[(p["panoramaId"],p["dir"]) for p in result if p.get("panoramaId") and p.get("dir") is not None]))
                    photo.update(data=frame["image"]["data"],w=frame["image"]["width"],h=frame["image"]["height"],at=frame["point"],
                                 dir=frame["azimuthDeg"],panoramaId=frame["panoramaId"],imageId=frame["imageId"],sourceUrl=frame["sourceUrl"],
                                 downloadedAt=frame["downloadedAt"],takenAt=frame["takenAt"])
                    break
                except Exception as e:
                    code=getattr(e,"code","source_unavailable");photo["reasonCode"]=code
                    if code in ("rate_limited","timeout","cancelled"):break
            result.append(photo)
            if photo.get("reasonCode")=="rate_limited":
                result += [{"id":v["id"],"source":"yandex","target":v["target"],"reasonCode":"rate_limited"} for v in plan[i+1:]]
                break
        result += [p for p in existing if p.get("id") not in consumed and p.get("id") not in {q.get("id") for q in result} and p.get("source")!="yandex"]
        return result

    def _capture_tiles(self,job):
        """Одна неизменяемая подборка байтов для проверки, PDF и PPTX данного запуска."""
        manifest={};size=0;root=job["path"]/"rasters"
        def get(provider,z,x,y,kind="sat"):
            nonlocal size
            self._check(job)
            key=f"{provider}:{kind}:{int(z)}:{int(x)}:{int(y)}"
            if key in manifest:
                sha=manifest[key]
                return (root/(sha+".bin")).read_bytes() if sha else None
            fetch=self.server.esri_tile if provider=="esri" else getattr(self.server.esri_tile,"ysat",None)
            data=fetch(z,x,y,kind) if provider=="esri" else fetch(z,x,y) if fetch else None
            if data:
                size+=len(data)
                if size>256*2**20:raise P.PreparationError("budget_exceeded","Снимки запуска превышают 256 МиБ")
                sha=P.body_hash(data);P.atomic_write(root/(sha+".bin"),data)
                manifest[key]=sha
            else:manifest[key]=None
            return data
        def tiles(z,x,y,kind="sat"):return get("esri",z,x,y,kind)
        tiles.ysat=lambda z,x,y:get("yandex",z,x,y)
        def finish():
            raw=P.dump({"schemaVersion":1,"tiles":manifest,"bytes":size,"checkedAt":P.utcnow()})
            P.atomic_write(job["path"]/"rasters.json",raw)
            return P.body_hash(raw)
        return tiles,finish

    def _frozen_tiles(self,path,expected,draft):
        file=path/"rasters.json"
        if not file.exists():
            if not draft:raise P.PreparationError("checkpoint_failed","Нет зафиксированных снимков этой версии",503)
            def blank(*args):return None
            blank.ysat=blank
            return blank
        raw=file.read_bytes()
        if not expected or P.body_hash(raw)!=expected:raise P.PreparationError("checkpoint_failed","Контрольная сумма снимков не совпала",503)
        manifest=json.loads(raw)
        if manifest.get("schemaVersion")!=1:raise P.PreparationError("unsupported_schema","Формат подборки снимков не поддерживается")
        def get(provider,z,x,y,kind="sat"):
            key=f"{provider}:{kind}:{int(z)}:{int(x)}:{int(y)}"
            if key not in manifest["tiles"]:
                if draft:return None
                raise P.PreparationError("checkpoint_failed","В версии нет необходимого тайла снимка",503)
            sha=manifest["tiles"][key]
            if sha is None:return None
            if not isinstance(sha,str) or len(sha)!=64 or any(c not in "0123456789abcdef" for c in sha):
                raise P.PreparationError("checkpoint_failed","Неверная ссылка на снимок",503)
            try:data=(path/"rasters"/(sha+".bin")).read_bytes()
            except FileNotFoundError:raise P.PreparationError("checkpoint_failed","Файл снимка версии утрачен",503) from None
            if P.body_hash(data)!=sha:raise P.PreparationError("checkpoint_failed","Файл снимка версии повреждён",503)
            return data
        def tiles(z,x,y,kind="sat"):return get("esri",z,x,y,kind)
        tiles.ysat=lambda z,x,y:get("yandex",z,x,y)
        return tiles

    def _run(self,job):
        heartbeat=threading.Thread(target=self._heartbeat,args=(job,),daemon=True);heartbeat.start()
        try:
            self._mark(job)
            self._sources(job)
            self._check(job)
            with A.access(self.server,job["actor"],job["projectId"],True) as rec:
                snapshot=copy.deepcopy(rec["project"]);revision=rec["revision"]
            photos=self._photos(job,snapshot)
            self._mark(job,phase="composition",updatedAt=P.utcnow(),progress={"got":0,"total":14})
            result=C.build_spec(snapshot,photos)
            self._check(job)
            self._mark(job,phase="checking",updatedAt=P.utcnow())
            import print_io
            frozen_tiles,finish=self._capture_tiles(job)
            print_io._pages(result["spec"],self.server.REDLN,self.server.LGR_DASH,frozen_tiles)
            result["preparation"]["rasterManifestSHA256"]=finish()
            verified=set()
            for sheet in result["spec"]["sheets"]:
                kind=sheet["mytishchiKind"]
                rasters=[m["sheet"].get("_rasterAcquisition") for m in sheet.get("maps",[]) if m["sheet"].get("basemap")]
                if rasters and all(r and r.get("complete") for r in rasters):verified.add(kind)
                if sheet.get("_labelQA"):result["issues"].append({"kind":kind,"reasonCode":"needs_check","field":"labels","message":"Проверьте подписи: "+"; ".join(sheet["_labelQA"][:5])})
                if sheet.get("_notReady"):result["issues"].append({"kind":kind,"reasonCode":"layout_overflow","message":"Не поместилось содержимое листа"})
            result["issues"]=[v for v in result["issues"] if not (v.get("field")=="basemap" and v.get("kind") in verified)]
            result["ready"]=not result["issues"]
            for kind,entry in result["preparation"]["sheets"].items():
                own=[v for v in result["issues"] if v["kind"]==kind]
                entry.update(state="needs_data" if own else "ready",reasonCodes=sorted({v["reasonCode"] for v in own}))
            for sheet in result["spec"]["sheets"]:sheet["draft"]=not result["ready"]
            candidate=copy.deepcopy(snapshot)
            candidate["album"]["sheets"]=result["spec"]["sheets"]
            candidate["album"]["meta"].update(result["spec"]["meta"])
            candidate["album"]["meta"]["sushpolPreparation"]=result["preparation"]
            st=_run_state(candidate);st["generation"]+=1
            final_refs=P.revisions(candidate)
            for sheet in st["sheets"].values():sheet["inputRevision"]=final_refs["inputRevision"]
            st["activeRun"].update(state="ready" if result["ready"] else "blocked",inputRevision=final_refs["inputRevision"],baseInputsRevision=final_refs["baseInputsRevision"],
                                   updatedAt=P.utcnow(),reasonCodes=sorted({x["reasonCode"] for x in result["issues"]}))
            P.check_profile(candidate)
            raw=P.dump(candidate);P.atomic_write(job["path"]/"candidate.grado2",raw)
            P.atomic_write(job["path"]/"report.json",P.dump(result["issues"]))
            with A.access(self.server,job["actor"],job["projectId"],True) as rec:
                if rec["revision"]!=revision:raise P.PreparationError("manual_conflict","Проект изменён во время сборки; кандидат не заменил текущий результат")
                self._check(job)
                if result["ready"] or not (rec["project"].get("album") or {}).get("sheets"):
                    self._write(rec,candidate,rec["meta"])
                else:
                    current=rec["project"]
                    _run_state(current)["activeRun"].update(state="blocked",updatedAt=P.utcnow(),reasonCodes=st["activeRun"]["reasonCodes"])
                    self._write(rec,current,rec["meta"])
            self._mark(job,state="ready" if result["ready"] else "blocked",phase="finished",ready=result["ready"],
                       candidateSHA256=P.body_hash(raw),report=_issue_summary(result["issues"]),
                       result={"pages":len(result["spec"]["sheets"]),"kinds":14,"generation":st["generation"]},
                       progress={"got":14,"total":14},updatedAt=P.utcnow())
        except Exception as e:
            code="forbidden" if isinstance(e,self.server.hubmod.HubError) and e.status in (401,403) else getattr(e,"code",None) or "source_unavailable"
            state="cancelled" if code=="cancelled" else "conflict" if code in ("manual_conflict","version_conflict") else "blocked"
            job.update(state=state,phase="stopped",ready=False,report={"total":1,"byCode":{code:1},"examples":[{"reasonCode":code,"message":str(e)[:350]}]},updatedAt=P.utcnow())
            if code in ("cancelled","budget_exceeded","source_unavailable") and not (job["path"]/"candidate.grado2").exists():
                try:
                    # Даже остановленная первая сборка оставляет доступный черновик принятых данных.
                    # Отозванное право запрещает создание/публикацию этого результата.
                    with A.access(self.server,job["actor"],job["projectId"],True) as rec:
                        partial=copy.deepcopy(rec["project"])
                        built=C.build_spec(partial)
                        partial["album"]["sheets"]=built["spec"]["sheets"]
                        partial["album"]["meta"].update(built["spec"]["meta"])
                        partial["album"]["meta"]["sushpolPreparation"]=built["preparation"]
                        for sheet in partial["album"]["sheets"]:sheet["draft"]=True
                        P.check_profile(partial)
                        raw=P.dump(partial)
                        issues=[{"kind":"project","reasonCode":code,"message":str(e)[:350]},*built["issues"]]
                        P.atomic_write(job["path"]/"candidate.grado2",raw)
                        P.atomic_write(job["path"]/"report.json",P.dump(issues))
                        job.update(candidateSHA256=P.body_hash(raw),report=_issue_summary(issues),
                                   result={"pages":len(built["spec"]["sheets"]),"kinds":14,"partial":True})
                except Exception:pass  # исходная причина остаётся; запрет записи после отзыва прав не обходится
            try:self._mark(job)
            except Exception:pass  # отозванный доступ запрещает даже финальную запись статуса в проект
        finally:
            job["stopHeartbeat"].set();heartbeat.join(timeout=.3)
            try:
                with A.access(self.server,job["actor"],job["projectId"],True,metadata_only=True) as rec:
                    rec["tx"].lease("release",job["runId"],job["leaseOwner"],str(uuid.uuid4()),lease_id=job["leaseId"])
            except Exception:pass
            HEAVY.release()

    def _record(self,c,pid,run_id=None,command_id=None):
        s=self.server
        with A.access(s,A._actor(s,c),pid,metadata_only=bool(run_id or command_id)) as rec:
            rid=run_id
            if command_id:
                cid=A._uuid(command_id);found=(rec["meta"].get("preparationStarts") or {}).get(rec["actor"]+":"+cid)
                if not found:raise P.PreparationError("run_not_found","Команда подготовки не найдена",404)
                rid=found["runId"]
            if rid:rid=A._uuid(rid)
            else:rid=(_run_state(rec["project"]).get("activeRun") or {}).get("runId")
            state=(rec["meta"].get("preparationRuns") or {}).get(rid)
            if not state:raise P.PreparationError("run_not_found","Подготовка не найдена",404)
            value=copy.deepcopy(state)
            live=self.jobs.get(rid)
            if live:
                value.update({k:copy.deepcopy(live[k]) for k in ("state","phase","ready","report","progress","updatedAt","result","candidateSHA256") if k in live})
            if rid not in self.jobs and value.get("state")=="running":value["state"]="interrupted"
            return rec,rid,value

    def get(self,c,server):
        pid=c.q("projectId");rec,rid,value=self._record(c,pid,c.q("runId") or None,c.q("commandId") or None)
        if c.route=="/api/preparation/status":
            wait=max(0,min(15,int(c.q("wait") or 0)))
            until=time.monotonic()+wait
            initial=P.digest(value)
            while value.get("state")=="running" and time.monotonic()<until:
                time.sleep(.2)
                rec,rid,value=self._record(c,pid,rid)
                if P.digest(value)!=initial:break
            key=(value.get("progress") or {}).get("sourceKey")
            progress=server.PROGRESS.get(key)
            return server._json(200,{"projectId":pid,**value,**({"sourceProgress":copy.deepcopy(progress)} if progress else {})})
        if c.route=="/api/preparation/issues":
            path=self._path(rec,rid)/"report.json"
            if not path.exists():return server._json(200,{"runId":rid,"issues":[],"total":0})
            issues=json.loads(path.read_bytes())
            offset=max(0,int(c.q("offset") or 0));limit=max(1,min(100,int(c.q("limit") or 25)))
            return server._json(200,{"runId":rid,"issues":issues[offset:offset+limit],"total":len(issues),"offset":offset})
        if c.route=="/api/preparation/export":
            fmt=c.q("format")
            if fmt not in ("pdf","pptx"):raise P.PreparationError("invalid_input","Формат должен быть pdf или pptx",400)
            draft=c.q("draft")=="1"
            if not value.get("ready") and not draft:raise P.PreparationError("not_ready","Комплект неполон: проверьте отчёт или явно запросите черновик")
            try:raw=(self._path(rec,rid)/"candidate.grado2").read_bytes()
            except FileNotFoundError:raise P.PreparationError("result_expired","Файл результата отсутствует; запустите подготовку заново",410) from None
            if P.body_hash(raw)!=value.get("candidateSHA256"):raise P.PreparationError("checkpoint_failed","Контрольная сумма результата не совпала",503)
            project=json.loads(raw);state=_run_state(project)
            spec={"meta":project["album"]["meta"],"sheets":project["album"]["sheets"]}
            if not HEAVY.acquire(blocking=False):raise P.PreparationError("busy","Сервер занят подготовкой; повторите выгрузку позже",503)
            try:
                import print_io
                for sheet in spec["sheets"]:sheet["draft"]=draft
                # Право проверяется вновь после длительной печати перед выдачей файла.
                body=getattr(print_io,"render_"+fmt)(spec,server.REDLN,server.LGR_DASH,
                    self._frozen_tiles(self._path(rec,rid),state.get("rasterManifestSHA256"),draft))
                with A.access(server,A._actor(server,c),pid):pass
                return server._file(body,"application/pdf" if fmt=="pdf" else "application/vnd.openxmlformats-officedocument.presentationml.presentation",f"grado-sushpol.{fmt}")
            finally:HEAVY.release()
        raise P.PreparationError("invalid_input","Неизвестная команда подготовки",404)

    def post(self,c,server):
        req=c.obj();pid=str(req.get("projectId") or "")
        if c.route=="/api/preparation/start":return server._json(200,self.start(c,req))
        if c.route=="/api/preparation/cancel":
            rec,rid,value=self._record(c,pid,req.get("runId"))
            with A.access(server,A._actor(server,c),pid,True) as checked:
                if value.get("actorId")!=checked["actor"] and checked["role"] not in ("owner","admin"):
                    raise P.PreparationError("forbidden","Остановить чужой запуск может только владелец проекта",403)
                job=self.jobs.get(rid)
                if job:job["cancel"].set()
                return server._json(200,{"runId":rid,"cancelRequested":bool(job)})
        if c.route=="/api/preparation/field":return self.resolve_field(c,req)
        if c.route=="/api/preparation/photo":return self.replace_photo(c,req)
        if c.route.startswith("/api/panorama/"):return self.panorama(c,req)
        raise P.PreparationError("invalid_input","Неизвестная команда подготовки",404)

    def resolve_field(self,c,req):
        server=self.server;pid=str(req.get("projectId") or "")
        basis=str(req.get("basis") or "").strip()
        source=str(req.get("sourceKey") or "");key=str(req.get("objectKey") or "");field=str(req.get("field") or "")
        action=req.get("action","value")
        if not basis or len(basis)>2000 or not field or len(field)>200 or action not in ("value","allow_missing","not_applicable"):
            raise P.PreparationError("invalid_input","Укажите поле, основание и действие value/allow_missing/not_applicable",400)
        value=req.get("value")
        if action=="value" and (not isinstance(value,(str,int,float)) or isinstance(value,bool) or isinstance(value,float) and not math.isfinite(value) or len(str(value))>10000):
            raise P.PreparationError("invalid_input","Укажите текстовое или числовое значение",400)
        with A.access(server,A._actor(server,c),pid,True) as rec:
            if req.get("expectedProjectRevision")!=rec["revision"]:
                raise P.PreparationError("version_conflict","Проект изменён; перечитайте статус")
            project=rec["project"];state=_run_state(project)
            if not state:raise P.PreparationError("not_ready","Сначала запустите подготовку")
            found=next((f for f in C.features(project,source) if C.feature_key(f)==key),None)
            project_metric=not source and key=="project.metrics" and field.split(".")[0] in ("metrics","demolitionMetrics") and field.split(".")[-1] in ("residentialRatio","spp","publicSpp","industrialSpp","mixedSpp","nonResidentialAboveGround","jobs")
            if found is None and not project_metric:raise P.PreparationError("invalid_input","Объект источника не найден",404)
            scope={"sourceKey":source,"objectKey":key,"field":field}
            common={"scope":scope,"dependencyRevision":P.digest(project.get("territory") if project_metric else found),"basis":basis,"actor":rec["actor"],"createdAt":P.utcnow()}
            for name in ("overrides","decisions"):
                state[name]=[v for v in state.get(name,[]) if v.get("scope")!=scope]
            if action=="value":state["overrides"].append({**common,"state":"accepted","value":value})
            else:state["decisions"].append({**common,"code":action})
            state["lastExport"]=None
            for sheet in state["sheets"].values():sheet.update(state="stale",reasonCodes=["stale_dependency"])
            result=self._write(rec,project,rec["meta"])
        return server._json(200,{"projectRevision":result["projectRevision"],"scope":scope,"requiresPrepare":True})

    def replace_photo(self,c,req):
        server=self.server;pid=str(req.get("projectId") or "");photo_id=str(req.get("photoId") or "")
        try:raw=base64.b64decode(req.get("image") or "",validate=True)
        except (ValueError,TypeError):raise P.PreparationError("invalid_input","Изображение передано неверно",400) from None
        if not raw or len(raw)>20*2**20:raise P.PreparationError("invalid_input","Размер фотографии должен быть не больше 20 МиБ",413)
        try:
            with Image.open(io.BytesIO(raw)) as original:
                if original.width*original.height>32_000_000:raise ValueError("pixels")
                exif=original.getexif();gps=exif.get_ifd(34853) if exif else {}
                point=None;direction=None
                if gps.get(2) and gps.get(4):
                    def degrees(v):return float(v[0])+float(v[1])/60+float(v[2])/3600
                    point=[degrees(gps[4])*(-1 if gps.get(3)=="W" else 1),degrees(gps[2])*(-1 if gps.get(1)=="S" else 1)]
                if gps.get(16)=="T" and gps.get(17) is not None:direction=float(gps[17])
                image=ImageOps.exif_transpose(original).convert("RGB");image.thumbnail((1600,1600))
                out=io.BytesIO();image.save(out,"JPEG",quality=92,subsampling=0);w,h=image.size;image.close()
        except (ValueError,TypeError,OSError,ZeroDivisionError,Image.DecompressionBombError):
            raise P.PreparationError("invalid_input","Не удалось прочитать фотографию или её EXIF",400) from None
        with A.access(server,A._actor(server,c),pid,True) as rec:
            project=rec["project"];state=_run_state(project)
            if not state:raise P.PreparationError("not_ready","Сначала создайте мытищинский набор")
            found=None;target_sheet=None
            for sheet in project.get("album",{}).get("sheets",[]):
                if sheet.get("kind")!="photos":continue
                if target_sheet is None:target_sheet=sheet
                for item in sheet.get("photos") or []:
                    if item.get("id")==photo_id:found=item;target_sheet=sheet;break
                if found:break
            if found is None:
                prefix=state["instanceId"]+":photo:"
                suffix=photo_id.removeprefix(prefix)
                if not photo_id.startswith(prefix) or not suffix.isdigit() or not 0<=int(suffix)<64 or target_sheet is None:
                    raise P.PreparationError("invalid_input","Неизвестная позиция фотографии",404)
                found={"id":photo_id}
                target_sheet.setdefault("photos",[]).append(found)
            if req.get("point") is not None:point=req["point"]
            if req.get("azimuthDeg") is not None:direction=req["azimuthDeg"]
            if point is None and req.get("confirmPrevious"):point=found.get("at")
            if direction is None and req.get("confirmPrevious"):direction=found.get("dir")
            if (not isinstance(point,(list,tuple)) or len(point)!=2 or not all(type(v) in (int,float) and math.isfinite(v) for v in point)
                    or not (-180<=point[0]<=180 and -90<=point[1]<=90) or type(direction) not in (int,float) or not math.isfinite(direction)):
                raise P.PreparationError("invalid_input","Укажите координаты/направление либо явно подтвердите прежние",400)
            found.clear();found.update(id=photo_id,name=str(req.get("name") or "Свой снимок")[:200],source="own",
                    data=base64.b64encode(out.getvalue()).decode("ascii"),w=w,h=h,at=list(point),dir=direction%360)
            state["sheets"]["photos"].update(state="stale",reasonCodes=["stale_dependency"])
            state["lastExport"]=None
            result=self._write(rec,project,rec["meta"])
        return server._json(200,{"photoId":photo_id,"point":list(point),"azimuthDeg":direction%360,
                               "requiresPrepare":True,"projectRevision":result["projectRevision"]})

    def panorama(self,c,req):
        from panorama_io import get_frame
        server=self.server;pid=str(req.get("projectId") or "");rid=A._uuid(req.get("requestId"))
        with A.access(server,A._actor(server,c),pid,True) as rec:
            actor_id=rec["actor"]
        key=(pid,rid)
        with self.lock:
            frames=getattr(self,"frames",None)
            if frames is None:self.frames={};frames=self.frames
            if c.route=="/api/panorama/cancel":
                item=frames.get(key)
                if item and item["actorId"]==actor_id:item["cancel"].set()
                return server._json(200,{"requestId":rid,"cancelRequested":bool(item)})
            args={k:req.get(k) for k in ("candidate","target","azimuthDeg","photoId","runId","inputRevision")}
            for name in ("candidate","target"):
                p=args[name]
                if not isinstance(p,list) or len(p)!=2 or not all(type(v) in (int,float) and math.isfinite(v) for v in p) or not (-180<=p[0]<=180 and -90<=p[1]<=90):
                    raise P.PreparationError("invalid_input","Нужны координаты WGS84 [долгота,широта]",400)
            if args["azimuthDeg"] is not None and (type(args["azimuthDeg"]) not in (int,float) or not math.isfinite(args["azimuthDeg"])):
                raise P.PreparationError("invalid_input","Азимут должен быть конечным числом",400)
            signature=P.digest(args)
            if key in frames:
                item=frames[key]
                if item["actorId"]!=actor_id or item["signature"]!=signature:raise P.PreparationError("version_conflict","Запрос кадра уже имеет другие параметры")
                if item.get("expired"):raise P.PreparationError("result_expired","Кадр вытеснен из памяти; задайте новый requestId",410)
                if item.get("result"):return server._json(item.get("status",200),item["result"])
                raise P.PreparationError("busy","Этот кадр уже получается",503)
            # Не держать изображения неограниченно в памяти. Повтор после вытеснения требует нового requestId.
            for old in [k for k,v in frames.items() if v.get("finished") and time.monotonic()-v["finished"]>300]:frames[old].update(result=None,expired=True)
            completed=[k for k,v in frames.items() if v.get("finished")]
            for old in completed[:-3]:frames[old].update(result=None,expired=True)
            if len(frames)>=1000:raise P.PreparationError("budget_exceeded","Достигнут лимит запросов кадров процесса",429)
            item={"actorId":actor_id,"signature":signature,"cancel":threading.Event()};frames[key]=item
        try:
            result=asyncio.run(get_frame(args["candidate"],args["target"],server.CACHE,bearing=args["azimuthDeg"],cancel=item["cancel"]))
            with A.access(server,A._actor(server,c),pid,True):pass
            response={"projectId":pid,"requestId":rid,**{k:v for k,v in args.items() if k not in ("candidate","target","azimuthDeg")},**result}
            item["result"]=response
            return server._json(200,response)
        except server.hubmod.HubError:
            raise
        except Exception as e:
            code=getattr(e,"code","source_unavailable")
            response={"projectId":pid,"requestId":rid,"runId":args["runId"],"photoId":args["photoId"],"reasonCode":code,"error":str(e)[:300],"retryAfterAt":getattr(e,"retry_after_at",None)}
            item["result"]=response
            item["status"]=429 if code=="rate_limited" else 504 if code=="timeout" else 422
            return server._json(item["status"],response)
        finally:item["finished"]=time.monotonic()
