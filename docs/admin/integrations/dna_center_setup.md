# Cisco DNA Center Integration Setup

This guide will walk you through steps to set up Cisco DNA Center integration with the `nautobot_ssot` app.

## Prerequisites

Before configuring the integration, please ensure, that `nautobot-ssot` app was [installed with Cisco DNA Center integration extra dependencies](../install.md#install-guide).

```shell
pip install nautobot-ssot[dna_center]
```

## Configuration

Connecting to a DNA Center instance is handled through the Nautobot [Controller](https://docs.nautobot.com/projects/core/en/stable/development/core/controllers/) object. There is an expectation that you will create an [ExternalIntegration](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/externalintegration/) with the requisite connection information for your DNA Center instance attached to that Controller object. All imported Devices will be associated to a [ControllerManagedDeviceGroup](https://docs.nautobot.com/projects/core/en/stable/user-guide/core-data-model/dcim/controllermanageddevicegroup/) that is found or created during each Job run. It will update the group name to be "\<Controller name\> Managed Devices" if it exists. When running the Sync Job you will specify which DNA Center Controller instance you wish to synchronize with.  Other behaviors for the integration can be controlled with the following settings:

| Configuration Variable                              | Type    | Usage                                                      | Default              |
| --------------------------------------------------- | ------- | ---------------------------------------------------------- | -------------------- |
| dna_center_import_global                            | boolean | Whether to import Global area from DNA Center.             | True                 |
| dna_center_import_merakis                           | boolean | Whether to import Meraki devices from DNA Center.          | False                |
| dna_center_delete_locations                         | boolean | Whether to delete Locations during sync.                   | True                 |
| dna_center_update_locations                         | boolean | Whether to update Locations during sync.                   | True                 |
| dna_center_show_failures                            | boolean | Whether to show report of Devices that weren't loaded.     | True                 |

Below is an example snippet from `nautobot_config.py` that demonstrates how to enable and configure the DNA Center integration:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_dna_center": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_DNA_CENTER", "true")),
        "dna_center_import_global": is_truthy(os.getenv("NAUTOBOT_DNAC_SSOT_DNA_CENTER_IMPORT_GLOBAL", "true")),
        "dna_center_import_merakis": is_truthy(os.getenv("NAUTOBOT_DNAC_SSOT_DNA_CENTER_IMPORT_MERAKIS", "false")),
        "dna_center_delete_locations": is_truthy(os.getenv("NAUTOBOT_DNAC_SSOT_DNA_CENTER_DELETE_LOCATIONS", "true")),
        "dna_center_update_locations": is_truthy(os.getenv("NAUTOBOT_DNAC_SSOT_DNA_CENTER_UPDATE_LOCATIONS", "true")),
        "dna_center_show_failures": is_truthy(os.getenv("NAUTOBOT_DNAC_SSOT_DNA_CENTER_SHOW_FAILURES", "true")),
    }
}
```

!!! note
    All integration settings are defined in the block above as an example. Only some will be needed as described above.
