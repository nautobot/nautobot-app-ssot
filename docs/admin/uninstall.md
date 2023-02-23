# Uninstall the App from Nautobot

Here you will find any steps necessary to cleanly remove the App from your Nautobot environment.

## Uninstall Guide

Remove the configuration you added in `nautobot_config.py` from `PLUGINS` & `PLUGINS_CONFIG`.

Uninstall the package

```bash
$ pip3 uninstall nautobot-ssot
```

## Database Cleanup

Drop all tables from the plugin: `nautobot_plugin_ssot*`.
