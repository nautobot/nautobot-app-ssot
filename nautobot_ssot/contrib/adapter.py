"""Base adapter module for interfacing with Nautobot in SSoT."""

# pylint: disable=protected-access
# Diffsync relies on underscore-prefixed attributes quite heavily, which is why we disable this here.

import warnings
from typing import Dict, Type, get_args

import pydantic
from diffsync import DiffSync
from diffsync.exceptions import ObjectCrudException
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras.models import Relationship, RelationshipAssociation
from nautobot.extras.models.metadata import MetadataType
from typing_extensions import get_type_hints

from nautobot_ssot.contrib.types import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    RelationshipSideEnum,
)
from nautobot_ssot.utils.cache import ORMCache
from nautobot_ssot.utils.orm import load_typed_dict, orm_attribute_lookup


class NautobotAdapter(DiffSync):
    """
    Adapter for loading data from Nautobot through the ORM.

    This adapter is able to infer how to load data from Nautobot based on how the models attached to it are defined.
    """

    def __init__(self, *args, job, sync=None, **kwargs):
        """Instantiate this class, but do not load data immediately from the local system."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.cache: ORMCache = kwargs.pop("cache", ORMCache())
        self.metadata_type = None
        self.metadata_scope_fields = {}

    def get_from_orm_cache(self, parameters: Dict, model_class: Type[Model]):
        """Retrieve an object from the ORM or the cache."""
        return self.cache.get_from_orm(model_class, parameters)

    @staticmethod
    def _get_parameter_names(diffsync_model):
        """Ignore the differences between identifiers and attributes, because at this point they don't matter to us."""
        return list(diffsync_model._identifiers) + list(diffsync_model._attributes)  # pylint: disable=protected-access

    def _load_objects(self, diffsync_model):
        """Given a diffsync model class, load a list of models from the database and return them."""
        parameter_names = self._get_parameter_names(diffsync_model)
        for database_object in diffsync_model._get_queryset():
            self._load_single_object(database_object, diffsync_model, parameter_names)

    def _handle_single_parameter(self, parameters, parameter_name, database_object, diffsync_model):
        type_hints = get_type_hints(diffsync_model, include_extras=True)
        # Handle custom fields and custom relationships. See CustomFieldAnnotation and CustomRelationshipAnnotation
        # docstrings for more details.
        is_custom_field = False
        custom_relationship_annotation = None
        metadata_for_this_field = getattr(type_hints[parameter_name], "__metadata__", [])
        for metadata in metadata_for_this_field:
            if isinstance(metadata, CustomFieldAnnotation):
                if metadata.name in database_object.cf:
                    parameters[parameter_name] = database_object.cf[metadata.key]
                is_custom_field = True
                break
            if isinstance(metadata, CustomRelationshipAnnotation):
                custom_relationship_annotation = metadata
                break
        if is_custom_field:
            return

        # Handling of foreign keys where the local side is the many and the remote side the one.
        # Note: This includes the side of a generic foreign key that has the foreign key, i.e.
        # the 'many' side.
        if "__" in parameter_name:
            if custom_relationship_annotation:
                parameters[parameter_name] = self._handle_custom_relationship_foreign_key(
                    database_object, parameter_name, custom_relationship_annotation
                )
            else:
                parameters[parameter_name] = orm_attribute_lookup(database_object, parameter_name)
            return

        # Handling of one- and many-to custom relationship fields:
        if custom_relationship_annotation:
            parameters[parameter_name] = self._handle_custom_relationship_to_many_relationship(
                database_object, diffsync_model, parameter_name, custom_relationship_annotation
            )
            return

        database_field = diffsync_model._model._meta.get_field(parameter_name)

        # Handling of one- and many-to-many non-custom relationship fields.
        # Note: This includes the side of a generic foreign key that constitutes the foreign key,
        # i.e. the 'one' side.
        if database_field.many_to_many or database_field.one_to_many:
            parameters[parameter_name] = self._handle_to_many_relationship(
                database_object, diffsync_model, parameter_name
            )
            return

        # Handling of normal fields - as this is the default case, set the attribute directly.
        if hasattr(self, f"load_param_{parameter_name}"):
            parameters[parameter_name] = getattr(self, f"load_param_{parameter_name}")(parameter_name, database_object)
        else:
            parameters[parameter_name] = getattr(database_object, parameter_name)

    def _load_single_object(self, database_object, diffsync_model, parameter_names):
        """Load a single diffsync object from a single database object."""
        parameters = {}
        for parameter_name in parameter_names:
            self._handle_single_parameter(parameters, parameter_name, database_object, diffsync_model)
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

    def _handle_custom_relationship_to_many_relationship(
        self, database_object, diffsync_model, parameter_name, annotation
    ):
        # Introspect type annotations to deduce which fields are of interest
        # for this many-to-many relationship.
        diffsync_field_type = get_type_hints(diffsync_model)[parameter_name]
        inner_type = get_args(diffsync_field_type)[0]
        related_objects_list = []
        # TODO: Allow for filtering, i.e. not taking into account all the objects behind the relationship.
        relationship = self.get_from_orm_cache({"label": annotation.name}, Relationship)
        relationship_association_parameters = self._construct_relationship_association_parameters(
            annotation, database_object
        )
        relationship_associations = RelationshipAssociation.objects.filter(**relationship_association_parameters)

        field_name = ""
        field_name += "source" if annotation.side == RelationshipSideEnum.DESTINATION else "destination"
        field_name += "_"
        field_name += (
            relationship.source_type.app_label.lower()
            if annotation.side == RelationshipSideEnum.DESTINATION
            else relationship.destination_type.app_label.lower()
        )
        field_name += "_"
        field_name += (
            relationship.source_type.model.lower()
            if annotation.side == RelationshipSideEnum.DESTINATION
            else relationship.destination_type.model.lower()
        )

        for association in relationship_associations:
            related_object = getattr(
                association, "source" if annotation.side == RelationshipSideEnum.DESTINATION else "destination"
            )
            # dictionary_representation = self._handle_typed_dict(inner_type, related_object)
            dictionary_representation = load_typed_dict(inner_type, related_object)
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

    @classmethod
    def _handle_typed_dict(cls, inner_type, related_object):
        """Handle a typed dict for many to many relationships.

        TODO: Deprecated and to be removed in future version. Use `nautobot_ssot.utils.orm.load_typed_dict` instead.
        """
        warnings.warn(
            "`_handle_typed_dict` is deprecated and will be removed in a future version. "
            "Use `nautobot_ssot.utils.orm.load_typed_dict` instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return load_typed_dict(inner_type, related_object)

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

    def _handle_to_many_relationship(self, database_object, diffsync_model, parameter_name):
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
        inner_type = get_args(get_type_hints(diffsync_model)[parameter_name])[0]
        related_objects_list = []
        # TODO: Allow for filtering, i.e. not taking into account all the objects behind the relationship.
        for related_object in getattr(database_object, parameter_name).all():
            # dictionary_representation = self._handle_typed_dict(inner_type, related_object)
            dictionary_representation = load_typed_dict(inner_type, related_object)
            # Only use those where there is a single field defined, all 'None's will not help us.
            if any(dictionary_representation.values()):
                related_objects_list.append(dictionary_representation)
        return related_objects_list

    def _handle_custom_relationship_foreign_key(
        self, database_object, parameter_name: str, annotation: CustomRelationshipAnnotation
    ):
        """Handle a single custom relationship foreign key field."""
        relationship_association_parameters = self._construct_relationship_association_parameters(
            annotation, database_object
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
            _, *lookups = parameter_name.split("__")
            for lookup in lookups[:-1]:
                related_object = getattr(related_object, lookup)
            return getattr(related_object, lookups[-1])
        raise ValueError("Foreign key custom relationship matched two associations - this shouldn't happen.")

    @staticmethod
    def _handle_foreign_key(database_object, parameter_name):
        """Handle a single foreign key field."""
        warnings.warn(
            "`_handle_foreign_key` is deprecated and will be removed in a future version. "
            "Use `nautobot_ssot.utils.orm.orm_attribute_lookup` instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return orm_attribute_lookup(database_object, parameter_name)

    def get_or_create_metadatatype(self):
        """Retrieve or create a MetadataType object to track the last sync time of this SSoT job."""
        # MetadataType name will be extracted from the Data Source name.
        metadata_type__name = self.job.__class__.Meta.data_source

        # Create a MetadataType of type datetime
        metadata_type, _ = MetadataType.objects.get_or_create(
            name=f"Last sync from {metadata_type__name}",
            defaults={
                "data_type": "datetime",
                "description": f"Timestamp of the last sync from the Data source {metadata_type__name}",
            },
        )

        # Get All diffsync models from adapter's top_level attribute
        diffsync_models = []
        for model_name in self.top_level:
            diffsync_model = self._get_diffsync_class(model_name)
            diffsync_models.append(diffsync_model)
            for children_parameter, _ in diffsync_model._children.items():
                diffsync_model_child = self._get_diffsync_class(model_name=children_parameter)
                diffsync_models.append(diffsync_model_child)

        for diffsync_model in diffsync_models:
            # Get nautobot model from diffsync model
            nautobot_model = diffsync_model._model
            # Attach ContentTypes to MetadataType
            content_type = ContentType.objects.get_for_model(nautobot_model)
            if content_type not in metadata_type.content_types.all():
                metadata_type.content_types.add(content_type)
            # Define scope fields per model
            obj_metadata_scope_fields = list(
                {parameter.split("__", maxsplit=1)[0] for parameter in self._get_parameter_names(diffsync_model)}
            )
            self.metadata_scope_fields[diffsync_model] = obj_metadata_scope_fields

        # Define the metadata type on the adapter so that can be used on the models crud operations
        self.metadata_type = metadata_type
