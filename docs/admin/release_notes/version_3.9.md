
# v3.9 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

This release brings several significant additions and changes:

- A new VMware vSphere integration!
- CVE-2022-42969 has been successfully fixed!
- Sync and sync logs are now searchable in the global search!
- The example Jobs now support synchronizing Tags on appropriate objects between Nautobot instances.
- All integrations that utilize the contrib pattern will automatically support [Object Metadata](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/objectmetadata/) being added to their models.

## [v3.9.0 (2025-06-25)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.9.0)

### Added

- [#500](https://github.com/nautobot/nautobot-app-ssot/issues/500) - Added VMWare vSphere Integration.
- [#836](https://github.com/nautobot/nautobot-app-ssot/issues/836) - Added `hide_in_diff_view` flag for `Sync` and `SyncLogEntry` to hide those models in version control diff view.
- [#840](https://github.com/nautobot/nautobot-app-ssot/issues/840) - Added support for synchronizing Tags between Nautobot instances for objects that support them in example Jobs.
- [#847](https://github.com/nautobot/nautobot-app-ssot/issues/847) - Added `get_orm_attribute` function and tests.
- [#847](https://github.com/nautobot/nautobot-app-ssot/issues/847) - Added `load_typed_dict` function and tests.
- [#850](https://github.com/nautobot/nautobot-app-ssot/issues/850) - Added Sync and SyncLogEntry to the searchable_models definition.
- [#853](https://github.com/nautobot/nautobot-app-ssot/issues/853) - Added `orm_attribute_lookup` utility function.

### Changed

- [#632](https://github.com/nautobot/nautobot-app-ssot/issues/632) - Enhance contrib to support object metadata.
- [#810](https://github.com/nautobot/nautobot-app-ssot/issues/810) - Moved caching in `NautobotAdapter` to dedicated class.
- [#847](https://github.com/nautobot/nautobot-app-ssot/issues/847) - Moved `nautobot_ssot/utils.py` to `nautobot_ssot/utils/__init__.py`
- [#853](https://github.com/nautobot/nautobot-app-ssot/issues/853) - Changed references in `NautobotAdapter` to point to utility functions.
- [#865](https://github.com/nautobot/nautobot-app-ssot/issues/865) - added closing bracket to example on docs

### Fixed

- [#678](https://github.com/nautobot/nautobot-app-ssot/issues/678) - - Removes Retry dependency, which in turn removes py depencency, thereby fixing CVE https://nvd.nist.gov/vuln/detail/CVE-2022-42969
- [#678](https://github.com/nautobot/nautobot-app-ssot/issues/678) - - Re-implements retry decorator
- [#784](https://github.com/nautobot/nautobot-app-ssot/issues/784) - Change _handle_to_many_relationship from static method to instance method
- [#807](https://github.com/nautobot/nautobot-app-ssot/issues/807) - Redo of fix for Meraki IP duplication bug.
- [#830](https://github.com/nautobot/nautobot-app-ssot/issues/830) - Fixed top_level list not being properly generated for software models.
- [#831](https://github.com/nautobot/nautobot-app-ssot/issues/831) - Refactored handling of various Nautobot versions and Device Lifecycle Management app handling Software, SoftwareImage, and ValidatedSoftware models being synced.
- [#842](https://github.com/nautobot/nautobot-app-ssot/issues/842) - Fixed IP version bug in Meraki integration on AP uplink ports.
- [#845](https://github.com/nautobot/nautobot-app-ssot/issues/845) - Fix DNA Center integration to ensure Meraki devices aren't included in the failed device list if the `import_meraki` setting is False.
- [#845](https://github.com/nautobot/nautobot-app-ssot/issues/845) - Fixed duplicate IPAddressToInterface diffs being created due to mask_length being included as identifier in DNA Center integration.
- [#859](https://github.com/nautobot/nautobot-app-ssot/issues/859) - Fixed a bug where the cache persisted between sync executions in the Infoblox integration.

### Documentation

- [#856](https://github.com/nautobot/nautobot-app-ssot/issues/856) - Added a note to the developer upgrade documentation to explain the default value for text fields declared with `blank=True, null=False`.
- [#870](https://github.com/nautobot/nautobot-app-ssot/issues/870) - Updated installation steps for vSphere integration.

## [v3.9.1 (2025-07-09)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.9.1)

### Release Overview

Please note that the behavior in the SNOW integration now is to swallow and log an overview of how many duplicates encountered, and provide file output outlining what duplicates were encountered.

### Changed

- [#874](https://github.com/nautobot/nautobot-app-ssot/issues/874) - Reverted changes in `NautobotModel` to be backwards compatible with other integrations.
- [#874](https://github.com/nautobot/nautobot-app-ssot/issues/874) - Reverted removal of `invalidate_cache` method in `NautobotAdapter`.

### Fixed

- [#844](https://github.com/nautobot/nautobot-app-ssot/issues/844) - Fixed job failure if there are duplicate devices in LibreNMS. Will skip device instead.
- [#867](https://github.com/nautobot/nautobot-app-ssot/issues/867) - Gracefully swallow ServiceNow exceptions
- [#867](https://github.com/nautobot/nautobot-app-ssot/issues/867) - Adds ServiceNow duplicate file reports
- [#867](https://github.com/nautobot/nautobot-app-ssot/issues/867) - Fixes ServiceNow comparison filters to only compare against company names with Manufacturer set to True

## [v3.9.2 (2025-08-08)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.9.2)

### Added

- [#860](https://github.com/nautobot/nautobot-app-ssot/issues/860) - Added `nautobot_ssot.utils.orm.get_custom_relationship_association_parameters` utility function.
- [#860](https://github.com/nautobot/nautobot-app-ssot/issues/860) - Added `nautobot_ssot.utils.orm.get_custom_relationship_associations` utility function.
- [#860](https://github.com/nautobot/nautobot-app-ssot/issues/860) - Added `nautobot_ssot.utils.typing.get_inner_type` utility function.

### Changed

- [#860](https://github.com/nautobot/nautobot-app-ssot/issues/860) - Changed `nautobot_ssot.contrib.adapter.NautobotAdapter` to use new `orm` and `typing` utility functions.

### Fixed

- [#596](https://github.com/nautobot/nautobot-app-ssot/issues/596) - Handles HTTP 404 exception case for expired A record and PTR reference, and logs as a warning instead of failing the job run.
- [#881](https://github.com/nautobot/nautobot-app-ssot/issues/881) - Fixed exception caused by missing secret value when creating a SecretsGroup with Bootstrap.
- [#904](https://github.com/nautobot/nautobot-app-ssot/issues/904) - Fixed exception caused by missing software version when creating ValidatedSoftware with Bootstrap.
- [#916](https://github.com/nautobot/nautobot-app-ssot/issues/916) - Fixed bootstrap signal DLM checks.
- [#921](https://github.com/nautobot/nautobot-app-ssot/issues/921) - Fixed missing Prefix bug in Meraki integration.
- [#926](https://github.com/nautobot/nautobot-app-ssot/issues/926) - Fixed issue with metadata_type when contrib models are used without the contrib adapter.

### Documentation

- [#925](https://github.com/nautobot/nautobot-app-ssot/issues/925) - Added Analytics GTM template override only to the public ReadTheDocs build.

## [v3.9.3 (2025-09-09)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.9.3)

### Added

- [#913](https://github.com/nautobot/nautobot-app-ssot/issues/913) - Added the enable_global_search configuration option to control whether the Nautobot global search includes synclogs.
- [#938](https://github.com/nautobot/nautobot-app-ssot/issues/938) - Added support for Object Metadata in the Bootstrap integration.
- [#948](https://github.com/nautobot/nautobot-app-ssot/issues/948) - Added ExternalIntegration creation to Bootstrap integration.

### Fixed

- [#548](https://github.com/nautobot/nautobot-app-ssot/issues/548) - Improved performance of the SSoT Sync history page by removing an unnecessary log prefetch and deferring large JSON fields.
- [#596](https://github.com/nautobot/nautobot-app-ssot/issues/596) - Use required default arg ("msg") instead of kwarg ("message") when using self.job.logger.
- [#723](https://github.com/nautobot/nautobot-app-ssot/issues/723) - Fixed `_handle_single_parameter` metadata key vs name inconsistency.
- [#910](https://github.com/nautobot/nautobot-app-ssot/issues/910) - Fixed Service Now caching sys_ids causing objects to not be created.
- [#936](https://github.com/nautobot/nautobot-app-ssot/issues/936) - Fixed creation of "Unknown" location when running LibreNMS integration in dry run mode.
- [#940](https://github.com/nautobot/nautobot-app-ssot/issues/940) - Fixed error in Citrix ADM integration when attempting to assign an IP Address to an Interface.
- [#947](https://github.com/nautobot/nautobot-app-ssot/issues/947) - Fixed Advanced Filters for Infoblox Config and Automation Gateway Management.
- [#953](https://github.com/nautobot/nautobot-app-ssot/issues/953) - Fixed an issue in the Cisco DNA Center integration where devices with unmapped platforms were silently skipped during synchronization, resulting in an incomplete inventory

### Housekeeping

- [#954](https://github.com/nautobot/nautobot-app-ssot/issues/954) - Update ruff to target Python 3.9
- Rebaked from the cookie `nautobot-app-v2.5.1`.

## New Contributors

* @cdtomkins made their first contribution in https://github.com/nautobot/nautobot-app-ssot/pull/929
* @kacem-expereo made their first contribution in https://github.com/nautobot/nautobot-app-ssot/pull/933
* @fpocai made their first contribution in https://github.com/nautobot/nautobot-app-ssot/pull/944
* @rodrigogbranco made their first contribution in https://github.com/nautobot/nautobot-app-ssot/pull/953
* @robertoduarte-codilime made their first contribution in https://github.com/nautobot/nautobot-app-ssot/pull/952
