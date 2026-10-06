# Adapters

In [`DiffSync`](https://github.com/networktocode/diffsync), an *adapter* loads data from one system into defined `DiffSyncModel` instances and saves them to its internal datastore. Each adapter is specific to one system, such as Nautobot or ServiceNow. A *diff* requires two adapters to be loaded to determine the differences between the two.

The `nautobot_ssot.contrib.adapter` module provides reusable boilerplate code for loading Nautobot ORM objects into a [`NautobotModel` class](./models.md). This eliminates most of the effort of writing a DiffSync adapter for the Nautobot side of a custom SSoT integration.

As long as your `DiffSync` models use `nautobot_ssot.contrib.model.NautobotModel`, you do not have to write a `load` method. The adapter infers how to read each model and its relationships from the Nautobot ORM. Writing changes back to Nautobot is handled by the models themselves; see [Models](./models.md#create-update-and-delete).

## Creating a Nautobot adapter

Subclass `NautobotAdapter`, attach each of your models as a class attribute, and declare which models are loaded at the top level:

```python
from nautobot_ssot.contrib import NautobotAdapter

from your_ssot_app.models import DiffSyncDevice, DiffSyncInterface, DiffSyncPrefix


class YourNautobotAdapter(NautobotAdapter):
    """DiffSync adapter for loading data from Nautobot."""

    top_level = ("device", "prefix")

    device = DiffSyncDevice
    prefix = DiffSyncPrefix
    interface = DiffSyncInterface  # Not in `top_level` — it is a child of the device model
```

Two things are required:

- **Model attributes** — assign each DiffSync model class to a class attribute. The attribute name must match the model's `_modelname`, because the adapter looks the class up by that name when it needs to load it.
- **`top_level`** — a tuple of the model names that should be loaded directly. Child models (those reachable through a parent's `_children`) are *not* listed here; the adapter discovers and loads them recursively while processing their parent.

!!! note
    The order of `top_level` matters.

    DiffSync applies changes in the order of the *destination* adapter's `top_level`, which is this adapter when syncing into Nautobot. List each model after any model it depends on. For example, location types must come before locations, or creating a location will fail because its location type does not exist yet.

    DiffSync only compares models that appear in the `top_level` of **both** adapters. A model listed in only one of them is silently skipped.

    Deletions follow the same order; they are **not** reversed. If deleting parents before their dependents is a problem for your data (for example, a `ProtectedError` from a referenced object), override `delete` on the affected models to handle it.

## How loading works

When `load()` is called, the adapter walks each model in `top_level` and, for every Nautobot object returned by that model's queryset, builds a DiffSync model instance by reading each of its synced parameters (its `_identifiers` plus `_attributes`). It handles the different field types automatically:

- **Normal fields** are read directly off the ORM object.
- **Foreign keys** (fields using Django's `__` lookup syntax) are traversed to pull the related value.
- **Custom fields** and **custom relationships** (declared with `CustomFieldAnnotation` / `CustomRelationshipAnnotation`) are resolved from the appropriate Nautobot machinery.
- **Object metadata** fields (declared with `ObjectMetadataAnnotation`) are read from the object's associated metadata. See [ObjectMetadata-Backed Fields](../../dev/contrib_object_metadata.md).
- **To-many relationships** are loaded as lists of typed dictionaries.

After loading an object, the adapter recurses into its children, so a single `load()` call populates the entire tree described by your models. How each field type is declared on the model is covered in detail in the [modeling guide](../modeling.md).

!!! note
    The adapter uses an internal `ORMCache` to avoid repeatedly querying the database for the same related objects during a sync. You generally do not need to interact with it directly.

## Overriding how a parameter is loaded

For most fields the default behavior is correct, but occasionally you need to control how a single basic parameter is read from Nautobot — for example, coercing a value to a string. Define a method named `load_param_<parameter_name>` on your adapter:

```python
from nautobot_ssot.contrib import NautobotAdapter


class YourNautobotAdapter(NautobotAdapter):
    ...

    def load_param_time_zone(self, parameter_name, database_object):
        """Load `time_zone` as a string rather than a `ZoneInfo` object."""
        return str(getattr(database_object, parameter_name))
```

!!! warning
    This override only applies to *basic* parameters. It does not affect foreign keys, custom fields, custom relationships, object metadata fields, or to-many relationships — those are always handled by the adapter's built-in logic.

## Using the adapter in a Job

The Nautobot adapter is instantiated with the running Job and then loaded. When syncing *into* Nautobot (a `DataSource` Job), this happens in `load_target_adapter`:

```python
def load_target_adapter(self):
    self.target_adapter = YourNautobotAdapter(job=self)
    self.target_adapter.load()
```

When syncing *from* Nautobot (a `DataTarget` Job), do the same in `load_source_adapter` and assign the result to `self.source_adapter`.

For the full picture — including the remote adapter and the `DataSource`/`DataTarget` Job that drives the sync — see [Developing Data Source and Data Target Jobs](../../dev/jobs.md).
