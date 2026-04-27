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

---

## Validation registry

Defined in `nautobot_ssot/utils/validator_registry.py`.

### Phase enum

```python
class Phase(str, Enum):
    A = "A"  # after both dumps, before any flush
    B = "B"  # between parent and child flushes (Tier 2 only)
    C = "C"  # after all flushes
```

### Phase semantics

```mermaid
flowchart TB
    subgraph PA["Phase A — after both dumps, before any flush<br/>context: source_records, dest_records, diff_results"]
        A1[Same-model uniqueness in scope]
        A2[Same-model topology]
        A3[Cross-model conditional]
        A4[Aggregate / cardinality]
    end

    subgraph PB["Phase B — between parent and child flushes<br/>context: DB &#43; remaining queues &#43; adapter maps"]
        B1[FK existence pre-check]
        B2[FK containment / fit — IP fits in prefix etc.]
    end

    subgraph PC["Phase C — after all flushes<br/>context: final DB"]
        C1[Post-hoc consistency audit]
    end

    Reg([Validator registry]) --> PA
    Reg --> PB
    Reg --> PC

    classDef phaseA fill:#eef2ff,stroke:#6366f1
    classDef phaseB fill:#ecfdf5,stroke:#10b981
    classDef phaseC fill:#fdf4ff,stroke:#a855f7
    class A1,A2,A3,A4 phaseA
    class B1,B2 phaseB
    class C1 phaseC
```

### `Severity` / `Issue` / `ValidatorContext` / `Validator`

```python
class Severity(str, Enum):
    WARN = "warn"
    ERROR = "error"
    STRICT = "strict"

@dataclass
class Issue:
    validator: str
    severity: Severity
    model_type: str
    unique_key: str
    message: str
    extra: dict | None = None

@dataclass
class ValidatorContext:
    store: DiffSyncStore
    dst_adapter: object
    pending_queues: dict | None
    # helpers: row(), scope(), queue(), aggregate()

class Validator:
    name: str
    phase: Phase
    category: int                              # 1..8
    severity: Severity = Severity.ERROR
    fires_before_flush_of: type | None = None  # Phase B only

    def run(self, ctx: ValidatorContext) -> list[Issue]: ...
```

### Registration

```python
class BulkNautobotMyIntAdapter(BulkOperationsMixin, NautobotMyIntAdapter):
    validator_registry = ValidatorRegistry([
        IPAddressContainmentValidator(),    # Phase A
        VlanVidUniqueValidator(),           # Phase A
        IPInPrefixValidator(),              # Phase B
    ])
```

The `BulkSyncer` reads the registry off the adapter and dispatches per
phase. Empty registry → zero overhead.

### Validator categories

Eight realistic subcategories of "validators with non-local context":

| Cat | Name | Needs to see | Phase | Examples |
|---|---|---|---|---|
| 1 | Referential existence | FK target | B | VLAN→VLANGroup |
| 2 | Referential containment / fit | FK target's content | B | IP fits in prefix |
| 3 | Same-model uniqueness in scope | all rows in scope | A | VID unique in vlangroup |
| 4 | Same-model topology | all rows of model | A | prefix tree, cable graph |
| 5 | Cross-model conditional | rows of A AND B | A | if active then primary_ip set |
| 6 | Aggregate / cardinality | all rows in scope | A | ≤ N VLANs per group |
| 7 | Mutual exclusion / exactly-one | all rows in scope | A | one primary_ip4 per Device |
| 8 | State-machine / transition | old + new for same row | A | status transition table |

### Shipped IPAM validators

`nautobot_ssot/utils/validators_ipam.py`:

| Validator | Phase | Category | Description |
|---|---|---|---|
| `IPInPrefixValidator` | B | 2 | Each queued IP fits in a valid prefix in its namespace's prefix tree |
| `IPAddressContainmentValidator` | A | 4 | IPs whose CIDR doesn't fit any prefix in their namespace |
| `VlanVidUniqueValidator` | A | 3 | Duplicate VIDs within a VLAN group |
