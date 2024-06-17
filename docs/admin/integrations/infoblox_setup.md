# Infoblox Integration Setup

This guide will walk you through the steps to set up Infoblox integration with the `nautobot_ssot` app.

## Prerequisites

Before configuring the integration, please ensure, that the `nautobot-ssot` app was [installed with the Infoblox integration extra dependencies](../install.md#install-guide).

```shell
pip install nautobot-ssot[infoblox]
```

## Configuration

!!! note
    Legacy configuration settings defined in the `nautobot_config.py` and environmental variables are deprecated. These settings are migrated on a best-effort basis on the first startup following migration to the Nautobot SSOT 2.7.0 or higher.

Integration configuration is defined in the instance of the `SSOTInfobloxConfig` model. Multiple configuration instances are supported. Synchronization jobs take the `Config` parameter which specifies the configuration instance to use.

To access integration configuration navigate to `Plugins -> Installed Plugins` and click on the cog icon in the `Single Source of Truth` entry. Then in the table `SSOT Integration Configs` click on the `Infoblox Configuration List` link. This will take you to the view where you can view/modify existing config instances or create new ones.

Configuration instance contains the below settings:

| Name | N/A | Unique name of the configuration instance. |
| Description | N/A | Description of the configuration instance. |
| Infoblox Instance Config | N/A | External Integration object describing remote Infoblox instance. |
| Infoblox WAPI Version  | v2.12 | The version of the Infoblox API. |
| Enabled for Sync Job | False | Allows this config to be used in the sync jobs. |
| Sync to Infoblox | False | Allows this config to be used in the job syncing from Nautobot to Infoblox. |
| Sync to Nautobot | True | Allows this config to be used in the job syncing from Infoblox to Nautobot. |
| Import IP Addresses | False | Import IP addresses from the source to the target system. |
| Import Networks | False | Import IP networks from the source to the target system. |
| Import VLAN Views |	False | Import VLAN Views from the source to the target system. |
| Import VLANs |	False | Import VLANs from the source to the target system. |
| Import IPv4 | True | Import IPv4 objects from the source to the target system.  |
| Import IPv6 | False | Import IPv6 objects from the source to the target system. |
| Fixed address type | 	Do not create record | Selects type of Fixed Address to create in Infoblox for imported IP Addresses. |   
| DNS record type | Do not create record | Selects the type of DNS record to create in Infoblox for imported IP Addresses. | 
| Default object status | Active | Default Status to be assigned to imported objects. |
| Infoblox - deletable models | [] | Infoblox model types whose instances are allowed to be deleted during sync. |
| Nautobot - deletable models | [] | Nautobot model types whose instances are allowed to be deleted during sync. |
| Infoblox Sync Filters | `[{"network_view": "default"}]` | Filters control what data is loaded from the source and target systems and considered for sync. |
| Infoblox Network View to DNS Mapping | `{}` | Map specifying Infoblox DNS View for each Network View where DNS records need to be created.
| Extensible Attributes/Custom Fields to Ignore |  `{"custom_fields": [], "extensible_attributes": []}` | Specifies Nautobot custom fields and Infoblox extensible attributes that are excluded from the sync. |

Each Infoblox configuration must be linked to an External Integration describing the Infoblox instance. The following External Integration fields must be defined for integration to work correctly:

| Remote URL | URL of the remote Infoblox instance to sync with. |
| Verify SSL | Toggle SSL verification when syncing data with Infoblox. |
| Secrets Group | Secrets Group defining credentials used when connecting to the Infoblox instance. |
| Timeout | How long HTTP requests to Infoblox should wait for a response before failing. |

The Secrets Group linked to the Infoblox External Integration must contain password and username secrets defined as per the below:

| Access Type | Secret Type |
| REST | Password |
| REST | Username |


### Configuring Infoblox Sync Filters

Infoblox Sync Filters is a mandatory setting used to control the scope of the IP objects that are loaded from Nautobot and Infoblox. Only these objects are in the scope of the synchronization process. The default value of this setting is:

```json
[
    {
        "network_view": "default"
    }
]
```

This default value specifies that all IPv4 and IPv6 objects located in Infoblox "default" Network View or Nautobot "Global" Namespace, will loaded for comparison and considered for synchronization.

Infoblox Sync Filters can contain multiple entries. Each entry is a dictionary with one mandatory key `network_view` and two optional keys `prefixes_ipv4` and `prefixes_ipv6`.

- `network_view` specifies the name of the Infoblox Network View/Nautobot Namespace from which to load IP objects. There can be only one filter entry per network view name.
- `prefixes_ipv4` (optional) - a list of top-level IPv4 prefixes from which to load IPv4 networks and IP addresses. This applies to both Infoblox and Nautobot. If this key is not defined, all IPv4 addresses within the given namespace are allowed to be loaded.
- `prefixes_ipv6` (optional) - a list of top-level IPv6 prefixes from which to load IPv6 networks and IP addresses. This applies to both Infoblox and Nautobot. If this key is not defined, all IPv6 addresses within the given namespace are allowed to be loaded.

Below is an example showing three filters used for filtering loaded data:

```json
[
    {
        "network_view": "default"
    },
    {
        "network_view": "dev",
        "prefixes_ipv4": [
            "192.168.0.0/16"
        ]
    },
    {
        "network_view": "test",
        "prefixes_ipv4": [
            "10.0.0.0/8"
        ],
        "prefixes_ipv6": [
            "2001:5b0:4100::/40"
        ]
    }
]
```

The above filters will allow the loading of the following data from Infoblox and Nautobot:

- All IPv4 and IPv6 prefixes and IP addresses in the Infoblox network view "default" and Nautobot namespace "Global".
- Only IPv4 prefixes and IP addresses, contained within the `192.168.0.0/16` container, located in Infoblox network view "dev" and Nautobot namespace "dev". All IPv6 prefixes and IP addresses in the Infoblox network view "dev" and Nautobot namespace "dev".
- Only IPv4 prefixes and IP addresses, contained within the `10.0.0.0/8` container, located in Infoblox network view "test" and Nautobot namespace "test".  Only IPv6 prefixes and IP addresses contained withing the `2001:5b0:4100::/40` container that are located in the Infoblox network view "test" and Nautobot namespace "test".


### Configuring Infoblox DNS View Mapping

Infoblox DNS View Mapping is an optional setting that tells Infoblox SSOT where to create DNS Host, A, and PTR records. Infoblox allows multiple DNS Views to be defined for one Network View. If no mappings are configured the application will create DNS records in the default DNS View associated with the Network View, usually named `default.{network_view_name}`, where `network_view_name` is the name of the parent Network View.

To define mapping specify the name of the Network View as the key and the name of the DNS View as the value. For example:


```json
{
    "dev": "dev view",
    "default": "corporate",
}
```

The above configuration will create DNS records linked to Network View "dev" in the "dev view" DNS View and records linked to Network View "default" in the "corporate" DNS View.

### Configuring Extensible Attributes/Custom Fields to Ignore

Extensible Attributes/Custom Fields to Ignore setting allows specifying Infoblox Extensive Attributes and Nautobot Custom Fields that are excluded from the synchronization. This stops unwanted extra data that is used for other purposes from being propagated between the systems.

The default value of this setting is:

```json
{
    "extensible_attributes": [],
    "custom_fields": []
}
```

That is, by default, all of the extensible attributes and custom fields will be synchronized, except the custom fields used internally by the Infoblox integration.

To exclude Infoblox extensible attributes from being synchronized to Nautobot add the attribute names to the list `extensible_attributes`  list.

To exclude Infoblox custom fields from being synchronized to Infoblox add the custom field names to the list `custom_fields`  list.

## Custom Fields, Tags, and Relationships Used by The Infoblox Integration

The Infoblox Integration requires the following Nautobot custom fields, tags, and relationships to function correctly. These are created automatically when Nautobot is started and care should be taken to ensure these are not deleted.

### Custom Fields

`dhcp_ranges` - Records DHCP ranges associated with a network. This applies to the following models: `Prefix`.
`ssot_synced_to_infoblox` - Records the date the Nautobot object was last synchronized to Infoblox. This applies to the following models: `IPAddress`, `Prefix`, `VLAN`, and `VLANGroup`.
`mac_address` - Records MAC address associated with an IP Address. This is required when creating an Infoblox Fixed Address of type MAC from Nautobot IP Address objects. This applies to the following model: `IPAddress`.
`fixed_address_comment` - Records comment for the corresponding Fixed Address record in Infoblox. This applies to the following model: `IPAddress`.
`dns_a_record_comment_custom_field` - Records comment for the corresponding DNS A record in Infoblox. This applies to the following model: `IPAddress`.
`dns_host_record_comment_custom_field` - Records comment for the corresponding DNS Host record in Infoblox. This applies to the following model: `IPAddress`.
`dns_ptr_record_comment_custom_field` - Records comment for the corresponding DNS PTR record in Infoblox. This applies to the following model: `IPAddress`.


### Tags

`SSoT Synced from Infoblox` - Used to tag Nautobot objects that were synchronized from Infoblox. This applies to the following models: `IPAddress`, `Namespace`, `Prefix`, and `VLAN`.
`SSoT Synced to Infoblox` - Used to tag Nautobot objects that were synchronized to Infoblox.
This applies to the following models: `IPAddress`, `Prefix`, and `VLAN`.


### Relationships

`prefix_to_vlan` - Used to link Nautobot Prefix to a Nautobot VLAN. This corresponds to an Infoblox Network to VLAN relationship.

### Usage Notes

- To create an Infoblox Fixed Address record from a Nautobot IP Address object the Nautobot side must have IP Address type set to `DHCP`.
- To create an Infoblox Fixed Address of type MAC the Nautobot IP Address must have a value defined in the `mac_address` custom field.


## Upgrading from `nautobot-plugin-ssot-infoblox` App

!!! warning
    When upgrading from `nautobot-plugin-ssot-infoblox` app, it's necessary to [avoid conflicts](../upgrade.md#potential-apps-conflicts).

- Uninstall the old app:
    ```shell
    pip uninstall nautobot-plugin-ssot-infoblox
    ```
- Upgrade the app with required extras:
    ```shell
    pip install --upgrade nautobot-ssot[infoblox]
    ```
