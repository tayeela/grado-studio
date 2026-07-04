"""Хранилище снимков — неизменяемые датированные выгрузки.

Снимок = каталог store/<id>/ с manifest.json и data.geojson. Дата и sha256
в манифесте фиксируют исходные данные на момент выгрузки (раздел ИРД,
ответ эксперту «откуда граница»). Повторное сохранение того же содержимого
идемпотентно; менять сохранённое нельзя — verify() ловит расхождение.
"""

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from .diff import diff as _diff, has_changes as _has_changes


class StoreError(RuntimeError):
    pass


class SnapshotStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        # save() сериализуется: стор — общий синглтон под ThreadingHTTPServer,
        # без блокировки exists()→mkdir() гонит (FileExistsError на
        # параллельном идентичном импорте) вместо идемпотентного возврата.
        self._lock = threading.Lock()

    def save(self, connector, result):
        data = json.dumps(
            {"type": "FeatureCollection", "features": result["features"]},
            ensure_ascii=False, sort_keys=True).encode("utf-8")
        sha = hashlib.sha256(data).hexdigest()
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sid = f"{connector.name}-{fetched_at[:10].replace('-', '')}-{sha[:8]}"
        target = self.root / sid
        manifest = {
            "id": sid, "connector": connector.name, "source": connector.source,
            "params": result["params"], "source_doc": result.get("source_doc"),
            "crs": result.get("crs", "EPSG:4326"), "notes": result.get("notes", []),
            "fetched_at": fetched_at, "count": len(result["features"]), "sha256": sha,
        }
        with self._lock:
            man_path = target / "manifest.json"
            if man_path.exists():
                if json.loads(man_path.read_text())["sha256"] == sha:
                    return sid  # идемпотентность: тот же контент — тот же снимок
                raise StoreError(f"коллизия идентификатора снимка {sid}")
            target.mkdir(exist_ok=True)
            (target / "data.geojson").write_bytes(data)
            # манифест — последним и атомарно: параллельный list()/latest()
            # (без блокировки) видит каталог валидным только целиком
            tmp = target / f".manifest.{os.getpid()}.tmp"
            tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            os.replace(tmp, man_path)
        return sid

    def manifest(self, sid):
        path = self.root / sid / "manifest.json"
        if not path.exists():
            raise StoreError(f"нет снимка {sid}")
        return json.loads(path.read_text(encoding="utf-8"))

    def features(self, sid):
        self.manifest(sid)
        data = (self.root / sid / "data.geojson").read_text(encoding="utf-8")
        return json.loads(data)["features"]

    def load(self, sid):
        return self.manifest(sid), self.features(sid)

    def verify(self, sid):
        m = self.manifest(sid)
        actual = hashlib.sha256((self.root / sid / "data.geojson").read_bytes()).hexdigest()
        if actual != m["sha256"]:
            raise StoreError(f"снимок {sid} изменён после сохранения (sha256 не совпадает)")
        return True

    def list(self, connector=None):
        out = []
        for p in sorted(self.root.iterdir()):
            if (p / "manifest.json").exists():
                m = json.loads((p / "manifest.json").read_text(encoding="utf-8"))
                if connector is None or m["connector"] == connector:
                    out.append(m)
        return sorted(out, key=lambda m: m["fetched_at"])

    def latest(self, connector, params=None):
        candidates = [m for m in self.list(connector)
                      if params is None or m["params"] == params]
        return candidates[-1] if candidates else None


class Subscriptions:
    """Подписки: «на этой территории следи за источником».

    check() делает свежий fetch, сравнивает с последним снимком и сохраняет
    новый только при изменениях — уведомление «на вашей территории изменился
    документ» в терминах архитектуры."""

    def __init__(self, store):
        self.store = store
        self.path = store.root / "subscriptions.json"

    def list(self):
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def add(self, connector_name, params):
        subs = self.list()
        entry = {"connector": connector_name, "params": params}
        if entry not in subs:
            subs.append(entry)
            self.path.write_text(json.dumps(subs, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
        return entry

    def check(self, connectors):
        reports = []
        for sub in self.list():
            conn = connectors[sub["connector"]]
            result = conn.fetch(**sub["params"])
            prev = self.store.latest(conn.name, result["params"])
            if prev is None:
                sid = self.store.save(conn, result)
                reports.append({**sub, "snapshot": sid, "initial": True, "diff": None})
                continue
            d = _diff(self.store.features(prev["id"]), result["features"])
            if _has_changes(d):
                sid = self.store.save(conn, result)
                reports.append({**sub, "snapshot": sid, "initial": False, "diff": d})
        return reports
