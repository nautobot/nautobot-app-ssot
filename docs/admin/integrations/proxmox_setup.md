# Proxmox VE Integration Setup

This guide describes how to enable and configure the Proxmox VE integration.

## Prerequisites

Install the SSoT app with the Proxmox VE extra (installs `proxmoxer`):

```shell
pip install nautobot-ssot[proxmox]
```

## Configuration surface: config file vs. GUI

`nautobot_config.py` only ever needs **two** keys for this integration:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_proxmox": True,
        # Required. Enables the Proxmox VE integration.
        "proxmox_create_default_secrets": True,
        # Optional (default True). When False, the integration does NOT auto-create the default
        # Secrets, SecretsGroup, ExternalIntegration, and SSOTProxmoxConfig — manage those yourself.
    },
}
```

Restart Nautobot for the change to take effect.

**Everything else is configured in the GUI**, on one page: the `SSOTProxmoxConfig` edit page under
**Apps → Single Source of Truth → Proxmox VE Config**. That single page covers credential *selection*
(picking a Secrets Group), the Proxmox instance's Remote URL/Verify SSL/Timeout, every sync behavior
toggle, the SSoT tag name/description, all three JSON map fields, and all the "default X name" fields
used for node Devices/Clusters/Locations. See [Configuration reference](#configuration-reference) for
the full field list.

The one thing that never moves into that GUI page is entering the *real* credential value — see
[Authentication](#authentication) for why and how.

## Authentication

The integration authenticates to Proxmox VE using an **API token** (no password login). Create a
token in Proxmox under *Datacenter → Permissions → API Tokens* and assign it a read-only role such
as `PVEAuditor`. When the token is created, Proxmox shows two values:

- the **Token ID**, in the form `user@realm!tokenid` (e.g. `root@pam!nautobot`), and
- the **token secret** (a UUID) — copy it immediately, it is **not shown again**.

These two values are stored in Nautobot as [Secrets][nb-secret], grouped in a
[Secrets Group][nb-secretsgroup], and attached to the Proxmox host via an
[External Integration][nb-extint]. If you are new to these objects, read the linked core Nautobot
documentation first — the rest of this section explains how the Proxmox integration expects them to
be arranged.

### How the credentials are mapped

The Proxmox integration does **not** use the usual username/password pattern — it maps the API
token onto the REST Username/Token secret slots. The `SSOTProxmoxConfig` is validated on save and
will be **rejected** unless its Secrets Group contains exactly these two associations
(see `models.py::_clean_proxmox_instance`):

| Access Type | Secret Type | Holds                                                  |
| :---------- | :---------- | :----------------------------------------------------- |
| REST        | Username    | The full **Token ID** — `user@realm!tokenid`           |
| REST        | Token       | The **token secret** (the UUID shown at creation time) |

> If either association is missing, saving the config raises a validation error naming the missing
> secret (e.g. *"Secrets group ... must have a secret with type Token and access type REST holding
> the API Token Secret."*).

### The one manual step: creating the Secrets

Entering the real token value into a Nautobot [Secret][nb-secret] is the **only** step here that can
never be done through the Config GUI page — Nautobot has no masked/password input surface for secret
material, so this stays a dedicated, purpose-built object regardless of how the rest of the
integration is configured.

Everything downstream of that — the Secrets Group, the External Integration, and the Config — is a
choice between two starting points:

- **Default path** (`proxmox_create_default_secrets=True`, the default): the
  `nautobot_database_ready` signal already created a ready-to-edit set of objects (see
  `signals.py`) — two Secrets, a Secrets Group wiring them to `REST`/`Username` and `REST`/`Token`, an
  External Integration, and a Config. Just edit the two Secrets with your real values (or point them
  at a different provider — see the note below), then set **Secrets Group**, **Remote URL**, **Verify
  SSL**, and **Timeout** on the **`ProxmoxConfigDefault`** Config page (**Apps → Single Source of
  Truth → Proxmox VE Config**) — these write straight through to the underlying `DefaultProxmoxInstance`
  External Integration. The Config form only lets you *select* an existing Secrets Group; it never
  creates or edits Secret values itself.
- **Manual path** (`proxmox_create_default_secrets=False`): nothing is auto-created — build it
  yourself. Create two [Secrets][nb-secret] holding the Token ID and token secret, a
  [Secrets Group][nb-secretsgroup] with the same two associations, then create an
  [External Integration][nb-extint] and a `SSOTProxmoxConfig` pointing at it (placeholder values are
  fine for both — the same Config page fields above set Remote URL/Verify SSL/Timeout/Secrets Group
  either way). The schema prerequisites (SSoT tag, custom fields, relationship, statuses, node Device
  prerequisites) are still created regardless of this setting — only the Secrets/SecretsGroup/
  ExternalIntegration/Config bootstrap is skipped.

!!! note "The secret provider is your choice"
    The environment-variable provider used by the default Secrets is **only an example** — **any
    Nautobot [secret provider][nb-secret] works** (environment variable, text, HashiCorp Vault, AWS
    Secrets Manager, etc.). The integration does not care how the values are sourced; the only hard
    requirement is the REST Username / REST Token mapping in the table above. Edit the default
    secrets to use whichever provider you prefer, or create your own.

Because the default secrets use the **environment-variable** provider, one easy path for the default
path above is to set those two env vars in the worker/Nautobot environment:

```bash
export NAUTOBOT_SSOT_PROXMOX_TOKEN_ID="root@pam!nautobot"
export NAUTOBOT_SSOT_PROXMOX_TOKEN_SECRET="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

