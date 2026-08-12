# v4.6 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Added a new Cisco SD-WAN integration for synchronizing data from Cisco Catalyst SD-WAN Manager (vManage) into Nautobot.
- Improved sync performance for the Infoblox integration.
- Fixed bugs across several integrations (LibreNMS, Arista CloudVision, Infoblox, Meraki, and Bootstrap).

<!-- towncrier release notes start -->

## [v4.6.1 (2026-08-07)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v4.6.1)

### Fixed

- [#1290](https://github.com/nautobot/nautobot-app-ssot/issues/1290) - Fixed LibreNMS sync failing with an `AttributeError` when no Tenant Filter was selected; IP addresses are now placed in the Global namespace when no tenant is set.
- [#1290](https://github.com/nautobot/nautobot-app-ssot/issues/1290) - Fixed the Tenant Filter being silently ignored by the Nautobot to LibreNMS job.
- [#1310](https://github.com/nautobot/nautobot-app-ssot/issues/1310) - Fixed a ProtectedError crash in the Meraki integration when a SoftwareVersion that was still assigned to a Device was deleted, by deferring SoftwareVersion deletion until after Devices have been updated.

## [v4.6.0 (2026-07-28)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v4.6.0)

### Added

- [#1252](https://github.com/nautobot/nautobot-app-ssot/issues/1252) - Added Cisco SD-WAN integration to synchronize Devices, Device Types, Software Versions, Interfaces, IP Addresses, and VRFs from Cisco Catalyst SD-WAN Manager (vManage) into Nautobot.

### Fixed

- [#1153](https://github.com/nautobot/nautobot-app-ssot/issues/1153) - Fixed LibreNMS device sync raising UnboundLocalError when updating a device's os_version without also updating its platform.
- [#1245](https://github.com/nautobot/nautobot-app-ssot/issues/1245) - Fixed Arista CloudVision sync handling of device attributes streamed across multiple gRPC notification frames.
- [#1292](https://github.com/nautobot/nautobot-app-ssot/issues/1292) - Fixed LibreNMS device sync overwriting a device's location on every run regardless of the sync_locations setting.
- [#1294](https://github.com/nautobot/nautobot-app-ssot/issues/1294) - Fixed Bootstrap `ScheduledJob` create/update failing on Nautobot v3.
- [#1296](https://github.com/nautobot/nautobot-app-ssot/issues/1296) - Improved Infoblox sync performance by bulk-fetching records and paging large prefixes.
- [#1299](https://github.com/nautobot/nautobot-app-ssot/issues/1299) - Fixed Infoblox location EA mapping to be case-insensitive, configurable, and resilient to incompatible LocationTypes.
- [#1304](https://github.com/nautobot/nautobot-app-ssot/issues/1304) - Fixed Meraki IP address sync incorrectly marking an address as primary when it was primary for a different device rather than the device being synced.
- [#1315](https://github.com/nautobot/nautobot-app-ssot/issues/1315) - Fixed Arista CloudVision SSoT failing to load on Python 3.12 when `setuptools` is not installed.
- [#1315](https://github.com/nautobot/nautobot-app-ssot/issues/1315) - Fixed DNA Center sync failing to import Devices on Nautobot v3.2.

### Documentation

- [#1298](https://github.com/nautobot/nautobot-app-ssot/issues/1298) - Updated the list of fields used in Infoblox integration documentation for better readability.

### Housekeeping

- [#1309](https://github.com/nautobot/nautobot-app-ssot/issues/1309) - Fixed Nautobot Upstream Monitor test failures against Nautobot 3.2.
- [#1315](https://github.com/nautobot/nautobot-app-ssot/issues/1315) - Fixed failing Device42 unit test caused by changed Interface ordering in Nautobot v3.2.
