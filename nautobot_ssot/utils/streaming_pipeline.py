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
) -> StreamingSyncResult:
    """Run the full streaming pipeline. `tier` ∈ {"tier1", "tier2"}.

    Args:
        src_adapter: source DiffSync adapter (already constructed; not yet loaded
                     unless `skip_load=True`).
        dst_adapter: destination DiffSync adapter (same).
        flags: SSoTFlags controlling tier + side-effects.
            * BULK_WRITES       → Tier 2 (bulk_create) instead of Tier 1
            * BULK_CLEAN        → call Model.bulk_clean(instances) before flush
            * BULK_SIGNAL       → fire bulk_post_* signals after each flush
            * REFIRE_POST_SAVE  → re-fire Django post_save per instance
        sqlite_path: path for the SQLite store. None → ":memory:".
        user: optional user for the change-logging context (Tier 1 only).
        skip_load: if True, the adapters have already been .load()'d.
        dryrun: if True, run the diff but skip the BulkSyncer replay phase.

    Returns the timing/stats record.
    """
    tier = "tier2" if (flags & SSoTFlags.BULK_WRITES) else "tier1"
    bulk_clean = bool(flags & SSoTFlags.BULK_CLEAN)
    bulk_signal = bool(flags & SSoTFlags.BULK_SIGNAL)
    refire_post_save = bool(flags & SSoTFlags.REFIRE_POST_SAVE)
    result = StreamingSyncResult()
    store = DiffSyncStore(path=sqlite_path)

    try:
        # ------------------------------------------------------------------
        # Source: load + dump + free
        # ------------------------------------------------------------------
        if not skip_load:
            t0 = time.perf_counter()
            src_adapter.load()
            result.t_src = time.perf_counter() - t0

        t0 = time.perf_counter()
        dump_adapter(src_adapter, store, "source_records")
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
        # Diff (SQLite-only).
        # ------------------------------------------------------------------
        t0 = time.perf_counter()
        differ = StreamingDiffer(store)
        result.diff_stats = differ.diff()
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