[nb-secret]: https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/secret/
[nb-secretsgroup]: https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/secret/#secrets-groups
[nb-extint]: https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/externalintegration/

## Configuration reference

!!! note "Defaults are sufficient — overrides are optional"
    Every field below ships with a sensible default, and the auto-created `ProxmoxConfigDefault`
    comes pre-populated with them. The **only values you must provide** are the Proxmox credentials
    and the instance's Remote URL (see [Authentication](#authentication)). Everything else — the
    status maps, the node interface type map, the SSoT tag, the default cluster/location/device
    objects, and the sync toggles — only needs changing if you want to override the default behavior.
    If the defaults suit you, leave these fields as-is.

The `SSOTProxmoxConfig` model exposes the following fields, all editable on its GUI page (**Apps →
Single Source of Truth → Proxmox VE Config**). Five of them (SSoT Tag, Default Cluster Type, Default
Location, Default Node Device Type, Default Node Device Role) are **object references** rendered as
dropdowns rather than free text — each points at an object `signals.py` pre-creates on first migrate,
so the pre-populated default is normally all you need:

| Field | Default | Purpose |
| ----- | ------- | ------- |
| **Sync to Nautobot** (`enable_sync_to_nautobot`) | `True` | Allow syncing data from Proxmox VE into Nautobot. Required for the config to appear in the job. |
| **Enabled for Sync Job** (`job_enabled`) | `False` | Make this config selectable in the sync job. Enable it before running. |
| **Use Clusters** (`use_clusters`) | `True` | Place VMs in their Proxmox cluster. If `False`, all VMs go in the default cluster. |
| **Sync LXC Containers** (`sync_lxc`) | `True` | Include LXC containers as Virtual Machines (in addition to QEMU VMs). |
| **Sync Nodes as Devices** (`sync_nodes_as_devices`) | `True` | Model Proxmox nodes as Nautobot Devices and link VMs to their host node. |
| **Sync Proxmox VE Tags** (`sync_proxmox_tags`) | `True` | Copy Proxmox VE tags onto Nautobot Virtual Machines as Tags. |
| **SSoT Tag** (`default_ssot_tag`) | Tag named "SSoT Synced from Proxmox" (pre-created) | Dropdown selecting the marker tag applied to every synced object. Also identifies which objects the integration manages (and may delete) — see [Limitations](../../user/integrations/proxmox.md#limitations). Edit the Tag object itself to change its name/description. |
| **VM status map** (`default_vm_status_map`) | see [The three JSON map fields](#the-three-json-map-fields) | Map Proxmox VM states to Nautobot Status names. |
| **IP status map** (`default_ip_status_map`) | see [The three JSON map fields](#the-three-json-map-fields) | Map IP states to Nautobot Status names. |
| **Node interface type map** (`default_node_interface_type_map`) | see [The three JSON map fields](#the-three-json-map-fields) | Map Proxmox node interface types to Nautobot DCIM interface types. |
| **Primary IP Sort Logic** (`primary_ip_sort_by`) | `Lowest` | How to choose a VM's primary IP when several are present. |
| **Ignore Link Local** (`default_ignore_link_local`) | `True` | Ignore link-local / APIPA addresses on VM interfaces. |
| **Default Cluster Group Name** (`default_clustergroup_name`) | `Proxmox VE Default Cluster Group` | Name given to the ClusterGroup created on first sync to group synced clusters. Free text — the sync creates it if it doesn't exist yet. |
| **Default Cluster Name** (`default_cluster_name`) | `Proxmox VE Default Cluster` | Name given to the Cluster created on first sync when **Use Clusters** is disabled. Free text — the sync creates it if it doesn't exist yet. |
| **Default Cluster Type** (`default_cluster_type`) | ClusterType named "Proxmox VE" (pre-created) | Dropdown selecting the ClusterType assigned to synced clusters. |
| **Default Location** (`default_location`) | Location named "Proxmox VE Default Location" (pre-created) | Dropdown selecting the Location assigned to node Devices. |
| **Default Node Device Type** (`default_device_type`) | DeviceType named "Proxmox Node" (pre-created) | Dropdown selecting the DeviceType assigned to node Devices. |
| **Default Node Device Role** (`default_device_role`) | Role named "Proxmox Node" (pre-created) | Dropdown selecting the Role assigned to node Devices. |

### Full example configuration

`name`, `proxmox_instance`, and the 5 object-reference fields (SSoT Tag, Default Cluster Type,
Default Location, Default Node Device Type, Default Node Device Role) are required — every other
field defaults to the value shown in the table above. For reference, here's the minimal
`nautobot-server nbshell` equivalent of filling in just the required fields via the GUI, pointing each
object reference at the object `signals.py` already pre-created:

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
    # All other fields take their GUI defaults shown in the table above; pass any of them here to
    # override, e.g. job_enabled=True.
)
```

### The three JSON map fields

Three fields on `SSOTProxmoxConfig` are JSON maps rather than simple values. They are **not separate
files** — each is entered as JSON directly into its field on the Config GUI page (**Apps → Single
Source of Truth → Proxmox VE Config**), or via `nbshell`.

#### VM status map

`default_vm_status_map` maps Proxmox VM states (from `/cluster/resources`: `running`, `stopped`,
`paused`) to Nautobot `Status` names. Values must be names of Statuses that already exist — the
config validates this on save and rejects unknown statuses. The default statuses (`Active`,
`Offline`, `Suspended`, `Reserved`) are created automatically when the integration is enabled. The
map must be a non-empty dict. Default:

```json
{
    "running": "Active",
    "stopped": "Offline",
    "paused": "Suspended"
}
```

#### IP status map

`default_ip_status_map` maps IP states to Nautobot `Status` names. Keys must be exactly `PREFERRED`
and `UNKNOWN` (both required, no other keys allowed); values must be names of existing Statuses.
Default:

```json
{
    "PREFERRED": "Active",
    "UNKNOWN": "Reserved"
}
```

#### Node interface type mapping

Proxmox's API does not report a node interface's link speed, so `default_node_interface_type_map`
maps each Proxmox interface type to a Nautobot DCIM interface type. Any Proxmox type not present in
the map falls back to `other`. Keys must be one of the known Proxmox interface types (`eth`, `bond`,
`OVSBond`, `bridge`, `OVSBridge`, `vlan`) and values must be valid Nautobot interface-type slugs; the
config is rejected on save otherwise. Default:

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

Override it if your hardware differs — for example, to map physical NICs to 10G instead of the
`1000base-t` default:

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

The integration creates and relies on a fixed set of Nautobot objects with stable names/keys
(defined in `nautobot_ssot/integrations/proxmox/constants.py`). These are useful when filtering,
reporting, or writing automation against the synced data — for example, to find everything the
integration manages, filter on the SSoT tag below.

| Purpose | Type | Name / key |
| :------ | :--- | :--------- |
| Marks every synced object | Tag | **SSoT Synced from Proxmox** (default; select a different Tag via `default_ssot_tag`) |
| Date/time of the last sync | Custom field (Date/Time, minute precision) | key `last_synced_from_proxmox_on` ("Last synced from Proxmox on") |
| Links a VM to its host node | Relationship (Device → VM, one-to-many) | label **Proxmox VM Host**, key `proxmox_vm_host` |
| Node PVE version | Device custom field (Text) | key `proxmox_pve_version` |
| Node CPU count | Device custom field (Integer) | key `proxmox_cpu_count` |
| Node memory (GB) | Device custom field (Integer) | key `proxmox_memory_gb` |
| Cluster type for Proxmox clusters | ClusterType | **Proxmox VE** |
