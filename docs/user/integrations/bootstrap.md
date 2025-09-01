## Usage

## Process

### Bootstrap as DataSource

Synchronization of data follows this workflow:

1. Load data from Bootstrap YAML file (limited to `models_to_sync`)
2. Load data from Nautobot (limited to `models_to_sync`, and objects that also have the `CustomField` `system_of_record` set to "Bootstrap".)
3. DiffSync determines Creates, Updates, Deletes
4. If an object is being created (an object loaded from Bootstrap was not loaded from Nautobot) Bootstrap will first check to see if an object with the same name exists in Nautobot but does not have the `system_of_record` field set. If it finds an object, it will update it with the Bootstrap values and set the `system_of_record` field to "Bootstrap".
5. If an object needs to be updated it will be updated with the values provided by Bootstrap data.
6. If an object needs to be deleted it will be deleted.

> Starting in SSoT 3.9.3, the Objects imported and updated by Bootstrap will have a [Object Metadata](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/objectmetadata/) created or updated to track the last update from Bootstrap.

### Bootstrap as DataTarget

NotYetImplemented

### Data structures

### General Notes on Data in the YAML file

Data values are generally normalized in the app code. If a value is supposed to be a string and you want it to be blank or none, include a blank string (`""`) in the value. Integers should be left completely blank. Lists should be set to an empty list (`[]`), and dictionaries should be set to a blank dictionary (`{}`) in the yaml file.

#### global_settings.yml (see '../bootstrap/fixtures/global_settings.yml for examples of supported models)

```yaml
secret:
  - name: Github_Service_Acct
    provider: environment-variable # or text-file
    parameters:
      variable: GITHUB_SERVICE_ACCT
      path:
  - name: Github_Service_Token
    provider: environment-variable # or text-file
    parameters:
      variable: GITHUB_SERVICE_TOKEN
      path:
secrets_group:
  - name: Github_Service_Account
    secrets:
      - name: Github_Service_Acct
        secret_type: username
        access_type: HTTP(S)
      - name: Github_Service_Token
        secret_type: token
        access_type: HTTP(S)
git_repository:
  - name: "Backbone Config Contexts"
    url: "https://github.com/nautobot/backbone-config-contexts.git"
    branch: "main" #  if branch is defined it will be used instead of the "git_branch" in the "branch" variable file.
    secrets_group_name: "Github_Service_Account"
    provided_data_type:
      - "config contexts"
  - name: "Datacenter Config Contexts"
    url: "https://github.com/nautobot/datacenter-config-contexts.git"
    secrets_group_name: "Github_Service_Account"
    provided_data_type:
      - "config contexts"
dynamic_group:
  - name: Backbone Domain
    content_type: dcim.device
    filter: |
      {
        "tenant": [
          "backbone"
        ]
      }
computed_field:
  - label: Compliance Change
    content_type: nautobot_golden_config.configcompliance
    template: '{{ obj | get_change_log }}'
custom_field:
  - label: Internal Circuit ID
    description: Circuit ID for internal records
    type: text
    content_types: 
      - circuits.circuit
tag:
  - name: Backbone
    color: '795548'
    content_types:
      - dcim.device
graph_ql_query:
  - name: "Backbone Devices"
    query: |
      query ($device_id: ID!) {
        device(id: $device_id) {
          config_context
          hostname: name
          device_role {
            name
          }
          tenant {
            name
          }
          primary_ip4 {
            address
          }
        }
      }
scheduled_job:
  - name: "Daily Log Cleanup"
    interval: "daily"
    start_time: "2025-01-28 23:00:00"
    job_model: "Logs Cleanup"
    user: "admin"
    job_vars:
      cleanup_types: ["extras.ObjectChange"]
      max_age: 90
software:
  - device_platform: "arista_eos"
    version: "4.25.10M"
    alias:
    release_date: "2023-12-04"
    eos_date:  "2023-12-04"
    documentation_url: "https://arista.com" # url is currently required due to a bug in the Device Lifecycle Management Plugin https://github.com/nautobot/nautobot-app-device-lifecycle-mgmt/issues/263
    lts: false
    pre_release: false
    tags: ['Backbone']
software_image:
  - software: arista_eos - 15.4.3
    platform: arista_eos
    software_version: 15.4.3
    file_name: arista15.4.3.bin
    download_url: https://arista.com
    image_file_checksum:
    default_image: false
    tags: ['Test']
validated_software:
  - software: "arista.eos.eos - 4.25.10M"
    valid_since: 2023-08-07
    valid_until:
    preferred_version: false
    tags: []
external_integration:
  - name: "Altiplano"
    remote_url: "https://my.altiplano.instance:45321"
    verify_ssl: false
    secrets_group_name: "Altiplano API Credentials"
    timeout: 30
    headers: |
      {
        "Accept": "application/yang-data+json",
        "Content-Type": "application/yang-data+json"
      }
    extra_config: |
      {
        "device_types": [
          "LS-SF-SFMB-A"
        ],
        "duid_prefixes_to_ignore": [
          "9876"
        ]
      }
```

