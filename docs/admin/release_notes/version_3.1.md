
## [v3.1.0 (2024-09-06)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.1.0)

### Added

- [#527](https://github.com/nautobot/nautobot-app-ssot/issues/527) - Added Python 3.12 support.
- [#528](https://github.com/nautobot/nautobot-app-ssot/issues/528) - Added DNA Center integration to _MIN_NAUTOBOT_VERSION as it requires Nautobot 2.2 for Controller object.

### Changed

- [#526](https://github.com/nautobot/nautobot-app-ssot/issues/526) - Updated the ExampleDataSource job to improve memory utilization with large data sets.
- [#526](https://github.com/nautobot/nautobot-app-ssot/issues/526) - Changed memory profiling logging output to format bytes into KiB/MiB.

### Fixed

- [#521](https://github.com/nautobot/nautobot-app-ssot/issues/521) - Fixed generalized Exception with SecretsGroup and add custom Exception in case SecretsGroup not found on ExternalIntegration.
- [#528](https://github.com/nautobot/nautobot-app-ssot/issues/528) - Fixed bug preventing use of Nautobot 2.1 due to ACI requiring 2.2.
- [#528](https://github.com/nautobot/nautobot-app-ssot/issues/528) - Fixed JobResult association to Sync object to CASCADE instead of PROTECT so Sync object is deleted when JobResult is instead of preventing deletion.
- [#530](https://github.com/nautobot/nautobot-app-ssot/issues/530) - Fixed Infoblox Configuration List Bug when on Nautobot 2.3 by disabling SSOTInfobloxConfig from being a saved view.

### Documentation

- [#520](https://github.com/nautobot/nautobot-app-ssot/issues/520) - Added instructions for enabling Infoblox integration.

### Housekeeping

- [#527](https://github.com/nautobot/nautobot-app-ssot/issues/527) - Rebaked from the cookie 'nautobot-app-v2.3.2'.
