# Installing the App in Nautobot

## Prerequisites

- The plugin is compatible with Nautobot 1.4.0 and higher.
- Databases supported: PostgreSQL, MySQL

!!! note
    Please check the [dedicated page](compatibility_matrix.md) for a full compatibility matrix and the deprecation policy.

## Install Guide

!!! note
    Plugins can be installed manually or using Python's `pip`. See the [nautobot documentation](https://nautobot.readthedocs.io/en/latest/plugins/#install-the-package) for more details. The pip package name for this plugin is [`nautobot-ssot`](https://pypi.org/project/nautobot-ssot/).

The plugin is available as a Python package via PyPI and can be installed with `pip`:

```shell
pip install nautobot-ssot
```

To ensure Single Source of Truth is automatically re-installed during future upgrades, create a file named `local_requirements.txt` (if not already existing) in the Nautobot root directory (alongside `requirements.txt`) and list the `nautobot-ssot` package:

```shell
echo nautobot-ssot >> local_requirements.txt
```

Once installed, the plugin needs to be enabled in your Nautobot configuration. The following block of code below shows the additional configuration required to be added to your `nautobot_config.py` file:

- Append `"nautobot_ssot"` to the `PLUGINS` list.
- Append the `"nautobot_ssot"` dictionary to the `PLUGINS_CONFIG` dictionary and override any defaults.

```python
# In your nautobot_config.py
PLUGINS = ["nautobot_ssot"]

# PLUGINS_CONFIG = {
#   "nautobot_ssot": {
#     "hide_example_jobs": True
#   }
# }
```

Once the Nautobot configuration is updated, run the Post Upgrade command (`nautobot-server post_upgrade`) to run migrations and clear any cache:

```shell
nautobot-server post_upgrade
```

Then restart (if necessary) the Nautobot services which may include:

- Nautobot
- Nautobot Workers
- Nautobot Scheduler

```shell
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

## App Configuration

The plugin behavior can be controlled with the following list of settings:

| Key                 | Example | Default | Description                                                |
| ------------------- | ------- | ------- | ---------------------------------------------------------- |
| `hide_example_jobs` | `True`  | `False` | A boolean to represent whether or display the example job. |

