# SSoT Performance & Validation Menu

Nautobot SSoT and DiffSync provide a straightforward ETL (Extract, Transform,
Load) framework with many features out of the box. ETL is not a new idea, so
the goal isn't to invent a new technology — it's to provide structure and
best practices around one. The platform's default behavior follows a KISS
(Keep It Simple, Stupid) approach: the slow, safe, boring path that's
correct out of the box. With that approach and the breadth of features
available, there are — as always — tradeoffs worth considering.

These features aren't always easy to understand, and their performance
implications (wall-clock time, CPU, memory, I/O) aren't always obvious from
the API surface. The most common pattern for loading data into Nautobot
includes the following:

* Every object is validated for correctness
* Every object creates a changelog entry tracking the change
* Every object dispatches webhooks
* Every object fires job hooks
* Every object publishes an event
* Some objects fire additional Django signals for:
    * Cache invalidation
    * Data cleanup
    * Other custom business logic
* All data is committed together, or none of it is (atomic transactions)
* The ability to run in dry-run mode
* The ability to track changes per job run

Some — or even all — of these features may not be needed for your
implementation. For example, if you're migrating from a legacy system
where data ownership is not yet established, do you really need a changelog?
Do you want webhooks firing if you're syncing thousands of records in one
go?

Sometimes the answer is a resounding yes; other times a clean no. Sometimes
you want most of these features but are willing to trade a slightly weaker
correctness guarantee for speed. Sometimes you already know the data is
valid and don't need to validate it again. There are many reasons to choose
speed over the KISS default — and this document is intended to make those
decisions clear, and to show you how each one can be implemented.

---

## How to read this doc

* **Part 1 — the anatomy of a sync** lays out what fires per object today.
* **Part 2 — the axes** is one chapter per behavioral knob.
* **Part 3 — composing it** offers pre-mixed presets, the measured matrix,
  and a per-integration recipe.
* For mechanical contracts (`SSoTFlags` enum, where the code lives), see
  the [Performance & Validation Reference][ref] document.

[ref]: performance_validation_reference.md

This document grows alongside the codebase. Each axis is added as the
feature that backs it lands.

### The benchmark substrate

Every claim is measured. The bundled benchmark
(`scripts/benchmark_infoblox.py --matrix`) exercises every available
mode at three scales — tiny / small / medium (8,143 objects). All
numbers in this document are from medium scale.

### Composable flag word

All SSoT pipeline + validation knobs live in a single `IntFlag` —
`nautobot_ssot.flags.SSoTFlags`. Compose with `|`. Bits 0..3 mirror
`diffsync.enum.DiffSyncFlags` exactly. The Job UI exposes the
single-bit flags as a single `MultiChoiceVar`. For the bit table see
the reference doc.

The default is `CONTINUE_ON_FAILURE | LOG_UNCHANGED_RECORDS`.

---

## Part 1 — The anatomy of a sync

```mermaid
flowchart TD
    Job([Job invoked]) --> Q1{streaming?}

    Q1 -->|No — legacy| L1[load src + dst<br/>both fully in memory]
    L1 --> L2[diff_to&#40;&#41; — build DiffSync Diff tree]
    L2 --> L3[sync_to&#40;&#41; — per-object validated_save / bulk_create]
    L3 --> Done([Done])

    Q1 -->|Yes — streaming| S_src[load src adapter] --> Sd_src[dump src to SQLite<br/>release src adapter store]
    Sd_src --> L_dst[load dst adapter]
    L_dst --> Sd_dst[dump dst to SQLite<br/>release dst adapter store]
    Sd_dst --> Diff[StreamingDiffer:<br/>walk SQLite -> diff_results]
    Diff --> Replay[BulkSyncer replays<br/>tier1 (per-row) or tier2 (bulk_create)]
    Replay --> Done

    classDef knob fill:#fff7e6,stroke:#d97706,color:#92400e
    class Q1,L1,L3,S_src,Sd_src,Sd_dst,Diff,Replay knob
```

---

## Part 2 — The axes

### Change logging — `ObjectChange` rows

**What it controls.** Whether each create/update/delete writes an
`ObjectChange` row.

**Default behavior.** Per-row immediate via `validated_save()` inside
`web_request_context`.

**Alternatives.** Deferred-batched (
`deferred_change_logging_for_bulk_operation()`) or none (when
`bulk_create()` skips `post_save`).

