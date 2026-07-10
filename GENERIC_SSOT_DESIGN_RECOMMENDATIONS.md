# Generic SSoT — Strategic Design Recommendations

_Author: Architecture review on top of the current MVP_
_Last updated: 2026-05-19_

---

## TL;DR

You already have **the right backend models**. The work that remains is mostly **UX and intelligence**: collapse the user-facing experience into a single guided workflow, lean hard on Nautobot's own schema introspection to do the "heavy lifting", and let the user focus on the one thing only they can answer — _"which JSON key maps to which Nautobot field?"_

The biggest unlock isn't a new model or a new abstraction. It's flipping the workflow from **source-first** to **target-first** and putting smart defaults in front of the user at every step.

---

## What's Already Right (Don't Rewrite)

| Concern | Existing Approach | Verdict |
|---|---|---|
| External system contract | `SSOTEndpoint` ties to `ExternalIntegration` for auth + URL + pagination | ✅ Keep — exactly the right surface |
| Source extraction | JMESPath in `source_field` | ✅ Keep — powerful, well-known, handles nesting |
| Target framework | DiffSync + `NautobotAdapter` from contrib | ✅ Keep — battle-tested, gives you diffs/dry-run for free |
| FK auto-creation policy | `SSOTFKCreateRule` per (sync_config, content_type) | ✅ Keep — per-relationship "skip vs. create" is the right granularity |
| Value transformations | `SSOTValueMap` + transformation_type enum | ✅ Keep — reusable lookup tables are the right pattern |
| Cross-endpoint joins | `SSOTEndpointJoin` with source_key → target_key | ✅ Keep — needed for real-world data shapes |
| Dynamic DiffSync models | Built at runtime from `SSOTFieldMapping` rows, topo-sorted | ✅ Keep — clever and correct |
| Endpoint-level normalization | `normalize_config` on `SSOTEndpoint` | ✅ Keep — handles raw API quirks before mapping |

## What's Misaligned (Refine, Don't Rebuild)

| Pain point | Why it hurts | Recommended change |
|---|---|---|
| **Too many top-level CRUD views** | User has to navigate Endpoints, Sync Configs, Field Mappings, FK Rules, Joins, Value Maps, Discoveries, Data Samples as separate pages | Hide most behind a **single Sync Plan workflow**. Power users can still drill in. |
| **Source-first builder** | User stares at JSON keys and has to know where they go in Nautobot | **Target-first builder**: pick model(s) → see required + optional fields → fill them from source |
| **FK rules configured separately** | User builds mappings, then has to remember to set FK rules in a different page | Prompt for FK strategy **inline** the moment a user maps an `__` field |
| **Discovery vs. live sync are disconnected** | Two jobs, two models (`SSOTDataSample`, `GenericSSOTDataDiscovery`), unclear which to use | Single "preview" action on the endpoint that caches sample data on the endpoint itself |
| **`smart_mapping.py` exists but isn't wired into the builder** | Auto-suggest infrastructure is built but unused | Surface suggestions as the **default** state in the mapping builder; user accepts or overrides |
| **No starter templates** | Every integration starts from a blank page | Ship a library of importable "recipes" (ServiceNow, Slurpit, NetBox, etc.) as JSON |
| **No record-level dry-run preview** | User has to run the job, read the log, and infer | Show **"sample record → Nautobot object"** preview live in the builder |

---

## Recommended User Journey

