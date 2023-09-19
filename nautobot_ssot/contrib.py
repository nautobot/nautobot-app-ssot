"""This module includes a base adapter and a base model class for interfacing with Nautobot."""
# pylint: disable=protected-access
# Diffsync relies on underscore-prefixed attributes quite heavily, which is why we disable this here.

from collections import defaultdict
from dataclasses import dataclass

import pydantic
from diffsync import DiffSyncModel, DiffSync
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError, MultipleObjectsReturned
from django.db.models import Model
from typing_extensions import get_type_hints


@dataclass
class CustomFieldAnnotation:
    """Map a model field to an arbitrary custom field name.

    For usage with `typing.Annotated`.

    This exists to map model fields to their corresponding custom fields. This solves the problem of Python object
    attributes not being able to include spaces, while custom field names/labels may.

    TODO: With Nautobot 2.0, the custom fields `key` field needs to be a valid Python identifier. This will probably
      simplify this a lot.

    Example:
        Given a boolean custom field "Is Global" on the Provider model:

        ```python
        class ProviderModel(NautobotModel):
            _model: Provider
            _identifiers = ("name",)
            _attributes = ("is_global",)

            name: str
            is_global: Annotated[bool, CustomFieldAnnotation(name="Is Global")
        ```

        This then maps the model field 'is_global' to the custom field 'Is Global'.
    """

    name: str


