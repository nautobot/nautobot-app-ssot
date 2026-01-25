# v4.1 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

This release brings exciting improvements to the platform’s performance and stability. The most notable addition is the support for parallel processing of each System of Records’ Adapters. As a result, loading data from Nautobot and your external system should now be significantly faster, with an average improvement of 30 to 50%. However, this feature is currently disabled by default. This is because each integration must undergo rigorous testing and verification to ensure compatibility with this enhancement before it becomes enabled by default. Developers interested in utilizing this feature will need to save the `parallel_loading` keyword argument in their Job’s `run()` method, similar to the `debug` argument.

<!-- towncrier release notes start -->


## [v4.1.0 (2026-01-21)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v4.1.0)

### Added

- [#36](https://github.com/nautobot/nautobot-app-ssot/issues/36) - Added ability to process data from both Systems of Record concurrently.
- [#1030](https://github.com/nautobot/nautobot-app-ssot/issues/1030) - Added ability to manage branch specific values for models in Bootstrap integration.
- [#1069](https://github.com/nautobot/nautobot-app-ssot/issues/1069) - Added support for Arista, F5 Networks, and Juniper to SolarWinds platform detection.

### Changed

- [#978](https://github.com/nautobot/nautobot-app-ssot/issues/978) - Moved Class validations for `nautobot_ssot.contrib.adapter.NautobotAdapter` to validate during `__init__`.

### Removed

- [#1035](https://github.com/nautobot/nautobot-app-ssot/issues/1035) - Removed breadcrumbs from Dashboard, History, Logs, and Itential Automation Gateway list views.

### Fixed

- [#1023](https://github.com/nautobot/nautobot-app-ssot/issues/1023) - Fix plugin initialization by moving config logic inside of ready()
- [#1049](https://github.com/nautobot/nautobot-app-ssot/issues/1049) - Fixed filtering bug inside log table within sync view.
- [#1055](https://github.com/nautobot/nautobot-app-ssot/issues/1055) - Fixed a performance issue with the SSoT log entries table view.
- [#1065](https://github.com/nautobot/nautobot-app-ssot/issues/1065) - Ensured that SSL verification is passed to request directly to fix communication to instances with self-signed certificates.
- [#1070](https://github.com/nautobot/nautobot-app-ssot/issues/1070) - Fixed duplicate logging that was occurring when using parallel processing option and ensured Job logger restored.

### Housekeeping

- Rebaked from the cookie `nautobot-app-v3.0.0`.
