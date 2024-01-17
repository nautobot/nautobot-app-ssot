# Infoblox Integration Setup

This guide will walk you through the steps to set up Infoblox integration with the `nautobot_ssot` app.

## Prerequisites

Before configuring the integration, please ensure, that `nautobot-ssot` app was [installed with the Infoblox integration extra dependencies](../install.md#install-guide).

```shell
pip install nautobot-ssot[infoblox]
```

## Configuration

Integration behavior can be controlled with the following settings:

| Setting                                    | Default | Description                                                            |
| ------------------------------------------ | ------- | ---------------------------------------------------------------------- |
| infoblox_url                               | N/A     | URL of the Infoblox instance to sync with.                             |
| infoblox_username                          | N/A     | The username to authenticate against Infoblox with.                    |
| infoblox_password                          | N/A     | The password to authenticate against Infblox with.                     |
| infoblox_verify_ssl                        | True    | Toggle SSL verification when syncing data with Infoblox.               |
| infoblox_wapi_version                      | v2.12   | The version of the Infoblox API.                                       |
| infoblox_enable_sync_to_infoblox           | False   | Add job to sync data from Nautobot into Infoblox.                      |
| infoblox_enable_rfc1918_network_containers | False   | Add job to sync network containers to Nautobot (top level aggregates). |
| infoblox_default_status                    | active  | Default Status to be assigned to imported objects.                     |
| infoblox_import_objects_ip_addresses       | False   | Import IP addresses from Infoblox to Nautobot.                         |
| infoblox_import_objects_subnets            | False   | Import subnets from Infoblox to Nautobot.                              |
| infoblox_import_objects_subnets_ipv6       | False   | Import IPv6 subnets from Infoblox to Nautobot.                         |
| infoblox_import_objects_vlan_views         | False   | Import VLAN views from Infoblox to Nautobot.                           |
| infoblox_import_objects_vlans              | False   | Import VLANs from Infoblox to Nautobot.                                |
| infoblox_import_subnets                    | N/A     | List of Subnets in CIDR string notation to filter import to.           |
| infoblox_network_view                      | N/A     | Only load IPAddresses from a specific Infoblox Network View.           |

Below is an example snippet from `nautobot_config.py` that demonstrates how to enable and configure Infoblox integration:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_infoblox": True,
        "infoblox_default_status": os.getenv("NAUTOBOT_SSOT_INFOBLOX_DEFAULT_STATUS", "active"),
        "infoblox_enable_rfc1918_network_containers": is_truthy(
            os.getenv("NAUTOBOT_SSOT_INFOBLOX_ENABLE_RFC1918_NETWORK_CONTAINERS")
        ),
        "infoblox_enable_sync_to_infoblox": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_ENABLE_SYNC_TO_INFOBLOX")),
        "infoblox_import_objects_ip_addresses": is_truthy(
            os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_OBJECTS_IP_ADDRESSES")
        ),
        "infoblox_import_objects_subnets": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_OBJECTS_SUBNETS")),
        "infoblox_import_objects_subnets_ipv6": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_OBJECTS_SUBNETS_IPV6")),
        "infoblox_import_objects_vlan_views": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_OBJECTS_VLAN_VIEWS")),
        "infoblox_import_objects_vlans": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_OBJECTS_VLANS")),
        "infoblox_import_subnets": os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_SUBNETS", "").split(","),
        "infoblox_password": os.getenv("NAUTOBOT_SSOT_INFOBLOX_PASSWORD"),
        "infoblox_url": os.getenv("NAUTOBOT_SSOT_INFOBLOX_URL"),
        "infoblox_username": os.getenv("NAUTOBOT_SSOT_INFOBLOX_USERNAME"),
        "infoblox_verify_ssl": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_VERIFY_SSL", True)),
        "infoblox_wapi_version": os.getenv("NAUTOBOT_SSOT_INFOBLOX_WAPI_VERSION", "v2.12"),
    }
}
```

!!! note
    All integration settings are defined in the block above as an example. Only some will be needed as described below.

## Upgrading from `nautobot-plugin-ssot-infoblox` App

!!! warning
    When upgrading from `nautobot-plugin-ssot-infoblox` app, it's necessary to [avoid conflicts](../upgrade.md#potential-apps-conflicts).

- Uninstall the old app:
    ```shell
    pip uninstall nautobot-plugin-ssot-infoblox
    ```
- Upgrade the app with required extras:
    ```shell
    pip install --upgrade nautobot-ssot[infoblox]
    ```
- Fix `nautobot_config.py` by removing `nautobot_ssot_infoblox` from `PLUGINS` and merging app configuration into `nautobot_ssot`:
    ```python
    PLUGINS = [
        "nautobot_ssot",
        # "infoblox"  # REMOVE THIS LINE
    ]

    PLUGINS_CONFIG = {
        # "nautobot_ssot_infoblox": {  REMOVE THIS APP CONFIGURATION
        #      MOVE CONFIGURATION TO `nautobot_ssot` SECTION AND UPDATE KEYS
        #     "NAUTOBOT_INFOBLOX_URL": os.getenv("NAUTOBOT_INFOBLOX_URL", ""),
        #     "NAUTOBOT_INFOBLOX_USERNAME": os.getenv("NAUTOBOT_INFOBLOX_USERNAME", ""),
        #     "NAUTOBOT_INFOBLOX_PASSWORD": os.getenv("NAUTOBOT_INFOBLOX_PASSWORD", ""),
        #     "NAUTOBOT_INFOBLOX_VERIFY_SSL": os.getenv("NAUTOBOT_INFOBLOX_VERIFY_SSL", "true"),
        #     "NAUTOBOT_INFOBLOX_WAPI_VERSION": os.getenv("NAUTOBOT_INFOBLOX_WAPI_VERSION", "v2.12"),
        #     "enable_sync_to_infoblox": False,
        #     "enable_rfc1918_network_containers": False,
        #     "default_status": "active",
        #     "infoblox_import_objects": {
        #         "vlan_views": os.getenv("NAUTOBOT_INFOBLOX_IMPORT_VLAN_VIEWS", True),
        #         "vlans": os.getenv("NAUTOBOT_INFOBLOX_IMPORT_VLANS", True),
        #         "subnets": os.getenv("NAUTOBOT_INFOBLOX_INFOBLOX_IMPORT_SUBNETS", True),
        #         "ip_addresses": os.getenv("NAUTOBOT_INFOBLOX_IMPORT_IP_ADDRESSES", True),
        #     },
        #     "infoblox_import_subnets": ["10.46.128.0/18", "192.168.1.0/24"],
        # }
        "nautobot_ssot": {
            # Enable Infoblox integration
            "enable_infoblox": True,
            # Following lines are moved from `nautobot_ssot_infoblox` and prefixed with `infoblox_`
            "infoblox_default_status": os.getenv("NAUTOBOT_SSOT_INFOBLOX_DEFAULT_STATUS", "active"),
            "infoblox_enable_rfc1918_network_containers": is_truthy(
                os.getenv("NAUTOBOT_SSOT_INFOBLOX_ENABLE_RFC1918_NETWORK_CONTAINERS")
            ),
            "infoblox_enable_sync_to_infoblox": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_ENABLE_SYNC_TO_INFOBLOX")),
            "infoblox_import_objects_ip_addresses": is_truthy(
                os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_OBJECTS_IP_ADDRESSES")
            ),
            "infoblox_import_objects_subnets": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_OBJECTS_SUBNETS")),
            "infoblox_import_objects_subnets_ipv6": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_OBJECTS_SUBNETS_IPV6")),
            "infoblox_import_objects_vlan_views": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_OBJECTS_VLAN_VIEWS")),
            "infoblox_import_objects_vlans": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_OBJECTS_VLANS")),
            "infoblox_import_subnets": os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_SUBNETS", "").split(","),
            "infoblox_password": os.getenv("NAUTOBOT_SSOT_INFOBLOX_PASSWORD"),
            "infoblox_url": os.getenv("NAUTOBOT_SSOT_INFOBLOX_URL"),
            "infoblox_username": os.getenv("NAUTOBOT_SSOT_INFOBLOX_USERNAME"),
            "infoblox_verify_ssl": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_VERIFY_SSL", True)),
            "infoblox_wapi_version": os.getenv("NAUTOBOT_SSOT_INFOBLOX_WAPI_VERSION", "v2.12"),
        }
    }
    ```

!!! note
    Configuration keys are prefixed with `infoblox_`.
