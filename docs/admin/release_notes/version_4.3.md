# v4.3 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Added support for loading port-channels as part of the Arista CloudVision integration
- Fixed bugs across multiple integrations (e.g., AristaCV, vSphere, Infoblox)

<!-- towncrier release notes start -->

## [v4.3.0 (2026-05-18)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v4.3.0)

### Added

- [#1192](https://github.com/nautobot/nautobot-app-ssot/issues/1192) - Added support for syncing Arista Port-Channel interfaces and their member assignments from CloudVision.

### Changed

- [#1206](https://github.com/nautobot/nautobot-app-ssot/issues/1206) - Optimized AristaCV SSoT device loading by fetching interface modes, transceivers, and descriptions once per device.

### Deprecated

- [#1174](https://github.com/nautobot/nautobot-app-ssot/issues/1174) - Deprecated `nautobot_ssot.integrations.aristacv.utils.cloudvision.get_cvp_version` in favor of `CloudvisionApi(config).get_version()`.

### Fixed

- [#753](https://github.com/nautobot/nautobot-app-ssot/issues/753) - Fixed `AttributeError: 'dict' object has no attribute '<key>'` when a diffsync model attribute traverses a Nautobot JSON field such as `_custom_field_data`, including through a foreign key (for example `vlan___custom_field_data__my_key`).
- [#1045](https://github.com/nautobot/nautobot-app-ssot/issues/1045) - Fixed `nautobot-server dumpdata nautobot_ssot` failing with `ProgrammingError: relation "nautobot_ssot_ssotconfig" does not exist` by giving the unmanaged `SSOTConfig` model a manager that returns an empty queryset.
- [#1173](https://github.com/nautobot/nautobot-app-ssot/issues/1173) - Fixed Arista SSoT integration to assign a device's software version on the first sync run.
- [#1173](https://github.com/nautobot/nautobot-app-ssot/issues/1173) - Fixed Arista SSoT integration to create new SoftwareVersion records with an Active status.
- [#1174](https://github.com/nautobot/nautobot-app-ssot/issues/1174) - Fixed Arista CloudVision integration to set the device's primary IP based on the IP CloudVision reports for the device, rather than only on Management interfaces.
- [#1176](https://github.com/nautobot/nautobot-app-ssot/issues/1176) - Fixed vSphere nautobot adapter sync_complete to handle missing VirtualMachine gracefully instead of raising DoesNotExist exception.
- [#1178](https://github.com/nautobot/nautobot-app-ssot/issues/1178) - Fixed Arista CloudVision SSoT `NautobotDevice.update()` to include the `status` attribute.
- [#1182](https://github.com/nautobot/nautobot-app-ssot/issues/1182) - Fixed the Arista CV integration get ip interfaces not accounting for intfID and ip address being in separate query responses.
- [#1183](https://github.com/nautobot/nautobot-app-ssot/issues/1183) - Fixed custom log groupings being discarded when parallel adapter loading was enabled.
- [#1189](https://github.com/nautobot/nautobot-app-ssot/issues/1189) - Removed reference to deleted `extras/inc/jobresult_js.html` template that was removed in Nautobot 3.1.0, which caused a `TemplateDoesNotExist` error on the Sync Job Logs tab.
- [#1192](https://github.com/nautobot/nautobot-app-ssot/issues/1192) - Fixed Arista CloudVision interface enumeration silently dropping interfaces that CloudVision returns in a multi-notification batch (commonly affects breakout/sub-port interfaces).
- [#1199](https://github.com/nautobot/nautobot-app-ssot/issues/1199) - Fixed missing descriptions on Loopback, SVI, and Port-Channel interfaces synced from Arista CloudVision.
- [#1202](https://github.com/nautobot/nautobot-app-ssot/issues/1202) - Fixes TypeError when passing multiple values for keyword argument 'sync' to super().run() in InfobloxDataSource by passing *args **kwargs cleanly.
- [#1206](https://github.com/nautobot/nautobot-app-ssot/issues/1206) - Fixed AristaCV `get_ip_interfaces` overwriting interface state when CloudVision coalesces notifications for multiple interfaces into a single gRPC batch.
- [#1208](https://github.com/nautobot/nautobot-app-ssot/issues/1208) - Fixed Infoblox SSoT sync not updating prefixes with `container` network type.
- [#1211](https://github.com/nautobot/nautobot-app-ssot/issues/1211) - Fixed the link on the Advanced tab for the Sync model to point to the API view.
- [#1213](https://github.com/nautobot/nautobot-app-ssot/issues/1213) - Fixed unittests for integrations that used outdated default LocationType parents

### Housekeeping

- Fixed markdownlint issues.
