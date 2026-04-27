# SSoT Performance & Validation — Reference

Mechanical contracts and complete file manifest for the features
described in the [Performance & Validation Menu][menu]. This document
is for engineers extending the framework; readers who just want to
configure their own sync should start with the menu.

[menu]: performance_validation_menu.md

This reference grows alongside the menu — sections are added as the
backing infrastructure lands.

---

## `SSoTFlags` enum

Defined in `nautobot_ssot/flags.py`. `SSoTFlags(IntFlag)` is the single
composable flag word covering pipeline shape, validation hooks, and
side-effect dispatch. Bits 0..3 mirror `diffsync.enum.DiffSyncFlags`
exactly so the same flag word passes through to `diff_to(flags=...)` /
`sync_to(flags=...)` without conversion.

### Bit table

| Bit | Name | Meaning |
|---|---|---|
| 0b1 | `CONTINUE_ON_FAILURE` | (= `DiffSyncFlags.CONTINUE_ON_FAILURE`) sync continues past per-model failures |
| 0b10 | `SKIP_UNMATCHED_SRC` | (= `DiffSyncFlags.SKIP_UNMATCHED_SRC`) suppresses creates |
| 0b100 | `SKIP_UNMATCHED_DST` | (= `DiffSyncFlags.SKIP_UNMATCHED_DST`) suppresses deletes |
| 0b110 | `SKIP_UNMATCHED_BOTH` | (composite of the above two) |
| 0b1000 | `LOG_UNCHANGED_RECORDS` | (= `DiffSyncFlags.LOG_UNCHANGED_RECORDS`) emit no-change log per row |
| 0b1_0000 | `STREAMING` | SQLite-backed streaming pipeline |
| 0b10_0000 | `BULK_WRITES` | Tier 2 bulk_create (implies STREAMING when used by the streaming pipeline) |
| 0b100_0000 | `PARALLEL_LOADING` | Concurrent src + dst load |
| 0b1000_0000 | `MEMORY_PROFILING` | tracemalloc per phase |
| 0b1_0000_0000 | `VALIDATE_SOURCE_SHAPE` | Hook 1 — strict source models (informational; Hook 1 is also gated on a per-integration `Strict<Adapter>` swap) |
| 0b10_0000_0000 | `VALIDATE_ON_DUMP` | Hook 2 — `clean_fields()` at dump time |
| 0b100_0000_0000 | `VALIDATE_RELATIONS` | Hook 3 — phased validator registry |
| 0b1000_0000_0000 | `VALIDATE_STRICT` | Raise on validation failure (else log) |
| 0b1_0000_0000_0000 | `BULK_CLEAN` | Call `Model.bulk_clean(instances)` before flush (Nautobot core feature; currently no-op until shipped) |
| 0b10_0000_0000_0000 | `BULK_SIGNAL` | Fire `bulk_post_{create,update,delete}` after each flush |
| 0b100_0000_0000_0000 | `REFIRE_POST_SAVE` | Re-fire Django `post_save` per instance after each bulk batch |

Note: bits for streaming, validation, and scope-related features are
defined now even when the supporting infrastructure lands in later
commits — keeping the enum stable from the start prevents bit-renaming
later.

### Defaults and composites

| Name | Value |
|---|---|
| `DEFAULT_FLAGS` | `CONTINUE_ON_FAILURE \| LOG_UNCHANGED_RECORDS` — applied when no flags selected |
| `STREAM_TIER1` | `STREAMING` |
| `STREAM_TIER2` | `STREAMING \| BULK_WRITES` |
| `STREAM_TIER1_5` | `STREAMING \| BULK_WRITES \| VALIDATE_SOURCE_SHAPE \| VALIDATE_ON_DUMP` |
| `STREAM_TIER1_7` | `STREAM_TIER1_5 \| VALIDATE_RELATIONS` |

Composites are code-only shortcuts — they do not appear in the Job UI's
`MultiChoiceVar` picker. The picker shows only single-bit flags.

### `SINGLE_BIT_NAMES`

Tuple of names for single-bit flags only — used to populate the Job
UI `MultiChoiceVar` choices. Composites and zero are excluded.

### Job integration

`DataSyncBaseJob.flags` is a `MultiChoiceVar` populated from
`SINGLE_BIT_NAMES`. Selected names are OR'd into `self.flags` during
`run()`. Subclasses that want to force certain bits can do so by
setting `self.flags |= SSoTFlags.X` after calling
`super().run(*args, **kwargs)`.

`self.diffsync_flags` is a property derived from `self.flags` (low 4
bits). The setter is preserved for backward compatibility with code
that does `self.diffsync_flags = DiffSyncFlags.X`.
