# Cisco SD-WAN SSoT Integration

The Cisco SD-WAN SSoT integration is built as part of the [Nautobot Single Source of Truth (SSoT)](https://github.com/nautobot/nautobot-app-ssot) app. The SSoT app enables Nautobot to be the aggregation point for data coming from multiple systems of record (SoR).

This integration synchronizes device inventory data from a Cisco Catalyst SD-WAN Manager (formerly vManage) into Nautobot.

## Usage

From the SSoT dashboard or the Jobs view, run the **Cisco SD-WAN to Nautobot** Job. The Job synchronizes the following SD-WAN data into Nautobot objects:

| Cisco SD-WAN              | Nautobot                                |
| ------------------------- | --------------------------------------- |
| Device Model              | DeviceType                              |
| Software Version          | SoftwareVersion                         |
| WAN Edge / Controller     | Device                                  |
| Interface                 | Interface                               |
| Interface IPv4 Address    | IPAddress, IPAddressToInterface, Prefix |
| VPN ID                    | VRF                                     |

### Job Options

- **Catalyst SD-WAN Manager**: The Nautobot Controller representing the SD-WAN Manager to synchronize with. The connection details (URL, credentials, SSL verification) are taken from the ExternalIntegration assigned to the Controller.
- **Controller Managed Device Group**: The device group associated with the Controller. Imported Devices are added to this group, and only Devices in this group are considered during the synchronization.
- **Devices**: Optionally limit the synchronization to the specified Devices.
- **Device Status / Role / Platform / Secrets Group / Tenant**: Values assigned to imported Devices.
- **Device Location**: The staging Location assigned to newly imported Devices. The integration never updates the Location of an existing Device, so Devices can be moved to their real Location in Nautobot without the change being reverted by subsequent synchronizations.
- **Device Model Normalization**: A regex pattern removed from the SD-WAN device model before it is used as the DeviceType model (for example, the default `^vedge-` turns `vedge-C8000V` into `C8000V`).
- **Ignore identical IP addresses with different subnet masks**: When enabled (the default), an IP address that already exists in Nautobot with a different mask is left untouched and a warning is logged. When disabled, the existing IP address mask is updated to match SD-WAN.
- **Delete Replaced IP Addresses**: When an interface's IP address changes, the old address is unassigned from the interface. When this option is enabled, the old IPAddress object is also deleted from Nautobot if it is no longer assigned to any interface.

### Behavior Notes

- Devices that exist in the Controller Managed Device Group in Nautobot but are no longer present in SD-WAN are **not deleted**; their status is set to the configured retired status (`Retired` by default). Retired Devices are ignored by subsequent synchronizations.
- The IP address of selected interfaces (the `system` interface by default, see the `cisco_sdwan_primary_ip_interfaces` setting) is assigned as the Device's primary IPv4 address.
- Parent Prefixes are created automatically in the Global namespace when needed by imported IP addresses.
- DeviceTypes and SoftwareVersions in Nautobot are scoped to those previously synchronized by this integration using [object metadata](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/objectmetadata/), so existing objects managed by other sources are not modified or removed. This requires the `enable_metadata_for` setting to include `CiscoSdwanDataSource` (see the [setup instructions](../../admin/integrations/cisco_sdwan_setup.md)).
