# v4.4 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Added significant performance improvements to the IP Fabric integration

<!-- towncrier release notes start -->

## [v4.4.0 (2026-06-01)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v4.4.0)

### Added

- [#1214](https://github.com/nautobot/nautobot-app-ssot/issues/1214) - Added thread safe caching for Nautobot objects an prefetching to reduce query overhead

### Fixed

- [#1203](https://github.com/nautobot/nautobot-app-ssot/issues/1203) - Fixed an AttributeError in Infoblox SSoT integration when updating Prefix VLAN assignments.
- [#1236](https://github.com/nautobot/nautobot-app-ssot/issues/1236) - Fixed vSphere SSoT source load crashing when vSphere contains duplicate VM names within a cluster.
- Fixed vSphere SSoT `sync_complete` raising `IPAddress.DoesNotExist` when a primary IP was not present in Nautobot.
- Fixed vSphere SSoT `VirtualMachineModel.update` omitting `cluster__name` from the lookup used in `sync_complete`.
