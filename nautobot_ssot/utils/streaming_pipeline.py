"""End-to-end orchestrator for the streaming SSoT pipeline.

Ties together:
    1. Source adapter `.load()`           — current API, unchanged
    2. Dump source to SQLite             — `streaming_differ.dump_adapter`
    3. Destination adapter `.load()`     — current API, unchanged
    4. Dump destination to SQLite         — `streaming_differ.dump_adapter`
    5. Compute diff via SQLite           — `StreamingDiffer.diff()`
    6. Replay diff via BulkSyncer        — `BulkSyncer.sync()`

Step 6 in the plan ("Wire Into Base Job") will call `run_streaming_sync()`
from `DataSyncBaseJob.sync_data()` when `self.streaming_sync` is True.
For the benchmark we drive it directly.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from ..flags import SSoTFlags
from ..scope import SyncScope, expand_subtree
from .bulk_syncer import BulkSyncer
from .sqlite_store import DiffSyncStore
from .streaming_differ import StreamingDiffer, dump_adapter

logger = logging.getLogger(__name__)


@dataclass
class StreamingSyncResult:
    """Per-phase timings + counts. Mirrors the keys the benchmark expects."""

    t_src: float = 0.0
    t_src_dump: float = 0.0
    t_dst: float = 0.0
    t_dst_dump: float = 0.0
    t_diff: float = 0.0
    t_sync: float = 0.0
    diff_stats: dict = field(default_factory=dict)
    sync_stats: dict = field(default_factory=dict)
    store_counts: dict = field(default_factory=dict)

    @property
    def total(self) -> float:
        return self.t_src + self.t_src_dump + self.t_dst + self.t_dst_dump + self.t_diff + self.t_sync


def run_streaming_sync(
    src_adapter,
    dst_adapter,
    *,
    flags: SSoTFlags = SSoTFlags.NONE,
    sqlite_path: Optional[str] = None,
    user=None,
    skip_load: bool = False,
    dryrun: bool = False,
    scope: Optional[SyncScope] = None,
    store_class=None,
) -> StreamingSyncResult:
    """Run the full streaming pipeline. `tier` ∈ {"tier1", "tier2"}.

    Args:
        src_adapter: source DiffSync adapter (already constructed; not yet loaded
                     unless `skip_load=True`).
        dst_adapter: destination DiffSync adapter (same).
        flags: SSoTFlags controlling tier + validation hooks.
            * BULK_WRITES         → Tier 2 (bulk_create) instead of Tier 1
            * VALIDATE_ON_DUMP    → Hook 2 clean_fields() at dump time
            * VALIDATE_STRICT     → raise on validation failure (else log+continue)
            * VALIDATE_RELATIONS  → Hook 3 phased validator registry
            (Hook 1 — strict source models — is a per-integration adapter class
             swap, not a flag the pipeline itself can enable.)
        sqlite_path: path for the SQLite store. None → ":memory:". Pass "auto"
                     for a temp file kept around for inspection.
        user: optional user for the change-logging context (Tier 1 only).
        skip_load: if True, the adapters have already been .load()'d.
        dryrun: if True, run the diff but skip the BulkSyncer replay phase.
        scope: optional SyncScope to constrain the diff to a single subtree.
            When set, only rows in the subtree (rooted at scope.model_type +
            scope.unique_key) participate in the diff — everything else is
            untouched. Per-integration custom expanders selected via
            scope.integration; defaults to walking parent_type/parent_key
            in SQLite (works for adapters using DiffSync `_children`).
        store_class: optional concrete store implementation. Defaults to
            `DiffSyncStore` (SQLite-backed). Pass `PyDictStore` to compare
            "what does SQLite actually buy us vs Python dicts?" — but note
            that PyDictStore lacks `.conn` and is incompatible with
            validators / scope expansion that hit SQL directly.

    Returns the timing/stats record.
    """
    tier = "tier2" if (flags & SSoTFlags.BULK_WRITES) else "tier1"
    validate_on_dump = bool(flags & SSoTFlags.VALIDATE_ON_DUMP)
    strict = bool(flags & SSoTFlags.VALIDATE_STRICT)
    validate_relations = (
        "strict" if (flags & SSoTFlags.VALIDATE_RELATIONS and strict)
        else bool(flags & SSoTFlags.VALIDATE_RELATIONS)
    )
    bulk_clean = bool(flags & SSoTFlags.BULK_CLEAN)
    bulk_signal = bool(flags & SSoTFlags.BULK_SIGNAL)
    refire_post_save = bool(flags & SSoTFlags.REFIRE_POST_SAVE)
    result = StreamingSyncResult()
    store_cls = store_class if store_class is not None else DiffSyncStore
    store = store_cls(path=sqlite_path)

    try:
        # ------------------------------------------------------------------
        # Source: load + dump + free
        # ------------------------------------------------------------------
        if not skip_load:
            t0 = time.perf_counter()
            src_adapter.load()
            result.t_src = time.perf_counter() - t0

        t0 = time.perf_counter()
        dump_adapter(
            src_adapter,
            store,
            "source_records",
            orm_resolver=dst_adapter if validate_on_dump else None,
            strict=strict,
        )
        result.t_src_dump = time.perf_counter() - t0

        # Free in-memory state from src_adapter — leaves the adapter object
        # but drops the DiffSync model instance store. Best-effort: not all
        # store backends expose a clear() method.
        _release_adapter_store(src_adapter)

        # ------------------------------------------------------------------
        # Destination: load + dump
        # NB: we don't free dst_adapter — its lookup maps (namespace_map etc.)
        # are needed during the BulkSyncer replay.
        # ------------------------------------------------------------------
        if not skip_load:
            t0 = time.perf_counter()
            dst_adapter.load()
            result.t_dst = time.perf_counter() - t0

        t0 = time.perf_counter()
        dump_adapter(dst_adapter, store, "dest_records")
        result.t_dst_dump = time.perf_counter() - t0

        _release_adapter_store(dst_adapter)

        # ------------------------------------------------------------------
        # Diff (SQLite-only). If `scope` is set, expand it to the subtree's
        # (model_type, unique_key) set BEFORE diff so the differ only walks
        # rows inside the subtree.
        # ------------------------------------------------------------------
        t0 = time.perf_counter()
        scope_keys = expand_subtree(scope, store) if scope is not None else None
        differ = StreamingDiffer(store, scope_keys=scope_keys)
        result.diff_stats = differ.diff()
        if scope_keys is not None:
            result.diff_stats["scope_keys_in_subtree"] = len(scope_keys)
        result.t_diff = time.perf_counter() - t0

        # ------------------------------------------------------------------
        # Sync (replay against dst_adapter, Tier 1 or 2). Skipped on dryrun.
        # ------------------------------------------------------------------
        if not dryrun:
            t0 = time.perf_counter()
            syncer = BulkSyncer(
                dst_adapter=dst_adapter,
                store=store,
                tier=tier,
                user=user,
                validate_relations=validate_relations,
                bulk_clean=bulk_clean,
                bulk_signal=bulk_signal,
                refire_post_save=refire_post_save,
            )
            result.sync_stats = syncer.sync()
            result.t_sync = time.perf_counter() - t0

        result.store_counts = store.counts()
    finally:
        store.close()

    return result


def _release_adapter_store(adapter) -> None:
    """Best-effort: drop the in-memory DiffSync model instances on `adapter`.

    Keeps adapter object & lookup maps alive (those are tiny). The big
    contributor to peak memory is the `store` dict of DiffSync model
    instances; clearing that frees the bulk of source/dest before the
    diff or sync phase runs.

    Different DiffSync versions expose different store APIs; we try the
    public-ish ones in order and stop on the first success.
    """
    store = getattr(adapter, "store", None)
    if store is None:
        return
    for method_name in ("clear", "remove_all", "_clear"):
        method = getattr(store, method_name, None)
        if callable(method):
            try:
                method()
                return
            except TypeError:
                continue
    # Final fallback: replace internal data dict if present.
    data = getattr(store, "_data", None)
    if isinstance(data, dict):
        data.clear()
