"""Base adapter module for interfacing with Nautobot in SSoT."""

# pylint: disable=protected-access
# Diffsync relies on underscore-prefixed attributes quite heavily, which is why we disable this here.

from collections import defaultdict
from typing import DefaultDict, Dict, FrozenSet, Hashable, Tuple, Type, get_args

import pydantic
from diffsync import Adapter
from diffsync.exceptions import ObjectCrudException
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras.models import Relationship, RelationshipAssociation
from nautobot_ssot.contrib.model import NautobotModel
from typing_extensions import get_type_hints

from nautobot_ssot.contrib.types import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    RelationshipSideEnum,
)

# This type describes a set of parameters to use as a dictionary key for the cache. As such, its needs to be hashable
# and therefore a frozenset rather than a normal set or a list.
#
# The following is an example of a parameter set that describes a tenant based on its name and group:
# frozenset(
#  [
#   ("name", "ABC Inc."),
#   ("group__name", "Customers"),
#  ]
# )
ParameterSet = FrozenSet[Tuple[str, Hashable]]


class InvalidResponseWarning(BaseException):
    """Custom warning for use in `NautobotAdapter` class indicating an invalid response."""


class ParameterType:
    """Parameter type values for use in `NautobotAdapter` class and dynamic method calling."""

    STANDARD = "standard"
    FOREIGN_KEY = "foreign_key"
    MANY_RELATIONSHIP = "many_relationship"
    CUSTOM_FIELD = "custom_field"
    CUSTOM_FOREIGN_KEY = "custom_foreign_key"
    CUSTOM_MANY_RELATIONSHIP = "custom_many_relationship"


