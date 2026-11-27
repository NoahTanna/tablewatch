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
                   first_service REAL, empty_before REAL, cleared_at REAL, went_red INTEGER);
               CREATE INDEX IF NOT EXISTS visits_left ON visits(left_at);"""
        )
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(visits)")]
        for col, kind in (("cleared_at", "REAL"), ("went_red", "INTEGER")):  # databases from before reports
            if col not in cols:
                self.conn.execute(f"ALTER TABLE visits ADD COLUMN {col} {kind}")
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
        v = {"cleared_at": None, "went_red": False, **v}
        self.conn.execute("INSERT INTO visits (table_id, seated_at, left_at, first_service, empty_before, cleared_at, went_red) "
                          "VALUES (:table_id, :seated_at, :left_at, :first_service, :empty_before, :cleared_at, :went_red)", v)
        self.conn.commit()

    def visits_since(self, t):
        return self.visits_between(t, float("inf"))

    def visits_between(self, start, end):
        """Parties that sat down in [start, end)."""
        cur = self.conn.execute("SELECT table_id, seated_at, left_at, first_service, empty_before, cleared_at, went_red "
                                "FROM visits WHERE seated_at >= ? AND seated_at < ? ORDER BY seated_at", (start, end))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur]
