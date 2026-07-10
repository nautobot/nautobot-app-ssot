# Generic SSoT Integration Requirements Document

## Overview

This document outlines the requirements for a **Generic SSoT Integration** that enables users to sync data between Nautobot and any external system via REST API endpoints, without requiring custom code for each integration. The system will use Nautobot's `ExternalIntegration` model to define API endpoints and provide a user-configurable field mapping system.

---

## Goals

1. **Zero-Code Integration**: Allow administrators to configure new SSoT integrations entirely through the Nautobot UI without writing Python code
2. **Flexible Field Mapping**: Enable dynamic mapping between external API response fields and Nautobot model fields
3. **Bidirectional Sync**: Support both importing data FROM external systems and exporting data TO external systems
4. **Multi-Endpoint Support**: Allow a single sync job to pull data from multiple API endpoints
5. **Reusable Mappings**: Save and reuse field mapping configurations across sync operations

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Generic SSoT Integration                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐  │
│  │ External        │     │ SSoT Sync        │     │ Nautobot            │  │
│  │ Integration(s)  │────▶│ Config           │────▶│ Models              │  │
│  │ (API Endpoints) │     │ (Field Mappings) │     │ (Devices, etc.)     │  │
│  └─────────────────┘     └──────────────────┘     └─────────────────────┘  │
│           │                      │                         │                │
│           ▼                      ▼                         ▼                │
│  ┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐  │
│  │ Data Discovery  │     │ Generic          │     │ NautobotAdapter     │  │
│  │ Job             │     │ DiffSync Models  │     │ (contrib)           │  │
│  │ (Load & Preview)│     │ (Dynamic)        │     │                     │  │
│  └─────────────────┘     └──────────────────┘     └─────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## User Workflow (Revised: Discovery-First)

Data is retrieved from the API based on a **list of endpoints** defined to gather data. Each endpoint loads its information into a **key in a master dictionary** (user-definable endpoint name). Sync configurations are built by selecting a saved Data Discovery and mapping its tables to Nautobot models.

### Phase 1: Data Discovery

