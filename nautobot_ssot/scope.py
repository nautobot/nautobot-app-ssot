"""Scoped sync — target a single subtree instead of the full adapter.

Today's SSoT pipeline is whole-adapter: every model that the integration
loads is part of the diff. For operational use cases — "this one prefix
needs to be re-synced," "this device just changed in the source," "fire
this from a webhook" — that's overkill. Scoped sync constrains the diff
(and optionally the load) to a single subtree rooted at a given key.

Pipeline-side scoping is generic: once both adapters are dumped to the
SQLite store, expand the subtree from the root key by walking either:

    1. `parent_type` / `parent_key` columns populated by `dump_adapter()`
       when the model uses DiffSync's `_children` metadata. Default.

    2. A per-integration custom expander, for integrations that encode
       parent/child relationships in `_identifiers` rather than `_children`
       (Infoblox, etc.). Registered via `register_subtree_expander()`.

The expander returns a set of `(model_type, unique_key)` pairs covering the
subtree across both source_records and dest_records — so dest-only orphans
WITHIN the subtree are correctly emitted as DELETEs, while everything OUTSIDE
the subtree is untouched.

Source-side scoped load (skipping the API call for out-of-scope data) is a
separate, optional optimization that lives per-integration in
`adapter.load(scope=...)`. Pipeline-side scoping is correctness-equivalent
without it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Set, Tuple

# Registry of per-integration custom subtree expanders.
# Keyed by an opaque "integration name" string the caller passes in.
_EXPANDER_REGISTRY: Dict[str, Callable] = {}


@dataclass(frozen=True)
class SyncScope:
    """Identifies a subtree of an adapter's data to sync.

    The subtree is rooted at (model_type, unique_key) and recursively
    includes every descendant reachable via either:

      * DiffSync `_children` metadata (default expander)
      * a per-integration custom expander (registered separately)

    Setting ``include_root=False`` syncs only the descendants — useful for
    cases like "force-resync just the IPs under this prefix without
    touching the prefix itself."

    The optional ``integration`` field selects which custom expander to use;
    `None` means use the default SQLite walker.
    """

    model_type: str
    unique_key: str
    include_root: bool = True
    integration: Optional[str] = None


# ---------------------------------------------------------------------------
# Default expander — walks parent_type/parent_key in SQLite
# ---------------------------------------------------------------------------


def _default_expander(scope: SyncScope, store) -> Set[Tuple[str, str]]:
    """Walk descendants via the parent_type/parent_key columns dump_adapter
    populates when the model uses DiffSync's `_children` metadata.

    Works for any integration that defines `_children` correctly. Returns
    the set of (model_type, unique_key) pairs covering the subtree across
    BOTH source_records AND dest_records (so dest-only orphans get included).
    """
    keys: Set[Tuple[str, str]] = set()
    if scope.include_root:
        keys.add((scope.model_type, scope.unique_key))

    queue = [(scope.model_type, scope.unique_key)]
    while queue:
        parent_type, parent_key = queue.pop()
        for table in ("source_records", "dest_records"):
            cur = store.conn.execute(
                f"SELECT model_type, unique_key FROM {table} "
                f"WHERE parent_type = ? AND parent_key = ?",
                (parent_type, parent_key),
            )
            for row in cur:
                if row not in keys:
                    keys.add(row)
                    queue.append(row)
    return keys


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def register_subtree_expander(integration: str, expander: Callable) -> None:
    """Register a custom expander for an integration whose hierarchy isn't
    expressible via DiffSync's `_children`.

    Expander signature: ``(scope: SyncScope, store: DiffSyncStore) -> set[tuple]``.
    """
    _EXPANDER_REGISTRY[integration] = expander


def expand_subtree(scope: SyncScope, store) -> Set[Tuple[str, str]]:
    """Expand `scope` into the set of (model_type, unique_key) pairs that
    fall within its subtree.

    Selects the per-integration expander if `scope.integration` is set and
    a matching expander was registered; otherwise uses the default SQLite
    walker.
    """
    if scope.integration is not None:
        custom = _EXPANDER_REGISTRY.get(scope.integration)
        if custom is not None:
            return custom(scope, store)
    return _default_expander(scope, store)


def lookup_record_identifiers(store, model_type: str, unique_key: str) -> dict:
    """Helper for custom expanders: fetch the identifiers JSON for a row.

    Tries source_records first, then dest_records. Returns {} if not found.
    """
    cur = store.conn.execute(
        "SELECT identifiers FROM source_records WHERE model_type = ? AND unique_key = ? "
        "UNION ALL "
        "SELECT identifiers FROM dest_records WHERE model_type = ? AND unique_key = ? "
        "LIMIT 1",
        (model_type, unique_key, model_type, unique_key),
    )
    row = cur.fetchone()
    if not row:
        return {}
    return json.loads(row[0] or "{}")
