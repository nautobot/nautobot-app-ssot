
# v2.0 Release Notes

## v2.0.0-beta.1 - 2023-07-13

### Added

- Added pylint-nautobot to dev dependencies.

### Changed

- Updated all imports to be derived from new module locations.
- Updated all models that no longer have slugs to use replacement field.
- Updated navigation to use new NavMenu elements.
- Updated metrics to use new Jobs model attributes.
- Updated example Jobs to use new Location model instead of Region/Site along with updating IPAddress to specify parent Prefix.
- Updated example Jobs to use new Job pattern with passed variables.
- Updated Job loading to use new register_jobs function.
- Updated logging in example Jobs to use new logger on JobResult.
- Updated Infoblox integration to work with Nautobot 2.0.
- Refactored Infoblox integration to have tags applied to imported objects after sync is complete.


## v2.0.0-beta.2 - 2023-08-16

### Added

- Added Cisco ACI, Arista CloudVision, and ServiceNow integrations

### Changed

- Updated Cisco ACI, Arista CloudVision, and ServiceNow integrations to work with Nautobot 2.0
- Updated ServiceNow Job to use load_source_adapter() and load_target_adapter() pattern
- Fixed Infoblox assignment of VRFs to Prefixes

## v2.0.0-rc.1 - 2023-08-24

### Added

- Added `network_driver` definition to Arista EOS Platform

### Changed

- [168](https://github.com/nautobot/nautobot-plugin-ssot/pull/168) - Update for Nautobot 2.0.0.rc1 Support by @jdrew82 in #168
- Fixed use of slug on Platform in Arista CVP integration.

## v2.0.0-rc.2 - 2023-09-8

### Changed

- [200](https://github.com/nautobot/nautobot-plugin-ssot/pull/200) - Enable RC2 Support by @jdrew82

## v2.0.0 - 2023-10-5

### Changed


- [228](https://github.com/nautobot/nautobot-plugin-ssot/pull/228) - Merge Main Back to Dev for 1.6.0 by @jdrew82
- [231](https://github.com/nautobot/nautobot-plugin-ssot/pull/231) - Update Device42 Integration for Nautobot 2.0 by @jdrew82
- [230](https://github.com/nautobot/nautobot-plugin-ssot/pull/230) - Update to Nautobot 2.0 by @jdrew82

## v2.0.1 - 2023-11-6

## Changed

- [242](https://github.com/nautobot/nautobot-plugin-ssot/pull/242) - Fix Infoblox import_subnets setting by @jdrew82
- [252](https://github.com/nautobot/nautobot-plugin-ssot/pull/252) - Add CODEOWNERS for the various integrations by @jdrew82
- [254](https://github.com/nautobot/nautobot-plugin-ssot/pull/254) - Add plugin-ssot as integration code owners by @jdrew82
- [251](https://github.com/nautobot/nautobot-plugin-ssot/pull/251) - Cookie initialy baked by NetworkToCode Cookie Drift Manager Tool by @snaselj
- [250](https://github.com/nautobot/nautobot-plugin-ssot/pull/250) - fixes possible error state in nautobot_ssot_duration_seconds metric by @Kircheneer
- [260](https://github.com/nautobot/nautobot-plugin-ssot/pull/260) - Fix Documentation for Device42 by @jdrew82
- [246](https://github.com/nautobot/nautobot-plugin-ssot/pull/246) - IPFabric integration settings updates for 2.0 by @alhogan
- [264](https://github.com/nautobot/nautobot-plugin-ssot/pull/264) - Add check for missing job_class attribute on 1.x Jobs by @jdrew82

## v2.0.2 - 2023-11-28

##  Changed

- [229](https://github.com/nautobot/nautobot-plugin-ssot/pull/229) - Add the ability to customize queryset used on NautobotModels by @qduk
- [259](https://github.com/nautobot/nautobot-plugin-ssot/pull/259) - add fix for issue #257 by @Renrut5
- [280](https://github.com/nautobot/nautobot-plugin-ssot/pull/280) - fixes tests / pylint warning by @Kircheneer
- [275](https://github.com/nautobot/nautobot-plugin-ssot/pull/275) - Fix CustomField Bug by @jdrew82
- [282](https://github.com/nautobot/nautobot-plugin-ssot/pull/282) - Fix CloudVision SSoT Jobs by @jdrew82
- [279](https://github.com/nautobot/nautobot-plugin-ssot/pull/279) - bug #266 by @gerardocastaldo
