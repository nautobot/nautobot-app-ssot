
# v2.6 Release Notes

## [v2.6.0 (2024-04-16)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v2.6.0)

### Added

- [#367](https://github.com/nautobot/nautobot-app-ssot/issues/367) - Added support of Roles, Platforms, Manufacturers, DeviceTypes, and Devices to example Jobs.

### Changed

- [#398](https://github.com/nautobot/nautobot-app-ssot/issues/398) - Changed Arista Cloud Vision jobs to optionally use ExternalIntegration.
- [#414](https://github.com/nautobot/nautobot-app-ssot/issues/414) - Changed IPFabric interface media matching to fall back on interface names.

### Fixed

- [#367](https://github.com/nautobot/nautobot-app-ssot/issues/367) - Fixed issues with example Jobs.
- [#407](https://github.com/nautobot/nautobot-app-ssot/issues/407) - Fixed logic check for 'hide_example_jobs' when defined, and also set to False.
- [#409](https://github.com/nautobot/nautobot-app-ssot/issues/409) - Fixed tagging and custom field updates for Nautobot objects synced to/from Infoblox.
- [#413](https://github.com/nautobot/nautobot-app-ssot/issues/413) - Fixed method of retrieving objects from IPFabric's technology categories.

### Housekeeping

- [#418](https://github.com/nautobot/nautobot-app-ssot/issues/418) - Unpins multiple dependencies.
- [#421](https://github.com/nautobot/nautobot-app-ssot/issues/421) - Opened prometheus-client dependency range and removed direct drf-spectacular dependency.

## [v2.6.1 (2024-04-29)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v2.6.1)

### Added

- [#436](https://github.com/nautobot/nautobot-app-ssot/issues/436) - Added additional unit tests for Device42 integration.

### Changed

- [#437](https://github.com/nautobot/nautobot-app-ssot/issues/437) - Improved performance of the Infoblox client by using `requests.Session` for API calls instead of `requests.request`.

### Fixed

- [#435](https://github.com/nautobot/nautobot-app-ssot/issues/435) - Fixed handling of DLM App installed but not enabled throwing RuntimeError.
- [#436](https://github.com/nautobot/nautobot-app-ssot/issues/436) - Fixed IPAddress attribute to be ip_version.
- [#436](https://github.com/nautobot/nautobot-app-ssot/issues/436) - Fixed IPAddress Status to Active if available, else Reserved.
- [#436](https://github.com/nautobot/nautobot-app-ssot/issues/436) - Fixed multiple bugs when assigning IPAddresses to Interfaces.
- [#436](https://github.com/nautobot/nautobot-app-ssot/issues/436) - Fixed check for Building definiton when creating a VLAN.
- [#436](https://github.com/nautobot/nautobot-app-ssot/issues/436) - Fixed VLAN to use location instead of location_id in create().

### Houstkeeping

- [#431](https://github.com/nautobot/nautobot-app-ssot/issues/431) - Updated note on nautobot_ssot/integrations/ipfabric/diffsync/adapter_ipfabric.py IPFabricDiffSync from Nautobot to IPFabric.
