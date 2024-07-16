
## [v2.7.0 (2024-07-16)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v2.7.0)

### Added

- [#432](https://github.com/nautobot/nautobot-app-ssot/issues/432) - Added an SSoT to sync Nautobot ==> Itential Automation Gateway.
- [#432](https://github.com/nautobot/nautobot-app-ssot/issues/432) - This integration allows users to sync Nautobot device inventory to Itential Automation Gateway(s) (IAG).
- [#432](https://github.com/nautobot/nautobot-app-ssot/issues/432) - The current IAG inventory that is supported is its default Ansible inventory.
- [#432](https://github.com/nautobot/nautobot-app-ssot/issues/432) - Netmiko, Nornir, HTTP requests inventories will be added at a later date.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Added plugin configuration page collecting configurations for integrations.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - added SSOTInfobloxConfig model used for providing Infoblox integration configuration.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - added support for multiple configuration instances.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - added support for Infoblox Network Views and Nautobot Namespaces.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - added support for selecting a subset of Network and IP address objects loaded for synchronization.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - added support for creating Infoblox IP Addresses as A and PTR records.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - added support for creating Infoblox IP Addresses as Fixed Address records of type RESERVED and MAC_ADDRESS.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - added support for excluding extensive attributes and custom fields when synchronizing objects.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - added support for selectively enabling synchronization of IPv4 and IPv6 objects.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - added support for specifying Infoblox DNS View where DNS records are created.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - added support for specifying record types subject to deletion in Infoblox and Nautobot.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - added methods to Infoblox handling fixed addresses, DNS A, Host and PTR records, network views, DNS views, and authoritative zones.
- [#469](https://github.com/nautobot/nautobot-app-ssot/issues/469) - Added more models for import in Example Jobs.

### Changed

- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - configuration settings are now defined in the instances of the SSOTInfobloxConfig model.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - functionality provided by the `infoblox_import_subnets` settings has been replaced with the `infoblox_sync_filters` field in the SSOTInfobloxConfig instance.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - updated Infoblox client methods to support Network View.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - standardized `JSONDecoderError` handling in the Infoblox client.

### Removed

- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - configuration settings defined in `nautobot_config.py` have been removed.
- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442) - Infoblox integration - configuration settings defined in environmental variables have been removed.

### Fixed

- [#234](https://github.com/nautobot/nautobot-app-ssot/issues/234) - Fixed integration tests so they're no longer dependent upon being enabled in dev environment.
- [#437](https://github.com/nautobot/nautobot-app-ssot/issues/437) - Fixed link from list view to filtered sync log view by changing filter query to `sync` from overview.
- [#443](https://github.com/nautobot/nautobot-app-ssot/issues/443) - Fixed issue with loading duplicate IPAddresses from Infoblox.
- [#456](https://github.com/nautobot/nautobot-app-ssot/issues/456) - Fix Device42 integration unit test that was expecting wrong BIG-IP netmiko platform name.
- [#463](https://github.com/nautobot/nautobot-app-ssot/issues/463) - Fixed call in CVP integration to pass `import_active` config setting to get_devices() function call.
- [#479](https://github.com/nautobot/nautobot-app-ssot/issues/479) - Correct get_or_instantiate() to use self.device_type instead of "device_type" in ACI adapter.
- [#479](https://github.com/nautobot/nautobot-app-ssot/issues/479) - Refactor load_interfaces() to have check for device_specs var being defined in case file isn't loaded.

### Documentation

- [#442](https://github.com/nautobot/nautobot-app-ssot/issues/442), [#450](https://github.com/nautobot/nautobot-app-ssot/issues/450) - Add missing attribution for Device42 integration to README.
- [#472](https://github.com/nautobot/nautobot-app-ssot/issues/472) - Update ServiceNow documentation for Locations and FAQ error.
