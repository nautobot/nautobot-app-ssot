
# v3.5 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Major features or milestones
- Changes to compatibility with Nautobot and/or other apps, libraries etc.

## [v3.5.0 (2025-02-04)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.5.0)

### Added

- [#672](https://github.com/nautobot/nautobot-app-ssot/issues/672) - Added LibreNMSDataTarget job to sync data from Nautobot to LibreNMS.
- [#677](https://github.com/nautobot/nautobot-app-ssot/issues/677) - Added ScheduledJob model to Bootstrap integration.

### Changed

- [#686](https://github.com/nautobot/nautobot-app-ssot/issues/686) - Changed SolarWinds integration to use IOSImage field to grab Aruba DeviceTypes.

### Fixed

- [#564](https://github.com/nautobot/nautobot-app-ssot/issues/564) - Skip OOB IP address population if mgmt tenant listed in ignore_tenants configuration setting
- [#654](https://github.com/nautobot/nautobot-app-ssot/issues/654) - Fixed ACI signal initializing Tags without ContentType or Color being populated
- [#654](https://github.com/nautobot/nautobot-app-ssot/issues/654) - Fixed ACI signal initializing Tag throwing duplicate key exception.
- [#666](https://github.com/nautobot/nautobot-app-ssot/issues/666) - Fix empty memory profiling metrics causing Prometheus error.
- [#680](https://github.com/nautobot/nautobot-app-ssot/issues/680) - Fixed error in Meraki integration when loading region_map with duplicate named Locations.
- [#681](https://github.com/nautobot/nautobot-app-ssot/issues/681) - Revert removal of app_name.

### Dependencies

- [#675](https://github.com/nautobot/nautobot-app-ssot/issues/675) - Removed unused dependency of orionsdk for SolarWinds integration.
