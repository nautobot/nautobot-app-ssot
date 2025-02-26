# SolarWinds Integration Setup

This guide will walk you through steps to set up the SolarWinds integration with the `nautobot_ssot` app.

## Prerequisites

Before configuring the integration, please ensure, that `nautobot-ssot` app was [installed](../install.md#install-guide).

```shell
pip install nautobot-ssot
```

## Configuration

Access to your SolarWinds instance is defined using the [ExternalIntegration](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/externalintegration/) model which allows you to utilize this integration with multiple instances concurrently. Please bear in mind that it will synchronize all data 1:1 with the specified instance to match exactly, meaning it will delete data missing from an instance. Each ExternalIntegration must specify a SecretsGroup with [Secrets](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/secret/) that contain the SolarWinds administrator Username and Password to authenticate with. You can find Secrets and SecretsGroups available under the Secrets menu.

Below is an example snippet from `nautobot_config.py` that demonstrates how to enable the SolarWinds integration:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_solarwinds": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_SOLARWINDS", "true")),
    }
}
```
