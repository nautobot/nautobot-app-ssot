# Modeling

This page describes how to model various kinds of fields on a `nautobot_ssot.contrib.NautobotModel` subclass.

## Quick Reference

The following table describes in brief the different types of model fields and how they are handled.

| Type of field                                      | Field name                | Notes                                                                                                                                            | Applies to                                                                                                                                                                                                              |
| -------------------------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Normal fields](#normal-fields)                    | Has to match ORM exactly  | Make sure that the name matches the name in the ORM model.                                                                                       | Fields that are neither custom fields nor relations                                                                                                                                                                     |
| [Custom fields](#custom-fields)                    | Field name doesn't matter | Use `nautobot_ssot.contrib.CustomFieldAnnotation`                                                                                                | [Nautobot custom fields](https://docs.nautobot.com/projects/core/en/stable/user-guides/custom-fields/?h=custom+fields)                                                                                                  |
| [*-to-one relationships](#-to-one-relationships)   | Django lookup syntax      | See [here](https://docs.djangoproject.com/en/3.2/topics/db/queries/#lookups-that-span-relationships) - your model fields need to use this syntax | `django.db.models.OneToOneField`, `django.db.models.ForeignKey`, `django.contrib.contenttypes.fields.GenericForeignKey`                                                                                                 |
| [*-to-many relationships](#-to-many-relationships) | Has to match ORM exactly  | In case of a generic foreign key see [here](#special-case-generic-foreign-key)                                                                   | `django.db.models.ManyToManyField`, `django.contrib.contenttypes.fields.GenericRelation`, `django.db.models.ForeignKey` [backwards](https://docs.djangoproject.com/en/3.2/topics/db/queries/#backwards-related-objects) |
| Custom Relationships                               | n/a                       | Not yet supported                                                                                                                                | https://docs.nautobot.com/projects/core/en/stable/models/extras/relationship/                                                                                                                                           |


## Normal Fields

For normal, non-relationship, non-custom fields on a model, all you need to do is to ensure that field name on your SSoT model class matches that of the Nautobot model class. To ensure this is the case, you can check out the model either by reading the corresponding source code on [GitHub](https://github.com/nautobot/nautobot) or through the [Nautobot Shell](https://docs.nautobot.com/projects/core/en/stable/administration/nautobot-shell/) - in there you can use commands like `dir(Tenant)` to get an overview of available fields for the different models.

!!! note
    If you want to sync data into a model provided by a [Nautobot App](https://docs.nautobot.com/projects/core/en/stable/plugins/), you need to navigate to its respective source code repository. Furthermore, you may need to manually import the model if you're using the Nautobot Shell approach.

## Custom Fields

For [custom fields](https://docs.nautobot.com/projects/core/en/stable/models/extras/customfield/), you will need to use the `nautobot_ssot.contrib.CustomFieldAnnotation` class. Given a custom field called "Test Custom Field" on the circuit provider model, this is how you could map that custom field into the diffsync model field `test_custom_field`:

```python
try:
    from typing import Annotated  # Python>=3.9
except ModuleNotFoundError:
    from typing_extensions import Annotated  # Python<3.9
from nautobot.circuits.models import Provider
from nautobot_ssot.contrib import NautobotModel, CustomFieldAnnotation

class ProviderModel(NautobotModel):
    _model = Provider
    _modelname = "provider"
    _identifiers = ("name",)
    _attributes = ("test_custom_field",)

    name: str
    test_custom_field: Annotated[str, CustomFieldAnnotation(name="Test Custom Field")]
```

!!! note
    Defining a `CustomFieldAnnotation` variable is necessary since custom field names may include spaces, which are un-representable in Python object field names.

## *-to-one Relationships

For many-to-one relationships (i.e. [foreign keys](https://docs.djangoproject.com/en/3.2/topics/db/examples/many_to_one/) or [generic foreign keys](https://docs.djangoproject.com/en/3.2/ref/contrib/contenttypes/#generic-relations)) a slightly different approach is employed. We need to add a field on our model for each field that we need in order to uniquely identify our related object behind the many-to-one relationship. We can do this using a [familiar syntax](https://docs.djangoproject.com/en/3.2/topics/db/queries/#lookups-that-span-relationships) of double underscore separated paths. Assuming we want to synchronize prefixes and associate them with locations, we may be faced with the problems that locations aren't uniquely identified by name alone, but rather need the location type as well, we can address this as follows.

```python
from nautobot.ipam.models import Prefix
from nautobot_ssot.contrib import NautobotModel

class PrefixModel(NautobotModel):
    _model = Prefix
    _identifiers = ("network", "prefix_length")
    _attributes = ("vlan__vid", "vlan__group__name")

    network: str
    prefix_length: int

    vlan__vid: int
    vlan__group__name: str
```

Now, on model `create` or `update`, the SSoT framework will dynamically pull in the location with the specified name and location type name, uniquely identifying the location and populating the foreign key. In this case, the corresponding query will look something like this:

```python
from nautobot.dcim.models import Location
prefix = PrefixModel(network="192.0.2.0", prefix_length=26, vlan__vid=1000, vlan__group__name="Datacenter")

# A query similar to the following line will be used to automatically populate the foreign key field upon `prefix.create`
VLAN.objects.get(vid=prefix.vlan__vid, group__name=prefix.vlan__group__name)
```

### Special Case: Generic Foreign Key

In the case of a [generic foreign key](https://docs.djangoproject.com/en/3.2/topics/db/examples/many_to_many/), we are faced with a problem. With normal foreign keys the [content type](https://docs.djangoproject.com/en/3.2/ref/contrib/contenttypes/) of a relationship field can be inferred from the model class. In the case of *generic* foreign keys however, this is not the case. In the example of the [IP address](https://docs.nautobot.com/projects/core/en/stable/models/ipam/ipaddress/?h=ip+address) model in Nautobot, the `assigned_object` field can point to either a device's or a VM's interface. We address this the following way:

```python
from nautobot.ipam.models import IPAddress
from nautobot_ssot.contrib import NautobotModel

class NautobotIPAddress(NautobotModel):
    _model = IPAddress
    _modelname = "ip_address"
    _identifiers = (
        "host",
        "prefix_length",
    )
    _attributes = (
        "status__name",
        "assigned_object__app_label",
        "assigned_object__model",
        "assigned_object__device__name",
        "assigned_object__name",
    )

    host: str
    prefix_length: int
    status__name: str
    assigned_object__app_label: str
    assigned_object__model: str
    assigned_object__device__name: str
    assigned_object__name: str
```

!!! warning
    A limitation of this approach is that we are locked into a single kind of content type per model and foreign key, unless the field names for all content types match. In this specific case, the VM interface model does not have a `device` field which will cause the `create` and `update` method of `NautobotIPAddress` to raise a `ValueError`. This is a known issue.

## *-to-many Relationships

For "*-to-many" relationships such as (generic) foreign keys traversed backwards or [many-to-many relationships](https://docs.djangoproject.com/en/3.2/topics/db/examples/many_to_many/), we need to employ a different mechanism. Again we start by identifying which fields of the related object we are interested in for queries **to** the model. In this case, our example will be using an `Interface` model for which we also want to sync the associated IP addresses. For our scenario, lets assume that our IP addresses can be uniquely identified through the `host` and `prefix_length` fields:

```python
try:
    from typing import TypedDict  # Python>=3.9
except ImportError:
    from typing_extensions import TypedDict  # Python<3.9

class IPAddressDict(TypedDict):
    """This typed dict is 100% decoupled from the `NautobotIPAddress` class defined above."""
    host: str
    prefix_length: int
```

Having defined this, we can now define our diffsync model:

```python
from typing import List  # use the builtin 'list' from Python 3.9 on
from nautobot.dcim.models import Interface
from nautobot_ssot.contrib import NautobotModel

class NautobotInterface(NautobotModel):
    _model = Interface
    _modelname = "interface"
    _identifiers = (
        "name",
        "device__name",
    )
    _attributes = ("ip_addresses",)

    name: str
    device__name: str
    ip_addresses: List[IPAddressDict] = []
```

!!! note
    In this example we can also see a case where a foreign key (named `device`, through `device__name`) constitutes part of the `_identfiers` field - this is a common pattern as model relationships define their uniqueness across multiple models in Nautobot.

Through us defining the model, Nautobot will now be able to dynamically load IP addresses related to our interfaces from Nautobot, and also set the related objects on the relationship in the `create` and `update` methods. 

!!! note
    Although `Interface.ip_addresses` is a generic relation, there is only one content type (i.e. `ipam.ipaddress`) that may be related through this relation, therefore we don't have to specific this in any way.


## Filtering Objects Loaded From Nautobot


If you'd like to filter the objects loaded from the Nautobot, you can do so creating a `get_queryset` function in your model class and return your own queryset. Here is an example where the adapter would only load Tenant objects whose name starts with an "s".

```python
from nautobot.tenancy.models import Tenant
from nautobot_ssot.contrib import NautobotModel

class TenantModel(NautobotModel):
    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("description",)

    name: str
    description: str

    @classmethod
    def get_queryset(cls):
        return Tenant.objects.filter(name__startswith="s")
```