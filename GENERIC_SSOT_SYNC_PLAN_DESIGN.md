# Nautobot External Data Import — Design

_Status: Scope committed. One-way ETL from external APIs into Nautobot._
_Date: 2026-07-01_

> **Note on the filename.** This doc used to be called "Sync Plan Design" and lived under the Generic SSoT integration name. The scope has narrowed and the framing has shifted: **one-way import forever, never bidirectional.** The concepts and naming below reflect that. The filename can be updated (`NAUTOBOT_DATA_IMPORT_DESIGN.md` would fit) when it's convenient — the file path is the least important part.

---

## Decisions Locked In

1. **One Django model: `ImportPlan`** holds the entire configuration as a JSON document.
2. **UI is the primary interface.** Most Nautobot administrators aren't coders.
3. **YAML/JSON view exists** as a power-user escape hatch and for export/import, but is not the default surface.
4. The system **does the heavy lifting** around Nautobot's schema: required fields, FK resolution, parent-object auto-creation, validation.
5. **One-way import only, forever.** External API → Nautobot. Never Nautobot → external. No sync direction field. No export path. If someone later wants to push Nautobot data outward, that's a different feature.
6. **This is an ETL job, not an SSoT adapter.** Positioned in the UI as "External Data Import" — no DiffSync jargon, no adapter concepts, no "sync direction". DiffSync stays as an internal execution helper for dry-run only.

---

## What an Import Plan Is

An Import Plan is a single artifact that fully describes _"pull data from this external API and project it into these Nautobot models."_ A user creates one through a guided wizard; the system stores it as a versionable document.

```mermaid
graph TB
    subgraph ImportPlan["📥 Import Plan (one model row)"]
        Meta["📋 Metadata<br/>name · description · integration"]
        Sources["🌐 Sources<br/>1+ API endpoints"]
        Joins["🔗 Joins<br/>cross-source data merging"]
        Emits["🎯 Emit blocks<br/>source record → Nautobot object(s)"]
        Defaults["⚙️ Defaults<br/>error handling · FK fallback"]
    end

    Meta --> Sources
    Sources --> Joins
    Joins --> Emits
    Emits --> Defaults

    style ImportPlan fill:#1e293b,stroke:#38bdf8,stroke-width:2px,color:#e2e8f0
    style Meta fill:#0b1220,stroke:#475569,color:#e2e8f0
    style Sources fill:#0b1220,stroke:#475569,color:#e2e8f0
    style Joins fill:#0b1220,stroke:#475569,color:#e2e8f0
    style Emits fill:#0b1220,stroke:#475569,color:#e2e8f0
    style Defaults fill:#0b1220,stroke:#475569,color:#e2e8f0
```

---

## System Architecture

Four layers, each with a clean responsibility. **No dedicated history model** — Nautobot's `JobResult` already provides that.

```mermaid
graph TB
    subgraph L4["Layer 4 — UI"]
        Wizard["🧭 Wizard<br/>(default surface)"]
        YamlEd["📝 YAML editor<br/>(escape hatch)"]
        Templates["📚 Template library"]
        Preview["👁️ Live preview"]
    end

    subgraph L3["Layer 3 — Storage"]
        IP["ImportPlan<br/>document : JSONField"]
        VM["ValueMap<br/>reusable lookups"]
        JR["JobResult<br/>(Nautobot native — history)"]
    end

    subgraph L2["Layer 2 — Execution (a Nautobot Job)"]
        Parser["🔍 Document parser<br/>+ schema validator"]
        Loader["⬇️ Source loader<br/>(pagination, joins, normalization)"]
        Mapper["🔄 Mapper<br/>(emit blocks → target ops)"]
        Runner["🏃 Upsert runner<br/>(DiffSync used for dry-run)"]
    end

    subgraph L1["Layer 1 — Intelligence Services"]
        Introspect["🔎 SchemaIntrospector"]
        Suggest["💡 FieldSuggester"]
        FKRes["🧩 FKResolver"]
        Valid["✅ PreflightValidator"]
    end

    L4 -->|reads/writes| L3
    L3 -->|consumed by| L2
    L2 -->|uses| L1
    L2 -->|writes| JR
    L4 -.->|uses for suggestions| L1

    style L4 fill:#1e293b,stroke:#38bdf8,color:#e2e8f0
    style L3 fill:#1e293b,stroke:#22c55e,color:#e2e8f0
    style L2 fill:#1e293b,stroke:#f59e0b,color:#e2e8f0
    style L1 fill:#1e293b,stroke:#a78bfa,color:#e2e8f0
```

