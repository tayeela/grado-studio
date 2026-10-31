"""ГРАДО 2 · серверные команды общей подготовки и доступа агента.

Guard проверяет вход; ProjectAccess повторно проверяет текущие права проекта под
блокировкой. UI и MCP используют одни команды. Проверки: tests/test_preparation_api.py.
"""
from __future__ import annotations

import asyncio
import base64
import copy
import json
import math
import sys
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

import preparation as P

CAP_HEADER = "X-Grado-Project-Capabilities"


def local_transaction(server, name):
    path = server.project_path(name)
    meta = server.PROJECTS/".preparation"/(P.digest(path.name)+".json")
    return P.Transaction(path, meta)


@contextmanager
def access(server, actor, project_id, edit=False, metadata_only=False):
    """actor получен только от Ctx.who, не из JSON/ownerClientId."""
    if server.HUB:
        with server.HUB.lock:
            login, meta, role = server.HUB._require(actor, project_id, "edit" if edit else "read")
            root = server.HUB._pdir(project_id)
            tx = P.Transaction(root/"project.grado2",root/"meta.json")
            with tx.guard():
                if metadata_only:
                    yield {"meta":json.loads(tx.meta.read_bytes()),"tx":tx,"actor":login,"role":role}
                    return
                body, metadata = tx.read()
                yield {"body":body,"project":json.loads(body),"meta":metadata,"tx":tx,
                       "actor":login,"revision":P.body_hash(body),"hubRevision":meta["rev"],"role":role}
    else:
        with server._SAVE_LOCK:
            tx = local_transaction(server,project_id)
            with tx.guard():
                if metadata_only:
                    if not tx.project.exists():raise P.PreparationError("project_not_found","Проект не найден",404)
                    yield {"meta":json.loads(tx.meta.read_bytes()) if tx.meta.exists() else {},"tx":tx,"actor":"local","role":"owner"}
                    return
                try:
                    body, metadata = tx.read()
                except FileNotFoundError:
                    raise P.PreparationError("project_not_found","Проект не найден",404) from None
                yield {"body":body,"project":json.loads(body),"meta":metadata,"tx":tx,
                       "actor":"local","revision":P.body_hash(body),"hubRevision":None,"role":"owner"}


def require_capabilities(headers, metadata, project=None):
    required = metadata.get("requiredCapabilities") or []
    if not required:
        return
    available = {v.strip() for v in (headers.get(CAP_HEADER) or "").split(",")}
    if not set(required) <= available:
        raise P.PreparationError("unsupported_schema","Этот проект требует клиента с поддержкой нового набора")
    if project is not None:
        state = ((project.get("album") or {}).get("meta") or {}).get("sushpolPreparation")
        if not isinstance(state,dict) or state.get("schemaVersion")!=P.SCHEMA:
            raise P.PreparationError("unsupported_schema","Нельзя сохранить проект с потерянными или неизвестными данными подготовки")


def summary(project_id, record):
    project=record["project"]
    state=((project.get("album") or {}).get("meta") or {}).get("sushpolPreparation")
    if state:
        state={**{k:v for k,v in state.items() if k not in ("requests","decisions","overrides","deferredSources")},
               "deferredSources":[{k:v for k,v in item.items() if k!="requestedArea"} for item in state.get("deferredSources",[])],
               "decisionsCount":len(state.get("decisions") or []),"overridesCount":len(state.get("overrides") or []),
               "requests":[{k:v for k,v in receipt.items() if k in
                  ("requestId","sourceKey","state","reasonCode","checkedAt","dataDate","layerIds","errorMessage")}
                  for receipt in (state.get("requests") or {}).values()]}
    if state and state.get("activeRun"):
        run=state["activeRun"];rid=run.get("runId")
        persisted=(record["meta"].get("preparationRuns") or {}).get(rid)
        if persisted:run.update({k:v for k,v in persisted.items() if k in ("state","phase","ready","progress","report")})
    territory=project.get("territory")
    return {"projectId":project_id,"name":project.get("name") or project_id,"projectRevision":record["revision"],
            "territory": {"bounds":list(P.project_territory(project).bounds)} if territory else None,
            "layers":[{"id":k,"title":v.get("title",k),"count":len((v.get("fc") or {}).get("features") or []),
                       "acquisitionRefs":v.get("acquisitionRefs",[])} for k,v in (project.get("data") or {}).items()],
            "sheets":[{"id":v.get("id"),"title":v.get("title"),"kind":v.get("mytishchiKind") or v.get("kind"),
                       "photos":[{k:p.get(k) for k in ("id","name","source","at","dir","reasonCode")} for p in v.get("photos") or []]}
                      for v in (project.get("album") or {}).get("sheets") or []],
            "preparation":copy.deepcopy(state)}


