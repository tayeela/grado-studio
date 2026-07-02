"""Сессия — единственный путь изменения модели.

Инструмент → команда (insert/update/delete) → дельты → журнал → подписчики.
Undo/redo — реплей обращённых дельт; ветка варианта — форк от main с
переключением через реплей журнала. Подписчики получают множество кодов
затронутых слоёв (в C++ ядре на этом месте — граф зависимостей и фоновый
пул; в эталонной реализации пересчёт синхронный).
"""

from contextlib import contextmanager

from . import deltas as D
from .journal import MAIN, Journal, JournalError


class Session:
    def __init__(self, project):
        self.project = project
        self.journal = Journal(project.conn)
        self._subscribers = []
        self._bulk = None

    # --- подписка -------------------------------------------------------

    def subscribe(self, callback):
        """callback(layer_codes: set[str]) — после каждого изменения модели."""
        self._subscribers.append(callback)

    def _notify(self, layer_codes):
        for fn in self._subscribers:
            fn(set(layer_codes))

    # --- команды --------------------------------------------------------

    def _commit(self, title, applied_deltas):
        if self._bulk is not None:
            self._bulk.extend(applied_deltas)
            return
        self.journal.append(self.journal.branch, title, applied_deltas)
        self._notify(D.affected_layers(applied_deltas))

    @contextmanager
    def bulk(self, title):
        """Собирает команды в одну запись журнала (импорт = один undo).

        При исключении внутри блока уже применённые дельты откатываются —
        пакет атомарен."""
        if self._bulk is not None:
            raise JournalError("пакетный коммит уже открыт")
        self._bulk = []
        try:
            yield
            deltas = self._bulk
        except BaseException:
            for d in reversed(self._bulk):
                D.apply(self.project, D.invert(d))
            raise
        finally:
            self._bulk = None
        if deltas:
            self.journal.append(self.journal.branch, title, deltas)
            self._notify(D.affected_layers(deltas))

    def insert_feature(self, code, geom, attrs=None, source="manual",
                       source_date=None, source_doc=None, title=None):
        layer = self.project.layer(code)
        fid = layer.add_feature(geom, attrs, source, source_date, source_doc)
        after = D.snapshot(layer.get_feature(fid))
        self._commit(title or f"добавление объекта в {code}",
                     [{"op": "insert", "layer": code, "fid": fid,
                       "before": None, "after": after}])
        return fid

    def update_feature(self, code, fid, geom=None, attrs=None, title=None):
        layer = self.project.layer(code)
        feature = layer.get_feature(fid)
        if feature is None:
            raise JournalError(f"в слое {code} нет объекта {fid}")
        before = D.snapshot(feature)
        after = dict(before, attrs=dict(before["attrs"]))
        if geom is not None:
            after["geom"] = geom
        if attrs:
            after["attrs"].update(attrs)
        layer.set_feature(fid, after)
        after = D.snapshot(layer.get_feature(fid))
        self._commit(title or f"правка объекта {fid} в {code}",
                     [{"op": "update", "layer": code, "fid": fid,
                       "before": before, "after": after}])

    def delete_feature(self, code, fid, title=None):
        layer = self.project.layer(code)
        feature = layer.get_feature(fid)
        if feature is None:
            raise JournalError(f"в слое {code} нет объекта {fid}")
        before = D.snapshot(feature)
        layer.delete_feature(fid)
        self._commit(title or f"удаление объекта {fid} из {code}",
                     [{"op": "delete", "layer": code, "fid": fid,
                       "before": before, "after": None}])

    # --- undo / redo ----------------------------------------------------

    def _replay(self, entry_deltas, inverse=False):
        ds = [D.invert(d) for d in reversed(entry_deltas)] if inverse else entry_deltas
        for d in ds:
            D.apply(self.project, d)
        return D.affected_layers(ds)

    @property
    def branch(self):
        return self.journal.branch

    def can_undo(self):
        b = self.journal.branch
        return self.journal.prev_entry(b, self.journal.head(b)) is not None

    def can_redo(self):
        b = self.journal.branch
        return self.journal.next_entry(b, self.journal.head(b)) is not None

    def undo(self):
        b = self.journal.branch
        entry = self.journal.prev_entry(b, self.journal.head(b))
        if entry is None:
            return None
        affected = self._replay(entry["deltas"], inverse=True)
        prev = self.journal.prev_entry(b, entry["seq"] - 1)
        self.journal.set_head(b, prev["seq"] if prev else self.journal.base(b))
        self._notify(affected)
        return entry["title"]

    def redo(self):
        b = self.journal.branch
        entry = self.journal.next_entry(b, self.journal.head(b))
        if entry is None:
            return None
        affected = self._replay(entry["deltas"])
        self.journal.set_head(b, entry["seq"])
        self._notify(affected)
        return entry["title"]

    def log(self):
        b = self.journal.branch
        head = self.journal.head(b)
        rows = self.journal.entries(b, self.journal.base(b), 2 ** 62)
        return [{"seq": r["seq"], "title": r["title"], "ts": r["ts"],
                 "applied": r["seq"] <= head} for r in rows]

    # --- ветки вариантов --------------------------------------------------

    def create_branch(self, name):
        """Форк от текущей позиции main (вариант концепции)."""
        if self.journal.branch != MAIN:
            raise JournalError("ветка создаётся только от main")
        self.journal.create_branch(name, self.journal.head(MAIN))
        return name

    def checkout(self, target):
        cur = self.journal.branch
        if target == cur:
            return
        affected = set()
        # 1. откатить записи текущей ветки до её базы
        if cur != MAIN:
            for entry in self.journal.entries(
                    cur, self.journal.base(cur), self.journal.head(cur), desc=True):
                affected |= self._replay(entry["deltas"], inverse=True)
            pos_main = self.journal.base(cur)
        else:
            pos_main = self.journal.head(MAIN)
        # 2. пройти по main до базы целевой ветки (или до головы main)
        target_pos = self.journal.head(MAIN) if target == MAIN else self.journal.base(target)
        if pos_main > target_pos:
            for entry in self.journal.entries(MAIN, target_pos, pos_main, desc=True):
                affected |= self._replay(entry["deltas"], inverse=True)
        elif pos_main < target_pos:
            for entry in self.journal.entries(MAIN, pos_main, target_pos):
                affected |= self._replay(entry["deltas"])
        # 3. применить записи целевой ветки
        if target != MAIN:
            for entry in self.journal.entries(
                    target, self.journal.base(target), self.journal.head(target)):
                affected |= self._replay(entry["deltas"])
        self.journal.set_branch(target)
        if affected:
            self._notify(affected)
