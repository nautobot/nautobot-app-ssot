# v3.6 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

The major thing to note about this release is that we've removed support for Python 3.8 from the project. There have been some additional features added to the Bootstrap and DNA Center integrations. In addition there have been a multitude of bugfixes and tweaks made to the project.

## [v3.6.0 (2025-04-05)](https://github.com/nautobot/nautobot-app-ssot/releases/tag/v3.6.0)

### Added

- [#632](https://github.com/nautobot/nautobot-app-ssot/issues/632) - Added support for Object Metadata to track last synchronization from DNA Center to imported Locations, Devices, Prefixes, and IPAddresses.
- [#705](https://github.com/nautobot/nautobot-app-ssot/issues/705) - Added custom_field creation to Bootstrap integration.
- [#744](https://github.com/nautobot/nautobot-app-ssot/issues/744) - Added extra check when determiming device_type for 'wireless' in Cisco model names.
- [#745](https://github.com/nautobot/nautobot-app-ssot/issues/745) - Added enabled option for ScheduledJob in Bootstrap SSOT.

### Changed

- [#692](https://github.com/nautobot/nautobot-app-ssot/issues/692) - Improve the replace_dashed_custom_fields migration (0007_replace_dashed_custom_fields.py) by iterating over a generator instead of loading all objects into a list.
- [#726](https://github.com/nautobot/nautobot-app-ssot/issues/726) - Create a new setting in the SSoT Infoblox integration that allows users to define mappings between Infoblox network views and Nautobot namespaces.
- [#731](https://github.com/nautobot/nautobot-app-ssot/issues/731) - Changed Aruba/Cisco Platform values to enable better differentation between Operating Systems.
- [#732](https://github.com/nautobot/nautobot-app-ssot/issues/732) - Allowed custom_property to be used for filtering without requiring location_override.
- [#732](https://github.com/nautobot/nautobot-app-ssot/issues/732) - Added location_override ability to be used without requiring custom_property.

### Fixed

- [#687](https://github.com/nautobot/nautobot-app-ssot/issues/687) - Fixed Location structure being imported incorrectly in DNA Center.
- [#695](https://github.com/nautobot/nautobot-app-ssot/issues/695) - Add check for parent of Location before looking for parent of parent.
- [#697](https://github.com/nautobot/nautobot-app-ssot/issues/697) - ACI integration: Change _tag.validated_save() to _tag.save()
- [#702](https://github.com/nautobot/nautobot-app-ssot/issues/702) - Fixed handling of timezones in scheduled jobs when timezone is specified in the yaml.
- [#703](https://github.com/nautobot/nautobot-app-ssot/issues/703) - Added catching of `ValueError` on `validated_save` in contrib models.
- [#707](https://github.com/nautobot/nautobot-app-ssot/issues/707) - Added exception handling to Slurpit functions to catch if an object already exists.
- [#708](https://github.com/nautobot/nautobot-app-ssot/issues/708) - Fixed bug that was causing all Devices to be assigned to same Building when Location structure included multiple Buildings of same name under differing Areas.
- [#710](https://github.com/nautobot/nautobot-app-ssot/issues/710) - Allowed Slurpit sync to be scheduled.
- [#710](https://github.com/nautobot/nautobot-app-ssot/issues/710) - Fix issue with duplicate prefixes from Nautobot causing exception during sync with Slurpit.
- [#710](https://github.com/nautobot/nautobot-app-ssot/issues/710) - Enable custom fields to accept `None` in the Slurpit models.
- [#710](https://github.com/nautobot/nautobot-app-ssot/issues/710) - Remove Napalm driver sync
- [#710](https://github.com/nautobot/nautobot-app-ssot/issues/710) - Add exception catch ObjectDoesNotExist
- [#717](https://github.com/nautobot/nautobot-app-ssot/issues/717) - Fixed missing import of Interfaces and IPAddresses for uplink Interfaces on small selection of APs in Meraki.
- [#721](https://github.com/nautobot/nautobot-app-ssot/issues/721) - Updated source and destination labels for Infoblox "Prefix -> VLAN" relationship
- [#729](https://github.com/nautobot/nautobot-app-ssot/issues/729) - Fixed the synchronization of the prefix location from Infoblox extensibility attributes.
- [#732](https://github.com/nautobot/nautobot-app-ssot/issues/732) - Fixed failure scenario with a user-friendly error message, if neither a location_type or location_override was specified.
- [#732](https://github.com/nautobot/nautobot-app-ssot/issues/732) - Fixed missing container name error, if comma separated container names included a space before or after a comma.
- [#734](https://github.com/nautobot/nautobot-app-ssot/issues/734) - Fixed bug where non-existing Building ID is found in SiteHierarchy for a device.
- [#737](https://github.com/nautobot/nautobot-app-ssot/issues/737) - Fixed Meraki AP port not being loaded and created correctly.
- [#737](https://github.com/nautobot/nautobot-app-ssot/issues/737) - Fixed Meraki location_map feature not updating Locations parent and name as expected.
- [#739](https://github.com/nautobot/nautobot-app-ssot/issues/739) - Fixes key errors if keys don't exist in global_settings.yaml and are enabled in models_to_sync.
- [#740](https://github.com/nautobot/nautobot-app-ssot/issues/740) - Added migration for SolarWinds integration to update CustomFields from Solarwinds to SolarWinds to match update in #696.
- [#748](https://github.com/nautobot/nautobot-app-ssot/issues/748) - Fixes handling empty keys in tag and location models
- [#750](https://github.com/nautobot/nautobot-app-ssot/issues/750) - Fixed ServiceNow instance configuration loading.

### Dependencies

- [#762](https://github.com/nautobot/nautobot-app-ssot/issues/762) - Removed support for Python 3.8.

### Documentation

- [#696](https://github.com/nautobot/nautobot-app-ssot/issues/696) - Corrected spelling of SolarWinds and removed note about Arista Labs.
- [#743](https://github.com/nautobot/nautobot-app-ssot/issues/743) - Added Mermaid diagrams for SSoT models to documentation.

### Housekeeping

- Rebaked from the cookie `nautobot-app-v2.4.2`.

## New Contributors
* @michalbil made their first contribution in https://github.com/nautobot/nautobot-app-ssot/pull/722
* @justinbrink made their first contribution in https://github.com/nautobot/nautobot-app-ssot/pull/751

**Full Changelog**: https://github.com/nautobot/nautobot-app-ssot/compare/v3.5.0...v3.6.0
