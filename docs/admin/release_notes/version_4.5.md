# v4.5 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Added opt-in progress logging to the contrib `NautobotAdapter`, so large syncs emit periodic "objects loaded" messages to the job log instead of running silently through the load phase. Enable it under with `enable_progress_logger: True` in your `PLUGINS_CONFIG` (defaults to `False`) and tune how often messages are logged with `progress_logger_interval` (number of objects between log lines, defaults to `1000`; `0` disables it)
- SSoT jobs can now suppress Nautobot's automatic Device/Module component instantiation during a sync. Opt in via a `DataSyncBaseJob` class attribute, the `PLUGINS_CONFIG` global setting, or the `SkipAutoComponentCreation` context manager directly (any source enabling it wins). Default behavior is unchanged for jobs that don't opt in, and the feature degrades gracefully (no-op plus a one-time warning) on Nautobot versions that lack the underlying core extension point.
- Added a generic `ObjectMetadataAnnotation` to `nautobot_ssot.contrib`, letting any contrib `NautobotModel` DiffSync model read and write a field's value to Nautobot `ObjectMetadata`. Reads are lenient (missing type/row resolves to `None`) and prefetched to avoid N+1 queries; writes are strict and idempotent, with None treated as a no-op.

<!-- towncrier release notes start -->

## [v4.5.0 (2026-06-29)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v4.5.0)

### Added

