## Usage

## Configuration

The LibreNMS integration supports several configuration options that can be set in your `nautobot_config.py` file:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `librenms_permitted_values` | dict | `{"role": ["network"]}` | Controls which device roles from LibreNMS are allowed to be imported into Nautobot. Only devices with roles listed in the `role` array will be synchronized. |
| `librenms_allow_ip_hostnames` | boolean | `false` | Whether to allow devices with IP addresses as hostnames to be imported. |
| `librenms_show_failures` | boolean | `true` | Whether to display detailed information about devices that failed to import. |
| `librenms_consolidated_platforms` | boolean | `false` | Name Platforms after the network driver (`cisco_ios`) so they are shared with [nautobot-app-device-onboarding](https://github.com/nautobot/nautobot-app-device-onboarding), instead of after the Ansible collection FQCN (`cisco.ios.ios`). See [Platform naming and network drivers](#platform-naming-and-network-drivers). |
| `librenms_network_driver_map` | dict | `{}` | Override or suppress the bundled LibreNMS `os` to network driver mappings. Highest precedence. Values are not validated against netutils, so this composes with Nautobot's `NETWORK_DRIVERS` setting. |

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
        "librenms_consolidated_platforms": False,
        "librenms_network_driver_map": {},
    }
}
```

## Platform naming and network drivers

LibreNMS reports a device OS as a short string such as `ios`, `iosxe` or `fortios`. Nautobot needs
two things from it: a `Platform` name, and a `network_driver` that driver-keyed consumers such as
Golden Config and Nornir dispatch can resolve.

`librenms_consolidated_platforms` selects how the name is derived:

| | `false` (default) | `true` |
|---|---|---|
| New Platform name | `cisco.ios.ios` | `cisco_ios` |
| `network_driver` on new Platforms | `cisco_ios` | `cisco_ios` |
| Existing Platforms | never modified | never modified; adopted in place |
| Identity used for diffing | Platform name | network driver |
| Devices moved when enabling | none | only the IOS/IOS-XE split |

In both modes a newly created Platform gets a valid `network_driver`, and existing Platforms are
never modified automatically.

Enable consolidated mode when you also run device-onboarding, which names Platforms after the
netmiko driver and looks them up by name. Without it, the two apps create two rows for the same OS
and every LibreNMS sync rewrites an onboarded device's platform from `cisco_ios` to `cisco.ios.ios`.

### Adopting platforms you already have

Consolidated mode resolves platform identity on read, and understands the legacy shapes, so
enabling it does not fork new rows for platforms you already hold:

| Existing Platform (name / driver) | LibreNMS `os` | Result |
|---|---|---|
| `cisco_ios` / `cisco_ios` (device-onboarding) | `ios` | No diff -- the row is shared |
| `cisco.ios.ios` / `cisco.ios.ios` (legacy) | `ios` | No diff, no writes |
| `cisco.ios.ios` / `cisco_ios` (dna_center style) | `ios` | No diff |
| `fortios` / `fortios` (legacy raw-OS name) | `fortios` | No diff |
| `opnsense` / blank (unmapped OS) | `opnsense` | No diff |
| `cisco.ios.ios` / `cisco.ios.ios` | `iosxe` | Diff -- devices move to a new `cisco_xe` |
| `Cisco IOS` / blank (hand-made) | `ios` | Diff -- devices move to `cisco_ios` |

### The IOS/IOS-XE split

Default naming maps both `ios` and `iosxe` onto a single `cisco.ios.ios` Platform. Consolidated mode
separates them into `cisco_ios` and `cisco_xe`, which is the only device movement enabling the
setting causes. Each move is logged, and step 3 of the sequence below shows the exact list before
anything is written. To decline the split:

```python
"librenms_network_driver_map": {"iosxe": "cisco_ios"},
```

Software versions belonging to the old platform are left in place; equivalent rows are created under
`cisco_xe`. Nothing is deleted automatically.

### Unmapped OS values

Genuinely ambiguous LibreNMS OS values are deliberately left unmapped rather than guessed: `dnos`
(OS9 versus OS10), `asyncos`, `junose`, `extremeware`, `zynos`, `zywall`, `sonicwall`, `pfsense`,
`opnsense`, `vmwareesxi`, `aix`, `cumulus` and `axos`. They keep their raw OS platform name and get
a blank `network_driver`. Map them yourself with `librenms_network_driver_map`:

```python
"librenms_network_driver_map": {"dnos": "dell_os10"},
```

An explicit empty string suppresses a bundled mapping, leaving the driver blank:

```python
"librenms_network_driver_map": {"fortios": ""},
```

### Enabling consolidated platforms

Each step is independently reversible up to step 4.

1. Run the **LibreNMS Platform Consolidation** job in dry-run with repair only, to see the
   landscape. The CSV it attaches lists every platform, its current driver and its intended driver.
2. Optionally run the repair phase for real. This sets correct drivers on existing FQCN-named rows,
   changes no names and moves no devices. Safe with `librenms_consolidated_platforms` still `false`.
   Enable **Repair manufacturers** in the same run to fold OS-named Manufacturers such as `panos`
   back onto `Palo Alto`.
3. Set `librenms_consolidated_platforms = True` and run **LibreNMS to Nautobot** in dry-run. The
   diff lists exactly which devices change platform. Existing rows are adopted in place, so the
   only entries should be the IOS/IOS-XE split and any hand-named platforms.
4. Run the sync for real.
5. Optionally run the consolidation job with `rename_legacy_platforms` and `merge_duplicates` to
   converge names on device-onboarding's.

### Platform Consolidation job

**LibreNMS Platform Consolidation** remediates existing Platform rows. It is opt-in, defaults to a
dry run, and is scoped by default to LibreNMS-synced platforms. It never invents a driver, never
overwrites a `network_driver` that disagrees, and never touches anything outside its scope.

Four phases, each independently selectable:

- **Repair drivers** (default on) -- for rows named after an Ansible FQCN whose `network_driver` is
  blank or duplicates the name, set the correct driver. Structurally cannot match a dna_center or
  device42 row, nor a hand-named one. Safe in either mode.
- **Rename legacy platforms** (default off) -- rename `cisco.ios.ios` to `cisco_ios` when the target
  name is free. Preserves the primary key, so all foreign keys, config context assignments, notes,
  metadata, relationships and dynamic groups survive. Refuses if an `ObjectPermission` constraint
  references the name; reports dynamic group, saved view and scheduled job references, and rewrites
  dynamic group filters only when you opt in.
- **Merge duplicates** (default off) -- collapse platforms sharing a `network_driver` onto one
  survivor, moving devices, virtual machines, controllers, software versions, config context links,
  notes and metadata. Refuses on a software version collision or a manufacturer conflict unless you
  explicitly choose how to resolve it, and never deletes a platform that still has software
  versions.
- **Repair manufacturers** (default off) -- rename Manufacturers named after the device OS, such as
  `panos` to `Palo Alto`. Renames in place when the vendor name is free, which moves nothing; merges
  when it is taken. Independent of the platform-naming mode, since a Manufacturer named after the OS
  is wrong either way. Refuses when the same device type model exists under both Manufacturers,
  because merging those moves real Devices between DeviceTypes -- set `device_type_collisions` to
  "merge" to allow it.

The rename and merge phases refuse to run while `librenms_consolidated_platforms` is `false`,
because in legacy mode the sync looks platforms up by FQCN name and would simply re-create the row.

The run records its plan as a **Data Sync**, so it appears in SSoT Sync History with the same
paginated diff view the sync jobs produce -- a repair reads as a before/after on `network_driver`,
a rename as one on `name`, and a refusal carries its reason. The job log additionally renders the
plan as a table, and attaches `librenms_platform_consolidation.csv` plus
`librenms_manufacturer_consolidation.csv` for estates too large to read on screen.

### Manufacturers named after the device OS

The Manufacturer is resolved from the LibreNMS `os` through the OS-to-manufacturer table, so `panos`
devices land under `Palo Alto` and `asa` devices under the same `Cisco` row as `ios` devices.

An estate synced by an earlier version may instead hold Manufacturers named after the OS string,
which fragments a vendor into one row per OS:

| LibreNMS `os` | Manufacturer present | Correct vendor |
|---|---|---|
| `panos` | `panos` | `Palo Alto` |
| `asa` | `asa` | `Cisco` |
| `fortios` | `fortios` | `Fortinet` |
| `arubaos` | `arubaos` | `Aruba Networks` |

Those rows are left alone until you run the consolidation job's **Repair manufacturers** phase, so
both `panos` and `Palo Alto` can be present in the meantime.

The phase is scoped by an internally derived name map rather than by the platform scope, so it can
only match a name that OS-named resolution could have produced -- a real vendor name is never a
candidate, and entries are dropped where two OS values disagree.

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
- device_secrets_group: Optional Secrets Group assigned to Devices created by this job. This is the Secrets Group holding the credentials used to connect to the device itself, not the LibreNMS API token on the External Integration. Devices need it for credential-dependent jobs such as nautobot-device-onboarding's `Sync Network Data From Network`, which has no credentials field of its own and reads them only from the Device's Secrets Group. See [the setup guide](../../admin/integrations/librenms_setup.md) for how to build it.

    A Device that already has a Secrets Group is never overwritten, so a group assigned by hand or by another job survives later syncs. This also means Devices created before this field existed are only backfilled when the sync updates them for some other reason; to fix them all at once, filter the Devices list view and use the bulk edit button to set Secrets Group.

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
