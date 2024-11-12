
# v3.2 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a
Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic
Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- There have been two new integrations added to the project!

    1. Bootstrap SSoT: The Bootstrap integration allows users to quickly and consistently setup NAutobot environments with base objects like Locations, LocationTypes, Tenants, VLANs and more. This integration, when linked to a Git repository with the requisite data will sync the provided objects, represented in YAML, and will synchronize these objects into Nautobot. Using this integration users can update multiple Nautobot instances with the same data, or easily test and promote changes through a pipeline. Users can also use Bootstrap to spin up local development environments with the base information needed to create test devices to develop new apps for Nautobot.

    2. Cisco Meraki SSoT: The Cisco Meraki integration allows users to import Networks, Devices, Ports, Prefixes, and IP Addresses from the Meraki Dashboard. Refer to the integration documentation for a full explanation of all capabilities and options for the integration.

- The DNA Center and Device42 integrations have been updated to allow specifying the LocationType for imported Location objects.

## [v3.2.0 (2024-10-21)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.2.0)

### Added

- [#541](https://github.com/nautobot/nautobot-app-ssot/issues/541) - Add Bootstrap SSoT to Nautobot SSoT Nautobot application
- [#546](https://github.com/nautobot/nautobot-app-ssot/issues/546) - Added support for specifying LocationType for Areas, Buildings, and Floors in DNA Center integration.
- [#546](https://github.com/nautobot/nautobot-app-ssot/issues/546) - Added support for specifying LocationType for Buildings in Device42 integration.
- [#574](https://github.com/nautobot/nautobot-app-ssot/issues/574) - Added integration with Cisco Meraki.

### Changed

- [#574](https://github.com/nautobot/nautobot-app-ssot/issues/574) - Updated DNA Center Job to use SSoT verify_controller_managed_device_group utility function so code is more DRY.

### Fixed

- [#479](https://github.com/nautobot/nautobot-app-ssot/issues/479) - Corrected the attribute used to reference the ControllerManagedDeviceGroup off a Controller object.
- [#548](https://github.com/nautobot/nautobot-app-ssot/issues/548) - Fixed SSoT jobs not respecting DryRun variable.
- [#558](https://github.com/nautobot/nautobot-app-ssot/issues/558) - Fixed VRF attribute for Prefix create() to be ids instead of attrs.
- [#561](https://github.com/nautobot/nautobot-app-ssot/issues/561) - Bug in IP Fabric that causes some network columns to return host bits set; changed `ip_network` to use `strict=False`.
- [#571](https://github.com/nautobot/nautobot-app-ssot/issues/571) - Fixed requests call that was missing URL scheme.
- [#574](https://github.com/nautobot/nautobot-app-ssot/issues/574) - Fixed the ACI integration's retrieval of Controller Managed Device Group name that was breaking ACI adapter.

### Documentation

- [#568](https://github.com/nautobot/nautobot-app-ssot/issues/568) - Changed documentation to include passing job in the example of loading Adapters.
- [#541](https://github.com/nautobot/nautobot-app-ssot/issues/541) - Fixed documentation errors with 1.5 release notes and missing links to integration setup and user sections.
- [#542](https://github.com/nautobot/nautobot-app-ssot/issues/542) - Correct documentation for ACI integration and add missing DNA Center installation documentation.
- [#546](https://github.com/nautobot/nautobot-app-ssot/issues/546) - Added documentation on how to use DNA Center integration along with screenshots of the steps.
- [#546](https://github.com/nautobot/nautobot-app-ssot/issues/546) - Updated documentation for Device42 integration and updated Job form screenshot to update for Building LocationType Job form change.
- [#569](https://github.com/nautobot/nautobot-app-ssot/issues/569) - Add missing links for integrations to Integrations Configuration portion of Install and Configure section.
- [#574](https://github.com/nautobot/nautobot-app-ssot/issues/574) - Added documentation for Meraki integration.
