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
* **Part 2 — the axes** is one chapter per behavioral knob. Each chapter
  follows the same shape: *what it controls, default behavior, when you'd
  dial it, alternatives, cost & tradeoffs, how to wire it*. Skip to the
  axis you care about.
* **Part 3 — composing it** offers pre-mixed presets, the measured matrix,
  and a per-integration recipe for adding the menu to a new SSoT
  integration.

This document grows alongside the codebase. Each axis is added as the
feature that backs it lands.

### The benchmark substrate

Every claim in this document is measured. The bundled benchmark
(`scripts/benchmark_infoblox.py --matrix`) exercises every available
mode at three scales — tiny / small / medium (8,143 objects). All
numbers in this document are from medium scale.

The "audit chain" column in the measured matrix tracks whether each
mode produces ObjectChange rows and fires webhooks/jobhooks/events —
that distinction matters more than raw speed for many integrations.

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

Every yellow node above is a knob. The default path is the leftmost —
the KISS guarantee. The other branches exist because not every sync
needs the full default chain, and the framework lets you opt out of
pieces you've measured aren't worth the cost.

---

## Part 2 — The axes

### Change logging — `ObjectChange` rows

**What it controls.** Whether each create/update/delete writes an
`ObjectChange` row recording who changed what when.

**Default behavior.** Every `validated_save()` (or plain `save()`)
inside a `web_request_context` fires `post_save`, which the changelog
signal handler captures and INSERTs as one `ObjectChange` per row —
~7.4 ms/row INSERT plus ~6.3 ms/row of `to_objectchange()`
serialization at medium scale.

**When you'd dial it.** Two opposing pressures: you don't need the
audit (initial bulk load, throwaway migration) → turn it off; or you
need the audit but per-row INSERT cost is dominating → batch the
INSERTs.

**Alternatives.**

| Mode | Behavior | Cost |
|---|---|---|
| Per-row immediate (default) | One INSERT per save | ~7.4 ms/row INSERT + ~6.3 ms/row serialization |
| Deferred-batched | Capture during the block, flush in one bulk_create at end | ~6.3 ms/row serialization (INSERT amortized) |
| None | `bulk_create()` skips `post_save` so no `ObjectChange`s | 0 |

**How to wire it.**

```python
from nautobot.extras.context_managers import (
    deferred_change_logging_for_bulk_operation, web_request_context,
)

with web_request_context(user, context_detail="my-job"):
    with deferred_change_logging_for_bulk_operation():
        # saves / bulk_creates inside here are batched at end of block
        ...
```

### Webhooks

**What it controls.** Outbound HTTP notifications fired by Nautobot in
response to `ObjectChange` rows.

**Default behavior.** Webhooks dispatch at the end of a
`web_request_context` block, iterating the `ObjectChange` rows
produced and matching them against configured `Webhook` objects.

**When you'd dial it.** Almost always when running a bulk migration —
firing 8,000 webhooks for a single sync rarely matches what downstream
consumers expect. Driven by axis "Change logging": disable changelog
→ webhooks don't fire.

**Cost & tradeoffs.** Per-row dispatch by default. SSoT does not
currently provide a "batched webhook" primitive.

**How to wire it.** Driven by axis "Change logging".

### Job hooks

**What it controls.** `JobHook` objects firing in response to data
changes — same shape as webhooks but firing internal Jobs instead of
HTTP calls.

**Default behavior.** Driven by `ObjectChange` creation. Each matching
`JobHook` enqueues a Celery task at end of `web_request_context`.

**Alternatives.** Same shape as webhooks — driven by axis "Change
logging".

**How to wire it.** Driven by axis "Change logging".

### Events (Nautobot Event framework)

**What it controls.** Nautobot's pub/sub Event publication on data
changes.

**Default behavior.** Driven by `ObjectChange` creation. One event
published per `ObjectChange` at end of `web_request_context`.

**Alternatives.** Same as webhooks — driven by axis "Change logging".

**How to wire it.** Driven by axis "Change logging".

### Business-logic signals (post_save consumers)

**What it controls.** Nautobot core's `post_save` handlers — Cable
propagation, Rack location cascading, custom-field cache invalidation,
search-index updates, etc. Not gated on `web_request_context`; they
fire on every `save()`.

**Default behavior.** With per-row `validated_save()` or `save()`,
every `post_save` handler fires per row. With `bulk_create()`, **none
of them fire** — that's where the speed comes from, but it silently
loses every side-effect they were responsible for.

**When you'd dial it.** Whenever you choose `bulk_create`, you've
implicitly dialed this to "none." Decide whether that's acceptable for
the models you're touching.

**Alternatives.**

| Mode | Behavior | Activated by |
|---|---|---|
| Per-row Django `post_save` | Default — dispatch per row | Default |
| Refire after bulk | After each bulk batch, loop and re-fire `post_save` per instance | `refire_post_save=True` kwarg on `flush_creates` / `flush_updates` |
| Per-batch dispatch | One `bulk_post_create` / `bulk_post_update` / `bulk_post_delete` signal per FK stage with the full batch | `bulk_signal=True` kwarg |
| None | All post_save consumers skipped | `bulk_create` alone with no replay |

**Audit of what's at risk.** When `bulk_create` runs with no replay:

