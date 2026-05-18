"""Bitwise flag system for SSoT pipeline + validation behavior.

Mirrors the pattern of `diffsync.enum.DiffSyncFlags` — a single composable
`IntFlag` controls every opt-in knob. Defaults are intentionally KISS:
the slow, safe path. Reach for flags only when you have measured a problem
that justifies a different trade-off.

The enum is a *superset* of `DiffSyncFlags` — the four diffsync bit values
are preserved verbatim (CONTINUE_ON_FAILURE = 0b1, SKIP_UNMATCHED_SRC = 0b10,
SKIP_UNMATCHED_DST = 0b100, LOG_UNCHANGED_RECORDS = 0b1000) so an SSoTFlags
value can be passed straight through to `diff_to(flags=...)` /
`sync_to(flags=...)` without conversion. Higher bits add SSoT-specific
behavior; diffsync ignores bits it doesn't recognize.
"""

from __future__ import annotations

from enum import IntFlag


class SSoTFlags(IntFlag):
    """Single composable enum for all SSoT job behavior.

    Bits 0..3 mirror `diffsync.enum.DiffSyncFlags` exactly. Higher bits are
    SSoT-specific. Compose with `|`.

    Defaults (set in `DataSyncBaseJob.__post_init__`) are
    `CONTINUE_ON_FAILURE | LOG_UNCHANGED_RECORDS` — preserves the diffsync
    behavior we've shipped to date and KISS for everything else.
    """

    NONE = 0

    # -- Diffsync-compatible bits (values must match diffsync.enum.DiffSyncFlags) --
    CONTINUE_ON_FAILURE   = 0b1
    SKIP_UNMATCHED_SRC    = 0b10
    SKIP_UNMATCHED_DST    = 0b100
    SKIP_UNMATCHED_BOTH   = SKIP_UNMATCHED_SRC | SKIP_UNMATCHED_DST  # 0b110
    LOG_UNCHANGED_RECORDS = 0b1000

    # -- Pipeline shape ----------------------------------------------------
    STREAMING        = 0b1_0000          # SQLite-backed streaming pipeline
    BULK_WRITES      = 0b10_0000         # Tier 2 bulk_create (implies STREAMING)
    PARALLEL_LOADING = 0b100_0000        # concurrent src + dst load
    MEMORY_PROFILING = 0b1000_0000       # tracemalloc per phase

    # -- Validation hooks (independent, layered) ---------------------------
    VALIDATE_SOURCE_SHAPE = 0b1_0000_0000   # Hook 1 - Strict* adapter / Pydantic
    VALIDATE_ON_DUMP      = 0b10_0000_0000  # Hook 2 - clean_fields() at dump
    VALIDATE_RELATIONS    = 0b100_0000_0000 # Hook 3 - phased validator registry
    VALIDATE_STRICT       = 0b1000_0000_0000  # raise on validation failure (else log)

    # -- Bulk-write side-effects (post-flush extension points) -------------
    BULK_CLEAN        = 0b1_0000_0000_0000     # call Model.bulk_clean(instances) before flush (Nautobot core feature, currently no-op)
    BULK_SIGNAL       = 0b10_0000_0000_0000    # fire bulk_post_{create,update,delete} signals after flush
    REFIRE_POST_SAVE  = 0b100_0000_0000_0000   # after bulk_create/bulk_update, re-fire Django post_save per instance so core handlers (cable propagation, cache invalidation, etc.) run

    # -- Code-only convenience composites (NOT exposed in the Job UI) ------
    # These are named coordinates of common combinations measured in
    # docs/dev/performance_validation_menu.md. Use them programmatically
    # ("flags = SSoTFlags.STREAM_TIER1_7"), not from the UI.
    STREAM_TIER1   = STREAMING
    STREAM_TIER2   = STREAMING | BULK_WRITES
    STREAM_TIER1_5 = STREAMING | BULK_WRITES | VALIDATE_SOURCE_SHAPE | VALIDATE_ON_DUMP
    STREAM_TIER1_7 = STREAM_TIER1_5 | VALIDATE_RELATIONS


# Single-bit names (i.e. real flags, not composites). Useful when building
# the Job MultiChoiceVar UI — composites are excluded from the picker on
# purpose; users select primitives and compose for themselves.
SINGLE_BIT_NAMES: tuple = tuple(
    f.name
    for f in SSoTFlags
    if f.value > 0 and (f.value & (f.value - 1)) == 0
)


# Default flag set applied if the user picks nothing. Preserves prior
# behavior of `self.diffsync_flags = CONTINUE_ON_FAILURE | LOG_UNCHANGED_RECORDS`.
DEFAULT_FLAGS = SSoTFlags.CONTINUE_ON_FAILURE | SSoTFlags.LOG_UNCHANGED_RECORDS
