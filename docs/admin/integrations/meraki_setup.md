# Cisco Meraki Integration Setup

This guide will walk you through steps to set up Cisco Meraki integration with the `nautobot_ssot` app.

## Prerequisites

Before configuring the integration, please ensure, that `nautobot-ssot` app was [installed with Cisco Meraki integration extra dependencies](../install.md#install-guide).

```shell
pip install nautobot-ssot[meraki]
```

## Configuration

Connecting to a Meraki instance is handled through the Nautobot [Controller](https://docs.nautobot.com/projects/core/en/stable/development/core/controllers/) object. There is an expectation that you will create an [ExternalIntegration](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/externalintegration/) with the requisite connection information for your Meraki dashboard attached to that Controller object. All imported Devices will be associated to a [ControllerManagedDeviceGroup](https://docs.nautobot.com/projects/core/en/stable/user-guide/core-data-model/dcim/controllermanageddevicegroup/) that is found or created during each Job run. It will update the group name to be "<Controller name\> Managed Devices" if it exists. When running the Sync Job you will specify which Meraki Controller instance you wish to synchronize with along with other settings for the synchronization.

Below is an example snippet from `nautobot_config.py` that demonstrates how to enable the Meraki integration:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_meraki": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_MERAKI", "true")),
    }
}
```