The same intelligence services power both the UI (autosuggest while building) and the Job (resolve FKs at runtime). One source of truth for "what does Nautobot need."

---

## Django Models (the entire storage layer)

**Two new models.** `JobResult` is Nautobot's, not ours.

```mermaid
erDiagram
    ExternalIntegration ||--o{ ImportPlan : "auth + base URL"
    ImportPlan }o--o{ ValueMap : "referenced by name in document"
    ImportPlan ||--o{ JobResult : "run history (via job_kwargs)"

    ImportPlan {
        uuid id PK
        string name UK
        string description
        uuid integration_id FK
        json document "the entire import plan"
        int schema_version
        bool enabled
        datetime last_sample_at
        json cached_sample "preview data per source id"
        string template_origin "e.g. servicenow-cmdb-v1"
        datetime created
        datetime last_updated
    }

    ValueMap {
        uuid id PK
        string name UK
        json mappings
        json default_value
        bool case_sensitive
    }

    JobResult {
        uuid id PK
        string status "pending/running/succeeded/failed"
        datetime date_created
        datetime date_done
        json job_kwargs "includes {import_plan_id: ...}"
        text log_entries
    }
```

Everything else (sources, joins, emit blocks, field mappings, FK rules) lives inside `ImportPlan.document`. The document is the source of truth; the model row is just the envelope. Every run of the plan produces a native `JobResult` — no separate history table.

---

## The Document Schema (v1)

The document validates against a strict JSON schema. Top-level shape:

```yaml
version: 1                       # schema version
sources:                         # 1+ endpoint definitions
  - id: <string>                 # local identifier, referenced by emit blocks
    api_path: <string>
    data_path: <jmespath>        # path into the response body
    method: GET | POST
    pagination:
      type: none | offset | page | cursor | link
      page_size: <int>
      params: { ... }
    headers: { ... }
    query_params: { ... }
    body_template: <jinja>       # for POST
    iterates: <source_id>        # optional: this is a child endpoint
    iterates_key: <jmespath>     # optional: extract param from parent record
    normalize: [ ... ]           # optional canonical-field defs (raw → clean)

joins:                           # optional cross-source joins
  - left: <source_id>
    left_key: <jmespath>
    right: <source_id>
    right_key: <jmespath>
    type: left | inner

emit:                            # source records → Nautobot objects
  - from: <source_id>
    to: <app_label.model>        # e.g. dcim.device
    when: <jmespath>             # optional record filter
    identifiers:                 # natural keys
      <nautobot_field>: <expr>
    fields:
      <nautobot_field>:
        source: <jmespath>
        default: <literal>
        required: true | false
        value_map: <inline_dict> | <ValueMap.name>
        type_cast: int | float | bool | datetime
        fk:                      # only for FK fields
          on_missing: skip_record | skip_field | create | lookup_only | static
          lookup_field: name | display_name | …
          create_defaults: { ... }
          static_value: <string>          # only when on_missing == static
          also_emit:                      # optional nested emit for parent
            to: <app_label.model>
            identifiers: { ... }
            fields: { ... }

defaults:                        # plan-wide fallbacks
  on_missing_fk: skip_record
  on_record_error: continue      # continue | abort
  delete_unmatched: false        # if true, remove Nautobot objects not seen in the import
```

Note the schema has no `direction` field, no `export` field, no `sync_direction`. Import Plans only import.

### How a Field Maps Visually

```mermaid
graph LR
    Src["🌐 Source record<br/>JSON from API"]
    JM["📍 JMESPath<br/>extract value"]
    Norm["🧹 Normalize<br/>(optional)"]
    Def["📌 Default<br/>(if null)"]
    VM["🔀 Value map<br/>or transform"]
    Cast["🎯 Type cast"]
    FK["🧩 FK resolve"]
    Out["📦 Nautobot field value"]

    Src --> JM --> Norm --> Def --> VM --> Cast --> FK --> Out

    style Src fill:#0b1220,stroke:#38bdf8,color:#e2e8f0
    style Out fill:#0b1220,stroke:#22c55e,color:#e2e8f0
    style JM fill:#1e293b,stroke:#475569,color:#e2e8f0
    style Norm fill:#1e293b,stroke:#475569,color:#e2e8f0
    style Def fill:#1e293b,stroke:#475569,color:#e2e8f0
    style VM fill:#1e293b,stroke:#475569,color:#e2e8f0
    style Cast fill:#1e293b,stroke:#475569,color:#e2e8f0
    style FK fill:#1e293b,stroke:#475569,color:#e2e8f0
```

