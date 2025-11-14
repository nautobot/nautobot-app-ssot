# v3.11 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

Version 3.11 marks the designation of the 3.x branch as a Long Term Maintenance (LTM) release. This designation establishes a clear maintenance strategy for the 3.x series: only critical bug fixes and security patches will be incorporated into future 3.x releases. All new features, enhancements, and non-critical improvements will be developed exclusively for the 4.x branch. This approach ensures stability and reliability for production deployments while allowing for continued innovation in the 4.x series. Organizations requiring new functionality should plan to migrate to the 4.x branch when ready.

## [v3.11.0 (2025-11-14)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.11.0)

### Added

- [#951](https://github.com/nautobot/nautobot-app-ssot/issues/951) - Added data validation for name, role, device_type, location and platform.
- [#1004](https://github.com/nautobot/nautobot-app-ssot/issues/1004) - Added the ability to sync Virtual Machine tags from vSphere to Nautobot

### Fixed

- [#973](https://github.com/nautobot/nautobot-app-ssot/issues/973) - Fixes issue when creating new SecretsGroup's with Secrets associations not being created when more than one is specified.
- [#973](https://github.com/nautobot/nautobot-app-ssot/issues/973) - Provides additional checks to ensure secrets are specified before creating associations.
- [#975](https://github.com/nautobot/nautobot-app-ssot/issues/975) - - In the Bootstrap User Guide, changes the type for the longitude and latitude fields under the `Location` section from `str` to `float`.
- [#989](https://github.com/nautobot/nautobot-app-ssot/issues/989) - Corrected identifiers for loading of Floor location associated to a Controller in DNA Center integration.
- [#990](https://github.com/nautobot/nautobot-app-ssot/issues/990) - Show SSOT job start time in user-defined timezone
- [#996](https://github.com/nautobot/nautobot-app-ssot/issues/996) - Fixed Infoblox integration diffsync model trying to assign a Prefix to Location M2M before the Prefix has been saved.
- [#1000](https://github.com/nautobot/nautobot-app-ssot/issues/1000) - Fixes contrib NautobotModel _get_queryset method to properly add related fields to prefetch_related method.
- [#1006](https://github.com/nautobot/nautobot-app-ssot/issues/1006) - Move diff to a separate tab so in case of a large diff only the diff tab timeouts but not entire Sync object detailed view.

### Housekeeping

- [#985](https://github.com/nautobot/nautobot-app-ssot/issues/985) - Corrected Nautobot destination terminology in InfoBlox integratin.
- [#1007](https://github.com/nautobot/nautobot-app-ssot/issues/1007) - Cleaned up outdated code related to older versions of Nautobot and the Device Lifecycle Management App.
- Rebaked from the cookie `nautobot-app-v2.7.0`.
- Rebaked from the cookie `nautobot-app-v2.7.1`.
