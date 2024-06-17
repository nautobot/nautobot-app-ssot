
# v2.7 Release Notes

## [v2.7.0 ()](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v2.7.0)

### Added

- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Added SSOTConfig model and view for exposing configurations of individual integrations.
- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - added Namespace, DnsARecord, DnsHostRecord and DnsPTRRecord diffsync models.
- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - modified Network and IPAddress models to support namespaces and creation of additional IP Address record types.
- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - synchronization jobs have a new mandatory field called `Config`. This field specifies which Infoblox Config to use with the job.
- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - Full support for Infoblox network views and Nautobot namespace has been added. Multiple network views/namespaces and their IP objects can now be safely loaded. This allows for importing overlapping prefixes from Infoblox that are assigned to corresponding Namespaces in Nautobot.
- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - added support for excluding extensible attributes and custom fields from sync.
- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - added configuration setting that specifies the mapping between network view and DNS view. This is required to correctly create DNS records in Infoblox.
- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - added support for specifying a subset of IP Prefixes and IP Addresses loaded for synchronization.
- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - added support for creating Infoblox IP Addresses as either Host or A records. An optional PTR record can be created alongside A record.
- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - added support for updating Infoblox Fixed Address, and DNS Host, A, and PTR records.
- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - added support for creating/updating IP Addresses in Infoblox as Fixed Address of type RESERVED or MAC_ADDRESS.
- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - added support for specifying record types that can be deleted in Infoblox and Nautobot.
- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - added multiple new methods in the Infoblox client for dealing with fixed addresses, DNS A, Host and PTR records, network views, DNS views and authoritative zones.
- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - added the following custom fields to support new functionality: `mac_address`, `fixed_address_comment`, `dns_a_record_comment`, `dns_host_record_comment`, `dns_ptr_record_comment`.
- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - added check for the minimum version of Nautobot. This release requires Nautobot 2.1 or greater.

### Changed

- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - configuration is no longer defined in `nautobot_config.py`. Configuration is now defined in the SSOT Infoblox Config object. This can be set up in UI or using Django ORM. 
    - The existing configuration is taken from `nautobot_config.py` will be automatically migrated to the SSOT Infoblox Config object named `InfobloxConfigDefault`. 
    - Configuration of the Infoblox instance is now recorded in the ExternalIntegration object. The existing configuration will be automatically migrated to the instance named `DefaultInfobloxInstance`.
    - Credentials are now defined in the Secrets Group. The migrated configuration expects the username to come from the `NAUTOBOT_SSOT_INFOBLOX_USERNAME` env var and the password to come from the `NAUTOBOT_SSOT_INFOBLOX_PASSWORD` env var. To use a different method of providing credentials modify secrets attached to the `InfobloxSSOTDefaultSecretGroup` SecretsGroup.

- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Default behavior when loading prefixes has changed. Previously all prefixes from all Infoblox network views were loaded by default, with duplicate prefixes removed. This process was non-deterministic and resulted in all Infoblox prefixes assigned to the "Global" namespace in Nautobot. Infoblox integration now enforces the use of the `infoblox_sync_filters` setting, defined in the Infoblox Config, with the default value set to `[{"network_view": "default"}]`. This default setting results in loading all of the prefixes from the Infoblox network view "default" only and assigning them to the "Global" namespace in Infoblox. See Infoblox sync filter documentation for details on how to define filters.
- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - standardized and improved error handling in the Infoblox client.


### Removed

- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Infoblox integration - environmental variables used to configure the integration have been deprecated.

### Fixed

- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - The Infoblox client logging level now honors the `debug` job option.

### Housekeeping

- [#442](https://github.com/nautobot/nautobot-app-ssot/pull/442) - Increased test coverage.

