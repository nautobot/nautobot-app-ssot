# Developing Data Source and Data Target Jobs

A goal of this Nautobot app is to make it relatively quick and straightforward to develop and integrate your own system-specific Data Sources and Data Targets into Nautobot with a common UI and user experience.

Familiarity with [DiffSync](https://diffsync.readthedocs.io/en/latest/) and with developing [Nautobot Jobs](https://nautobot.readthedocs.io/en/latest/additional-features/jobs/) is recommended.

## Quickstart Example

The following code presents a minimum viable example for syncing VLANs from a remote system into Nautobot. You will have to adapt the following things to make this work for your use case:

- Swap out any mention of a "remote system" for your actual remote system, such as your IPAM tool
- Implement any models that you need, unless you are actually only interested in VLAN data
- Your `load` function in the remote adapter will probably be a little harder to implement, check the example integrations in this repository (under `nautobot_ssot/integrations`)

It contains 3 steps:

- Data modeling
- Adapters
    - Nautobot
    - Remote
- Nautobot Job

```python
# example_ssot_plugin/jobs.py
from typing import Optional

from diffsync import DiffSync
from nautobot.ipam.models import VLAN
from nautobot.extras.jobs import Job
from nautobot_ssot.contrib import NautobotModel, NautobotAdapter
from nautobot_ssot.jobs import DataSource
from remote_system import APIClient  # This is only an example


# Step 1 - data modeling
class VLANModel(NautobotModel):
    """DiffSync model for VLANs."""
    _model = VLAN
    _modelname = "vlan"
    _identifiers = ("vid", "group__name")
    _attributes = ("description",)

    vid: int
    group__name: Optional[str] = None
    description: Optional[str] = None

# Step 2.1 - the Nautobot adapter
class MySSoTNautobotAdapter(NautobotAdapter):
    """DiffSync adapter for Nautobot."""
    vlan = VLANModel
    top_level = ("vlan",)

# Step 2.2 - the remote adapter
class MySSoTRemoteAdapter(DiffSync):
    """DiffSync adapter for remote system."""
    vlan = VLANModel
    top_level = ("vlan",)
    
    def __init__(self, *args, api_client, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_client = api_client

    def load(self):
        for vlan in self.api_client.get_vlans():
            loaded_vlan = self.vlan(vid=vlan["vlan_id"], group__name=vlan["grouping"], description=vlan["description"])
            self.add(loaded_vlan)

# Step 3 - the job
class ExampleDataSource(DataSource, Job):
    """SSoT Job class."""
    class Meta:
        name = "Example Data Source"

    def load_source_adapter(self):
        self.source_adapter = MySSoTRemoteAdapter(api_client=APIClient())
        self.source_adapter.load()

    def load_target_adapter(self):
        self.target_adapter = MySSoTNautobotAdapter()
        self.target_adapter.load()

jobs = [ExampleDataSource]
```

!!! note
    This example is able to be so brief because usage of the `NautobotModel` class provides `create`, `update` and `delete` out of the box for the `VLANModel`. If you want to sync data _from_ Nautobot to another remote system, you will need to implement those yourself using whatever client or SDK provides the ability to write to that system. For examples, check out the existing integrations under `nautobot_ssot/integrations`

The following sections describe the individual steps in more detail.

### Step 1 - Defining the Models

The models use DiffSync, which in turn uses [Pydantic](https://docs.pydantic.dev/latest/) for its data modeling. Nautobot SSoT comes with a set of classes in `nautobot_ssot.contrib` that implement a lot of functionality for you automatically, provided you adhere to a set of rules.

The first rule is to define your models tightly after the Nautobot models themselves. Example:

```python
from nautobot.tenancy.models import Tenant
from nautobot_ssot.contrib import NautobotModel

class DiffSyncTenant(NautobotModel):
    """An example model of a tenant."""
    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("description",)

    name: str
    description: str
```

As you can see when looking at the [source code](https://github.com/nautobot/nautobot/blob/develop/nautobot/tenancy/models.py#L81) of the `nautobot.tenancy.models.Tenant` model, the fields on this model (`name` and `description`) match the names of the fields on the Nautobot model exactly. This enables the base class `NautobotModel` to dynamically load, create, update and delete your tenants without you needing to implement this functionality yourself.

The above example shows the simplest field type (an attribute on the model), however, to build a production implementation you will need to understand how to identify different variants of fields by following the [modeling docs](../user/modeling.md).

### Step 2.1 - Creating the Nautobot Adapter

Having created all your models, creating the Nautobot side adapter is very straight-forward:

```python
from nautobot_ssot.contrib import NautobotAdapter

from your_ssot_app.models import DiffSyncDevice, DiffSyncPrefix, DiffSyncIPAddress


class YourSSoTNautobotAdapter(NautobotAdapter):
    top_level = ("device", "prefix")

    device = DiffSyncDevice
    prefix = DiffSyncPrefix
    ip_address = DiffSyncIPAddress  # Not in the `top_level` tuple, since it's a child of the prefix model
```

The `load` function is already implemented on this adapter and will automatically and recursively traverse any children relationships for you, provided the models are [defined correctly](../user/modeling.md).

Developers are able to override the default loading of basic parameters to control how that parameter is loaded from Nautobot. 

This only works with basic parameters belonging to the model and does not override more complex parameters (foreign keys, custom fields, custom relationships, etc.).

To override a parameter, simply add a method with the name `load_param_{param_key}` to your adapter class inheriting from `NautobotAdapter`:

```python
from nautobot_ssot.contrib import NautobotAdapter

class YourSSoTNautobotAdapter(NautobotAdapter):
    ...    
    def load_param_time_zone(self, parameter_name, database_object):
        """Custom loader for `time_zone` parameter."""
        return str(getattr(database_object, parameter_name))
```

### Step 2.2 - Creating the Remote Adapter

Regardless of which direction you are synchronizing data in, you need to write the `load` method for the remote adapter yourself. You can find many examples of how this can be done in the `nautobot_ssot.integrations` module, which contains pre-existing integrations with remote systems.

!!! note
    As the features in `nautobot_ssot.contrib` are still very new, most existing integrations do not use them. The example job in `nautobot_ssot/jobs/examples.py` can serve as a fully working example.

### Step 3 - The Job

Develop a Job class, derived from either the `nautobot_ssot.jobs.base.DataSource` or `nautobot_ssot.jobs.base.DataTarget` classes provided by this Nautobot app, and implement the methods to populate the `self.source_adapter` and `self.target_adapter` attributes that are used by the built-in implementation of `sync_data`. This `sync_data` method is an opinionated way of running the process including some performance data (more about this in the next section), but you could overwrite it completely or any of the key hooks that it calls.

The methods [`calculate_diff`][nautobot_ssot.jobs.base.DataSyncBaseJob.calculate_diff] and [`execute_sync`][nautobot_ssot.jobs.base.DataSyncBaseJob.execute_sync] are both implemented by default, using the data that is loaded into the adapters through the respective methods. Note that `execute_sync` will _only_ execute when dry-run is set to false.

Optionally, on your Job class, also implement the [`lookup_object`][nautobot_ssot.jobs.base.DataSyncBaseJob.lookup_object], [`data_mapping`][nautobot_ssot.jobs.base.DataSyncBaseJob.data_mappings], and/or [`config_information`][nautobot_ssot.jobs.base.DataSyncBaseJob.config_information] APIs (to provide more information to the end user about the details of this Job), as well as the various metadata properties on your Job's Meta inner class. Refer to the example Jobs provided in this Nautobot app for examples and further details.
Install your Job via any of the supported Nautobot methods (installation into the `JOBS_ROOT` directory, inclusion in a Git repository, or packaging as part of an app) and it should automatically become available!

### Extra Step: Implementing `create`, `update` and `delete`

If you are synchronizing data _to_ Nautobot and not _from_ Nautobot, you can entirely skip this step. The `nautobot_ssot.contrib.NautobotModel` class provides this functionality automatically.

If you need to perform the `create`, `update` and `delete` operations on the remote system however, it will be up to you to implement those on your model.

!!! note
    You still want your models to adhere to the [modeling guide](../user/modeling.md), since it provides you the auto-generated `load` function for the diffsync adapter on the Nautobot side.
