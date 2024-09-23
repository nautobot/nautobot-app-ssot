
## [v2.8.0 (2024-08-21)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v2.8.0)

### Added

- [#504](https://github.com/nautobot/nautobot-app-ssot/issues/504) - Added pagination to the `get_all_subnets` Infoblox client call.

### Documentation

- [#488](https://github.com/nautobot/nautobot-app-ssot/issues/488) - Fixed issue with Infoblox setup docs.

### Fixed

- [#491](https://github.com/nautobot/nautobot-app-ssot/issues/491) - Fixed tenant names and introduced tag for multisite.
- [#497](https://github.com/nautobot/nautobot-app-ssot/issues/497) - Fixed IPFabric test failures under Django 4.2.


## v2.8.1 - 2024-09-23

### Fixed

- [#530](https://github.com/nautobot/nautobot-app-ssot/issues/530) - Fixed Infoblox Configuration List Bug when on Nautobot 2.3 by disabling SSOTInfobloxConfig from being a saved view.
