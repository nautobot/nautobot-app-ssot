# Itential Integration Setup

This guide will walk you through steps to set up Itential integration with the `nautobot_ssot` app.

## Prerequisites

Before configuring the integration, please ensure, that `nautobot-ssot` app was [installed with the Itential integration extra dependencies](../install.md#install-guide).

```shell
pip install nautobot-ssot[itential]
```

## Configuration

The Itential integration leverages the [External Integrations](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/externalintegration/?h=external) and [Secrets](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/secret/?h=secrets) heavily to configure the integration. The only change that is required to be made in `nautobot_config.py` is to enable the integration.

Below is an example snippet from `nautobot_config.py` that demonstrates how to enable the Itential integration:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_itential": True,
    }
}
```