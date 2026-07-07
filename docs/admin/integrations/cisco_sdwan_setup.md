# Cisco SD-WAN Integration Setup

This guide will walk you through steps to set up the Cisco SD-WAN integration with the `nautobot_ssot` app. This integration synchronizes data from a Cisco Catalyst SD-WAN Manager (formerly vManage) into Nautobot.

## Prerequisites

Before configuring the integration, please ensure, that the `nautobot-ssot` app was [installed with the Cisco SD-WAN integration extra dependencies](../install.md#install-guide).

```shell
pip install nautobot-ssot[cisco_sdwan]
```

## Configuration

Connecting to a Cisco Catalyst SD-WAN Manager instance is handled through the Nautobot [Controller](https://docs.nautobot.com/projects/core/en/stable/development/core/controllers/) object. There is an expectation that you will create an [ExternalIntegration](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/externalintegration/) with the requisite connection information for your SD-WAN Manager instance attached to that Controller object:

1. Create a [Secrets Group](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/secret/#secrets-groups) with two secrets of access type `HTTP(S)`: one of secret type `Username` and one of secret type `Password`, holding the SD-WAN Manager credentials.
2. Create an ExternalIntegration with the `Remote URL` of your SD-WAN Manager (for example `https://vmanage.example.com`), the Secrets Group from the previous step, and the desired `Verify SSL` setting.
3. Create a Controller representing the SD-WAN Manager and assign the ExternalIntegration to it.
4. Create a [ControllerManagedDeviceGroup](https://docs.nautobot.com/projects/core/en/stable/user-guide/core-data-model/dcim/controllermanageddevicegroup/) associated with the Controller. Imported Devices are added to this group, and the group scopes which Nautobot Devices the Job considers during the synchronization.

The integration is enabled with the `enable_cisco_sdwan` setting. In addition, the integration **requires** the SSoT metadata feature to be enabled for its Job via the `enable_metadata_for` setting. The metadata records which objects were last synchronized by the integration, and the Job uses it to scope shared objects (DeviceTypes and SoftwareVersions) to those it manages.

Below is an example snippet from `nautobot_config.py` that demonstrates how to enable and configure the Cisco SD-WAN integration:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_cisco_sdwan": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_CISCO_SDWAN", "true")),
        "enable_metadata_for": ["CiscoSdwanDataSource"],
    }
}
```

Other behaviors for the integration can be controlled with the following settings:

| Configuration Variable                       | Type    | Usage                                                                                                     | Default                              |
| -------------------------------------------- | ------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| cisco_sdwan_default_interface_status         | string  | Status assigned to imported Interfaces.                                                                    | "Active"                             |
| cisco_sdwan_default_interface_type           | string  | Interface type assigned to imported Interfaces.                                                            | "other"                              |
| cisco_sdwan_default_ipaddress_status         | string  | Status assigned to imported IP Addresses.                                                                  | "Active"                             |
| cisco_sdwan_device_retired_status            | string  | Status assigned to Devices removed from SD-WAN instead of deleting them.                                   | "Retired"                            |
| cisco_sdwan_excluded_interfaces              | list    | Interface names to exclude from the import.                                                                | ["Loopback65528", "Loopback65529"]   |
| cisco_sdwan_excluded_prefixes                | list    | IP addresses within these prefixes are excluded from the import.                                           | ["169.254.0.0/16"]                   |
| cisco_sdwan_if_up_states                     | list    | SD-WAN admin states that mark an Interface as enabled.                                                     | ["if-state-up", "up"]                |
| cisco_sdwan_null_ip_addresses                | list    | SD-WAN IP address values to treat as undefined.                                                            | ["-", "0.0.0.0"]                     |
| cisco_sdwan_null_mtu_values                  | list    | SD-WAN MTU values to treat as undefined.                                                                   | ["0"]                                |
| cisco_sdwan_primary_ip_interfaces            | list    | Interface names whose IP address is set as the Device's primary IPv4 address.                              | ["sdwan-system-intf"]                |
| cisco_sdwan_software_version_platform_name   | string  | Name of the Platform that imported SoftwareVersions are associated with. Only set this when SoftwareVersions should use a different Platform than the one assigned to imported Devices; by default the Job's Device Platform is used. | None (the Job's Device Platform) |

!!! note
    The default interface exclusions (`Loopback65528`, `Loopback65529`) are loopbacks used internally by Cisco SD-WAN devices. Extend the `cisco_sdwan_excluded_prefixes` list with any address ranges (for example transport or management ranges) that you do not want imported into Nautobot.
