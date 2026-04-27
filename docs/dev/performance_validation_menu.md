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
mode at three scales — tiny / small / medium (8,143 objects) — and
prints a TOTAL-time pivot table per scale. Re-run via:

```bash
./scripts/run_benchmark_matrix.sh
```

Inside the dev container, `scripts/_bench_env.sh` exports the env
variables (DB / Redis hosts, password, settings module) needed to run
the benchmark against the local instance. All numbers in this document
are from medium scale.

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

### Bulk-write batching

**What it controls.** Whether each row is INSERTed individually
(`save()`) or in batches (`bulk_create()` / `bulk_update()`).

**Default behavior.** `validated_save()` per row — one round-trip per
row.

**When you'd dial it.** When per-row INSERT round-trips dominate sync
time (typically true above a few hundred rows). The headline
measurement on the bundled benchmark: at medium scale (8,143 rows),
switching from `validated_save` to `bulk_b250` is roughly 30× faster
all by itself. This is the single largest write-path lever in the menu.

**Alternatives.**

| Mode | Behavior | Cost |
|---|---|---|
| **Per-row save (default)** | One INSERT per row | N round-trips |
| **`bulk_create` / `bulk_update`** | One INSERT per batch (batch size configurable, default 250) | ⌈N / batch_size⌉ round-trips |

**Cost & tradeoffs.** `bulk_create()` skips:

* `post_save` signals (covered by separate axes once they land)
* Per-row `clean()` (covered by validation axis once it lands)
* Per-row changelog (covered by changelog axis once it lands)

Each of those concerns gets its own axis later in this doc as the
relevant infrastructure ships. For now, `bulk_create()` alone is the
"raw speed, no audit chain" lever.

**Batch size.** Default 250. Larger batches reduce round-trip count
but increase memory footprint per batch. Empirically 250 wins at our
scale; higher (1000) gives no measurable improvement.

**How to wire it.** Subclass the integration's `NautobotAdapter` with
`BulkOperationsMixin`, override each model's `create()` / `update()`
to queue rather than save, and call `self.flush_all()` in
`sync_complete()`. See the per-integration recipe in Part 3.

### Dry-run

**What it controls.** Whether the sync writes or just computes the diff.

**Default behavior.** Dry-run is on by default in the Job UI (per
`DryRunVar` default). Engineers should explicitly turn it off to commit
writes.

**When you'd dial it.** Always on for the first run when wiring up a
new sync. Off for production runs.

**Alternatives.** On / off (the `DryRunVar`).

**Cost & tradeoffs.** Dry-run runs the load + diff phases and skips the
write phase. Same cost as a full sync minus the writes. Useful for
preview, capacity planning, and CI smoke tests.

**How to wire it.** `dryrun=True` on the Job — provided by the standard
`DataSyncBaseJob` base class.

---

## Part 3 — Composing it

### Per-integration recipe (in progress)

The framework in `nautobot_ssot/utils/` is integration-agnostic. Each
integration adds glue files that wire its DiffSync models to the
framework. Recipe steps land here as the relevant infrastructure
ships. Today only Step 2 (bulk write adapter) is documented.

#### Step 2 — Bulk write adapter

**File: `nautobot_ssot/integrations/<myint>/diffsync/adapters/nautobot_bulk.py`**

```python
from <orm.models> import OrmFoo, OrmBar
from nautobot_ssot.utils.bulk import BulkOperationsMixin
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
```

**Per-integration knowledge.**

* **FK ordering**: `_bulk_create_order` must list ORM classes
  parent-first; otherwise `bulk_create()` hits FK violations.
* **Adapter maps**: queueing requires updating
  `adapter.<thing>_map[key] = orm.pk` *before* the queued object is
  flushed. UUID PKs are set at `OrmModel(...)` instantiation, so this
  is straightforward.
* **Post-flush hooks**: integrations that need extra bulk-write work
  after `flush_all()` define a `bulk_sync_complete()` method on the
  adapter; later infrastructure will call it automatically.

For a working reference see Infoblox's
`BulkNautobotAdapter` in
`nautobot_ssot/integrations/infoblox/diffsync/adapters/nautobot_bulk.py`.