| Category | Examples | Consequence |
|---|---|---|
| Cable / connection propagation | `update_connected_endpoints` | Cable.connection_state never updates |
| Location cascading | `handle_rackgroup_location_change` | Child Racks / Devices keep old location |
| Cluster membership | `assign_virtualchassis_master` | VirtualChassis never picks a master |
| Cross-model validation (m2m) | `vrf_prefix_associated`, `vrf_device_associated` | Validation row consistency doesn't run |
| Cache invalidation | `invalidate_choices_cache`, `invalidate_relationship_models_cache` | Stale cached choices / metadata |

**IPAM models** (Namespace, Prefix, IPAddress, VLAN, VLANGroup) have
no direct `post_save` handlers in core — `bulk_create` alone is safe
for IPAM-only syncs. **DCIM models** (Cable, Rack, RackGroup,
VirtualChassis) DO have handlers that do real work — pair with
`refire_post_save=True`.

**`bulk_post_*` signals.** A new pair of signals emitted by
`BulkOperationsMixin.flush_*` when `bulk_signal=True`. Subscribers see
the batch:

```python
from django.dispatch import receiver
from nautobot_ssot.signals import bulk_post_create

@receiver(bulk_post_create, sender=IPAddress)
def invalidate_caches(sender, instances, **kwargs):
    cache.delete_many([f"ip:{i.pk}" for i in instances])  # one Redis op
```

### Atomic transactions

**What it controls.** The granularity of rollback. If part of the sync
fails, what gets rolled back?

**Default behavior.** Per-Job atomic block. The sync runs inside one
`transaction.atomic()`; if it raises, all writes roll back.

**Alternatives today.** SSoT does not currently expose a knob for
transaction scope; it inherits Nautobot's per-Job atomic behavior.
Bulk pipeline's per-batch flushes commit incrementally — if the sync
fails mid-stream, already-flushed batches stay committed unless the
outer transaction rolls them back.

**Cost & tradeoffs.** Wider transactions hold locks longer (concurrency
cost). Narrower transactions risk partial-commit on failure
(consistency cost). The current default tries to balance both.

### Bulk-write batching

**What it controls.** Whether each row is INSERTed individually
(`save()`) or in batches (`bulk_create()` / `bulk_update()`).

**Default behavior.** `validated_save()` per row.

**When you'd dial it.** When per-row INSERT round-trips dominate sync
time. At medium scale, switching from `validated_save` to `bulk_b250`
is roughly 30× faster all by itself.

**Alternatives.**

| Mode | Behavior | Cost |
|---|---|---|
| Per-row save (default) | One INSERT per row | N round-trips |
| `bulk_create` / `bulk_update` | One INSERT per batch (default 250) | ⌈N / batch_size⌉ round-trips |

**Composing with the audit chain.** `bulk_create` skips `post_save`,
which means no `ObjectChange` rows, no webhooks, no jobhooks, no
events. Restoring the chain on the bulk path uses three opt-in kwargs
on `BulkOperationsMixin.flush_*`:

| kwarg | what it does |
|---|---|
| `refire_post_save=True` | Re-fire `post_save` per instance after each bulk batch — restores Nautobot core handlers |
| `bulk_signal=True` | Fire `bulk_post_*` once per flush stage with the full batch |
| `bulk_clean=True` | Call hypothetical `Model.bulk_clean(instances)` (no-op until Nautobot core ships the API) |

Compose with Nautobot core's existing context managers for full audit:

```python
from nautobot.extras.context_managers import (
    deferred_change_logging_for_bulk_operation, web_request_context,
)
# BulkNautobotAdapter set with refire_post_save=True, bulk_signal=True
with web_request_context(user, context_detail="my-job"):
    with deferred_change_logging_for_bulk_operation():
        src.diff_to(dst)
        src.sync_to(dst)
```

The `bulk_b250_audit` benchmark mode demonstrates this composition:
~5 s at medium with the **same audit semantics as production** (~150 s)
— roughly 30× faster.

**Batch size.** Default 250.

### Dry-run

**What it controls.** Whether the sync writes or just computes the diff.

**Default behavior.** Dry-run is on by default in the Job UI.

**Alternatives.** On / off (the `DryRunVar`).

**How to wire it.** `dryrun=True` on the Job.

---

## Part 3 — Composing it

### Per-integration recipe (in progress)

The framework in `nautobot_ssot/utils/` is integration-agnostic. Each
integration adds glue files. Today Step 2 (bulk write adapter) is
documented.

#### Step 2 — Bulk write adapter

```python
from nautobot_ssot.utils.bulk import BulkOperationsMixin
# ...
class BulkNautobotMyIntAdapter(BulkOperationsMixin, NautobotMyIntAdapter):
    foo = BulkNautobotFoo
    bar = BulkNautobotBar
    _bulk_create_order = [OrmFoo, OrmBar]   # FK dependency order

    # Optional: opt into the audit chain side-effects on the legacy bulk pipeline
    refire_post_save: bool = False
    bulk_signal: bool = False
    bulk_clean: bool = False
```

**Per-integration knowledge.**

* **FK ordering**: `_bulk_create_order` must list ORM classes
  parent-first.
* **Adapter maps**: queueing requires updating
  `adapter.<thing>_map[key] = orm.pk` *before* the queued object is
  flushed.
* **Post-flush hooks**: `bulk_sync_complete()` for extra bulk-write
  work after `flush_all()`.

For a working reference see `BulkNautobotAdapter` in
`nautobot_ssot/integrations/infoblox/diffsync/adapters/nautobot_bulk.py`.
