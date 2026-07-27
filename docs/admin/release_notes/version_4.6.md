# v4.6 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Major features or milestones
- Changes to compatibility with Nautobot and/or other apps, libraries etc.

<!-- towncrier release notes start -->

## [v4.6.0 (2026-07-27)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v4.6.0)

### Added

- [#1252](https://github.com/nautobot/nautobot-app-ssot/issues/1252) - Added Cisco SD-WAN integration, synchronizing Devices, DeviceTypes, SoftwareVersions, Interfaces, IP Addresses, and VRFs from a Cisco Catalyst SD-WAN Manager (vManage) into Nautobot.

### Fixed

- [#1153](https://github.com/nautobot/nautobot-app-ssot/issues/1153) - Fixed LibreNMS device sync raising UnboundLocalError when updating a device's os_version without also updating its platform.
- [#1245](https://github.com/nautobot/nautobot-app-ssot/issues/1245) - Fixed the remaining methods in Arista CloudVision SSoT sync when attributes are streamed in multiple gRPC notification frames.
- [#1292](https://github.com/nautobot/nautobot-app-ssot/issues/1292) - Fixed LibreNMS device sync overwriting a device's location on every run regardless of the sync_locations setting.
- [#1294](https://github.com/nautobot/nautobot-app-ssot/issues/1294) - Fixed Bootstrap `ScheduledJob` create/update failing on Nautobot v3.
- [#1296](https://github.com/nautobot/nautobot-app-ssot/issues/1296) - Speed up Infoblox by bulk-fetching records and paging large prefixes.
- [#1299](https://github.com/nautobot/nautobot-app-ssot/issues/1299) - Fix Infoblox location EA mapping: case-insensitive, LocationType-safe, and configurable.
- [#1304](https://github.com/nautobot/nautobot-app-ssot/issues/1304) - Fixed Meraki IP address sync incorrectly marking an address as primary when it was primary for a different device rather than the device being synced.

### Documentation

- [#1298](https://github.com/nautobot/nautobot-app-ssot/issues/1298) - Updated the list of fields used in Infoblox integration documentation for better readability.

### Housekeeping

- [#1309](https://github.com/nautobot/nautobot-app-ssot/issues/1309) - Fixed Nautobot Upstream Monitor test failures against Nautobot 3.2.
