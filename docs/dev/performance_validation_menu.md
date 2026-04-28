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

* **Part 1 — the anatomy of a sync** lays out what fires per object today
  and frames each downstream effect as a knob you can dial.
* **Part 2 — the axes** is one chapter per behavioral knob, in roughly the
  order most engineers think about them. Each chapter follows the same
  shape: *what it controls, default behavior, when you'd dial it,
  alternatives, cost & tradeoffs, how to wire it*. Skip to the axis you
  care about.
* **Part 3 — composing it** offers pre-mixed presets, the measured matrix,
  and a per-integration recipe for adding this menu to a new SSoT
  integration.
* For the mechanical contracts (the `SSoTFlags` enum, the validator
  registry interface, the deferred-X context shape, the scope API) see
  the companion [Performance & Validation Reference][ref] document.

[ref]: performance_validation_reference.md

### The benchmark substrate

Every claim in this document is measured. The bundled benchmark
(`scripts/benchmark_infoblox.py --matrix`) exercises every mode at three
scales — tiny / small / medium (8,143 objects) — and prints a TOTAL-time
pivot table per scale. Re-run via:

```bash
./scripts/run_benchmark_matrix.sh
```

Inside the dev container, sourced env wrapper handles DB / Redis hosts.
All numbers in this document are from medium scale. The "audit chain"
column in §3 tracks whether each mode produces ObjectChange rows and
fires webhooks/jobhooks/events — that distinction matters more than raw
speed for many integrations.

---

## Part 1 — The anatomy of a sync

```mermaid
flowchart TD
    Job([Job invoked]) --> Load[Load source + target adapters]
    Load --> Diff[Compute diff]
    Diff --> Apply{Per-row write path?}

    Apply -->|"validated_save (default)"| PerRow["full_clean → save → post_save signals"]
    Apply -->|"save (no clean)"| PerRowNoClean["save → post_save signals"]
    Apply -->|"bulk_create / bulk_update"| Bulk["bulk INSERT batches<br/>(no signals fire)"]

    PerRow --> Signals[post_save fires for every row]
    PerRowNoClean --> Signals
    Signals --> Audit["Audit chain:<br/>ObjectChange → webhooks / jobhooks / events"]
    Signals --> Domain["Domain-logic signals:<br/>Cable propagation, cache invalidation, …"]

    Bulk --> Skipped[All signals skipped by default]

    classDef knob fill:#fff7e6,stroke:#d97706,color:#92400e
    class Apply,PerRow,PerRowNoClean,Bulk,Signals,Audit,Domain,Skipped knob
```

Every yellow node above is a knob. The default path is the leftmost — the
KISS guarantee. The other branches exist because not every sync needs the
full default chain, and the framework lets you opt out of pieces you've
measured aren't worth the cost.

The rest of Part 2 walks through each axis individually. Most are
independent and compose freely.

---

## Part 2 — The axes

### 1. Validation

**What it controls.** What gets checked about each row, when, and how
expensively, before the row reaches the database.

**Default behavior.** `validated_save()` runs Django's `full_clean()` on
every row before INSERT. That means: per-field validators (CIDR / IP /
choices), the model's own `clean()` method (which often does its own DB
queries — e.g., `IPAddress._get_closest_parent`), and uniqueness checks.
Cost is roughly **1.7 ms/row** of `full_clean()` time on top of save.

**When you'd dial it.** When you have ~thousands of rows and the
per-row clean cost becomes a meaningful share of total sync time, OR
when you want validation that the model's own `clean()` method does not
provide (cross-row uniqueness, prefix overlap, IP-in-prefix containment).

**Alternatives.** Five sub-axes, layered:

| Sub-axis | When it runs | Cost | Activated by |
|---|---|---|---|
| **Source-shape** validation (Pydantic) | At `adapter.load()` time, before diff | µs/row | Per-integration: subclass source models with `IPAMShapeValidationMixin` and use a `Strict<Adapter>` |
| **Per-field** validation (`clean_fields()`) | At dump time, no DB round-trip | 10–20 µs/row | `SSoTFlags.VALIDATE_ON_DUMP` (streaming pipeline only) + `to_orm_kwargs()` resolver on the target adapter |
| **Relational / cross-row** validation | Phase A (pre-flush) / B (between flushes) / C (post-flush) | depends; e.g. IP-in-prefix Phase B ≈ 37 µs/row | `SSoTFlags.VALIDATE_RELATIONS`; validators registered on the adapter via `validator_registry` class attr |
| **Model `clean()`** | Per row, inside `validated_save()` | ~1.7 ms/row | Default; on by definition when using `validated_save()` |
| **Batched `bulk_clean()`** | Once per flush stage in bulk pipeline | depends on the model | `SSoTFlags.BULK_CLEAN`; **no-op until Nautobot core ships `Model.bulk_clean(instances)`** |