#### develop.yml

```yaml
git_branch: develop
```

## Content Types

There are a couple models like Tags and Git Repositories that have associated content types. These require a specific format when listing them in the YAML file. The format of these is the `app_label`.`model`, though other Apps and integrations for Nautobot can add additional types (for example Golden Config types for Git Repositories), here is a list of some of the most common ones:

### Role Content Types:
```yaml
- dcim.controller
- dcim.device
- dcim.interface
- dcim.module
- dcim.rack
- dcim.virtualdevicecontext
- extras.contactassociation
- ipam.ipaddress
- ipam.prefix
- ipam.vlan
- virtualization.virtualmachine
- virtualization.vminterface
```

## Git Repository Provided Content Types

```yaml
- extras.configcontext
- extras.configcontextschema
- extras.exporttemplate
- extras.graphqlquery
- extras.job
- nautobot_device_onboarding.onboarding_command_mappers
- backup configs
- intended configs
- jinja templates
- Golden Config properties
```

### Tag Content Types
```yaml
- circuits.circuit
- circuits.circuittermination
- circuits.provider
- circuits.providernetwork
- cloud.cloudaccount
- cloud.cloudnetwork
- cloud.cloudresourcetype
- cloud.cloudservice
- dcim.cable
- dcim.consoleport
- dcim.consoleserverport
- dcim.controller
- dcim.controllermanageddevicegroup
- dcim.device
- dcim.devicebay
- dcim.devicefamily
- dcim.deviceredundancygroup
- dcim.devicetype
- dcim.frontport
- dcim.interface
- dcim.interfaceredundancygroup
- dcim.inventoryitem
- dcim.location
- dcim.module
- dcim.modulebay
- dcim.moduletype
- dcim.powerfeed
- dcim.poweroutlet
- dcim.powerpanel
- dcim.powerport
- dcim.rack
- dcim.rackreservation
- dcim.rearport
- dcim.softwareimagefile
- dcim.softwareversion
- dcim.virtualchassis
- dcim.virtualdevicecontext
- extras.contact
- extras.dynamicgroup
- extras.externalintegration
- extras.gitrepository
- extras.job
- extras.jobqueue
- extras.metadatatype
- extras.secret
- extras.team
- ipam.ipaddress
- ipam.namespace
- ipam.prefix
- ipam.routetarget
- ipam.service
- ipam.vlan
- ipam.vlangroup
- ipam.vrf
- nautobot_device_lifecycle_mgmt.contactlcm
- nautobot_device_lifecycle_mgmt.contractlcm
- nautobot_device_lifecycle_mgmt.cvelcm
- nautobot_device_lifecycle_mgmt.devicesoftwarevalidationresult
- nautobot_device_lifecycle_mgmt.hardwarelcm
- nautobot_device_lifecycle_mgmt.inventoryitemsoftwarevalidationresult
- nautobot_device_lifecycle_mgmt.softwareimagelcm
- nautobot_device_lifecycle_mgmt.softwarelcm
- nautobot_device_lifecycle_mgmt.validatedsoftwarelcm
- nautobot_device_lifecycle_mgmt.vulnerabilitylcm
- nautobot_golden_config.compliancefeature
- nautobot_golden_config.compliancerule
- nautobot_golden_config.configcompliance
- nautobot_golden_config.configplan
- nautobot_golden_config.configremove
- nautobot_golden_config.configreplace
- nautobot_golden_config.goldenconfig
- nautobot_golden_config.goldenconfigsetting
- nautobot_golden_config.remediationsetting
- nautobot_ssot.automationgatewaymodel
- nautobot_ssot.ssotinfobloxconfig
- tenancy.tenant
- virtualization.cluster
- virtualization.virtualmachine
- virtualization.vminterface
- wireless.radioprofile
- wireless.supporteddatarate
- wireless.wirelessnetwork
```

