# v3.11 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Improved reliability of SecretsGroup creation when multiple Secrets are associated.
- Corrected data type definitions and terminology for better consistency and clarity.
- Displayed SSOT job start times in the user’s local timezone.
- Updated Infoblox integration to prevent model synchronization errors.
- Rebaked from the latest Nautobot app cookie for compatibility.

## [v3.11.0 (2025-10-29)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.11.0)

### Fixed

- [#973](https://github.com/nautobot/nautobot-app-ssot/issues/973) - Fixes issue when creating new SecretsGroup's with Secrets associations not being created when more than one is specified.
- [#973](https://github.com/nautobot/nautobot-app-ssot/issues/973) - Provides additional checks to ensure secrets are specified before creating associations.
- [#975](https://github.com/nautobot/nautobot-app-ssot/issues/975) - - In the Bootstrap User Guide, changes the type for the longitude and latitude fields under the `Location` section from `str` to `float`.
- [#990](https://github.com/nautobot/nautobot-app-ssot/issues/990) - Show SSOT job start time in user-defined timezone
- [#996](https://github.com/nautobot/nautobot-app-ssot/issues/996) - Fixed Infoblox integration diffsync model trying to assign a Prefix to Location M2M before the Prefix has been saved.

### Housekeeping

- [#985](https://github.com/nautobot/nautobot-app-ssot/issues/985) - Corrected Nautobot destination terminology in InfoBlox integratin.
- Rebaked from the cookie `nautobot-app-v2.7.0`.
