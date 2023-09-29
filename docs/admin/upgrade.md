# Upgrading the App

## Upgrade Guide

When a new release comes out it may be necessary to run a migration of the database to account for any changes in the data models used by this Nautobot app. Execute the command `nautobot-server post-upgrade` within the runtime environment of your Nautobot installation after updating the `nautobot-ssot` package via `pip`.

### Potential Apps Conflicts

!!! warning
    If upgrading from versions prior to 1.4 of the `nautobot-ssot` app, note that it now incorporates features previously provided by individual apps.

Conflicting apps list:

- `nautobot_ssot_aci`
- `nautobot_ssot_arista_cloudvision`
- `nautobot_ssot_infoblox`
- `nautobot_ssot_ipfabric`
- `nautobot_ssot_servicenow`

To prevent conflicts during `nautobot-ssot` upgrade:

- Remove conflicting applications from the `PLUGINS` section in your Nautobot configuration before enabling the latest `nautobot-ssot` version.
- Transfer the configuration for conflicting apps to the `PLUGIN_CONFIG["nautobot_ssot"]` section of your Nautobot configuration. See `development/nautobot_config.py` for an example. Each [integration set up guide](../integrations/) contains a chapter with upgrade instructions.
- Remove conflicting applications from your project's requirements.

These steps will help prevent issues during `nautobot-ssot` upgrades. Always back up your data and thoroughly test your configuration after these changes.

!!! note
    It's possible to allow conflicting apps to remain in `PLUGINS` during the upgrade process. You can specify the following environment variable in `development/development.env` to allow conflicting apps:

    ```bash
    NAUTOBOT_SSOT_ALLOW_CONFLICTING_APPS=True
    ```

    However, this is not recommended.

!!! warning
    If conflicting apps remain in `PLUGINS`, the `nautobot-ssot` app will raise an exception during startup to prevent potential conflicts.
