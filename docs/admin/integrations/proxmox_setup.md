# Proxmox VE Integration Setup

This guide describes how to enable and configure the Proxmox VE integration.

## Prerequisites

Install the SSoT app with the Proxmox VE extra (installs `proxmoxer`):

```shell
pip install nautobot-ssot[proxmox]
```

## Enabling the integration

Add the following keys to `PLUGINS_CONFIG` in `nautobot_config.py`:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_proxmox": True,
        "proxmox_create_default_secrets": True,
    },
}
```

| Key | Default | Description |
| --- | ------- | ----------- |
| `enable_proxmox` | `False` | Enables the Proxmox VE integration. |
| `proxmox_create_default_secrets` | `True` | Creates default Secrets, a Secrets Group, an External Integration, and an `SSOTProxmoxConfig` on startup. Set to `False` to create these objects manually. |

Restart Nautobot after changing these settings.

All other settings are stored on the `SSOTProxmoxConfig` object and edited in the UI under
**Apps → Single Source of Truth → Proxmox VE Config**. See the
[Configuration reference](#configuration-reference) for the full field list.

## Authentication

The integration authenticates to Proxmox VE with an API token. Password login is not supported.

Create a token in Proxmox under *Datacenter → Permissions → API Tokens* and assign it a read-only
role such as `PVEAuditor`. Proxmox displays two values when the token is created:

- **Token ID**, in the form `user@realm!tokenid` (for example `root@pam!nautobot`).
- **Token secret**, a UUID. Proxmox shows it only once, so copy it immediately.

Nautobot stores both values as [Secrets][nb-secret], grouped in a [Secrets Group][nb-secretsgroup]
that is attached to an [External Integration][nb-extint] for the Proxmox host.

### Secrets Group associations

The Secrets Group must contain the following two associations. Saving an `SSOTProxmoxConfig` fails
with a validation error if either one is missing.

| Access Type | Secret Type | Value                                         |
| :---------- | :---------- | :-------------------------------------------- |
| REST        | Username    | Token ID (`user@realm!tokenid`)               |
| REST        | Token       | Token secret (UUID shown at creation time)    |

### Creating the Secrets

Secret values are always entered on the Secret objects themselves. The Config page only selects an
existing Secrets Group.

**With `proxmox_create_default_secrets=True` (default):**

1. Edit the two default Secrets so they resolve to the Token ID and token secret.
2. Open the `ProxmoxConfigDefault` config under **Apps → Single Source of Truth → Proxmox VE
   Config**.
3. Set **Secrets Group**, **Remote URL**, **Verify SSL**, and **Timeout**. These values are saved to
   the `DefaultProxmoxInstance` External Integration.

**With `proxmox_create_default_secrets=False`:**

1. Create two Secrets for the Token ID and token secret.
2. Create a Secrets Group with the associations listed above.
3. Create an External Integration and an `SSOTProxmoxConfig` that references it. Remote URL, Verify
   SSL, Timeout, and Secrets Group can then be set on the Config page as described above.

The SSoT tag, custom fields, relationship, statuses, and node Manufacturer/DeviceType/Role are
created in both cases. The default Location (`Proxmox VE Default Location`) is only created when
`proxmox_create_default_secrets` is `True`.

!!! note "Secret providers"
    The default Secrets use the environment-variable provider, but any Nautobot
    [secret provider][nb-secret] can be used, for example HashiCorp Vault or AWS Secrets Manager.
    The integration only requires the REST Username and REST Token associations listed above.

To use the default environment-variable Secrets, set these variables in the Nautobot and worker
environments:

```bash
export NAUTOBOT_SSOT_PROXMOX_TOKEN_ID="root@pam!nautobot"
export NAUTOBOT_SSOT_PROXMOX_TOKEN_SECRET="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

[nb-secret]: https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/secret/
[nb-secretsgroup]: https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/secret/#secrets-groups
[nb-extint]: https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/externalintegration/

