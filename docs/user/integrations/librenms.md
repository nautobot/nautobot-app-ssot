## Usage

## Process

### LibreNMS as DataSource

The LibreNMS SSoT integration is built as part of the [Nautobot Single Source of Truth (SSoT)](https://github.com/nautobot/nautobot-app-ssot) app. the SSoT app enables Nautobot to be the aggregation point for data coming from multiple systems of record (SoR).

#### Job Options

- Debug: Additional Logging
- Librenms Server: External integration object pointing to the required LibreNMS instance.
- hostname_field: Which LibreNMS field to use as the hostname in Nautobot. sysName or hostanme.
- sync_location_parents: Whether to lookup City and State to add parent locations for geo locations.
- tenant: This is used as a filter for objects synced with Nautobot and LibreNMS. This can be used to sync multiple LibreNMS instances into different tenants, like in an MSP environment. This affects which devices are loaded from Nautobot during the sync. It does not affect which devices are loaded from LibreNMS

From LibreNMS into Nautobot, the app synchronizes devices, their interfaces, associated IP addresses, and Locations. Here is a table showing the data mappings when syncing from LibreNMS.

| LibreNMS objects        | Nautobot objects             |
| ----------------------- | ---------------------------- |
| geo location            | Location                     |
| device                  | Device                       |
| interface               | Interface                    |
| device os               | Platform/Manufacturer `*`    |
| os version              | Software/SoftwareImage       |
| ip address              | IPAddress                    |
| hardware                | DeviceType                   |


`*` Device OS from LibreNMS is not standardized and therefore there is a mapping that can be updated in the `constants.py` file for the integration as more device manufacturers and platforms need to be added.

### LibreNMS as DataTarget

NotYetImplemented