Each step is optional. The user only sees pieces they configure; the engine assembles the pipeline.

---

## Runtime Execution Flow

What happens when a user clicks "Run import".

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Job as ImportJob (plain Nautobot Job)
    participant Engine as Execution Engine
    participant Schema as Schema Introspector
    participant API as External API
    participant Resolver as FK Resolver
    participant NB as Nautobot ORM
    participant JR as JobResult

    User->>Job: Run ImportPlan (live or dry-run)
    Job->>Engine: parse(document)
    Engine->>Schema: validate document against schema
    Engine->>Schema: for each emit.to, get required fields + FKs
    Schema-->>Engine: schema metadata

    loop For each source in sources
        Engine->>API: fetch (with pagination)
        API-->>Engine: records
        Engine->>Engine: apply normalize_config
    end

    Engine->>Engine: apply joins (merge cross-source data)

    loop For each emit block (ordered by FK deps)
        Engine->>Engine: filter records by `when`
        loop For each record
            Engine->>Engine: extract identifiers + fields
            Engine->>Resolver: resolve FK references
            Resolver->>NB: lookup or create related objects
            Resolver-->>Engine: resolved references
            alt live run
                Engine->>NB: update_or_create(identifiers, defaults)
            else dry-run
                Engine->>Engine: record projected change (no DB write)
            end
        end
    end

    Engine-->>Job: result summary (creates / updates / skips / errors)
    Job-->>JR: log entries + summary
    Job-->>User: results + per-record drilldown
```

**Dry-run implementation:** the engine runs the full pipeline but replaces the ORM `update_or_create` call with a "would create/update this" record. No DiffSync adapter dance required — dry-run is just "run the pipeline in report mode." Same code path, different terminal step.

---

## UI Surface

The user never has to see the YAML if they don't want to. Every document feature has a UI affordance.

### The Wizard Journey

```mermaid
journey
    title Building an Import Plan
    section Step 1 — Connect
      Pick External Integration: 5: User
      Or import a Template: 5: User
    section Step 2 — Discover
      Define source endpoint(s): 4: User
      Test fetch: 5: User, System
      Cache sample data: 5: System
      Preview records: 5: User
    section Step 3 — Map
      Pick target model: 5: User
      Required fields shown first: 5: System
      Auto-suggest field mappings: 5: System
      Resolve FK strategies inline: 4: User
      Add Value Maps inline: 4: User
      Live record preview: 5: User, System
    section Step 4 — Run
      Pre-flight validation: 5: System
      Dry-run with projected changes: 5: User, System
      Review changes: 5: User
      Run live: 5: User
      View JobResult: 5: User
```

### UI Affordances Map Cleanly to Document Features

| Document feature | UI affordance |
| --- | --- |
| `name`, `description`, `integration` | Step 1 form fields |
| `sources[].api_path`, `pagination`, etc. | Step 2 endpoint cards with a "Test fetch" button |
| `sources[].iterates` (child endpoint) | Step 2: "this endpoint runs per record of…" dropdown |
| `joins` | Step 2: "Combine data" panel (only visible if 2+ sources) |
| `emit[]` (multiple blocks) | Step 3: tab per target model (or "+ Add another model") |
| `emit[].identifiers` vs `fields` | Visual distinction in the mapping table (★ marker for identifiers) |
| `emit[].fields[].source` | Source field dropdown with autocomplete + JMESPath hint |
| `emit[].fields[].fk` | Inline popover triggered by an ⓘ next to FK fields |
| `emit[].fields[].fk.also_emit` | "Auto-create parent objects" toggle in the FK popover |
| `emit[].fields[].value_map` | "Add value map" modal that lists distinct sample values |
| `emit[].when` | "Only import records where…" filter at the top of the emit tab |
| `defaults` | Step 4 settings panel (with sensible defaults pre-set) |
| Full document | "View YAML" toggle (hidden by default; collapses everything to text) |

### Where YAML Hides

```mermaid
graph TB
    subgraph Default["💚 Default surface (90% of users)"]
        W["Wizard mode<br/>step-by-step forms"]
        V["Saved plans list view"]
        D["Plan detail view"]
        R["JobResult view (native Nautobot)"]
    end

    subgraph Power["⚡ Power-user surface (10% of users)"]
        Y["YAML editor toggle<br/>(CodeMirror + JSON Schema)"]
        E["Export plan as YAML"]
        I["Import plan from YAML"]
    end

    W -.->|"'View YAML' toggle"| Y
    D -.->|"'Export' button"| E
    V -.->|"'Import' button"| I

    style Default fill:#1e293b,stroke:#22c55e,color:#e2e8f0
    style Power fill:#1e293b,stroke:#a78bfa,color:#e2e8f0