## Object Model Notes

### Manufacturer

Create Manufacturer objects. Uses the folowing data structure:

```yaml
manufacturer:
  - name:  # str
    description:  # str
```

### Platform

Create Platform objects. Uses the following data structure:

```yaml
platform:
  - name:  # str
    manufacturer:  # str
    network_driver:  # str
    napalm_driver:  # str
    napalm_arguments: {} # dict
    description:  # str
```

Ensure Manufacturer objects are created before reference.

### LocationType

Create LocationType objects. Uses the following data structure:

```yaml
location_type:
  - name:  # str
    parent:  # str
    nestable: # bool
    description:  # str
    content_types: [] # List[str]
```

### Location

Create Location objects. Uses the following data structure:

```yaml
location:
  - name:  # str
    location_type:  # str
    parent:  # str
    status:  # str
    facility:  # str
    asn: # int
    time_zone:   # str
    description:  # str
    tenant:  # str
    physical_address:  # str
    shipping_address:  # str
    latitude:  # str
    longitude:  # str
    contact_name:  # str
    contact_phone:  # str
    contact_email:  # str
    tags: [] # List[str]
```

`location_type`, `parent`, `status`, `time_zone`, `tenant`, and `tags` are all references to objects. Ensure they exist prior to attempting to reference them here.

Ensure that location types that you reference here are first defined in the location models or they will fail to create.

### TenantGroup

Create TenantGroup objects. Uses the following data structure:

```yaml
tenant_group:
  - name:  # str
    parent:  # str
    description:  # str
```

### Tenant

Create Tenant objects. Uses the following data structure:

```yaml
tenant:
  - name:  # str
    tenant_group:  # str
    description:  # str
    tags: []  # List[str]
```

Ensure that tenant groups that you reference here are first defined in the location models or they will fail to create.

### Role

Create Role objects. Uses the following data structure:

```yaml
role:
  - name: # str
    weight: # int
    description: # str
    color: # str
    content_types: # List[str]
  - name: "Administrative"   # str
    weight: # int
    description: "Unit plays an administrative role"  # str
    color: "2196f3"  # str
    content_types: # List[str]
      - "extras.contactassociation"
  - name: "Anycast"
    weight:
    description: ""
    color: "ffc107"
    content_types:
      - "ipam.ipaddress"
  - name: "Billing"
    weight:
    description: "Unit plays a billing role"
    color: "4caf50"
    content_types:
      - "extras.contactassociation"
  - name: "CARP"
    weight:
    description: ""
    color: "4caf50"
    content_types:
      - "ipam.ipaddress"
  - name: "GLBP"
    weight:
    description: ""
    color: "4caf50"
    content_types:
      - "ipam.ipaddress"
  - name: "HSRP"
    weight:
    description: ""
    color: "4caf50"
    content_types:
      - "ipam.ipaddress"
  - name: "Loopback"
    weight:
    description: ""
    color: "9e9e9e"
    content_types:
      - "ipam.ipaddress"
  - name: "On Site"
    weight:
    description: "Unit plays an on site role"
    color: "111111"
    content_types:
      - "extras.contactassociation"
  - name: "Secondary"
    weight:
    description: ""
    color: "2196f3"
    content_types:
      - "ipam.ipaddress"
  - name: "Support"
    weight:
    description: "Unit plays a support role"
    color: "ffeb3b"
    content_types:
      - "extras.contactassociation"
  - name: "VIP"
    weight:
    description: ""
    color: "4caf50"
    content_types:
      - "ipam.ipaddress"
  - name: "VRRP"
    weight:
    description: ""
    color: "4caf50"
    content_types:
      - "ipam.ipaddress"
```

