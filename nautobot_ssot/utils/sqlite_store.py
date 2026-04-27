"""SQLite-backed store for streaming DiffSync syncs.

Replaces the in-memory `Diff` tree + dual `Adapter.store` dicts with four
flat tables on a SQLite file (or `:memory:` connection):

    source_records   — rows dumped from src_adapter.dict()
    dest_records     — rows dumped from dst_adapter.dict()
    visited_keys     — keys touched during diff (used to compute orphans)
    diff_results     — one row per CREATE / UPDATE / DELETE action

Why SQLite, not Redis: no extra service, set ops via SQL, smaller per-row
overhead than Python objects. See `streaming_differ.py` for how rows are
walked, and `bulk_syncer.py` for how `diff_results` is replayed.

The store is generic across integrations — only requires `adapter.top_level`
plus `model._modelname` / `_identifiers` / `_attributes` / `_children`
metadata, which is part of the DiffSync contract.
"""

import json
import os
import sqlite3
import tempfile
from typing import Iterable, Optional


class DiffSyncStore:
    """Owns the SQLite connection and table schema used by the streaming pipeline.

    Use :memory: to keep everything resident (still cheaper than Python objects),
    or pass `path=` for a file the user can inspect after a failed run.
    """

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS source_records (
        model_type TEXT NOT NULL,
        unique_key TEXT NOT NULL,
        identifiers TEXT NOT NULL,        -- JSON dict
        attrs TEXT NOT NULL,              -- JSON dict
        parent_type TEXT,                 -- NULL for top-level
        parent_key TEXT,                  -- NULL for top-level
        tree_depth INTEGER NOT NULL DEFAULT 0,
        type_order INTEGER NOT NULL,      -- index in adapter.top_level
        PRIMARY KEY (model_type, unique_key)
    );

    CREATE TABLE IF NOT EXISTS dest_records (
        model_type TEXT NOT NULL,
        unique_key TEXT NOT NULL,
        identifiers TEXT NOT NULL,
        attrs TEXT NOT NULL,
        parent_type TEXT,
        parent_key TEXT,
        tree_depth INTEGER NOT NULL DEFAULT 0,
        type_order INTEGER NOT NULL,
        PRIMARY KEY (model_type, unique_key)
    );

    CREATE INDEX IF NOT EXISTS idx_source_type_order
        ON source_records (type_order, tree_depth);

    CREATE INDEX IF NOT EXISTS idx_dest_type_order
        ON dest_records (type_order, tree_depth);

    CREATE TABLE IF NOT EXISTS visited_keys (
        model_type TEXT NOT NULL,
        unique_key TEXT NOT NULL,
        PRIMARY KEY (model_type, unique_key)
    );

    CREATE TABLE IF NOT EXISTS diff_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_type TEXT NOT NULL,
        unique_key TEXT NOT NULL,
        action TEXT NOT NULL,             -- 'create' | 'update' | 'delete'
        identifiers TEXT NOT NULL,
        new_attrs TEXT,                   -- JSON dict (CREATE/UPDATE) or NULL (DELETE)
        old_attrs TEXT,                   -- JSON dict (UPDATE/DELETE) or NULL (CREATE)
        tree_depth INTEGER NOT NULL DEFAULT 0,
        type_order INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_diff_action_order
        ON diff_results (action, type_order, tree_depth);
    """

    def __init__(self, path: Optional[str] = None):
        """Open the SQLite connection.

        Args:
            path: ":memory:" (default if None), or a file path. A temp file
                  is auto-created if path is the literal string "auto".
        """
        if path is None:
            path = ":memory:"
        elif path == "auto":
            fd, path = tempfile.mkstemp(prefix="ssot_diff_", suffix=".sqlite")
            os.close(fd)
        self.path = path
        # check_same_thread=False because the pipeline can call from different
        # threads when wired into a Job (Celery). Single connection, never
        # shared concurrently — guarded by the caller.
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=MEMORY;")
        self.conn.execute("PRAGMA synchronous=OFF;")
        self.conn.executescript(self.SCHEMA_SQL)

    # ------------------------------------------------------------------
    # Bulk dump helpers
    # ------------------------------------------------------------------

    def insert_records(self, table: str, rows: Iterable[tuple]) -> int:
        """Insert rows into source_records or dest_records via executemany.

        Each row tuple: (model_type, unique_key, identifiers_json, attrs_json,
                         parent_type, parent_key, tree_depth, type_order)
        """
        if table not in ("source_records", "dest_records"):
            raise ValueError(f"insert_records: unsupported table {table!r}")
        sql = f"""
        INSERT OR REPLACE INTO {table}
            (model_type, unique_key, identifiers, attrs,
             parent_type, parent_key, tree_depth, type_order)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        cur = self.conn.cursor()
        cur.executemany(sql, rows)
        return cur.rowcount

    def insert_diff(self, row: tuple) -> None:
        """Append one row to diff_results.

        Tuple: (model_type, unique_key, action, identifiers_json,
                new_attrs_json, old_attrs_json, tree_depth, type_order)
        """
        self.conn.execute(
            """
            INSERT INTO diff_results
                (model_type, unique_key, action, identifiers,
                 new_attrs, old_attrs, tree_depth, type_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )

    def mark_visited(self, model_type: str, unique_key: str) -> None:
        """Record that this dest key was matched by a src key (so it won't be a DELETE)."""
        self.conn.execute(
            "INSERT OR IGNORE INTO visited_keys (model_type, unique_key) VALUES (?, ?)",
            (model_type, unique_key),
        )

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def fetch_source_in_order(self):
        """Yield source rows in (type_order, tree_depth) order — parents first."""
        cur = self.conn.execute(
            """
            SELECT model_type, unique_key, identifiers, attrs,
                   parent_type, parent_key, tree_depth, type_order
            FROM source_records
            ORDER BY type_order ASC, tree_depth ASC, unique_key ASC
            """
        )
        for row in cur:
            yield row

    def fetch_dest(self, model_type: str, unique_key: str):
        """Look up one dest row, or None."""
        cur = self.conn.execute(
            """
            SELECT model_type, unique_key, identifiers, attrs,
                   parent_type, parent_key, tree_depth, type_order
            FROM dest_records
            WHERE model_type = ? AND unique_key = ?
            """,
            (model_type, unique_key),
        )
        return cur.fetchone()

    def fetch_unvisited_dest(self):
        """Yield dest rows not present in visited_keys — these become DELETE actions.

        Ordered children-before-parents (descending type_order then tree_depth)
        so FK constraints are honored on delete.
        """
        cur = self.conn.execute(
            """
            SELECT d.model_type, d.unique_key, d.identifiers, d.attrs,
                   d.parent_type, d.parent_key, d.tree_depth, d.type_order
            FROM dest_records d
            LEFT JOIN visited_keys v
                ON v.model_type = d.model_type AND v.unique_key = d.unique_key
            WHERE v.unique_key IS NULL
            ORDER BY d.type_order DESC, d.tree_depth DESC, d.unique_key ASC
            """
        )
        for row in cur:
            yield row

    def fetch_diff_results(self, action: str):
        """Yield diff_results rows for a given action.

        CREATE  → ascending  (parents before children)
        UPDATE  → ascending  (any order works, but pick one for stability)
        DELETE  → descending (children before parents)
        """
        if action not in ("create", "update", "delete"):
            raise ValueError(f"fetch_diff_results: unknown action {action!r}")
        order = "DESC" if action == "delete" else "ASC"
        cur = self.conn.execute(
            f"""
            SELECT id, model_type, unique_key, action, identifiers,
                   new_attrs, old_attrs, tree_depth, type_order
            FROM diff_results
            WHERE action = ?
            ORDER BY type_order {order}, tree_depth {order}, id ASC
            """,
            (action,),
        )
        for row in cur:
            yield row

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def counts(self) -> dict:
        """Snapshot of row counts in each table — useful for logs and tests."""
        out = {}
        for tbl in ("source_records", "dest_records", "visited_keys", "diff_results"):
            row = self.conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
            out[tbl] = row[0]
        return out

    def diff_summary(self) -> dict:
        """{action: count} summary, for matching DiffSync's `creates/updates/deletes` numbers."""
        out = {"create": 0, "update": 0, "delete": 0}
        for action, count in self.conn.execute(
            "SELECT action, COUNT(*) FROM diff_results GROUP BY action"
        ):
            out[action] = count
        return out

    def close(self) -> None:
        """Close the SQLite connection. The file (if any) is left for inspection."""
        try:
            self.conn.close()
        finally:
            self.conn = None


def encode(value) -> str:
    """JSON-encode a Python value, defaulting unknown types to str (UUIDs etc.)."""
    return json.dumps(value, default=str, sort_keys=True)


def decode(blob: Optional[str]) -> dict:
    """Inverse of encode()."""
    if not blob:
        return {}
    return json.loads(blob)
