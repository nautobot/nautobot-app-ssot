# v3.7 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

This release focuses on bugfixes for the DNA Center, Citrix ADM, Bootstrap and Slurpit integrations along with some dependency updates.

## [v3.7.0 (2025-05-07)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.7.0)

### Added

- [#457](https://github.com/nautobot/nautobot-app-ssot/issues/457) - Added `sort_relationships()` helper function
- [#457](https://github.com/nautobot/nautobot-app-ssot/issues/457) - Added tests for `sort_relationships()` helper function
- [#457](https://github.com/nautobot/nautobot-app-ssot/issues/457) - Added call to `sort_relationships()` function in contrib `NautobotAdapter`

### Fixed

- [#708](https://github.com/nautobot/nautobot-app-ssot/issues/708) - Fixes Device Building, parent Area if the location_map feature is used.
- [#708](https://github.com/nautobot/nautobot-app-ssot/issues/708) - Also reverted 724 as there should only be one host address ever found as I originally thought.
- [#760](https://github.com/nautobot/nautobot-app-ssot/issues/760) - Fixed issue causing bootstrap scheduled_job to fail when updating the User field.
- [#767](https://github.com/nautobot/nautobot-app-ssot/issues/767) - Fixed IPAddressToInterface model in DNA Center by adding mask_length as identifier. This should allow multiple IPAddresses with same host address.
- [#772](https://github.com/nautobot/nautobot-app-ssot/issues/772) - The default value for the Network Views to Nautobot Namespace setting in the Infoblox integration should be a dictionary, not a list.
- [#778](https://github.com/nautobot/nautobot-app-ssot/issues/778) - Fixed description and tags not updating on Prefix objects after creation.
- [#780](https://github.com/nautobot/nautobot-app-ssot/issues/780) - Fixes syncing devices without a Lat/Long defined in Slurpit.
- [#781](https://github.com/nautobot/nautobot-app-ssot/issues/781) - Fixes syncing devices if they do not have a site defined in Slurpit by adding a default location.
- [#787](https://github.com/nautobot/nautobot-app-ssot/issues/787) - Add `SKIP_UNMATCHED_DST` to Slurpit sync.
- [#793](https://github.com/nautobot/nautobot-app-ssot/issues/793) - Fixed search for parent Prefix of IPAddress to include Namespace to avoid getting multiple results in Citrix ADM integration.
- [#793](https://github.com/nautobot/nautobot-app-ssot/issues/793) - Fixed DNA Center loading of Controller locations with missing parent.

### Dependencies

- [#709](https://github.com/nautobot/nautobot-app-ssot/issues/709) - Update packaging and ipfabric dependencies to allow newer versions to be used.
- [#764](https://github.com/nautobot/nautobot-app-ssot/issues/764) - Update dependency for Device Lifecycle Management App to allow use of 3.x with the various integrations.
