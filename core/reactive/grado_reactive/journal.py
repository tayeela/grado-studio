"""Журнал дельт — персистентный лог изменений внутри файла проекта.

Таблицы grado_journal / grado_branches живут в том же GeoPackage: файл
проекта остаётся самодостаточным (инвариант local-first). Один журнал
закрывает undo/redo, автосейв (состояние = журнал), ветки вариантов
и — позже — синхронизацию с PostGIS-хабом.

Позиции: head(ветка) — seq последней применённой записи ветки; для ветки
без применённых записей head равен её base_seq (у main база 0).
"""

import json

from .deltas import invert as _invert  # noqa: F401  (реэкспорт для удобства)

MAIN = "main"


class JournalError(ValueError):
    pass


class Journal:
    def __init__(self, conn):
        self.conn = conn
        self._ensure_tables()

    def _ensure_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS grado_journal (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                branch TEXT NOT NULL,
                ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                title TEXT NOT NULL,
                deltas TEXT NOT NULL)""")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS grado_branches (
                name TEXT PRIMARY KEY,
                base_seq INTEGER NOT NULL,
                created TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")
        self.conn.execute(
            "INSERT OR IGNORE INTO grado_meta VALUES ('journal_branch', ?)", (MAIN,))
        self.conn.execute(
            "INSERT OR IGNORE INTO grado_meta VALUES ('journal_heads', '{}')")
        self.conn.commit()

    def _meta(self, key):
        return self.conn.execute(
            "SELECT value FROM grado_meta WHERE key=?", (key,)).fetchone()[0]

    def _set_meta(self, key, value):
        self.conn.execute("UPDATE grado_meta SET value=? WHERE key=?", (value, key))
        self.conn.commit()

    @property
    def branch(self):
        return self._meta("journal_branch")

    def set_branch(self, name):
        if name != MAIN and name not in self.branches():
            raise JournalError(f"нет ветки {name!r}")
        self._set_meta("journal_branch", name)

    def branches(self):
        return {r[0]: r[1] for r in
                self.conn.execute("SELECT name, base_seq FROM grado_branches")}

    def base(self, branch):
        if branch == MAIN:
            return 0
        branches = self.branches()
        if branch not in branches:
            raise JournalError(f"нет ветки {branch!r}")
        return branches[branch]

    def create_branch(self, name, base_seq):
        if name == MAIN or name in self.branches():
            raise JournalError(f"ветка {name!r} уже существует")
        self.conn.execute(
            "INSERT INTO grado_branches (name, base_seq) VALUES (?,?)", (name, base_seq))
        self.conn.commit()

    def head(self, branch):
        heads = json.loads(self._meta("journal_heads"))
        return heads.get(branch, self.base(branch))

    def set_head(self, branch, seq):
        heads = json.loads(self._meta("journal_heads"))
        heads[branch] = seq
        self._set_meta("journal_heads", json.dumps(heads))

    def entries(self, branch, above, up_to, desc=False):
        """Записи ветки с above < seq <= up_to."""
        order = "DESC" if desc else "ASC"
        rows = self.conn.execute(
            f"SELECT seq, title, deltas, ts FROM grado_journal "
            f"WHERE branch=? AND seq>? AND seq<=? ORDER BY seq {order}",
            (branch, above, up_to))
        return [{"seq": r[0], "title": r[1], "deltas": json.loads(r[2]), "ts": r[3]}
                for r in rows]

    def next_entry(self, branch, after_seq):
        row = self.conn.execute(
            "SELECT seq, title, deltas FROM grado_journal "
            "WHERE branch=? AND seq>? ORDER BY seq LIMIT 1", (branch, after_seq)).fetchone()
        if row is None:
            return None
        return {"seq": row[0], "title": row[1], "deltas": json.loads(row[2])}

    def prev_entry(self, branch, up_to_seq):
        base = self.base(branch)
        row = self.conn.execute(
            "SELECT seq, title, deltas FROM grado_journal "
            "WHERE branch=? AND seq>? AND seq<=? ORDER BY seq DESC LIMIT 1",
            (branch, base, up_to_seq)).fetchone()
        if row is None:
            return None
        return {"seq": row[0], "title": row[1], "deltas": json.loads(row[2])}

    def append(self, branch, title, deltas):
        head = self.head(branch)
        # новая запись после undo отсекает redo-хвост (линейная история)
        if branch == MAIN:
            orphans = [n for n, b in self.branches().items() if b > head]
            if orphans and self.next_entry(branch, head):
                raise JournalError(
                    f"отсечение redo-хвоста main осиротит ветки {sorted(orphans)}")
        self.conn.execute(
            "DELETE FROM grado_journal WHERE branch=? AND seq>?", (branch, head))
        cur = self.conn.execute(
            "INSERT INTO grado_journal (branch, title, deltas) VALUES (?,?,?)",
            (branch, title, json.dumps(deltas, ensure_ascii=False)))
        self.conn.commit()
        self.set_head(branch, cur.lastrowid)
        return cur.lastrowid
