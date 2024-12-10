# v3.3 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

There have been two new integrations added to the project!

    1. Citrix ADM: This integration allows you to pull in the inventory of your Application Delivery Controllers from Citrix ADM into Nautobot.
    2. Slurp`It: This integration enables users to import data from Slurp`It that's a bit more flexible than their custom Nautobot App.

- Additionally, support for the SoftwareVersion model has been added to the DNA Center and Bootstrap integrations.

## [v3.3.0 (2024-12-06)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.3.0)

### Added

- [#310](https://github.com/nautobot/nautobot-app-ssot/issues/310) - Added common TypedDicts for Contrib SSoT.
- [#449](https://github.com/nautobot/nautobot-app-ssot/issues/449) - Add `delete_records` flag to the ServiceNow DataTarget job
- [#588](https://github.com/nautobot/nautobot-app-ssot/issues/588) - Added support for Software Version object in DNA Center integration.
- [#593](https://github.com/nautobot/nautobot-app-ssot/issues/593) - Added ability to rename Network in Meraki and Datacenter in DNA Center integrations using location_map.
- [#593](https://github.com/nautobot/nautobot-app-ssot/issues/593) - Added support for SoftwareVersion in Bootstrap integration.
- [#599](https://github.com/nautobot/nautobot-app-ssot/issues/599) - Added Citrix ADM integration.
- [#600](https://github.com/nautobot/nautobot-app-ssot/issues/600) - Added integration with Slurpit.

### Changed

- [#590](https://github.com/nautobot/nautobot-app-ssot/issues/590) - Improved error message for validated save in contrib model.

### Removed

- [#588](https://github.com/nautobot/nautobot-app-ssot/issues/588) - Removed use of OS Version CustomField in DNA Center integration. Now uses Software Version from Nautobot 2.2 and/or Device Lifecycle Management SoftwareLCM object if found.

### Fixed

- [#411](https://github.com/nautobot/nautobot-app-ssot/issues/411) - Fixed imports in CustomFields migration that was causing installation issues.
- [#449](https://github.com/nautobot/nautobot-app-ssot/issues/449) - Fix logic used for loading location records to make ServiceNow SSoT Nautobot 2.x compatible
- [#467](https://github.com/nautobot/nautobot-app-ssot/issues/467) - Fix get_tags_by_type() to handle possible RpcError Exception being thrown.
- [#582](https://github.com/nautobot/nautobot-app-ssot/issues/582) - Fixed erroneous print statement in sync logs.
- [#585](https://github.com/nautobot/nautobot-app-ssot/issues/585) - Fixed use of DLM classes with Bootstrap integration.
- [#588](https://github.com/nautobot/nautobot-app-ssot/issues/588) - Fixed hostname mapping functionality in DNA Center integration. It is now available in the Job form.
- [#593](https://github.com/nautobot/nautobot-app-ssot/issues/593) - Fixed Meraki loading of Nautobot Prefixes that have multiple Locations assigned.
- [#593](https://github.com/nautobot/nautobot-app-ssot/issues/593) - Fixed DNA Center loading incorrect location names for Devices.
- [#593](https://github.com/nautobot/nautobot-app-ssot/issues/593) - Fixed KeyError being thrown when port is missing from uplink_settings dict in Meraki integration.
- [#593](https://github.com/nautobot/nautobot-app-ssot/issues/593) - Fixed error in Bootstrap integration in loading ValidatedSoftwareLCM when SoftwareLCM doesn't exist.
- [#593](https://github.com/nautobot/nautobot-app-ssot/issues/593) - Fixed DoesNotExist thrown when attempting to load ContentType that doesn't exist in Bootstrap integration.
- [#599](https://github.com/nautobot/nautobot-app-ssot/issues/599) - Fixed Bootstrap signals that are using create_or_update_custom_field() to pass apps. This was done to correct bug causing Nautobot to crash during startup.
- [#607](https://github.com/nautobot/nautobot-app-ssot/issues/607) - Fix hostname_mapping functionailty in Citrix ADM integration.
- [#610](https://github.com/nautobot/nautobot-app-ssot/issues/610) - Fix delete function for NautobotValidatedSoftware so UUID is used to find object instead of querying for Platform and Software object.
- [#612](https://github.com/nautobot/nautobot-app-ssot/issues/612) - Fixed AttributeError on attempting to load Platforms with no Manufacturer assigned.
- [#614](https://github.com/nautobot/nautobot-app-ssot/issues/614) - Fixed creating platforms with no Manufacturer assigned.
- [#614](https://github.com/nautobot/nautobot-app-ssot/issues/614) - Fixed time_zone attribute normalization on Location objects.
- [#616](https://github.com/nautobot/nautobot-app-ssot/issues/616) - Ensure Devices missing Platform are not loaded from DNA Center.

### Documentation

- [#585](https://github.com/nautobot/nautobot-app-ssot/issues/585) - Fix documentation for Bootstrap installation.
- [#605](https://github.com/nautobot/nautobot-app-ssot/issues/605) - Add missing acknowledgements for a few integrations.

### Housekeeping

- [#585](https://github.com/nautobot/nautobot-app-ssot/issues/585) - Disabled the BootstrapDataTarget Job as it's not usable at this time.
- [#587](https://github.com/nautobot/nautobot-app-ssot/issues/587) - Changed model_class_name in .cookiecutter.json to a valid model to help with drift management.
- [#593](https://github.com/nautobot/nautobot-app-ssot/issues/593) - Add code owners for DNA Center, Meraki, and Itential integrations.
- [#599](https://github.com/nautobot/nautobot-app-ssot/issues/599) - Consolidated repeat function, parse_hostname_for_role(), from DNA Center and Citrix integrations as SSoT utility function.
- [#605](https://github.com/nautobot/nautobot-app-ssot/issues/605) - Add code owner for Citrix ADM integration.
- [#607](https://github.com/nautobot/nautobot-app-ssot/issues/607) - Remove redundant parse_hostname_for_role() function in Meraki integration that was missed in 599.