**Cost & tradeoffs.** Source-shape and per-field validation are cheap
enough to leave on for any sync that cares about catching bad data
early. Relational validation costs depend on the validator: a single
batched DB query per validator (like `IPInPrefixValidator`) is cheap;
naïve per-row queries are not. `validated_save`'s `full_clean()` is the
expensive default — it dominates per-row save cost at scale.

**Tightening the failure mode.** `SSoTFlags.VALIDATE_STRICT` flips
per-field and relational validators from log-and-continue to raise. Use
when bad data should abort the run rather than be silently logged.

**How to wire it.** For source-shape and per-field validation, see the
per-integration recipe in [Part 3](#part-3--composing-it). For relational
validators, subclass `Validator` and register it on the adapter's
`validator_registry`. For the contracts, see the
[Validation reference][ref-validation].

[ref-validation]: performance_validation_reference.md#validation-registry

---

### 2. Change logging — `ObjectChange` rows

**What it controls.** Whether each create/update/delete writes an
`ObjectChange` row in the Nautobot database recording who changed what
when.

**Default behavior.** Every `validated_save()` (or plain `save()`) inside
a `web_request_context` fires `post_save`, which the changelog signal
handler captures and INSERTs as one `ObjectChange` per row. That's full
per-row audit, paid as ~7.4 ms/row INSERT plus ~6.3 ms/row of
`to_objectchange()` serialization at medium scale.

**When you'd dial it.** Two opposing pressures:

* You don't need the audit trail (initial bulk load, throwaway
  migration, dev / fixture data) — turn it off entirely.
* You need the audit trail but the per-row INSERT cost is dominating
  total time — batch the INSERTs.

**Alternatives.**

| Mode | Behavior | When it runs | Cost |
|---|---|---|---|
| **Per-row immediate (default)** | One `ObjectChange` INSERT per save, in the same DB round trip | inside `web_request_context` | ~7.4 ms/row INSERT + ~6.3 ms/row serialization |
| **Deferred-batched** | Captures `ObjectChange`s during the block, flushes them in one `bulk_create` at end of block | inside `deferred_change_logging_for_bulk_operation()` | ~6.3 ms/row serialization (no INSERT amortized in) |
| **None** | `bulk_create()` skips `post_save` so no `ObjectChange`s are written | when using `BULK_WRITES` without a deferred CL wrapper | 0 |

**Cost & tradeoffs.** Deferring the changelog saves the INSERT
round-trip cost (~43% speedup over per-save in our medium benchmark)
but **does not** save the serialization cost — `to_objectchange()`
runs per row regardless. If you need the audit trail and you have
thousands of rows, deferred is strictly better than immediate. If
you don't need the audit trail, skipping it entirely (Tier 2 bulk
without the wrapper) is dramatically better.

**How to wire it.**

```python
from nautobot.extras.context_managers import (
    deferred_change_logging_for_bulk_operation,
    web_request_context,
)

with web_request_context(user, context_detail="my-job"):
    with deferred_change_logging_for_bulk_operation():
        # any saves / bulk_creates inside here
        # writes are batched at end of block
        ...
```

To skip the changelog entirely, run `bulk_create()` outside any
`web_request_context` (the changelog signal handler short-circuits
when no change context is active).

---

### 3. Webhooks

**What it controls.** Outbound HTTP notifications fired in response to
data changes.

**Default behavior.** Webhooks are dispatched at the end of a
`web_request_context` block, iterating the `ObjectChange` rows produced
during the block and matching them against configured `Webhook` objects.
One outbound HTTP call per matching `ObjectChange` × webhook
configuration.

**When you'd dial it.** Almost always when running a bulk migration —
firing 8,000 webhooks for a single sync rarely matches what downstream
consumers expect. Dialing the underlying changelog axis to "none" turns
off webhooks too (no `ObjectChange` rows means no webhooks).

**Alternatives.**

| Mode | Behavior | Cost |
|---|---|---|
| **Per-row immediate** | (currently inherent to Nautobot) one webhook fired per row at end of `web_request_context` | proportional to row count × matching webhook count |
| **Deferred-batched (via deferred CL)** | All `ObjectChange`s land in one `bulk_create`, then `web_request_context` cleanup iterates them — webhooks still fire one per row, just at end-of-block | same dispatch cost; only the OC INSERT cost is amortized |
| **None** | No `ObjectChange` rows → no webhooks dispatched | 0 |

**Cost & tradeoffs.** Webhooks are unconditionally per-row. SSoT does
not currently provide a "batched webhook" primitive — that would need
either a Nautobot-core change to webhook dispatch, or a per-integration
deferred context that captures webhook calls and batches them
(`deferred_webhook` is hypothetical today).

**How to wire it.** Driven by axis 2 (change logging). Disable
changelog → webhooks don't fire. Keep changelog → webhooks fire normally.

