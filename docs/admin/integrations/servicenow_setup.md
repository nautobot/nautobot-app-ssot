# ServiceNow Integration Setup

This guide will walk you through steps to set up ServiceNow integration with the `nautobot_ssot` app.

## Prerequisites

Before configuring the integration, please ensure, that `nautobot-ssot` app was [installed with ServiceNow integration extra dependencies](../install.md#install-guide).

```shell
pip install nautobot-ssot[servicenow]
```

## Configuration

Integration behavior can be controlled with the following settings:

- `instance`: The ServiceNow instance to point to (as in `<instance>.servicenow.com`)
- `username`: Username to access this instance
- `password`: Password to access this instance

There is also the option of omitting these settings from `PLUGINS_CONFIG` and instead defining them through the UI at `/plugins/ssot-servicenow/config/` (reachable by navigating to **Plugins > Installed Plugins** then clicking the "gear" icon next to the *Nautobot SSoT ServiceNow* entry) using Nautobot's standard UI and [secrets](https://nautobot.readthedocs.io/en/stable/core-functionality/secrets/) functionality.

> If you configure the integration's settings in `PLUGINS_CONFIG`, those values will take precedence over any configuration in the UI.

Depending on the amount of data involved, and the performance of your ServiceNow instance, you may need to increase the Nautobot job execution time limits ([`CELERY_TASK_SOFT_TIME_LIMIT`](https://nautobot.readthedocs.io/en/stable/configuration/optional-settings/#celery_task_soft_time_limit) and [`CELERY_TASK_TIME_LIMIT`](https://nautobot.readthedocs.io/en/stable/configuration/optional-settings/#celery_task_time_limit)) so that the job can execute to completion without timing out.

Below is an example snippet from `nautobot_config.py` that demonstrates how to enable and configure ServiceNow integration:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_servicenow": True,
        "servicenow_instance": os.getenv("SERVICENOW_INSTANCE", ""),
        "servicenow_password": os.getenv("SERVICENOW_PASSWORD", ""),
        "servicenow_username": os.getenv("SERVICENOW_USERNAME", ""),
    }
}
```

!!! note
    All integration settings are defined in the block above as an example. Only some will be needed as described below.

## Upgrading from `nautobot-plugin-ssot-servicenow` App

!!! warning
    When upgrading from `nautobot-plugin-ssot-servicenow` app, it's necessary to [avoid conflicts](../upgrade.md#potential-apps-conflicts).

- Uninstall the old app:
    ```shell
    pip uninstall nautobot-plugin-ssot-servicenow
    ```
- Upgrade the app with required extras:
    ```shell
    pip install --upgrade nautobot-ssot[servicenow]
    ```
- Fix `nautobot_config.py` by removing `nautobot_ssot_servicenow` from `PLUGINS` and merging app configuration into `nautobot_ssot`:
    ```python
    PLUGINS = [
        "nautobot_ssot",
        # "servicenow"  # REMOVE THIS LINE
    ]

    PLUGINS_CONFIG = {
        # "nautobot_ssot_servicenow": {  REMOVE THIS APP CONFIGURATION
        #      MOVE CONFIGURATION TO `nautobot_ssot` SECTION AND UPDATE KEYS
        #     "instance": os.getenv("SERVICENOW_INSTANCE"),
        #     "username": os.getenv("SERVICENOW_USERNAME"),
        #     "password": os.getenv("SERVICENOW_PASSWORD"),
        # }
        "nautobot_ssot": {
            # Enable ServiceNow integration
            "enable_servicenow": True,
            # Following lines are moved from `nautobot_ssot_servicenow` and prefixed with `servicenow_`
            "servicenow_instance": "",
            "servicenow_password": "",
            "servicenow_username": "",
        }
    }
    ```

!!! note
    Configuration keys are prefixed with `servicenow_`.