This also recreates the default Roles included in Nautobot core. This is because the Role model does not support custom fields, and therefore can not be selectively synced with the SSoT framework. Any roles not included in the Bootstrap `global_settings.yaml` file will be deleted. The list obove is the default list of roles included in Nautobot Core. See section on Content Types for examples of what can be listed in `content_types`.

### Team

Create Team objects. Uses the following data structure:

```yaml
team:
  - name:  # str
    phone:  # str
    email:  # str
    address:  # str
    # contacts: []
```

Currently, assigning contacts to a team through the `contact:` key is not supported due to the way that DiffSync works. Assign Contacts to a Team by adding the Team to the `team` list in the `Contact` model. In part this is due to the fact that contacts need to exist before being assigned to `team.contacts`.

### Contact

Create Contact objects. Uses the following data structure:

```yaml
contact:
  - name:  # str
    phone:  # str
    email:  # str
    address:  # str
    teams: [] # List[str]
```

As noted above, a `Contact` can be assigned to a `Team` by listing the `Team` names in the `teams:` key in the `Contact` model.


### Provider

Create Provider objects. Uses the following data structure:

```yaml
provider:
  - name:  # str
    asn: # int
    account_number:  # str
    portal_url:  # str
    noc_contact:  # str
    admin_contact:  # str
    tags: [] # List[str]
```

### Provider Network

Create ProviderNetwork objects. Uses the following data structure:

```yaml
provider_network:
  - name: # str
    provider: # str
    description: # str
    comments: # str
    tags: [] # List[str]
```

`provider` is a reference to a Provider object. Ensure it exists before trying to assign it.

### CircuitType

Create CircuitType objects. Uses the following data structure:

```yaml
circuit_type:
  - name: # str
    description: # str
```

### Circuit

Create Circuit objects. Uses the following data structure:

```yaml
circuit:
  - circuit_id: # str
    provider: # str
    circuit_type: # str
    status: # str
    date_installed: # date (YYYY-MM-DD)
    commit_rate_kbps:  # int
    description: # str
    tenant: # str
    tags: [] # List[str]
```

`circuit_type`, `status`, `tenant`, and `tags` are references to existing objects in Nautobot. Make sure these exist before trying to assign them.

### CircuitTermination

Create CircuitTermination objects. Uses the following data structure.

```yaml
circuit_termination:
  - name: # str
    termination_type: # str
    location: # str
    provider_network: # str
    port_speed_kbps: # int
    upstream_speed_kbps: # int
    cross_connect_id: # str
    patch_panel_or_ports: # str
    description: # str
    tags: [] # List[str]
```

`termination_type` can be "Provider Network" or "Location" which are the only allowed relationships in the database for CircuitTermination objects. If you specify `termination_type` as "Provider Network" you will need to provide a valid Provider Network name in the `provider_network` field. If you specify "Location" as the `termination_type` you will specify a valid Location name in the `location` field. The `name` field is a bit special and should be formatted as follows as it is used to reference the Circuit objects `<circuit_id>__<provider_name>__<termination_side>`. The termination side can be "A" or "Z", and the Circuit ID and Provider Name are used to look up the correct Circuit and Provider information on creation, so make sure those exist prior to reference.