class BaseAdapter(Adapter):
    """Mixin for common functionality in Diffsync adapters."""
    
    def __init__(self, *args, job, sync=None, **kwargs):
        """Initialize common features for Diffsync adapters."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync

    def get_diffsync_class(self, model_name):
        """Given a model name, return the diffsync class."""
        try:
            diffsync_class = getattr(self, model_name)
        except AttributeError as error:
            raise AttributeError(f"Adapter class `{self}` missing `{model_name}` attribute.") from error
        if not issubclass(diffsync_class, NautobotModel):
            raise TypeError(f"Class `{diffsync_class.__class__}` is not a subclasses of `DiffsyncModel`.")
        return diffsync_class
        

class NautobotAdapter(BaseAdapter):
    """
    Adapter for loading data from Nautobot through the ORM.

    This adapter is able to infer how to load data from Nautobot based on how the models attached to it are defined.
    """

    # This dictionary acts as an ORM cache.
    _cache: DefaultDict[str, Dict[ParameterSet, Model]]
    _cache_hits: DefaultDict[str, int] = defaultdict(int)

    def __init__(self, *args, **kwargs):
        """Instantiate this class, but do not load data immediately from the local system."""
        super().__init__(*args, **kwargs)
        self.invalidate_cache()

    def invalidate_cache(self, zero_out_hits=True):
        """Invalidates all the objects in the ORM cache."""
        self._cache = defaultdict(dict)
        if zero_out_hits:
            self._cache_hits = defaultdict(int)

    def get_from_orm_cache(self, parameters: Dict, model_class: Type[Model]):
        """Retrieve an object from the ORM or the cache."""
        parameter_set = frozenset(parameters.items())
        content_type = ContentType.objects.get_for_model(model_class)
        model_cache_key = f"{content_type.app_label}.{content_type.model}"
        if cached_object := self._cache[model_cache_key].get(parameter_set):
            self._cache_hits[model_cache_key] += 1
            return cached_object
        # As we are using `get` here, this will error if there is not exactly one object that corresponds to the
        # parameter set. We intentionally pass these errors through.
        self._cache[model_cache_key][parameter_set] = model_class.objects.get(**dict(parameter_set))
        return self._cache[model_cache_key][parameter_set]

    def _load_objects(self, diffsync_model):
        """Given a diffsync model class, load a list of models from the database and return them."""
        parameter_names = diffsync_model.synced_parameters()
        for database_object in diffsync_model._get_queryset():
            self._load_single_object(database_object, diffsync_model, parameter_names)

    def _load_single_object(self, database_object, diffsync_model, parameter_names):
        """Load a single object from the database into the Diffsync store."""
        parameters = {}
        for parameter_name in parameter_names:
            try:
                parameters[parameter_name] = self.get_parameter_value(
                    parameter_name,
                    database_object,
                    diffsync_model,
                )
            except InvalidResponseWarning:
                # These responsees are simply skipped and not added to the parameters var
                pass
        parameters["pk"] = database_object.pk
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
            diffsync_model_child = self.get_diffsync_class(children_parameter)
            for child in children:
                parameter_names = diffsync_model_child.synced_parameters()
                child_diffsync_object = self._load_single_object(child, diffsync_model_child, parameter_names)
                diffsync_model.add_child(child_diffsync_object)

    def load(self):
        """Generic implementation of the load function."""
        if not hasattr(self, "top_level") or not self.top_level:
            raise ValueError("'top_level' needs to be set on the class.")

        for model_name in self.top_level:
            diffsync_model = self.get_diffsync_class(model_name)

            # This function directly mutates the diffsync store, i.e. it will create and load the objects
            # for this specific model class as well as its children without returning anything.
            self._load_objects(diffsync_model)

    def _handle_typed_dict(self, inner_type, related_object):
        """Handle a typed dict for many to many relationships.

        Args:
            inner_type: The typed dict.
            related_object: The related object
        Returns: The dictionary representation of `related_object` as described by `inner_type`.
        """
        dictionary_representation = {}
        for field_name in get_type_hints(inner_type):
            if "__" in field_name:
                dictionary_representation[field_name] = self._param_foreign_key_value(name=field_name, db_obj=related_object)
                continue
            dictionary_representation[field_name] = getattr(related_object, field_name)
        return dictionary_representation

    ###########################
    # Parameter-Based Methods #
    ###########################
    
    def get_parameter_value(self, parameter_name, database_object, diffsync_model):
        """Handle a single parameter for a model."""
        model_type_hints = get_type_hints(diffsync_model, include_extras=True)
        metadata_for_this_field = getattr(model_type_hints[parameter_name], "__metadata__", [])

        # Check for custom handling of the method
        _custom_parameter_method = f"load_param_{parameter_name}"
        if hasattr(self, _custom_parameter_method):
            return getattr(self, _custom_parameter_method)(
                parameter_name,
                database_object,
                metadata=annotation,
                diffsync_model=diffsync_model,
            )

        param_type, annotation = self._get_parameter_meta(parameter_name, metadata_for_this_field, diffsync_model)
        return getattr(self, f"_param_{param_type}_value")(
            name=parameter_name,
            annotation=annotation,
            db_obj=database_object,
            diffsync_model=diffsync_model,
        )

    def _get_parameter_meta(self, param_name, metadata, diffsync_model) -> tuple[ParameterType, dict]:
        """Get parameter type and metadata (if applicable)."""
        # 1: Check if custom field or custom relationship
        for entry in metadata:
            if isinstance(entry, CustomFieldAnnotation):
                return ParameterType.CUSTOM_FIELD, entry
            if isinstance(entry, CustomRelationshipAnnotation):
                if "__" in param_name:
                    param_type = ParameterType.CUSTOM_FOREIGN_KEY
                else:
                    param_type = ParameterType.CUSTOM_MANY_RELATIONSHIP
                return param_type, entry

        # 2: Check for other parameter types
        if "__" in param_name:
            return ParameterType.FOREIGN_KEY, None

        database_field = diffsync_model._model._meta.get_field(param_name)
        if database_field.many_to_many or database_field.one_to_many:
            return ParameterType.MANY_RELATIONSHIP, None
        return ParameterType.STANDARD, None

    def _construct_relationship_association_parameters(self, annotation, database_object):
        relationship = self.get_from_orm_cache({"label": annotation.name}, Relationship)
        relationship_association_parameters = {
            "relationship": relationship,
            "source_type": relationship.source_type,
            "destination_type": relationship.destination_type,
        }
        if annotation.side == RelationshipSideEnum.SOURCE:
            relationship_association_parameters["source_id"] = database_object.id
        else:
            relationship_association_parameters["destination_id"] = database_object.id
        return relationship_association_parameters

    def _param_standard_value(self, name, db_obj, *args, **kwargs):
        return getattr(db_obj, name)

    def _param_custom_field_value(self, annotation, db_obj, *args, **kwargs):
        if annotation.name not in db_obj.cf:
            raise InvalidResponseWarning
        return db_obj.cf[annotation.key]

    def _param_foreign_key_value(self, name, db_obj, *args, **kwargs):
        """Handle a single foreign key field.

        Given the object from the database as well as the name of parameter in the form of
        f'{foreign_key_field_name}__{remote_field_name}'
        return the field at 'remote_field_name' on the object behind the foreign key at 'foreign_key_field_name'.

        Furthermore, 'remote_field_name' may be a series of '__' delimited lookups.

        :param database_object: The Django ORM database object
        :param parameter_name: The field name of the specific relationship to handle
        :return: If present, the object behind the (generic) foreign key, else None
        """
        related_model, *lookups = name.split("__")
        related_object = getattr(db_obj, related_model)

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
    
    def _param_custom_foreign_key_value(self, name, annotation, db_obj, *args, **kwargs):
        """Handle a single custom relationship foreign key field."""
        relationship_association_parameters = self._construct_relationship_association_parameters(
            annotation, db_obj
        )

        relationship_association = RelationshipAssociation.objects.filter(**relationship_association_parameters)
        amount_of_relationship_associations = relationship_association.count()
        if amount_of_relationship_associations == 0:
            return None
        if amount_of_relationship_associations == 1:
            association = relationship_association.first()
            related_object = getattr(
                association, "source" if annotation.side == RelationshipSideEnum.DESTINATION else "destination"
            )
            # Discard the first part as there is no actual field on the model corresponding to that part.
            _, *lookups = name.split("__")
            for lookup in lookups[:-1]:
                related_object = getattr(related_object, lookup)
            return getattr(related_object, lookups[-1])
        raise ValueError("Foreign key custom relationship matched two associations - this shouldn't happen.")

    def _param_many_relationship_value(self, name, db_obj, diffsync_model, *args, **kwargs):
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
        inner_type = get_args(get_type_hints(diffsync_model)[name])[0]
        related_objects_list = []
        # TODO: Allow for filtering, i.e. not taking into account all the objects behind the relationship.
        for related_object in getattr(db_obj, name).all():
            dictionary_representation = self._handle_typed_dict(inner_type, related_object)
            # Only use those where there is a single field defined, all 'None's will not help us.
            if any(dictionary_representation.values()):
                related_objects_list.append(dictionary_representation)
        return related_objects_list
        
    def _param_custom_many_relationship_value(self, name, annotation, db_obj, diffsync_model, *args, **kwargs):
        # Introspect type annotations to deduce which fields are of interest
        # for this many-to-many relationship.
        diffsync_field_type = get_type_hints(diffsync_model)[name]
        inner_type = get_args(diffsync_field_type)[0]

        # TODO: Allow for filtering, i.e. not taking into account all the objects behind the relationship.
        relationship = self.get_from_orm_cache({"label": annotation.name}, Relationship)
        relationship_association_parameters = self._construct_relationship_association_parameters(
            annotation, db_obj
        )
        relationship_associations = RelationshipAssociation.objects.filter(**relationship_association_parameters)
        
        # Initialize Return Object: List of related objects
        related_objects_list = []
        for association in relationship_associations:
            related_object = getattr(
                association, "source" if annotation.side == RelationshipSideEnum.DESTINATION else "destination"
            )
            dictionary_representation = self._handle_typed_dict(inner_type, related_object)
            # Only use those where there is a single field defined, all 'None's will not help us.
            if any(dictionary_representation.values()):
                related_objects_list.append(dictionary_representation)

        # For one-to-many, we need to return an object, not a list of objects
        if (
            relationship.type == RelationshipTypeChoices.TYPE_ONE_TO_MANY
            and annotation.side == RelationshipSideEnum.DESTINATION
        ):
            if not related_objects_list:
                return None

            if len(related_objects_list) == 1:
                return related_objects_list[0]

            raise ObjectCrudException(
                f"More than one related objects for a {RelationshipTypeChoices.TYPE_ONE_TO_MANY} relationship: {related_objects_list}"
            )

        return related_objects_list
