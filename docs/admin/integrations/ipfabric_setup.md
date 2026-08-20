# IPFabric Integration Setup

This guide will walk you through steps to set up IPFabric integration with the `nautobot_ssot` app.

## Prerequisites

Before configuring the integration, please ensure, that `nautobot-ssot` app was [installed with the IPFabric integration extra dependencies](../install.md#install-guide).

```shell
pip install nautobot-ssot[ipfabric]
```

## Configuration

Integration behavior can be controlled with the following settings:

!!! warning
    The setting names have been updated to help avoid any potential conflicts, please update the settings in `PLUGINS_CONFIG` accordingly.

### Required Settings

| `Setting`             | `Description`                                                                                 |
|-----------------------|-----------------------------------------------------------------------------------------------|
| `ipfabric_host`       | Hostname/IP address of the IPFabric instance.                                                 |
| `ipfabric_api_token`  | API token for IPFabric authentication.                                                        |
| `ipfabric_ssl_verify` | Verify the SSL certificate of the IPFabric instance.                                          |
| `nautobot_host`       | FQDN of your Nautobot instance. This is used to provide a URL to the job results via ChatOps. |

Below is an example snippet from `nautobot_config.py` that demonstrates how to enable and configure IPFabric integration:

```python
import os
from nautobot.core.settings_funcs import is_truthy

PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_ipfabric": True,
        "ipfabric_api_token": os.getenv("NAUTOBOT_SSOT_IPFABRIC_API_TOKEN"),
        "ipfabric_host": os.getenv("NAUTOBOT_SSOT_IPFABRIC_HOST"),
        "ipfabric_ssl_verify": is_truthy(os.getenv("NAUTOBOT_SSOT_IPFABRIC_SSL_VERIFY", "true")),
        "nautobot_host": os.getenv("NAUTOBOT_HOST"),
    }
}
```

### Optional Settings

| `Setting`                               | `Description`                                                                                                                                                                                 | `Default`           |
|-----------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------|
| `ipfabric_timeout`                      | Timeout (in seconds) for API requests to IPFabric.                                                                                                                                            | `15`                |
| `ipfabric_default_device_role`          | The device role used if a matching role is not found.                                                                                                                                         | `Network Device`    |
| `ipfabric_default_device_role_color`    | The color used for the default device role.                                                                                                                                                   | `ff0000`            |
| `ipfabric_sync_ipf_dev_type_to_role`    | Whether to use the IP Fabric Device Type to sync to the Nautobot Device Role field; if disabled new devices will use `ipfabric_default_device_role` and updates to the field will be skipped. | `True`              |
| `ipfabric_default_device_status`        | The status of the synced device used if a matching status is not found.                                                                                                                       | `Active`            |
| `ipfabric_default_device_status_color`  | The color used for the default status.                                                                                                                                                        | `ff0000`            |
| `ipfabric_default_interface_mac`        | The MAC used for an interface when no MAC is found in IPFabric.                                                                                                                               | `00:00:00:00:00:01` |
| `ipfabric_default_interface_mtu`        | The MTU used for an interface when no MTU is found in IPFabric.                                                                                                                               | `1500`              |
| `ipfabric_default_interface_type`       | The Interface type used for interfaces synced.                                                                                                                                                | `1000base-t`        |
| `ipfabric_default_cable_status`         | The status used for Cables synced from the connectivity matrix.                                                                                                                               | `Connected`         |
| `ipfabric_safe_delete_device_status`    | The status that is set for a Device when the `Safe Delete Mode` flag is set in the Job.                                                                                                       | `Offline`           |
| `ipfabric_safe_delete_location_status`  | The status that is set for a Location when the `Safe Delete Mode` flag is set in the Job.                                                                                                     | `Decommissioning`   |
| `ipfabric_safe_delete_vlan_status`      | The status that is set for a VLAN when the `Safe Delete Mode` flag is set in the Job.                                                                                                         | `Deprecated`        |
| `ipfabric_safe_delete_ipaddress_status` | The status that is set for an IP Address when the `Safe Delete Mode` flag is set in the Job.                                                                                                  | `Deprecated`        |
| `ipfabric_safe_delete_cable_status`     | The status that is set for a Cable when the `Safe Delete Mode` flag is set in the Job.                                                                                                        | `Decommissioning`   |
| `ipfabric_use_canonical_interface_name` | Whether to attempt to elongate interface names as found in IP Fabric.                                                                                                                         | `False`             |
| `ipfabric_sync_<object type>`           | Pre-selects an object type on the Job form. See [Choosing what to sync](#choosing-what-to-sync).                                                                                              | Varies by type      |
| `ipfabric_disabled_sync_objects`        | Object types that may not be selected on the Job form at all. See [Choosing what to sync](#choosing-what-to-sync).                                                                            | `[]`                |


Below is an example snippet from `nautobot_config.py` that demonstrates how to enable and configure the IPFabric SSoT integration along with the optional settings:

```python
import os
from nautobot.core.settings_funcs import is_truthy

PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_ipfabric": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_IPFABRIC", "true")),
        "ipfabric_api_token": os.getenv("NAUTOBOT_SSOT_IPFABRIC_API_TOKEN"),
        "ipfabric_host": os.getenv("NAUTOBOT_SSOT_IPFABRIC_HOST"),
        "ipfabric_ssl_verify": is_truthy(os.getenv("NAUTOBOT_SSOT_IPFABRIC_SSL_VERIFY", "true")),
        "nautobot_host": os.getenv("NAUTOBOT_HOST"),
        "ipfabric_timeout": os.getenv("NAUTOBOT_SSOT_IPFABRIC_TIMEOUT"),
        "ipfabric_default_device_role": os.getenv("NAUTOBOT_SSOT_IPFABRIC_DEVICE_ROLE"),
        "ipfabric_sync_ipf_dev_type_to_role": is_truthy(
            os.getenv("NAUTOBOT_SSOT_IPFABRIC_SYNC_IPF_DEV_TYPE_TO_ROLE", "true")
        ),
        "ipfabric_default_device_status": os.getenv("NAUTOBOT_SSOT_IPFABRIC_DEVICE_STATUS"),
        "ipfabric_default_interface_mac": os.getenv("NAUTOBOT_SSOT_IPFABRIC_INTERFACE_MAC"),
        "ipfabric_default_interface_mtu": os.getenv("NAUTOBOT_SSOT_IPFABRIC_INTERFACE_MTU"),
        "ipfabric_default_interface_type": os.getenv("NAUTOBOT_SSOT_IPFABRIC_INTERFACE_TYPE"),
        "ipfabric_default_cable_status": os.getenv("NAUTOBOT_SSOT_IPFABRIC_CABLE_STATUS"),
        "ipfabric_safe_delete_device_status": os.getenv("NAUTOBOT_SSOT_IPFABRIC_DEVICE_DELETE_STATUS"),
        "ipfabric_safe_delete_location_status": os.getenv("NAUTOBOT_SSOT_IPFABRIC_LOCATION_DELETE_STATUS"),
        "ipfabric_safe_delete_vlan_status": os.getenv("NAUTOBOT_SSOT_IPFABRIC_VLAN_DELETE_STATUS"),
        "ipfabric_safe_delete_ipaddress_status": os.getenv("NAUTOBOT_SSOT_IPFABRIC_IPADDRESS_DELETE_STATUS"),
        "ipfabric_safe_delete_cable_status": os.getenv("NAUTOBOT_SSOT_IPFABRIC_CABLE_DELETE_STATUS"),
        "ipfabric_use_canonical_interface_name": is_truthy(
            os.getenv("NAUTOBOT_SSOT_USE_CANONICAL_INTERFACE_NAME", "true")
        ),
        "ipfabric_sync_cables": is_truthy(os.getenv("NAUTOBOT_SSOT_IPFABRIC_SYNC_CABLES", "false")),
        # For example, ["primary_ip"] to remove it from the Job form entirely.
        "ipfabric_disabled_sync_objects": [],
    }
}
```

!!! note
    All integration settings are defined in the block above as an example. Only some will be needed as described below.

## Upgrading from `nautobot-plugin-ssot-ipfabric` App

!!! warning
    When upgrading from `nautobot-plugin-ssot-ipfabric` app, it's necessary to [avoid conflicts](../upgrade.md#potential-apps-conflicts).

- Uninstall the old app:
    ```shell
    pip uninstall nautobot-plugin-ssot-ipfabric
    ```
- Upgrade the app with required extras:
    ```shell
    pip install --upgrade nautobot-ssot[ipfabric]
    ```
- Fix `nautobot_config.py` by removing `nautobot_ssot_ipfabric` from `PLUGINS` and merging app configuration into `nautobot_ssot`:
    ```python
    import os
    from nautobot.core.settings_funcs import is_truthy

    PLUGINS = [
        "nautobot_ssot",
        # "nautobot_ssot_ipfabric"  # REMOVE THIS LINE
    ]

    PLUGINS_CONFIG = {
        # "nautobot_ssot_ipfabric": {  REMOVE THIS APP CONFIGURATION
        #      MOVE CONFIGURATION TO `nautobot_ssot` SECTION
        #     "ipfabric_api_token": os.environ.get("IPFABRIC_API_TOKEN"),
        #     "ipfabric_host": os.environ.get("IPFABRIC_HOST"),
        #     "ipfabric_ssl_verify": os.environ.get("IPFABRIC_SSL_VERIFY"),
        #     "ipfabric_timeout": os.environ.get("IPFABRIC_TIMEOUT"),
        #     "nautobot_host": os.environ.get("NAUTOBOT_HOST"),
        # }
        "nautobot_ssot": {
            # Enable IPFabric integration
            "enable_ipfabric": True,
            # Following lines are moved from `nautobot_ssot_ipfabric`
            "ipfabric_api_token": os.getenv("NAUTOBOT_SSOT_IPFABRIC_API_TOKEN"),
            "ipfabric_host": os.getenv("NAUTOBOT_SSOT_IPFABRIC_HOST"),
            "ipfabric_ssl_verify": is_truthy(os.getenv("NAUTOBOT_SSOT_IPFABRIC_SSL_VERIFY", "true")),
            "nautobot_host": os.getenv("NAUTOBOT_HOST"),
        }
    }
    ```

!!! warning
    The setting names have been updated to help avoid any potential conflicts, please update the settings in `PLUGINS_CONFIG` accordingly.

## Choosing what to sync

The Job form carries a checkbox per object type, so a run can be narrowed to the data an
installation actually wants IP Fabric to own. Deselecting a type keeps it out of the sync in both
directions: it is neither read from IP Fabric nor read from Nautobot, so existing Nautobot records
of that type are left untouched rather than treated as absent from the source and removed.

| Object type    | Job field            | Default | Requires       |
|----------------|----------------------|---------|----------------|
| `locations`    | `Sync Locations`     | On      |                |
| `interfaces`   | `Sync Interfaces`    | On      |                |
| `ip_addresses` | `Sync IP Addresses`  | On      | `interfaces`   |
| `primary_ip`   | `Sync Primary IP`    | On      | `ip_addresses` |
| `vlans`        | `Sync VLANs`         | On      |                |
| `cables`       | `Sync Cables`        | Off     | `interfaces`   |

Devices are always synced. Every other object type is either a Device or hangs off one, so a run with
Devices excluded would have nothing left to do.

### Locations

Locations are the root of the object tree: every Device and VLAN belongs to one. Deselecting them
therefore does not stop Locations being *read* — it stops them being *written*. No Location is
created, updated or deleted, and the `ipfabric_site_id` custom field is left alone, but Devices at
Locations that already exist in Nautobot still sync normally.

Two consequences follow from that, both of which are the point rather than a limitation:

- **A site IP Fabric has discovered is not created**, and neither are the Devices at it. There is no
  Location for them to belong to, so the whole site is skipped.
- **A Nautobot Location that IP Fabric does not report is left completely alone**, including the
  Devices at it. With Locations out of scope the sync holds no opinion about which sites exist, so it
  cannot treat a missing site as evidence that the Devices at it are gone. With Locations in scope,
  that same site and its Devices are deleted, subject to Safe Delete Mode.

Deselect Locations where another system owns the site list. Leave it selected — the default — to keep
the existing behaviour.

An object type is skipped when a type it requires is not selected, and the Job log says which
requirement was unmet. Selecting `Sync Cables` without `Sync Interfaces`, for example, syncs no
Cables, because a Cable can only be matched through the Interfaces it terminates on.

### Pre-selecting a type

`ipfabric_sync_<object type>` sets the initial state of a checkbox, for installations that want a
different starting point from the shipped default. It changes what the form offers, not what it
permits, so an operator can still override it for one run:

```python
"ipfabric_sync_cables": True,
```

### Disabling a type outright

`ipfabric_disabled_sync_objects` removes object types from the form altogether, for cases where
another system is authoritative and the answer must not vary run to run. A disabled type cannot be
re-enabled by an operator, by the REST API, or by a scheduled Job saved before it was disabled:

```python
"ipfabric_disabled_sync_objects": ["locations", "primary_ip"],
```

Disabling a type also disables everything that requires it, since those have nothing to attach to.
Every exclusion is reported in the Job log, so a run whose selections were overruled says so rather
than quietly doing less than asked.
