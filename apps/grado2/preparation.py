"""ГРАДО 2 · подтверждения получения, ревизии и безопасная публикация подготовки.

Общий контракт UI/MCP: площади проверяются в МСК; проект и metadata публикуются
через восстанавливаемый журнал. Проверки: tests/test_preparation.py.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from grado_connectors import crs
import numpy as np
from shapely import transform, union_all
from shapely.geometry import mapping, shape

RECIPE = "sushpol-mytishchi"
CAPABILITY = "sushpol-v1"
SCHEMA = 1
KINDS = ("title", "location", "district_ortho", "territory_ortho", "existing_use", "land_rights",
         "parcels_oks", "restrictions", "photos", "general_plan", "pzz", "planning_docs", "education", "healthcare")
LIMITS = {"layers": 100, "features": 50000, "parcels": 500, "buildings": 2000, "photos": 64,
          "pages": 200, "bytes": 160 * 2**20}
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_LOCK = threading.Lock()


class PreparationError(ValueError):
    """Типизированная причина остановки; не выдаёт ошибку за готовый пустой результат."""
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code, self.status = code, status


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _numbers(value):
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PreparationError("invalid_input", "Числа должны быть конечными", 400)
        return int(value) if value.is_integer() and abs(value) <= 2**53 - 1 else value
    if isinstance(value, dict):
        return {k: _numbers(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_numbers(v) for v in value]
    return value


def dump(value):
    return json.dumps(_numbers(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(dump(value)).hexdigest()


def body_hash(body):
    return hashlib.sha256(body).hexdigest()


def polygon(geojson):
    if isinstance(geojson, dict) and geojson.get("type") == "Feature":
        geojson = geojson.get("geometry")
    try:
        g = shape(geojson)
    except (TypeError, KeyError, ValueError, AttributeError):
        raise PreparationError("invalid_geometry", "Нужна полигональная граница территории", 400) from None
    if g.geom_type not in ("Polygon", "MultiPolygon") or g.is_empty or not g.is_valid:
        raise PreparationError("invalid_geometry", "Граница должна быть непустым валидным полигоном", 400)
    if not all(math.isfinite(v) for v in g.bounds):
        raise PreparationError("invalid_geometry", "В границе есть неконечные координаты", 400)
    return g


def project_territory(project):
    g = polygon(project.get("territory"))
    w, s, e, n = g.bounds
    if not (-180 <= w <= e <= 180 and -90 <= s <= n <= 90):
        raise PreparationError("invalid_geometry", "Координаты GeoJSON ожидаются в WGS84", 400)
    return g


def to_msk(geometry):
    return transform(geometry, lambda xy: np.array([crs.wgs84_to_msk(*p) for p in xy]))


def to_wgs(geometry):
    return transform(geometry, lambda xy: np.array([crs.msk_to_wgs84(*p) for p in xy]))


def coverage(area, checked_parts, sublayers):
    """Пересечение реально проверенных частей каждого подслоя, без подмены bbox объектов."""
    requested = to_msk(polygon(area))
    covered = requested
    for sub in sublayers:
        pieces = [to_msk(polygon(p["area"])) for p in checked_parts
                  if p.get("sublayer") == sub and p.get("outcome") in ("received", "empty")]
        covered = covered.intersection(union_all(pieces)) if pieces else requested.difference(requested)
    if not sublayers:
        covered = requested.difference(requested)
    missing = requested.difference(covered)
    ratio = min(1., max(0., covered.area / requested.area)) if requested.area else 0.
    return {"ratio": ratio, "complete": missing.area <= max(1e-6, requested.area * 1e-10),
            "missingAreaM2": missing.area, "missingArea": mapping(to_wgs(missing))}


def revisions(project, photos=None):
    p = copy.deepcopy(project)
    album = p.get("album") or {}
    meta = {k: v for k, v in (album.get("meta") or {}).items()
            if k not in ("sushpolPreparation", "peak")}
    state = (album.get("meta") or {}).get("sushpolPreparation") or {}
    if state.get("schemaVersion", SCHEMA) != SCHEMA:
        raise PreparationError("unsupported_schema", "Версия подготовки не поддерживается")
    dependencies = {}
    requests = state.get("requests") or {}
    for key, data in (p.get("data") or {}).items():
        value = {k: v for k, v in data.items() if k not in ("history", "fetched_at", "acquisitionRefs")}
        refs = []
        for rid in data.get("acquisitionRefs") or []:
            receipt = requests.get(rid)
            if receipt:
                clean = {k: v for k, v in receipt.items() if k not in
                         ("requestId", "runId", "checkedAt", "dataRevision")}
                clean["checkedParts"] = [{k: v for k, v in part.items() if k not in
                                          ("checkedAt", "originalRequestId")} for part in clean.get("checkedParts", [])]
                refs.append(clean)
        value["acquisition"] = sorted(refs, key=digest)
        dependencies[key] = digest(value)
    manual=[]
    all_photos=photos if photos is not None else [ph for sh in album.get("sheets") or [] if sh.get("kind")=="photos" for ph in sh.get("photos") or []]
    for sheet in album.get("sheets") or []:
        if sheet.get("recipeId")==RECIPE:
            auto=sheet.get("automatic") or {}
            item={k:sheet[k] for k in ("title","center","scale") if k in sheet and k in auto and sheet[k]!=auto[k]}
            item.update({k:sheet[k] for k in ("edits","items","manual") if sheet.get(k)})
            if item:manual.append({"id":sheet.get("id"),**item})
        else:
            manual.append({k:v for k,v in sheet.items() if k in ("id","title","center","scale","edits","items","radius_m","layout","manual")})
    own_photos=[{k:v for k,v in ph.items() if k not in ("number","downloadedAt")} for ph in all_photos if ph.get("source")!="yandex"]
    if all_photos:
        dependencies["__photos"]=digest([{k:v for k,v in ph.items() if k not in ("number","downloadedAt")} for ph in all_photos])
    base = digest({"territory": p.get("territory"), "coordinates": p.get("coordinates"), "meta": meta,
                   "layers": p.get("layers") or [], "manual": manual, "ownPhotos":own_photos,
                   "overrides": state.get("overrides", []), "decisions": state.get("decisions", [])})
    return {"baseInputsRevision": base, "dependencyRevisions": dependencies,
            "inputRevision": digest({"baseInputsRevision": base, "dependencyRevisions": dependencies})}


def new_state(instance_id=None):
    iid = instance_id or str(uuid.uuid4())
    return {"schemaVersion": SCHEMA, "recipeId": RECIPE, "recipeVersion": 1, "instanceId": iid,
            "generation": 0, "activeRun": None, "requests": {}, "decisions": [], "overrides": [],
            "numbering": {}, "lastExport": None,
            "sheets": {k: {"sheetId": f"{iid}:{k}", "kind": k, "state": "waiting", "reasonCodes": [],
                            "dependencyRevisions": {}, "inputRevision": None, "pageIds": [], "decisionIds": []}
                       for k in KINDS}}


def check_profile(project):
    data = project.get("data") or {}
    counts = {"layers": len(data), "features": sum(len((v.get("fc") or {}).get("features") or []) for v in data.values()),
              "parcels": len(((data.get("nspd.parcels") or {}).get("fc") or {}).get("features") or []),
              "buildings": len(((data.get("nspd.buildings") or {}).get("fc") or {}).get("features") or []),
              "pages": len((project.get("album") or {}).get("sheets") or []),
              "photos": sum(len(s.get("photos") or []) for s in (project.get("album") or {}).get("sheets") or []),
              "bytes": len(dump(project))}
    over = [k for k, v in counts.items() if v > LIMITS[k]]
    if over:
        raise PreparationError("budget_exceeded", "Превышен профиль подготовки: " + ", ".join(over), 413)
    return counts


def atomic_write(path, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".part")
    try:
        with tmp.open("xb") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        if os.name != "nt":
            fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        tmp.unlink(missing_ok=True)


class Transaction:
    """Пара project/metadata с roll-forward до чтения и CAS до публикации.

    Сервер передаёт разрешённые им пути после проверки доступа, клиент путей не задаёт.
    failpoint используется только тестами аварий между двумя заменами.
    """
    def __init__(self, project_path, meta_path, failpoint=None):
        self.project = Path(project_path).resolve()
        self.meta = Path(meta_path).resolve()
        self.root = self.meta.parent / (".preparation-txn-" + digest(str(self.project))[:16])
        self.pending = self.root / "pending.json"
        self.failpoint = failpoint or (lambda stage: None)
        with _LOCKS_LOCK:
            self.lock = _LOCKS.setdefault(str(self.project), threading.RLock())

    def _recover(self):
        if not self.pending.exists():
            return
        try:
            record = json.loads(self.pending.read_bytes())
            command_id = str(uuid.UUID(record["commandId"]))
            stage = self.root / command_id
            body, meta = (stage / "project.next").read_bytes(), (stage / "meta.next").read_bytes()
            if body_hash(body) != record["projectSHA256"] or body_hash(meta) != record["metaSHA256"]:
                raise ValueError("checksum")
        except (OSError, ValueError, KeyError, TypeError):
            raise PreparationError("recovery_failed", "Журнал подготовки повреждён: требуется восстановление контрольной версии", 503) from None
        atomic_write(self.project, body)
        self.failpoint("project_published")
        atomic_write(self.meta, meta)
        self.failpoint("metadata_published")
        self.pending.unlink()
        # Stage-файлы не удаляем до удаления журнала: повтор после падения обязан иметь оба файла.
        for p in stage.iterdir():
            p.unlink()
        stage.rmdir()

    @contextmanager
    def guard(self):
        with self.lock:
            self._recover()
            yield self

    def read(self):
        with self.guard():
            body = self.project.read_bytes()
            meta = json.loads(self.meta.read_bytes()) if self.meta.exists() else {}
            return body, meta

    def publish(self, body, metadata, command_id, expected_revision):
        command_id = str(uuid.UUID(command_id))
        json.loads(body)  # никогда не публиковать оборванный JSON
        with self.guard():
            old, old_meta = self.read()
            previous = (old_meta.get("preparationCommits") or {}).get(command_id)
            if previous:
                if previous["projectRevision"] != body_hash(body):
                    raise PreparationError("version_conflict", "Идентификатор команды уже использован с другим результатом")
                return previous
            if expected_revision != body_hash(old):
                raise PreparationError("version_conflict", "Проект изменён после начала подготовки")
            result = {"commandId": command_id, "projectRevision": body_hash(body), "committedAt": utcnow()}
            commits = dict(old_meta.get("preparationCommits") or {})
            commits[command_id] = result
            commits = dict(list(commits.items())[-64:])
            next_meta = {**metadata, "preparationCommits": commits}
            stage = self.root / command_id
            atomic_write(stage / "project.next", body)
            atomic_write(stage / "meta.next", dump(next_meta))
            self.failpoint("staged")
            atomic_write(self.pending, dump({"commandId": command_id, "baseRevision": expected_revision,
                         "projectSHA256": body_hash(body), "metaSHA256": digest(next_meta)}))
            self.failpoint("journal_published")
            self._recover()
            return result

    def checkpoint(self, expected_revision):
        with self.guard():
            body, _ = self.read()
            if body_hash(body) != expected_revision:
                raise PreparationError("version_conflict", "Проект изменён перед контрольной версией")
            cid = str(uuid.uuid4())
            atomic_write(self.root / "checkpoints" / (cid + ".grado2"), body)
            return {"checkpointId": cid, "projectRevision": expected_revision, "contentSHA256": body_hash(body)}

    def lease(self, action, run_id, owner, command_id, lease_id=None, expected_revision=None, now=None):
        now = time.time() if now is None else now
        with self.guard():
            meta = json.loads(self.meta.read_bytes()) if self.meta.exists() else {}
            lease = meta.get("preparationLease") or {}
            if action == "acquire":
                if lease.get("commandId") == command_id and lease.get("expiresAt", 0) > now:
                    if (lease.get("runId"), lease.get("ownerClientId")) != (run_id, owner):
                        raise PreparationError("version_conflict", "Команда принадлежит другому запуску")
                    return copy.deepcopy(lease)
                if expected_revision != body_hash(self.project.read_bytes()) or lease.get("expiresAt", 0) > now:
                    raise PreparationError("version_conflict", "Проект уже занят либо изменён")
                lease = {"leaseId": str(uuid.uuid4()), "runId": run_id, "ownerClientId": owner,
                         "commandId": command_id, "expiresAt": now + 30}
            elif action in ("renew", "release"):
                if action == "release" and not lease:
                    return {"released": False}
                if (lease.get("leaseId"), lease.get("runId"), lease.get("ownerClientId")) != (lease_id, run_id, owner):
                    raise PreparationError("version_conflict", "Право на запуск принадлежит другому клиенту")
                if action == "renew":
                    if lease.get("expiresAt", 0) <= now:
                        raise PreparationError("version_conflict", "Срок права на запуск истёк")
                    if lease.get("renewCommandId") == command_id:
                        return copy.deepcopy(lease)
                    lease = {**lease, "expiresAt": now + 30, "renewCommandId": command_id}
                else:
                    meta.pop("preparationLease", None)
                    atomic_write(self.meta, dump(meta))
                    return {"released": True}
            else:
                raise PreparationError("invalid_input", "Неизвестное действие с правом запуска", 400)
            meta["preparationLease"] = lease
            atomic_write(self.meta, dump(meta))
            return copy.deepcopy(lease)


def receipt(source_key, bbox, layer, error, expected_sublayers, run_id, request_id):
    """Неподтверждённый или отсутствующий ответ не становится successfully empty."""
    from shapely.geometry import box
    requested = mapping(box(*bbox))
    proof = (layer or {}).get("acquisition") or {}
    parts = [{**p,"originalRequestId":request_id} for p in proof.get("checkedParts") or []]
    result = coverage(requested,parts,[str(s) for s in expected_sublayers])
    reason = proof.get("reasonCode")
    if error:
        state,reason=("partial" if parts else "failed"),"source_unavailable"
    elif not proof:
        state,reason="failed","unknown_outcome"
    elif not result["complete"]:
        state,reason="partial","partial_coverage"
    elif proof.get("state")=="partial":
        state,reason="partial",reason or "partial_coverage"
    else:
        state="received" if ((layer or {}).get("features") or {}).get("features") else "empty"
    return {"requestId":request_id,"runId":run_id,"sourceKey":source_key,"requestedArea":requested,
            "checkedParts":parts,"expectedSublayers":[str(v) for v in expected_sublayers],"state":state,"checkedAt":utcnow(),"dataDate":proof.get("dataDate"),
            "reasonCode":reason,"layerIds":[source_key] if layer else [],"dataRevision":None,
            "coverageRatio":result["ratio"],"errorMessage":str(error)[:350] if error else None}