class NautobotAdapter(DiffSync):
    """
    Adapter for loading data from Nautobot through the ORM.

    This adapter is able to infer how to load data from Nautobot based on how the models attached to it are defined.
    """

    @staticmethod
    def _get_parameter_names(diffsync_model):
        """Ignore the differences between identifiers and attributes, because at this point they don't matter to us."""
        return list(diffsync_model._identifiers) + list(diffsync_model._attributes)  # pylint: disable=protected-access

    def _load_objects(self, diffsync_model):
        """Given a diffsync model class, load a list of models from the database and return them."""
        parameter_names = self._get_parameter_names(diffsync_model)

        # Here we identify any foreign keys (i.e. fields with '__' in them) so that we can load them directly in the
        # first query.
        prefetch_related_parameters = [parameter.split("__")[0] for parameter in parameter_names if "__" in parameter]

        # TODO: Allow for filtering, i.e. not getting all models from a table but just some.
        for database_object in diffsync_model._model.objects.prefetch_related(*prefetch_related_parameters).all():
            self._load_single_object(database_object, diffsync_model, parameter_names)

    def _load_single_object(self, database_object, diffsync_model, parameter_names):
        """Load a single diffsync object from a single database object."""
        parameters = {}
        type_hints = get_type_hints(diffsync_model, include_extras=True)
        for parameter_name in parameter_names:
            # Handling of foreign keys where the local side is the many and the remote side the one.
            # Note: This includes the side of a generic foreign key that has the foreign key, i.e.
            # the 'many' side.
            if "__" in parameter_name:
                parameters[parameter_name] = self._handle_foreign_key(database_object, parameter_name)
                continue

            # Handle custom fields. See CustomFieldAnnotation docstring for more details.
            is_custom_field = False
            metadata_for_this_field = getattr(type_hints[parameter_name], "__metadata__", [])
            for metadata in metadata_for_this_field:
                if isinstance(metadata, CustomFieldAnnotation):
                    parameters[parameter_name] = database_object.cf[metadata.name]
                    is_custom_field = True
                    break
            if is_custom_field:
                continue

            database_field = diffsync_model._model._meta.get_field(parameter_name)

            # Handling of one- and many-to-many fields.
            # Note: This includes the side of a generic foreign key that constitues the foreign key,
            # i.e. the 'one' side.
            if database_field.many_to_many or database_field.one_to_many:
                parameters[parameter_name] = self._handle_to_many_relationship(
                    database_object, diffsync_model, parameter_name
                )
                continue

            # Handling of normal fields - as this is the default case, set the attribute directly.
            parameters[parameter_name] = getattr(database_object, parameter_name)
        try:
            diffsync_model = diffsync_model(**parameters)
        except pydantic.ValidationError as error:
            raise ValueError(f"Parameters: {parameters}") from error
        self.add(diffsync_model)

        self._handle_children(database_object, diffsync_model)
        return diffsync_model

    def _handle_children(self, database_object, diffsync_model):
        """Recurse through all the children for this model."""
        for children_parameter, children_field in diffsync_model._children.items():
            children = getattr(database_object, children_field).all()
            diffsync_model_child = self._get_diffsync_class(model_name=children_parameter)
            for child in children:
                parameter_names = self._get_parameter_names(diffsync_model_child)
                child_diffsync_object = self._load_single_object(child, diffsync_model_child, parameter_names)
                diffsync_model.add_child(child_diffsync_object)

    def load(self):
        """Generic implementation of the load function."""
        if not hasattr(self, "top_level") or not self.top_level:
            raise ValueError("'top_level' needs to be set on the class.")

        for model_name in self.top_level:
            diffsync_model = self._get_diffsync_class(model_name)

            # This function directly mutates the diffsync store, i.e. it will create and load the objects
            # for this specific model class as well as its children without returning anything.
            self._load_objects(diffsync_model)

    def _get_diffsync_class(self, model_name):
        """Given a model name, return the diffsync class."""
        try:
            diffsync_model = getattr(self, model_name)
        except AttributeError as error:
            raise AttributeError(
                f"Please define {model_name} to be the diffsync model on this adapter as a class level attribute."
            ) from error
        return diffsync_model

    @staticmethod
    def _handle_to_many_relationship(database_object, diffsync_model, parameter_name):
        """Handle a single one- or many-to-many relationship field.

        one- or many-to-many relationships are type annotated as a list of typed dictionaries. The typed
        dictionary type expresses, which attributes we are interested in for diffsync.

        :param database_object: The Django ORM database object
        :param diffsync_model: The diffsync model class (not specific object) for this ORM object
        :param parameter_name: The field name of the specific relationship to handle
        :return: A list of dictionaries which represent the related objects.

        :example:

        Example parameters:
        - a `nautobot.dcim.models.Interface` instance with two IP addresses assigned
          through the `ip_addresses` many-to-many relationship as `database_object`
        - an InterfaceModel class like the following `NautobotInterface` as `diffsync_model`

        ```python
        class IPAddressDict(TypedDict):
            host: str
            prefix_length: int


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

        - a field name like `ip_addresses` as the `parameter_name`

        Example return list within the above input example:

        ```python
        [
          {"host": "192.0.2.0/25", "prefix_length": 25},
          {"host": "192.0.2.128/25", "prefix_length": 25},
        ]
        ```
        """
        # Introspect type annotations to deduce which fields are of interest
        # for this many-to-many relationship.
        diffsync_field_type = diffsync_model.__annotations__[parameter_name]
        inner_type = diffsync_field_type.__dict__["__args__"][0]
        related_objects_list = []
        # TODO: Allow for filtering, i.e. not taking into account all the objects behind the relationship.
        for related_object in getattr(database_object, parameter_name).all():
            dictionary_representation = {
                field_name: getattr(related_object, field_name) for field_name in inner_type.__annotations__
            }
            # Only use those where there is a single field defined, all 'None's will not help us.
            if any(dictionary_representation.values()):
                related_objects_list.append(dictionary_representation)
        return related_objects_list

    @staticmethod
    def _handle_foreign_key(database_object, parameter_name):
        """Handle a single foreign key field.

        Given the object from the database as well as the name of parameter in the form of
        f'{foreign_key_field_name}__{remote_field_name}'
        return the field at 'remote_field_name' on the object behind the foreign key at 'foreign_key_field_name'.

        Furthermore, 'remote_field_name' may be a series of '__' delimited lookups.

        :param database_object: The Django ORM database object
        :param parameter_name: The field name of the specific relationship to handle
        :return: If present, the object behind the (generic) foreign key, else None
        """
        related_model, *lookups = parameter_name.split("__")
        related_object = getattr(database_object, related_model)
        # If the foreign key does not point to anything, return None
        if not related_object:
            return None
        for lookup in lookups[:-1]:
            related_object = getattr(related_object, lookup)
            # If the foreign key does not point to anything, return None
            if not related_object:
                return None
        # Return the result of the last lookup directly.
        try:
            return getattr(related_object, lookups[-1])
        # If the lookup doesn't point anywhere, check whether it is using the convention for generic foreign keys.
        except AttributeError:
            if lookups[-1] in ["app_label", "model"]:
                return getattr(ContentType.objects.get_for_model(related_object), lookups[-1])
        return None


