# vSphere Integration Setup

This guide will walk you through the steps to set up vSphere integration with the `nautobot_ssot` app.

## Prerequisites

Before configuring the integration, please ensure, that `nautobot-ssot` app was [installed with the vSphere integration extra dependencies](../install.md#install-guide).

```shell
pip install nautobot-ssot[vsphere]
```

Below is an example snippet from `nautobot_config.py` that demonstrates how to enable the vSphere integration:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_vsphere": True,
    }
}
```

## Configuration

Integration configuration is deinfed in the instance of the `SSOTvSphereConfig` model. Multiple configuration instances are supported. Synchronization jobs take the `Config` parameter which specifies the configuration instnace to use. 

To access integration configuration navigate to `Apps -> Installed Apps` and click on the cog icon in the `Single Source of Truth` entry. Then, in the table `SSOT Integration Configs` click on the `vSphere Configuration Instance` link. This will take you to the view where youi can view/modify existing config insances or create new ones.

Configuration instances contain the below settings:

| Setting                       | Default                                                                        | Description                                                               |
| :---------------------------- | :----------------------------------------------------------------------------- | :------------------------------------------------------------------------ |
| Name                          | N/A                                                                            | Unique name of the configuration instance.                                |
| Description                   | N/A                                                                            | Description of the configuration instance.                                |
| vSphere Instance Config       | N/A                                                                            | External Integration object describing remote vSphere instance.           |
| Enable for Sync Job           | False                                                                          | Allows this config to be used in the sync jobs.                           |
| Sync to Nautobot              | True                                                                           | Allows this config to be used in the job syncing from vSphere to Nautobot |
| Primary IP Sort Logic         | Lowest                                                                         | The logic used to assign the Primary IP to a Virtual Machine              |
| Virtual Machine Status Map    | `{"POWERED_OFF": "Offline", "POWERED_ON": "Active", "SUSPENDED": "Suspended"}` | Maps vSphere Virtual Machine status to Nautobot status.                   |
| Virtual Machine IP Status Map | `{"PREFERRED": "Active", "UNKNOWN": "Reserved"}`                               | Maps vSPhere IP status to Nautobot status                                 |
| Virtual Machine Interface Map | `{"CONNECTED": true, "NOT_CONNECTED": false}`                                  | Maps vSphere interface state to boolean values.                           |

Each vShere configuration must be linked to an [External integrtion](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/externalintegration/?h=external+int) descrbing the vSphere instance. The following External Integration fields must be defined for integration to work correctly:

| Setting       | Description                                                                      |
| :------------ | :------------------------------------------------------------------------------- |
| Remote URL    | URL of the remote vSphere instance to sync with.                                 |
| Verify SSL    | Toggle SSL verification when sycning data with vSphere                           |
| Secrets Group | Secrets Group defining credentials used when connecting to the vSphere instance. |
| Timeout       | How long HTTP requests to vSphere should wait for a response before failing.     |

The Secrets Group linked to the vSphere External Integration must contain password and username secrets defined as per the below:

| Access Type | Secret Type |
| :---------- | :---------- |
| REST        | Password    |
| REST        | Username    |


### Configuring Virtual Machine Status Map

Virtual Machine Status Map is a mandatory setting used to map the status of a machine in vSphere to a status in Nautobot.

```json
{
    "POWERED_OFF": "Offline",
    "POWERED_ON": "Active",
    "SUSPENDED": "Suspended"
}
```

The default value says that the status of `POWERED_OFF` translates to the `Offline` status in Nautobot, `POWERED_ON` to the `Active` status in Nautobot and `SUSPENDED` to the `Suspended` status in Nautobot.

> Note: Installation of the vSphere integration with ensure that the above 3 statuses exist. If you change this setting, you will have to ensure that the Nautobot status you are mapping to has already been created.

### Configuring Virtual Machine IP Status Map

Virtual Machine IP Status Map is a mandatory setting used to map the status of and IP address in vSphere to a status in Nautobot.

```json
{
    "PREFERRED": "Active",
    "UNKNOWN": "Reserved"
}
```

The default maps the `PREFERRED` and `UNKNOWN` states from vSphere to the `Active` and `Reserved`, respectively. 

### Configuring Virtual Machine Interface Map

Virtual Machine Interface map is a mandatory setting used to map interface state to boolean values.

I STILL NEED TO FINISH THIS PART

## Custom Fields, Statuses and Tags

The vSphere Integration requires the following Nautobot custom fields and tags to function correctly. These are created automatically when Nautobot is started and care shoul dbe taken to ensure these are not deleted. 

### Custom Fields

`last_synced_from_vsphere` - Records the last date an object was synced from vSphere.

### Statuses

`Suspended` - Created to align with the default `SUSPENDED` value in the Virtual Machine Status Map.

### Tags

`SSoT Synced from vSphere` - Tag to assign to objects if that Object was synced from vSphere at some point.