
# v2.5 Release Notes

## [v2.5.0 (2024-03-20)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v2.5.0)

### Added

- [#359](https://github.com/nautobot/nautobot-app-ssot/issues/359) - Added warning for Device Types with Interfaces.

### Changed

- [#343](https://github.com/nautobot/nautobot-app-ssot/issues/343) - Replaced pydocstyle with ruff.
- [#390](https://github.com/nautobot/nautobot-app-ssot/issues/390) - Use typing.get_args in contrib in favor of accessing __args__.

### Fixed

- [#377](https://github.com/nautobot/nautobot-app-ssot/issues/377) - Allow foreign keys inside of many to many relationships.
- [#380](https://github.com/nautobot/nautobot-app-ssot/issues/380) - Fixed issue with generic relationships and `NautobotAdapter.load`.
- [#393](https://github.com/nautobot/nautobot-app-ssot/issues/393) - Fixed custom 1 to many contrib management
- [#395](https://github.com/nautobot/nautobot-app-ssot/issues/395) - Fix examples.py Jobs

### Housekeeping

- [#8](https://github.com/nautobot/nautobot-app-ssot/issues/8), [#394](https://github.com/nautobot/nautobot-app-ssot/issues/394) - Re-baked from the latest template.
- [#384](https://github.com/nautobot/nautobot-app-ssot/issues/384) - Re-baked from the latest template `nautobot-app-v2.2.0`.
