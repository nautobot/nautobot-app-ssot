# Models

In [`DiffSync`](https://github.com/networktocode/diffsync), a *model* describes one kind of record that both sides of a sync agree on: which fields uniquely identify it, which fields are compared, and how it nests under other records.

The `nautobot_ssot.contrib.model` module provides `NautobotModel`, a `DiffSyncModel` base class that maps a DiffSync model onto a Nautobot (Django ORM) model. A `NautobotModel` subclass gets working `create`, `update`, and `delete` methods for free, and tells the [`NautobotAdapter`](./adapters.md) everything it needs to load existing data from Nautobot.

## Defining a model

Subclass `NautobotModel`, point it at the ORM model with `_model`, and declare its fields:

```python
from typing import Optional

from nautobot.tenancy.models import Tenant
from nautobot_ssot.contrib import NautobotModel


class DiffSyncTenant(NautobotModel):
    """DiffSync model for Nautobot tenants."""

    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("description", "tenant_group__name")

    name: str
    description: str
    tenant_group__name: Optional[str] = None
```

| Attribute      | Purpose                                                                                                                                         |
|----------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| `_model`       | The Nautobot ORM model class this DiffSync model maps to. Required.                                                                             |
| `_modelname`   | The DiffSync name of the model. The adapter attribute holding this class must use the same name (see [Adapters](./adapters.md)).               |
| `_identifiers` | Fields that together uniquely identify a record. Used to match records between the two systems; they cannot change during an update.           |
| `_attributes`  | Fields that are compared and synchronized. A change in any of them results in an update.                                                        |
| `_children`    | Optional. Maps a child model's `_modelname` to the ORM field or attribute that returns its related objects, e.g. `{"interface": "interfaces"}`. |

Each name in `_identifiers` and `_attributes` must also be declared as a typed field on the class. How each field is named and typed depends on what it maps to in Nautobot: normal fields, foreign keys (`__` lookup syntax), to-many relationships, custom fields, and custom relationships each follow their own convention. The [modeling guide](../modeling.md) covers each one in detail, and [ObjectMetadata-Backed Fields](../../dev/contrib_object_metadata.md) covers fields stored as object metadata.

!!! note
    Every `NautobotModel` also has a `pk` field. The adapter fills it with the primary key of the ORM object when loading from Nautobot, and `update` and `delete` use it to find that object again. It is not synchronized, so do not add it to `_identifiers` or `_attributes`.

## Nesting models with `_children`

Use `_children` to nest one model under another, for example interfaces under devices:

```python
from typing import List

from nautobot.dcim.models import Device, Interface
from nautobot_ssot.contrib import NautobotModel


class DiffSyncInterface(NautobotModel):
    _model = Interface
    _modelname = "interface"
    _identifiers = ("device__name", "name")
    _attributes = ("description",)

    device__name: str
    name: str
    description: str


class DiffSyncDevice(NautobotModel):
    _model = Device
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = ()
    _children = {"interface": "interfaces"}

    name: str
    interfaces: List[DiffSyncInterface] = []
```

The value in `_children` (`"interfaces"` here) does two jobs: it names the attribute on the ORM object that returns the related objects, and it names the field on the DiffSync model where DiffSync tracks the children. Declare that field as a list with an empty default, as above.

When loading from Nautobot, the adapter reads `device.interfaces` for every device and loads each result as a `DiffSyncInterface` under its parent. The child model does not go in the adapter's `top_level`.

## Create, update, and delete

`NautobotModel` implements all three CRUD operations against the ORM:

- **`create`** builds a new `_model` instance from the identifiers and attributes, resolves foreign keys and relationships, validates it, and saves it.
- **`update`** fetches the existing object by `pk`, applies the changed attributes, and saves it.
- **`delete`** fetches the existing object by `pk` and deletes it.

Failures raise DiffSync's `ObjectNotCreated`, `ObjectNotUpdated`, or `ObjectNotDeleted`. Deleting an object that another object still references (a Django `ProtectedError`) raises `ObjectNotDeleted` rather than crashing the sync.

If you need extra behavior, override the method and call `super()`:

```python
class DiffSyncTenant(NautobotModel):
    ...

    def delete(self):
        """Log tenants before they are removed."""
        self.adapter.job.logger.info(f"Deleting tenant {self.name}")
        return super().delete()
```

!!! note
    These methods write to Nautobot, so they only matter when Nautobot is the *target* of the sync. When syncing *from* Nautobot to a remote system, the remote side's models need their own `create`, `update`, and `delete`; see [Developing Data Source and Data Target Jobs](../../dev/jobs.md#extra-step-1-implementing-create-update-and-delete).

## Custom Querysets

By default every object of `_model` is loaded. To limit the sync to a subset based on a predefined filter, you can override the `get_queryset` class method:

```python
class DiffSyncTenant(NautobotModel):
    ...

    @classmethod
    def get_queryset(cls):
        return Tenant.objects.filter(tenant_group__name="Customers")
```

The adapter adds `prefetch_related` for the foreign keys in your synced fields on top of whatever you return, so you do not need to handle prefetching yourself.

!!! warning
    Objects outside the queryset are not loaded, so they do not appear in the diff, and the sync will not update or delete them. If the remote system contains a record matching one of them, the sync will try to *create* it and may fail on a uniqueness constraint.
