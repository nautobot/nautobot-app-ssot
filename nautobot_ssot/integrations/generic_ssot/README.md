# Generic SSoT Integration - MVP

This is an MVP implementation of the Generic SSoT Integration that enables zero-code synchronization between Nautobot and external REST APIs.

## Features

- **Zero-Code Integration**: Configure syncs entirely through the Nautobot UI
- **Flexible Field Mapping**: Map external API fields to Nautobot model fields using JMESPath
- **Data Discovery**: Fetch and preview sample data from API endpoints
- **Field Transformations**: Support for static values, value mapping, and type conversion
- **Import Sync**: Sync data FROM external systems TO Nautobot

## Setup

1. **Enable the integration** in `nautobot_config.py`:
   ```python
   PLUGINS_CONFIG = {
       "nautobot_ssot": {
           "enable_generic_ssot": True,
       }
   }
   ```

2. **Run migrations**:
   ```bash
   nautobot-server migrate
   ```

3. **Install dependencies**:
   ```bash
   poetry install
   # or
   pip install jmespath
   ```

## Workflow (matches diagram)

1. **Create External Integration** – Define the external system (base URL, auth via SecretsGroup).
2. **Create SSoT Endpoints** – Under **Plugins > SSoT > Endpoints**, create one or more endpoints tied to that integration (name, api_path, data_path, HTTP method, pagination, etc.).
3. **Run Discovery Job** – Run **Generic SSoT - Data Discovery**: select the same integration’s endpoints (multi-select). The job fetches from each and saves a **Data Discovery** (master dictionary).
4. **Create Sync Config** – Under **Plugins > SSoT > Generic SSoT Configs**, create a Sync Config; link the **Data Discovery** and add **Endpoints** (via the Sync Config Endpoints panel – same SSoT Endpoints used for discovery).
5. **Build field mappings** – On the Sync Config detail page, click **Build field mappings**. This creates/uses an **SSoT Mapping** and lets you map each source field (per endpoint) to a Nautobot model and field.
6. **Run Sync Job** – Run **Generic SSoT - Import**: select the **Sync Config** and the **SSoT Mapping** (the one linked to that config). Optionally run with dry run first.

## Usage (step-by-step)

### Step 1: Create External Integration

Create an `ExternalIntegration` object in Nautobot that defines:
- Base URL of the external API
- Authentication credentials (via SecretsGroup)
- SSL verification settings

### Step 2: Create SSoT Endpoints

1. Go to **Plugins > SSoT > Endpoints**.
2. Click **Add** and create endpoints for your integration:
   - **Integration**: The External Integration from Step 1
   - **Name**: Friendly name (used as the key in the discovery result)
   - **API Path**: e.g. `/api/v1/devices`
   - **Data Path**: JMESPath to the data array (e.g. `results` or `data.items`)
   - **HTTP Method Read**: GET or POST
   - **Pagination** and optional headers/query params as needed
3. Create as many endpoints as you need (all must use the same integration for a single discovery run).

### Step 3: Run Data Discovery

1. Run the **Generic SSoT - Data Discovery** job:
   - **Endpoint definitions**: Select one or more **SSoT Endpoints** you created (multi-select; all must share the same integration)
   - **Discovery name**: Optional; leave blank for auto-generated
   - **Sample size**: Max records per endpoint (default 100)
2. The job fetches from each selected endpoint and saves a **Data Discovery**. Review the discovered data to understand the API structure.

### Step 4: Create Sync Config and add Endpoints

1. Navigate to **Plugins > SSoT > Generic SSoT Configs** and create a new **Sync Config**:
   - **Data Discovery**: Link the Data Discovery from Step 3 (or use “Create Sync Config from this Discovery” on the discovery detail page)
   - **Sync Direction**: “Import” (for MVP)
   - **Enabled**: True
2. On the sync config detail page, in the **Endpoints** panel, add one or more **SSoT Endpoints** (the same ones you used for discovery). Order is controlled by the **weight** on each Sync Config Endpoint row.

### Step 5: Build field mappings

1. On the sync config detail page, click **Build field mappings**.
2. For each endpoint and each source column, choose the **Nautobot model** (ContentType) and **Nautobot field**. This creates/updates an **SSoT Mapping** and its **Field Mappings** (per endpoint).
3. Save. The sync config’s **SSoT Mapping** is set or reused automatically.

### Step 6: Run Sync

1. Run the **Generic SSoT - Import** job:
   - **Sync Config**: Your sync configuration
   - **SSoT Mapping**: The mapping linked to that config (or the one you built in Step 5)
   - **Dry Run**: True to preview, then False to apply
   - **Skip Unmatched Dst**: True to avoid deleting objects in Nautobot that don’t exist in source
2. Review results and run again with dry run off to apply changes.

## JMESPath Examples

- Simple field: `hostname`
- Nested field: `attributes.location.name`
- Array index: `interfaces[0].ip_address`
- Array projection: `interfaces[*].name`
- Filtered selection: `interfaces[?type=='management'].ip_address | [0]`

## Limitations (MVP)

- Export functionality (Nautobot → External) not yet implemented
- Only offset-based pagination supported
- Limited transformation types (none, static, value_map, type_cast)
- No visual drag-and-drop mapping editor
- No bidirectional sync
- No scheduled sync jobs

## Next Steps

See `generic_ssot_requirements.md` for planned Phase 2 and Phase 3 features.
