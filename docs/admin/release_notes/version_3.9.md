
# v3.9 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

This release brings several significant additions and changes:

- A new VMware vSphere integration!
- CVE-2022-42969 has been successfully fixed!
- Sync and sync logs are now searchable in the global search!
- The example Jobs now support synchronizing Tags on appropriate objects between Nautobot instances.
- All integrations that utilize the contrib pattern will automatically support [Object Metadata](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/objectmetadata/) being added to their models.

## [v3.9.0 (2025-06-20)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.9.0)

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
- [#830](https://github.com/nautobot/nautobot-app-ssot/issues/830) - Fixed top_level list not being properly generated for software models.
- [#831](https://github.com/nautobot/nautobot-app-ssot/issues/831) - Refactored handling of various Nautobot versions and Device Lifecycle Management app handling Software, SoftwareImage, and ValidatedSoftware models being synced.
- [#842](https://github.com/nautobot/nautobot-app-ssot/issues/842) - Fixed IP version bug in Meraki integration on AP uplink ports.
- [#845](https://github.com/nautobot/nautobot-app-ssot/issues/845) - Fix DNA Center integration to ensure Meraki devices aren't included in the failed device list if the `import_meraki` setting is False.
- [#845](https://github.com/nautobot/nautobot-app-ssot/issues/845) - Fixed duplicate IPAddressToInterface diffs being created due to mask_length being included as identifier in DNA Center integration.
- [#859](https://github.com/nautobot/nautobot-app-ssot/issues/859) - Fixed a bug where the cache persisted between sync executions in the Infoblox integration.

### Documentation

- [#856](https://github.com/nautobot/nautobot-app-ssot/issues/856) - Added a note to the developer upgrade documentation to explain the default value for text fields declared with `blank=True, null=False`.