### Namespace (IPAM)

Create Namespace objects. Uses the following data structure:ß

```yaml
namespace:
  - name: # str
    description: # str
    location: # str
```

`location` is a reference to a location name and the app will attempt to look up this location by name and associate it with the namespace. Make sure the location exists. All uniqueness constraints are enforced by the ORM.

### RIR (IPAM)

Create RIR objects. Uses the following data structure:

```yaml
rir:
  - name: # str
    private: # bool: defaults to false
    description: # str
```

### VRF (IPAM)

Create VRF objects. Uses the following data structure:

```yaml
vrf:
  - name: # str
    namespace: # str
    route_distinguisher: # str
    description: # str
    # prefixes: # List[str]
    tenant: # str
    tags: # List[str]
```

`namespace` and `tenant` are strings which reference the namespace and tenant names respectively. Make sure these exist in Nautobot or are in global_settings.yaml so they can be associated. `tenant` defaults to None if blank or can't find the Nautobot Tenant. `namespace` defaults to the Global namespace if blank or can't be found. Currently due to the order that the app syncs objects, `prefixes` can't be defined on VRFs and must be assigned from the `prefix` object by specifying `vrfs` on the `prefix` definition. All uniqueness constraints are enforced by the ORM.

### VLAN Group

Create VLANGroup objects. Uses the following data structure:

```yaml
vlan_group:
  - name: # str
    location: # str
    description: # str
```

`location` is a reference to a location name and the app will attempt to look up this location by name and associate it with the namespace. Make sure the location exists. All uniqueness constraints are enforced by the ORM.

### VLAN

Create VLAN objects. Uses the following data structure:

```yaml
vlan:
  - name: # str
    vid: # int between 1 and 4094
    description: # str
    status: # str
    role: # str
    locations: # List[str]
    vlan_group: # str
    tenant: # str
    tags: # List[str]
```

`locations` and `tags` lists of strings which reference the location and tag names respectively. Make sure these exist in Nautobot or are in global_settings.yaml so they can be associated. `vlan_group` is a reference to a Nautobot VLANGroup name. This will be associated if it exists, or default to None if the Nautobot VLANGroup can't be found. `tenant`, `role`, and `status` are references to Tenant, Role, and Status objects in Nautobot. The app will attempt to look these up and associate them. `role` and `tenant` default to None if the object can't be found. `status` defaults to Active if a improper status is defined. All uniqueness constraints are enforced by the ORM.

### Prefix

Create Prefix objects. Uses the following data structure:

```yaml
prefix:
  - network: # str (cidr notation)
    namespace: # str
    prefix_type: # str  # network, container, or pool
    status: # str
    role: # str
    rir: # str
    date_allocated: # str(datetime) (YYYY-mm-dd HH:mm:ss)
    description: # str
    vrfs: # List[str]
    locations: # List[str]
    vlan: # str
    tenant: # str
    tags: # List[str]
```

`vrfs`, `locations`, and `tags` are lists of strings that reference the names of VRF, Location, and Tag objects in Nautobot. Make sure these exist or they will default to None if they can't be found. `network` is the CIDR notation for the prefix. `namespace`, `status`, `role`, `rir`, `vlan`, and `tenant` are also references to names of their respective objects in Nautobot. `status` defaults to Active, and the rest default to None if not found or are left blank. `prefix_type` options are limited by the `PrefixStatusChoices` defined in `nautobot.ipam.choices`. `date_allocated` should be in the format indicated above as a datetime string (Year-Month-Day Hours:Minutes:Seconds) with time in 24 hour format in order to properly set the `date_allocated` field on the prefix object. For example "1970-01-01 00:00:00". They are all lowercase network, container, or pool. All uniqueness constraints are enforced by the ORM.

### Secret

Create Secret objects. Uses the following data structure:

```yaml
secret:
  - name:  # str
    provider: "environment-variable"  # or text-file
    parameters:  # str
      variable: # str
      path: # str
```

