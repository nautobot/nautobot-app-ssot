# Generic SSoT — Architectural Options From First Principles

_Author: Architecture exploration_
_Date: 2026-05-19_

---

## Restating The Problem (without prejudice)

A Nautobot administrator wants to declare _"pull data from this external API and project it into these Nautobot models"_ without writing Python.

Properties that matter:

1. **The target schema is known and fixed** (Nautobot models). The system can introspect required fields, FK relationships, custom fields, natural keys.
2. **The source schema is variable and unknown** (any REST API). The user is the only one who knows the source's shape.
3. **Relationships are the hard part.** A Device needs a Location, Status, Role, DeviceType, and DeviceType needs a Manufacturer. The system should figure out what extra objects to fetch/create — the user shouldn't have to thread the needle.
4. **Configuration is iterative.** Real-world data is messy. Users will sample, map, dry-run, fix, sample again, dozens of times before going live.
5. **Configurations are shareable.** A "ServiceNow → Nautobot Devices" mapping is the same for every customer with ServiceNow. There should be a portable artifact you can hand someone.
6. **Sync needs to be observable.** When a Device shows up wrong, the user needs to trace it back to a source record.

That's the problem. Now let's consider approaches that aren't constrained by what already exists.

---

## Approach A — Configuration-as-Data (the current direction)

Everything is a Django model: Endpoints, SyncConfigs, FieldMappings, FKRules, ValueMaps, EndpointJoins. The user configures them through Django forms; runtime composes them into DiffSync models.

**Pros**

- Native Nautobot UX: every concept gets list/detail/edit pages for free
- Audit trail via Django change logging
- REST API generated automatically
- Filterable, taggable, custom-fieldable like any Nautobot object

**Cons**

- Model proliferation: 8-10 top-level entities the user has to learn
- Configuration is fragmented across many pages and forms
- Sharing a configuration means dumping/loading 8 tables in the right order
- Hard to version-control a sync plan
- The user-facing concept ("I want to sync ServiceNow devices") doesn't map to any single object

---

## Approach B — Configuration-as-Code (declarative YAML/JSON)

One model: `SyncPlan` with a JSON document inside it. The document fully describes the sync: sources, mappings, transformations, FK rules. The UI is a structured editor on top of the JSON.

```yaml
version: 1
name: ServiceNow CMDB → Nautobot Devices
external_integration: 7c2f...
sources:
  - id: servers
    api_path: /api/now/table/cmdb_ci_server
    data_path: result
    pagination: { type: offset, page_size: 100 }

emit:
  - from: servers
    to: dcim.device
    identifiers: { name: "{{ name }}" }
    fields:
      status:
        source: operational_status
        value_map: { "1": Active, "2": Maintenance, "6": Decommissioned }
      role:
        source: u_device_role
        fk: { on_missing: create }
      device_type:
        source: "model_id.display_value"
        fk:
          on_missing: create
          also_emit:
            to: dcim.devicetype
            identifiers: { model: "{{ model_id.display_value }}" }
            fields:
              manufacturer:
                source: "manufacturer.display_value"
                fk: { on_missing: create }
      location:
        source: "location.display_value"
        fk: { on_missing: skip_record }
      serial: { source: serial_number }
      _cf_servicenow_id: { source: sys_id }

  - from: servers
    to: ipam.ipaddress
    when: "ip_address != null"
    identifiers: { host: "{{ ip_address }}" }
    fields:
      parent: { fk: { on_missing: auto_parent_prefix } }
```

**Pros**

