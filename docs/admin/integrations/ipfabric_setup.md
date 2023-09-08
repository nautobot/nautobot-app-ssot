# IPFabric Integration Setup

This guide will walk you through steps to set up IPFabric integration with the `nautobot_ssot` app.

## Prerequisites

Before configuring the integration, please ensure, that `nautobot-ssot` app was [installed with the IPFabric integration extra dependencies](../install.md#install-guide).

```shell
pip install nautobot-ssot[ipfabric]
```

## Configuration

Integration behavior can be controlled with the following settings:

| `Setting` | `Description` |
| --------- | ------------- |
| `ipfabric_url` | URL of the IPFabric instance to sync with. |
| `ipfabric_api_token` | API token for IPFabric authentication. |
| `ipfabric_host` | Hostname/IP address of the IPFabric instance. |
| `ipfabric_ssl_verify` | Verify the SSL certificate of the IPFabric instance. |
| `ipfabric_timeout` | Timeout (in seconds) for API requests to IPFabric. |
| `nautobot_host` | FQDN of your Nautobot instance. This is used to provide a URL to the job results via ChatOps. |

Below is an example snippet from `nautobot_config.py` that demonstrates how to enable and configure IPFabric integration:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_ipfabric": True,
        "ipfabric_api_token": os.environ.get("IPFABRIC_API_TOKEN"),
        "ipfabric_host": os.environ.get("IPFABRIC_HOST"),
        "ipfabric_ssl_verify": os.environ.get("IPFABRIC_SSL_VERIFY"),
        "ipfabric_timeout": os.environ.get("IPFABRIC_TIMEOUT"),
        "nautobot_host": os.environ.get("NAUTOBOT_HOST"),
    }
}
```

!!! note
    All integration settings are defined in the block above as an example. Only some will be needed as described below.

## Upgrading from `nautobot-plugin-ssot-ipfabric` App

!!! warning
    When upgrading from `nautobot-plugin-ssot-ipfabric` app, it's necessary to [avoid conflicts](../upgrade.md#potential-apps-conflicts).

- Uninstall the old app:
    ```shell
    pip uninstall nautobot-plugin-ssot-ipfabric
    ```
- Upgrade the app with required extras:
    ```shell
    pip install --upgrade nautobot-ssot[ipfabric]
    ```
- Fix `nautobot_config.py` by removing `nautobot_ssot_ipfabric` from `PLUGINS` and merging app configuration into `nautobot_ssot`:
    ```python
    PLUGINS = [
        "nautobot_ssot",
        # "nautobot_ssot_ipfabric"  # REMOVE THIS LINE
    ]

    PLUGINS_CONFIG = {
        # "nautobot_ssot_ipfabric": {  REMOVE THIS APP CONFIGURATION
        #      MOVE CONFIGURATION TO `nautobot_ssot` SECTION
        #     "ipfabric_api_token": os.environ.get("IPFABRIC_API_TOKEN"),
        #     "ipfabric_host": os.environ.get("IPFABRIC_HOST"),
        #     "ipfabric_ssl_verify": os.environ.get("IPFABRIC_SSL_VERIFY"),
        #     "ipfabric_timeout": os.environ.get("IPFABRIC_TIMEOUT"),
        #     "nautobot_host": os.environ.get("NAUTOBOT_HOST"),
        # }
        "nautobot_ssot": {
            # Enable IPFabric integration
            "enable_ipfabric": True,
            # Following lines are moved from `nautobot_ssot_ipfabric`
            "ipfabric_api_token": os.environ.get("IPFABRIC_API_TOKEN"),
            "ipfabric_host": os.environ.get("IPFABRIC_HOST"),
            "ipfabric_ssl_verify": os.environ.get("IPFABRIC_SSL_VERIFY"),
            "ipfabric_timeout": os.environ.get("IPFABRIC_TIMEOUT"),
            "nautobot_host": os.environ.get("NAUTOBOT_HOST"),
        }
    }
    ```