`Secret` objects need to be created before `SecretsGroup` objects references them, so make sure any `Secret` objects you are wanting to reference in `SecretGroups` objects are created here or already exist in Nautobot.

### SecretsGroup

Create SecretsGroup objects. Uses the following data structure:

```yaml
secrets_group:
  - name: # str
    secrets: # str
      - name: # str
        secret_type: # str
        access_type: # str
      - name: # str
        secret_type: # str
        access_type: # str
```

`Secret` objects need to be created before SecretsGroup references them, so make sure any `Secret` objects you are wanting to reference in `SecretGroups` objects are created here or already exist in Nautobot.

### GitRepository

Create GitRepository objects. Uses the following data structure:

```yaml
git_repository:
  - name: # str
    url: # str
    branch: # str
    secrets_group_name: # str
    provided_data_type: [] # List[str]

# develop/staging/production.yaml
git_branch: # str
```

GitRepositories are a bit unique. If you specify they `branch:` key in the global_settings.yaml file, this will override the `git_branch:` key in the `<environment>.yaml` file. The `git_branch:` key in the environment specific yaml file is the default, so you don't have to specify branches for each git repository. See section on Content Types for examples of what can be listed in `provided_data_type`.

### DynamicGroup

Create DynamicGroup objects. Uses the following data structure:

```yaml
dynamic_group:
  - name: # str
    content_type: # str
    description: # str
    filter: | # str
```

The `filter:` key for DynamicGroup objects takes a string representation of the JSON filter to group the devices required.

### Computed_Field

Create ComputedField objects. Uses the following data structure:

```yaml
computed_field:
  - label: # str
    content_type: # str
    template: # str
```

The `template:` key for ComputedField objects takes a jinja variable format string which will display the calculated information.

### Custom_Field

Create CustomField objects. Uses the following data structure, only `label`, `type`, and `content_types` are required. Any custom_fields not included in the Bootstrap `global_settings.yaml` file may be deleted.

```yaml
custom_field:
  - label: CustomField1 # str
    type: text # str -- Options are: text, integer, boolean, date, url, select, multi-select, json, markdown
    content_types: # list
      - dcim.device
      - circuits.circuit
    # Optional Arguments
    required: # bool, default: False
    grouping: # str
    weight: # int, default: 100
    default: # default value, type depends on custom_field type
    filter_logic: # str -- Options are loose, disabled, exact, default: loose
    advanced_ui: # bool, move this field to the Advanced page. default: False
    validation_minimum: # int
    validation_maximum: # int
    validation_regex: # str
    custom_field_choices: # list, requires Type of 'select' or 'multi-select'
      - value: Choice1-Value
        weight: 100
      - value: Choice2-Value
        weight: 200
```

### Tag

Create Tag objects. Uses the following data structure:

```yaml
tag:
  - name: # str
    color: # str
    description: # str
    content_types: [] # List[str]
```

The `color` tag is optional, but will default to grey if not specified. The `content_types` list is a list of `path.model` formatted strings for the types of objects that the tags should be able to apply to. See section on Content Types for examples of what can be listed in `content_types`.

### GraphQLQuery

Create GraphQLQuery objects. Uses the following data structure:

```yaml
graph_ql_query:
  - name: # str
    query: | # str
```

The `query:` key takes a graphql formatted string to retrieve the information required.

### ScheduledJob
Create a ScheduledJob. The Job to be scheduled must already exist. As Job's vary greatly, any Job specific variables should be under the `job_vars` key, and you should check the Job specific documentation for details on what these values should be. The `start_time` must be in the future if the ScheduledJob is being updated or created. Once created, it does not need to be updated unless you wish to modify the schedule. The Bootstrap `system_of_record` cannot be applied to ScheduledJobs, make sure all desired ScheduledJobs exist in your YAML definition.

