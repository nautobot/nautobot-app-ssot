# Overview

The SSoT plugin comes with several MixIns that can be used to integrate when syncing with Nautobot. There are three MixIns that are currently supported.

## DiffSyncModelMixIn

As the class name indicates, this is intended to be used to extend a `DiffSyncModel` based class. There are 5 private attributes (private to avoid namespace and Pydantic overwrite) that are used to control how the CRUD operations works. The defintion of the attributes is:

```python
class DiffSyncModelMixIn:

    _foreign_key = {}
    _many_to_many = {}
    _generic_relation = {}
    _unique_fields = ("pk",)
    _skip = ()
```

For the CRUD operations to work, the attributes names must match what the model attribute names are. The design calls for the `DiffSyncModel` to name the attribute exactly as the Django model attribute name and the Adapter to handle all logic to get the data into that format. In general, the model on the other instance should look exactly the same, except for the `pk` and any other metadata, that may be required, such as to use for ordering.

The methods for `create`, `update`, and `delete` are created and currently work for all known use cases. The basic premise is to follow simple patterns and based on the private attributes assign the data. Consider the following conditions.

* By default, set the attribute to the name of the attribute value on the current model
* `_foreign_key` is a dictionary, in the format of the current attribute name on the model as the key, and the name of the model on. Based on that information you can find the `pk` value of the foreign key. 
    * e.g. `_foreign_key = {"device": "device", "untagged_vlan": "vlan"}` where `device` and `untagged_vlan` is an attribute on the current model.
* `_many_to_many` is a in the same format. Based on the same information you can add to the other model instance to the, the current object.
    * e.g. `_many_to_many = {"tagged_vlans": "vlan"}` where `tagged_vlans` is an attribute on the current model.
* `_generic_relation` is in the format of the key is the current model attribute and value of a dictionary. The dictionary needs to include 3 keys, `parent` to identify the model of the parent, `identifiers` is a list of the identifiers, and `attr` is the attribute to be set to.
    * e.g. `_generic_relation = {"interface": {"parent": "interface", "identifiers": ["device", "interface"], "attr": "assigned_object"}}`


## DiffSyncMixIn

The `DiffSyncMixIn` provides two features:

* Creates the `_unique_data` attribute to be able to stuff data into
* Super class's add method, to automatically update `_unique_data` as needed.

## AdapterMixIn

The `AdapterMixIn` provides two features:

* apply_model_flags - Provides a convenience method to apply model flags.
* *apply_diffsync_flags - Provides a convenience method to apply model flags based on tags on the nautobot model.