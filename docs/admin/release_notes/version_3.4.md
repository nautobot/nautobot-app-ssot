
# v3.4 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

This release adds two new integrations to the project, one for SolarWinds Orion and one for LibreNMS! There are also a lot of bug fixes for various integrations.

## [v3.4.0 (2025-01-14)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.4.0)

### Added

- [#631](https://github.com/nautobot/nautobot-app-ssot/issues/631) - Added integration with SolarWinds.
- [#636](https://github.com/nautobot/nautobot-app-ssot/issues/636) - Added LibreNMS integration.

### Documentation

- [#631](https://github.com/nautobot/nautobot-app-ssot/issues/631) - Added documentation for SolarWinds integration.

### Fixed

- [#597](https://github.com/nautobot/nautobot-app-ssot/issues/597) - Fixed ACI integration LocationType usage in CRUD operations to match Job device_site or specified APIC Location's LocationType.
- [#598](https://github.com/nautobot/nautobot-app-ssot/issues/598) - Swapped out `nautobot.extras.plugins.PluginTemplateExtension` for `TemplateExtension`
- [#621](https://github.com/nautobot/nautobot-app-ssot/issues/621) - Fixed ASN updates on Location objects.
- [#621](https://github.com/nautobot/nautobot-app-ssot/issues/621) - Fixed documentation on data normalization.
- [#624](https://github.com/nautobot/nautobot-app-ssot/issues/624) - Fixed Floors respecting location map for Building related changes.
- [#626](https://github.com/nautobot/nautobot-app-ssot/issues/626) - Fixed SoftwareVersion update on Devices in DNA Center integration.
- [#634](https://github.com/nautobot/nautobot-app-ssot/issues/634) - Fixed load locations on the source adapter for the ServiceNow integration when a site filter is applied.
- [#641](https://github.com/nautobot/nautobot-app-ssot/issues/641) - Fixed incorrectly nested imports within if block used for Device Lifecycle Models.
- [#643](https://github.com/nautobot/nautobot-app-ssot/issues/643) - Fixed DNA Center bug where empty Locations were imported.
- [#646](https://github.com/nautobot/nautobot-app-ssot/issues/646) - Fixed IPAddress assigned wrong parent Prefix in Citrix ADM.
- [#648](https://github.com/nautobot/nautobot-app-ssot/issues/648) - Fixed Citrix ADM deleting SoftwareVersion in use with ValidatedSoftware.
- [#648](https://github.com/nautobot/nautobot-app-ssot/issues/648) - Fixed Meraki deleting SoftwareVersion in use with ValidatedSoftware.
- [#650](https://github.com/nautobot/nautobot-app-ssot/issues/650) - Fixed Device floor name being incorrectly defined and including Building name when it shouldn't.

### Housekeeping

- [#1](https://github.com/nautobot/nautobot-app-ssot/issues/1) - Rebaked from the cookie `nautobot-app-v2.4.1`.
