# LibreNMS

## Description

This App will sync data from the LibreNMS API into Nautobot to create Device and IPAM inventory items. Most items will receive a custom field associated with them called "System of Record", which will be set to "LibreNMS" (or whatever you set the `NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD` environment variable to). These items are then the only ones managed by the LibreNMS SSoT App. Other items within the Nautobot instance will not be affected unless there's items with overlapping names. If an item exists in Nautobot by it's identifiers but it does not have the "System of Record" custom field on it, the item will be updated with "LibreNMS" (or `NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD` environment variable value) when the App runs. This way no duplicates are created, and the App will not delete any items that are not defined in the LibreNMS API data but were manually created in Nautobot.

## Installation

Before configuring the integration, please ensure, that `nautobot-ssot` app was [installed with LibreNMS integration extra dependencies](../install.md#install-guide).

```shell
pip install nautobot-ssot[librenms]
```

## Configuration

Once the SSoT package has been installed you simply need to enable the integration by setting `enable_librenms` to True. The `librenms_geocode_api_key` will give additional lookups to find City/State information based on GPS coordinates (if available/defined in LibreNMS) for Locations sync'd from LibreNMS. By default there are limits on how many queries can be performed so it might take a couple of job runs to get all the information into Nautobot.

```python
PLUGINS = ["nautobot_ssot"]

PLUGINS_CONFIG = {
  "nautobot_ssot": {
        # Other nautobot_ssot settings ommitted.
        "enable_librenms": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_LIBRENMS", "true")),
        "librenms_geocode_api_key": os.getenv("NAUTOBOT_SSOT_LIBRENMS_GEOCODE_API_KEY", ""),
  }
}
```

### External Integrations

#### LibreNMS as DataSource

The way you add your LibreNMS server instance is through the "External Integrations" objects in Nautobot. First, create a secret in Nautobot with your LibreNMS API token using an Environment Variable (or sync via secrets provider). Then create a SecretsGroup object and select the Secret you just created and set the Access Type to `HTTP(S)` and the Secret Type to `Token`.

Once this is created, go into the Extensibility Menu and select `External Integrations`. Add an External Intergration with the Remote URL being your LibreNMS server URL (including http(s)://), set the method to `GET`, and select any other headers/settings you might need for your specific instance. Select the secrets group you created as this will inject the API token. Once created, you will select this External Integration when you run the LibreNMS to Nautobot SSoT job.

#### LibreNMS as DataTarget

NotYetImplemented

### LibreNMS API

An API key with global read-only permissions is the minimum needed to sync information from LibreNMS.
