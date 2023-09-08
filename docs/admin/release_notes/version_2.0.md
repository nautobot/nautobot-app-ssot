
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

- Updated everything to support Nautobot 2.0.0rc1
- Fixed use of slug on Platform in Arista CVP integration.

## v2.0.0-rc.2 - 2023-09-8

### Changed

- Updated everything to support Nautobot 2.0.0rc2
