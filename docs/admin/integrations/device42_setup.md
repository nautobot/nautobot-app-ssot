# Device42 Integration Setup

This guide will walk you through steps to set up Device42 integration with the `nautobot_ssot` app.

## Prerequisites

Before configuring the integration, please ensure, that `nautobot-ssot` app was [installed with Device42 integration extra dependencies](../install.md#install-guide).

```shell
pip install nautobot-ssot[device42]
```

## Configuration

Integration behavior can be controlled with the following settings:

| Configuration Variable | Type    | Usage                                                                                                 |
| ---------------------- | ------- | ----------------------------------------------------------------------------------------------------- |
| device42_host          | string  | This defines the FQDN of the Device42 instance, ie `https://device42.example.com`.                    |
| device42_username      | string  | This defines the username of the account used to connect to the Device42 API endpoint.                |
| device42_password      | string  | This defines the password of the account used to connect to the Device42 API endpoint.                |
| device42_verify        | boolean | This denotes whether SSL validation of the Device42 endpoint should be enabled or not.                |

When creating Sites and Racks in Nautobot it is required to define a Status for each. It is also required to define a Role for your Device when created. You may define the default for each of those objects being imported with the respective values in your `nautobot_config.py` file.

| Configuration Variable                              | Type   | Usage                                                      | Default              |
| --------------------------------------------------- | ------ | ---------------------------------------------------------- | -------------------- |
| device42_defaults["site_status"]                    | string | Default status for Sites synced to Nautobot.               | Active               |
| device42_defaults["rack_status"]                    | string | Default status for Racks synced to Nautobot.               | Active               |
| device42_defaults["device_role"]                    | string | Default role for Devices synced to Nautobot.               | Unknown              |

When syncing from Device42, the integration will create new Devices that do not exist in Nautobot and delete any that are not in Device42. This behavior can be controlled with the `device42_delete_on_sync` setting. This option prevents objects from being deleted from Nautobot during a synchronization. This is handy if your Device42 data fluctuates a lot and you wish to control what is removed from Nautobot. This means objects will only be added, never deleted when set to False. In addition, while syncing your Devices from Device42 you can enable the `device42_use_dns` setting to perform DNS resolution of Device hostname's when assigning management IP addresses. When True, there will be an additional process of performing DNS queries for each Device in the sync and if an A record is found, will be assigned as management IP for the Device. It will attempt to use the interface for the IP based upon data from Device42 but will create a Management interface and assign the IP to it if an interface can't be determined.

| Configuration Variable                              | Type    | Usage                                                                        | Default              |
| --------------------------------------------------- | ------- | ---------------------------------------------------------------------------- | -------------------- |
| device42_delete_on_sync                             | boolean | Devices in Nautobot that don't exist in Device42 will be deleted.            | False                |
| device42_use_dns                                    | boolean | Enables DNS resolution of Device name's for assigning primary IP addresses.  | False                |
| device42_customer_is_facility                       | boolean | True when  utilizing the Customer field in Device42 to denote the site code. | False                |

> When these variables are not defined in the app settings, the integration will use the default values mentioned.

Due to particular data points not being available in Device42 it was decided to utilize the tagging system as a secondary method of defining information. The 'device42_facility_prepend' setting defines the string that is expected on a Tag when determining a Building's site code. If a Building has a Tag that starts with `sitecode-` it will assume the remaining Tag is the facility code. Like the `device42_facility_prepend` option, the `device42_role_prepend` setting defines the string on a Tag that defines a Device's role. If a Device has a Tag that starts with `nautobot-` it will assume the remaining string is the name of the Device's role, such as `access-switch` for example. Lastly, there is the `device42_ignore_tag` setting that enables the specification of a Tag that when found on a Device will have it skipped from import.

| Configuration Variable                              | Type    | Usage                                                                        | Default              |
| --------------------------------------------------- | ------- | ---------------------------------------------------------------------------- | -------------------- |
| device42_facility_prepend                           | str     | Devices in Nautobot that don't exist in Device42 will be deleted.            | ""                   |
| device42_role_prepend                               | str     | Define DeviceRole using a Tag. Will use Tag starting with this string.       | ""                   |
| device42_ignore_tag                                 | str     | True when  utilizing the Customer field in Device42 to denote the site code. | ""                   |

Finally, there is the `device42_hostname_mapping` setting that enables the parsing of Device hostname's for codes that indicate the assigned Site using the site code. This option allows you to define a mapping of a regex pattern that defines a Device's hostname and which Site the Device should be assigned. This is helpful if the location information for Devices in Device42 is inaccurate and your Device's are named with the Site name or code in it. For example, if you have Device's called `DFW-access-switch`, you could map that as `{"^DFW.+": "dallas"}` where `dallas` is the slug form for your Site name.

| Configuration Variable     | Type        | Usage                                                      | Default |
| -------------------------- | ----------- | ---------------------------------------------------------- | ------- |
| device42_hostname_mapping  | List[dict]  | Define mapping of a hostname that indicate site.           | [{}]    |

> As the Device hostname is used as the identifier for Device objects any change in hostname implies a new Device and thus should trigger a deletion and creation of a new Device in Nautobot. For this reason, the hostname parsing feature is not done during updates and only at initial creation of the Device. If you need to correct the Site or Role for a Device after initial creation you will need to manually correct it or delete it and run the import Job again.

Below is an example snippet from `nautobot_config.py` that demonstrates how to enable and configure the Device42 integration:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_device42": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_DEVICE42")),
        "device42_host": os.getenv("NAUTOBOT_SSOT_DEVICE42_HOST", ""),
        "device42_username": os.getenv("NAUTOBOT_SSOT_DEVICE42_USERNAME", ""),
        "device42_password": os.getenv("NAUTOBOT_SSOT_DEVICE42_PASSWORD", ""),
        "device42_verify_ssl": False,
        "device42_defaults": {
            "site_status": "Active",
            "rack_status": "Active",
            "device_role": "Unknown",
        },
        "device42_delete_on_sync": False,
        "device42_use_dns": True,
        "device42_customer_is_facility": True,
        "device42_facility_prepend": "sitecode-",
        "device42_role_prepend": "nautobot-",
        "device42_ignore_tag": "",
        "device42_hostname_mapping": [],
    }
```

!!! note
    All integration settings are defined in the block above as an example. Only some will be needed as described above.
