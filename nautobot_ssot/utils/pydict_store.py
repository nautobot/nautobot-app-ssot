"""In-memory dict-based store with the same interface as `DiffSyncStore`.

Sole purpose: isolate "what does SQLite buy us vs plain Python dicts in the
streaming pipeline." This is a benchmark/measurement aid, not a production
component.

Differences from `DiffSyncStore`:

    * No `.conn` attribute (no SQL connection). Validators and scope
      expansion that hit `store.conn.execute(...)` won't work against this
      store — that's by design; the benchmark mode that uses this skips
      Hooks 1/2/3 and scope to keep the comparison clean.

    * `with self.conn:` (used in `StreamingDiffer.diff` for transactions)
      is implemented via a no-op context manager.

    * Memory-resident only. There is no `path=`. Equivalent to SQLite's
      `:memory:` mode but without the SQL engine.

    * Iteration uses Python list `.sort()` over the in-memory dict values
      instead of SQL `ORDER BY` over a B-tree.

Tracking the same row schema lets the same `dump_adapter` / `StreamingDiffer`
/ `BulkSyncer` code call this store unchanged.
"""

from __future__ import annotations

from contextlib import nullcontext
from typing import Iterable


class PyDictStore:
    """Dict-backed reimplementation of `DiffSyncStore` for benchmarking.

    Row layouts are byte-compatible with the SQLite schema:

        source_records / dest_records:
            (model_type, unique_key, identifiers, attrs,
             parent_type, parent_key, tree_depth, type_order)
            indices: 0..7

        diff_results (after id is prepended):
            (id, model_type, unique_key, action, identifiers,
             new_attrs, old_attrs, tree_depth, type_order)
            indices: 0..8
    """

    def __init__(self, path=None):  # noqa: ARG002 — path ignored for parity with DiffSyncStore signature
        # {(model_type, unique_key): row_tuple}
        self._source: dict = {}
        self._dest: dict = {}
        # {(model_type, unique_key)} — set of dest keys already matched by source
        self._visited: set = set()
        # list of diff_result row tuples in insertion order
        self._diff_rows: list = []
        # No SQL connection; expose a no-op context manager for the
        # `with store.conn:` idiom used in StreamingDiffer.diff().
        self.conn = _NullConn()
        self.path = ":pydict:"

    # ------------------------------------------------------------------
    # Insertion (mirror DiffSyncStore.insert_records / insert_diff / mark_visited)
    # ------------------------------------------------------------------

    def insert_records(self, table: str, rows: Iterable[tuple]) -> int:
        if table == "source_records":
            target = self._source
        elif table == "dest_records":
            target = self._dest
        else:
            raise ValueError(f"insert_records: unsupported table {table!r}")
        n = 0
        for row in rows:
            target[(row[0], row[1])] = tuple(row)
            n += 1
        return n

    def insert_diff(self, row: tuple) -> None:
        rid = len(self._diff_rows) + 1
        self._diff_rows.append((rid,) + tuple(row))

    def mark_visited(self, model_type: str, unique_key: str) -> None:
        self._visited.add((model_type, unique_key))

    # ------------------------------------------------------------------
    # Iteration (mirror fetch_source_in_order / fetch_dest / fetch_unvisited_dest / fetch_diff_results)
    # ------------------------------------------------------------------

    def fetch_source_in_order(self):
        # ORDER BY type_order ASC, tree_depth ASC, unique_key ASC
        rows = sorted(self._source.values(), key=lambda r: (r[7], r[6], r[1]))
        return iter(rows)

    def fetch_dest(self, model_type: str, unique_key: str):
        return self._dest.get((model_type, unique_key))

    def fetch_unvisited_dest(self):
        # ORDER BY type_order DESC, tree_depth DESC, unique_key ASC
        unvisited = [r for k, r in self._dest.items() if k not in self._visited]
        unvisited.sort(key=lambda r: (-r[7], -r[6], r[1]))
        return iter(unvisited)

    def fetch_diff_results(self, action: str):
        if action not in ("create", "update", "delete"):
            raise ValueError(f"fetch_diff_results: unknown action {action!r}")
        rows = [r for r in self._diff_rows if r[3] == action]
        if action == "delete":
            # ORDER BY type_order DESC, tree_depth DESC, id ASC
            rows.sort(key=lambda r: (-r[8], -r[7], r[0]))
        else:
            # ORDER BY type_order ASC, tree_depth ASC, id ASC
            rows.sort(key=lambda r: (r[8], r[7], r[0]))
        return iter(rows)

    # ------------------------------------------------------------------
    # Misc — match DiffSyncStore's API surface
    # ------------------------------------------------------------------

    def counts(self) -> dict:
        return {
            "source_records": len(self._source),
            "dest_records": len(self._dest),
            "visited_keys": len(self._visited),
            "diff_results": len(self._diff_rows),
        }

    def diff_summary(self) -> dict:
        out = {"create": 0, "update": 0, "delete": 0}
        for r in self._diff_rows:
            action = r[3]
            out[action] = out.get(action, 0) + 1
        return out

    def close(self) -> None:
        # Drop references so the dicts can be GC'd.
        self._source = {}
        self._dest = {}
        self._visited = set()
        self._diff_rows = []


class _NullConn:
    """No-op stand-in for `sqlite3.Connection` so `with store.conn:` works."""

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False
