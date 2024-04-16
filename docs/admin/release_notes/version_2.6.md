
# v2.5 Release Notes

## [v2.6.0 (2024-04-16)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v2.6.0)

### Added

- [#367](https://github.com/nautobot/nautobot-app-ssot/issues/367) - Added support of Roles, Platforms, Manufacturers, DeviceTypes, and Devices to example Jobs.

### Changed

- [#398](https://github.com/nautobot/nautobot-app-ssot/issues/398) - Changed Arista Cloud Vision jobs to optionally use ExternalIntegration.
- [#414](https://github.com/nautobot/nautobot-app-ssot/issues/414) - Changed IPFabric interface media matching to fall back on interface names.

### Fixed

- [#367](https://github.com/nautobot/nautobot-app-ssot/issues/367) - Fixed issues with example Jobs.
- [#407](https://github.com/nautobot/nautobot-app-ssot/issues/407) - + Fixed logic check for 'hide_example_jobs' when defined, and also set to False.
- [#409](https://github.com/nautobot/nautobot-app-ssot/issues/409) - + Fixes tagging and custom field updates for Nautobot objects synced to/from Infoblox.
- [#413](https://github.com/nautobot/nautobot-app-ssot/issues/413) - Fixed method of retrieving objects from IPFabric's technology categories.

### Housekeeping

- [#418](https://github.com/nautobot/nautobot-app-ssot/issues/418) - Unpins multiple dependencies.
- [#421](https://github.com/nautobot/nautobot-app-ssot/issues/421) - Opened prometheus-client dependency range and removed direct drf-spectacular dependency.
