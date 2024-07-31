# NautobotSsotBootstrap


## Description

This plugin will sync data from yaml files into Nautobot to create baseline environments. Most items will receive a custom field associated with them called "System of Record", which will be set to "Bootstrap". These items are then the only ones managed by the Bootstrap SSoT App. Other items within the Nautobot instance will not be affected unless there's items with overlapping names. There is currently two exceptions to this and those are the ComputedField, and GraphQLQuery models since they can't have a custom field associated. If you choose to manage ComputedField or GraphQLQuery objects with the Bootstrap SSoT App, make sure to define them all within the yaml file, since any "locally defined" Computed Fields and GraphQL Queries within Nautobot will end up getting deleted when the job runs. If an item exists in Nautobot by it's identifiers but it does not have the "System of Record" custom field on it, the item will be updated with "Bootstrap" (or `SYSTEM_OF_RECORD` environment variable value) when the plugin runs. This way no duplicates are created, and the plugin will not delete any items that are not definied in the Bootstrap data but were manually created in Nautobot.

## Installation

Add the plugin to your poetry environment `poetry install nautobot-ssot-bootstrap`, then configure your `nautobot_config.py` to include the app and the settings.


### nautobot_config.py

The settings here are pretty straightforward, `nautobot_environment_branch` will be loaded from the environment variable `NAUTOBOT_BOOTSTRAP_SSOT_ENVIRONMENT_BRANCH`, or default to develop. The rest of the settings define which models/objects you want to have the plugin sync to Nautobot. There are a couple of caveats to these. For example, for DynamicGroup objects to sync, the filter criteria need to already exist in Nautobot. So, if you are going to have groups that are filtered on platforms/regions/sites/etc make sure not to include DynamicGroup objects in the "models_to_sync" until those items exist. Same for Git Repositories when you want to sync Golden Config-related repositories. The Golden Config plugin needs to be installed, for the `provided_contents` items to be able to be found. This also goes for the Lifecycle Management app with `Software/ValidatedSoftware` models.

```python
PLUGINS = ["nautobot_ssot", "nautobot_ssot_bootstrap"]

PLUGINS_CONFIG = {
  "nautobot_ssot_bootstrap": {
        # What to assign to the System of Record custom field.
        "nautobot_environment_branch": os.getenv("NAUTOBOT_BOOTSTRAP_SSOT_ENVIRONMENT_BRANCH", "develop"),
        # Which models to import from YAML into Nautobot
        "models_to_sync": {
            "secret": True,
            "secrets_group": True,
            "git_repository": True,
            "dynamic_group": True,
            "computed_field": True,
            "tag": True,
            "graph_ql_query": True,
            "software": True,
            "software_image": True,
            "validated_software": True,
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
        },
      }
}
```

## Configuration

### Bootstrap data

Bootstrap data can be stored in 2 fashions. Firstly, it can be stored within the `nautobot_ssot_bootstrap/fixtures` directory, or you may create a Git Repository within an existing Nautobot instance that contains the word `Bootstrap` in the name and provides `config context` data. The data structure is flat files, there is a naming scheme to these files. The first one required is `global_settings.yml`. This contains the main data structures of what data can be loaded `Secrets,SecretsGroups,GitRepository,DynamicGroup,Tag,etc`. You can then create additional `.yml` files with naming of your CI environments, i.e. production, development, etc. This is where the environment variables described below would be matched to pull in additional data from the other yaml files defined in the directory. A simple structure would look something like this:

```text
global_settings.yml
develop.yml
prod.yml
staging.yml
```

There are 2 environment variables that control how certain things are loaded in the app.

  1. `NAUTOBOT_BOOTSTRAP_SSOT_LOAD_SOURCE` - defines whether to load from the local `fixtures` folder or a GitRepository already present in Nautobot.
    - Acceptable options are `file` or `git`.
  2. `NAUTOBOT_BOOTSTRAP_SSOT_ENVIRONMENT_BRANCH` - Defines the environment and settings you want to import. I.e. production, develop, staging.

## Process

### Bootstrap as DataSource

Synchronization of data follows this workflow:
1. Load data from Bootstrap yaml file (limited to `models_to_sync`)
2. Load data from Nautobot (limited to `models_to_sync`, and objects that also have the `CustomField` `system_of_record` set to "Bootstrap".)
3. DiffSync determines Creates, Updates, Deletes
4. If an object is being created (an object loaded from Bootstrap was not loaded from Nautobot) Bootstrap will first check to see if an object with the same name exists in Nautobot but does not have the `system_of_record` field set. If it finds an object, it will update it with the Bootstrap values and set the `system_of_record` field to "Bootstrap".
5. If an object needs to be updated it will be updated with the values provided by Bootstrap data.
6. If an object needs to be deleted it will be deleted.


### Bootstrap as DataTarget

NotYetImplemented
