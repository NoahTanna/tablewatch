"""SQLite storage. Stdlib only.

tables: current state, one JSON row per table.
visits: one row per finished party (times only, no people data), used for
        tonight's averages on the dashboard.
"""
import json
import sqlite3


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(
            """CREATE TABLE IF NOT EXISTS table_state (id TEXT PRIMARY KEY, data TEXT NOT NULL);
               CREATE TABLE IF NOT EXISTS visits (
                   table_id TEXT, seated_at REAL, left_at REAL,
                   first_service REAL, empty_before REAL);
               CREATE INDEX IF NOT EXISTS visits_left ON visits(left_at);"""
        )
        self.conn.commit()

    def ensure(self, table):
        self.conn.execute("INSERT OR IGNORE INTO table_state VALUES (?, ?)",
                          (table["id"], json.dumps(table)))
        self.conn.commit()

    def get(self, table_id):
        row = self.conn.execute("SELECT data FROM table_state WHERE id = ?", (table_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def all(self):
        return [json.loads(r[0]) for r in self.conn.execute("SELECT data FROM table_state ORDER BY rowid")]

    def save(self, table):
        self.conn.execute("UPDATE table_state SET data = ? WHERE id = ?", (json.dumps(table), table["id"]))
        self.conn.commit()

    def remove_except(self, ids):
        q = ",".join("?" * len(ids))
        self.conn.execute(f"DELETE FROM table_state WHERE id NOT IN ({q})", list(ids))
        self.conn.commit()

    def add_visit(self, v):
        self.conn.execute("INSERT INTO visits VALUES (:table_id, :seated_at, :left_at, :first_service, :empty_before)", v)
        self.conn.commit()

    def visits_since(self, t):
        cur = self.conn.execute("SELECT table_id, seated_at, left_at, first_service, empty_before "
                                "FROM visits WHERE left_at >= ?", (t,))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur]