class NautobotModel(DiffSyncModel):
    """
    Base model for any diffsync models interfacing with Nautobot through the ORM.

    This provides the `create`, `update` and `delete` operations in a generic fashion, meaning you don't have to
    implement them yourself.

    In order to accomplish this, the `_model` field has to be set on subclasses to map them to the corresponding ORM
    model class.
    """

    _model: Model

    @classmethod
    def _check_field(cls, name):
        """Check whether the given field name is defined on the diffsync (pydantic) model."""
        if name not in cls.__fields__:
            raise ValueError(f"Field {name} is not defined on the model.")

    def get_from_db(self):
        """Get the ORM object for this diffsync object from the database using the identifiers."""
        return self._model.objects.get(**self.get_identifiers())

    def update(self, attrs):
        """Update the ORM object corresponding to this diffsync object."""
        obj = self.get_from_db()
        self._update_obj_with_parameters(obj, attrs)

    def delete(self):
        """Delete the ORM object corresponding to this diffsync object."""
        self.get_from_db().delete()

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create the ORM object corresponding to this diffsync object."""
        # Only diffsync cares about the distinction between ids and attrs, we do not.
        # Therefore, we merge the two into parameters.
        parameters = ids.copy()
        parameters.update(attrs)

        # This is in fact callable, because it is a model
        obj = cls._model()  # pylint: disable=not-callable

        cls._update_obj_with_parameters(obj, parameters)

        return super().create(diffsync, ids, attrs)

    @classmethod
    def _update_obj_with_parameters(cls, obj, parameters):
        """Update a given Nautobot ORM object with the given parameters."""
        # Example: {"group": {"name": "Group Name", "_model_class": TenantGroup}}
        foreign_keys = defaultdict(dict)

        # Example: {"tags": [Tag-1, Tag-2]}
        many_to_many_fields = defaultdict(list)

        # Use type hints at runtime to determine which fields are custom fields
        type_hints = get_type_hints(cls, include_extras=True)

        for field, value in parameters.items():
            cls._check_field(field)

            # Prepare handling of foreign keys.
            # Example: If field is `tenant__group__name`, then
            # `foreign_keys["tenant"]["group__name"] = value`
            # Also, the model class will be added to the dictionary, so we can later use it
            # for querying:
            # `foreign_keys["tenant"]["_model_class"] = nautobot.tenancy.models.Tenant
            if "__" in field:
                related_model, lookup = field.split("__", maxsplit=1)
                django_field = cls._model._meta.get_field(related_model)
                foreign_keys[related_model][lookup] = value
                # Add a special key to the dictionary to point to the related model's class
                foreign_keys[related_model]["_model_class"] = django_field.related_model
                continue

            # Handle custom fields. See CustomFieldAnnotation docstring for more details.
            is_custom_field = False
            metadata_for_this_field = getattr(type_hints[field], "__metadata__", [])
            for metadata in metadata_for_this_field:
                if isinstance(metadata, CustomFieldAnnotation):
                    obj.cf[metadata.name] = value
                    is_custom_field = True
                    continue
            if is_custom_field:
                continue

            django_field = cls._model._meta.get_field(field)

            # Prepare handling of many-to-many fields. If we are dealing with a many-to-many field,
            # we get all the related objects here to later set them once the object has been saved.
            if django_field.many_to_many or django_field.one_to_many:
                many_to_many_fields[field] = [
                    django_field.related_model.objects.get(**parameters) for parameters in value
                ]
                continue

            # As the default case, just set the attribute directly
            setattr(obj, field, value)

        # Set foreign keys
        cls._lookup_and_set_foreign_keys(foreign_keys, obj)

        # Save the object to the database
        try:
            obj.validated_save()
        except ValidationError as error:
            raise ValidationError(f"Parameters: {parameters}") from error

        # Set many-to-many fields after saving
        cls._set_many_to_many_fields(many_to_many_fields, obj)

    @classmethod
    def _set_many_to_many_fields(cls, many_to_many_fields, obj):
        """
        Given a dictionary, set many-to-many relationships on an object.

        This will always use `set`, thereby replacing any elements that are already part of the relationship.

        Example dictionary:
        {
            "relationship_field_name": [<Object 1>, <Object 2>],
            ...
        }
        """
        for field_name, related_objects in many_to_many_fields.items():
            many_to_many_field = getattr(obj, field_name)
            many_to_many_field.set(related_objects)

    @classmethod
    def _lookup_and_set_foreign_keys(cls, foreign_keys, obj):
        """
        Given a list of foreign keys as dictionaries, look up and set foreign keys on an object.

        Dictionary should be in the form of:
        [
          {"field_1": "value_1", "field_2": "value_2"},
          ...
        ]
        where each item in the list corresponds to the parameters needed to uniquely identify a foreign key object.
        """
        for field_name, related_model_dict in foreign_keys.items():
            related_model = related_model_dict.pop("_model_class")
            # Generic foreign keys will not have this dictionary field. As such, we need to retrieve the appropriate
            # model class through other means.
            if not related_model:
                try:
                    app_label = related_model_dict.pop("app_label")
                    model = related_model_dict.pop("model")
                except KeyError as error:
                    raise ValueError(
                        f"Missing annotation for '{field_name}__app_label' or '{field_name}__model - this is required"
                        f"for generic foreign keys."
                    ) from error
                related_model = ContentType.objects.get(app_label=app_label, model=model).model_class()
            # Set the foreign key to 'None' when none of the fields are set to anything
            if not any(related_model_dict.values()):
                setattr(obj, field_name, None)
                continue
            try:
                related_object = related_model.objects.get(**related_model_dict)
            except related_model.DoesNotExist as error:
                raise ValueError(f"Couldn't find {field_name} instance with: {related_model_dict}.") from error
            except MultipleObjectsReturned as error:
                raise ValueError(f"Found multiple instances for {field_name} wit: {related_model_dict}") from error
            setattr(obj, field_name, related_object)
