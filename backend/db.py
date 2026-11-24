"""SQLite storage for current table state (one row per table). Stdlib only."""
import sqlite3


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS tables (
                id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                unattended_since REAL,
                updated_at REAL
            )"""
        )
        self.conn.commit()

    def ensure(self, table):
        self.conn.execute(
            "INSERT OR IGNORE INTO tables VALUES (:id, :state, :unattended_since, :updated_at)", table
        )
        self.conn.commit()

    def get(self, table_id):
        row = self.conn.execute("SELECT * FROM tables WHERE id = ?", (table_id,)).fetchone()
        return dict(row) if row else None

    def all(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM tables ORDER BY rowid")]

    def save(self, table):
        self.conn.execute(
            "UPDATE tables SET state = :state, unattended_since = :unattended_since, "
            "updated_at = :updated_at WHERE id = :id",
            table,
        )
        self.conn.commit()

    def remove_except(self, ids):
        q = ",".join("?" * len(ids))
        self.conn.execute(f"DELETE FROM tables WHERE id NOT IN ({q})", list(ids))
        self.conn.commit()
