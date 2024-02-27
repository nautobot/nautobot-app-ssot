
# v2.3 Release Notes

## v2.3.0 - 2024-02-21

## Added

- [292](https://github.com/nautobot/nautobot-app-ssot/pull/292) - Adds back in all the skipped contrib test cases by @Kircheneer
- [296](https://github.com/nautobot/nautobot-app-ssot/pull/296) - Implements caching mechanism into the NautobotAdapter by @Kircheneer
- [334](https://github.com/nautobot/nautobot-app-ssot/pull/334) - Add support for Platform to IPFabric by @jmcgill298
- [328](https://github.com/nautobot/nautobot-app-ssot/pull/328) - Add support for DHCP ranges to InfoBlox by @jmcgill298

## Fixed

- [336](https://github.com/nautobot/nautobot-app-ssot/pull/336) - IPFabric use actual interface type instead of config value by @jmcgill298
- [339](https://github.com/nautobot/nautobot-app-ssot/pull/339) - Fix ACI LocationType Bug by @jdrew82
- [342](https://github.com/nautobot/nautobot-app-ssot/pull/342) - Fix get ipv4address by @jmcgill298
- [351](https://github.com/nautobot/nautobot-app-ssot/pull/351) - Fix docs badge in README by @cmsirbu
- [348](https://github.com/nautobot/nautobot-app-ssot/pull/348) - Fix Infoblox Config Bug by @jdrew82
- [345](https://github.com/nautobot/nautobot-app-ssot/pull/345) - Fetch networks to get mask length in IPFabric by @jmcgill298
- [350](https://github.com/nautobot/nautobot-app-ssot/pull/350) - Fixes custom field contrib functionality by @Kircheneer

## Changed

- [333](https://github.com/nautobot/nautobot-app-ssot/pull/333) - Allow Exceptions To Fail Job by @jdrew82
- [341](https://github.com/nautobot/nautobot-app-ssot/pull/341) - Wrap IPFabric's database calls around try/except by @jmcgill298
- [362](https://github.com/nautobot/nautobot-app-ssot/pull/362) - Use typing.get_type_hints everywhere in favor of __annotations__ by @Kircheneer
