"""Base adapter module for interfacing with Nautobot in SSoT."""

# pylint: disable=protected-access
# Diffsync relies on underscore-prefixed attributes quite heavily, which is why we disable this here.

import re
from typing import Dict, Type

import pydantic
from diffsync import DiffSync, DiffSyncModel
from diffsync.exceptions import ObjectCrudException
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras.models import Relationship
from nautobot.extras.models.metadata import MetadataType
from typing_extensions import get_type_hints

from nautobot_ssot.contrib.types import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    RelationshipSideEnum,
)
from nautobot_ssot.utils.cache import ORMCache
from nautobot_ssot.utils.orm import (
    get_custom_relationship_associations,
    load_typed_dict,
    orm_attribute_lookup,
)
from nautobot_ssot.utils.typing import get_inner_type


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

    def invalidate_cache(self, zero_out_hits=True):
        """Deprecated, kept for backwards compatibility."""
        self.job.logger.warning(
            "Adapter class method `self.invalidate_cache()` is deprecated and will be removed in a future version. "
            "Use `self.cache.invalidate_cache()` instead."
        )
        self.cache.invalidate_cache(zero_out_hits=zero_out_hits)

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
                field_key = metadata.key or metadata.name
                if field_key in database_object.cf:
                    parameters[parameter_name] = database_object.cf[field_key]
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
        self,
        database_object: Model,
        diffsync_model: DiffSyncModel,
        parameter_name: str,
        annotation: CustomRelationshipAnnotation,
    ):
        # Introspect type annotations to deduce which fields are of interest
        # for this many-to-many relationship.
        inner_type = get_inner_type(diffsync_model, parameter_name)
        # TODO: Allow for filtering, i.e. not taking into account all the objects behind the relationship.
        relationship: Relationship = self.get_from_orm_cache({"label": annotation.name}, Relationship)
        relationship_associations, _ = get_custom_relationship_associations(
            relationship=relationship,
            db_obj=database_object,
            relationship_side=annotation.side,
        )

        related_objects_list = []
        for association in relationship_associations:
            related_object = getattr(
                association, "source" if annotation.side == RelationshipSideEnum.DESTINATION else "destination"
            )
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
        inner_type = get_inner_type(diffsync_model, parameter_name)
        related_objects_list = []
        # TODO: Allow for filtering, i.e. not taking into account all the objects behind the relationship.
        for related_object in getattr(database_object, parameter_name).all():
            dictionary_representation = load_typed_dict(inner_type, related_object)
            # Only use those where there is a single field defined, all 'None's will not help us.
            if any(dictionary_representation.values()):
                related_objects_list.append(dictionary_representation)
        return related_objects_list

    def _handle_custom_relationship_foreign_key(
        self, database_object, parameter_name: str, annotation: CustomRelationshipAnnotation
    ):
        """Handle a single custom relationship foreign key field."""
        relationship_associations, association_count = get_custom_relationship_associations(
            relationship=self.cache.get_from_orm(Relationship, {"label": annotation.name}),
            db_obj=database_object,
            relationship_side=annotation.side,
        )

        if association_count == 0:
            return None
        if association_count > 1:
            self.job.logger.warning(
                f"Foreign key ({database_object.__name__}.{parameter_name}) "
                "custom relationship matched two associations - this shouldn't happen."
            )

        return orm_attribute_lookup(
            getattr(
                relationship_associations.first(),
                "source" if annotation.side == RelationshipSideEnum.DESTINATION else "destination",
            ),
            # Discard the first part of the paramater name as it references the initial related object
            re.sub("^(.*?)__", "", parameter_name),
        )

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
