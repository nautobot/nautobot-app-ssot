# v1.6 Release Notes

## v1.6.0 - 2023-09-29

## Added

- [221](https://github.com/nautobot/nautobot-plugin-ssot/pull/221) - Add Device42 integration by @jdrew82
- [222](https://github.com/nautobot/nautobot-plugin-ssot/pull/222) - Add conflicting message link by @snaselj
- [224](https://github.com/nautobot/nautobot-plugin-ssot/pull/224) - Allow Skipping Conflicting Apps Check by @snaselj

## Changed

- [219](https://github.com/nautobot/nautobot-plugin-ssot/pull/219) - Attempt fixing CI error in #214 by @Kircheneer
- [220](https://github.com/nautobot/nautobot-plugin-ssot/pull/220) - Update ci.yml by @Kircheneer
- [214](https://github.com/nautobot/nautobot-plugin-ssot/pull/214) - Sync Main to Develop for 1.5.0 by @jdrew82
- [218](https://github.com/nautobot/nautobot-plugin-ssot/pull/218) - Fixes contrib.NautobotModel not returning objects on update/delete by @Kircheneer
- [161](https://github.com/nautobot/nautobot-plugin-ssot/pull/161) - Reverts ChatOps dependency removal by @snaselj
- [213](https://github.com/nautobot/nautobot-plugin-ssot/pull/213) - fix: :bug: Several fixes in the ACI integration by @chadell
- [205](https://github.com/nautobot/nautobot-plugin-ssot/pull/205) - Migrate PR #164 from Arista Child Repo by @qduk

## v1.6.1 - 2024-02-21

## Fixed

- [243](https://github.com/nautobot/nautobot-app-ssot/pull/243) - Fix Infoblox import_subnet for ltm-1.6 by @jdrew82
- [261](https://github.com/nautobot/nautobot-app-ssot/pull/261) - Fix Device42 documentation. by @jdrew82

## Changed

- [245](https://github.com/nautobot/nautobot-app-ssot/pull/245) - IPFabric integration settings updates by @alhogan

- [357](https://github.com/nautobot/nautobot-app-ssot/pull/357) - Backport contrib changes to LTM by @Kircheneer
- [361](https://github.com/nautobot/nautobot-app-ssot/pull/361) - Backport of #350 by @Kircheneer
- [363](https://github.com/nautobot/nautobot-app-ssot/pull/363) - Backport #362 by @Kircheneer

## v1.6.2 - 2024-03-12

## Fixed

- [386](https://github.com/nautobot/nautobot-app-ssot/pull/386) - Fixes bug in backport of contrib custom relationship handling

## Changed

- [386](https://github.com/nautobot/nautobot-app-ssot/pull/386) - Improves error handling in contrib (backport of #374)
- [373](https://github.com/nautobot/nautobot-app-ssot/pull/373) - Change contrib.NautobotModel.get_from_db to use a PK (backport of #371)

## v1.6.3 - 2024-03-20

## Fixed

- [396](https://github.com/nautobot/nautobot-app-ssot/pull/396) - Fix custom one-to-many relationships (backport of #393)
- [396](https://github.com/nautobot/nautobot-app-ssot/pull/396) -
  Use `typing.get_args` in favor of accessing `__args__` directly (backport of #390)
- [396](https://github.com/nautobot/nautobot-app-ssot/pull/396) -
  Fixed issue with generic relationships and `NautobotAdapter.load` (backport of #388)
- [396](Fixed issue with generic relationships and `NautobotAdapter.load`.) -
  Allow foreign keys inside of many to many relationships (backport of #377)

## Housekeeping

- Replicate module and test module structure for contrib code in LTM branch

## Fixed

- [243](https://github.com/nautobot/nautobot-app-ssot/pull/243) - Fix Infoblox import_subnet for ltm-1.6 by @jdrew82
- [261](https://github.com/nautobot/nautobot-app-ssot/pull/261) - Fix Device42 documentation. by @jdrew82
- [419](https://github.com/nautobot/nautobot-app-ssot/pull/419) - Fix Device42 Plugin Settings for LTM by @jdrew82

## Changed

- [245](https://github.com/nautobot/nautobot-app-ssot/pull/245) - IPFabric integration settings updates by @alhogan
- [357](https://github.com/nautobot/nautobot-app-ssot/pull/357) - backport contrib changes to LTM by @Kircheneer
- [361](https://github.com/nautobot/nautobot-app-ssot/pull/361) - Backport of #350 by @Kircheneer
- [363](https://github.com/nautobot/nautobot-app-ssot/pull/363) - Backport #362 by @Kircheneer
- [373](https://github.com/nautobot/nautobot-app-ssot/pull/373) - change contrib.NautobotModel.get_from_db to use a PK by @Kircheneer