---

### 4. Job hooks

**What it controls.** Nautobot `JobHook` objects firing in response to
data changes, identical dispatch shape to webhooks but firing internal
Jobs instead of HTTP calls.

**Default behavior.** Same as webhooks — driven by `ObjectChange`
creation. Each matching `JobHook` enqueues a Celery task to run the
target Job at end of `web_request_context`.

**When you'd dial it.** Same as webhooks. A bulk migration that
triggers thousands of background Jobs is rarely what you want.

**Alternatives.** Same shape as webhooks — driven by axis 2 (change
logging).

**Cost & tradeoffs.** Per-row dispatch into the Celery queue. The Jobs
themselves run async, so the synchronous cost is just the enqueue. But
the queued backlog is real — tens of thousands of queued Jobs can
cascade into hours of work for the worker pool.

**How to wire it.** Driven by axis 2.

---

### 5. Events (Nautobot Event framework)

**What it controls.** Nautobot's pub/sub Event publication on data
changes, used by external event subscribers (monitoring systems,
analytics pipelines, integrations).

**Default behavior.** Same shape as webhooks and job hooks — driven by
`ObjectChange` creation. One event published per `ObjectChange` at end
of `web_request_context`.

**When you'd dial it.** Same as webhooks. If your event subscribers are
designed for high-rate streams, leaving them on may be fine; if they're
designed for human-paced changes, a bulk sync will spam them.

**Alternatives.** Same as webhooks — driven by axis 2.

**Cost & tradeoffs.** Async fan-out via the configured event broker
(NATS, Redis Streams, etc.) — synchronous cost is just the publish call,
but downstream load can be substantial.

**How to wire it.** Driven by axis 2.

---

### 6. Business-logic signals (post_save consumers)

**What it controls.** Nautobot core's `post_save` handlers — Cable
propagation, Rack location cascading, custom-field cache invalidation,
search-index updates, virtual-chassis assignment, etc. These are NOT
gated on `web_request_context`; they fire on every `save()` regardless
of changelog.

**Default behavior.** With per-row `validated_save()` or `save()`, every
`post_save` handler fires per row. With `bulk_create()`, **none of them
fire** — that's where the speed comes from, but it silently loses every
side-effect they were responsible for.

**When you'd dial it.** Whenever you choose `BULK_WRITES`, you've
implicitly dialed this to "none." You then have to decide whether that's
acceptable for the models you're touching.

**Alternatives.**

| Mode | Behavior | Cost | Activated by |
|---|---|---|---|
| **Per-row Django `post_save`** | Default; one signal dispatch per row | proportional to row count × handler count | Default for `save()` / `validated_save()` |
| **Refire after bulk** | After each bulk batch, loop and re-fire `post_save` per instance — restores Nautobot core handlers (Cable, Rack, custom-field cache, …) | per-row dispatch — pays back some bulk speed | `SSoTFlags.REFIRE_POST_SAVE` |
| **Per-batch dispatch** | Fires `bulk_post_create` / `bulk_post_update` / `bulk_post_delete` once per FK stage with the full batch of instances | one signal per stage | `SSoTFlags.BULK_SIGNAL` (subscribers must be written for the batched form) |
| **Shape-B batched contexts** | Per-domain context that captures a signal during the block, runs one batched implementation at end of block — e.g. `deferred_domainlogic_cable` | per-domain, dramatically cheaper than per-row replay when the handler does cross-row work | Wrap the sync in `nautobot_ssot.contexts.deferred_domainlogic_*` |
| **None** | All post_save consumers skipped | 0 | `BULK_WRITES` alone with no replay/wrapper |

**Audit of what's at risk.** When `BULK_WRITES` runs with no replay:

| Category | Examples | Consequence |
|---|---|---|
| Cable / connection propagation | `update_connected_endpoints`, `nullify_connected_endpoints` | `Cable.connection_state` never updates; `link_peer` references stay stale |
| Location cascading | `handle_rackgroup_location_change`, `handle_rack_location_change` | Child Racks / Devices keep old location after parent moves |
| Cluster membership | `assign_virtualchassis_master`, `clear_virtualchassis_members`, `clear_deviceredundancygroup_members` | VirtualChassis never picks a master; redundancy group members not detached on delete |
| Cross-model validation (m2m) | `prevent_adding_tagged_vlans_with_incorrect_mode_or_site`, `validate_vdcs_interface_relationships`, `vrf_prefix_associated`, `vrf_device_associated` | Validation Nautobot relies on for row consistency doesn't run |
| Cache invalidation | `invalidate_choices_cache`, `invalidate_relationship_models_cache`, `invalidate_validation_rule_caches`, `invalidate_models_cache` | Stale cached choices / metadata / validation rules until something else invalidates them |