### Webhooks / Job hooks / Events

Driven by `ObjectChange` creation. Disable changelog → none of these
fire. Same shape across all three.

### Business-logic signals (post_save consumers)

**What it controls.** Nautobot core's `post_save` handlers — Cable
propagation, Rack cascading, custom-field cache invalidation, etc.

**Default behavior.** With per-row save, every handler fires per row.
With `bulk_create()`, none of them fire.

**Alternatives.**

| Mode | Activated by |
|---|---|
| Per-row Django `post_save` | Default |
| Refire after bulk | `SSoTFlags.REFIRE_POST_SAVE` |
| Per-batch dispatch | `SSoTFlags.BULK_SIGNAL` |
| None | `SSoTFlags.BULK_WRITES` alone |

IPAM models have no direct `post_save` handlers — `BULK_WRITES` alone
is safe. DCIM models DO — pair with `REFIRE_POST_SAVE`.

### Atomic transactions

Per-Job atomic block by default. SSoT does not currently expose a
knob for transaction scope.

### Bulk-write batching

**What it controls.** Per-row INSERT vs batched.

**Default behavior.** `validated_save()` per row.

**Alternatives.** `bulk_create` / `bulk_update` (default batch 250)
via `BulkOperationsMixin` adapter or `SSoTFlags.BULK_WRITES` in the
streaming pipeline. At medium scale, ~30× faster than `validated_save`.
The `bulk_b250_audit` mode demonstrates same audit semantics as
production at ~5 s vs ~150 s.

### Memory shape

**What it controls.** Peak memory footprint during the diff phase.

**Default behavior.** Both adapters fully in memory plus the `Diff`
tree built by `src.diff_to(dst)`. At medium scale, peak is ~30 MiB.
The persisted `Sync.diff` JSONField also has a ~1 GB limit that
real-world large diffs can exceed.

**When you'd dial it.** OOM on large initial syncs, or syncs whose
diff serialization would exceed the JSONField cap.

**Alternatives.**

| Mode | Behavior | Peak memory at medium |
|---|---|---:|
| In-memory `Diff` tree (default) | Both adapters + `Diff` tree concurrent | ~30 MiB |
| SQLite-backed streaming | Dump each adapter to SQLite, release adapter store, walk SQLite for diff | ~20 MiB |

**Cost & tradeoffs.** Streaming caps memory by holding only
`source_records` + `dest_records` in SQLite, releasing the in-memory
DiffSync model instances after dump. Memory savings scale with row
count: ~10 MiB freed at 8k rows projects to ~60 MiB at 100k and ~600
MiB at 1M.

The streaming pipeline orchestrator
(`nautobot_ssot/utils/streaming_pipeline.py`) handles
load → dump → release → diff → replay. The `BulkSyncer` walks
`diff_results` and replays per-row (Tier 1) or bulk_create (Tier 2).

**How to wire it.** `SSoTFlags.STREAMING` (Tier 1, per-row replay) or
`SSoTFlags.STREAM_TIER2` (= `STREAMING | BULK_WRITES`, bulk replay).

### Concurrency

**What it controls.** Sequential vs parallel adapter loading.

**Default behavior.** Sequential.

**Alternatives.** `SSoTFlags.PARALLEL_LOADING`. Reduces wall-clock
when both adapters are I/O-bound and don't contend.

### Dry-run

On by default. `DryRunVar` toggles writes off.

### Memory profiling

**What it controls.** `tracemalloc` per phase, results stored on the
`Sync` record.

**Default behavior.** Off.

**Alternatives.** `SSoTFlags.MEMORY_PROFILING`.

---

## Part 3 — Composing it

### Per-integration recipe (in progress)

Recipe steps land here as the relevant infrastructure ships.

#### Step 2 — Bulk write adapter

```python
from nautobot_ssot.utils.bulk import BulkOperationsMixin

class BulkNautobotMyIntAdapter(BulkOperationsMixin, NautobotMyIntAdapter):
    foo = BulkNautobotFoo
    bar = BulkNautobotBar
    _bulk_create_order = [OrmFoo, OrmBar]

    refire_post_save: bool = False
    bulk_signal: bool = False
    bulk_clean: bool = False
```

For a working reference see `BulkNautobotAdapter` in
`nautobot_ssot/integrations/infoblox/diffsync/adapters/nautobot_bulk.py`.