1. **Create Discovery Endpoints** (form-based, no JSON): User goes to **Plugins > SSoT > Discovery Endpoints** and clicks **Add** for each endpoint. Each form has text fields: Name, API Path, Data Path, HTTP Method, Pagination, headers, query params, etc. User can add as many as needed (each "Add" creates one; no JSON or plus-in-form required—the list view's Add button is the "plus").
2. **Run Discovery Job**: User runs **Generic SSoT - Data Discovery** and selects:
   - **External Integration**: Base API URL and authentication
   - **Endpoint definitions**: Multi-select of the **Discovery Endpoints** created above
   - Optional discovery name and sample size
3. **Job Execution**: The discovery job fetches data from each selected endpoint and builds a **master dictionary**: `{ endpoint_name_1: [record, ...], endpoint_name_2: [record, ...], ... }`
4. **Save as Data Discovery**: The result is saved as a **GenericSSOTDataDiscovery** model instance (master dictionary + metadata) for future reference.

### Phase 2: Create Sync Config from Data Discovery

1. **Select Data Discovery**: User creates an **SSOTSyncConfig** by picking an existing **GenericSSOTDataDiscovery** object.
2. **Load into Tables**: The chosen Data Discovery is loaded into a **set of tables** in the UI:
   - Each **master dictionary key** (endpoint name) is shown as a **separate table**
   - **Column headers** = attributes (fields) of the items
   - **Rows** = each entry that was loaded into that master dictionary key
3. **Build Mapping**: For each table (endpoint key), the user picks **Nautobot models and attributes** that correspond to each column to build the **field mapping**. A **tree-picker** (or other user-friendly selector) is used to choose the appropriate Nautobot model/attribute per column.
4. **Save Sync Config**: The mapping is stored (e.g. via `SSOTSyncEndpoint` per table/key and `SSOTFieldMapping` per column → Nautobot field) and used by the import job.

### Phase 3: Execute Sync

1. **Select Sync Configuration**: User selects a saved sync configuration (tied to a Data Discovery and its endpoint definitions).
2. **Choose Sync Direction / Options**: Import (External → Nautobot), dry run, atomic, etc.
3. **Execute Sync**: The sync job uses the same endpoint definitions (from the Data Discovery / Sync Config) to fetch live data and apply the stored mappings.
4. **Review Results**: View sync results, created/updated/deleted objects.

---

## Data Models

### GenericSSOTDataDiscovery

Stores the **master dictionary** of data fetched from multiple endpoints during a discovery run. Each key is a user-defined endpoint name; each value is the list of records returned from that endpoint. Used when creating an SSOTSyncConfig so the user can map tables (endpoint keys) and columns (attributes) to Nautobot models/fields.

```python
class GenericSSOTDataDiscovery(PrimaryModel):
    """Stores the master dictionary of data from a discovery job for mapping configuration."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # Base API and auth (one integration per discovery run)
    integration = models.ForeignKey(
        to="extras.ExternalIntegration",
        on_delete=models.CASCADE,
        related_name="ssot_data_discoveries",
    )

    # Master dictionary: { endpoint_name: [record, record, ...], ... }
    master_data = models.JSONField(
        default=dict,
        help_text="Master dictionary keyed by endpoint name; values are lists of records",
    )

    # Endpoint definitions used for this discovery (so sync can re-fetch the same way)
    # List of dicts: [{"name": "devices", "api_path": "/api/devices", "data_path": "results", ...}, ...]
    endpoint_definitions = models.JSONField(
        default=list,
        help_text="List of endpoint configs (name, api_path, data_path, pagination, etc.) used for this discovery",
    )

    # When was this discovery run?
    discovered_at = models.DateTimeField(auto_now_add=True)
```

### SSOTDiscoveryEndpoint

Reusable endpoint definition for discovery runs. Users create these via the UI (**Plugins > SSoT > Discovery Endpoints**, **Add**) with text fields for name, API path, data path, pagination, etc.—no JSON. The Discovery job then takes a **MultiObjectVar** of these; user selects which endpoints to run.

```python
class SSOTDiscoveryEndpoint(BaseModel):
    """Reusable endpoint definition for data discovery runs."""

    name = models.CharField(max_length=255)  # Key in master dictionary
    api_path = models.CharField(max_length=500, blank=True)
    data_path = models.CharField(max_length=255, blank=True)  # JMESPath
    http_method_read = models.CharField(choices=[("GET", "GET"), ("POST", "POST")], default="GET")
    request_headers = models.JSONField(default=dict, blank=True)
    query_parameters = models.JSONField(default=dict, blank=True)
    request_body_template = models.TextField(blank=True)
    pagination_type = models.CharField(...)
    pagination_config = models.JSONField(default=dict, blank=True)
    weight = models.PositiveIntegerField(default=100)
```

### SSOTSyncConfig

Stores the overall sync configuration. Created by **picking a GenericSSOTDataDiscovery**; endpoints and mappings are then configured from the discovery's tables (one endpoint per master-dict key, field mappings per column).

```python
class SSOTSyncConfig(PrimaryModel):
    """Configuration for a Generic SSoT sync operation."""

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)

    # Optional: link to the Data Discovery this config was built from
    data_discovery = models.ForeignKey(
        to="GenericSSOTDataDiscovery",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sync_configs",
        help_text="Data Discovery this sync config was created from (for table-based mapping UI)",
    )

    # Endpoints (one per discovery key / table); integration and path config from discovery or copied
    integrations = models.ManyToManyField(
        to="extras.ExternalIntegration",
        through="SSOTSyncEndpoint",
        related_name="ssot_sync_configs",
    )

    # Sync direction
    sync_direction = models.CharField(
        max_length=50,
        choices=[
            ("import", "Import (External → Nautobot)"),
            ("export", "Export (Nautobot → External)"),
            ("bidirectional", "Bidirectional"),
        ],
        default="import",
    )

    # Optional: Default dry-run setting
    dry_run_default = models.BooleanField(default=True)

    # Enable/disable
    enabled = models.BooleanField(default=True)
```

### SSOTSyncEndpoint

Defines how to interact with a specific API endpoint within a sync configuration.

```python
class SSOTSyncEndpoint(BaseModel):
    """Configuration for a single API endpoint within a sync config."""

    sync_config = models.ForeignKey(
        to="SSOTSyncConfig",
        on_delete=models.CASCADE,
        related_name="endpoints",
    )

    integration = models.ForeignKey(
        to="extras.ExternalIntegration",
        on_delete=models.CASCADE,
        related_name="ssot_endpoints",
    )

    # Endpoint-specific configuration
    name = models.CharField(max_length=255)  # Friendly name for this endpoint

    # API path (appended to integration's remote_url)
    api_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="API path to append to the integration's base URL (e.g., '/api/v1/devices')",
    )

    # HTTP method for fetching data
    http_method_read = models.CharField(
        max_length=10,
        choices=[("GET", "GET"), ("POST", "POST")],
        default="GET",
    )

    # HTTP method for writing data (export direction)
    http_method_write = models.CharField(
        max_length=10,
        choices=[("POST", "POST"), ("PUT", "PUT"), ("PATCH", "PATCH")],
        default="POST",
    )

    # Request configuration (stored as JSON)
    request_headers = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional headers to include in API requests",
    )

    query_parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Query parameters to include in GET requests",
    )

    request_body_template = models.TextField(
        blank=True,
        help_text="Jinja2 template for POST request body (for read operations that require POST)",
    )

    # Response parsing configuration
    data_path = models.CharField(
        max_length=255,
        blank=True,
        help_text="JSONPath or dot-notation path to the data array in the response (e.g., 'results' or 'data.items')",
    )

    # Pagination configuration
    pagination_type = models.CharField(
        max_length=50,
        choices=[
            ("none", "No Pagination"),
            ("offset", "Offset-based (limit/offset)"),
            ("page", "Page-based (page/per_page)"),
            ("cursor", "Cursor-based"),
            ("link", "Link Header (RFC 5988)"),
        ],
        default="none",
    )

    pagination_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Pagination-specific configuration (param names, page size, etc.)",
    )

    # Ordering for processing (allows dependencies between endpoints)
    weight = models.PositiveIntegerField(default=100)

    class Meta:
        ordering = ["weight", "name"]
        unique_together = ["sync_config", "name"]
```

### SSOTFieldMapping

Defines how individual fields map between external data and Nautobot models.

```python
class SSOTFieldMapping(BaseModel):
    """Maps a field from external data to a Nautobot model field."""

    endpoint = models.ForeignKey(
        to="SSOTSyncEndpoint",
        on_delete=models.CASCADE,
        related_name="field_mappings",
    )

    # Target Nautobot model (using ContentType for flexibility)
    nautobot_content_type = models.ForeignKey(
        to="contenttypes.ContentType",
        on_delete=models.CASCADE,
        limit_choices_to=models.Q(app_label__in=["dcim", "ipam", "tenancy", "circuits", "extras"]),
    )

    # Source field configuration (supports JMESPath expressions)
    source_field = models.CharField(
        max_length=500,
        help_text="JMESPath expression to extract data (e.g., 'hostname', 'attributes.location.name', 'interfaces[0].ip')",
    )

    # Target Nautobot field
    nautobot_field = models.CharField(
        max_length=255,
        help_text="Nautobot model field name (e.g., 'name' or 'location__name' for related fields)",
    )

    # Is this field part of the unique identifier?
    is_identifier = models.BooleanField(
        default=False,
        help_text="If True, this field is used to uniquely identify objects for updates",
    )

    # Is this field required?
    is_required = models.BooleanField(
        default=False,
        help_text="If True, records missing this field will be skipped",
    )

    # Default value if source field is missing/null
    default_value = models.JSONField(
        null=True,
        blank=True,
        help_text="Default value to use if source field is missing or null",
    )

    # Transformation configuration
    transformation_type = models.CharField(
        max_length=50,
        choices=[
            ("none", "No Transformation"),
            ("static", "Static Value"),
            ("template", "Jinja2 Template"),
            ("value_map", "Value Mapping"),
            ("regex", "Regex Extract/Replace"),
            ("type_cast", "Type Conversion"),
            ("reference", "Reference Lookup"),
            ("custom", "Custom Python Expression"),
        ],
        default="none",
    )

    transformation_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configuration for the selected transformation type",
    )

    # Enable/disable this mapping
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["endpoint", "-is_identifier", "nautobot_field"]
```

### SSOTValueMap

Provides reusable value mapping tables (e.g., external status codes → Nautobot statuses).

```python
class SSOTValueMap(PrimaryModel):
    """Reusable value mapping table for field transformations."""

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)

    # The mapping table (source_value -> target_value)
    mappings = models.JSONField(
        default=dict,
        help_text="Dictionary mapping source values to target values",
    )

    # Default value if source value is not in the mapping
    default_value = models.JSONField(
        null=True,
        blank=True,
        help_text="Default value to use if source value is not in the mapping",
    )

    # Case sensitivity for string matching
    case_sensitive = models.BooleanField(default=False)
```

### SSOTDataSample (Legacy / Optional)

Stores sample data per endpoint for mapping configuration. **Superseded by GenericSSOTDataDiscovery** in the discovery-first workflow: discovery results are now stored as a single master dictionary on GenericSSOTDataDiscovery. SSOTDataSample may be kept for backwards compatibility or removed once the Data Discovery flow is fully adopted.

```python
class SSOTDataSample(BaseModel):
    """Stores sample data from an endpoint for mapping configuration (legacy)."""

    endpoint = models.ForeignKey(
        to="SSOTSyncEndpoint",
        on_delete=models.CASCADE,
        related_name="data_samples",
    )

    sample_data = models.JSONField(default=list, ...)
    discovered_fields = models.JSONField(default=dict, ...)
    collected_at = models.DateTimeField(auto_now=True)
    total_record_count = models.PositiveIntegerField(null=True, blank=True)
```

---

## Jobs

### GenericSSOTDataDiscoveryJob

Fetches data from a **list of endpoints** (user-defined names and paths) using a single **ExternalIntegration** for base URL and authentication, builds a **master dictionary** keyed by endpoint name, and saves it as a **GenericSSOTDataDiscovery** model.

```python
class GenericSSOTDataDiscoveryJob(Job):
    """Discover available data from external API endpoints and save as Data Discovery."""

    class Meta:
        name = "Generic SSoT - Data Discovery"
        description = "Fetch data from API endpoints and save as a Data Discovery for mapping configuration"

    integration = ObjectVar(
        model=ExternalIntegration,
        required=True,
        description="External Integration for base API URL and authentication",
    )

    # User selects from predefined Discovery Endpoints (created under Plugins > SSoT > Discovery Endpoints)
    endpoint_definitions = MultiObjectVar(
        model=SSOTDiscoveryEndpoint,
        required=True,
        description="Select one or more Discovery Endpoints to fetch (create these under Plugins > SSoT > Discovery Endpoints)",
    )

    discovery_name = StringVar(
        required=False,
        description="Name for the saved Data Discovery (default: auto-generated from integration + timestamp)",
    )

    sample_size = IntegerVar(
        required=False,
        default=100,
        description="Max number of records to fetch per endpoint (for discovery preview); 0 = fetch all",
    )

    def run(self, integration, endpoints, discovery_name, sample_size):
        """
        1. For each endpoint in endpoints: build full URL from integration.remote_url + api_path
        2. Use integration's auth (SecretsGroup) to make request(s)
        3. Extract list of records using data_path (JMESPath) or raw response
        4. Store list under endpoint['name'] in master_data dict
        5. Save GenericSSOTDataDiscovery(integration=..., master_data=master_data, endpoint_definitions=endpoints)
        """
        pass
```

### GenericSSOTSyncJob (DataSource)

Syncs data FROM external systems TO Nautobot.

```python
class GenericSSOTSyncJob(DataSource):
    """Generic SSoT sync from external system to Nautobot."""

    class Meta:
        name = "Generic SSoT - Import"
        description = "Sync data from external API endpoints to Nautobot"

    sync_config = ObjectVar(
        model=SSOTSyncConfig,
        required=True,
        queryset=SSOTSyncConfig.objects.filter(enabled=True),
        description="Sync configuration to use",
    )

    dry_run = BooleanVar(
        required=False,
        default=True,
        description="Perform a dry-run without making changes",
    )

    atomic = BooleanVar(
        required=False,
        default=False,
        description="Atomic sync: rollback all changes if any record fails",
    )

    use_bulk_operations = BooleanVar(
        required=False,
        default=False,
        description="Use bulk API operations for better performance (if supported by target)",
    )

    bulk_batch_size = IntegerVar(
        required=False,
        default=100,
        description="Number of records per bulk operation (only used if bulk operations enabled)",
    )

    # DiffSync flags exposed as options
    skip_unmatched_dst = BooleanVar(
        required=False,
        default=False,
        description="Skip deletion of objects in Nautobot that don't exist in source",
    )

    def load_source_adapter(self):
        """
        1. Load sync config and associated endpoints
        2. For each endpoint, fetch data from external API
        3. Build dynamic DiffSync models based on field mappings
        4. Populate adapter with external data
        """
        self.source_adapter = GenericExternalAdapter(
            job=self,
            sync=self.sync,
            sync_config=self.sync_config,
        )
        self.source_adapter.load()

    def load_target_adapter(self):
        """
        1. Use NautobotAdapter from contrib
        2. Configure it based on the target models in field mappings
        3. Load existing Nautobot data for diff comparison
        """
        self.target_adapter = GenericNautobotAdapter(
            job=self,
            sync=self.sync,
            sync_config=self.sync_config,
        )
        self.target_adapter.load()
```

### GenericSSOTExportJob (DataTarget)

Syncs data FROM Nautobot TO external systems.

```python
class GenericSSOTExportJob(DataTarget):
    """Generic SSoT sync from Nautobot to external system."""

    class Meta:
        name = "Generic SSoT - Export"
        description = "Sync data from Nautobot to external API endpoints"

    sync_config = ObjectVar(
        model=SSOTSyncConfig,
        required=True,
        queryset=SSOTSyncConfig.objects.filter(enabled=True, sync_direction__in=["export", "bidirectional"]),
        description="Sync configuration to use",
    )

    dry_run = BooleanVar(
        required=False,
        default=True,
        description="Perform a dry-run without making changes",
    )

    atomic = BooleanVar(
        required=False,
        default=False,
        description="Atomic sync: rollback all changes if any record fails",
    )

    use_bulk_operations = BooleanVar(
        required=False,
        default=False,
        description="Use bulk API operations for better performance (if supported by target)",
    )

    bulk_batch_size = IntegerVar(
        required=False,
        default=100,
        description="Number of records per bulk operation (only used if bulk operations enabled)",
    )

    skip_unmatched_src = BooleanVar(
        required=False,
        default=False,
        description="Skip creation of objects in external system that don't exist in Nautobot",
    )

    def load_source_adapter(self):
        """Load Nautobot data as the source."""
        self.source_adapter = GenericNautobotAdapter(
            job=self,
            sync=self.sync,
            sync_config=self.sync_config,
        )
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load external system data as target (for diff comparison)."""
        self.target_adapter = GenericExternalAdapter(
            job=self,
            sync=self.sync,
            sync_config=self.sync_config,
        )
        self.target_adapter.load()

    # Override sync execution to make API POST/PUT calls
    def execute_sync(self):
        """
        For each create/update/delete operation:
        1. Build request payload using field mappings (reverse direction)
        2. Make appropriate HTTP request (POST for create, PUT/PATCH for update, DELETE for delete)
        3. Log results
        """
        pass
```

---

## Adapters

### GenericExternalAdapter

Dynamic adapter that builds DiffSync models from field mapping configuration.

```python
class GenericExternalAdapter(Adapter):
    """Generic adapter for external API data."""

    def __init__(self, job, sync, sync_config):
        super().__init__()
        self.job = job
        self.sync = sync
        self.sync_config = sync_config
        self._build_dynamic_models()

    def _build_dynamic_models(self):
        """
        Dynamically create DiffSyncModel classes based on field mappings.

        For each unique (endpoint, nautobot_content_type) combination:
        1. Get all field mappings for that combination
        2. Build a DiffSyncModel class with:
           - _modelname from content_type
           - _identifiers from fields where is_identifier=True
           - _attributes from remaining fields
           - Pydantic fields for each mapping
        3. Register the model with the adapter
        """
        pass

    def load(self):
        """
        For each endpoint in sync_config:
        1. Make API request(s) with pagination
        2. Extract data using data_path (JMESPath expression)
        3. For each record, extract fields using JMESPath expressions
        4. Apply field transformations
        5. Create DiffSyncModel instance
        6. Add to adapter
        """
        pass

    def _fetch_data(self, endpoint):
        """Fetch data from an endpoint with pagination support."""
        pass

    def _extract_field(self, record, jmespath_expression):
        """Extract a field value from a record using JMESPath."""
        import jmespath
        return jmespath.search(jmespath_expression, record)

    def _apply_transformations(self, record, field_mapping):
        """Apply configured transformation to a field value."""
        pass
```

### GenericNautobotAdapter

Leverages existing `NautobotAdapter` from contrib with dynamic configuration.

```python
class GenericNautobotAdapter(NautobotAdapter):
    """Generic Nautobot adapter configured from field mappings."""

    def __init__(self, job, sync, sync_config):
        super().__init__(job=job, sync=sync)
        self.sync_config = sync_config
        self._configure_from_mappings()

    def _configure_from_mappings(self):
        """
        Configure the adapter based on field mappings:
        1. Determine which Nautobot models to load
        2. Build corresponding NautobotModel classes
        3. Configure queryset filters if needed
        """
        pass
```

---

## Field Transformation Types

### 1. None (Direct Copy)
```json
{
  "transformation_type": "none"
}
```

### 2. Static Value
```json
{
  "transformation_type": "static",
  "transformation_config": {
    "value": "Active"
  }
}
```

### 3. Jinja2 Template
```json
{
  "transformation_type": "template",
  "transformation_config": {
    "template": "{{ hostname | lower }}-{{ site_code }}"
  }
}
```

### 4. Value Mapping
```json
{
  "transformation_type": "value_map",
  "transformation_config": {
    "value_map_id": "uuid-of-ssot-value-map",
    // OR inline mapping:
    "inline_map": {
      "1": "Active",
      "2": "Planned",
      "3": "Decommissioned"
    }
  }
}
```

### 5. Regex Extract/Replace
```json
{
  "transformation_type": "regex",
  "transformation_config": {
    "pattern": "^([A-Z]{3})-.*",
    "replacement": "\\1",
    // OR for extraction:
    "extract_group": 1
  }
}
```

### 6. Type Conversion
```json
{
  "transformation_type": "type_cast",
  "transformation_config": {
    "target_type": "integer",  // string, integer, float, boolean, datetime
    "datetime_format": "%Y-%m-%dT%H:%M:%SZ"  // for datetime conversion
  }
}
```

### 7. Reference Lookup
```json
{
  "transformation_type": "reference",
  "transformation_config": {
    "target_model": "dcim.location",
    "lookup_field": "name",
    "create_if_missing": false,
    "default_value": null
  }
}
```

### 8. Custom Python Expression
```json
{
  "transformation_type": "custom",
  "transformation_config": {
    "expression": "value.split('-')[0] if value else None"
  }
}
```

---

## API Endpoints

### REST API

```
/api/plugins/ssot/data-discoveries/
  GET    - List all Data Discoveries
  POST   - Create new Data Discovery (typically created by discovery job)

/api/plugins/ssot/data-discoveries/{id}/
  GET    - Retrieve Data Discovery (includes master_data, endpoint_definitions)
  PUT    - Update
  PATCH  - Partial update
  DELETE - Delete

/api/plugins/ssot/sync-configs/
  GET    - List all sync configurations
  POST   - Create new sync configuration (data_discovery optional)

/api/plugins/ssot/sync-configs/{id}/
  GET    - Retrieve sync configuration
  PUT    - Update sync configuration
  PATCH  - Partial update
  DELETE - Delete sync configuration

/api/plugins/ssot/sync-endpoints/
  GET    - List all sync endpoints
  POST   - Create new endpoint

/api/plugins/ssot/field-mappings/
  GET    - List all field mappings
  POST   - Create new field mapping

/api/plugins/ssot/value-maps/
  GET    - List all value maps
  POST   - Create new value map

/api/plugins/ssot/data-samples/
  GET    - List data samples (legacy)

/api/plugins/ssot/sync-configs/{id}/sync/
  POST   - Trigger a sync job
```

---

## UI Views

### Data Discovery List
- Table of all **GenericSSOTDataDiscovery** objects
- Columns: Name, Integration, Endpoint keys (count), Discovered at, Actions
- "Run Discovery" action (links to discovery job with optional pre-fill)

### Data Discovery Detail
- Overview: Name, integration, discovered_at, endpoint_definitions (read-only)
- **Tables panel**: One table per master-dict key; each table shows columns = attributes, rows = records
- "Create Sync Config from this Discovery" button → creates SSOTSyncConfig with data_discovery set and pre-creates endpoints from discovery keys

### Sync Configuration List
- Table of all sync configurations
- Columns: Name, Data Discovery (link), Direction, Enabled, Last Sync, Actions
- Bulk actions: Enable, Disable, Delete

### Sync Configuration Create (from Data Discovery)
- User picks a **GenericSSOTDataDiscovery** (required when creating from discovery flow)
- UI loads the Data Discovery's **master_data** into a set of tables (one table per endpoint key)
- For each table: columns = attributes, rows = entries
- **Mapping builder**: For each table (endpoint key), user selects target Nautobot model (e.g. Device, Location). For each column (source attribute), user picks the corresponding Nautobot model attribute. A **tree-picker** (or dropdown/hierarchical selector) is used to choose the Nautobot model and attribute (e.g. dcim → Device → name, dcim → Device → location → name). This builds SSOTSyncEndpoint (one per table) and SSOTFieldMapping (one per column → Nautobot field).

### Sync Configuration Detail
- Overview tab: Basic config, description, linked Data Discovery, status
- Endpoints tab: List of configured endpoints (one per discovery key / table)
- Field Mappings tab: Per-endpoint field mappings (source attribute → Nautobot model/field)
- Sync History tab: List of past sync operations

### Field Mapping Editor (per endpoint/table)
- Source: columns (attributes) from the discovery table for that endpoint
- Target: **Tree-picker** (or user-friendly alternative) to select Nautobot model and attribute:
  - Option A: Tree view (App → Model → Field, with support for related fields like location__name)
  - Option B: Grouped dropdowns (ContentType for model, then field name dropdown filtered by model)
- Transformation configuration modal
- Preview panel showing sample transformations

---

## Security Considerations

1. **Credential Storage**: All API credentials stored via Nautobot's SecretsGroup mechanism (already part of ExternalIntegration)

2. **Custom Expression Sandboxing**: The "custom" transformation type must use a sandboxed Python execution environment (e.g., RestrictedPython) to prevent arbitrary code execution

3. **Request Validation**: Validate all outgoing API requests to prevent SSRF attacks

4. **Rate Limiting**: Implement configurable rate limiting for API requests to external systems

5. **Audit Logging**: All sync operations logged through Nautobot's standard job logging and Sync model

---

## Phase 1 Implementation (MVP)

### Dependencies:
- `jmespath` - For nested JSON field extraction

### Included in MVP:
- [ ] `SSOTSyncConfig` model with basic fields
- [ ] `SSOTSyncEndpoint` model with GET request support
- [ ] `SSOTFieldMapping` model with JMESPath support and basic transformations (none, static, value_map, type_cast)
- [ ] `SSOTValueMap` model
- [ ] `SSOTDataSample` model for discovery results
- [ ] `GenericSSOTDataDiscoveryJob` for fetching sample data
- [ ] `GenericSSOTSyncJob` (DataSource) for import operations with atomic/bulk options
- [ ] Basic REST API for all models
- [ ] Simple list/detail views for sync configurations
- [ ] DiffSync flag exposure (skip_unmatched_dst, skip_unmatched_src)

### Deferred to Phase 2:
- [ ] Export functionality (DataTarget)
- [ ] Advanced transformations (template, regex, custom)
- [ ] Visual drag-and-drop mapping editor
- [ ] Pagination support beyond offset-based
- [ ] Multi-model relationships in single sync
- [ ] Webhook triggers for real-time sync

### Deferred to Phase 3:
- [ ] Bidirectional sync
- [ ] Conflict resolution strategies
- [ ] Scheduled sync jobs
- [ ] GraphQL API support
- [ ] Import/export of sync configurations

---

## Success Criteria

1. **Functional**: A user can configure a sync from an arbitrary REST API to Nautobot Device model without writing code
2. **Performance**: Sync of 1,000 records completes within 60 seconds (bulk operations enabled)
3. **Reliability**:
   - With `atomic=True`: Failed syncs rollback completely, leaving no partial data
   - With `atomic=False`: Failed records are logged, successful records are committed
4. **Usability**: A new user can configure their first sync within 30 minutes using documentation
5. **Maintainability**: Adding support for a new transformation type requires < 50 lines of code

---

## Design Decisions

The following decisions have been made for key architectural questions:

### 1. Nested Object Handling: JMESPath

**Decision**: Use [JMESPath](https://jmespath.org/) for referencing deeply nested JSON structures.

JMESPath provides a powerful query language for JSON that supports:
- Nested object access: `device.interfaces[0].ip_addresses[0].address`
- Array projections: `devices[*].name`
- Filtering: `devices[?status=='active'].name`
- Multi-select: `{name: name, ip: primary_ip}`

**Example source_field values**:
```
# Simple field
hostname

# Nested object
attributes.location.name

# Array index
interfaces[0].ip_address

# Array projection (returns list)
interfaces[*].name

# Filtered selection
interfaces[?type=='management'].ip_address | [0]
```

### 2. Relationship Dependencies: DiffSync Handles Automatically

**Decision**: Leverage DiffSync's built-in dependency management through model hierarchy.

DiffSync already handles relationship dependencies through:
- `_children` attribute on DiffSyncModel classes defines parent-child relationships
- `top_level` attribute on adapters defines processing order
- Models are processed in dependency order automatically

**Implementation**:
- Define model hierarchy in dynamic model generation
- Use `weight` field on `SSOTSyncEndpoint` for endpoint processing order
- DiffSync ensures parents are created before children

### 3. Conflict Resolution: DiffSync Handles Automatically

**Decision**: Use DiffSync's built-in diff flags for conflict resolution.

DiffSync provides several flags to control sync behavior:
- `DiffSyncFlags.CONTINUE_ON_FAILURE` - Continue processing after errors
- `DiffSyncFlags.SKIP_UNMATCHED_DST` - Don't delete objects missing from source
- `DiffSyncFlags.SKIP_UNMATCHED_SRC` - Don't create objects missing from target

**Implementation**:
- Expose relevant DiffSync flags as job parameters
- For bidirectional sync, run two separate sync operations with appropriate flags
- Document flag combinations for common use cases

### 4. Bulk Operations: Configurable Job Option

**Decision**: Make bulk operations an optional feature enabled per-job.

**Implementation**:
- Add `use_bulk_operations` boolean parameter to sync jobs
- When enabled, batch create/update operations into bulk API calls
- Configurable batch size (default: 100)
- Fall back to individual operations if bulk endpoint fails

**Job Parameters**:
```python
use_bulk_operations = BooleanVar(
    required=False,
    default=False,
    description="Use bulk API operations for better performance (if supported)",
)

bulk_batch_size = IntegerVar(
    required=False,
    default=100,
    description="Number of records per bulk operation",
)
```

### 5. Error Recovery: Atomic Commits Option

**Decision**: Provide an atomic commits option that rolls back all changes on any failure.

**Implementation**:
- Add `atomic` boolean parameter to sync jobs
- When `atomic=True`: Wrap entire sync in a database transaction; any failure rolls back all changes
- When `atomic=False`: Use DiffSync's `CONTINUE_ON_FAILURE` flag; log errors and continue with remaining records
- Default: `atomic=False` (continue on failure) for flexibility

**Job Parameters**:
```python
atomic = BooleanVar(
    required=False,
    default=False,
    description="Atomic sync: rollback all changes if any record fails",
)
```

**Behavior Matrix**:
| atomic | Behavior on Error |
|--------|-------------------|
| True | Rollback all changes, job fails |
| False | Log error, continue with remaining records, job succeeds with warnings |

---

## Appendix: Example Use Case

### Use Case: Sync devices from ServiceNow CMDB

**Step 1: Create External Integration**
```yaml
Name: ServiceNow Production
Remote URL: https://company.service-now.com
Secrets Group: servicenow-prod-creds
```

**Step 2: Create Sync Configuration**
```yaml
Name: ServiceNow Device Import
Direction: Import
```

**Step 3: Configure Endpoint**
```yaml
Integration: ServiceNow Production
API Path: /api/now/table/cmdb_ci_server
HTTP Method: GET
Data Path: result
Pagination Type: offset
Pagination Config:
  limit_param: sysparm_limit
  offset_param: sysparm_offset
  page_size: 100
```

**Step 4: Run Discovery**
- System fetches sample data
- User sees fields: `name`, `sys_id`, `ip_address`, `location.name`, `u_device_role`, `operational_status`

**Step 5: Configure Field Mappings**
| Source Field (JMESPath) | Nautobot Field | Transformation |
|------------------------|----------------|----------------|
| `name` | `Device.name` | None (identifier) |
| `sys_id` | `Device.custom_fields.servicenow_id` | None |
| `ip_address` | `Device.primary_ip4` | Reference lookup |
| `location.name` | `Device.location` | Reference lookup |
| `u_device_role` | `Device.role` | Value map (SNOW roles → Nautobot roles) |
| `operational_status` | `Device.status` | Value map (1=Active, 2=Maintenance, etc.) |
| `hardware.manufacturer` | `Device.device_type.manufacturer` | Reference lookup |
| `interfaces[?primary==\`true\`].ip \| [0]` | `Device.primary_ip4` | Reference lookup (complex JMESPath) |

**Step 6: Run Sync**
```yaml
Sync Configuration: ServiceNow Device Import
Dry Run: True  # Preview first
Atomic: False  # Continue on errors
Use Bulk Operations: True
Bulk Batch Size: 100
Skip Unmatched Dst: True  # Don't delete devices not in ServiceNow
```
- Dry run shows: 150 creates, 23 updates, 0 deletes
- Execute sync (dry_run=False)
- Review results: 150 devices created, 23 updated, 2 errors logged (invalid location reference)
