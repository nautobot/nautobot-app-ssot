
# v3.8 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

This release has a new IPFabric feature for syncing the Device Role using the Device Type. There were also a lot of bugfixes for a few integrations and performance improvements by adding an index to a few fields on the Sync and SyncLogEntry classes.

## [v3.8.0 (2025-05-16)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.8.0)

### Added

- [#812](https://github.com/nautobot/nautobot-app-ssot/issues/812) - Added `ipfabric_sync_ipf_dev_type_to_role` flag to IP Fabric SSoT integration defaulting to True. Disabling this flag will prevent the sync of device types to device roles in IP Fabric and use the default device role mapping for new devices.
- [#813](https://github.com/nautobot/nautobot-app-ssot/issues/813) - Added IP Fabric Site Filter using Attribute Filters when a Nautobot Location Filter is used in the SSoT integration to optimize performance.
- [#7154](https://github.com/nautobot/nautobot-app-ssot/issues/7154) - Added db_index to start_time in Sync
- [#7154](https://github.com/nautobot/nautobot-app-ssot/issues/7154) - Added db_index to timestamp in SyncLogEntry

### Fixed

- [#467](https://github.com/nautobot/nautobot-app-ssot/issues/467) - Fixed gRPC error during get_devices() call in CVP integration.
- [#796](https://github.com/nautobot/nautobot-app-ssot/issues/796) - Fixed incorrect URL used in CloudVision integration when attempting to connect to portal and get version.
- [#802](https://github.com/nautobot/nautobot-app-ssot/issues/802) - Fix TypeError `contrib.sorting` for issue #802.
- [#807](https://github.com/nautobot/nautobot-app-ssot/issues/807) - Fixed Meraki integration creating duplicate IPAddresses with same host address.
- [#811](https://github.com/nautobot/nautobot-app-ssot/issues/811) - Fixed the number of API calls to IP Fabric resulting in non-optimal performance causing SSoT synchronization timeouts.
- [#814](https://github.com/nautobot/nautobot-app-ssot/issues/814) - Removed `ipfabric_allow_duplicate_addresses` flag as it is not implemented in the IP Fabric integration.
- [#815](https://github.com/nautobot/nautobot-app-ssot/issues/815) - Fixed return of `nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.Device.create` method to return the newly created device so child objects are also synchronized and job succeeds without failures.
- [#816](https://github.com/nautobot/nautobot-app-ssot/issues/816) - Fixed sorting bug for types without `__annotation__`.
- [#819](https://github.com/nautobot/nautobot-app-ssot/issues/819) - Fix check before loading ValidatedSoftware Model.

### Housekeeping

- Rebaked from the cookie `nautobot-app-v2.5.0`.

## [v3.8.1 (2025-05-16)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.8.1)

### Changed

- [#822](https://github.com/nautobot/nautobot-app-ssot/issues/822) - Disabled auto sorting in SSoT.
