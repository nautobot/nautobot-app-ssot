"""Mixins to be used when working with Nautobot."""

from typing import Optional
from diffsync.enum import DiffSyncFlags, DiffSyncModelFlags


def get_fk(fks, diffsync, key, value):
    """Function to get the fk of an object, given information stored in ORM."""
    # fks comes from self._foreign_keys
    # key matches a key in `_foreign_keys` which is the local attribute
    # value is the get_unique_id() we are looking for
    if key in list(fks.keys()):
        model = [val for _key, val in fks.items() if _key == key][0]
        key_model = diffsync.meta[model]
        pkey = diffsync.get(model, value).pk
    return key_model.objects.get(pk=pkey)


class DiffSyncModelMixIn:
    """MixIn class to handle sync generically."""

    _foreign_key = {}
    _many_to_many = {}
    _generic_relation = {}
    _unique_fields = ("pk",)
    _skip = []

    pk: Optional[str]

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Method to handle generically."""
        model = super().create(ids=ids, diffsync=diffsync, attrs=attrs)
        # model is the DiffSyncModel instance, which has data about the instance required
        db_model = cls.Meta.model
        obj = db_model()
        instance_values = {**ids, **attrs}
        combined = (
            list(model._foreign_key.keys()) + list(model._many_to_many.keys()) + list(model._generic_relation.keys())
        )
        for key, value in instance_values.items():
            if hasattr(model, "_skip") and key in model._skip:
                continue
            if key not in combined:
                setattr(obj, key, value)
            else:
                if not value:  # need to find the value of the other object, if none exists, that won't work
                    continue
                if key in list(model._generic_relation.keys()):
                    with_parent = {
                        key: model._generic_relation[key]["parent"] for key in list(model._generic_relation.keys())
                    }
                    with_values = "__".join(
                        [instance_values[key] for key in list(model._generic_relation[key]["identifiers"])]
                    )
                    db_obj = get_fk(with_parent, diffsync, key, with_values)
                    setattr(obj, model._generic_relation[key]["attr"], db_obj)
                if key in list(model._foreign_key.keys()):
                    db_obj = get_fk(model._foreign_key, diffsync, key, value)
                    setattr(obj, key, db_obj)
                if key in list(model._many_to_many.keys()):
                    if isinstance(value, list):
                        for val in value:
                            db_obj = get_fk(model._many_to_many, diffsync, key, val)
                            getattr(obj, key).add(db_obj)
                    else:
                        db_obj = get_fk(model._many_to_many, diffsync, key, value)
                        obj.set(db_obj)

        obj.validated_save()
        if not model.pk:
            setattr(model, "pk", obj.pk)
        return model

    def update(self, attrs):  # pylint: disable=too-many-branches
        """Create Method to handle generically."""
        db_model = self.Meta.model
        diffsync = self.diffsync
        combined = list(self._foreign_key.keys()) + list(self._many_to_many.keys())
        instance_values = {**attrs}
        _vars = self.get_identifiers()
        for key, val in _vars.items():
            if key in list(self._foreign_key.keys()):
                db_obj = get_fk(self._foreign_key, diffsync, key, val)
                _vars[key] = str(db_obj.pk)
            if key in list(self._many_to_many.keys()):
                db_obj = get_fk(self._many_to_many, diffsync, key, val)
                _vars[key] = str(db_obj.pk)

        obj = db_model.objects.get(**_vars)

        for key, value in instance_values.items():
            if hasattr(self, "_skip") and key in self._skip:
                continue
            if key not in combined:
                setattr(obj, key, value)
            else:
                if not value:  # need to find the value of the other object, if none exists, that won't work
                    continue
                if key in list(self._generic_relation.keys()):
                    with_parent = {
                        key: self._generic_relation[key]["parent"] for key in list(self._generic_relation.keys())
                    }
                    with_values = "__".join(
                        [instance_values[key] for key in list(self._generic_relation[key]["identifiers"])]
                    )
                    db_obj = get_fk(with_parent, diffsync, key, with_values)
                    setattr(obj, self._generic_relation[key]["attr"], db_obj)
                if key in list(self._foreign_key.keys()):
                    db_obj = get_fk(self._foreign_key, diffsync, key, value)
                    setattr(obj, key, db_obj)
                if key in list(self._many_to_many.keys()):
                    if isinstance(value, list):
                        for val in value:
                            db_obj = get_fk(self._many_to_many, diffsync, key, val)
                            getattr(obj, key).add(db_obj)
                    else:
                        db_obj = get_fk(self._many_to_many, diffsync, key, value)
                        obj.set(db_obj)
        obj.save()
        return super().update(attrs)

    def delete(self):
        """Create Method to handle generically."""
        db_model = self.Meta.model
        obj = db_model.objects.get(pk=self.pk)
        obj.delete()

        super().delete()
        return self


class DiffSyncMixIn:
    """Mixin to update add to allow for 'stuffing' data based on unique fields."""

    _unique_data = {}

    def add(self, obj, *args, **kwargs):
        """Override add method to stuff data into dictionary based on the `_unique_fields`."""
        super().add(obj, *args, **kwargs)
        modelname = obj._modelname

        for attr in getattr(obj, "_unique_fields", []):
            if hasattr(obj, attr):
                if not self._unique_data.get(modelname):
                    self._unique_data[modelname] = {}
                if not self._unique_data[modelname].get(attr):
                    self._unique_data[modelname][attr] = {}
                self._unique_data[modelname][attr][getattr(obj, attr)] = obj


class AdapterMixIn:
    def apply_diffsync_flags(self):
        """Helper function for DiffSync Flag assignment."""
        if not self.diffsync_flags:
            return
        for item in self.diffsync_flags:
            if not hasattr(DiffSyncFlags, item):
                raise ValueError(f"There was an attempt to add a non-existing flag of `{item}`")
            self.global_flags |= getattr(DiffSyncFlags, item)

    def apply_model_flags(self, obj, tags):
        """Helper function for DiffSync Flag assignment on model instances."""
        if not self.diffsync_model_flags:
            return
        for item in tags:
            if not hasattr(DiffSyncModelFlags, item):
                continue
            obj.model_flags |= getattr(DiffSyncModelFlags, item)
        if not self.diffsync_model_flags.get(obj._modelname):
            return
        for item in self.diffsync_model_flags[obj._modelname]:
            if not hasattr(DiffSyncModelFlags, item):
                raise ValueError(f"There was an attempt to add a non-existing flag of `{item}`")
            obj.model_flags |= getattr(DiffSyncModelFlags, item)
