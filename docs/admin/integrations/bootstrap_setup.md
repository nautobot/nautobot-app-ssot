# Bootstrap


## Description

This App will sync data from YAML files into Nautobot to create baseline environments. Most items will receive a custom field associated with them called "System of Record", which will be set to "Bootstrap". These items are then the only ones managed by the Bootstrap SSoT App. Other items within the Nautobot instance will not be affected unless there's items with overlapping names. There is currently two exceptions to this and those are the ComputedField, and GraphQLQuery models since they can't have a custom field associated. If you choose to manage ComputedField or GraphQLQuery objects with the Bootstrap SSoT App, make sure to define them all within the YAML file, since any "locally defined" Computed Fields and GraphQL Queries within Nautobot will end up getting deleted when the job runs. If an item exists in Nautobot by it's identifiers but it does not have the "System of Record" custom field on it, the item will be updated with "Bootstrap" (or `SYSTEM_OF_RECORD` environment variable value) when the App runs. This way no duplicates are created, and the App will not delete any items that are not defined in the Bootstrap data but were manually created in Nautobot.

## Installation

Before configuring the integration, please ensure, that `nautobot-ssot` app was [installed with Bootstrap integration extra dependencies](../install.md#install-guide).

```shell
pip install nautobot-ssot[bootstrap]
```


### nautobot_config.py

The settings here are pretty straightforward, `nautobot_environment_branch` will be loaded from the environment variable `NAUTOBOT_BOOTSTRAP_SSOT_ENVIRONMENT_BRANCH`, or default to develop. The rest of the settings define which models/objects you want to have the App sync to Nautobot. There are a couple of caveats to these. For example, for DynamicGroup objects to sync, the filter criteria need to already exist in Nautobot. So, if you are going to have groups that are filtered on platforms/regions/sites/etc make sure not to include DynamicGroup objects in the "models_to_sync" until those items exist. Same for Git Repositories when you want to sync Golden Config-related repositories. The Golden Config App needs to be installed, for the `provided_contents` items to be able to be found. This also goes for the Lifecycle Management app with `Software/ValidatedSoftware` models.

```python
PLUGINS = ["nautobot_ssot"]

PLUGINS_CONFIG = {
  "nautobot_ssot": {
        # Other nautobot_ssot settings ommitted.
        "bootstrap_nautobot_environment_branch": os.getenv("NAUTOBOT_BOOTSTRAP_SSOT_ENVIRONMENT_BRANCH", "develop"),
        "bootstrap_models_to_sync": {
            "secret": True,
            "secrets_group": True,
            "git_repository": True,
            "dynamic_group": True,
            "computed_field": True,
            "tag": True,
            "graph_ql_query": True,
            "software": False,
            "software_image": False,
            "validated_software": False,
            "tenant_group": True,
            "tenant": True,
            "role": True,
            "manufacturer": True,
            "platform": True,
            "location_type": True,
            "location": True,
            "team": True,
            "contact": True,
            "provider": True,
            "provider_network": True,
            "circuit_type": True,
            "circuit": True,
            "circuit_termination": True,
            "namespace": True,
            "rir": True,
            "vlan_group": True,
            "vlan": True,
            "vrf": True,
            "prefix": True,
        },
        "enable_bootstrap": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_BOOTSTRAP", "false")),
  }
}
```

## Configuration

### Bootstrap data

Bootstrap data can be stored in 2 fashions.

1. (Recommended) Bootstrap data can be stored in a Git Repository and referenced in the app as a Git Datasource. A user should create a Git Repository in Nautobot (including any necessary Secrets and SecretsGroups for access) with the word "Bootstrap" in the name, and with a provided content type of `config contexts`. This is how the App will locate the correct repository. The data structure is flat files, and there is a naming scheme to these files. The first one required is `global_settings.yml`. This contains the main data structures of what data can be loaded `Secrets,SecretsGroups,GitRepository,DynamicGroup,Tag,etc`. You can then create additional `.yml` files with naming of your CI environments, i.e. production, development, etc for default values for specific items. This is where the environment variables described below would be matched to pull in additional data from the other YAML files defined in the directory.

2. Bootstrap data can be stored within the `nautobot_ssot/bootstrap/fixtures` directory. Using local files is not recommended as this requires a fork of the plugin and locally editing the YAML data files in the fixtures folder.

A simple structure would look something like this:

```text
global_settings.yml
develop.yml
prod.yml
staging.yml
```

There are 2 environment variables that control how certain things are loaded in the app.

  1. `NAUTOBOT_BOOTSTRAP_SSOT_LOAD_SOURCE` - defines whether to load from the local `fixtures` folder or a GitRepository already present in Nautobot. This setting will get overridden if the user selects something other than `env_var` in the job's GUI settings.
    - Acceptable options are `file` or `git`.
  2. `NAUTOBOT_BOOTSTRAP_SSOT_ENVIRONMENT_BRANCH` - Defines the environment and settings you want to import. I.e. production, develop, staging.