**IPAM models** (Namespace, Prefix, IPAddress, VLAN, VLANGroup) have
**no direct `post_save` handlers** in core. `BULK_WRITES` alone is safe
for IPAM-only syncs. **DCIM models** (Cable, Rack, RackGroup,
VirtualChassis, etc.) DO have handlers that do real work — pair with
`REFIRE_POST_SAVE` or shape-B contexts.

**Cost & tradeoffs.** `REFIRE_POST_SAVE` is per-row (N invocations).
`BULK_SIGNAL` + handlers written for the batched form is one dispatch
per stage. Shape-B contexts (like `deferred_domainlogic_cable`) deliver
the highest leverage — one batched call against the whole set instead
of N — but require the handler to be rewritten or replaced. The
[Deferred-X reference][ref-deferred-x] documents the contract for
writing new shape-B contexts.

**How to wire it.** Set the appropriate flags and wrap with the
appropriate contexts. See the recipes in [Part 3](#part-3--composing-it)
for the common compositions.

[ref-deferred-x]: performance_validation_reference.md#deferred-x-context-contract

---

### 7. Atomic transactions

**What it controls.** The granularity of rollback. If part of the sync
fails, what gets rolled back?

**Default behavior.** Per-Job atomic block. The sync runs inside one
`transaction.atomic()`; if it raises, all writes roll back. This is
Nautobot's default for Jobs.

**When you'd dial it.** Bulk syncs that hit per-row failures may want
finer-grained boundaries — e.g., commit per batch so a single bad row
doesn't lose 8,000 successful writes. Or coarser — commit-per-Job is
already the default, but you might explicitly want a full
`transaction.atomic()` wrapping every phase including pre-flight
validation.

**Alternatives today.** SSoT does not currently expose a knob for
transaction scope; it inherits Nautobot's per-Job atomic behavior. The
streaming pipeline's per-batch flushes commit incrementally — if the
sync fails mid-stream, already-flushed batches stay committed unless
the outer transaction rolls them back.

**Cost & tradeoffs.** Wider transactions hold locks longer (concurrency
cost). Narrower transactions risk partial-commit on failure
(consistency cost). The current default tries to balance both.

**How to wire it.** No SSoT-side flag today. If you need per-batch
commit, use the streaming pipeline — each `flush_creates` is its own
DB round-trip and will commit unless wrapped in an outer transaction
that fails.

---

### 8. Bulk-write batching

**What it controls.** Whether each row is INSERTed individually
(`save()`) or in batches (`bulk_create()` / `bulk_update()`).

**Default behavior.** `validated_save()` per row — one round-trip per
row.

**When you'd dial it.** When per-row INSERT round-trips dominate sync
time (typically true above a few hundred rows). The headline measurement
on the bundled benchmark: at medium scale (8,143 rows), switching from
`validated_save` to `bulk_b250` is **~30× faster** all by itself. This
is the single largest write-path lever in the menu.

**Alternatives.**

| Mode | Behavior | Cost |
|---|---|---|
| **Per-row save (default)** | One INSERT per row | N round-trips |
| **`bulk_create` / `bulk_update`** | One INSERT per batch (batch size configurable, default 250) | ⌈N / batch_size⌉ round-trips |

**Cost & tradeoffs.** `bulk_create()` skips:

* `post_save` signals (covered by axis 6)
* Per-row `clean()` (covered by axis 1)
* Per-row changelog (covered by axis 2)

You can selectively restore each of those with the relevant axis's
opt-in. `bulk_b250_audit` (`bulk_create` + `REFIRE_POST_SAVE` + deferred
changelog) demonstrates the full restoration — same audit semantics as
production at ~30× the speed.

**Batch size**. Default 250. Larger batches reduce round-trip count but
increase memory footprint per batch. Empirically 250 wins at our scale;
higher (1000) gives no measurable improvement.

**How to wire it.** Subclass the integration's `NautobotAdapter` with
`BulkOperationsMixin`, override each model's `create()` / `update()` to
queue rather than save, and call `self.flush_all()` in
`sync_complete()`. See the per-integration recipe in
[Part 3](#part-3--composing-it).

---

### 9. Memory shape

**What it controls.** Peak memory footprint during the diff phase.

**Default behavior.** Both adapters fully in memory (DiffSync model
instances), plus the `Diff` tree built by `src.diff_to(dst)`. At medium
scale, peak is ~30 MiB. The persisted `Sync.diff` JSONField also has a
~1 GB limit that real-world large diffs can exceed.

**When you'd dial it.** OOM on large initial syncs, or syncs whose diff
serialization would exceed the JSONField cap. Memory pressure is the
primary motivator — the streaming pipeline does not deliver dramatic
speed wins (see axis 9 vs axis 8 in the matrix).

**Alternatives.**

| Mode | Behavior | Peak memory at medium |
|---|---|---:|
| **In-memory `Diff` tree (default)** | Both adapters + `Diff` tree concurrent | ~30 MiB |
| **SQLite-backed streaming** | Dump each adapter to SQLite, release adapter store, walk SQLite for diff | ~20 MiB |
| **PyDict-backed streaming (analysis instrument)** | Same as SQLite but with Python dicts as the store | ~24 MiB |

**Cost & tradeoffs.** Streaming caps memory by holding only
`source_records` + `dest_records` in SQLite, releasing the in-memory
DiffSync model instances after dump. Memory savings scale with row
count: ~10 MiB freed at 8k rows projects to ~60 MiB at 100k and ~600
MiB at 1M.

The PyDict variant is a benchmark instrument, not a feature: it isolates
"what does SQLite specifically buy us?" — the answer is *memory*, not
speed. PyDict is ~5% faster but uses ~25% more memory than SQLite.
SQLite also enables features (validators, scope expansion) that PyDict
cannot.

**How to wire it.** `SSoTFlags.STREAMING` (Tier 1, per-row replay) or
`SSoTFlags.STREAM_TIER2` (= `STREAMING | BULK_WRITES`, bulk replay).

---

### 10. Sync scope

**What it controls.** Which subset of rows participates in a sync. Full
adapter (default), a subtree (everything under one parent), or a single
record.

**Default behavior.** Every row from the source adapter is loaded,
diffed, and synced. For a 14k-row Infoblox dataset, a full sync visits
all 14k rows — even if you only care about one.

**When you'd dial it.** When external events tell you exactly what
changed: an Infoblox webhook says prefix X is dirty, a user clicked
"Resync from SoT" on a Nautobot detail page, a scheduled job wants to
refresh just one VRF.

**Alternatives.**

| Mode | Behavior |
|---|---|
| **Full adapter (default)** | Every row participates |
| **Subtree-bounded** | Pass `scope=SyncScope("prefix", "10.0.0.0/8__Global")` — only rows in the subtree rooted there participate |
| **Single record** | Same as subtree but the scope identifies one row (subtree expander returns just that row) |

**Cost & tradeoffs.** Scope filters at the differ stage — load + dump
still process the full adapter unless the integration also implements a
source-side scoped load. Even without source-side optimization, the
diff and sync phases drop from "all rows" to "subtree only," typically
at least an order of magnitude.

For per-integration source-side scoped loads (load only the subtree
from the upstream API), each integration needs its own
`adapter.load(scope=...)`. Not built generically.

**How to wire it.**

```python
from nautobot_ssot.scope import SyncScope
from nautobot_ssot.utils.streaming_pipeline import run_streaming_sync

scope = SyncScope(
    model_type="prefix",
    unique_key="10.0.0.0/24__ns-default",
    integration="infoblox",
)
run_streaming_sync(src, dst, scope=scope, flags=SSoTFlags.STREAM_TIER2)
```

Or via the API endpoint (axis 14). For the contracts and per-integration
expanders, see the [Scope reference][ref-scope].

[ref-scope]: performance_validation_reference.md#scope-reference

---

### 11. Concurrency

**What it controls.** Whether source and target adapters load
sequentially or in parallel.

**Default behavior.** Sequential — source loads, then target loads.

**When you'd dial it.** When both adapters are I/O-bound and don't
contend for the same resource. Source is typically a remote API
(network-bound); target is the local Nautobot DB. Loading them
concurrently overlaps the wall-clock — about 50% wall-clock saving on
the load phase if both phases are similar in length.

**Alternatives.** Two settings: sequential (default) or parallel.

**Cost & tradeoffs.** Concurrent threads increase peak memory (both
adapters in flight at once). Doesn't help when one phase dominates the
other (sequential is already as fast as the slower phase).

**How to wire it.** `SSoTFlags.PARALLEL_LOADING`. The Job framework
handles the threading.

---

### 12. Dry-run

**What it controls.** Whether the sync writes or just computes the diff.

**Default behavior.** Dry-run is on by default in the Job UI (per
`DryRunVar` default). Engineers should explicitly turn it off to commit
writes.

**When you'd dial it.** Always on for the first run when wiring up a
new sync. Off for production runs.

**Alternatives.** On / off (the `DryRunVar`).

**Cost & tradeoffs.** Dry-run runs the load + diff phases; skips the
write phase. Same cost as a full sync minus the writes. Useful for
preview, capacity planning, and CI smoke tests.

**How to wire it.** `dryrun=True` on the Job.

---

### 13. Memory profiling

**What it controls.** Whether `tracemalloc` records peak memory per
phase and stores it on the `Sync` record.

**Default behavior.** Off. Memory tracking has measurable overhead.

**When you'd dial it.** Diagnosing OOM symptoms or budgeting a sync
against a memory ceiling.

**Alternatives.** On / off.

**How to wire it.** `SSoTFlags.MEMORY_PROFILING`. Populates
`Sync.<phase>_memory_*` fields.

---

### 14. External triggering

**What it controls.** What can start a sync — Job UI, scheduled task,
HTTP API, webhook receiver.

**Default behavior.** Job UI (manual) and the scheduler (cron-style
recurring jobs) — both inherited from Nautobot core.

**When you'd dial it.** When external systems should drive resyncs:

* External SoT pushes a change → fire a scoped resync within seconds
* Operator dashboard "Resync this row" button → fire a scoped resync
* Pipeline orchestrator (Argo, Airflow, etc.) → drive Nautobot syncs
  as part of a larger workflow

**Alternatives.**

| Trigger | Use case |
|---|---|
| **Job UI** (default) | Manual operator-initiated runs |
| **Scheduled** (Nautobot core) | Cron-style recurring syncs |
| **Scoped sync API** (`POST /api/plugins/ssot/sync/scoped/`) | External systems trigger targeted resyncs |
| **Per-integration webhook receiver** | Each integration ships its own authenticated receiver that translates the source's notification format into a `SyncScope` and calls the API |

**Cost & tradeoffs.** Webhook receivers are per-integration because
every source has a different payload format and auth scheme. The
framework provides the scope + pipeline + API; integrations provide the
authenticated receiver + payload translator.

**Coalescing high-volume webhooks.** A real-world risk: Infoblox runs a
batch update on 5,000 prefixes; webhook fires 5,000 times in 30 seconds.
Two patterns the framework should provide (today TODO):

* **Debounce** — same scope key arriving multiple times schedules one
  task and reschedules on each new arrival; runs after the burst settles.
* **Batch** — collect distinct scope keys for N seconds, emit ONE
  scoped sync with a multi-root scope.

For now, integrations should debounce in their own Celery tasks.

**How to wire it.** See the [API reference][ref-api] for the endpoint
contract and the per-integration recipe in
[Part 3](#part-3--composing-it) for webhook receiver scaffolding.

[ref-api]: performance_validation_reference.md#api-endpoint

---

## Part 3 — Composing it

### Pre-mixed presets

Each preset is a coordinate in the axis space. Numbers are TOTAL
pipeline seconds at medium scale (8,143 objects), per the bundled
benchmark.

> **Which row is "production"?** A real SSoT job runs inside a
> `JobChangeContext` — signals fire normally, the changelog handler
> creates `ObjectChange` rows per save, and `web_request_context`
> cleanup fires webhooks/jobhooks/events. The `validated_save` row below
> captures this — it's the cost shape today's deployments actually pay.
> The `validated_save_no_cl` row runs the same `validated_save()` calls
> outside a change context (no `web_request_context`), so the changelog
> signal handler short-circuits and no OC rows are written. Useful as a
> lower-bound reference, **not** what production runs.

The "audit chain" column tracks whether each mode produces ObjectChange
rows and fires webhooks / jobhooks / events.

| Preset | medium total | speedup vs prod | audit chain |
|---|---:|---:|---|
| **`validated_save`** ← **PRODUCTION today** | **163.31 s** | **1.00 ×** | **FULL** — per-row OC + webhooks/jobhooks/events |
| `validated_save_no_cl` (no change context — reference only) | 40.95 s | 3.99 × | none — signal handler short-circuits |
| `save` (no clean, no change context) | 29.31 s | 5.57 × | none |
| `save_immediate_cl` (production minus clean) | 132.32 s | 1.23 × | full (no clean) |
| `save_deferred_cl` | 77.63 s | 2.10 × | full (no clean), batched OC |
| `bulk_b250` | 4.91 s | 33.28 × | none |
| `bulk_b1000` (b=1000) | 5.04 s | 32.38 × | none |
| **`bulk_b250_audit`** (`bulk_create` + `REFIRE_POST_SAVE` + deferred CL) | **4.85 s** | **33.67 ×** | **FULL** — same audit as production, no streaming |
| `stream_tier1` (`STREAMING`) | 88.28 s | 1.85 × | **FULL** — deferred CL |
| **`stream_tier1_5`** (`STREAMING \| BULK_WRITES \| VALIDATE_SOURCE_SHAPE \| VALIDATE_ON_DUMP`) | 1.83 s | **89.27 ×** | none (validation only) |
| **`stream_tier1_7`** (`STREAM_TIER1_5 \| VALIDATE_RELATIONS`) | 2.04 s | 79.93 × | none (validation only) |
| **`stream_tier2_audit`** (`STREAMING \| BULK_WRITES \| REFIRE_POST_SAVE` + `deferred_change_logging`) | **1.50 s** | **108.98 ×** | **FULL** — bulk write + REFIRE + deferred OC + webhook fan-out |
| `stream_tier2` (`STREAMING \| BULK_WRITES`, SQLite store) | 1.28 s | 127.93 × | none |
| `stream_tier2_pydict` (PyDict store — benchmark instrument) | 1.23 s | 132.80 × | none — PyDict has no `.conn` |

### Selection guide

| If your top concern is… | Recommended preset | Notes |
|---|---|---|
| Operating like today, just with bigger inputs | `NONE` (defaults) | no behavior change |
| **Maximum speed with full audit chain** (no streaming required) | **`bulk_b250_audit`** | the headline option — same audit as production at ~30× the speed |
| Maximum speed, no audit needed | `STREAM_TIER2` | fastest measured at ~110× |
| Speed + concern about garbage source data | `STREAM_TIER1_5` (+ `Strict<Adapter>`) | catches malformed input; ~150 ms slower than `STREAM_TIER2` |
| Speed + relational validation (IP-in-prefix etc.) | `STREAM_TIER1_7` | adds ~37 µs/row for the IP-in-prefix Phase B validator |
| OOM on large initial syncs | `STREAM_TIER2` or `STREAM_TIER1_5` | streaming caps memory |
| Multi-tenant / shared customer infra (full audit, accept the speed hit) | `STREAM_TIER1` | preserves changelog for compliance |
| Targeted resync from external trigger | `STREAM_TIER2` + `SyncScope(...)` | scope filter restricts to the subtree |

### What `deferred_change_logging` actually buys you

The `save` / `save_immediate_cl` / `save_deferred_cl` triplet
decomposes the changelog cost. At medium scale per-row times:

| operation | per-row cost |
|---|---:|
| `save()` round-trip | **3.0 ms** |
| `+` `full_clean()` (production has this; benchmark `save_*_cl` modes do not) | **+1.7 ms** |
| `+` per-row `to_objectchange()` serialization | **+6.3 ms** (paid in both immediate and deferred) |
| `+` per-row OC INSERT (immediate mode) | **+7.4 ms** |
| `+` batched OC INSERT (deferred mode) | **+0.0 ms** (amortized into one bulk_create) |

Production = save + clean + serialize + INSERT ≈ **18.4 ms/row**, ~150 s
at medium scale. `deferred_change_logging`'s actual contribution is the
INSERT amortization — about **7 ms saved per row, ~58 s on the medium
benchmark**. Serialization cost is unchanged.

That's a 43% speedup over the per-save changelog default — useful when:

* you NEED changelog (audit, webhooks, jobhooks, per-object signals), AND
* you CAN'T switch to `BULK_WRITES`

If you don't need changelog, `BULK_WRITES` (Tier 2) is the better
operating point — 1.5 s vs 78 s.

### Deferred-X: SSoTFlags + contexts compose

The flags control **whether the side-effect signals fire at all** —
contexts then control **how the side-effects get batched once they
fire**. Practical recipes:

| Goal | Flags | Contexts |
|---|---|---|
| Maximum speed, no side-effects | `STREAM_TIER2` | none |
| Speed + Nautobot core post_save handlers (per-row replay) | `STREAM_TIER2 \| REFIRE_POST_SAVE` | none |
| Speed + batched Cable propagation specifically | `STREAM_TIER2 \| BULK_SIGNAL` | `deferred_domainlogic_cable()` |
| Speed + audit + webhooks/jobhooks/events | `STREAM_TIER2 \| REFIRE_POST_SAVE` | `web_request_context()`, `deferred_change_logging_for_bulk_operation()` |
| Speed + audit + Cable propagation batched | `STREAM_TIER2 \| REFIRE_POST_SAVE \| BULK_SIGNAL` | all three above |
| Today's default (per-row, full audit) | none | `web_request_context()` (handled by Job framework) |

For the Cable case specifically — why per-row replay is sometimes the
wrong shape — see the [Deferred-X reference][ref-deferred-x].

---

### Per-integration recipe

The framework in `nautobot_ssot/utils/` is integration-agnostic. Each
integration adds glue files that wire its DiffSync models to the
framework. The recipe shape is the same regardless of integration. For a
working reference, see Infoblox's implementation —
`nautobot_ssot/integrations/infoblox/diffsync/`.

#### Step 1 — Strict source models (optional, for axis 1 source-shape validation)

**File: `nautobot_ssot/integrations/<myint>/diffsync/models/validated.py`**

```python
from nautobot_ssot.utils.diffsync_validators import IPAMShapeValidationMixin
from .base import (  # your existing source-side DiffSync models
    MyIntPrefix, MyIntIPAddress, MyIntVLAN,
)

class StrictMyIntPrefix(IPAMShapeValidationMixin, MyIntPrefix):
    pass

class StrictMyIntIPAddress(IPAMShapeValidationMixin, MyIntIPAddress):
    pass
# … one Strict* subclass per source model
```

**File: `nautobot_ssot/integrations/<myint>/diffsync/adapters/<myint>_strict.py`**

```python
from .<myint> import MyIntAdapter
from ..models.validated import StrictMyIntPrefix, StrictMyIntIPAddress

class StrictMyIntAdapter(MyIntAdapter):
    prefix = StrictMyIntPrefix
    ipaddress = StrictMyIntIPAddress
```

The mixin only validates fields the model actually has (`network`,
`prefix`, `address`, `prefix_length`, `vid`, `dns_name`) — safe to
apply to any IPAM-shaped DiffSync model. For non-IPAM integrations,
write your own mixin following the same `@field_validator(...,
check_fields=False)` pattern.

#### Step 2 — Bulk write adapter (axis 8)

**File: `nautobot_ssot/integrations/<myint>/diffsync/adapters/nautobot_bulk.py`**

```python
from <orm.models> import OrmFoo, OrmBar
from nautobot_ssot.utils.bulk import BulkOperationsMixin
from nautobot_ssot.utils.validator_registry import ValidatorRegistry
from nautobot_ssot.utils.validators_ipam import IPInPrefixValidator
from ..models.nautobot import NautobotFoo, NautobotBar
from .nautobot import NautobotMyIntAdapter

# 1) Override each model.create() to queue instead of validated_save()
class BulkNautobotFoo(NautobotFoo):
    @classmethod
    def create(cls, adapter, ids, attrs):
        _orm = OrmFoo(field=ids["field"])
        adapter.foo_map[ids["field"]] = _orm.pk     # update lookup map
        adapter.queue_for_create(OrmFoo, _orm)
        return NautobotFoo.create(ids=ids, adapter=adapter, attrs=attrs)

# 2) Compose the bulk adapter
class BulkNautobotMyIntAdapter(BulkOperationsMixin, NautobotMyIntAdapter):
    foo = BulkNautobotFoo
    bar = BulkNautobotBar

    _bulk_create_order = [OrmFoo, OrmBar]   # FK dependency order

    # Optional: register relational validators for axis 1 sub-axis (relational)
    validator_registry = ValidatorRegistry([
        IPInPrefixValidator(),
    ])

    # Optional: per-field validation hook (axis 1 sub-axis)
    def to_orm_kwargs(self, model_type, ids, attrs):
        if model_type == "foo":
            return OrmFoo, {"field": ids["field"]}, []
        if model_type == "bar":
            return OrmBar, {"name": ids["name"]}, ["foo"]
        return None
```

`to_orm_kwargs()` returning `None` for a model_type cleanly opts that
type out of `clean_fields`-at-dump validation. The `exclude_fk_fields`
list keeps `clean_fields()` from blowing up on unset FK fields (those
are validated by DB constraints at INSERT, not Python).

#### Step 3 — What you DON'T need to write

The framework handles all of these — no per-integration code:

* SQLite store schema and connection management
* `dump_adapter()` walking `top_level` + `_children`
* Streaming differ (SQL set ops on `source_records` + `dest_records`)
* `BulkSyncer` orchestration (action replay, FK-ordered flush)
* Phase A / B / C validator dispatch
* Flag plumbing (`SSoTFlags.STREAMING`, `BULK_WRITES`, `VALIDATE_*`)
* `Sync.diff` summary-write workaround
* Job-level wiring (`DataSyncBaseJob.flags` MultiChoiceVar, the
  `sync_data()` branch on `STREAMING`)

#### Step 4 — Per-integration knowledge

* **FK ordering**: `_bulk_create_order` must list ORM classes
  parent-first; otherwise `bulk_create()` hits FK violations.
* **Adapter maps**: queueing requires updating
  `adapter.<thing>_map[key] = orm.pk` *before* the queued object is
  flushed, so children referencing the parent by PK can resolve it. UUID
  PKs are set at `OrmModel(...)` instantiation, so this is
  straightforward.
* **Post-flush hooks**: integrations that need extra bulk-write work
  after `flush_all()` (e.g., Infoblox bulk-inserts `extras_taggeditem`
  rows) define a `bulk_sync_complete()` method on the adapter;
  `BulkSyncer` calls it automatically.

#### Step 5 — Test the new integration

1. Run the bundled benchmark pattern for your integration:
   ```bash
   python scripts/benchmark_<myint>.py --stream-tier2 medium
   python scripts/benchmark_<myint>.py --stream-tier1-7 medium
   ```
2. Add to the matrix runner if you want it included in the
   cross-integration table.
3. Wire a smoke test like `scripts/test_phase_a_validators.py` to
   confirm your registered validators actually fire.

---

For mechanical contracts (the `SSoTFlags` enum reference, validator
registry interface, deferred-X context shape, scope API, full file
manifest), see the [Performance & Validation Reference][ref] document.

[ref]: performance_validation_reference.md