def create_project(server,c,req):
    name=str(req.get("name") or "").strip()
    geo=req.get("territory")
    coordinates=req.get("coordinates","wgs84")
    if coordinates not in ("msk","wgs84"):
        raise P.PreparationError("invalid_input","Укажите msk или wgs84",400)
    geometry=P.polygon(geo)
    if coordinates=="msk":geometry=P.to_wgs(geometry)
    from shapely.geometry import mapping
    project={"format":"grado2","version":2,"name":name,"territory":{"type":"Feature","geometry":mapping(geometry),"properties":{}},
             "checked":[],"layers":[],"data":{},"views":[],"groups":[],"imports":{},"graph":{},
             "album":{"meta":{"sushpolPreparation":P.new_state(),"requiredCapabilities":[P.CAPABILITY]},"sheets":[]}}
    P.project_territory(project)
    P.check_profile(project)
    if server.HUB:
        out=server.HUB.create_project(c.who(),name,project)
        project_id=out["id"]
    else:
        server.project_path(name)
        with server._SAVE_LOCK:
            if server.project_path(name).exists():
                raise P.PreparationError("version_conflict","Проект с таким именем уже есть")
            server.save_project(name,P.dump(project),capabilities={CAP_HEADER:P.CAPABILITY})
        project_id=name
    with access(server,c.who() if server.HUB else None,project_id,True) as record:
        metadata={**record["meta"],"requiredCapabilities":[P.CAPABILITY]}
        P.atomic_write(record["tx"].meta,P.dump(metadata))
        return summary(project_id,{**record,"meta":metadata})


def _actor(server,c):
    return c.who() if server.HUB else None


def _uuid(value):
    try:return str(uuid.UUID(str(value)))
    except (ValueError,TypeError,AttributeError):
        raise P.PreparationError("invalid_input","Нужен UUID идентификатора команды/запуска",400) from None


def get(c,server):
    if c.route=="/api/agent/health":
        return server._json(200,{"version":server.VERSION,"protocolVersion":1,"recipes":[P.RECIPE],
                                 "hub":bool(server.HUB),"experimental":True})
    if c.route=="/api/agent/projects":
        values=server.HUB.list_projects(c.who()) if server.HUB else server.list_projects()
        return server._json(200,{"projects":values})
    project_id=c.q("projectId")
    with access(server,_actor(server,c),project_id) as record:
        if c.route=="/api/preparation/revision":
            return server._json(200,{"projectRevision":record["revision"],**P.revisions(record["project"])})
        if c.route=="/api/preparation/commit-status":
            result=(record["meta"].get("preparationCommits") or {}).get(c.q("commandId"))
            return server._json(200,{"state":"committed" if result else "not_committed","result":result})
        if c.route=="/api/preparation/status":
            result=summary(project_id,record)
            # Процесс не помнит прежний run: его нельзя объявить всё ещё исполняющимся.
            state=result.get("preparation") or {}
            run=state.get("activeRun") or {}
            if run and not c.q("runId") and not c.q("commandId"):
                from sushpol_jobs import service
                live=service(server).jobs.get(run.get("runId"))
                if live:run.update({k:copy.deepcopy(live[k]) for k in ("state","phase","ready","report","progress") if k in live})
                elif run.get("state")=="running":run["state"]="interrupted"
            if not c.q("runId") and not c.q("commandId"):
                return server._json(200,result)
    from sushpol_jobs import service
    return service(server).get(c,server)


def post(c,server):
    req=c.obj()
    if c.route=="/api/agent/project":
        return server._json(200,create_project(server,c,req))
    project_id=str(req.get("projectId") or "")
    actor=_actor(server,c)
    with access(server,actor,project_id,True) as record:
        require_capabilities(c.headers,record["meta"])
        if c.route=="/api/preparation/revision":
            return server._json(200,{"projectRevision":record["revision"],**P.revisions(record["project"])})
        if c.route=="/api/preparation/lease":
            owner=(record["actor"]+":"+str(req.get("ownerClientId") or ""))[:400]
            result=record["tx"].lease(req.get("action"),_uuid(req.get("runId")),owner,_uuid(req.get("commandId")),
                    req.get("leaseId"),req.get("expectedProjectRevision"))
            return server._json(200,{"ack":True,"projectId":project_id,**result})
        if c.route=="/api/preparation/checkpoint":
            expected=req.get("expectedProjectRevision")
            if expected!=record["revision"]:
                raise P.PreparationError("version_conflict","Проект изменён перед снимком")
            return server._json(200,record["tx"].checkpoint(expected))
    from sushpol_jobs import service
    return service(server).post(c,server)


def answer(c,server):
    try:
        return get(c,server) if c.method in ("GET","HEAD") else post(c,server)
    except P.PreparationError as e:
        return server._json(e.status,{"error":str(e),"reasonCode":e.code})
    except server.hubmod.HubError as e:
        return server._json(e.status,{"error":e.message if e.status<500 else server.INTERNAL_ERROR})
