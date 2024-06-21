# Itential Integration Setup

This guide will walk you through steps to set up Itential integration with the `nautobot_ssot` app.

## Prerequisites

Before configuring the integration, please ensure, that `nautobot-ssot` app was [installed with the Itential integration extra dependencies](../install.md#install-guide).

```shell
pip install nautobot-ssot[itential]
```

## Configuration

The integration with Itential primarily utilizes the [External Integrations](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/externalintegration/?h=external) and [Secrets](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/secret/?h=secrets) features within Nautobot to set up the integration. To enable this integration, the only modification needed is to activate it in the nautobot_config.py file.

Below is an example snippet from `nautobot_config.py` that demonstrates how to enable the Itential integration:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_itential": True,
    }
}
```

Remaining configurations are performed in the Nautobot UI or through the Nautobot API.

### Secrets

The Itential integration necessitates four secret values: (1) Itential API access username, (2) Itential API access password, (3) network device access username, and (4) network device access password. You can store these secrets using the secrets provider of your choice.

### Secrets Group

When assigning secrets to a secrets group, please refer to the table below to correctly assign each secret to its respective access type and secret type.

| Secret Description    | Access Type | Secret Type |
|-----------------------|-------------|-------------|
| Itential API username | REST        | Username    |
| Itential API password | REST        | Password    |
| Device username       | GENERIC     | Username    |
| Device password       | GENERIC     | Password    |

### External Integration

When setting up an external integration, you must provide the following required fields:

1. **Name**: The unique identifier for the integration.
2. **Remote URL**: The endpoint URL, including the protocol and port, if applicable.
3. **Verify SSL**: A boolean value indicating whether SSL certificates should be verified.
4. **Secrets Group**: The group of secrets associated with the integration, containing necessary authentication details.

The remote URL must include both the protocol (either http or https) and the TCP port used by the automation gateway. For example, to access the automation gateway, you would enter a URL like: https://iag.example.com:8443.

### Automation Gateway Management

To manage the Automation Gateway, navigate to Plugins -> Single Source of Truth -> Itential Automation Gateway in your application. From this interface, you can input details about the automation gateway, which include:

1. **Name**: Specify the name of the automation gateway.
2. **Description**: Provide a brief description of what the automation gateway is used for.
3. **Location**: Indicate the primary location of the devices managed by the automation gateway.
4. **Location Descendants**: This boolean value determines whether the automation gateway should also manage devices in child locations of the specified primary location.
5. **Enabled**: This boolean setting allows you to enable or disable inventory synchronization with the automation gateway.
