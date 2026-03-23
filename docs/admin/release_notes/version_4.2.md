# v4.2 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Major features or milestones
- Changes to compatibility with Nautobot and/or other apps, libraries etc.

<!-- towncrier release notes start -->

## [v4.2.0 (2025-03-23)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v4.2.0)

### Added

- [#1027](https://github.com/nautobot/nautobot-app-ssot/issues/1027) - Added Job input to Assign All Meraki Devices Under a Single Location
- [#1028](https://github.com/nautobot/nautobot-app-ssot/issues/1028) - Added setting to Allow Syncing of DHCP-Based Management IPs
- [#1062](https://github.com/nautobot/nautobot-app-ssot/issues/1062) - Added an option in the Meraki Integration to sync firewall IPs and Prefixes.
- [#1078](https://github.com/nautobot/nautobot-app-ssot/issues/1078) - Added validations for Controller LocationType and parent Location for the DNA Center integration.
- [#1096](https://github.com/nautobot/nautobot-app-ssot/issues/1096) - Added two new settings to the Arista CV integration to allow for the deletion of namespaces and prefixes that are present in Nautobot but not present in CloudVision (both default to False).
- [#1111](https://github.com/nautobot/nautobot-app-ssot/issues/1111) - Utility method mixin class for `DiffSyncModel` at `nautobot_ssot.utils.diffsync`.
- [#1120](https://github.com/nautobot/nautobot-app-ssot/issues/1120) - Adds job input to define the default status for synced Meraki devices.

### Changed

- [#1111](https://github.com/nautobot/nautobot-app-ssot/issues/1111) - Changed `NautobotAdapter` and `NautobotModel` to use new utility methods.

### Fixed

- [#SD-793](https://github.com/nautobot/nautobot-app-ssot/issues/SD-793) - Fixed various issues in IPFabric SSoT integration, including logging errors, platform creation, IP creation fallback, and VLAN location handling.
- [#950](https://github.com/nautobot/nautobot-app-ssot/issues/950) - Fixed bug in TemplateExtension that was causing an Exception when more than one Sync is returned in a get() query.
- [#961](https://github.com/nautobot/nautobot-app-ssot/issues/961) - Fixed Bootstrap integration crash when user configuration is missing expected keys in bootstrap_models_to_sync settings.
- [#977](https://github.com/nautobot/nautobot-app-ssot/issues/977) - Fixed Bootstrap location sync failing with AttributeError when a tenant is assigned to a location.
- [#1029](https://github.com/nautobot/nautobot-app-ssot/issues/1029) - Fixed vSphere sync failing when Virtual Machine has a disk with no capacity.
- [#1032](https://github.com/nautobot/nautobot-app-ssot/issues/1032) - Fixed incorrect field name `prefix_length` in `IPAddressDict` TypedDict (should be `mask_length` to match the Nautobot `IPAddress` model).
- [#1059](https://github.com/nautobot/nautobot-app-ssot/issues/1059) - Fixed a bug in the Meraki integration that was causing the sync job to fail when a Meraki MX WAN port is configured as PPPoE port.
- [#1063](https://github.com/nautobot/nautobot-app-ssot/issues/1063) - Fixed vSphere sync crash caused by tags with missing name or category resulting in empty-string DiffSync identifiers.
- [#1079](https://github.com/nautobot/nautobot-app-ssot/issues/1079) - Fixed integrations to match example Job run() with args and kwargs ensuring that parallel processing option is saved.
- [#1084](https://github.com/nautobot/nautobot-app-ssot/issues/1084) - Call .get() on an object to retrieve an attribute that might not exist
- [#1086](https://github.com/nautobot/nautobot-app-ssot/issues/1086) - Save data on Device upate syncing from DNA Center
- [#1088](https://github.com/nautobot/nautobot-app-ssot/issues/1088) - Set Location.physical_address in DNA Center SSOT to an empty string if source data is None
- [#1090](https://github.com/nautobot/nautobot-app-ssot/issues/1090) - Changed referenced variable in logging
- [#1092](https://github.com/nautobot/nautobot-app-ssot/issues/1092) - Fixed DNA center resyncing Latitude and longitude every sync in building model by changing data type to float.
- [#1095](https://github.com/nautobot/nautobot-app-ssot/issues/1095) - Change MTU in DNAC integration's base model to be optional.
- [#1096](https://github.com/nautobot/nautobot-app-ssot/issues/1096) - Fixed a bug in the Arista CV integration that was attempting to create duplicate namespaces and prefixes that were already present in Nautobot but were not associated with an Arista device.
- [#1106](https://github.com/nautobot/nautobot-app-ssot/issues/1106) - Fixed vSphere import failure when a VM has a disconnected network adapter with an unexpected state such as UNRECOVERABLE_ERROR.
- [#1109](https://github.com/nautobot/nautobot-app-ssot/issues/1109) - Fixed non-sortable columns (duration, status, user, synced_object) causing errors in Sync and SyncLogEntry list views.
- [#1116](https://github.com/nautobot/nautobot-app-ssot/issues/1116) - Replaced deprecated pytz with stdlib zoneinfo in the Bootstrap integration.
- [#1119](https://github.com/nautobot/nautobot-app-ssot/issues/1119) - Support Meraki SDK pagination to retrieve all organization devices.
- [#1143](https://github.com/nautobot/nautobot-app-ssot/issues/1143) - Load meraki switchports only once, instead of loading them per device.
- [#1146](https://github.com/nautobot/nautobot-app-ssot/issues/1146) - Fixed display of large diffs by implementing pagination in render_diff() method.
- [#1149](https://github.com/nautobot/nautobot-app-ssot/issues/1149) - Fixed loading code in Bootstrap `NautobotAdapter` integration.
- [#1150](https://github.com/nautobot/nautobot-app-ssot/issues/1150) - Fixed logic in Bootstrap integration loaders.

### Documentation

- [#1078](https://github.com/nautobot/nautobot-app-ssot/issues/1078) - Updated the DNA Center integration documentation to clarify the expected LocationType hierarchy.
- [#1097](https://github.com/nautobot/nautobot-app-ssot/issues/1097) - Added documentation around the change to the run() method in 4.1.0.

### Housekeeping

- Rebaked from the cookie `nautobot-app-v3.1.2`.
