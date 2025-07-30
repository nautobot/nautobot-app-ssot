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

    def _load_single_object(self, database_object, diffsync_model, parameter_names):
        """Load a single diffsync object from a single database object."""
        parameters = {}
        for parameter_name in parameter_names:
            parameters[parameter_name] = diffsync_model._interfaces[parameter_name].load(database_object)
        parameters["pk"] = database_object.pk
        try:
            diffsync_model = diffsync_model(**parameters)
        except pydantic.ValidationError as error:
            raise ValueError(f"Parameters ({diffsync_model._model}): {parameters}") from error
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
