## Usage

## Configuration

The LibreNMS integration supports several configuration options that can be set in your `nautobot_config.py` file:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `librenms_permitted_values` | dict | `{"role": ["network"]}` | Controls which device roles from LibreNMS are allowed to be imported into Nautobot. Only devices with roles listed in the `role` array will be synchronized. |
| `librenms_allow_ip_hostnames` | boolean | `false` | Whether to allow devices with IP addresses as hostnames to be imported. |
| `librenms_show_failures` | boolean | `true` | Whether to display detailed information about devices that failed to import. |

### Example Configuration

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_librenms": True,
        "librenms_permitted_values": {
            "role": ["network", "access", "core", "distribution"],
        },
        "librenms_allow_ip_hostnames": False,
        "librenms_show_failures": True,
    }
}
```

## Process

### Shared Job Options

- Debug: Additional Logging
- Librenms Server: External integration object pointing to the required LibreNMS instance.
- hostname_field: Which LibreNMS field to use as the hostname in Nautobot. sysName or hostanme.
- sync_locations: Whether to sync locations from Nautobot to LibreNMS.
- location_type: This is used to filter which locations are synced to LibreNMS. This should be the Location Type that actually has devices assigned. For example, Site. Since LibreNMS does not support nested locations.
- tenant: This is used as a filter for objects synced with Nautobot and LibreNMS. This can be used to sync multiple LibreNMS instances into different tenants, like in an MSP environment. This affects which devices are loaded from Nautobot during the sync. It does not affect which devices are loaded from LibreNMS


### LibreNMS as DataSource

The LibreNMS SSoT integration is built as part of the [Nautobot Single Source of Truth (SSoT)](https://github.com/nautobot/nautobot-app-ssot) app. the SSoT app enables Nautobot to be the aggregation point for data coming from multiple systems of record (SoR).

#### Job Specific Options

- load_type: Whether to load data from a local fixture file or from the External Integration API. File is only used for testing or trying out the integration without a connection to a LibreNMS instance.

From LibreNMS into Nautobot, the app synchronizes devices, and Locations. Here is a table showing the data mappings when syncing from LibreNMS to Nautobot.

| LibreNMS objects        | Nautobot objects             |
| ----------------------- | ---------------------------- |
| geo location            | Location                     |
| device                  | Device                       |
| interface               | Interface `**`               |
| device os               | Platform/Manufacturer `*`    |
| os version              | Software/SoftwareImage       |
| ip address              | IPAddress `**`               |
| hardware                | DeviceType                   |


`*` Device OS from LibreNMS is not standardized and therefore there is a mapping that can be updated in the `constants.py` file for the integration as more device manufacturers and platforms need to be added. If new device manufacturers and platforms are added, open an issue or PR to add them.
`**` Not yet implemented, but planned for the future.

### LibreNMS as DataTarget

This is a job that can be used to sync data from Nautobot to LibreNMS. 

#### Job Specific Options

- force_add: Whether to force add devices to LibreNMS. This will bypass the ICMP check. Will not work correctly until SNMP credential support is added to the LibreNMSDataTarget job.
- ping_fallback: Whether to add device as ping-only if device is not reachable via SNMP.

From Nautobot into LibreNMS, the app synchronizes devices, and Locations. Here is a table showing the data mappings when syncing from Nautobot to LibreNMS.

| Nautobot objects             | LibreNMS objects        |
| ---------------------------- | ----------------------- |
| Device                       | device `*`              |
| Location                     | geo location `**`       |

`*` Devices in Nautobot must have a primary IP address set for them to be added to LibreNMS.
`**` Locations must have GPS coordinates set for them to be added to LibreNMS.
