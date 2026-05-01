# Performance & Validation Design Notes

!!! abstract "Status: design notes, not a shipping framework"
    This document is a **menu of design choices** for SSoT performance and correctness, originally written alongside [PR #1194](https://github.com/nautobot/nautobot-app-ssot/pull/1194)'s prototype. It records the design conversation; it is **not** documentation of features available in `develop`.

    Every alternative below is labeled:

    - **(today)** — works on the current `develop` branch using shipped Nautobot core / SSoT primitives.
    - **(proposed)** — sketched in PR #1194's prototype only. The framework primitives (`SSoTFlags`, the streaming pipeline, `BulkOperationsMixin`, `validator_registry`, `SyncScope`, the scoped-sync API, `deferred_domainlogic_*` contexts) are **not** in `develop`. Treat them as design proposals.

    For tuning advice you can apply right now, see the [user-facing Performance chapter](../user/performance.md). This document is for engineers thinking about where SSoT could go next.

Nautobot SSoT and DiffSync provide a straightforward ETL (Extract, Transform, Load) framework with many features out of the box. ETL is not a new idea, so the goal isn't to invent a new technology — it's to provide structure and best practices around one. The platform's default behavior follows a KISS (Keep It Simple, Stupid) approach: the slow, safe, boring path that's correct out of the box. With that approach and the breadth of features available, there are — as always — tradeoffs worth considering.

These features aren't always easy to understand, and their performance implications (wall-clock time, CPU, memory, I/O) aren't always obvious from the API surface. The most common pattern for loading data into Nautobot includes the following:

* Every object is validated for correctness
* Every object creates a changelog entry tracking the change
* Every object dispatches webhooks
* Every object fires job hooks
* Every object publishes an event
* Some objects fire additional Django signals for:
    * Cache invalidation
    * Data cleanup
    * Other custom business logic
* Dry-run mode lets you preview changes
* Per-job change tracking is recorded automatically

Some — or even all — of these features may not be needed for your implementation. For example, if you're migrating from a legacy system where data ownership is not yet established, do you really need a changelog? Do you want webhooks firing if you're syncing thousands of records in one go?

Sometimes the answer is a resounding yes; other times a clean no. Sometimes you want most of these features but are willing to trade a slightly weaker correctness guarantee for speed. Sometimes you already know the data is valid and don't need to validate it again. There are many reasons to choose speed over the KISS default — and this document is intended to make those decisions clear.

---

## How to read this doc

* **Part 1 — the anatomy of a sync** lays out what fires per object today and frames each downstream effect as a knob you can dial.
* **Part 2 — the axes** is one chapter per behavioral knob, in roughly the order most engineers think about them. Each chapter follows the same shape: *what it controls, default behavior, when you'd dial it, alternatives, cost & tradeoffs, how to wire it*. Each "alternative" is tagged **(today)** or **(proposed)**.
* **Part 3 — composing it** offers pre-mixed presets, the measured matrix from PR #1194's benchmark, and a per-integration recipe for the proposed framework.
* For the mechanical contracts referenced from Part 2 (the proposed `SSoTFlags` enum, the validator registry interface, the deferred-X context shape, the scope API) see the companion [Performance & Validation Reference][ref] document.

[ref]: performance_validation_reference.md

### What lives where

A recurring critique of this menu has been that some axes describe work that arguably belongs in **DiffSync** or **Nautobot core** rather than SSoT. That's a fair scoping question, and the matrix below records where each lever's *implementation* would naturally live so future contributors can pick the right repo:

| Axis | Implementation home |
|---|---|
| 1. Validation — source-shape (Pydantic) | SSoT (sits on top of DiffSync's load) |
| 1. Validation — `clean_fields()` at dump | SSoT (or DiffSync, if dump-time hooks are exposed) |
| 1. Validation — relational / phased | SSoT |
| 1. Validation — model `clean()` / `bulk_clean` | Nautobot core (`bulk_clean` doesn't exist yet) |
| 2. Change logging — deferred batch | Nautobot core (already shipped) |
| 3. Webhooks — batched dispatch | Nautobot core |
| 4. Job hooks — batched dispatch | Nautobot core |
| 5. Events — batched publish | Nautobot core |
| 6. `post_save` consumers — batched form | Nautobot core (per-handler) |
| 7. Atomic transactions — granularity | SSoT (caller of `transaction.atomic`) |
| 8. Bulk-write batching | SSoT (orchestrates `bulk_create` / `bulk_update`) |
| 9. Memory shape — streaming store | SSoT (or DiffSync if dump abstraction lifts) |
| 10. Sync scope | SSoT (and per-integration adapter) |
| 11. Concurrency — parallel adapter loading | SSoT (already shipped) |
| 12. Dry-run | Nautobot core (already shipped via `DryRunVar`) |
| 13. Memory profiling | SSoT (already shipped) |
| 14. External triggering — scoped-sync API | SSoT (and per-integration receiver) |

So roughly half the menu is genuinely SSoT-shaped; the other half either ships in core today or would need core changes to be done well. PR #1194 explores the SSoT-shaped half plus a placeholder for the core-shaped half (`BULK_CLEAN`); landing the full menu would require coordinated work across DiffSync, SSoT, and Nautobot core.

### Where this menu doesn't help

A separate, valid critique: **at very large scale (millions of rows in a first-time load) none of these axes replace a bespoke loader.** The framework here helps the long middle — incremental syncs, small-bulk migrations, scope-bounded refreshes. For initial-load workloads in the hundreds-of-thousands-to-millions range, you will want to stream from source to database directly without ever materializing both adapters; that's its own design and not what this menu is for.

### The benchmark substrate

The numbers throughout this document come from the bundled benchmark in PR #1194 (`scripts/benchmark_infoblox.py --matrix`), which exercises the prototype at three scales — tiny / small / medium (8,143 objects). They are **measurements of the prototype implementation against the Infoblox integration on a development container**, not universal SSoT speedups. They are useful for the relative ordering of choices; absolute numbers will vary by integration, dataset shape, and infrastructure.

Re-run via:

```bash
./scripts/run_benchmark_matrix.sh
```

Inside the dev container, the sourced env wrapper handles DB / Redis hosts. All numbers in this document are from medium scale. The "audit chain" column in §3 tracks whether each mode produces `ObjectChange` rows and fires webhooks/jobhooks/events — that distinction matters more than raw speed for many integrations.

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

Every yellow node above is a knob. The default path is the leftmost — the KISS guarantee. The other branches exist because not every sync needs the full default chain, and the framework lets you opt out of pieces you've measured aren't worth the cost.

The rest of Part 2 walks through each axis individually. Most are independent and compose freely.

---

## Part 2 — The axes

### 1. Validation

**What it controls.** What gets checked about each row, when, and how expensively, before the row reaches the database.

**Default behavior.** `validated_save()` runs Django's `full_clean()` on every row before INSERT. That means: per-field validators (CIDR / IP / choices), the model's own `clean()` method (which often does its own DB queries — e.g., `IPAddress._get_closest_parent`), and uniqueness checks. Cost is roughly **1.7 ms/row** of `full_clean()` time on top of save (measured against Infoblox on the prototype).

**When you'd dial it.** When you have ~thousands of rows and the per-row clean cost becomes a meaningful share of total sync time, OR when you want validation that the model's own `clean()` method does not provide (cross-row uniqueness, prefix overlap, IP-in-prefix containment).

**Alternatives.** Five sub-axes, layered:

| Sub-axis | Status | When it runs | Cost | Activated by |
|---|---|---|---|---|
| **Source-shape** validation (Pydantic) | **(today, DIY)** | At `adapter.load()` time, before diff | µs/row | Per-integration: subclass source models with a Pydantic validation mixin and use a `Strict<Adapter>` |
| **Per-field** validation (`clean_fields()`) | **(today, DIY)** | At dump time, no DB round-trip | 10–20 µs/row | Call `instance.clean_fields(exclude=[...])` before flush in your bulk flush routine |
| **Relational / cross-row** validation | **(today, DIY — formalized in PR #1194 as `VALIDATE_RELATIONS`)** | Phase A (pre-flush) / B (between flushes) / C (post-flush) | Depends; e.g. IP-in-prefix Phase B ≈ 37 µs/row in the prototype | Today: write a custom check before / between / after flushes. Proposed: `SSoTFlags.VALIDATE_RELATIONS` + a `validator_registry` on the adapter |
| **Model `clean()`** | **(today)** | Per row, inside `validated_save()` | ~1.7 ms/row | Default; on by definition when using `validated_save()` |
| **Batched `bulk_clean()`** | **(proposed in Nautobot core; not shipped)** | Once per flush stage in bulk pipeline | Depends on the model | `SSoTFlags.BULK_CLEAN`; **no-op until Nautobot core ships `Model.bulk_clean(instances)`** |

**Cost & tradeoffs.** Source-shape and per-field validation are cheap enough to leave on for any sync that cares about catching bad data early. Relational validation costs depend on the validator: a single batched DB query per validator (like `IPInPrefixValidator`) is cheap; naïve per-row queries are not. `validated_save`'s `full_clean()` is the expensive default — it dominates per-row save cost at scale.

**Tightening the failure mode.** PR #1194 proposes `SSoTFlags.VALIDATE_STRICT` to flip per-field and relational validators from log-and-continue to raise. Today, a custom validator can raise on its own.

**How to wire it. (today)** Implement source-shape validators per-integration as a Pydantic mixin layered onto the source DiffSync models. Call `clean_fields(exclude=fk_field_names)` on each instance before `bulk_create`. Run cross-row checks as plain SQL aggregates. **(proposed)** For the contracts of the proposed registry, see the [Validation reference][ref-validation].

[ref-validation]: performance_validation_reference.md#validation-registry

---

### 2. Change logging — `ObjectChange` rows

**What it controls.** Whether each create/update/delete writes an `ObjectChange` row in the Nautobot database recording who changed what when.

**Default behavior.** Every `validated_save()` (or plain `save()`) inside a `web_request_context` fires `post_save`, which the changelog signal handler captures and INSERTs as one `ObjectChange` per row. That's full per-row audit, paid as ~7.4 ms/row INSERT plus ~6.3 ms/row of `to_objectchange()` serialization on the prototype's medium scale.

**When you'd dial it.** Two opposing pressures:

* You don't need the audit trail (initial bulk load, throwaway migration, dev / fixture data) — turn it off entirely.
* You need the audit trail but the per-row INSERT cost is dominating total time — batch the INSERTs.

**Alternatives.**

| Mode | Status | Behavior | When it runs | Cost |
|---|---|---|---|---|
| **Per-row immediate (default)** | **(today)** | One `ObjectChange` INSERT per save, in the same DB round trip | inside `web_request_context` | ~7.4 ms/row INSERT + ~6.3 ms/row serialization |
| **Deferred-batched** | **(today)** | Captures `ObjectChange`s during the block, flushes them in one `bulk_create` at end of block | inside `deferred_change_logging_for_bulk_operation()` | ~6.3 ms/row serialization (no INSERT amortized in) |
| **None** | **(today)** | `bulk_create()` skips `post_save` so no `ObjectChange`s are written | when you call `bulk_create` outside a change context, or run with the proposed `BULK_WRITES` flag | 0 |

**Cost & tradeoffs.** Deferring the changelog saves the INSERT round-trip cost (~43% speedup over per-save in the prototype's medium benchmark) but **does not** save the serialization cost — `to_objectchange()` runs per row regardless. If you need the audit trail and you have thousands of rows, deferred is strictly better than immediate. If you don't need the audit trail, skipping it entirely is dramatically better.

**How to wire it. (today)**

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

To skip the changelog entirely, run `bulk_create()` outside any `web_request_context` (the changelog signal handler short-circuits when no change context is active).

---

### 3. Webhooks

**What it controls.** Outbound HTTP notifications fired in response to data changes.

**Default behavior.** Webhooks are dispatched at the end of a `web_request_context` block, iterating the `ObjectChange` rows produced during the block and matching them against configured `Webhook` objects. One outbound HTTP call per matching `ObjectChange` × webhook configuration.

**When you'd dial it.** Almost always when running a bulk migration — firing 8,000 webhooks for a single sync rarely matches what downstream consumers expect. Dialing the underlying changelog axis to "none" turns off webhooks too (no `ObjectChange` rows means no webhooks).

**Alternatives.**

| Mode | Status | Behavior | Cost |
|---|---|---|---|
| **Per-row immediate** | **(today)** — inherent to Nautobot | One webhook fired per row at end of `web_request_context` | proportional to row count × matching webhook count |
| **Deferred-batched (via deferred CL)** | **(today)** | All `ObjectChange`s land in one `bulk_create`, then `web_request_context` cleanup iterates them — webhooks still fire one per row, just at end-of-block | same dispatch cost; only the OC INSERT cost is amortized |
| **None** | **(today)** | No `ObjectChange` rows → no webhooks dispatched | 0 |

**Cost & tradeoffs.** Webhooks are unconditionally per-row. SSoT does not currently provide a "batched webhook" primitive — that would need either a Nautobot-core change to webhook dispatch, or a per-integration deferred context that captures webhook calls and batches them.

**How to wire it.** Driven by axis 2 (change logging). Disable changelog → webhooks don't fire. Keep changelog → webhooks fire normally.

---

### 4. Job hooks

**What it controls.** Nautobot `JobHook` objects firing in response to data changes, identical dispatch shape to webhooks but firing internal Jobs instead of HTTP calls.

**Default behavior.** Same as webhooks — driven by `ObjectChange` creation. Each matching `JobHook` enqueues a Celery task to run the target Job at end of `web_request_context`.

**When you'd dial it.** Same as webhooks. A bulk migration that triggers thousands of background Jobs is rarely what you want.

**Alternatives.** Same shape as webhooks — driven by axis 2 (change logging).

**Cost & tradeoffs.** Per-row dispatch into the Celery queue. The Jobs themselves run async, so the synchronous cost is just the enqueue. But the queued backlog is real — tens of thousands of queued Jobs can cascade into hours of work for the worker pool.

**How to wire it.** Driven by axis 2.

---

### 5. Events (Nautobot Event framework)

**What it controls.** Nautobot's pub/sub Event publication on data changes, used by external event subscribers (monitoring systems, analytics pipelines, integrations).

**Default behavior.** Same shape as webhooks and job hooks — driven by `ObjectChange` creation. One event published per `ObjectChange` at end of `web_request_context`.

**When you'd dial it.** Same as webhooks. If your event subscribers are designed for high-rate streams, leaving them on may be fine; if they're designed for human-paced changes, a bulk sync will spam them.

**Alternatives.** Same as webhooks — driven by axis 2.

**Cost & tradeoffs.** Async fan-out via the configured event broker (NATS, Redis Streams, etc.) — synchronous cost is just the publish call, but downstream load can be substantial.

**How to wire it.** Driven by axis 2.

---

### 6. Business-logic signals (post_save consumers)

**What it controls.** Nautobot core's `post_save` handlers — Cable propagation, Rack location cascading, custom-field cache invalidation, search-index updates, virtual-chassis assignment, etc. These are NOT gated on `web_request_context`; they fire on every `save()` regardless of changelog.

**Default behavior.** With per-row `validated_save()` or `save()`, every `post_save` handler fires per row. With `bulk_create()`, **none of them fire** — that's where the speed comes from, but it silently loses every side-effect they were responsible for.

**When you'd dial it.** Whenever you choose `bulk_create`-based writes, you've implicitly dialed this to "none." You then have to decide whether that's acceptable for the models you're touching.

**Alternatives.**

| Mode | Status | Behavior | Cost | Activated by |
|---|---|---|---|---|
| **Per-row Django `post_save`** | **(today)** | Default; one signal dispatch per row | proportional to row count × handler count | Default for `save()` / `validated_save()` |
| **Refire after bulk** | **(today, DIY — formalized in PR #1194 as `REFIRE_POST_SAVE`)** | After each bulk batch, loop and re-fire `post_save` per instance — restores Nautobot core handlers (Cable, Rack, custom-field cache, …) | per-row dispatch — pays back some bulk speed | Today: manual `for instance in batch: post_save.send(...)`. Proposed: `SSoTFlags.REFIRE_POST_SAVE` |
| **Per-batch dispatch** | **(proposed)** | Fires `bulk_post_create` / `bulk_post_update` / `bulk_post_delete` once per FK stage with the full batch of instances | one signal per stage | `SSoTFlags.BULK_SIGNAL` (subscribers must be written for the batched form) |
| **Shape-B batched contexts** | **(proposed)** | Per-domain context that captures a signal during the block, runs one batched implementation at end of block — e.g. `deferred_domainlogic_cable` | per-domain, dramatically cheaper than per-row replay when the handler does cross-row work | Wrap the sync in `nautobot_ssot.contexts.deferred_domainlogic_*` (PR #1194) |
| **None** | **(today)** | All post_save consumers skipped | 0 | Bare `bulk_create` with no replay/wrapper |

**Audit of what's at risk.** When `bulk_create` runs with no replay (true today; same risk applies to the proposed `BULK_WRITES`):

| Category | Examples | Consequence |
|---|---|---|
| Cable / connection propagation | `update_connected_endpoints`, `nullify_connected_endpoints` | `Cable.connection_state` never updates; `link_peer` references stay stale |
| Location cascading | `handle_rackgroup_location_change`, `handle_rack_location_change` | Child Racks / Devices keep old location after parent moves |
| Cluster membership | `assign_virtualchassis_master`, `clear_virtualchassis_members`, `clear_deviceredundancygroup_members` | VirtualChassis never picks a master; redundancy group members not detached on delete |
| Cross-model validation (m2m) | `prevent_adding_tagged_vlans_with_incorrect_mode_or_site`, `validate_vdcs_interface_relationships`, `vrf_prefix_associated`, `vrf_device_associated` | Validation Nautobot relies on for row consistency doesn't run |
| Cache invalidation | `invalidate_choices_cache`, `invalidate_relationship_models_cache`, `invalidate_validation_rule_caches`, `invalidate_models_cache` | Stale cached choices / metadata / validation rules until something else invalidates them |

**IPAM models** (Namespace, Prefix, IPAddress, VLAN, VLANGroup) have **no direct `post_save` handlers** in core — `bulk_create` alone is safe for IPAM-only syncs. **DCIM models** (Cable, Rack, RackGroup, VirtualChassis, etc.) DO have handlers that do real work — pair with re-fire or batched contexts.

**Cost & tradeoffs.** Re-firing `post_save` is per-row (N invocations). Per-batch dispatch is one dispatch per stage. Shape-B contexts (like `deferred_domainlogic_cable`) deliver the highest leverage — one batched call against the whole set instead of N — but require the handler to be rewritten or replaced. The [Deferred-X reference][ref-deferred-x] documents the contract for writing new shape-B contexts.

**How to wire it. (today)** Manually re-fire `post_save` per instance after a `bulk_create` batch when correctness requires it. **(proposed)** Set `SSoTFlags.REFIRE_POST_SAVE` / `BULK_SIGNAL` and wrap with `deferred_domainlogic_*` contexts.

[ref-deferred-x]: performance_validation_reference.md#deferred-x-context-contract

---

### 7. Atomic transactions

**What it controls.** The granularity of rollback. If part of the sync fails, what gets rolled back?

**Default behavior. (today, Nautobot 2.x)** Jobs are **not** wrapped in a single atomic transaction by default — each ORM call commits independently unless your code explicitly opens a `transaction.atomic()` block. (This changed from Nautobot 1.x, where every Job was atomic by default.)

**When you'd dial it.** Bulk syncs that hit per-row failures may want finer-grained boundaries — e.g., commit per batch so a single bad row doesn't lose 8,000 successful writes. Or coarser — wrap the whole sync in `transaction.atomic()` if all-or-nothing semantics matter.

**Alternatives. (today)**

| Mode | Behavior |
|---|---|
| **Per-call commit (default)** | Each ORM call commits independently; partial failures leave partial state |
| **Whole-sync atomic** | Wrap `execute_sync` in `transaction.atomic()` for all-or-nothing semantics |
| **Per-batch atomic** | Wrap each bulk flush in `transaction.atomic()` for batch-granular rollback |

The streaming pipeline proposal in PR #1194 commits per-batch by virtue of how it flushes; if that lands, this axis would gain a coordinated `commit_per_batch` knob.

**Cost & tradeoffs.** Wider transactions hold locks longer (concurrency cost). Narrower transactions risk partial-commit on failure (consistency cost).

**How to wire it. (today)** Wrap the relevant code with `from django.db import transaction; with transaction.atomic(): ...`.

---

### 8. Bulk-write batching

**What it controls.** Whether each row is INSERTed individually (`save()`) or in batches (`bulk_create()` / `bulk_update()`).

**Default behavior.** `validated_save()` per row — one round-trip per row.

**When you'd dial it.** When per-row INSERT round-trips dominate sync time (typically true above a few hundred rows). The headline measurement on the bundled benchmark: at medium scale (8,143 rows), switching from `validated_save` to `bulk_create(batch_size=250)` was about 30× faster on the prototype's Infoblox dataset. This is the single largest write-path lever in the menu.

**Alternatives.**

| Mode | Status | Behavior | Cost |
|---|---|---|---|
| **Per-row save (default)** | **(today)** | One INSERT per row | N round-trips |
| **`bulk_create` / `bulk_update`** | **(today)** — already used by DNA Center / Meraki / ServiceNow integrations | One INSERT per batch (batch size configurable, default 250) | ⌈N / batch_size⌉ round-trips |
| **Generalized `BulkOperationsMixin` + adapter wiring** | **(proposed)** | Framework-managed queue + flush ordering + audit-chain integration | Same as `bulk_create` underneath |

Existing SSoT integrations that use `bulk_create` today, for reference:

* `nautobot_ssot/integrations/dna_center/diffsync/adapters/nautobot.py` (`bulk_create_update`)
* `nautobot_ssot/integrations/meraki/diffsync/adapters/nautobot.py`
* `nautobot_ssot/integrations/servicenow/diffsync/adapter_servicenow.py` (`bulk_create_interfaces`)

**Cost & tradeoffs.** `bulk_create()` skips:

* `post_save` signals (covered by axis 6)
* Per-row `clean()` (covered by axis 1)
* Per-row changelog (covered by axis 2)

You can selectively restore each of those with the relevant axis's opt-in. The prototype's `bulk_b250_audit` preset (`bulk_create` + re-fire `post_save` + deferred changelog) demonstrates the full restoration — same audit semantics as production at much higher throughput on the Infoblox benchmark.

**Batch size.** `batch_size=250` is the value used across SSoT integrations today and is a reasonable default. Larger batches reduce round-trip count but increase memory footprint per batch. Empirically 250 wins at the prototype's scale; higher (1000) gives no measurable improvement. Beyond a few thousand rows per batch you risk hitting the database parameter limit on a single statement.

**How to wire it. (today)** Subclass the integration's `NautobotAdapter`, override each model's `create()` / `update()` to queue ORM instances rather than save, and call `objects.bulk_create(...)` in `sync_complete()`. The DNA Center adapter is a working reference. **(proposed)** PR #1194 proposes `BulkOperationsMixin` to encapsulate the queue/flush plumbing — see the [Per-integration recipe](#per-integration-recipe) below.

---

### 9. Memory shape

**What it controls.** Peak memory footprint during the diff phase.

**Default behavior.** Both adapters fully in memory (DiffSync model instances), plus the `Diff` tree built by `src.diff_to(dst)`. At the prototype's medium scale, peak is ~30 MiB. The persisted `Sync.diff` JSONField also has a practical size limit that real-world large diffs can exceed.

**When you'd dial it.** OOM on large initial syncs, or syncs whose diff serialization would exceed the JSONField cap. Memory pressure is the primary motivator — the streaming pipeline does not deliver dramatic speed wins relative to plain bulk writes.

**Alternatives.**

| Mode | Status | Behavior | Peak memory at the prototype's medium scale |
|---|---|---|---:|
| **In-memory `Diff` tree (default)** | **(today)** | Both adapters + `Diff` tree concurrent | ~30 MiB |
| **SQLite-backed streaming** | **(proposed)** | Dump each adapter to SQLite, release adapter store, walk SQLite for diff | ~20 MiB |
| **PyDict-backed streaming (analysis instrument)** | **(proposed; benchmark instrument only)** | Same as SQLite but with Python dicts as the store | ~24 MiB |

**Cost & tradeoffs.** Streaming caps memory by holding only `source_records` + `dest_records` in SQLite, releasing the in-memory DiffSync model instances after dump. Memory savings scale with row count: ~10 MiB freed at 8k rows projects to ~60 MiB at 100k and ~600 MiB at 1M.

The PyDict variant is a benchmark instrument, not a feature: it isolates "what does SQLite specifically buy us?" — the answer is *memory*, not speed. PyDict is ~5% faster but uses ~25% more memory than SQLite. SQLite also enables features the proposal layers on top (validators, scope expansion) that PyDict cannot.

**How to wire it. (today, DIY)** For ad-hoc large migrations, manually dump adapter state to a temporary SQLite file and walk it for the diff, releasing the adapter from memory in between. **(proposed)** PR #1194 packages this as `SSoTFlags.STREAMING` / `SSoTFlags.STREAM_TIER2`.

---

### 10. Sync scope

**What it controls.** Which subset of rows participates in a sync. Full adapter (default), a subtree (everything under one parent), or a single record.

**Default behavior.** Every row from the source adapter is loaded, diffed, and synced. For a 14k-row Infoblox dataset, a full sync visits all 14k rows — even if you only care about one.

**When you'd dial it.** When external events tell you exactly what changed: an Infoblox webhook says prefix X is dirty, a user clicked "Resync from SoT" on a Nautobot detail page, a scheduled job wants to refresh just one VRF.

**Alternatives.**

| Mode | Status | Behavior |
|---|---|---|
| **Full adapter (default)** | **(today)** | Every row participates |
| **Per-integration sync filters** | **(today)** | Many integrations support config-driven filters (e.g., Infoblox network views, ServiceNow company groups) that restrict the source-side load |
| **Subtree-bounded (`SyncScope`)** | **(proposed)** | `scope=SyncScope("prefix", "10.0.0.0/8__Global")` — only rows in the subtree rooted there participate |
| **Single record** | **(proposed)** | Same as subtree but the scope identifies one row |

**Cost & tradeoffs.** The proposed pipeline-side scope filter operates at the differ stage — load + dump still process the full adapter unless the integration also implements a source-side scoped load. Even without source-side optimization, the diff and sync phases drop from "all rows" to "subtree only," typically at least an order of magnitude.

For per-integration source-side scoped loads (load only the subtree from the upstream API), each integration would need its own `adapter.load(scope=...)`. Not built generically.

**How to wire it. (today)** Use whatever sync filter your integration supports (most integrations have a `SSOT<Name>Config` model with filter fields) to narrow the source-side load. **(proposed)**

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

For the proposed contracts and per-integration expanders, see the [Scope reference][ref-scope].

[ref-scope]: performance_validation_reference.md#scope-reference

---

### 11. Concurrency

**What it controls.** Whether source and target adapters load sequentially or in parallel.

**Default behavior. (today)** Parallel by default since SSoT 4.0.0 — source and target adapters load concurrently in two threads.

**When you'd dial it.** Disable when adapter code isn't thread-safe, or when you need adapters loaded in a specific order for debugging.

**Alternatives. (today)** Parallel (default) or sequential.

**Cost & tradeoffs.** Concurrent threads increase peak memory (both adapters in flight at once). Doesn't help when one phase dominates the other (sequential is already as fast as the slower phase).

**How to wire it. (today)** Set `parallel_loading=False` on the Job or pass `parallel_loading: false` at runtime. PR #1194 also surfaces this as `SSoTFlags.PARALLEL_LOADING` for consistency with other flags, but the underlying mechanism is unchanged.

---

### 12. Dry-run

**What it controls.** Whether the sync writes or just computes the diff.

**Default behavior. (today)** Dry-run is on by default in the Job UI (per `DryRunVar` default). Engineers should explicitly turn it off to commit writes.

**When you'd dial it.** Always on for the first run when wiring up a new sync. Off for production runs.

**Alternatives. (today)** On / off (the `DryRunVar`).

**Cost & tradeoffs.** Dry-run runs the load + diff phases; skips the write phase. Same cost as a full sync minus the writes. Useful for preview, capacity planning, and CI smoke tests.

**How to wire it. (today)** `dryrun=True` on the Job.

---

### 13. Memory profiling

**What it controls.** Whether `tracemalloc` records peak memory per phase and stores it on the `Sync` record.

**Default behavior. (today)** Off. Memory tracking has measurable overhead.

**When you'd dial it.** Diagnosing OOM symptoms or budgeting a sync against a memory ceiling.

**Alternatives. (today)** On / off.

**How to wire it. (today)** Tick the "Memory Profiling" checkbox at job execution. PR #1194 also surfaces this as `SSoTFlags.MEMORY_PROFILING` for consistency; behavior is unchanged.

---

### 14. External triggering

**What it controls.** What can start a sync — Job UI, scheduled task, HTTP API, webhook receiver.

**Default behavior. (today)** Job UI (manual) and the scheduler (cron-style recurring jobs) — both inherited from Nautobot core.

**When you'd dial it.** When external systems should drive resyncs:

* External SoT pushes a change → fire a scoped resync within seconds
* Operator dashboard "Resync this row" button → fire a scoped resync
* Pipeline orchestrator (Argo, Airflow, etc.) → drive Nautobot syncs as part of a larger workflow

**Alternatives.**

| Trigger | Status | Use case |
|---|---|---|
| **Job UI** (default) | **(today)** | Manual operator-initiated runs |
| **Scheduled** (Nautobot core) | **(today)** | Cron-style recurring syncs |
| **Job API** (`POST /api/extras/jobs/.../run/`) | **(today)** | Trigger any Nautobot job via the REST API; payload may include job vars |
| **Scoped sync API** (`POST /api/plugins/ssot/sync/scoped/`) | **(proposed)** | External systems trigger targeted resyncs with a `SyncScope` |
| **Per-integration webhook receiver** | **(proposed pattern)** | Each integration ships its own authenticated receiver that translates the source's notification format into a `SyncScope` and calls the API |

**Cost & tradeoffs.** Webhook receivers are per-integration because every source has a different payload format and auth scheme. The proposed framework provides the scope + pipeline + API; integrations would provide the authenticated receiver + payload translator.

**Coalescing high-volume webhooks (proposed).** A real-world risk: Infoblox runs a batch update on 5,000 prefixes; webhook fires 5,000 times in 30 seconds. Two patterns the framework should provide (TODO):

* **Debounce** — same scope key arriving multiple times schedules one task and reschedules on each new arrival; runs after the burst settles.
* **Batch** — collect distinct scope keys for N seconds, emit ONE scoped sync with a multi-root scope.

For now, integrations should debounce in their own Celery tasks.

**How to wire it. (today)** Use the standard Nautobot Job API to trigger a sync; pass any sync filter values as job vars. **(proposed)** See the [API reference][ref-api] for the scoped-sync endpoint contract and the [Per-integration recipe](#per-integration-recipe) below for webhook receiver scaffolding.

[ref-api]: performance_validation_reference.md#api-endpoint

---

## Part 3 — Composing it

!!! warning "These numbers measure PR #1194's prototype, not develop"
    The matrix below is a pivot of TOTAL pipeline seconds at medium scale (8,143 Infoblox objects) on a development container, executing the prototype in PR #1194. They are illustrative of the relative ordering of tradeoffs, **not** a promise of universal SSoT speedups. Absolute numbers will vary by integration, dataset shape, and infrastructure. None of the `STREAM_*` / `BULK_WRITES` / `REFIRE_POST_SAVE` modes are available on `develop` today.

### Pre-mixed presets (prototype only)

> **Which row reflects "production today"?** A real SSoT job runs inside a `JobChangeContext` — signals fire normally, the changelog handler creates `ObjectChange` rows per save, and `web_request_context` cleanup fires webhooks/jobhooks/events. The `validated_save` row below captures this — it's the cost shape today's deployments actually pay. The `validated_save_no_cl` row runs the same `validated_save()` calls outside a change context (no `web_request_context`), so the changelog signal handler short-circuits and no OC rows are written. Useful as a lower-bound reference, **not** what production runs.

The "audit chain" column tracks whether each mode produces ObjectChange rows and fires webhooks / jobhooks / events.

| Preset | medium total | speedup vs prod | audit chain |
|---|---:|---:|---|
| **`validated_save`** ← **PRODUCTION today** | **163.31 s** | **1.00 ×** | **FULL** — per-row OC + webhooks/jobhooks/events |
| `validated_save_no_cl` (no change context — reference only) | 40.95 s | 3.99 × | none — signal handler short-circuits |
| `save` (no clean, no change context) | 29.31 s | 5.57 × | none |
| `save_immediate_cl` (production minus clean) | 132.32 s | 1.23 × | full (no clean) |
| `save_deferred_cl` | 77.63 s | 2.10 × | full (no clean), batched OC |
| `bulk_b250` | 4.91 s | 33.28 × | none |
| `bulk_b1000` (b=1000) | 5.04 s | 32.38 × | none |
| `bulk_b250_audit` (`bulk_create` + `REFIRE_POST_SAVE` + deferred CL) | 4.85 s | 33.67 × | **FULL** — same audit as production, no streaming |
| `stream_tier1` (`STREAMING`) | 88.28 s | 1.85 × | **FULL** — deferred CL |
| `stream_tier1_5` (`STREAMING \| BULK_WRITES \| VALIDATE_SOURCE_SHAPE \| VALIDATE_ON_DUMP`) | 1.83 s | 89.27 × | none (validation only) |
| `stream_tier1_7` (`STREAM_TIER1_5 \| VALIDATE_RELATIONS`) | 2.04 s | 79.93 × | none (validation only) |
| `stream_tier2_audit` (`STREAMING \| BULK_WRITES \| REFIRE_POST_SAVE` + `deferred_change_logging`) | 1.50 s | 108.98 × | **FULL** — bulk write + REFIRE + deferred OC + webhook fan-out |
| `stream_tier2` (`STREAMING \| BULK_WRITES`, SQLite store) | 1.28 s | 127.93 × | none |
| `stream_tier2_pydict` (PyDict store — benchmark instrument) | 1.23 s | 132.80 × | none — PyDict has no `.conn` |

### Selection guide

When deciding which preset to reach for, the principal question is which guarantees you're willing to give up. The matrix below maps "top concern" to a starting point on the prototype:

| If your top concern is… | Recommended preset | Notes |
|---|---|---|
| Operating like today, just with bigger inputs | `NONE` (defaults) | no behavior change |
| Maximum speed *with* the audit chain (no streaming required) | `bulk_b250_audit` | restores full audit at much higher throughput in the benchmark |
| Maximum speed, no audit needed | `STREAM_TIER2` | fastest measured |
| Speed + concern about garbage source data | `STREAM_TIER1_5` (+ `Strict<Adapter>`) | catches malformed input; modest overhead vs. `STREAM_TIER2` |
| Speed + relational validation (IP-in-prefix etc.) | `STREAM_TIER1_7` | adds the prototype's IP-in-prefix Phase B validator |
| OOM on large initial syncs | `STREAM_TIER2` or `STREAM_TIER1_5` | streaming caps memory |
| Multi-tenant / shared customer infra (full audit, accept the speed hit) | `STREAM_TIER1` | preserves changelog for compliance |
| Targeted resync from external trigger | `STREAM_TIER2` + `SyncScope(...)` | scope filter restricts to the subtree |

### What `deferred_change_logging` actually buys you

The `save` / `save_immediate_cl` / `save_deferred_cl` triplet decomposes the changelog cost. At the prototype's medium scale, per-row times:

| operation | per-row cost |
|---|---:|
| `save()` round-trip | **3.0 ms** |
| `+` `full_clean()` (production has this; benchmark `save_*_cl` modes do not) | **+1.7 ms** |
| `+` per-row `to_objectchange()` serialization | **+6.3 ms** (paid in both immediate and deferred) |
| `+` per-row OC INSERT (immediate mode) | **+7.4 ms** |
| `+` batched OC INSERT (deferred mode) | **+0.0 ms** (amortized into one bulk_create) |

Production = save + clean + serialize + INSERT ≈ **18.4 ms/row**, ~150 s at medium scale. `deferred_change_logging`'s actual contribution is the INSERT amortization — about **7 ms saved per row, ~58 s on the medium benchmark**. Serialization cost is unchanged.

That's a 43% speedup over the per-save changelog default — useful when:

* you NEED changelog (audit, webhooks, jobhooks, per-object signals), AND
* you CAN'T switch to bulk writes

If you don't need changelog, bulk writes (the proposed Tier 2) are the better operating point — 1.5 s vs 78 s on the benchmark.

### Deferred-X: SSoTFlags + contexts compose (proposed)

The proposed flags control **whether the side-effect signals fire at all** — contexts then control **how the side-effects get batched once they fire**. Practical recipes:

| Goal | Flags | Contexts |
|---|---|---|
| Maximum speed, no side-effects | `STREAM_TIER2` | none |
| Speed + Nautobot core post_save handlers (per-row replay) | `STREAM_TIER2 \| REFIRE_POST_SAVE` | none |
| Speed + batched Cable propagation specifically | `STREAM_TIER2 \| BULK_SIGNAL` | `deferred_domainlogic_cable()` |
| Speed + audit + webhooks/jobhooks/events | `STREAM_TIER2 \| REFIRE_POST_SAVE` | `web_request_context()`, `deferred_change_logging_for_bulk_operation()` |
| Speed + audit + Cable propagation batched | `STREAM_TIER2 \| REFIRE_POST_SAVE \| BULK_SIGNAL` | all three above |
| Today's default (per-row, full audit) | none | `web_request_context()` (handled by Job framework) |

For the Cable case specifically — why per-row replay is sometimes the wrong shape — see the [Deferred-X reference][ref-deferred-x].

---

### Per-integration recipe

!!! note "Status: proposed framework"
    The framework primitives below (`BulkOperationsMixin`, `ValidatorRegistry`, `IPAMShapeValidationMixin`, the `to_orm_kwargs` resolver hook) live in [PR #1194](https://github.com/nautobot/nautobot-app-ssot/pull/1194)'s prototype. They are **not** in `develop`. The recipe is included here so the design is reviewable as a whole.

The proposed framework in `nautobot_ssot/utils/` is integration-agnostic. Each integration adds glue files that wire its DiffSync models to the framework. The recipe shape is the same regardless of integration. For a working reference inside the prototype, see Infoblox's implementation in `nautobot_ssot/integrations/infoblox/diffsync/` on the PR branch.

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

The mixin only validates fields the model actually has (`network`, `prefix`, `address`, `prefix_length`, `vid`, `dns_name`) — safe to apply to any IPAM-shaped DiffSync model. For non-IPAM integrations, write your own mixin following the same `@field_validator(..., check_fields=False)` pattern.

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

`to_orm_kwargs()` returning `None` for a model_type cleanly opts that type out of `clean_fields`-at-dump validation. The `exclude_fk_fields` list keeps `clean_fields()` from blowing up on unset FK fields (those are validated by DB constraints at INSERT, not Python).

#### Step 3 — What you DON'T need to write

The proposed framework would handle all of these — no per-integration code:

* SQLite store schema and connection management
* `dump_adapter()` walking `top_level` + `_children`
* Streaming differ (SQL set ops on `source_records` + `dest_records`)
* `BulkSyncer` orchestration (action replay, FK-ordered flush)
* Phase A / B / C validator dispatch
* Flag plumbing (`SSoTFlags.STREAMING`, `BULK_WRITES`, `VALIDATE_*`)
* `Sync.diff` summary-write workaround
* Job-level wiring (`DataSyncBaseJob.flags` MultiChoiceVar, the `sync_data()` branch on `STREAMING`)

#### Step 4 — Per-integration knowledge

* **FK ordering**: `_bulk_create_order` must list ORM classes parent-first; otherwise `bulk_create()` hits FK violations.
* **Adapter maps**: queueing requires updating `adapter.<thing>_map[key] = orm.pk` *before* the queued object is flushed, so children referencing the parent by PK can resolve it. UUID PKs are set at `OrmModel(...)` instantiation, so this is straightforward.
* **Post-flush hooks**: integrations that need extra bulk-write work after `flush_all()` (e.g., Infoblox bulk-inserts `extras_taggeditem` rows) define a `bulk_sync_complete()` method on the adapter; `BulkSyncer` calls it automatically.

#### Step 5 — Test the new integration

1. Run the bundled benchmark pattern for your integration:

    ```bash
    python scripts/benchmark_<myint>.py --stream-tier2 medium
    python scripts/benchmark_<myint>.py --stream-tier1-7 medium
    ```

2. Add to the matrix runner if you want it included in the cross-integration table.
3. Wire a smoke test like `scripts/test_phase_a_validators.py` to confirm your registered validators actually fire.

---

For mechanical contracts (the proposed `SSoTFlags` enum reference, validator registry interface, deferred-X context shape, scope API, full file manifest), see the [Performance & Validation Reference][ref] document.

[ref]: performance_validation_reference.md