!!! warning
    Use of the `enabled` parameter to disable a ScheduledJob will cause it to no longer appear in the Scheduled Jobs list view in the UI. You will need to use Bootstrap again or the [nbshell](https://docs.nautobot.com/projects/core/en/stable/user-guide/administration/tools/nautobot-shell/) to re-enable it.

```yaml
scheduled_job:
  - name: # str
    interval: # str -- Options are: daily, weekly, hourly, future, custom
    start_time: # str -- ISO 8601 format (YYYY-MM-DD HH:MM:SS), UTC
    crontab: # str -- Basic Crontab syntax. Use with interval 'custom'
    job_model: # str -- The name of the Job you wish to schedule
    user: # str -- Username to run this scheduled job as
    enabled: # bool -- Optional, defaults to True
    profile: # bool -- Optional, defaults to False
    task_queue: # str -- Optional, celery queue name, defaults to None (default queue)
    job_vars: # dict -- Optional
      job_var1: # specific to Job
      job_var2: # ...etc
```

### Software

- Note: Requires Nautobot Device Lifecycle Plugin Installed

Create Software objects. Uses the following data structure:

```yaml
software:
  - device_platform: # str
    status: * # str
    version: # str
    alias: # str
    release_date: # date (YYYY-MM-DD)
    eos_date: # date (YYYY-MM-DD)
    documentation_url:  # str
    lts: # bool
    pre_release: # bool
    tags: [] # List[str]
```

The `device_platform` key must be a Platform that exists in Nautobot or is created by this plugin. The date fields `release_date` and `eos_date` need to be formatted YYYY-MM-DD in order to properly import. Fields with a * are required if on Nautobot version 2.3.0 or later as the models moved to Core from the Device LifeCycle app and added additional required fields.

### SoftwareImage

- Note: Requires Nautobot Device Lifecycle Plugin Installed

Create Software Image objects. Uses the following data structure:

```yaml
software_image:
  - software: # str
    platform: # str
    status: * # str
    software_version: # str
    file_name: # str
    file_size: * # int
    download_url: # str
    image_file_checksum: # str
    hashing_algorithm: # str
    default_image: # bool
    device_types: * [] # List[str]
    tags: [] # List[str]
```

The `software`, `platform`, and `software_version` keys are linked and should be consistent. The Platform and Software must already be present in Nautobot for these models to be created. The format for the `software:` key is important and should be `<platform><space>-</space><software_version>`. Fields with a * are required if on Nautobot version 2.3.0 or later as the models moved to Core from the Device LifeCycle app and added additional required fields.

### ValidatedSoftware

- Note: Requires Nautobot Device Lifecycle Plugin Installed

Create ValidatedSoftware objects. Uses the following data structure:

```yaml
validated_software:
  - software: # str
    valid_since: # date (YYYY-MM-DD)
    valid_until: # date {YYYY-MM-DD}
    preferred_version: # bool
    devices: [] # List[str]
    device_types: [] # List[str]
    device_roles: [] # List[str]
    inventory_items: [] # List[str]
    object_tags: [] # List[str]
    tags: [] # List[str]
```

The `software:` key is a reference to the platform and software version of a Software object that already exists in Nautobot (or is created by this plugin). The `valid_since` and `valid_until` fields must dates in YYYY-MM-DD format. The `devices`, `device_types`, `device_roles`, `inventory_items`, and `object_tags` are all lists of objects to apply the validated software to for validation against what is currently running on the device.

### ExternalIntegration

Create ExternalIntegration objects. Uses the following data structure, only `name`, `remote_url`, and `timeout` are required. Any external_integrations not included in the Bootstrap `global_settings.yaml` file may be deleted.

```yaml
external_integration:
  - name: # str
    remote_url: # str
    timeout: # int
    # Optional Arguments
    verify_ssl: # bool, default: True
    secrets_group_name: # str
    headers: {} # dict
    http_method: # str -- Options are: get, post, put, patch, delete
    ca_file_path: # str
    extra_config: {} # dict
    tags: [] # List[str]
```