```

The YAML editor is _never_ the default. It's a toggle/button on the wizard and detail pages, primarily for templates, debugging, and Git-backed configuration management.

---

## Intelligence Layer (the "heavy lifting")

These are the four utility services that make the system feel smart. They're shared between the UI (for autosuggest) and the Job (for runtime resolution).

### 1. SchemaIntrospector

Given a Nautobot ContentType, returns everything we need to know:

```python
{
  "required_fields": ["name", "status", "device_type", "role", "location"],
  "optional_fields": ["serial", "asset_tag", "platform", "tenant", ...],
  "custom_fields": [
    {"key": "servicenow_id", "type": "text", "label": "ServiceNow ID"},
    ...
  ],
  "foreign_keys": {
    "status":      {"model": "extras.Status",      "lookup": "name"},
    "role":        {"model": "extras.Role",        "lookup": "name"},
    "location":    {"model": "dcim.Location",      "lookup": "name"},
    "device_type": {"model": "dcim.DeviceType",    "lookup": "model",
                    "parents": ["manufacturer"]},
    "primary_ip4": {"model": "ipam.IPAddress",     "lookup": "host",
                    "parents": ["parent"]},
    ...
  },
  "natural_keys": ["name"],
}
```

The wizard uses this to render the field list "required first, optional next". The Job uses it to validate the document before run.

### 2. FieldSuggester

Given sample data + a target model, proposes field mappings using fuzzy match.

```mermaid
flowchart LR
    Sample["Sample record<br/>{hostname, status, model_name, site, ...}"]
    Target["Target model<br/>dcim.Device"]
    Schema["Schema introspector"]
    Suggest["Field suggester<br/>(fuzzy match + heuristics)"]
    Out["Suggested mappings<br/>hostname → name (98%)<br/>status → status (100%)<br/>model_name → device_type (82%)"]

    Sample --> Suggest
    Target --> Schema --> Suggest
    Suggest --> Out

    style Sample fill:#0b1220,stroke:#38bdf8,color:#e2e8f0
    style Out fill:#0b1220,stroke:#22c55e,color:#e2e8f0
    style Schema fill:#1e293b,stroke:#a78bfa,color:#e2e8f0
    style Suggest fill:#1e293b,stroke:#f59e0b,color:#e2e8f0
    style Target fill:#1e293b,stroke:#475569,color:#e2e8f0
```

### 3. FKResolver

Handles every FK strategy declared in the document:

```mermaid
flowchart TD
    Start([FK field needs resolution])
    Lookup{Lookup<br/>by attribute}
    Found{Found?}
    Strategy{Strategy?}

    Skip["⏭️ Skip record"]
    SkipField["⏭️ Skip just this field"]
    Static["📌 Use static value"]
    Create["✨ Create with defaults"]
    Parents{Parents<br/>declared?}
    EmitParent["📦 also_emit parent<br/>(recursive)"]
    Done([Return resolved reference])

    Start --> Strategy
    Strategy -->|static| Static --> Done
    Strategy -->|lookup_only / skip_record / create| Lookup
    Lookup --> Found
    Found -->|yes| Done
    Found -->|no| Strategy2{Which no-match<br/>behavior?}
    Strategy2 -->|skip_record| Skip
    Strategy2 -->|skip_field| SkipField
    Strategy2 -->|create| Parents
    Parents -->|yes| EmitParent --> Create
    Parents -->|no| Create
    Create --> Done
    Skip --> Done
    SkipField --> Done

    style Start fill:#0b1220,stroke:#38bdf8,color:#e2e8f0
    style Done fill:#0b1220,stroke:#22c55e,color:#e2e8f0
    style Create fill:#1e293b,stroke:#22c55e,color:#e2e8f0
    style Static fill:#1e293b,stroke:#f59e0b,color:#e2e8f0
    style Skip fill:#1e293b,stroke:#ef4444,color:#e2e8f0
    style SkipField fill:#1e293b,stroke:#f59e0b,color:#e2e8f0
    style EmitParent fill:#1e293b,stroke:#a78bfa,color:#e2e8f0
