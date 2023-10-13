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

| `Setting` | `Description` |
| --------- | ------------- |
| `ipfabric_host` | Hostname/IP address of the IPFabric instance. |
| `ipfabric_api_token` | API token for IPFabric authentication. |
| `ipfabric_ssl_verify` | Verify the SSL certificate of the IPFabric instance. |
| `nautobot_host` | FQDN of your Nautobot instance. This is used to provide a URL to the job results via ChatOps. |

Below is an example snippet from `nautobot_config.py` that demonstrates how to enable and configure IPFabric integration:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_ipfabric": True,
        "ipfabric_api_token": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_API_TOKEN"),
        "ipfabric_host": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_HOST"),
        "ipfabric_ssl_verify": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_SSL_VERIFY"),
        "nautobot_host": os.environ.get("NAUTOBOT_HOST"),
    }
}
```

### Optional Settings

| `Setting` | `Description` | `Default` |
| --------- | ------------- | ---------- |
| `ipfabric_timeout` | Timeout (in seconds) for API requests to IPFabric. | `15` |
| `ipfabric_allow_duplicate_addresses` | If an IP Address already exists, setting this flag to `False` will prevent a duplicate IP Address from being created and will instead assign the existing IP to the synced Interface. | `True` |
| `ipfabric_default_device_role` | The device role used if a matching role is not found. | `Network Device` |
| `ipfabric_default_device_role_color` | The color used for the default device role. | `ff0000` |
| `ipfabric_default_device_status` | The status of the synced device used if a matching status is not found. | `Active` |
| `ipfabric_default_device_status_color` | The color used for the default status. | `ff0000` |
| `ipfabric_default_interface_mac` | The MAC used for an interface when no MAC is found in IPFabric. | `00:00:00:00:00:01` |
| `ipfabric_default_interface_mtu` | The MTU used for an interface when no MTU is found in IPFabric. | `1500` |
| `ipfabric_default_interface_type` | The Interface type used for interfaces synced. | `1000base-t` |
| `ipfabric_safe_delete_device_status` | The status that is set for a Device when the `Safe Delete Mode` flag is set in the Job. | `Offline` |
| `ipfabric_safe_delete_site_status` | The status that is set for a Site when the `Safe Delete Mode` flag is set in the Job. | `Decommissioning` |
| `ipfabric_safe_delete_vlan_status` | The status that is set for a VLAN when the `Safe Delete Mode` flag is set in the Job. | `Deprecated` |
| `ipfabric_safe_delete_ipaddress_status` | The status that is set for an IP Address when the `Safe Delete Mode` flag is set in the Job. | `Deprecated` |


Below is an example snippet from `nautobot_config.py` that demonstrates how to enable and configure the IPFabric SSoT integration along with the optional settings:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_ipfabric": True,
        "ipfabric_api_token": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_API_TOKEN"),
        "ipfabric_host": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_HOST"),
        "ipfabric_ssl_verify": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_SSL_VERIFY"),
        "nautobot_host": os.environ.get("NAUTOBOT_HOST"),
        "ipfabric_timeout": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_TIMEOUT"),
        "ipfabric_allow_duplicate_addresses": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_DUPLICATE_ADDRESSES"),
        "ipfabric_default_device_role": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_DEVICE_ROLE"),
        "ipfabric_default_device_status": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_DEVICE_STATUS"),
        "ipfabric_default_interface_mac": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_INTERFACE_MAC"),
        "ipfabric_default_interface_mtu": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_INTERFACE_MTU"),
        "ipfabric_default_interface_type": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_INTERFACE_TYPE"),
        "ipfabric_safe_delete_device_status": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_DEVICE_DELETE_STATUS"),
        "ipfabric_safe_delete_site_status": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_SITE_DELETE_STATUS"),
        "ipfabric_safe_delete_vlan_status": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_VLAN_DELETE_STATUS"),
        "ipfabric_safe_delete_ipaddress_status": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_IPADDRESS_DELETE_STATUS"),
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
            "ipfabric_api_token": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_API_TOKEN"),
            "ipfabric_host": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_HOST"),
            "ipfabric_ssl_verify": os.environ.get("NAUTOBOT_SSOT_IPFABRIC_SSL_VERIFY"),
            "nautobot_host": os.environ.get("NAUTOBOT_HOST"),
        }
    }
    ```
!!! warning
    The setting names have been updated to help avoid any potential conflicts, please update the settings in `PLUGINS_CONFIG` accordingly.