- One model, one document. The whole sync plan is a single artifact.
- Trivially exportable, importable, version-controllable, shareable, templateable
- Composable: one source record can emit multiple Nautobot objects (Device + DeviceType + IPAddress) in one block
- Per-field FK resolution (today's `SSOTFKCreateRule` is per-content-type — less flexible)
- The GUI is a renderer of the JSON, not the source of truth
- Power users can write/edit YAML directly; novice users get the wizard

**Cons**

- Need to invest in a robust JSON schema and validation layer
- No automatic CRUD UI for sub-elements (you build the editor yourself)
- Migrating existing configurations to a new schema means migrating documents, not just adding columns

---

## Approach C — Visual Pipeline Builder (DAG nodes)

Drag-and-drop boxes: Source → Transform → Join → Target. Like Dagster, Airflow UI, or Apache NiFi.

**Pros**

- Strong intuition for complex multi-step pipelines
- Visual lineage is built-in

**Cons**

- Massive engineering investment (canvas, drag-drop, port-snapping, undo/redo, layout algorithms)
- Overkill for the 80% case (one source → one or two models)
- Not how Nautobot users currently work — large adoption hill

**Verdict**: Skip. Solving for the wrong end of the complexity curve.

---

## Approach D — Use an Existing ETL Engine (Singer / dlt / Airbyte)

Instead of building, embed a standard ETL framework. Write a generic REST API tap and a Nautobot target.

**Pros**

- Decades of community work on connectors, scheduling, observability
- Standard formats (Singer spec, Airbyte spec) mean leveraging existing taps for ServiceNow, Salesforce, etc.

**Cons**

- These tools are schema-naive. They move data but don't understand Nautobot's required fields, FK relationships, custom fields, validation rules. The "heavy lifting" the user explicitly asked for evaporates.
- Singer/Airbyte connectors typically materialize data into a warehouse-style row-per-record table; Nautobot's data model is graph-shaped (FKs everywhere). Massive impedance mismatch.
- Operating a separate engine alongside Nautobot is more infrastructure to run

**Verdict**: Borrow patterns (the Singer "tap/target" mental model, the idea of catalog discovery), don't embed the engine.

---

## Approach E — Code SDK (Python primitives, no UI)

Provide a Python library: `Endpoint`, `Mapping`, `FKResolver`. Users write a small Python file per integration.

**Pros**

- Maximum flexibility
- Best fit for engineers
- Composable with the rest of Python (custom transformations, callouts, etc.)

**Cons**

- Violates the explicit "zero-code" requirement
- Doesn't solve the "non-developer admin" persona at all

**Verdict**: Could ship as a layer underneath the declarative format, but not as the primary UX.

---

## Recommendation: Approach B (declarative document) with a wizard UI

> **The sync plan is a JSON document. The UI is a renderer. The engine consumes the document. Templates are pre-baked documents.**

Why this wins:

1. **One mental model for the user**: "a sync plan". Not 8 separate Django models.
2. **The artifact is portable**. Export to YAML, version it, share it, import it into another Nautobot instance. Templates are just example documents.
3. **Power-user escape hatch built in**. Wizard-built today, YAML-edited tomorrow when the user outgrows the wizard.
4. **Composability is first-class**. One source record can emit a Device + DeviceType + Manufacturer + IPAddress in one block — the engine sorts dependencies. This is awkward in the current model-per-mapping approach.
5. **Schema-aware engine**. Because we control the engine end-to-end, we can do the heavy lifting (required fields, FK resolution, auto-create parents) that off-the-shelf ETL can't.
6. **Inverts the diff direction**. The runtime model (DiffSync) maps cleanly to "emit" blocks in the document, eliminating the dynamic-model-construction layer that exists today.

---

## What the System Layers Look Like

```
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 4: UI                                                         │
│   Wizard mode  •  YAML mode  •  Template library  •  Diff preview   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ reads/writes
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 3: Storage                                                    │
│   SyncPlan(name, integration, document JSON, status, last_run_at)   │
│   SyncRun(plan, started_at, results JSON, log_entries)              │
│   ValueMap (still useful as a reusable lookup table, optional)      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ executes
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 2: Execution Engine                                           │
│   Document parser  →  Source loader  →  Mapper  →  DiffSync runner  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ uses
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 1: Intelligence Services                                      │
│   NautobotSchemaIntrospector  •  FieldSuggester  •  FKResolver      │
│   ValueMapAutogen  •  PreflightValidator                            │
└─────────────────────────────────────────────────────────────────────┘
```

The same intelligence services power both the UI (auto-suggest in the wizard) and the engine (resolve FKs at runtime). One source of truth for "what does Nautobot need."

---

## Concrete Layer 3 Schema

```python
class SyncPlan(PrimaryModel):
    name = CharField(unique=True)
    description = TextField(blank=True)
    integration = FK(ExternalIntegration)  # auth + base URL
    document = JSONField()                  # the entire sync plan
    schema_version = PositiveIntegerField(default=1)
    enabled = BooleanField(default=True)
    last_sample_at = DateTimeField(null=True, blank=True)
    cached_sample = JSONField(default=dict) # { source_id: [records...] }
    template_origin = CharField(blank=True) # which template was used


class SyncRun(BaseModel):
    plan = FK(SyncPlan)
    started_at = DateTimeField(auto_now_add=True)
    finished_at = DateTimeField(null=True)
    result_summary = JSONField(default=dict)  # { creates, updates, deletes, skips, errors }
    full_log = TextField(blank=True)
    dry_run = BooleanField(default=False)


class ValueMap(PrimaryModel):       # optional, still useful as a reusable artifact
    name = CharField(unique=True)
    mappings = JSONField(default=dict)
    default_value = JSONField(null=True, blank=True)
```

That's three models total (plus the existing `ExternalIntegration` from Nautobot core). Down from ten in the current design.

---

## Concrete Document Schema (v1)

A `SyncPlan.document` is validated against a JSON schema. Top-level keys:

```yaml
version: 1                   # schema version (so we can evolve safely)
sources:                     # 1+ endpoint definitions
  - id: <string>             # local name, referenced by emit blocks
    api_path: <string>
    data_path: <jmespath>    # path into the response body
    pagination: { type, page_size, params: {...} }
    method: GET | POST
    headers: {}
    query_params: {}
    body_template: <jinja>   # for POST
    iterates: <source_id>    # optional — declares this is a child endpoint
    iterates_key: <jmespath> # optional — JMESPath on parent record
    normalize: [...]         # optional canonical-field definitions

joins:                       # optional cross-source joins
  - left: <source_id>
    left_key: <jmespath>
    right: <source_id>
    right_key: <jmespath>
    type: left | inner

emit:                        # the heart of the plan
  - from: <source_id>
    to: <app_label.model>    # e.g. dcim.device
    when: <jmespath>         # optional record filter
    identifiers:             # dict of Nautobot field → source expression
      <field>: <jmespath | jinja>
    fields:                  # dict of Nautobot field → field spec
      <field>:
        source: <jmespath>
        default: <literal>
        required: true|false
        value_map: <inline-dict> | <ValueMap-name>
        type_cast: int | float | bool | datetime
        fk:                  # only for FK fields
          on_missing: skip_record | skip_field | create | lookup_only
          lookup_field: name | display_name | …
          create_defaults: { … }
          also_emit:         # optional — full nested emit block for parent
            to: <app_label.model>
            identifiers: { … }
            fields: { … }

defaults:                    # optional plan-wide defaults
  on_missing_fk: skip_record # default FK strategy
  continue_on_record_error: true
```

This document is human-readable, version-controllable, schema-validated, and richer than the current model approach. Every "field mapping row" today maps cleanly to an entry under `fields`; every "FK rule" maps to an `fk` block inline with the field; "endpoint joins" become a top-level `joins` array.

---

## Why "emit" is the Right Primitive

In the current model, the relationship is _endpoint → mapping → content_type → field_. That makes it hard to express _"this one source record produces a Device AND a DeviceType AND a Manufacturer AND an IPAddress"_ — you have to scatter the relationship across several `SSOTFieldMapping` rows and rely on the engine to topo-sort.

With `emit`, the user (or wizard) declares each output object explicitly:

```yaml
emit:
  - from: servers
    to: dcim.device
    ...
  - from: servers          # same source, different target
    to: ipam.ipaddress
    when: "ip_address != null"
    ...
```

And `fk.also_emit` lets a single field declaration cascade implicitly:

```yaml
device_type:
  source: "model_id.display_value"
  fk:
    on_missing: create
    also_emit:
      to: dcim.devicetype
      fields:
        manufacturer: { source: "manufacturer.display_value", fk: { on_missing: create } }
```

You can read this top-to-bottom and understand what will happen in Nautobot. That's not true of the current design.

---

## The Wizard UI Maps Cleanly to the Document

| Wizard step | Document section |
|---|---|
| **1. Connect** | `name`, `description`, `integration` (top-level fields on the SyncPlan model) |
| **2. Discover** | `sources` (one card per endpoint) |
| **3. Map** | `emit` (one tab/section per emit block) |
| **4. Sync** | runtime execution, populates `SyncRun` |

A user sees forms, but every form maps to a JSON path. Behind the scenes the wizard is just constructing and editing the document. A "View YAML" toggle exposes the raw document for power users.

---

## Migration Path From The Current Design

This isn't a "throw it all away" recommendation. The existing work maps cleanly onto the new shape:

| Today | Tomorrow |
|---|---|
| `SSOTEndpoint` rows | items in `sources` |
| `SSOTSyncConfigEndpoint` | source `id` references in `emit.from` |
| `SSOTEndpointJoin` | items in `joins` |
| `SSOTFieldMapping` row | entries under `emit[…].fields` |
| `SSOTFKCreateRule` | `fk` block on each field (more granular) |
| `SSOTValueMap` | unchanged — referenced by name from `value_map:` |
| `SSOTSyncConfig` | the `SyncPlan` itself |
| `SSOTDataSample` / `GenericSSOTDataDiscovery` | `cached_sample` JSON on `SyncPlan` |

A migration script can construct documents from existing model rows. Existing users don't lose work.

---

## What I'd Demand From This Approach Before Committing

1. **A strict JSON schema** for the document, with versioning. Migrations between schema versions are explicit, not implicit.
2. **A YAML / JSON editor** in the UI (Monaco or CodeMirror) with schema-driven autocomplete, so the "code mode" is genuinely usable, not a fallback.
3. **A first-class template library** — at least 3 reference templates shipped with the app (ServiceNow, NetBox, Slurpit). Without these, the document approach feels heavyweight for new users.
4. **A schema-aware document generator** that, given a target content type, produces a starter `emit` block with all required fields pre-stubbed. This is what makes the wizard fast.
5. **Idempotent document parsing**. Loading a document, dumping it back to YAML, and reloading it must produce the same result every time. No magic side effects.

---

## What I'd _Not_ Do

- **Don't make the document Turing-complete.** No `if`/`else`/`for` in YAML. Jinja templates in string positions are fine; full control flow is not. Keep it declarative.
- **Don't conflate "sync plan" with "sync run".** They're different lifecycles. A plan is a config; a run is an execution event.
- **Don't put schedule definitions in the document.** Use Nautobot's existing scheduled jobs to invoke a plan. Keeps concerns separated.

---

## Tradeoffs Honestly Stated

| Dimension | Approach A (status quo) | Approach B (this proposal) |
|---|---|---|
| Familiarity for Nautobot devs | High (everything is a Django model) | Medium (JSON document is non-standard for Nautobot apps) |
| User-facing simplicity | Low (8+ concepts) | High (1 concept: "sync plan") |
| Portability of a configuration | Low (multi-table dump) | High (single YAML/JSON file) |
| Template-library viability | Medium (need fixtures or import jobs) | High (templates are documents) |
| Engineering investment to ship v1 | Medium (continue current path) | Medium-High (build schema + parser + editor) |
| Power-user ergonomics | Low (clicking through forms) | High (edit YAML directly) |
| Long-term maintenance | High (many models, many forms, many migrations) | Medium (one schema to evolve, one parser to maintain) |

The honest cost of this approach is **upfront investment in the document schema and editor**. The honest payoff is **a simpler mental model, a portable artifact, and a smaller long-term surface area**.

---

## Three Things I'd Want To Validate Before Committing

1. **Does the document approach handle 80% of real-world integrations?** Pick 3 messy real-world APIs (ServiceNow, a custom CMDB, an SNMP/REST gateway), prove the document schema captures them.
2. **Can existing Nautobot users grok YAML?** The persona is "Nautobot administrator who doesn't write Python." Some can read YAML, some can't. Validate the wizard is the primary entry point and YAML is the escape hatch, not vice versa.
3. **What's the migration story for the existing MVP?** Existing field mappings need to map cleanly to documents. Sketch the migration before committing.
