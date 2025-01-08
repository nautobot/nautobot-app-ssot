# Tutorial: Developing a Data Source Integration

This tutorial will walk you through building a custom DataSource (i.e. synchronizing data _to_ Nautobot) SSoT integration with a remote system. We will be using static data as the remote system, but it should be easy enough to substitute this later for any external system you want to integrate with.

*Familiarity with [DiffSync](https://diffsync.readthedocs.io/en/latest/) and with developing [Nautobot Jobs](https://nautobot.readthedocs.io/en/latest/additional-features/jobs/) is a plus, but important concepts will be explained or linked to along the way.**

## Creating a New Nautobot App

To start building your own SSoT integration, you first need a project as well as the accompanying development environment. Network to Code provides the [Cookiecutter Nautobot App](https://github.com/nautobot/cookiecutter-nautobot-app) to make this as easy as possible for you. Check out the README of that project and bake a `nautobot-app-ssot` cookie.

Resume this tutorial whenever you have a folder on your development device with an up and running development environment.

## Building the model

To synchronize data from a remote system into Nautobot, you need to first write a common model to bridge between the two systems. This model will be a [Pydantic](https://docs.pydantic.dev/latest/) model with built-in SSoT intelligence on top, specifically a subclass of `nautobot_ssot.contrib.NautobotModel`.

The following code snippet shows a basic VLAN model that includes the `name`, `vid` and `description` fields for the synchronization:

```python
# tutorial_ssot_app/ssot/models.py
from typing import Optional

from nautobot.ipam.models import VLAN
from nautobot_ssot.contrib import NautobotModel


class VLANModel(NautobotModel):
    _model = VLAN  # `NautobotModel` models need to have a 1-to-1 mapping with a concrete Nautobot model
    _modelname = "vlan"  # This is the model name DiffSync uses for its logging output
    _identifiers = ("name",)  # These are the fields that uniquely identify a model instance
    _attributes = ("vid", "status__name", "description",)  # The rest of the data fields go here
    
    # The field names here need to match those in the Nautobot model exactly, otherwise it doesn't work.
    name: str  
    vid: int
    description: Optional[str] = None
    
    # This is a foreign key to the `extras.status` model whose instances can be uniquely identified through its `name`
    # field.
    status__name: str
```

!!! note
    This example is able to be so brief because usage of the `NautobotModel` class provides `create`, `update` and `delete` methods out of the box for the `VLANModel`. If you want to sync data _from_ Nautobot _to_ another remote system, you will need to implement those yourself using whatever client or SDK provides the ability to write to that system. For examples, check out the existing integrations under `nautobot_ssot/integrations`.


## Building the Adapters

On its own, the model is not particularly interesting. We have to combine it with an adapter to make it do interesting things. The adapter is responsible for pulling data out of Nautobot or your remote system (which is also Nautobot if you're following this tutorial). 

### Building the Local Adapter

First, we define the adapter to load data from the local Nautobot instance - this is very straight-forward.

```python
# tutorial_ssot_app/ssot/adapters.py
from nautobot_ssot.contrib import NautobotAdapter
from tutorial_ssot_app.ssot.models import VLANModel


class MySSoTNautobotAdapter(NautobotAdapter):
    vlan = VLANModel  # Map your model into your `NautobotAdapter` subclass
    top_level = ("vlan",)  # Configure the order of model processing
```

Now create a couple of VLANs in the web GUI of Nautobot so that the adapter has some data to load. Once you're done, you can test the adapter using the Python REPL interface as follows:

```python
from tutorial_ssot_app.ssot.adapters import MySSoTNautobotAdapter

adapter = MySSoTNautobotAdapter(job=None)
adapter.load()
adapter.count("vlan")  # This will return the amount of VLANs that were loaded from Nautobot

test_vlan = adapter.get_all("vlan")[0]  # Now we retrieve an example VLAN to test the model with
test_vlan.update(attrs={"description": "My updated description"})  # Verify the update has worked using the web GUI
test_vlan.delete()  # Verify the deletion has worked using the web GUI
```

### Building the Remote Adapter

To synchronize a diff, we need to pull data from both Nautobot and the remote system of record. Therefore, we now need to build the remote adapter. In this example we are reading static data, but feel free to substitute this adapter with your remote system of choice.

!!! note
    Note that we are not subclassing from `nautobot_ssot.contrib.NautobotAdapter` here as we don't want the SSoT framework to auto-derive the loading implementation of the adapter for us, but rather want to handle this ourselves.

```python
# tutorial_ssot_app/ssot/adapters.py
from diffsync import Adapter

from tutorial_ssot_app.ssot.models import VLANModel

class MySSoTRemoteAdapter(Adapter):
    """DiffSync adapter for remote system."""
    vlan = VLANModel
    top_level = ("vlan",)

    def __init__(self, *args, api_client, job=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_client = api_client
        self.job = job

    def load(self):
        vlans = [
            {"name": "Servers", "vid": 100, "description": "Server VLAN Datacenter", "status__name": "Active"},
            {"name": "Printers", "vid": 200, "description": "Printer VLAN Office", "status__name": "Deprecated"},
            {"name": "Clients", "vid": 300, "description": "Client VLAN Office", "status__name": "Active"},
        ]
        for vlan in vlans:
            loaded_vlan = self.vlan(
                name=vlan["name"],
                vid=vlan["vid"],
                description=vlan["description"],
                status__name=vlan["status__name"]
            )
            self.add(loaded_vlan)
```

Now you can verify that this adapter is working in a similar manner to how we did with the Nautobot adapter, feel free to try this!

## Putting it Together in a Job

Having built the model and both adapters, we can now put everything together into a job to finish up the integration.

```python
# tutorial_ssot_app/jobs.py
from nautobot_ssot.jobs.base import DataSource
from nautobot.apps.jobs import Job, register_jobs
from tutorial_ssot_app.ssot.adapters import MySSoTRemoteAdapter, MySSoTNautobotAdapter

class TutorialDataSource(DataSource):
    class Meta:
        name = "Example Data Source"

    def load_source_adapter(self):
        self.source_adapter = MySSoTRemoteAdapter(api_client=APIClient(), job=self)
        self.source_adapter.load()

    def load_target_adapter(self):
        self.target_adapter = MySSoTNautobotAdapter(job=self)
        self.target_adapter.load()

register_jobs(TutorialDataSource)
```

At this point, the job will show up in the web GUI, and you can enable it and even run it! You should see the objects you specified in the remote adapter being synchronized into Nautobot now. Clicking on the "SSoT Sync Details" button in the top right of the job result page provides additional information on what is happening during the synchronization process.

The above example shows the simplest field type (an attribute on the model), however, to build a production implementation you will need to understand how to identify different variants of fields by following the [modeling docs](../dev/modeling.md).