## Configuration reference

All fields have defaults, and the auto-created `ProxmoxConfigDefault` is pre-populated with them.
Only the credentials and the Remote URL must be set before running a sync.

The following fields are editable on the `SSOTProxmoxConfig` page. SSoT Tag, Default Cluster Type,
Default Location, Default Node Device Type, and Default Node Device Role reference existing objects
and default to the objects created on first migrate. SSoT Tag is optional; the other four are
required.

| Field | Default | Purpose |
| ----- | ------- | ------- |
| **Sync to Nautobot** (`enable_sync_to_nautobot`) | `True` | Allow syncing data from Proxmox VE into Nautobot. Required for the config to appear in the job. |
| **Enabled for Sync Job** (`job_enabled`) | `False` | Make this config selectable in the sync job. Enable it before running. |
| **Use Clusters** (`use_clusters`) | `True` | Place VMs in their Proxmox cluster. If `False`, all VMs go in the default cluster. |
| **Sync LXC Containers** (`sync_lxc`) | `True` | Include LXC containers as Virtual Machines (in addition to QEMU VMs). |
| **Sync Nodes as Devices** (`sync_nodes_as_devices`) | `True` | Model Proxmox nodes as Nautobot Devices and link VMs to their host node. |
| **Sync Proxmox VE Tags** (`sync_proxmox_tags`) | `True` | Copy Proxmox VE tags onto Nautobot Virtual Machines as Tags. |
| **SSoT Tag** (`default_ssot_tag`) | Tag named "SSoT Synced from Proxmox" (pre-created) | Optional. Tag applied to every synced object for visibility in the UI. It does not affect which objects the sync manages; that is determined by the `last_synced_from_proxmox_on` custom field. If the tag is deleted, this field is cleared and the next sync recreates the tag. See [Limitations](../../user/integrations/proxmox.md#limitations). |
| **VM status map** (`default_vm_status_map`) | see [The three JSON map fields](#the-three-json-map-fields) | Map Proxmox VM states to Nautobot Status names. |
| **IP status map** (`default_ip_status_map`) | see [The three JSON map fields](#the-three-json-map-fields) | Map IP states to Nautobot Status names. |
| **Node interface type map** (`default_node_interface_type_map`) | see [The three JSON map fields](#the-three-json-map-fields) | Map Proxmox node interface types to Nautobot DCIM interface types. |
| **Primary IP Sort Logic** (`primary_ip_sort_by`) | `Lowest` | How to choose a VM's primary IP when several are present. |
| **Ignore Link Local** (`default_ignore_link_local`) | `True` | Ignore link-local / APIPA addresses on VM interfaces. |
| **Default Cluster Group Name** (`default_clustergroup_name`) | `Proxmox VE Default Cluster Group` | Name of the ClusterGroup that contains synced clusters. Created by the sync if it does not exist. |
| **Default Cluster Name** (`default_cluster_name`) | `Proxmox VE Default Cluster` | Name of the Cluster used when **Use Clusters** is disabled. Created by the sync if it does not exist. |
| **Default Cluster Type** (`default_cluster_type`) | ClusterType named "Proxmox VE" (pre-created) | ClusterType assigned to synced clusters. |
| **Default Location** (`default_location`) | Location named "Proxmox VE Default Location" (pre-created when `proxmox_create_default_secrets=True`, the default) | Location assigned to node Devices. Not pre-created when `proxmox_create_default_secrets` is `False`; select an existing Location instead. |
| **Default Node Device Type** (`default_device_type`) | DeviceType named "Proxmox Node" (pre-created) | DeviceType assigned to node Devices. |
| **Default Node Device Role** (`default_device_role`) | Role named "Proxmox Node" (pre-created) | Role assigned to node Devices. |

### Example configuration

`name`, `proxmox_instance`, Default Cluster Type, Default Location, Default Node Device Type, and
Default Node Device Role are required. The following `nbshell` example creates a config with the
required fields and the default SSoT Tag, using the objects created on first migrate:

```python
from nautobot.dcim.models import DeviceType, Location
from nautobot.extras.models import ExternalIntegration, Role, Tag
from nautobot.virtualization.models import ClusterType
from nautobot_ssot.integrations.proxmox.models import SSOTProxmoxConfig

SSOTProxmoxConfig.objects.create(
    name="Production Proxmox",
    proxmox_instance=ExternalIntegration.objects.get(name="DefaultProxmoxInstance"),
    default_ssot_tag=Tag.objects.get(name="SSoT Synced from Proxmox"),
    default_cluster_type=ClusterType.objects.get(name="Proxmox VE"),
    default_location=Location.objects.get(name="Proxmox VE Default Location"),
    default_device_type=DeviceType.objects.get(model="Proxmox Node"),
    default_device_role=Role.objects.get(name="Proxmox Node"),
    # Other fields use the defaults listed above; pass them here to override, e.g. job_enabled=True.
)
```

### The three JSON map fields

Three `SSOTProxmoxConfig` fields hold JSON maps. They are edited as JSON on the Config page or set via
`nbshell`.

#### VM status map

`default_vm_status_map` maps Proxmox VM states (from `/cluster/resources`: `running`, `stopped`,
`paused`) to Nautobot `Status` names. The map must not be empty, and each value must name an
existing Status. The default statuses (`Active`, `Offline`, `Suspended`, `Reserved`) are created
when the integration is enabled. Default:

```json
{
    "running": "Active",
    "stopped": "Offline",
    "paused": "Suspended"
}
```

#### IP status map

`default_ip_status_map` maps IP states to Nautobot `Status` names. The keys must be exactly
`PREFERRED` and `UNKNOWN`, and each value must name an existing Status. Default:

```json
{
    "PREFERRED": "Active",
    "UNKNOWN": "Reserved"
}
```

#### Node interface type mapping

Proxmox's API does not report a node interface's link speed, so `default_node_interface_type_map`
maps each Proxmox interface type to a Nautobot DCIM interface type. Any Proxmox type not present in
the map uses `other`. Keys must be Proxmox interface types (`eth`, `bond`, `OVSBond`, `bridge`,
`OVSBridge`, `vlan`) and values must be valid Nautobot interface types. Default:

```json
{
    "eth": "1000base-t",
    "bond": "lag",
    "OVSBond": "lag",
    "bridge": "bridge",
    "OVSBridge": "bridge",
    "vlan": "virtual"
}
```

For example, to map physical NICs to 10GBASE-T instead of 1000BASE-T:

```json
{
    "eth": "10gbase-t",
    "bond": "lag",
    "OVSBond": "lag",
    "bridge": "bridge",
    "OVSBridge": "bridge",
    "vlan": "virtual"
}
```

## Reference: objects & naming

The integration creates the following objects with fixed names and keys. They can be used for
filtering, reporting, and automation. To find all objects managed by the integration, filter on the
`last_synced_from_proxmox_on` custom field rather than the tag.

| Purpose | Type | Name / key |
| :------ | :--- | :--------- |
| Identifies which objects the integration manages | Custom field (Date) | key `last_synced_from_proxmox_on` ("Last synced from Proxmox on") |
| Marks synced objects for visibility in the UI | Tag | **SSoT Synced from Proxmox** (configurable via `default_ssot_tag`) |
| Links a VM to its host node | Relationship (Device → VM, one-to-many) | label **Proxmox VM Host**, key `proxmox_vm_host` |
| Node PVE version | Device custom field (Text) | key `proxmox_pve_version` |
| Node CPU count | Device custom field (Integer) | key `proxmox_cpu_count` |
| Node memory (GB) | Device custom field (Integer) | key `proxmox_memory_gb` |
| Cluster type for Proxmox clusters | ClusterType | **Proxmox VE** |
