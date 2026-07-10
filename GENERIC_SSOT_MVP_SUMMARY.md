# Generic SSoT Integration — Current State & Plan

_Last updated: 2026-04-01_

---

## Goal

A zero-code ETL tool built into Nautobot. Non-developer administrators define REST API endpoints, run a discovery job to gather sample data, map that data to Nautobot models via a UI builder, and run a sync job — all without writing Python.

---

## User Workflow

```
1. Create SSOTEndpoint(s)         →  define API paths, auth, pagination
2. Run DataDiscovery Job          →  fetches sample data → GenericSSOTDataDiscovery
3. Create SSOTSyncConfig          →  link to discovery + mapping
4. Create SSOTMapping             →  container for field mappings
5. Build Field Mappings (UI)      →  ModelCentricMappingBuilderView
   └─ Configure FK rules          →  skip record vs. auto-create per related model
6. Run GenericSSOTDataSource Job  →  live sync to Nautobot
```

---

## Data Models (Current)

| Model | Purpose |
|---|---|
| `SSOTEndpoint` | Unified endpoint definition (used by both discovery and sync). Supports bulk and child (iterated) types. |
| `GenericSSOTDataDiscovery` | Stores the master dict from a discovery run: `{endpoint_name: [records]}` |
| `SSOTMapping` | Field mapping container — linked to a discovery; holds all `SSOTFieldMapping` records |
| `SSOTSyncConfig` | Sync operation config — links discovery + mapping + endpoints, controls direction/dry-run/delete |
| `SSOTSyncConfigEndpoint` | Through model for `SSOTSyncConfig` ↔ `SSOTEndpoint` M2M with ordering weight |
| `SSOTEndpointJoin` | Defines cross-endpoint joins (source_key → target_key, left/inner) for multi-endpoint syncs |
| `SSOTFieldMapping` | Maps one source JMESPath field → one Nautobot model field, with transformations |
| `SSOTValueMap` | Reusable lookup table: source value → Nautobot value |
| `SSOTFKCreateRule` | Per-(mapping, ContentType): skip record or auto-create when FK target not found |
| `SSOTDataSample` | Cached sample data per endpoint from last discovery run |

### Key Relationships
```
SSOTEndpoint ──────────────────────────────────┐
     │                                          │
     │ (through SSOTSyncConfigEndpoint)          │
     ▼                                          ▼
SSOTSyncConfig ──── ssot_mapping ──► SSOTMapping ──► SSOTFieldMapping(s)
     │                                    │               │
     └──── data_discovery ──►             │               └── nautobot_content_type
              GenericSSOTDataDiscovery     │               └── source_field (JMESPath)
                                          └──► SSOTFKCreateRule(s)
                                                    └── target_content_type
                                                    └── on_missing (skip/create)
```

---

## Field Mapping Data Flow (Runtime)

```
source record (JSON)
  → extract_field_value()        JMESPath extraction
  → is_required check            skip record if missing + required
  → default_value fallback       if raw_value is None
  → apply_transformation()       none / static / value_map / type_cast
  → coerce to str                all DiffSync fields are Optional[str]
  → DiffSync model instance
```

---

## Adapters

### GenericExternalAdapter
- Dynamically builds `DiffSyncModel` subclasses from `SSOTFieldMapping` records, grouped by Nautobot ContentType
- Three-phase `load()`:
  1. Fetch all endpoint data (bulk + child types, with pagination)
  2. Apply `SSOTEndpointJoin` cross-endpoint joins via `build_joined_dataset()`
  3. Build DiffSync objects; merges records from multiple endpoints sharing the same identifiers
