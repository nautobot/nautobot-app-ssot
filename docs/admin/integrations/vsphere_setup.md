# vSphere Integration Setup

This guide will walk you through the steps to set up vSphere integration with the `nautobot_ssot` app.

## Prerequisites

Before configuring the integration, please ensure that the `nautobot-ssot` app was [installed with the vSphere integration extra dependencies](../install.md#install-guide).

```shell
pip install nautobot-ssot[vsphere]
```
The integration with vSphere utilizes [External Integrations](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/externalintegration/?h=external) to specify your vSphere host information. To enable this integration, the only modification needed is to activate it in the nautobot_config.py file.

Below is an example snippet from `nautobot_config.py` that demonstrates how to enable the vSphere integration. 

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_vsphere": True,
    }
}
```

## Configuration

Configuration for the vSphere integration is defined in the instance of the `SSOTvSphereConfig` model. Multiple configuration instances are supported. Synchronization jobs take the `Config` parameter which specifies the configuration instance to use. 

To access integration configuration navigate to `Apps -> Installed Apps` and click on the cog icon in the `Single Source of Truth` entry. Then, in the table `SSOT Integration Configs` click on the `vSphere Configuration Instance` link. This will take you to the view where you can view/modify existing config insances or create new ones.

Configuration instances contain the below settings:

| Setting                       | Default                                                                        | Description                                                                                                   |
| :---------------------------- | :----------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------ |
| Name                          | N/A                                                                            | Unique name of the configuration instance.                                                                    |
| Description                   | N/A                                                                            | Description of the configuration instance.                                                                    |
| vSphere Instance Config       | N/A                                                                            | External Integration object describing remote vSphere instance.                                               |
| Enable for Sync Job           | False                                                                          | Allows this config to be used in the sync jobs.                                                               |
| Ignore Link Local             | True                                                                           | Ignore link local addresses when sycning from vSphere                                                         |
| Primary IP Sort Logic         | Lowest                                                                         | The logic used to assign the Primary IP to a Virtual Machine                                                  |
| Use Clusters                  | True                                                                           | Sync Cluster and ClusterGroups from vSphere. If set to False, a default Cluster and Clust Group will be used. |
| Sync to Nautobot              | True                                                                           | Allows this config to be used in the job syncing from vSphere to Nautobot                                     |
| Sync Tagged Only              | True                                                                           | Only take into consideration tagged VMs (on the Nautobot side) when performing the sync.                      |
| Virtual Machine Status Map    | `{"POWERED_OFF": "Offline", "POWERED_ON": "Active", "SUSPENDED": "Suspended"}` | Maps vSphere Virtual Machine status to Nautobot status.                                                       |
| Virtual Machine IP Status Map | `{"PREFERRED": "Active", "UNKNOWN": "Reserved"}`                               | Maps vSphere IP status to Nautobot status                                                                     |
| Virtual Machine Interface Map | `{"CONNECTED": true, "NOT_CONNECTED": false}`                                  | Maps vSphere interface state to boolean values.                                                               |
| Default Cluster Group Name    | vSphere Default Cluster Group                                                  | Denotes the default Cluster Group name used in the sync if `Use Clusters` is set to False.                    |
| Default Cluster Name          | vSphere Default Cluster                                                        | Denotes the default Cluster name used in the sync if `Use Clusters` is set to Fals.e.                         |
| Default Cluster Type          | VMWare vSphere                                                                 | Denotes the default Cluster Type to set in the sync.                                                          |

Each vSphere configuration must be linked to an [External integration](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/externalintegration/?h=external+int) describing the vSphere instance. The following External Integration fields must be defined for integration to work correctly:

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

Virtual Machine Status Map is a mandatory setting used to map the status of a machine in vSphere to a Status in Nautobot.

```json
{
    "POWERED_OFF": "Offline",
    "POWERED_ON": "Active",
    "SUSPENDED": "Suspended"
}
```

The default value says that the status of `POWERED_OFF` translates to the `Offline` status in Nautobot, `POWERED_ON` to the `Active` status in Nautobot and `SUSPENDED` to the `Suspended` status in Nautobot.

> Note: Installation of the vSphere integration will ensure that the above 3 Statuses exist. If you change this setting, you will have to ensure that the Nautobot Status you are mapping to has already been created. It is highly recommended to leave the default settings here.

### Configuring Virtual Machine IP Status Map

Virtual Machine IP Status Map is a mandatory setting used to map the status of and IP address in vSphere to a Status in Nautobot.

```json
{
    "PREFERRED": "Active",
    "UNKNOWN": "Reserved"
}
```

The default maps the `PREFERRED` and `UNKNOWN` states from vSphere to the `Active` and `Reserved`, respectively. 

> Note: Installation of the vSphere integration will ensure that the above 2 Statuses exist. If you change this setting, you will have to ensure that the Nautobot Status you are mapping to has already been created. It is highly recommended to leave the default settings here.

### Configuring Virtual Machine Interface Status Map

Virtual Machine Interface Status Map is a mandatory setting used to map the status of an Interface in vSphere to a Status in Nautobot.

```json
{
    "CONNECTED": true,
    "NOT_CONNECTED": false
}
```
> Note: Installation of the vSphere integration will ensure that the above 2 Statuses exist. If you change this setting, you will have to ensure that the Nautobot Status you are mapping to has already been created. It is highly recommended to leave the default settings here.
## Custom Fields, Statuses and Tags

The vSphere Integration requires the following Nautobot Custom Fields and Tags to function correctly. These are created automatically when Nautobot is started and care should be taken to ensure these are not deleted. 

### Custom Fields

`Last Synced From vSphere` - Records the last date an object was synced from vSphere.

### Statuses

`Suspended` - Created to align with the default `SUSPENDED` value in the Virtual Machine Status Map.

### Tags

`SSoT Synced from vSphere` - Tag to assign to objects if that Object was synced from vSphere at some point.