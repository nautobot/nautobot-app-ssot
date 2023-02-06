# Nautobot Single Source of Truth (SSoT)

A plugin for [Nautobot](https://github.com/nautobot/nautobot). This plugin facilitates integration and data synchronization between various "source of truth" (SoT) systems, with Nautobot acting as a central clearinghouse for data - a Single Source of Truth, if you will.

A goal of this plugin is to make it relatively quick and straightforward to [develop and integrate](https://nautobot-plugin-ssot.readthedocs.io/en/latest/developing_jobs/) your own system-specific Data Sources and Data Targets into Nautobot with a common UI and user experience.

## Installation

The plugin is available as a Python package in PyPI and can be installed with `pip`:

```shell
pip install nautobot-ssot
```

> This plugin is compatible with Nautobot 1.0.3 and higher.

Once installed, the plugin needs to be enabled in your `nautobot_config.py`:

```python
# In your nautobot_config.py
PLUGINS = ["nautobot_ssot"]

PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "hide_example_jobs": False,  # defaults to False if unspecified
    }
}
```

The plugin behavior can be controlled with the following list of settings:

- `"hide_example_jobs"`: By default this plugin includes a pair of example data source / data target jobs so that you can see how it works without installing any additional plugins to provide specific system integrations. Once you have installed or developed some "real" system integrations to work with this plugin, you may wish to hide the example jobs, which you may do by setting this configuration setting to `True`.

## Usage

Refer to the [documentation](https://nautobot-plugin-ssot.readthedocs.io/en/latest/) for usage details.

## Questions

For any questions or comments, please check the [FAQ](FAQ.md) first and feel free to swing by the [Network to Code slack channel](https://networktocode.slack.com/) (channel #networktocode).
Sign up [here](http://slack.networktocode.com/)

## Screenshots

![Dashboard screenshot](https://nautobot-plugin-ssot.readthedocs.io/en/latest/images/dashboard_initial.png)

![Data Source detail view](https://nautobot-plugin-ssot.readthedocs.io/en/latest/images/data_source_detail.png)

![Sync detail view](https://nautobot-plugin-ssot.readthedocs.io/en/latest/images/sync_detail.png)

![Example data source - Arista CloudVision](https://nautobot-plugin-ssot.readthedocs.io/en/latest/images/example_cloudvision.png)

![Example data target - ServiceNow](https://nautobot-plugin-ssot.readthedocs.io/en/latest/images/example_servicenow.png)
