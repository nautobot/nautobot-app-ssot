
# v3.10 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Mitigate CVE by enforcing permissions on the ServiceNow Config view.
- Minimum Nautobot version is now 2.4.20.
- Minimum Python version is now 3.10.

## [v3.10.0 (2025-10-21)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.10.0)

### Security

- [#991](https://github.com/nautobot/nautobot-app-ssot/issues/991) - Enforce permissions on ServiceNow Config view to mitigate https://github.com/nautobot/nautobot-app-ssot/security/advisories/GHSA-535g-62r7-cx6v.

### Added

- [#877](https://github.com/nautobot/nautobot-app-ssot/issues/877) - Added contrib base classes `BaseNautobotAdapter` and `BaseNautobotModel`.

### Fixed

- [#878](https://github.com/nautobot/nautobot-app-ssot/issues/878) - Fixed inability of vSphere integration to sync IPv6 addresses
- [#964](https://github.com/nautobot/nautobot-app-ssot/issues/964) - Fixes sync of anycast IPs for CloudVision SSOT.
- [#964](https://github.com/nautobot/nautobot-app-ssot/issues/964) - Implements tag deduplication for CloudVision SSOT.
- [#964](https://github.com/nautobot/nautobot-app-ssot/issues/964) - Removes log noise when duplicate IP or IPAssignments are found by CloudVision SSOT.
- [#964](https://github.com/nautobot/nautobot-app-ssot/issues/964) - Fixes cert failures for CloudVision SSOT CVaaS implementations (verify cert = False). Such cases can happen when SSL inspection for nautobot workers is in place.
- [#980](https://github.com/nautobot/nautobot-app-ssot/issues/980) - Fix Bootstrap SoftwareVersion deletion error.
- [#982](https://github.com/nautobot/nautobot-app-ssot/issues/982) - Fixed Exception when attempting to delete Software referenced by a Device.

### Housekeeping

- [#984](https://github.com/nautobot/nautobot-app-ssot/issues/984) - Removed redundant nautobot minimum version check in jobs module.
- [#991](https://github.com/nautobot/nautobot-app-ssot/issues/991) - Implemented UIViewSets and Component UI.
- Rebaked from the cookie `nautobot-app-v2.6.0`.
