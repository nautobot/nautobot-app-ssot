# v3.12 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Major features or milestones
- Changes to compatibility with Nautobot and/or other apps, libraries etc.

<!-- towncrier release notes start -->


## [v3.12.3 (2026-03-24)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.12.3)

### Fixed

- [#1146](https://github.com/nautobot/nautobot-app-ssot/issues/1146) - Fixed display of large diffs by implementing pagination in render_diff() method.

## [v3.12.2 (2026-03-24)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.12.2)

### Added

- [#1120](https://github.com/nautobot/nautobot-app-ssot/issues/1120) - Adds job input to define the default status for synced Meraki devices.

### Fixed

- [#1119](https://github.com/nautobot/nautobot-app-ssot/issues/1119) - Support Meraki SDK pagination to retrieve all organization devices.
- [#1143](https://github.com/nautobot/nautobot-app-ssot/issues/1143) - Load meraki switchports only once, instead of loading them per device.
- [#1154](https://github.com/nautobot/nautobot-app-ssot/issues/1154) - Support uv controlled development environment to run unittest.

## [v3.12.0 (2026-01-22)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.12.0)

### Added

- [#1027](https://github.com/nautobot/nautobot-app-ssot/issues/1027) - Added Job input to Assign All Meraki Devices Under a Single Location
- [#1028](https://github.com/nautobot/nautobot-app-ssot/issues/1028) - Added setting to Allow Syncing of DHCP-Based Management IPs

## [v3.12.1 (2026-03-09)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.12.1)

### Added

- [#1096](https://github.com/nautobot/nautobot-app-ssot/issues/1096) - Added two new settings to the Arista CV integration to allow for the deletion of namespaces and prefixes that are present in Nautobot but not present in CloudVision (both default to False).

### Fixed

- [#1096](https://github.com/nautobot/nautobot-app-ssot/issues/1096) - Fixed a bug in the Arista CV integration that was attempting to create duplicate namespaces and prefixes that were already present in Nautobot but were not associated with an Arista device.
- [#1098](https://github.com/nautobot/nautobot-app-ssot/issues/1098) - Fixed Device42 integration `load_sites()` passing `LocationType.name` string instead of `LocationType` instance to `Location.objects.filter()`, causing the sync job to fail.