- [#304](https://github.com/nautobot/nautobot-app-ssot/issues/304) - Added configurable logging to log progress when using contrib adapter.
- [#1226](https://github.com/nautobot/nautobot-app-ssot/issues/1226) - Added `skip_auto_component_creation` opt-in for SSoT jobs, suppressing Nautobot's automatic Device/Module component instantiation during sync via Nautobot core's `nautobot.apps.dcim.SkipAutoComponentCreation` extension point (nautobot/nautobot#9026).
- [#1249](https://github.com/nautobot/nautobot-app-ssot/issues/1249) - Added `ObjectMetadataAnnotation` to `nautobot_ssot.contrib`, letting DiffSync models on the `NautobotModel` base read and write a field's value to Nautobot ObjectMetadata.
- [#1261](https://github.com/nautobot/nautobot-app-ssot/issues/1261) - Added the `aristacv_delete_ipaddresses_on_sync` setting to the Arista CloudVision integration to allow for the deletion of IP addresses that are present in Nautobot but not present in CloudVision (defaults to False).
- [#1275](https://github.com/nautobot/nautobot-app-ssot/issues/1275) - Added automatic `sysparm_fields` selection to the ServiceNow integration so each table load only requests the columns referenced by its mappings, and made the ServiceNow page size (`limit`) configurable.

### Fixed

- [#NTC-5652](https://github.com/nautobot/nautobot-app-ssot/issues/NTC-5652) - Change MTU in DNA Center integration to account for 0 as an output from DNAC and save it in Nautobot as None.
- [#791](https://github.com/nautobot/nautobot-app-ssot/issues/791) - Fixed two latent bugs in the SSoT contrib adapter and model where custom-relationship error handlers referenced attributes that do not exist (a model instance's `__name__` and `Relationship.name`), raising `AttributeError` instead of the intended warning/error message.
- [#1159](https://github.com/nautobot/nautobot-app-ssot/issues/1159) - Fixed Meraki SSoT crashing Nautobot startup with `MultipleObjectsReturned` when more than one Platform name contains "Meraki", by looking up the canonical `Cisco Meraki` Platform by exact name instead of `name__icontains`.
- [#1205](https://github.com/nautobot/nautobot-app-ssot/issues/1205) - Fixed Meraki SSoT assigning the management/primary IP from a Not-Active uplink: an inactive static uplink no longer sets `mgmt_ip`, so it cannot shadow an Active uplink or suppress the DHCP management-IP fallback.
- [#1211](https://github.com/nautobot/nautobot-app-ssot/issues/1211) - Fixed Infoblox SSoT sync bug - blanking out Infoblox `comment` field when any field of nautobot Prefix object gets updated
- [#1222](https://github.com/nautobot/nautobot-app-ssot/issues/1222) - Fix Meraki firewall port loading when devices have no uplink IP configured.
- [#1235](https://github.com/nautobot/nautobot-app-ssot/issues/1235) - Fixed token authentication against on-premise Arista CloudVision portals.
- [#1238](https://github.com/nautobot/nautobot-app-ssot/issues/1238) - Resolve KeyError in LibreNMS if IP is missing.
- [#1239](https://github.com/nautobot/nautobot-app-ssot/issues/1239) - Resolve version parsing on newer Citrix devices.
- [#1245](https://github.com/nautobot/nautobot-app-ssot/issues/1245) - Fixed Arista CloudVision SSoT sync failing when attributes are streamed in multiple gRPC notification frames.
- [#1250](https://github.com/nautobot/nautobot-app-ssot/issues/1250) - Fixed vSphere SSoT sync crash when more than one `IPAddress` shares the primary IP host, by catching `MultipleObjectsReturned` during primary IP assignment.
- [#1257](https://github.com/nautobot/nautobot-app-ssot/issues/1257) - Moved any non-testing imports of nautobot_ssot.tests.contrib_base_classes.py over to nautobot_ssot.contrib to avoid test dependency loading in a non-dev environment.
- [#1258](https://github.com/nautobot/nautobot-app-ssot/issues/1258) - Fixed handling children when child attribute is OneToOneField.
- [#1261](https://github.com/nautobot/nautobot-app-ssot/issues/1261) - Fixed the Arista CloudVision integration attempting to create an IP address that already existed in Nautobot.
- [#1274](https://github.com/nautobot/nautobot-app-ssot/issues/1274) - Fixed a bug in the LibreNMS integration where the port parameter was not passed to the parent ApiEndpoint class, causing all connections to default to port 443 regardless of the configured port.
- [#1275](https://github.com/nautobot/nautobot-app-ssot/issues/1275) - Fixed ServiceNow integration silently truncating tables larger than 10,000 rows; `all_table_entries()` now paginates through the entire result set.
- [#1275](https://github.com/nautobot/nautobot-app-ssot/issues/1275) - Fixed ServiceNow integration raising a spurious `ObjectNotUpdated` on successful updates; updates now write and verify only the mapped fields and key on the record's known `sys_id`, instead of comparing server-managed columns such as `sys_updated_on`.

### Housekeeping

- [#791](https://github.com/nautobot/nautobot-app-ssot/issues/791) - Reorganized the SSoT `contrib` unit tests into the `nautobot_ssot/tests/contrib/` subpackage and brought the entire `contrib` module to 100% test coverage.
- [#1248](https://github.com/nautobot/nautobot-app-ssot/issues/1248) - Fixed a test that was failing due to a recent change in Nautobot's next branch for 3.2.0.
- [#1248](https://github.com/nautobot/nautobot-app-ssot/issues/1248) - Fixed many test cases that were using TransactionTestCase when TestCase was acceptable.
- [#1248](https://github.com/nautobot/nautobot-app-ssot/issues/1248) - Fixed some of the test cases that were failing when running with --keepdb.
- [#1248](https://github.com/nautobot/nautobot-app-ssot/issues/1248) - Fixed all test cases to correctly import from nautobot.apps instead of nautobot.core or django.test.
- [#1255](https://github.com/nautobot/nautobot-app-ssot/issues/1255) - Increased unit test coverage of the core (non-integration) `nautobot_ssot` modules to 100%, adding tests for the SSoT jobs base class, Prometheus metrics, views and detail-page panels, models, template content, utility helpers, custom exceptions, and the app, URL, and navigation integration-loading hooks.
- [#1255](https://github.com/nautobot/nautobot-app-ssot/issues/1255) - Reorganized the jobs tests so shared behavior runs once -- using `TestCase` except for the parallel-loading path that requires `TransactionTestCase` -- made the Status-dependent test setups self-sufficient so the suite no longer fails when re-run with `--keepdb`, and replaced flaky wall-clock timing assertions with a deterministic thread-barrier concurrency check that no longer fails intermittently on busy CI runners.
