# App Overview

This document provides an overview of the App including critical information and important considerations when applying it to your Nautobot environment.

This Nautobot app facilitates integration and data synchronization between various "source of truth" (SoT) systems, with Nautobot acting as a central clearinghouse for data - a Single Source of Truth, if you will.

!!! note
    Throughout this documentation, the terms "app" and "plugin" will be used interchangeably.

## Description

The Nautobot SSoT app builds atop the [DiffSync](https://github.com/networktocode/diffsync) Python library and Nautobot's Jobs feature. This enables the rapid development and integration of Jobs that can be run within Nautobot to pull data from other systems ("Data Sources") into Nautobot and/or push data from Nautobot into other systems ("Data Targets") as desired.

## Key Features

### Sync execution

* **Forward sync** ("Data Source" Jobs) pulls data from an external system into Nautobot.
* **Reverse sync** ("Data Target" Jobs) pushes data from Nautobot into an external system.
* **Dry run** mode computes the diff and skips writes — preview before commit.
* **Streaming pipeline** *(opt-in)* dumps both adapters into a temporary SQLite store and runs the diff via SQL set operations, capping memory usage and sidestepping the JSONField size limit on the persisted diff.
* **Bulk write mode** *(opt-in)* replays the diff via `bulk_create` / `bulk_update` for dramatically faster writes at the cost of per-object signals and changelog.
* **Parallel adapter loading** *(opt-in)* loads source and target concurrently when both are I/O-bound.

### Configuration and scoping

* **Per-integration configuration models** with full UI / API / filterset / permission stack (e.g. `SSOTInfobloxConfig`).
* **Sync filters** scope what the Job pulls (e.g. specific Infoblox network views, ServiceNow company groups).
* **Mapping configuration** translates source identifiers to Nautobot identifiers (e.g. network view → namespace).
* **Data mappings UI** shows source ⇄ target field correspondence on the Job page.
* **Configuration information UI** surfaces the effective non-secret runtime config alongside each Job.
* **Per-integration enable flags** (`NAUTOBOT_SSOT_ENABLE_<NAME>` env vars) make installed integrations opt-in.

### Safety and correctness

* **Atomic transactions** wrap writes for rollback safety.
* **Data validation menu** *(opt-in, layered)* — Pydantic source-shape validators, Django `clean_fields()` at dump time, plus a planned phased validator registry. See [Performance & Validation Menu](../dev/performance_validation_menu.md) for details.
* **Change logging** ranges from per-object signals (full audit) to deferred-batched to none, depending on the chosen write path.
* **Standard Django permissions** gate `Sync` and `SyncLogEntry` views.
* **Job approval workflows** (inherited from Nautobot core) gate prod-critical syncs.

### Observability

* **Dashboard UI** lists all registered Data Sources and Data Targets and shows synchronization history at a glance.
* **Sync history** records every run with source, target, dry-run flag, summary, and full diff.
* **Diff view** renders the calculated changes in the UI, before or after the sync runs.
* **Per-action log entries** (`SyncLogEntry`) capture every create/update/delete/no-change with action, status, message, and a generic FK back to the affected Nautobot object.
* **Per-phase timings** — source-load, target-load, diff, sync — are recorded as `DurationField`s on every `Sync` record.
* **Per-phase memory metrics** — final and peak memory for each phase — captured when memory profiling is enabled.
* **Memory profiling toggle** drives `tracemalloc` instrumentation on demand.
* **Job logs and `JobResult` linkage** — every `Sync` references its `JobResult`, so DiffSync's structlog output flows into the standard Nautobot Job UI.

### Data lineage

* **`MetadataType` integration** *(opt-in via `enable_metadata_for`)* stamps `last_synced_from_sor` and `system_of_record` on every touched Nautobot object so you can trace which sync owned which row.

### Extension points for developers

* **`DataSyncBaseJob`** base class with overridable `load_source_adapter`, `load_target_adapter`, `calculate_diff`, `execute_sync`, `lookup_object`, `data_mappings`, `config_information` hooks.
* **`NautobotAdapter` and `NautobotModel`** in `contrib/` provide a type-driven adapter that auto-loads from the ORM using `TypedDict`s and field annotations — minimal boilerplate for new integrations.
* **`CustomFieldAnnotation` and `CustomRelationshipAnnotation`** declare which custom fields and custom relationships participate in sync without per-field code.
* **Pre-built typed relationship payloads** (`TagDict`, `LocationDict`, `DeviceDict`, `InterfaceDict`, `PrefixDict`, `IPAddressDict`, `VLANDict`, `VirtualMachineDict`).
* **`BulkOperationsMixin`** — drop-in support for Tier 2 bulk writes on any integration's NautobotAdapter.
* **Per-integration signal registration** — each integration package may ship a `signals.py` and register its own pre/post-save handlers.

### Platform (15+ shipped integrations)

Infoblox, ServiceNow, Meraki, DNA Center, ACI, Arista CloudVision, Citrix ADM, Device42, IPFabric, Itential, LibreNMS, SolarWinds, Slurpit, vSphere, Bootstrap.

### Inherited from Nautobot core (commonly used with SSoT)

* **Job scheduler** — cron syncs via Nautobot's scheduled jobs.
* **Webhooks** fire on `ObjectChange` rows the sync produces (full per-object in Tier 1, none in Tier 2).
* **Job hooks** react to ObjectChanges with another Job.

## Audience (User Personas) - Who should use this App?

* Nautobot app developers looking to sync data from an outside source into Nautobot and/or vice-versa.

## Authors and Maintainers

* Glenn Matthew (@glennmatthews)
* Christian Adell (@chadell)
* Justin Drew (@jdrew82)
* Leo Kirchener (@Kircheneer)
