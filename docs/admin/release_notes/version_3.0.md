# [v3.0.0 (2024-08-22)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.0.0)

## Release 3.0.0 Overview

There are two major updates in this release. First, the entire project has been upgraded to support DiffSync 2.0 which utilizes pydantic 2.0. This should improve processing times for any integrations or personal Apps utilizing the SSoT framework. However, it will require some slight changes to any code using the framework. You can find details about these required updates in [the documentation](https://docs.nautobot.com/projects/ssot/en/latest/dev/upgrade/).

Second, this release also adds a new integration supporting Cisco's DNA Center product. In addition, we've migrated the IPFabric ChatOps command allowing triggering of the SSoT sync Job to the ChatOps project so you will be required to upgrade to 3.1.0 if you use that Job.

### Added

- [#451](https://github.com/nautobot/nautobot-app-ssot/issues/451) - Added integration for DNA Center.

### Changed

- [#471](https://github.com/nautobot/nautobot-app-ssot/pull/471) - Updated ACI, Device42, and DNA Center integrations to use Controller or ExternalIntegration instead of PLUGINS_CONFIG settings.

### Removed

- [#508](https://github.com/nautobot/nautobot-app-ssot/issues/508) - Removed IPFabric ChatOps command as it has been migrated to ChatOps project [here](https://github.com/nautobot/nautobot-app-chatops/pull/318).

### Dependencies

- [#433](https://github.com/nautobot/nautobot-app-ssot/issues/433) - Removed ipfabric-diagrams
- [#433](https://github.com/nautobot/nautobot-app-ssot/issues/433) - Removed nautobot-chatops
- [#433](https://github.com/nautobot/nautobot-app-ssot/issues/433) - Upgraded DiffSync to 2.0.0

Updating DiffSync required changes to imports and many files changed `from diffsync import Diffsync` to `from diffsync import Adapter` and then changing `diffsync` to `adapter` in the file.

### Housekeeping

- [#433](https://github.com/nautobot/nautobot-app-ssot/issues/433) - Black 24.4.0 includes new formatting which was applied to all python files.

## [v3.0.1 (2024-08-23)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.0.1)

### Fixed

- [#507](https://github.com/nautobot/nautobot-app-ssot/issues/507) - Fixed DataTarget example Job to include run() function for using ExternalIntegration or supplied URL and token.

### Dependencies

- [#516](https://github.com/nautobot/nautobot-app-ssot/issues/516) - Fix the dependencies for mkdocstrings and mkdocstrings-python to fix RTD build.

### Documentation

- [#518](https://github.com/nautobot/nautobot-app-ssot/issues/518) - Minor doc updates on upgrade to 3.0.

### Housekeeping

- [#515](https://github.com/nautobot/nautobot-app-ssot/issues/515) - Rebaked from the cookie `nautobot-app-v2.3.0`.