```

### 4. PreflightValidator

Runs before a user can hit "Run live". Inline warnings, not exceptions.

```mermaid
flowchart LR
    Doc[Import Plan document]
    V1[All required fields mapped?]
    V2[All FKs have a strategy?]
    V3[Sample data fresh<br/>< N days?]
    V4[Identifier fields present<br/>per emit block?]
    V5[Referenced ValueMaps exist?]
    V6[No circular FK deps?]

    Pass([✅ Ready to run])
    Fail([⚠️ Warnings shown inline<br/>in the builder])

    Doc --> V1 --> V2 --> V3 --> V4 --> V5 --> V6
    V6 -->|all pass| Pass
    V6 -->|any fail| Fail

    style Doc fill:#0b1220,stroke:#38bdf8,color:#e2e8f0
    style Pass fill:#1e293b,stroke:#22c55e,color:#e2e8f0
    style Fail fill:#1e293b,stroke:#f59e0b,color:#e2e8f0
```

---

## Template Library

Ship pre-built import plans for common integrations. Users import a template, point it at their integration, customize anything that differs, run.

```mermaid
graph LR
    subgraph Bundled["📚 Bundled templates<br/>(in-repo)"]
        T1["ServiceNow CMDB"]
        T2["NetBox import"]
        T3["Slurpit"]
        T4["LibreNMS"]
        T5["Generic CSV<br/>over HTTP"]
    end

    subgraph User["👤 User"]
        U[Admin]
    end

    subgraph Plan["📥 New Import Plan"]
        P[Pre-filled document<br/>+ user's integration]
    end

    T1 -.->|import| P
    T2 -.->|import| P
    T3 -.->|import| P
    U -->|"'Import template'<br/>in wizard Step 1"| Bundled
    U -->|customize + run| P

    style Bundled fill:#1e293b,stroke:#22c55e,color:#e2e8f0
    style Plan fill:#1e293b,stroke:#38bdf8,color:#e2e8f0
    style User fill:#0b1220,stroke:#a78bfa,color:#e2e8f0
```

Templates live as JSON files under `nautobot_ssot/integrations/generic_ssot/templates/` (folder rename can follow later — path is not user-visible). The "Import Template" button in Step 1 lists them.

---

## The Import Job

A single Nautobot Job class powers all Import Plans:

```python
class RunImportPlan(Job):
    """Execute an Import Plan against Nautobot."""

    class Meta:
        name = "Run Import Plan"

    import_plan = ObjectVar(model=ImportPlan, queryset=ImportPlan.objects.filter(enabled=True))
    dry_run = BooleanVar(default=True)

    def run(self, import_plan, dry_run):
        engine = ImportEngine(import_plan.document, job_logger=self.logger)
        summary = engine.execute(dry_run=dry_run)
        self.create_file("import_report.json", json.dumps(summary))
        return summary
```

That's the entire Job surface. Every run creates a `JobResult` — Nautobot's native history mechanism. No custom `SyncRun` model, no history table to maintain, no separate dashboard.

**Scheduling** is Nautobot's existing scheduled-job mechanism. You schedule this Job with `{"import_plan": <uuid>}` as its kwargs and Nautobot's scheduler fires it. No new scheduling concept.

---

## Implementation Phases

Three phases, each delivering value independently.

```mermaid
gantt
    title Implementation Roadmap
    dateFormat YYYY-MM-DD
    axisFormat %b

    section Phase 1 — Foundation
    Document JSON schema + validation : p1a, 2026-07-01, 14d
    ImportPlan + ValueMap models + migration : p1b, after p1a, 5d
    Engine (parser, loader, mapper, upsert runner) : p1c, after p1b, 21d
    SchemaIntrospector service : p1d, after p1a, 7d
    FKResolver service : p1e, after p1d, 14d
    RunImportPlan Job + basic detail view + YAML editor : p1f, after p1c, 14d

    section Phase 2 — Wizard UI
    Wizard shell (4 steps + state) : p2a, after p1f, 14d
    Step 1 — Connect : p2b, after p2a, 7d
    Step 2 — Discover + sample cache : p2c, after p2b, 14d
    Step 3 — Map (target-first builder) : p2d, after p2c, 21d
    FieldSuggester wired into Step 3 : p2e, after p2d, 7d
    Inline FK strategy popover : p2f, after p2d, 14d
    Live preview pane : p2g, after p2d, 14d
    Step 4 — Dry-run + live run : p2h, after p2g, 14d

    section Phase 3 — Polish
    Template library (3 starter templates) : p3a, after p2h, 14d
    PreflightValidator + inline warnings : p3b, after p2h, 7d
    Export / Import YAML actions : p3c, after p2h, 7d
    Documentation + tutorials : p3e, after p3c, 14d
```

### Phase 1 — Foundation (engine + storage, no wizard yet)

- Define and version the document JSON schema
- Build `ImportPlan` and `ValueMap` models (no `SyncRun` — use `JobResult`)
- Build the execution engine (parser → loader → mapper → upsert runner)
- Build `SchemaIntrospector` and `FKResolver` services
- Ship the `RunImportPlan` Job and a minimal detail view with a YAML editor — power users can run import plans without the wizard

**End-of-phase test**: a developer writes a YAML document by hand, saves it as an ImportPlan, runs the Job, sees Nautobot objects created and a `JobResult` populated.

### Phase 2 — Wizard UI (the main UX)

- Build the 4-step wizard
- Wire `FieldSuggester` into the Map step
- Build the inline FK strategy popover
- Build the live record preview pane
- Build the dry-run projected-changes viewer

**End-of-phase test**: a non-developer admin creates a working import from scratch using only the wizard, no YAML.

### Phase 3 — Polish

- Ship 3 starter templates (ServiceNow CMDB, NetBox, generic CSV-over-HTTP)
- Build the preflight validator with inline warnings
- Build YAML export / import for the GitOps workflow
- Document the system

**End-of-phase test**: new users start from a template and reach a working import in <15 minutes.

---

## Clean Slate — Existing MVP Models Are Discarded

The previous MVP iteration was never put into production use, so there's no migration burden. **Phase 1 starts from an empty slate**: drop the existing tables (`SSOTEndpoint`, `SSOTSyncConfig`, `SSOTFieldMapping`, `SSOTFKCreateRule`, `SSOTEndpointJoin`, `SSOTDataSample`, `GenericSSOTDataDiscovery`, and their through-models) and create the two new tables fresh.

```mermaid
graph LR
    subgraph Old["🗑 Old MVP (drop)"]
        T1[SSOTEndpoint]
        T2[SSOTSyncConfig]
        T3[SSOTSyncConfigEndpoint]
        T4[SSOTFieldMapping]
        T5[SSOTFKCreateRule]
        T6[SSOTEndpointJoin]
        T7[SSOTDataSample]
        T8[GenericSSOTDataDiscovery]
    end

    subgraph New["✨ New (build)"]
        N1[ImportPlan]
        N2[ValueMap]
        N3["(JobResult — Nautobot native)"]
    end

    Old -->|"single migration:<br/>delete all"| New

    style Old fill:#1e293b,stroke:#ef4444,color:#e2e8f0
    style New fill:#1e293b,stroke:#22c55e,color:#e2e8f0
```

A single Django migration drops the old tables and creates the new ones. No data migration, no compatibility shims.

---

## What The Reframing Eliminated

Committing to "one-way import forever" — and adopting the ETL positioning — deletes the following complexity from the design:

| Removed | Because |
| --- | --- |
| `sync_direction` field on ImportPlan | Only one direction exists |
| Export path in the execution engine | Not building it |
| `DataSource` / `DataTarget` job hierarchy | Plain `Job` is sufficient |
| `SyncRun` model | `JobResult` covers history |
| Bidirectional conflict-resolution UI | Not applicable |
| "Which system is source of truth?" framing | Nautobot is target; external is source; done |
| The word "sync" throughout the UX | Replaced with "import" — clearer, honest |
| DiffSync adapter classes as user-facing concepts | Engine uses DiffSync only for dry-run internally |

That's not superficial. Each of those was going to consume design time, code, and docs. All gone.

---

## Open Questions To Resolve Before Phase 1

1. **YAML editor library** — Monaco (heavy, full-featured) vs CodeMirror (lighter, simpler). Recommend CodeMirror 6 with JSON Schema validation extension.
2. **Document storage format** — store as JSON in the DB, render as YAML in the UI? Or store as YAML string? Recommend: JSON in DB (cleaner queries), YAML in UI (more readable).
3. **Schema versioning strategy** — how do we evolve the document schema without breaking saved plans? Recommend: explicit `version: N` field + migration functions per version bump.
4. **Where do templates live?** In-repo JSON files vs. database fixtures vs. external Git repo. Recommend: in-repo as JSON files with a Django management command to refresh them.
5. **Delete-unmatched semantics** — when `delete_unmatched: true`, do we only delete records that _were_ imported by this plan (tracked via a custom field), or any Nautobot record matching the target type? Recommend: track-imported-only. Nautobot might have manually-created objects the user does not want removed.
6. **Multi-tenancy** — can an ImportPlan be scoped to a Tenant? Recommend: yes, via a standard `tenant` FK on `ImportPlan` (Nautobot pattern).
7. **Folder/name renames** — the code currently lives at `nautobot_ssot/integrations/generic_ssot/`. Rename to something like `integrations/data_import/` to match the new naming? Not urgent; the path isn't user-visible. Can wait until Phase 3.

---

## A Concrete Example, End-to-End

To make the design tangible, here's what a real ServiceNow → Nautobot Devices Import Plan looks like.

### What the user does in the wizard

```mermaid
graph LR
    A["Step 1<br/>📡 Pick ServiceNow integration"]
    B["Step 2<br/>📥 Add endpoint<br/>/api/now/table/cmdb_ci_server<br/>(click Test fetch)"]
    C["Step 3<br/>🎯 Pick target: dcim.Device<br/>(8 of 10 fields auto-suggested<br/>2 FK popovers to confirm)"]
    D["Step 4<br/>🏃 Dry-run shows<br/>87 creates · 13 updates · 3 skips<br/>Click Run live"]

    A --> B --> C --> D

    style A fill:#1e293b,stroke:#38bdf8,color:#e2e8f0
    style B fill:#1e293b,stroke:#38bdf8,color:#e2e8f0
    style C fill:#1e293b,stroke:#38bdf8,color:#e2e8f0
    style D fill:#1e293b,stroke:#22c55e,color:#e2e8f0
```

### What's stored in the database

A single `ImportPlan` row with this document:

```yaml
version: 1
sources:
  - id: servers
    api_path: /api/now/table/cmdb_ci_server
    data_path: result
    method: GET
    pagination:
      type: offset
      page_size: 100
      params: { limit_param: sysparm_limit, offset_param: sysparm_offset }

emit:
  - from: servers
    to: dcim.device
    identifiers:
      name: "{{ name }}"
    fields:
      status:
        fk: { on_missing: static, static_value: Active }
      role:
        source: u_device_role
        fk: { on_missing: create }
      device_type:
        source: "model_id.display_value"
        fk:
          on_missing: create
          also_emit:
            to: dcim.devicetype
            identifiers:
              model: "{{ model_id.display_value }}"
            fields:
              manufacturer:
                source: "manufacturer.display_value"
                fk: { on_missing: create }
      location:
        source: "location.display_value"
        fk: { on_missing: skip_record }
      serial:        { source: serial_number }
      asset_tag:     { source: asset_tag }
      _cf_servicenow_id: { source: sys_id }

  - from: servers
    to: ipam.ipaddress
    when: "ip_address != null"
    identifiers:
      host: "{{ ip_address }}"
    fields:
      parent: { fk: { on_missing: auto_parent_prefix } }

defaults:
  on_missing_fk: skip_record
  on_record_error: continue
  delete_unmatched: false
```

The user never typed any of that. The wizard built it. But it's there if they want to export it, version it in Git, code-review it, or share it with a colleague.

That's the whole point.