- Topological dependency sort on `top_level` (Kahn's algorithm) based on `__` FK traversal fields

### GenericNautobotAdapter
- Extends `NautobotAdapter` (contrib)
- Dynamically configures models the same way as the external adapter
- `get_from_orm_cache()` override: checks `SSOTFKCreateRule` per (mapping, ContentType) to decide skip vs. `get_or_create` when a FK target is missing
- Auto-creates parent Prefix for IPAddress records
- Stub models (dependencies not directly mapped) get identifiers only — DiffSync won't try to update their attributes
- Skips duplicate objects gracefully rather than crashing

---

## Jobs

### GenericSSOTDataDiscoveryJob
- **Inputs:** ExternalIntegration, SSOTEndpoint(s) (multi-select), optional name, sample size
- **Output:** Creates/updates `GenericSSOTDataDiscovery` with `master_data` dict

### GenericSSOTDataSource (DataSource)
- **Input:** SSOTSyncConfig (filtered to enabled=True)
- Loads source via `GenericExternalAdapter`, target via `GenericNautobotAdapter`, runs DiffSync

---

## UI / Views

| View | Route | Purpose |
|---|---|---|
| `GenericSSOTDataDiscoveryUIViewSet` | `/generic-ssot/data-discoveries/` | CRUD for discoveries |
| `SSOTEndpointUIViewSet` | `/generic-ssot/endpoints/` | CRUD for endpoints |
| `SSOTMappingUIViewSet` | `/generic-ssot/mappings/` | CRUD for mappings |
| `SSOTSyncConfigUIViewSet` | `/generic-ssot/sync-configs/` | CRUD for sync configs |
| `SSOTSyncConfigEndpointUIViewSet` | `/generic-ssot/sync-config-endpoints/` | CRUD for config↔endpoint links |
| `SSOTFieldMappingUIViewSet` | `/generic-ssot/field-mappings/` | CRUD for field mappings |
| `SSOTEndpointJoinUIViewSet` | `/generic-ssot/endpoint-joins/` | CRUD for joins |
| `ModelCentricMappingBuilderView` | `/generic-ssot/mappings/<pk>/build-field-mappings/` | **Primary builder**: Nautobot fields → JMESPath + FK rules |
| `SyncConfigFieldMappingBuilderView` | `/generic-ssot/sync-configs/<pk>/build-field-mappings/` | Legacy source-first builder |

All detail views have `Dashboard → List → Object` breadcrumb navigation.

---

## Migration Chain

| Migration | What it does |
|---|---|
| 0018 | Initial models (now partially superseded) |
| 0019 | No-op dependency node |
| 0020 | Adds `GenericSSOTDataDiscovery`, links to `SSOTSyncConfig` |
| 0021 | Adds old `SSOTDiscoveryEndpoint` (removed in 0022) |
| 0022 | **Major rework**: introduces `SSOTEndpoint`, `SSOTMapping`, `SSOTSyncConfigEndpoint`; migrates data; removes old endpoint models |
| 0023 | Constraint + ordering cleanups |
| 0024 | Adds `SSOTMapping.synced_content_types`, `SSOTSyncConfig.delete_unmatched` |
| 0025 | Adds `SSOTEndpointJoin`, child endpoint fields, `selected_models`, dependency-aware field mapping unique constraint |
| 0026 | Adds `SSOTFKCreateRule` |

---

## Known Gaps / Next Steps

### Must-Have for Working Demo
- [ ] **End-to-end test**: run discovery → build mappings in UI → run sync, verify objects created in Nautobot
- [ ] **SSOTSyncConfig detail page**: needs clear links to "Build Mappings" and "Run Sync" in the right order (guided workflow)
- [ ] **Verify job wiring**: confirm `GenericSSOTDataSource.load_source_adapter()` correctly passes `SSOTMapping` from `sync_config.ssot_mapping` to `GenericExternalAdapter`

### UX / Polish
- [ ] **Navigation flow**: after creating a SSOTMapping, guide user to the builder (currently requires knowing to click "Build Field Mappings")
- [ ] **Builder: source field dropdown** populated from the linked discovery's `master_data` keys
- [ ] **Builder: FK rules panel** shows only FK fields relevant to mapped content types

### Before Merge
- [ ] **Squash migrations 0018–0026** into a single clean migration once all model changes are finalized

### Deferred (Phase 2+)
- Export / bidirectional sync
- Advanced transformations (regex, template, custom Python)
- Scheduled sync jobs
- Conflict resolution strategies
- Cursor/link-based pagination