### The 4-Step Sync Plan Wizard

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ 1. Connect   │ → │ 2. Discover  │ → │ 3. Map       │ → │ 4. Sync      │
├──────────────┤   ├──────────────┤   ├──────────────┤   ├──────────────┤
│ Integration  │   │ Add 1+       │   │ Pick target  │   │ Dry-run      │
│ + auth       │   │ endpoints,   │   │ model(s)     │   │ preview      │
│              │   │ test fetch,  │   │ Auto-suggest │   │              │
│ (or start    │   │ see sample   │   │ mappings     │   │ Live run     │
│ from a       │   │              │   │ Resolve FKs  │   │              │
│ template)    │   │              │   │ inline       │   │ Re-run /     │
│              │   │              │   │              │   │ schedule     │
└──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
```

Each step has **forward + backward navigation**, **live preview**, and a **save-as-draft** behavior so a user can leave the wizard and pick it back up.

### Per-Step Detail

#### Step 1 — Connect

- Pick or create an `ExternalIntegration` (existing Nautobot model)
- _Or_ start from a **Sync Plan Template** (ServiceNow CMDB → Devices, Slurpit → Devices+Interfaces, etc.)
- A template pre-fills steps 2 and 3; user can still tweak.

#### Step 2 — Discover

- Define one or more `SSOTEndpoint`s (form-driven, no JSON)
- **"Test fetch" button** runs a small sample and shows the response in a JSON viewer
- Sample data is cached on the endpoint row (replaces `SSOTDataSample`/`GenericSSOTDataDiscovery`)
- For child endpoints, the wizard explicitly walks through parent-key configuration

#### Step 3 — Map (the heart of the UX)

This is the big change. The current builder is laid out as "for each source field, pick a target". The recommended layout is **target-first**:

```
┌─ Step 3: Map fields to Nautobot ────────────────────────────────────────┐
│                                                                          │
│ Target Model: [ Device ▾ ]   (auto-pick from template, or user chooses)  │
│                                                                          │
│ ┌──────────────────────────┬──────────────────────────────────────────┐ │
│ │ Nautobot Field           │ Source                                   │ │
│ ├──────────────────────────┼──────────────────────────────────────────┤ │
│ │ ★ name      (required)   │ [hostname        ▾]  ✓ auto-suggested    │ │
│ │ ★ status    (required)   │ [status          ▾]  + value map: 1=Active│ │
│ │ ★ role      (required)   │ [device_role     ▾]  FK: ⓘ create if missing│
│ │ ★ device_type            │ [model           ▾]  FK: ⓘ skip if missing │ │
│ │ ★ location  (required)   │ [site.name       ▾]  FK: ⓘ lookup by name  │ │
│ │   serial                 │ [serial_number   ▾]                       │ │
│ │   primary_ip4            │ [mgmt_ip         ▾]  FK: ⓘ create + parent prefix│
│ │   _cf_servicenow_id      │ [sys_id          ▾]  (custom field)        │ │
│ │                          │ [+ add another field]                     │ │
│ └──────────────────────────┴──────────────────────────────────────────┘ │
│                                                                          │
│ Live preview (record #1 of 47):                                          │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │ Source:                       Target (Nautobot Device):              │ │
│ │ { "hostname": "rtr-1",        { name: "rtr-1",                       │ │
│ │   "status": 1,                  status: <Status: Active>,            │ │
│ │   "device_role": "router",      role: <Role: router> ← will create,  │ │
│ │   "model": "C9300",             device_type: <DeviceType: C9300>,    │ │
│ │   "site": { "name": "DC1" },    location: <Location: DC1>,           │ │
│ │   "mgmt_ip": "10.0.0.1",        primary_ip4: <IPAddress: 10.0.0.1/?>,│ │
│ │   "sys_id": "abc123" }          _cf_servicenow_id: "abc123" }        │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│ [+ Add another model to sync]   [← Back]   [Save draft]   [Next: Sync →] │
└──────────────────────────────────────────────────────────────────────────┘
```

Notice what's happening here:

1. **Required fields are surfaced first** (the star prefix). Nautobot's schema tells us which fields are mandatory — we don't make the user discover that.
2. **FK strategy is set inline** — clicking the ⓘ icon next to an FK opens a small popover with the choice (lookup / create / skip / static), which writes the `SSOTFKCreateRule`. The user doesn't navigate away.
3. **Value maps are inline** — the "+ value map" affordance opens a popup that creates/links an `SSOTValueMap`.
4. **The live preview** answers the question "what will my sync actually do?" — based on the cached sample data.
5. **Custom fields** are first-class — Nautobot tells us what custom fields exist on the target content type.

#### Step 4 — Sync

- Big "Dry run" button → shows the full DiffSync diff (creates / updates / deletes / no-changes) with per-record drilldown
- "Looks good?" → "Run live"
- After run: result summary with links to created objects and per-error detail
- "Re-run later" → option to schedule via Nautobot scheduled jobs

---

## What This Means for Backend Models

Most of the model surface stays the same. Net delta:

### Add
- `SSOTSyncPlan` (new wrapper — or just repurpose `SSOTSyncConfig`) with a `status` field: `draft` / `ready` / `archived` and a `template_origin` pointer
- Cached `last_sample_data` + `last_sample_at` columns on `SSOTEndpoint` (replaces `SSOTDataSample`)
- `SSOTSyncPlanTemplate` model + a `templates/` directory of canonical JSON recipes that ship with the app

### Remove / collapse
- `SSOTDataSample` → fold into `SSOTEndpoint.last_sample_data`
- `GenericSSOTDataDiscovery` → no longer needed once sampling is per-endpoint and live
- `SSOTSyncConfigEndpoint` through model → keep, but stop exposing it as its own CRUD page

### Keep
- `SSOTEndpoint`, `SSOTSyncConfig`, `SSOTFieldMapping`, `SSOTValueMap`, `SSOTFKCreateRule`, `SSOTEndpointJoin`

The model layer barely changes. **The win is in views and intelligence.**

---

## Intelligence Layer (the "heavy lifting")

This is what the user is really asking for. The system should know:

### 1. What Nautobot Models Need

A `NautobotModelIntrospector` utility that, given a `ContentType`, returns:

```python
{
    "required_fields": ["name", "status", "device_type", "role", "location"],
    "optional_fields": ["serial", "asset_tag", "platform", "tenant", ...],
    "custom_fields": [{"name": "servicenow_id", "type": "text"}, ...],
    "foreign_keys": {
        "status": {"model": "extras.Status", "lookup": "name"},
        "role": {"model": "extras.Role", "lookup": "name"},
        "location": {"model": "dcim.Location", "lookup": "name"},
        ...
    },
    "natural_keys": ["name"],
    "computed_fields": [...],
}
```

This drives the target-first builder.

### 2. Field Name Fuzzy Matching

`smart_mapping.py` already has the bones. Wire it into the builder:
- Pre-fill source-field dropdowns with the best fuzzy match
- Mark confidence: green ≥80%, yellow 50–79%, gray <50% (still pickable)
- Special-case patterns: `*_id` → consider as identifier, `ip_*` → consider as IP field, `status`/`state` → suggest value map

### 3. Value Map Auto-Generation

When the user maps a `status`-like field, the system:
- Scans the cached sample for distinct values
- Tries to match them to existing Nautobot Statuses for that content type
- Pre-fills a candidate `SSOTValueMap` (user accepts/edits)

### 4. FK Resolution Defaults

When a user maps any `<fk>__name` field, the wizard immediately prompts:

- **Lookup by name (default)** — find existing only; skip record if missing
- **Lookup or create** — create the related object with defaults if missing
- **Static value** — always use a single fixed related object
- **Skip if missing** — record gets skipped entirely

The popover writes/updates `SSOTFKCreateRule(sync_config, target_content_type)`.

### 5. Pre-flight Validation

Before letting the user run live (not even dry-run), the system checks:
- All required fields on the target model are mapped (or have static defaults)
- All FK relationships have a resolution strategy set
- Sample data has been fetched within the last N days (configurable)
- Identifier fields are present

Failing checks become inline warnings in the builder, not run-time errors.

---

## Template Library (the secret weapon)

A `templates/` directory of versioned JSON recipes. Each recipe captures:

```json
{
  "name": "ServiceNow CMDB → Nautobot Devices",
  "description": "Pulls cmdb_ci_server records and creates/updates Devices",
  "version": "1.0",
  "endpoints": [
    {
      "name": "servers",
      "api_path": "/api/now/table/cmdb_ci_server",
      "data_path": "result",
      "pagination_type": "offset",
      "pagination_config": {"limit_param": "sysparm_limit", "page_size": 100}
    }
  ],
  "field_mappings": [
    {"endpoint": "servers", "content_type": "dcim.device", "source": "name", "target": "name", "is_identifier": true},
    {"endpoint": "servers", "content_type": "dcim.device", "source": "sys_id", "target": "_cf_servicenow_id"},
    {"endpoint": "servers", "content_type": "dcim.device", "source": "operational_status", "target": "status__name",
     "transformation_type": "value_map", "value_map": "snow_status_to_nautobot"},
    ...
  ],
  "value_maps": [
    {"name": "snow_status_to_nautobot", "mappings": {"1": "Active", "2": "Maintenance", "6": "Decommissioning"}}
  ],
  "fk_rules": [
    {"target_content_type": "dcim.location", "on_missing": "create"},
    {"target_content_type": "extras.status", "on_missing": "skip_record"}
  ]
}
```

A user importing this recipe gets 90% of their work done. They just:
1. Point it at their ServiceNow integration
2. Adjust any names that differ (their custom field might be named differently)
3. Run

Ship 5-10 of these at launch (ServiceNow, NetBox, LibreNMS, Slurpit, Solarwinds CMDB, generic CSV-over-HTTP, etc.). They become the **gold path** for adoption.

---

## What I Wouldn't Do (Yet)

- **Bidirectional sync.** It's a 5x complexity multiplier. Ship import-only v1; add `DataTarget` later.
- **Custom Python expressions** in transformations. Sandboxing is a security minefield. Use Jinja templates as the "escape hatch" once it's needed.
- **GraphQL source support.** Different ergonomics; do REST well first.
- **Per-record write-back to source.** Punt to v2.
- **Conflict resolution UI.** DiffSync flags cover the common cases; build the UI later when users hit real conflicts.

---

## Concrete Next Steps (if you wanted to act on this)

In order of expected impact:

1. **Wire `smart_mapping.py` into `ModelCentricMappingBuilderView`** so suggestions appear as default values. Smallest change, biggest UX win.
2. **Add inline FK strategy popover** to the builder — let users set `SSOTFKCreateRule` without leaving the page.
3. **Add live preview panel** to the builder showing "sample source → projected Nautobot object".
4. **Cache sample data on the endpoint** and add a "Test fetch" button — collapse Discovery into the endpoint detail page.
5. **Build the wizard shell** that strings Steps 1–4 together. Each step is an existing view; the wizard is just a frame around them.
6. **Ship 3 sync plan templates** as a JSON library and add an "Import template" action.
7. **Add pre-flight validator** that blocks live runs until required fields and FK strategies are set.
8. Deprecate `SSOTDataSample` + `GenericSSOTDataDiscovery` once endpoint-level sampling is live.

Stop here for v1. Bidirectional sync, advanced transformations, scheduling, and conflict resolution all defer to later phases.

---

## Open Questions for the Team

1. **How opinionated should the wizard be?** Strict (forces order, hides advanced) vs. flexible (any step accessible, advanced options visible). Recommend: strict by default, "Advanced" toggle reveals the underlying CRUD pages.
2. **Where do sync plan templates live?** In-repo (ship with the app) vs. as Nautobot data (admin-loadable). Recommend both: bundled defaults + import/export to JSON.
3. **Should the live preview run transformations server-side or client-side?** Server-side is consistent with the real sync; client-side is snappier. Recommend server-side (one extra HTTP call is fine; correctness > snap).
4. **Custom field strategy** — auto-create Nautobot custom fields when a user maps `_cf_*` to a non-existent field? Recommend: detect and prompt, but don't auto-create silently.
