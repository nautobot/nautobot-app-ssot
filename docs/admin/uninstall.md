# Uninstall the App from Nautobot

Here you will find any steps necessary to cleanly remove the App from your Nautobot environment.

## Uninstall Guide

!!! warning "Developer Note - Remove Me!"
    Detailed instructions on how to remove the app from Nautobot.

Remove the configuration you added in `nautobot_config.py` from `PLUGINS` & `PLUGINS_CONFIG`.

## Database Cleanup

!!! warning "Developer Note - Remove Me!"
    Any cleanup operations to ensure the database is clean after the app is removed. Beyond deleting tables, is there anything else that needs cleaning up, such as CFs, relationships, etc. if they're no longer desired?

Drop all tables from the plugin: `nautobot_plugin_ssot*`.
